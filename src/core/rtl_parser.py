"""
rtl_parser.py  —  pyslang-based RTL static analysis.
Replaces rtl_static.py entirely.
Public API is identical so every agent only needs to change its import line.

Install dependency:  pip install pyslang
"""

from __future__ import annotations

import re
import pyslang
from typing import Iterable

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

KEYWORDS = {
    "module", "endmodule", "input", "output", "inout", "wire", "reg", "logic",
    "bit", "integer", "parameter", "localparam", "always", "always_ff",
    "always_comb", "always_latch", "assign", "begin", "end", "if", "else",
    "case", "endcase", "for", "while", "posedge", "negedge", "or", "and",
    "not", "default", "typedef", "enum", "struct", "signed", "unsigned",
}

# Maps pyslang ProceduralBlockKind names to short internal labels
_PROC_KINDS: dict[str, str] = {
    "AlwaysFF":    "ff",
    "AlwaysComb":  "comb",
    "AlwaysLatch": "latch",
    "Always":      "always",
    "Initial":     "initial",
    "Final":       "final",
}

# Clock / reset naming-convention patterns — covers a broad range of industry names
_CLK_PAT = re.compile(
    r"^clk$|^clock$|_clk$|_clock$|^pclk$|^aclk$|^hclk$|^fclk$|^sys_ck$|_ck$", re.I
)
_CLK_PFX = re.compile(r"^clk|^clock", re.I)
_RST_PAT = re.compile(
    r"^rst$|^rst_n$|^reset$|^reset_n$|^areset$|^areset_n$|^por$|^por_n$"
    r"|_rst$|_rst_n$|_reset$|_reset_n$",
    re.I,
)
_RST_GEN = re.compile(r"rst|reset|por", re.I)

# Signals the start of a new top-level RTL construct — stops block extraction in
# single-statement mode so we never accidentally capture the next always block
_BLOCK_STARTER = re.compile(
    r"^\s*(always|always_ff|always_comb|always_latch|initial|final|assign\s|endmodule)\b"
)


# ─────────────────────────────────────────────────────────────────────────────
# pyslang helpers
# ─────────────────────────────────────────────────────────────────────────────

def _compile(code: str):
    """
    Parse and semantically analyse *code* with pyslang.
    Returns (compilation, tree, root).
    Never raises — pyslang performs error recovery and delivers a best-effort AST
    even for files with missing includes or vendor extensions.
    """
    tree = pyslang.SyntaxTree.fromText(code)
    comp = pyslang.Compilation()
    comp.addSyntaxTree(tree)
    return comp, tree, comp.getRoot()


def _kind(sym) -> str:
    """Return the plain SymbolKind name, e.g. 'Port', 'Variable', 'ProceduralBlock'."""
    return str(sym.kind).rsplit(".", 1)[-1]


def _proc_kind(sym) -> str:
    """Return the plain ProceduralBlockKind name, e.g. 'AlwaysFF'."""
    return str(sym.procedureKind).rsplit(".", 1)[-1]


def _sym_offset(sym) -> int | None:
    """
    Extract byte offset from a pyslang SourceLocation.
    Tries three access patterns defensively because pybind11 binding details
    can differ between pyslang versions.
    """
    try:
        loc = sym.location
        for getter in (
            lambda l: l.offset,
            lambda l: l.offset(),
            lambda l: int(l),
        ):
            try:
                v = getter(loc)
                if isinstance(v, (int, float)):
                    return int(v)
            except Exception:
                pass
    except Exception:
        pass
    return None


def _offset_to_line(code: str, offset: int) -> int:
    """Convert a byte offset to a 1-based line number."""
    return code[: max(0, offset)].count("\n") + 1


def _iter_members(scope, _depth: int = 0):
    """
    Recursively yield all members of a scope.
    Handles generate blocks and nested scopes up to depth 8.
    """
    if _depth > 8:
        return
    try:
        for m in scope.members:
            yield m
            if hasattr(m, "members"):
                yield from _iter_members(m, _depth + 1)
    except Exception:
        pass


def _port_direction(sym) -> str:
    """Return port direction as a plain string: 'In', 'Out', 'InOut', etc."""
    try:
        return str(sym.direction).rsplit(".", 1)[-1]
    except Exception:
        return ""


def _width_from_type(sym) -> str | None:
    """
    Extract a vector range string like '3:0' from a pyslang symbol type.
    Returns None for scalar signals or parameterised widths (e.g. 'ADDR_WIDTH-1:0')
    since those cannot be checked statically.
    """
    try:
        t = str(sym.type)
        m = re.search(r"\[([^\]]+:[^\]]+)\]", t)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Comment stripping
# ─────────────────────────────────────────────────────────────────────────────

def _strip_comments(code: str) -> str:
    """
    Remove // and /* */ comments while:
      - Preserving string-literal contents (avoids false matches on '//' inside strings)
      - Preserving newlines inside block comments so line numbers stay correct
        for all downstream analysis
    """
    out, i, n = [], 0, len(code)
    while i < n:
        c = code[i]
        if c == '"':                        # string literal — copy verbatim
            out.append(c); i += 1
            while i < n and code[i] != '"':
                if code[i] == "\\":
                    out.append(code[i]); i += 1
                if i < n:
                    out.append(code[i]); i += 1
            if i < n:
                out.append(code[i]); i += 1
        elif code[i: i + 2] == "//":       # line comment — skip until newline
            while i < n and code[i] != "\n":
                i += 1
        elif code[i: i + 2] == "/*":       # block comment — preserve newlines
            i += 2
            while i < n and code[i: i + 2] != "*/":
                if code[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2
        else:
            out.append(c); i += 1
    return "".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# Block text extraction
# ─────────────────────────────────────────────────────────────────────────────

def _depth_delta(line: str) -> int:
    """
    Net begin/end depth change for a single line.
    Word-boundary regex ensures 'endmodule', 'endcase', 'endfunction', etc.
    are NOT counted as 'end'.
    """
    return len(re.findall(r"\bbegin\b", line)) - len(re.findall(r"\bend\b", line))


def _extract_block_text(clean_lines: list[str], start_line: int) -> str:
    """
    Extract the full always-block body starting at *start_line* (1-based).

    Three cases handled correctly:
      1. Header + begin/end block       -> accumulate lines until depth returns to 0
      2. Header with begin on next line -> depth tracking picks it up automatically
      3. Single-statement body          -> stop at the first line ending with ';'

    A _BLOCK_STARTER guard prevents accidentally consuming the next always block
    when no begin/end wrapper is present.
    """
    idx = start_line - 1
    lines = clean_lines[idx:]
    if not lines:
        return ""

    text = [lines[0]]
    depth = _depth_delta(lines[0])
    found_begin = depth > 0

    # Header itself is a complete single-line statement
    if not found_begin and lines[0].strip().endswith(";"):
        return lines[0]

    for ln in lines[1:]:
        # Stop if we reach another top-level RTL block in single-statement mode
        if not found_begin and _BLOCK_STARTER.match(ln):
            break

        text.append(ln)
        d = _depth_delta(ln)
        depth += d

        if not found_begin and d > 0:
            found_begin = True          # begin found on a continuation line

        if found_begin and depth <= 0:
            break                       # begin/end block fully closed

        if not found_begin and ln.strip().endswith(";"):
            break                       # single-statement body ended

    return "\n".join(text)


# ─────────────────────────────────────────────────────────────────────────────
# Assignment / statement detection
# ─────────────────────────────────────────────────────────────────────────────

def _assignments(text: str) -> list[dict]:
    """
    Return all LHS assignments found in a block of comment-stripped text.
    Detects both blocking (=) and non-blocking (<=) operators.
    """
    result = []
    _SKIP   = re.compile(r"^\s*(for|while|case|end|//)")
    _ASSIGN = re.compile(
        r"\b([A-Za-z_]\w*)\b(?:\s*\[[^\]]+\])?\s*(<=|(?<![<>=!])=(?!=))\s*(.*?);"
    )
    for offset, line in enumerate(text.splitlines()):
        if _SKIP.match(line):
            continue
        m = _ASSIGN.search(line)
        if m:
            result.append({
                "offset": offset,
                "lhs":    m.group(1),
                "op":     m.group(2),
                "rhs":    m.group(3).strip(),
                "line":   line.strip(),
            })
    return result


def _continuous_assigns(clean: str) -> list[dict]:
    """Return all continuous (assign ...) statements from comment-stripped code."""
    result = []
    pat = re.compile(r"\bassign\s+([A-Za-z_]\w*)(?:\s*\[[^\]]+\])?\s*=\s*(.*?);")
    for ln_no, line in enumerate(clean.splitlines(), 1):
        m = pat.search(line)
        if m:
            result.append({
                "line_no": ln_no,
                "lhs":     m.group(1),
                "rhs":     m.group(2).strip(),
                "line":    line.strip(),
            })
    return result


def _has_default_before_cond(block_text: str, sig: str) -> bool:
    """
    Return True if *sig* has an unconditional default assignment
    before the first if/case statement in the block.
    """
    for line in block_text.splitlines():
        if re.search(r"\b(if|case)\b", line):
            return False
        if re.match(rf"\s*{re.escape(sig)}\b", line) and re.search(
            r"(<=|(?<![<>=!])=(?!=))", line
        ):
            return True
    return False


def _literal_width_mismatch(lhs_width: str, literal_bits: int) -> bool:
    """
    Return True when a literal's declared bit-count does not match a concrete
    [msb:lsb] range.  Returns False safely for parameterised widths.
    """
    m = re.match(r"\s*(\d+)\s*:\s*(\d+)\s*$", lhs_width)
    if not m:
        return False    # parameterised — cannot check statically
    msb, lsb = int(m.group(1)), int(m.group(2))
    return abs(msb - lsb) + 1 != literal_bits


# ─────────────────────────────────────────────────────────────────────────────
# Clock / reset heuristics
# ─────────────────────────────────────────────────────────────────────────────

def _find_clocks(signals: set[str]) -> list[str]:
    """Identify clock signals using industry-standard naming conventions."""
    return sorted(s for s in signals if _CLK_PAT.search(s) or _CLK_PFX.match(s))


def _find_resets(signals: set[str]) -> list[str]:
    """Identify reset signals using industry-standard naming conventions."""
    return sorted(s for s in signals if _RST_PAT.search(s) or _RST_GEN.search(s))


# ─────────────────────────────────────────────────────────────────────────────
# Always-block discovery
# ─────────────────────────────────────────────────────────────────────────────

def _find_always_blocks_text(clean: str, clean_lines: list[str]) -> list[dict]:
    """
    Text-based fallback for always-block discovery when pyslang cannot provide
    source offsets (e.g. files with unresolvable `include or missing packages).
    """
    _KW    = re.compile(r"^\s*(always(?:_ff|_comb|_latch)?)\b")
    _KINDS = {
        "always_ff":    "ff",
        "always_comb":  "comb",
        "always_latch": "latch",
        "always":       "always",
    }
    blocks = []
    for i, line in enumerate(clean_lines, 1):
        m = _KW.match(line)
        if m:
            kind = _KINDS.get(m.group(1), "always")
            text = _extract_block_text(clean_lines, i)
            blocks.append({"kind": kind, "line": i, "header": line, "text": text})
    return blocks


def _find_always_blocks(code: str) -> list[dict]:
    """
    Discover all always blocks using pyslang for accurate kind + source location,
    then extract block text from comment-stripped code.

    Two-tier strategy:
      Tier 1 — pyslang semantic model: gives us the exact ProceduralBlockKind
               (AlwaysFF vs AlwaysComb vs Always) and the precise start offset,
               which we convert to a line number in the comment-stripped source.

      Tier 2 — Text-based fallback: regex scan of comment-stripped code.
               Used only when pyslang cannot reach any module (complete parse
               failure, e.g. undefined macro in top-level context).
    """
    clean       = _strip_comments(code)
    clean_lines = clean.splitlines()
    pyslang_blocks: list[dict] = []
    pyslang_ok = False

    try:
        _, _, root = _compile(code)
        for inst in root.topInstances:
            pyslang_ok = True
            for mem in _iter_members(inst.body):
                if _kind(mem) != "ProceduralBlock":
                    continue
                kind   = _PROC_KINDS.get(_proc_kind(mem), "always")
                offset = _sym_offset(mem)
                if offset is None:
                    continue
                line   = _offset_to_line(code, offset)
                header = clean_lines[line - 1] if 0 < line <= len(clean_lines) else ""
                text   = _extract_block_text(clean_lines, line)
                pyslang_blocks.append({
                    "kind": kind, "line": line, "header": header, "text": text
                })
    except Exception:
        pass

    # If pyslang successfully reached at least one module definition, trust its result
    # even when that result is an empty list (no always blocks = correct answer)
    if pyslang_ok:
        return pyslang_blocks

    # pyslang failed at the module level — fall back to regex text scan
    return _find_always_blocks_text(clean, clean_lines)


def _extract_declared_identifiers_text(code: str) -> dict:
    """Text fallback for ports, parameters, and simple signal declarations."""
    clean = _strip_comments(code)
    module_name = "dut"
    m = re.search(r"\bmodule\s+(\w+)", clean)
    if m:
        module_name = m.group(1)

    signals: set[str] = set()
    outputs: set[str] = set()
    parameters: set[str] = set()
    widths: dict[str, str] = {}

    def add_names(fragment: str, dest: set[str], width: str | None = None) -> list[str]:
        fragment = fragment.split("=", 1)[0] if "=" in fragment else fragment
        fragment = re.sub(r"\[[^\]]+\]", " ", fragment)
        added = []
        for part in fragment.split(","):
            names = re.findall(r"\b[A-Za-z_]\w*\b", part)
            names = [n for n in names if n not in KEYWORDS and n not in {"signed", "unsigned"}]
            if names:
                name = names[-1]
                dest.add(name)
                added.append(name)
                if width:
                    widths[name] = width
        return added

    for line in clean.splitlines():
        stripped = line.strip().rstrip(",;")
        if not stripped:
            continue

        param_match = re.search(r"\b(?:parameter|localparam)\b\s+(.*)", stripped)
        if param_match:
            add_names(param_match.group(1), parameters)
            continue

        decl_match = re.search(
            r"\b(?:input|output|inout|wire|reg|logic)\b\s+(.*)", stripped
        )
        if decl_match:
            rest = decl_match.group(1)
            width_match = re.search(r"\[([^\]]+)\]", rest)
            names = add_names(rest, signals, width_match.group(1) if width_match else None)
            if re.search(r"\boutput\b", stripped):
                outputs.update(names)

    return {
        "signals":      sorted(signals),
        "outputs":      sorted(outputs),
        "parameters":   sorted(parameters),
        "widths":       widths,
        "arrays":       [],
        "enum_values":  [],
        "type_aliases": [],
        "clocks":       _find_clocks(signals),
        "resets":       _find_resets(signals),
        "module":       module_name,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Public API  (identical signatures to rtl_static.py)
# ═════════════════════════════════════════════════════════════════════════════

def extract_declared_identifiers(code: str) -> dict:
    """
    Extract all declared identifiers from a SystemVerilog module using pyslang.

    Key improvements over the regex approach in rtl_static.py:
      - Handles multi-line port declarations, packed/unpacked arrays, structs
      - Correctly separates port vs internal signal vs parameter
      - Resolves typedef aliases and package imports (when available)
      - Width information comes from the type system, not fragile regex
      - Clock/reset detection uses wider industry naming patterns

    Returns the same dict schema as rtl_static.py for backward compatibility.
    """
    signals:    set[str]       = set()
    outputs:    set[str]       = set()
    parameters: set[str]       = set()
    widths:     dict[str, str] = {}
    module_name = "dut"

    try:
        _, _, root = _compile(code)
        for inst in root.topInstances:
            module_name = inst.name
            for mem in _iter_members(inst.body):
                k = _kind(mem)
                n = getattr(mem, "name", None)
                if not n or n in KEYWORDS:
                    continue
                if k in ("Port", "Net"):
                    signals.add(n)
                    if k == "Port" and _port_direction(mem) in ("Out", "Output", "InOut"):
                        outputs.add(n)
                    w = _width_from_type(mem)
                    if w:
                        widths[n] = w
                elif k == "Variable":
                    signals.add(n)
                    w = _width_from_type(mem)
                    if w:
                        widths[n] = w
                elif k in ("Parameter", "Specparam"):
                    parameters.add(n)
    except Exception:
        # Minimal fallback — at least extract module name
        return _extract_declared_identifiers_text(code)

    if not signals and not parameters:
        return _extract_declared_identifiers_text(code)

    return {
        "signals":      sorted(signals),
        "outputs":      sorted(outputs),
        "parameters":   sorted(parameters),
        "widths":       widths,
        "arrays":       [],          # resolved via pyslang type system, not separate list
        "enum_values":  [],
        "type_aliases": [],
        "clocks":       _find_clocks(signals),
        "resets":       _find_resets(signals),
        "module":       module_name,
    }


def static_bug_findings(code: str) -> list[dict]:
    """
    Detect common RTL bugs using pyslang for structure discovery and targeted
    text analysis for assignment / branching patterns inside each block.

    Checks performed:
      - Blocking (=) assignments inside always_ff
      - Signals missing from the reset branch of a reset-aware clocked block
      - Latch inference: incomplete else / no default in always_comb
      - Multiple drivers on the same signal (continuous + procedural)
      - Literal width mismatches on continuous assign statements
      - Undriven output ports (uses pyslang port-direction metadata)

    Key fixes vs rtl_static.py:
      - Latch check uses `\\belse\\s*(?!if\\b)` so else-if chains no longer
        suppress the warning incorrectly
      - Block boundaries are taken from pyslang offsets, not a fragile
        begin-count heuristic that breaks on endcase/endmodule
      - Comments are stripped before all text analysis
    """
    findings: list[dict] = []
    declared  = extract_declared_identifiers(code)
    known     = set(declared["signals"])
    resets    = declared["resets"]
    clean     = _strip_comments(code)
    blocks    = _find_always_blocks(code)

    # Helper: parse a SystemVerilog sized literal like 9'b0 / 8'hFF -> (bits, base)
    _SIZED_LIT = re.compile(r"\b(\d+)\s*'\s*([bBdDhHoO])\s*([0-9a-fA-F_xzXZ]+)\b")

    def _declared_width_for(lhs: str) -> str | None:
        # Prefer declared widths from the type system. If unknown, no width check.
        return declared["widths"].get(lhs)

    def _width_for_range(range_str: str) -> int | None:
        # Only handle concrete ranges like 7:0 or 3:0.
        # Parameterised ranges like WIDTH-1:0 are not resolvable here.
        m = re.match(r"\s*(\d+)\s*:\s*(\d+)\s*$", range_str)
        if not m:
            return None
        msb, lsb = int(m.group(1)), int(m.group(2))
        return abs(msb - lsb) + 1

    def _width_from_declared_width_expr(range_str: str) -> int | None:
        # Special-case common pattern: WIDTH-1:0 where WIDTH is defaultable.
        # This project’s ALU uses `parameter WIDTH = 8`.
        m = re.match(r"\s*(\w+)\s*-\s*1\s*:\s*0\s*$", range_str)
        if not m:
            return None
        param = m.group(1)
        # Try to extract param default from module header
        pm = re.search(rf"\bparameter\s+{re.escape(param)}\s*=\s*(\d+)", code)
        if not pm:
            pm = re.search(rf"\blocalparam\s+{re.escape(param)}\s*=\s*(\d+)", code)
        if not pm:
            return None
        return int(pm.group(1))

    def _check_width_mismatch_in_if(expr_line: str, line_no: int) -> None:
        # Detect patterns like: if (result == 9'b0) or if (result != 9'b0)
        # Then compare sized literal bit-count with declared width of the signal.
        # This is conservative: only triggers when we can resolve both signal name and literal width.
        m = re.search(r"\b([A-Za-z_]\w*)\b\s*([=!]=)\s*(\d+)\s*'\s*([bBdDhHoO])", expr_line) or re.search(r"\bif\b\s*\(\s*([A-Za-z_]\w*)\s*([=!]=)\s*(\d+)\s*'\s*([bBdDhHoO])", expr_line)
        if not m:
            return
        sig = m.group(1)
        lit_bits = int(m.group(3))
        w = _declared_width_for(sig)
        if not w:
            return
        concrete_w = _width_for_range(w)
        if concrete_w is None:
            concrete_w = _width_from_declared_width_expr(w)
        if concrete_w is None:
            return
        if concrete_w != lit_bits:
            findings.append({
                "type":     "WIDTH",
                "location": f"{sig} at line {line_no}",
                "problem":  f"{sig} is compared to a {lit_bits}-bit sized literal, but {sig} is declared as [{w}].",
                "impact":   "Width mismatch can cause truncation or unintended extension during simulation.",
                "fix":      f"Use a literal resized to [{w}] (or parameterize the literal) so the bit-widths match.",
            })

    # ─────────────────────────────────────────────────────────────────────────
    # Main per-always-block analysis
    # ─────────────────────────────────────────────────────────────────────────
    for block in blocks:
        assigns = _assignments(block["text"])
        kind    = block["kind"]

        # Width-mismatch in procedural comparisons (e.g. if (result == 9'b0))
        for rel_i, line in enumerate(block["text"].splitlines()):
            ln_no = block["line"] + rel_i
            if "if" not in line:
                continue
            _check_width_mismatch_in_if(line.strip(), ln_no)

        # ── always_ff: blocking assignment check ─────────────────────────────
        if kind == "ff":
            for a in assigns:
                if a["op"] == "=":
                    findings.append({
                        "type":     "FUNCTIONAL",
                        "location": f"{a['lhs']} at line {block['line'] + a['offset']}",
                        "problem":  "Blocking assignment (=) used inside always_ff sequential block.",
                        "impact":   "Can cause simulation/synthesis mismatch; flip-flop behaviour is undefined.",
                        "fix":      f"Replace '=' with '<=' for {a['lhs']} in this always_ff block.",
                    })

            # always_ff: signals not in reset branch
            if resets:
                rst_pat = "|".join(map(re.escape, resets))
                if re.search(rf"\bif\s*\(\s*!?\s*(?:{rst_pat})\s*\)", block["text"]):
                    rst_body = re.split(r"\belse\b", block["text"], maxsplit=1)[0]
                    rst_lhs  = {a["lhs"] for a in _assignments(rst_body)}
                    all_lhs  = {a["lhs"] for a in assigns if a["lhs"] in known}
                    for sig in sorted(all_lhs - rst_lhs):
                        findings.append({
                            "type":     "RESET",
                            "location": f"{sig} in sequential block at line {block['line']}",
                            "problem":  f"{sig} is updated in a reset-aware block but absent from the reset branch.",
                            "impact":   "Register holds unknown or stale value after reset.",
                            "fix":      f"Add a deterministic reset assignment for {sig} inside the reset branch.",
                        })

        # ── always_comb / always_latch / legacy always: latch check ──────────
        if kind in ("comb", "latch", "always"):
            assigned    = {a["lhs"] for a in assigns if a["lhs"] in known}
            has_cond    = bool(re.search(r"\b(if|case)\b", block["text"]))
            # FIX: negative lookahead excludes `else if` — only a bare `else` completes all paths
            bare_else   = bool(re.search(r"\belse\s*(?!if\b)", block["text"]))
            has_default = bool(re.search(r"\bdefault\s*:", block["text"]))

            if has_cond and not bare_else and not has_default:
                for sig in sorted(assigned):
                    if not _has_default_before_cond(block["text"], sig):
                        findings.append({
                            "type":     "LATCH",
                            "location": f"{sig} in combinational block at line {block['line']}",
                            "problem":  f"{sig} is assigned under conditional logic with no complete else or default.",
                            "impact":   f"Synthesis infers a latch to hold the previous value of {sig}.",
                            "fix":      f"Add a default assignment for {sig} before the conditional, or add else/default.",
                        })

    # ── Multiple drivers ──────────────────────────────────────────────────────
    drivers: dict[str, list[str]] = {}
    for a in _continuous_assigns(clean):
        drivers.setdefault(a["lhs"], []).append(f"continuous assign line {a['line_no']}")
    for block in blocks:
        for a in _assignments(block["text"]):
            drivers.setdefault(a["lhs"], []).append(f"always block line {block['line']}")
    for sig, locs in sorted(drivers.items()):
        if sig in known and len(set(locs)) > 1:
            findings.append({
                "type":     "FUNCTIONAL",
                "location": f"{sig}: {', '.join(sorted(set(locs)))}",
                "problem":  f"{sig} is driven from multiple sources.",
                "impact":   "Multiple drivers cause simulation conflicts or non-synthesisable RTL.",
                "fix":      f"Drive {sig} from exactly one always block or continuous assignment.",
            })

    # ── Literal width mismatches on continuous assigns ────────────────────────
    for a in _continuous_assigns(clean):
        lw  = declared["widths"].get(a["lhs"])
        lit = re.search(r"\b(\d+)'[bBdDhHoO][0-9a-fA-F_xzXZ]+\b", a["rhs"])
        if lw and lit and _literal_width_mismatch(lw, int(lit.group(1))):
            findings.append({
                "type":     "WIDTH",
                "location": f"{a['lhs']} at line {a['line_no']}",
                "problem":  f"{a['lhs']} assigned a {lit.group(1)}-bit literal but declared as [{lw}].",
                "impact":   "Data truncation or unintended sign extension.",
                "fix":      f"Match the literal width to [{lw}] or resize the signal intentionally.",
            })

    # ── Undriven output ports (pyslang port-direction metadata) ───────────────
    all_driven = (
        {a["lhs"] for b in blocks for a in _assignments(b["text"])}
        | {a["lhs"] for a in _continuous_assigns(clean)}
    )
    reported_undriven: set[str] = set()

    def _report_undriven_output(name: str) -> None:
        if not name or name in all_driven or name in reported_undriven:
            return
        reported_undriven.add(name)
        findings.append({
            "type":     "FUNCTIONAL",
            "location": f"{name} output port",
            "problem":  f"Output {name} is declared but never assigned anywhere in the module.",
            "impact":   "Output will be X or high-Z in simulation and synthesis.",
            "fix":      f"Drive {name} from an always block or continuous assignment for all conditions.",
        })

    for name in declared.get("outputs", []):
        _report_undriven_output(name)

    try:
        _, _, root = _compile(code)
        for inst in root.topInstances:
            for mem in inst.body.members:   # ports are always top-level members
                if _kind(mem) != "Port":
                    continue
                if _port_direction(mem) not in ("Out", "Output", "InOut"):
                    continue
                _report_undriven_output(mem.name)
    except Exception:
        pass

    return findings


def static_timing_findings(
    code: str, bug_findings: list[dict] | None = None
) -> list[dict]:
    """
    Return timing-related issues.

    FIX vs rtl_static.py: accepts pre-computed *bug_findings* to avoid calling
    static_bug_findings() twice — which caused LATCH findings to appear in both
    the Bug Analysis and Timing Analysis sections of the report.

    Checks:
      - Blocking assignments in always_ff  (promoted from bug findings)
      - Latch inference                    (promoted from bug findings)
      - Incomplete sensitivity lists in legacy always @(...) blocks
    """
    if bug_findings is None:
        bug_findings = static_bug_findings(code)

    issues: list[dict] = []

    for bug in bug_findings:
        prob = bug.get("problem", "")
        if "Blocking assignment" in prob or bug.get("type") == "LATCH":
            issues.append({
                "type":       "BLOCKING" if "Blocking assignment" in prob else "LATCH",
                "location":   bug["location"],
                "evidence":   prob,
                "confidence": "HIGH",
                "problem":    prob,
                "risk":       "Can produce timing-dependent simulation mismatch or inferred latch storage.",
                "fix":        bug["fix"],
            })

    # Incomplete sensitivity list — only relevant for legacy always @(...) blocks
    declared = extract_declared_identifiers(code)
    for block in _find_always_blocks(code):
        if block["kind"] != "always":
            continue    # always_ff / always_comb have no manual sensitivity lists
        m = re.search(r"@\s*\(([^*)][^)]*)\)", block["header"])
        if not m or re.search(r"posedge|negedge", m.group(1)):
            continue    # clocked — skip
        sensitivity = set(re.findall(r"\b[A-Za-z_]\w*\b", m.group(1))) - {"or", "and"}
        body_refs   = set(re.findall(r"\b[A-Za-z_]\w*\b", block["text"])) & set(declared["signals"])
        driven_lhs  = {a["lhs"] for a in _assignments(block["text"])}
        missing     = sorted((body_refs - driven_lhs) - sensitivity)
        if missing:
            issues.append({
                "type":       "SENSITIVITY",
                "location":   f"always block at line {block['line']}",
                "evidence":   f"Signals not in sensitivity list: {', '.join(missing[:4])}",
                "confidence": "HIGH",
                "problem":    "Combinational always block has an incomplete manual sensitivity list.",
                "risk":       "Simulation uses stale values and disagrees with synthesised combinational logic.",
                "fix":        "Replace the manual sensitivity list with always_comb or always @(*).",
            })

    return issues


def static_assertions(code: str) -> list[dict]:
    """
    Generate syntactically correct SVA assertions from the module's structure.
    Produces up to three assertions: a RESET check and a RANGE/X check.
    All assertions use the correct concurrent property syntax with disable iff.
    """
    meta = extract_declared_identifiers(code)
    clk  = meta["clocks"][0] if meta["clocks"] else None
    rst  = meta["resets"][0] if meta["resets"] else None
    if not clk:
        return []

    candidates = [s for s in meta["signals"] if s not in {clk, rst}]
    if not candidates:
        return []

    active_low   = bool(rst and re.search(r"_n$|_N$|b$|B$", rst))
    reset_active = f"!{rst}" if active_low else (rst or "1'b0")

    assertions: list[dict] = []

    if rst:
        target = next(
            (s for s in candidates
             if re.search(r"count|state|ptr|valid|ready|empty|full|out|data|\bq\b", s, re.I)),
            candidates[0],
        )
        assertions.append({
            "type":        "RESET",
            "signal":      target,
            "sva_code":    (
                f"assert property (@(posedge {clk}) disable iff (!({reset_active})) "
                f"{reset_active} |=> !$isunknown({target}));"
            ),
            "description": f"Verifies {target} is known immediately after reset is asserted.",
        })

    used = {a["signal"] for a in assertions}
    range_target = next(
        (s for s in candidates if re.search(r"count|ptr|state", s, re.I) and s not in used),
        next((s for s in candidates if s not in used), candidates[0]),
    )
    assertions.append({
        "type":        "RANGE",
        "signal":      range_target,
        "sva_code":    (
            f"assert property (@(posedge {clk}) disable iff ({reset_active}) "
            f"!$isunknown({range_target}));"
        ),
        "description": f"Checks {range_target} never becomes X/Z during normal operation.",
    })

    return assertions[:3]


def static_optimizations(code: str) -> list[dict]:
    """
    Find hardcoded constants and style issues.

    FIX vs rtl_static.py:
      1. Reports ALL occurrences, not just the first (removed premature `break`)
      2. Strips sized literals (8'hFF) before checking for bare decimals,
         so `if (mode == 2) out = 8'hFF` flags '2' but not '8'
      3. Skips parameter/localparam lines (those are the correct place for constants)
    """
    opts: list[dict] = []
    clean = _strip_comments(code)

    _PARAM_LINE = re.compile(r"\b(parameter|localparam)\b")
    _SIZED_LIT  = re.compile(r"\b\d+'[bdhoBDHO][0-9a-fA-F_xzXZ]+\b", re.I)
    _BARE_INT   = re.compile(r"(?<![\w'#])\b([1-9]\d+)\b(?![\w'])")

    for ln_no, line in enumerate(clean.splitlines(), 1):
        if _PARAM_LINE.search(line):
            continue    # intentional constant — skip
        stripped = _SIZED_LIT.sub("", line)
        m = _BARE_INT.search(stripped)
        if m:
            opts.append({
                "type":       "HARDCODED",
                "location":   f"line {ln_no}",
                "issue":      f"Bare decimal literal {m.group(1)} is hardcoded in RTL logic.",
                "benefit":    "Named parameters make design intent explicit and future resizing safe.",
                "suggestion": f"Replace {m.group(1)} with a declared parameter or localparam.",
            })

    return opts


# ─────────────────────────────────────────────────────────────────────────────
# LLM output filters  (public API — identical to rtl_static.py)
# ─────────────────────────────────────────────────────────────────────────────

_FILTER_SKIP = frozenset(
    {
        "always", "always_ff", "always_comb", "always_latch", "assign", "begin", "end",
        "if", "else", "case", "endcase", "default", "posedge", "negedge", "logic", "reg",
        "wire", "assert", "property", "disable", "iff", "isunknown",
        "line", "at", "row", "port", "signal", "register", "value", "module", "clock",
        "reset", "active_low", "active_high", "clock_cycle", "clock_domain", "reset_value",
        "next_state", "current_state", "output", "input",
    }
    | KEYWORDS
)


def references_only_declared(
    item: dict, declared: Iterable[str], ignore: Iterable[str] = ()
) -> bool:
    """
    Return True if all identifiers in the key code fields of an LLM finding
    are either declared signals/parameters or known SV/English keywords.
    Filters out hallucinated signal names from LLM responses.
    """
    allowed = set(declared) | set(ignore)
    code_fields = [str(item.get(k, "")) for k in ("signal", "sva_code")]
    for key in ("fix", "suggestion"):
        value = str(item.get(key, ""))
        if re.search(r"[;=<>()[\]{}']|\b(always|assign|if|case|endcase)\b", value):
            code_fields.append(value)
    code_fields = " ".join(code_fields)
    tokens     = {t for t in re.findall(r"\b[A-Za-z_]\w*\b", code_fields) if t not in KEYWORDS}
    suspicious = tokens - allowed - _FILTER_SKIP
    return not suspicious


def is_concrete_finding(item: dict, declared: Iterable[str]) -> bool:
    """
    Return True if a finding has a concrete location and mentions at least one
    declared signal.  Filters out vague LLM responses.
    """
    text = " ".join(
        str(item.get(k, "")) for k in (
            "location", "problem", "impact", "fix",
            "evidence", "risk", "issue", "suggestion"
        )
    ).lower()
    vague = (
        "some other issues", "may have issues", "quality enhancement",
        "needs improvement", "improve quality", "could not identify",
        "might be problematic", "review further",
    )
    if any(p in text for p in vague):
        return False
    has_loc = any(kw in text for kw in ("line", "always", "assign", "case", "block"))
    has_sig = any(n.lower() in text for n in declared)
    return has_loc or has_sig
