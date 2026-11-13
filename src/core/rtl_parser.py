"""
rtl_parser.py  -  pyslang-based RTL static analysis (with text fallbacks).

Public API is unchanged.  New in this version (see CHANGES at the bottom of
the docstring list):
  extract_declared_identifiers() additionally returns "inputs" and fills
  "arrays" (unpacked arrays / memories).

CHANGES vs previous version
  1. latch check: `else if` no longer counts as a complete `else`
  2. reset/clock detection is token based ("first_valid", "burst_len",
     "report_en" are no longer reset signals; "clk_en" is no longer a clock)
  3. _assignments(): statement based. Fixes lines starting with end*/for*/
     case* identifiers being skipped, `if (a <= b)` parsed as an assignment,
     several statements per line, multi-line statements.
  4. _continuous_assigns(): multi-line assigns
  5. legacy `always @(posedge clk)` is treated as sequential: blocking
     assignments / missing reset are checked, and it is no longer reported
     as a latch
  6. memories (unpacked arrays) are not reported as "missing reset"
  7. extract_clocking_blocks(): `posedge clk or negedge rst_n` now yields
     edge=posedge (it used to yield negedge, so validate_sva_against_rtl
     rejected every LLM assertion on async-reset designs); combinational
     `always @(*)` is no longer treated as clocked
  8. static_assertions(): clock/edge/reset polarity come from the block that
     actually drives the target; inputs and never-reset registers are not
     asserted to be non-X
  9. pyslang import is optional (text fallbacks keep working without it)
 10. extra_check.py heuristics (unused inputs, missing case defaults, width
     literals, multi-bit CDC) are wired into static_bug_findings() and
     static_timing_findings(), and COMMENTS is accepted in
     validate_optimization_against_rtl().
"""

from __future__ import annotations

import re
from typing import Iterable

try:
    import pyslang
except ImportError:          # text fallbacks are used everywhere
    pyslang = None

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

KEYWORDS = {
    "module", "endmodule", "input", "output", "inout", "wire", "reg", "logic",
    "bit", "integer", "parameter", "localparam", "always", "always_ff",
    "always_comb", "always_latch", "assign", "begin", "end", "if", "else",
    "case", "endcase", "for", "while", "posedge", "negedge", "or", "and",
    "not", "default", "typedef", "enum", "struct", "signed", "unsigned",
}

_PROC_KINDS: dict[str, str] = {
    "AlwaysFF": "ff", "AlwaysComb": "comb", "AlwaysLatch": "latch",
    "Always": "always", "Initial": "initial", "Final": "final",
}

_RESET_TOKENS = {
    "rst", "reset", "rstn", "resetn", "arst", "areset", "nrst", "nreset",
    "srst", "sreset", "por", "porn", "rstb", "resetb", "rstz", "resetz",
}
_CLOCK_TOKENS = {"clk", "clock", "ck", "aclk", "pclk", "hclk", "fclk", "sclk"}
_NOT_CLOCK_LAST = {"en", "enable", "sel", "valid", "ready", "cnt", "count",
                   "req", "ack", "stop"}

_BLOCK_STARTER = re.compile(
    r"^\s*(always|always_ff|always_comb|always_latch|initial|final|assign\s|endmodule)\b"
)


def _tokens(name: str) -> list[str]:
    parts = re.split(r"_+|(?<=[a-z0-9])(?=[A-Z])", name)
    return [re.sub(r"\d+$", "", p.lower()) or p.lower() for p in parts if p]


def _is_reset_name(name: str) -> bool:
    return any(t in _RESET_TOKENS for t in _tokens(name))


def _is_clock_name(name: str) -> bool:
    t = _tokens(name)
    return bool(t) and any(x in _CLOCK_TOKENS for x in t) and t[-1] not in _NOT_CLOCK_LAST


def _find_clocks(signals: Iterable[str]) -> list[str]:
    return sorted(s for s in signals if _is_clock_name(s))


def _find_resets(signals: Iterable[str]) -> list[str]:
    return sorted(s for s in signals if _is_reset_name(s))


# --------------------------------------------------------------------------
# pyslang helpers
# --------------------------------------------------------------------------

def _compile(code: str):
    if pyslang is None:
        raise RuntimeError("pyslang not installed")
    tree = pyslang.SyntaxTree.fromText(code)
    comp = pyslang.Compilation()
    comp.addSyntaxTree(tree)
    return comp, tree, comp.getRoot()


def _kind(sym) -> str:
    return str(sym.kind).rsplit(".", 1)[-1]


def _proc_kind(sym) -> str:
    return str(sym.procedureKind).rsplit(".", 1)[-1]


def _sym_offset(sym) -> int | None:
    try:
        loc = sym.location
        for getter in (lambda l: l.offset, lambda l: l.offset(), lambda l: int(l)):
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
    return code[: max(0, offset)].count("\n") + 1


def _iter_members(scope, _depth: int = 0):
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
    try:
        return str(sym.direction).rsplit(".", 1)[-1]
    except Exception:
        return ""


def _width_from_type(sym) -> str | None:
    try:
        m = re.search(r"\[([^\]]+:[^\]]+)\]", str(sym.type))
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------
# Comment stripping / block extraction
# --------------------------------------------------------------------------

def _strip_comments(code: str) -> str:
    """Remove comments, keep string literals and ALL newlines."""
    out, i, n = [], 0, len(code)
    while i < n:
        c = code[i]
        if c == '"':
            out.append(c); i += 1
            while i < n and code[i] != '"':
                if code[i] == "\\":
                    out.append(code[i]); i += 1
                if i < n:
                    out.append(code[i]); i += 1
            if i < n:
                out.append(code[i]); i += 1
        elif code[i: i + 2] == "//":
            while i < n and code[i] != "\n":
                i += 1
        elif code[i: i + 2] == "/*":
            i += 2
            while i < n and code[i: i + 2] != "*/":
                if code[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2
        else:
            out.append(c); i += 1
    return "".join(out)


def _depth_delta(line: str) -> int:
    return len(re.findall(r"\bbegin\b", line)) - len(re.findall(r"\bend\b", line))


def _extract_block_text(clean_lines: list[str], start_line: int) -> str:
    idx = start_line - 1
    lines = clean_lines[idx:]
    if not lines:
        return ""
    text = [lines[0]]
    depth = _depth_delta(lines[0])
    found_begin = depth > 0
    if not found_begin and lines[0].strip().endswith(";"):
        return lines[0]
    for ln in lines[1:]:
        if not found_begin and _BLOCK_STARTER.match(ln):
            break
        text.append(ln)
        d = _depth_delta(ln)
        depth += d
        if not found_begin and d > 0:
            found_begin = True
        if found_begin and depth <= 0:
            break
        if not found_begin and ln.strip().endswith(";"):
            break
    return "\n".join(text)


# --------------------------------------------------------------------------
# Statement level analysis
# --------------------------------------------------------------------------

def _blank(text: str, start: int, end: int, out: list) -> None:
    for k in range(start, min(end, len(out))):
        if out[k] != "\n":
            out[k] = " "


def _blank_constructs(text: str) -> str:
    """Blank `always...@(...)` headers and `if/for/while/case (...)` heads
    (balanced parentheses) so only statements remain.  Length and newlines
    are preserved, so offsets/line numbers stay valid."""
    out = list(text)
    for m in re.finditer(
        r"\balways(?:_ff|_comb|_latch)?\b\s*(?:@\s*\([^)]*\)|@\s*\*)?", text
    ):
        _blank(text, m.start(), m.end(), out)
    for m in re.finditer(
        r"\b(?:if|for|while|foreach|repeat|case|casez|casex)\s*\(", text
    ):
        i = m.end() - 1
        depth, j = 0, i
        while j < len(text):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        _blank(text, m.start(), j + 1, out)
    return "".join(out)


_LEAD = re.compile(
    r"^\s*(?:begin(?:\s*:\s*\w+)?|end(?:\s*:\s*\w+)?(?!\w)|else(?!\w)|endcase(?!\w)"
    r"|default\s*:|[A-Za-z_0-9'`$.]+(?:\s*,\s*[A-Za-z_0-9'`$.]+)*\s*:(?!:))"
)
_STMT = re.compile(
    r"^([A-Za-z_]\w*)((?:\s*\[[^\]]*\])*)\s*(<=|(?<![<>=!])=(?!=))\s*(.*)$", re.DOTALL
)


def _assignments(text: str) -> list[dict]:
    """All procedural assignments in a block of comment-free text.
    Returns dicts: offset (line offset in `text`), lhs, op, rhs, line, indexed."""
    blanked = _blank_constructs(text)
    result = []
    for sm in re.finditer(r"[^;]*;", blanked):
        seg, start = sm.group(0)[:-1], sm.start()
        while True:
            m = _LEAD.match(seg)
            if not m or m.end() == 0:
                break
            start += m.end()
            seg = seg[m.end():]
        stripped = seg.lstrip()
        start += len(seg) - len(stripped)
        am = _STMT.match(stripped)
        if not am:
            continue
        rhs = " ".join(am.group(4).split())
        result.append({
            "offset": text.count("\n", 0, start),
            "lhs": am.group(1),
            "op": am.group(3),
            "rhs": rhs,
            "line": f"{am.group(1)}{am.group(2)} {am.group(3)} {rhs};".strip(),
            "indexed": bool(am.group(2).strip()),
        })
    return result


def _continuous_assigns(clean: str) -> list[dict]:
    result = []
    pat = re.compile(
        r"\bassign\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)*=\s*([^;]*);"
    )
    for m in pat.finditer(clean):
        result.append({
            "line_no": clean.count("\n", 0, m.start()) + 1,
            "lhs": m.group(1),
            "rhs": " ".join(m.group(2).split()),
            "line": " ".join(m.group(0).split()),
        })
    return result


def _unpacked_arrays(clean: str) -> set[str]:
    """Names declared with unpacked dimensions, e.g. `logic [7:0] mem [DEPTH];`"""
    arrays: set[str] = set()
    decl = re.compile(
        r"^\s*(?:logic|reg|bit|wire|byte|int|integer|[A-Za-z_]\w*_t)\b([^;=]*);", re.M
    )
    for m in decl.finditer(clean):
        for name in re.findall(r"\b([A-Za-z_]\w*)\s*\[", m.group(1)):
            arrays.add(name)
    return arrays


def _has_default_before_cond(block_text: str, sig: str) -> bool:
    for line in block_text.splitlines():
        if re.search(r"\b(if|case)\b", line):
            return False
        if re.match(rf"\s*{re.escape(sig)}\b", line) and re.search(
            r"(<=|(?<![<>=!])=(?!=))", line
        ):
            return True
    return False


def _literal_width_mismatch(lhs_width: str, literal_bits: int) -> bool:
    m = re.match(r"\s*(\d+)\s*:\s*(\d+)\s*$", lhs_width)
    if not m:
        return False
    return abs(int(m.group(1)) - int(m.group(2))) + 1 != literal_bits


_SEQ_EVENT = re.compile(r"@\s*\([^)]*\b(?:posedge|negedge)\b")


def _is_sequential(block: dict) -> bool:
    if block["kind"] == "ff":
        return True
    return block["kind"] == "always" and bool(_SEQ_EVENT.search(block.get("header", "")))


def _dedupe_findings(items: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for it in items:
        key = (str(it.get("type", "")).upper(), str(it.get("location", "")))
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


# --------------------------------------------------------------------------
# Always-block discovery
# --------------------------------------------------------------------------

def _find_always_blocks_text(clean: str, clean_lines: list[str]) -> list[dict]:
    kw = re.compile(r"^\s*(always(?:_ff|_comb|_latch)?)\b")
    kinds = {"always_ff": "ff", "always_comb": "comb",
             "always_latch": "latch", "always": "always"}
    blocks = []
    for i, line in enumerate(clean_lines, 1):
        m = kw.match(line)
        if m:
            blocks.append({"kind": kinds.get(m.group(1), "always"), "line": i,
                           "header": line, "text": _extract_block_text(clean_lines, i)})
    return blocks


def _find_always_blocks(code: str) -> list[dict]:
    clean = _strip_comments(code)
    clean_lines = clean.splitlines()
    found: list[dict] = []
    ok = False
    try:
        _, _, root = _compile(code)
        for inst in root.topInstances:
            ok = True
            for mem in _iter_members(inst.body):
                if _kind(mem) != "ProceduralBlock":
                    continue
                kind = _PROC_KINDS.get(_proc_kind(mem), "always")
                off = _sym_offset(mem)
                if off is None:
                    continue
                line = _offset_to_line(code, off)
                header = clean_lines[line - 1] if 0 < line <= len(clean_lines) else ""
                found.append({"kind": kind, "line": line, "header": header,
                              "text": _extract_block_text(clean_lines, line)})
    except Exception:
        pass
    if ok:
        return found
    return _find_always_blocks_text(clean, clean_lines)


# --------------------------------------------------------------------------
# Declared identifiers
# --------------------------------------------------------------------------

def _extract_declared_identifiers_text(code: str) -> dict:
    clean = _strip_comments(code)
    # one port per line, so several ports on a line are parsed separately
    clean = re.sub(r",\s*(?=(?:input|output|inout)\b)", ",\n", clean)
    m = re.search(r"\bmodule\s+(\w+)", clean)
    module_name = m.group(1) if m else "dut"

    signals: set[str] = set()
    outputs: set[str] = set()
    inputs: set[str] = set()
    parameters: set[str] = set()
    widths: dict[str, str] = {}

    def add_names(fragment, dest, width=None):
        fragment = fragment.split("=", 1)[0] if "=" in fragment else fragment
        fragment = re.sub(r"\[[^\]]+\]", " ", fragment)
        added = []
        for part in fragment.split(","):
            names = [n for n in re.findall(r"\b[A-Za-z_]\w*\b", part)
                     if n not in KEYWORDS]
            if names:
                dest.add(names[-1]); added.append(names[-1])
                if width:
                    widths[names[-1]] = width
        return added

    for line in clean.splitlines():
        s = line.strip().rstrip(",;")
        if not s:
            continue
        pm = re.search(r"\b(?:parameter|localparam)\b\s+(.*)", s)
        if pm:
            add_names(pm.group(1), parameters)
            continue
        dm = re.search(r"\b(?:input|output|inout|wire|reg|logic)\b\s+(.*)", s)
        tm = re.match(r"^([A-Za-z_]\w*_t)\s+(.+)$", s)      # typedef'd variables
        if dm or tm:
            rest = dm.group(1) if dm else tm.group(2)
            wm = re.search(r"\[([^\]]+)\]", rest)
            names = add_names(rest, signals, wm.group(1) if wm else None)
            if re.search(r"\boutput\b", s):
                outputs.update(names)
            if re.search(r"\binput\b", s):
                inputs.update(names)

    return {
        "signals": sorted(signals), "outputs": sorted(outputs),
        "inputs": sorted(inputs), "parameters": sorted(parameters),
        "widths": widths, "arrays": sorted(_unpacked_arrays(clean)),
        "enum_values": [], "type_aliases": [],
        "clocks": _find_clocks(signals), "resets": _find_resets(signals),
        "module": module_name,
    }


def extract_declared_identifiers(code: str) -> dict:
    signals: set[str] = set()
    outputs: set[str] = set()
    inputs: set[str] = set()
    parameters: set[str] = set()
    widths: dict[str, str] = {}
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
                    if k == "Port":
                        d = _port_direction(mem)
                        if d in ("Out", "Output", "InOut"):
                            outputs.add(n)
                        if d in ("In", "Input", "InOut"):
                            inputs.add(n)
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
        return _extract_declared_identifiers_text(code)

    if not signals and not parameters:
        return _extract_declared_identifiers_text(code)

    return {
        "signals": sorted(signals), "outputs": sorted(outputs),
        "inputs": sorted(inputs), "parameters": sorted(parameters),
        "widths": widths, "arrays": sorted(_unpacked_arrays(_strip_comments(code))),
        "enum_values": [], "type_aliases": [],
        "clocks": _find_clocks(signals), "resets": _find_resets(signals),
        "module": module_name,
    }


# ==========================================================================
# Public API
# ==========================================================================

def static_bug_findings(code: str) -> list[dict]:
    findings: list[dict] = []
    declared = extract_declared_identifiers(code)
    known = set(declared["signals"])
    arrays = set(declared.get("arrays", []))
    resets = declared["resets"]
    clean = _strip_comments(code)
    blocks = _find_always_blocks(code)

    def _width_for_range(r: str) -> int | None:
        m = re.match(r"\s*(\d+)\s*:\s*(\d+)\s*$", r)
        return abs(int(m.group(1)) - int(m.group(2))) + 1 if m else None

    def _width_from_param_expr(r: str) -> int | None:
        m = re.match(r"\s*(\w+)\s*-\s*1\s*:\s*0\s*$", r)
        if not m:
            return None
        p = re.search(rf"\b(?:parameter|localparam)\s+(?:\w+\s+)?{re.escape(m.group(1))}\s*=\s*(\d+)", code)
        return int(p.group(1)) if p else None

    def _check_width_in_if(expr_line: str, line_no: int) -> None:
        m = re.search(r"\b([A-Za-z_]\w*)\b\s*([=!]=)\s*(\d+)\s*'\s*[bBdDhHoO]", expr_line)
        if not m:
            return
        sig, lit_bits = m.group(1), int(m.group(3))
        w = declared["widths"].get(sig)
        if not w:
            return
        cw = _width_for_range(w)
        if cw is None:
            cw = _width_from_param_expr(w)
        if cw is not None and cw != lit_bits:
            findings.append({
                "type": "WIDTH",
                "location": f"{sig} at line {line_no}",
                "problem": f"{sig} is compared to a {lit_bits}-bit sized literal, but {sig} is declared as [{w}].",
                "impact": "Width mismatch can cause truncation or unintended extension during simulation.",
                "fix": f"Use a literal resized to [{w}] (or parameterize the literal) so the bit-widths match.",
            })

    for block in blocks:
        assigns = _assignments(block["text"])
        seq = _is_sequential(block)

        for rel, line in enumerate(block["text"].splitlines()):
            if re.search(r"\bif\b", line):
                _check_width_in_if(line.strip(), block["line"] + rel)

        if seq:
            for a in assigns:
                if a["op"] == "=":
                    findings.append({
                        "type": "FUNCTIONAL",
                        "location": f"{a['lhs']} at line {block['line'] + a['offset']}",
                        "problem": "Blocking assignment (=) used inside clocked sequential block.",
                        "impact": "Can cause simulation/synthesis mismatch; flip-flop behaviour is undefined.",
                        "fix": f"Replace '=' with '<=' for {a['lhs']} in this clocked block.",
                    })
            if resets:
                rst_pat = "|".join(map(re.escape, resets))
                if re.search(rf"\bif\s*\(\s*!?\s*(?:{rst_pat})\s*\)", block["text"]):
                    rst_body = re.split(r"\belse\b", block["text"], maxsplit=1)[0]
                    rst_lhs = {a["lhs"] for a in _assignments(rst_body)}
                    all_lhs = {a["lhs"] for a in assigns
                               if a["lhs"] in known and a["lhs"] not in arrays}
                    for sig in sorted(all_lhs - rst_lhs):
                        findings.append({
                            "type": "RESET",
                            "location": f"{sig} in sequential block at line {block['line']}",
                            "problem": f"{sig} is updated in a reset-aware block but absent from the reset branch.",
                            "impact": "Register holds unknown or stale value after reset.",
                            "fix": f"Add a deterministic reset assignment for {sig} inside the reset branch.",
                        })
        elif block["kind"] in ("comb", "latch", "always"):
            assigned = {a["lhs"] for a in assigns if a["lhs"] in known}
            has_cond = bool(re.search(r"\b(if|case)\b", block["text"]))
            # `else` NOT followed by `if` (an else-if chain is not a complete else)
            bare_else = bool(re.search(r"\belse\b(?!\s+if\b)", block["text"]))
            has_default = bool(re.search(r"\bdefault\s*:", block["text"]))
            if has_cond and not bare_else and not has_default:
                for sig in sorted(assigned):
                    if not _has_default_before_cond(block["text"], sig):
                        findings.append({
                            "type": "LATCH",
                            "location": f"{sig} in combinational block at line {block['line']}",
                            "problem": f"{sig} is assigned under conditional logic with no complete else or default.",
                            "impact": f"Synthesis infers a latch to hold the previous value of {sig}.",
                            "fix": f"Add a default assignment for {sig} before the conditional, or add else/default.",
                        })

    # multiple drivers
    drivers: dict[str, list[str]] = {}
    for a in _continuous_assigns(clean):
        drivers.setdefault(a["lhs"], []).append(f"continuous assign line {a['line_no']}")
    for block in blocks:
        for a in _assignments(block["text"]):
            drivers.setdefault(a["lhs"], []).append(f"always block line {block['line']}")
    for sig, locs in sorted(drivers.items()):
        if sig in known and len(set(locs)) > 1:
            findings.append({
                "type": "FUNCTIONAL",
                "location": f"{sig}: {', '.join(sorted(set(locs)))}",
                "problem": f"{sig} is driven from multiple sources.",
                "impact": "Multiple drivers cause simulation conflicts or non-synthesisable RTL.",
                "fix": f"Drive {sig} from exactly one always block or continuous assignment.",
            })

    # literal width mismatch on continuous assigns
    for a in _continuous_assigns(clean):
        lw = declared["widths"].get(a["lhs"])
        lit = re.search(r"\b(\d+)'[bBdDhHoO][0-9a-fA-F_xzXZ]+\b", a["rhs"])
        if lw and lit and _literal_width_mismatch(lw, int(lit.group(1))):
            findings.append({
                "type": "WIDTH",
                "location": f"{a['lhs']} at line {a['line_no']}",
                "problem": f"{a['lhs']} assigned a {lit.group(1)}-bit literal but declared as [{lw}].",
                "impact": "Data truncation or unintended sign extension.",
                "fix": f"Match the literal width to [{lw}] or resize the signal intentionally.",
            })

    # undriven outputs
    all_driven = ({a["lhs"] for b in blocks for a in _assignments(b["text"])}
                  | {a["lhs"] for a in _continuous_assigns(clean)})
    for name in declared.get("outputs", []):
        if name not in all_driven:
            findings.append({
                "type": "FUNCTIONAL",
                "location": f"{name} output port",
                "problem": f"Output {name} is declared but never assigned anywhere in the module.",
                "impact": "Output will be X or high-Z in simulation and synthesis.",
                "fix": f"Drive {name} from an always block or continuous assignment for all conditions.",
            })

    # extra deterministic checks (unused inputs, case without default, width literals, multi-bit CDC)
    try:
        from src.core.extra_check import bug_extras
        findings.extend(bug_extras(code))
    except ImportError:
        pass

    return _dedupe_findings(findings)


def static_timing_findings(code: str, bug_findings: list[dict] | None = None) -> list[dict]:
    """Timing view of the static findings.  NOTE: blocking-assignment and LATCH
    findings intentionally appear in BOTH the bug and the timing report; pass
    `bug_findings` to avoid recomputing them."""
    if bug_findings is None:
        bug_findings = static_bug_findings(code)
    issues: list[dict] = []
    for bug in bug_findings:
        prob = bug.get("problem", "")
        if "Blocking assignment" in prob or bug.get("type") == "LATCH":
            issues.append({
                "type": "BLOCKING" if "Blocking assignment" in prob else "LATCH",
                "location": bug["location"], "evidence": prob, "confidence": "HIGH",
                "problem": prob,
                "risk": "Can produce timing-dependent simulation mismatch or inferred latch storage.",
                "fix": bug["fix"],
            })
    declared = extract_declared_identifiers(code)
    for block in _find_always_blocks(code):
        if block["kind"] != "always":
            continue
        m = re.search(r"@\s*\(([^*)][^)]*)\)", block["header"])
        if not m or re.search(r"posedge|negedge", m.group(1)):
            continue
        sens = set(re.findall(r"\b[A-Za-z_]\w*\b", m.group(1))) - {"or", "and"}
        refs = set(re.findall(r"\b[A-Za-z_]\w*\b", block["text"])) & set(declared["signals"])
        driven = {a["lhs"] for a in _assignments(block["text"])}
        missing = sorted((refs - driven) - sens)
        if missing:
            issues.append({
                "type": "SENSITIVITY",
                "location": f"always block at line {block['line']}",
                "evidence": f"Signals not in sensitivity list: {', '.join(missing[:4])}",
                "confidence": "HIGH",
                "problem": "Combinational always block has an incomplete manual sensitivity list.",
                "risk": "Simulation uses stale values and disagrees with synthesised combinational logic.",
                "fix": "Replace the manual sensitivity list with always_comb or always @(*).",
            })

    # extra timing checks (multi-bit CDC, case without default)
    try:
        from src.core.extra_check import timing_extras
        issues.extend(timing_extras(code))
    except ImportError:
        pass

    return _dedupe_findings(issues)


def static_assertions(code: str) -> list[dict]:
    """Template SVA for registers that are (a) driven by a clocked block and
    (b) assigned in that block's reset branch.  Clock, edge and reset polarity
    come from that block, not from signal names.  Inputs and registers that
    are never reset are not asserted (they are legitimately X)."""
    meta = extract_declared_identifiers(code)
    arrays = set(meta.get("arrays", []))
    cands: list[tuple[str, dict]] = []
    for b in extract_clocking_blocks(code):
        if not b.get("reset") or not b.get("rst_lhs"):
            continue
        for s in sorted(b["rst_lhs"]):
            if s not in arrays and s != b["clock"] and s != b["reset"]:
                cands.append((s, b))
    if not cands:
        return []

    pref = re.compile(r"count|state|ptr|valid|ready|empty|full|out|data|\bq\b", re.I)
    reset_target = next((c for c in cands if pref.search(c[0])), cands[0])
    others = [c for c in cands if c[0] != reset_target[0]]
    range_pref = re.compile(r"count|ptr|state", re.I)
    range_target = next((c for c in others if range_pref.search(c[0])),
                        others[0] if others else reset_target)

    def reset_expr(b):
        return f"!{b['reset']}" if b["reset_active_low"] else b["reset"]

    out = []
    sig, b = reset_target
    out.append({
        "type": "RESET", "signal": sig,
        "sva_code": f"assert property (@({b['edge'] or 'posedge'} {b['clock']}) "
                    f"{reset_expr(b)} |=> !$isunknown({sig}));",
        "description": f"Verifies {sig} is known one cycle after reset is asserted.",
    })
    sig, b = range_target
    out.append({
        "type": "RANGE", "signal": sig,
        "sva_code": f"assert property (@({b['edge'] or 'posedge'} {b['clock']}) "
                    f"disable iff ({reset_expr(b)}) !$isunknown({sig}));",
        "description": f"Checks {sig} never becomes X/Z once reset is released.",
    })
    return out


def static_optimizations(code: str) -> list[dict]:
    opts: list[dict] = []
    clean = _strip_comments(code)
    param_line = re.compile(r"\b(parameter|localparam)\b")
    sized = re.compile(r"\b\d+'[bdhoBDHO][0-9a-fA-F_xzXZ]+\b", re.I)
    bare = re.compile(r"(?<![\w'#])\b([1-9]\d+)\b(?![\w'])")
    for ln_no, line in enumerate(clean.splitlines(), 1):
        if param_line.search(line):
            continue
        m = bare.search(sized.sub("", line))
        if m:
            opts.append({
                "type": "HARDCODED", "location": f"line {ln_no}",
                "issue": f"Bare decimal literal {m.group(1)} is hardcoded in RTL logic.",
                "benefit": "Named parameters make design intent explicit and future resizing safe.",
                "suggestion": f"Replace {m.group(1)} with a declared parameter or localparam.",
            })
    return opts


# --------------------------------------------------------------------------
# LLM output filters
# --------------------------------------------------------------------------

_FILTER_SKIP = frozenset({
    "always", "always_ff", "always_comb", "always_latch", "assign", "begin", "end",
    "if", "else", "case", "endcase", "default", "posedge", "negedge", "logic", "reg",
    "wire", "assert", "property", "disable", "iff", "isunknown",
    "line", "at", "row", "port", "signal", "register", "value", "module", "clock",
    "reset", "active_low", "active_high", "clock_cycle", "clock_domain", "reset_value",
    "next_state", "current_state", "output", "input",
} | KEYWORDS)


def references_only_declared(item: dict, declared: Iterable[str], ignore: Iterable[str] = ()) -> bool:
    allowed = set(declared) | set(ignore)
    fields = [str(item.get(k, "")) for k in ("signal", "sva_code")]
    for key in ("fix", "suggestion"):
        v = str(item.get(key, ""))
        if re.search(r"[;=<>()[\]{}']|\b(always|assign|if|case|endcase)\b", v):
            fields.append(v)
    tokens = {t for t in re.findall(r"\b[A-Za-z_]\w*\b", " ".join(fields)) if t not in KEYWORDS}
    return not (tokens - allowed - _FILTER_SKIP)


def extract_clocking_blocks(code: str) -> list[dict]:
    """Clocked always blocks with clock, edge, reset (+polarity) and the LHS
    sets assigned in / outside the reset branch."""
    blocks = []
    declared = extract_declared_identifiers(code)
    known = set(declared.get("signals", []))
    resets_decl = set(declared.get("resets", []))

    for blk in _find_always_blocks(code):
        kind = blk.get("kind")
        if kind not in ("ff", "always"):
            continue
        text, header = blk.get("text", ""), blk.get("header", "")

        events = re.findall(r"\b(posedge|negedge)\s+([A-Za-z_]\w*)", header)
        if kind == "always" and not events:
            continue                      # combinational always @(*)

        clk = edge = None
        for e, s in events:               # clock = first event that is not a reset
            if s not in resets_decl:
                clk, edge = s, e
                break
        if clk is None and events:
            edge, clk = events[0]
        if clk is None:                   # always_ff without visible event list
            if not declared.get("clocks"):
                continue
            clk, edge = declared["clocks"][0], "posedge"

        reset, active_low = None, False
        for r in sorted(resets_decl):
            if re.search(rf"\bif\s*\(\s*!\s*{re.escape(r)}\s*\)", text):
                reset, active_low = r, True
                break
            if re.search(rf"\bif\s*\(\s*{re.escape(r)}\s*\)", text):
                reset, active_low = r, False
                break
        if reset is None:                 # asynchronous reset from the event list
            for e, s in events:
                if s != clk and s in resets_decl:
                    reset, active_low = s, (e == "negedge")
                    break

        rst_lhs: set[str] = set()
        non_rst_lhs: set[str] = set()
        all_lhs = {a["lhs"] for a in _assignments(text) if a["lhs"] in known}
        if reset and re.search(rf"\bif\s*\(\s*!?\s*{re.escape(reset)}\s*\)", text):
            parts = re.split(r"\belse\b", text, maxsplit=1)
            rst_lhs = {a["lhs"] for a in _assignments(parts[0]) if a["lhs"] in known}
            if len(parts) > 1:
                non_rst_lhs = {a["lhs"] for a in _assignments(parts[1]) if a["lhs"] in known}
        if not non_rst_lhs:
            non_rst_lhs = all_lhs

        blocks.append({
            "kind": "clocked_ff", "line": blk.get("line"), "clock": clk, "edge": edge,
            "reset": reset, "reset_active_low": active_low,
            "rst_lhs": rst_lhs, "non_rst_lhs": non_rst_lhs,
        })
    return blocks


def extract_sva_clock_reset_target(sva_code: str) -> dict:
    mclk = re.search(r"@\s*\(\s*(posedge|negedge)\s+([A-Za-z_]\w*)\s*\)", sva_code)
    mrst = re.search(r"disable\s+iff\s*\(\s*([^)]*)\)", sva_code)
    reset, active_low = None, False
    if mrst:
        expr = mrst.group(1).replace(" ", "")
        m1 = re.fullmatch(r"!\(?([A-Za-z_]\w*)\)?", expr)
        m2 = re.fullmatch(r"\(?([A-Za-z_]\w*)\)?", expr)
        if m1:
            reset, active_low = m1.group(1), True
        elif m2:
            reset = m2.group(1)
    mt = re.search(r"\$isunknown\s*\(\s*([A-Za-z_]\w*)\s*\)", sva_code)
    return {"clock": mclk.group(2) if mclk else None,
            "edge": mclk.group(1) if mclk else None,
            "reset": reset, "reset_active_low": active_low,
            "target": mt.group(1) if mt else None}


def validate_sva_against_rtl(code: str, assertion: dict) -> bool:
    sva = str(assertion.get("sva_code", ""))
    if not sva or "assert property" not in sva:
        return False
    parsed = extract_sva_clock_reset_target(sva)
    if not parsed.get("clock") or not parsed.get("edge") or not parsed.get("target"):
        return False
    for blk in extract_clocking_blocks(code):
        if blk.get("clock") != parsed["clock"]:
            continue
        if blk.get("edge") and blk["edge"] != parsed["edge"]:
            continue
        if parsed.get("reset"):
            if blk.get("reset") != parsed["reset"]:
                continue
            if blk.get("reset_active_low") != parsed["reset_active_low"]:
                continue
        if parsed["target"] in blk.get("non_rst_lhs", set()) | blk.get("rst_lhs", set()):
            return True
    return False


def validate_immediate_assertions_against_rtl(code: str, assertion: dict) -> bool:
    raw = str(assertion.get("sva_code", ""))
    if not raw or "assert property" in raw or "assert (" not in raw:
        return False
    d = extract_declared_identifiers(code)
    allowed = set(d.get("signals", [])) | set(d.get("parameters", []))
    tokens = {t for t in re.findall(r"\b[A-Za-z_]\w*\b", raw) if t not in KEYWORDS}
    return tokens.issubset(allowed | {"assert", "else", "error", "fatal", "display"})


def validate_optimization_against_rtl(code: str, optimization: dict) -> bool:
    """HARDCODED must match a static finding; NAMING/REDUNDANT/COMMENTS/MISSING_COMMENTS/
    STYLE are accepted when they reference only declared identifiers."""
    issue_type = str(optimization.get("type", "")).upper()
    if issue_type == "HARDCODED":
        text = (str(optimization.get("issue", "")) + " " + str(optimization.get("suggestion", ""))).lower()
        return bool(static_optimizations(code)) and any(
            w in text for w in ("hardcod", "literal", "magic", "constant", "parameter"))
    if issue_type in {"NAMING", "REDUNDANT", "COMMENTS", "MISSING_COMMENTS", "STYLE"}:
        d = extract_declared_identifiers(code)
        return references_only_declared(optimization, set(d["signals"]) | set(d["parameters"]))
    return False


def is_concrete_finding(item: dict, declared: Iterable[str]) -> bool:
    """Deprecated heuristic, kept for backward compatibility."""
    text = " ".join(str(item.get(k, "")) for k in (
        "location", "problem", "impact", "fix", "evidence", "risk", "issue", "suggestion")).lower()
    vague = ("some other issues", "may have issues", "quality enhancement",
             "needs improvement", "improve quality", "could not identify",
             "might be problematic", "review further")
    if any(p in text for p in vague):
        return False
    return (any(k in text for k in ("line", "always", "assign", "case", "block"))
            or any(n.lower() in text for n in declared))