import re
from typing import Iterable


KEYWORDS = {
    "module", "endmodule", "input", "output", "inout", "wire", "reg", "logic",
    "bit", "integer", "parameter", "localparam", "always", "always_ff",
    "always_comb", "always_latch", "assign", "begin", "end", "if", "else",
    "case", "endcase", "for", "while", "posedge", "negedge", "or", "and",
    "not", "default", "typedef", "enum", "struct", "signed", "unsigned",
}

TYPE_WORDS = {
    "input", "output", "inout", "wire", "reg", "logic", "bit", "integer",
    "signed", "unsigned", "tri", "supply0", "supply1",
}


def strip_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return re.sub(r"//.*", "", code)


def numbered_lines(code: str) -> list[tuple[int, str]]:
    return list(enumerate(code.splitlines(), 1))


def get_module_name(code: str) -> str:
    match = re.search(r"\bmodule\s+([A-Za-z_]\w*)", strip_comments(code))
    return match.group(1) if match else "dut"


def extract_declared_identifiers(code: str) -> dict:
    clean = strip_comments(code)
    signals = set()
    parameters = set()
    widths = {}
    arrays = set()
    enum_values = _enum_values(clean)
    type_aliases = _typedef_aliases(clean)

    param_pattern = r"\b(?:parameter|localparam)\b([^;,)]+)"
    for match in re.finditer(param_pattern, clean):
        for name in _split_declaration_names(match.group(1)):
            parameters.add(name)

    for stmt in _declaration_statements(clean, type_aliases):
        width = _width_from_declaration(stmt)
        for name in _split_declaration_names(stmt):
            if name not in KEYWORDS and name not in parameters and name not in enum_values:
                signals.add(name)
                if width:
                    widths[name] = width
                if _is_array_declaration(stmt, name):
                    arrays.add(name)

    clocks = sorted(s for s in signals if re.search(r"(^clk$|clk|clock)", s, re.I))
    resets = sorted(s for s in signals if re.search(r"(^rst$|reset|rst_n|reset_n)", s, re.I))

    return {
        "signals": sorted(signals),
        "parameters": sorted(parameters),
        "widths": widths,
        "arrays": sorted(arrays),
        "enum_values": sorted(enum_values),
        "type_aliases": sorted(type_aliases),
        "clocks": clocks,
        "resets": resets,
        "module": get_module_name(code),
    }


def _enum_values(clean: str) -> set[str]:
    values = set()
    for body in re.findall(r"\btypedef\s+enum\b.*?\{(.*?)\}", clean, flags=re.S):
        for name in _split_declaration_names(body):
            values.add(name)
    return values


def _typedef_aliases(clean: str) -> set[str]:
    aliases = set()
    for match in re.finditer(r"\btypedef\b[^;]*\b([A-Za-z_]\w*)\s*;", clean, flags=re.S):
        aliases.add(match.group(1))
    return aliases


def _is_array_declaration(stmt: str, name: str) -> bool:
    return bool(re.search(rf"\b{re.escape(name)}\b\s*\[[^\]]+\]", stmt))


def _declaration_statements(clean: str, type_aliases: Iterable[str] = ()) -> list[str]:
    statements = []
    decl_words = ["input", "output", "inout", "wire", "reg", "logic", "bit", "integer", *type_aliases]
    pattern = r"\b(?:" + "|".join(map(re.escape, decl_words)) + r")\b[^;]*[;,)]"
    for match in re.finditer(pattern, clean):
        statements.append(match.group(0))
    return statements


def _split_declaration_names(text: str) -> list[str]:
    text = re.sub(r"\b(?:parameter|localparam)\b", " ", text)
    text = re.sub(r"\b(?:" + "|".join(TYPE_WORDS) + r")\b", " ", text)
    text = re.sub(r"\b[A-Za-z_]\w*_t\b", " ", text)
    text = re.sub(r"\[[^\]]+\]", " ", text)
    names = []
    for part in re.split(r",", text):
        part = re.sub(r"=.*", "", part).strip()
        part = part.strip(");(")
        match = re.search(r"\b([A-Za-z_]\w*)\b", part)
        if match and match.group(1) not in KEYWORDS:
            names.append(match.group(1))
    return names


def _width_from_declaration(text: str) -> str | None:
    match = re.search(r"\[([^\]]+)\]", text)
    return match.group(1).strip() if match else None


def _is_clocked_block(block: dict) -> bool:
    return bool(re.search(r"\balways_ff\b|@\s*\([^)]*(?:posedge|negedge)", block["header"]))


def _is_comb_block(block: dict) -> bool:
    return bool(re.search(r"\balways_comb\b|@\s*\(\s*\*\s*\)|@\s*\(\s*all\s*\)", block["header"]))


def _assignments(text: str) -> list[dict]:
    assignments = []
    for offset, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith(("for", "while", "case", "end")):
            continue
        match = re.search(r"\b([A-Za-z_]\w*)\b(?:\s*\[[^\]]+\])?\s*(<=|(?<![<>=!])=(?!=))\s*(.*?);", line)
        if match:
            assignments.append({
                "offset": offset,
                "lhs": match.group(1),
                "op": match.group(2),
                "rhs": match.group(3).strip(),
                "line": stripped,
            })
    return assignments


def _continuous_assignments(code: str) -> list[dict]:
    assigns = []
    for line_no, line in numbered_lines(strip_comments(code)):
        match = re.search(r"\bassign\s+([A-Za-z_]\w*)\b(?:\s*\[[^\]]+\])?\s*=\s*(.*?);", line)
        if match:
            assigns.append({
                "line_no": line_no,
                "lhs": match.group(1),
                "rhs": match.group(2).strip(),
                "line": line.strip(),
            })
    return assigns


def _line_has_default_assignment(block_text: str, signal: str) -> bool:
    for line in block_text.splitlines():
        if re.search(r"\b(if|case)\b", line):
            return False
        if re.match(rf"\s*{re.escape(signal)}(?:\s*\[[^\]]+\])?\s*(?:<=|=)", line):
            return True
    return False


def identifiers_in_text(text: str) -> set[str]:
    return {tok for tok in re.findall(r"\b[A-Za-z_]\w*\b", text or "") if tok not in KEYWORDS}


def references_only_declared(item: dict, declared: Iterable[str], ignore: Iterable[str] = ()) -> bool:
    allowed = set(declared) | set(ignore)
    # Only parse code/signal fields to avoid false positives from English prose
    code_fields = " ".join(str(item.get(k, "")) for k in ("location", "fix", "signal", "sva_code", "suggestion"))
    tokens = identifiers_in_text(code_fields)
    suspicious = tokens - allowed
    
    verilog_keywords = {
        "always", "always_ff", "always_comb", "always_latch", "assign", "begin", "end", 
        "if", "else", "case", "endcase", "default", "posedge", "negedge", "logic", "reg", "wire"
    }
    ignored_words = {
        "line", "at", "row", "port", "signal", "register", "value", "module", "clock", "reset",
        "active_low", "active_high", "clock_cycle", "clock_domain", "reset_value", "reset_condition",
        "always_comb", "always_ff", "always_latch", "next_state", "current_state"
    }
    suspicious = suspicious - verilog_keywords - ignored_words
    return not suspicious


def is_concrete_finding(item: dict, declared: Iterable[str]) -> bool:
    text = " ".join(str(item.get(k, "")) for k in (
        "location", "problem", "impact", "fix", "evidence", "risk", "issue", "suggestion"
    )).lower()
    vague_phrases = (
        "some other issues",
        "may have issues",
        "quality enhancement",
        "needs improvement",
        "improve quality",
        "could not identify",
        "might be problematic",
        "review further",
    )
    if any(phrase in text for phrase in vague_phrases):
        return False
    has_location = "line" in text or "always" in text or "assign" in text or "case" in text
    has_declared_signal = any(name.lower() in text for name in declared)
    return has_location or has_declared_signal


def _find_always_blocks(code: str) -> list[dict]:
    lines = numbered_lines(code)
    blocks = []
    i = 0
    while i < len(lines):
        line_no, line = lines[i]
        if re.search(r"\balways(?:_ff|_comb)?\b", line):
            text = [line]
            depth = line.count("begin") - len(re.findall(r"\bend\b", line))
            j = i + 1
            while j < len(lines) and (depth > 0 or len(text) == 1):
                _, next_line = lines[j]
                text.append(next_line)
                depth += next_line.count("begin") - len(re.findall(r"\bend\b", next_line))
                if depth <= 0 and len(text) > 1:
                    break
                j += 1
            blocks.append({"line": line_no, "header": line.strip(), "text": "\n".join(text)})
            i = max(j, i + 1)
        else:
            i += 1
    return blocks


def static_bug_findings(code: str) -> list[dict]:
    findings = []
    declared = extract_declared_identifiers(code)
    known_signals = set(declared["signals"])

    for block in _find_always_blocks(code):
        assignments = _assignments(block["text"])
        if _is_clocked_block(block):
            for item in assignments:
                if item["op"] == "=":
                    findings.append({
                        "type": "FUNCTIONAL",
                        "location": f"{item['lhs']} at line {block['line'] + item['offset']}",
                        "problem": "Blocking assignment is used inside sequential logic.",
                        "impact": "Simulation can race against other clocked logic and differ from intended flip-flop behavior.",
                        "fix": "Use non-blocking assignment '<=' for registers updated in this clocked block.",
                    })

            has_reset_branch = bool(re.search(r"\bif\s*\(\s*!?\s*(?:" + "|".join(map(re.escape, declared["resets"])) + r")\s*\)", block["text"])) if declared["resets"] else False
            if declared["resets"] and has_reset_branch:
                reset_part = re.split(r"\belse\b", block["text"], maxsplit=1)[0]
                reset_assigned = {a["lhs"] for a in assignments if a["line"] in reset_part}
                for sig in sorted(({a["lhs"] for a in assignments if a["lhs"] in known_signals} - reset_assigned) - set(declared["arrays"])):
                    findings.append({
                        "type": "RESET",
                        "location": f"{sig} in sequential block starting line {block['line']}",
                        "problem": f"{sig} is updated in a reset-aware clocked block but is not assigned in the reset branch.",
                        "impact": "The register can retain an unknown or stale value after reset.",
                        "fix": f"Assign a deterministic reset value to {sig} in the reset branch.",
                    })

        if _is_comb_block(block):
            assigned = {a["lhs"] for a in assignments if a["lhs"] in known_signals}
            conditional = bool(re.search(r"\b(if|case)\b", block["text"]))
            has_else_or_default = bool(re.search(r"\belse\b|\bdefault\s*:", block["text"]))
            for sig in sorted(assigned):
                if conditional and not has_else_or_default and not _line_has_default_assignment(block["text"], sig):
                    findings.append({
                        "type": "LATCH",
                        "location": f"{sig} in combinational block starting line {block['line']}",
                        "problem": f"{sig} is assigned under conditional logic without a visible default/else path.",
                        "impact": "Synthesis can infer a latch to preserve the previous value.",
                        "fix": f"Give {sig} a default assignment before the conditional or cover all branches.",
                    })

    drivers = {}
    for assign in _continuous_assignments(code):
        drivers.setdefault(assign["lhs"], []).append(f"continuous assign line {assign['line_no']}")
    for block in _find_always_blocks(code):
        for item in _assignments(block["text"]):
            drivers.setdefault(item["lhs"], []).append(f"always block line {block['line']}")
    for sig, locations in sorted(drivers.items()):
        if sig in known_signals and len(set(locations)) > 1:
            findings.append({
                "type": "FUNCTIONAL",
                "location": f"{sig}: {', '.join(sorted(set(locations)))}",
                "problem": f"{sig} is driven from multiple procedural/continuous sources.",
                "impact": "Multiple drivers can create simulation conflicts or non-synthesizable RTL.",
                "fix": f"Drive {sig} from exactly one always block or continuous assignment.",
            })

    for item in _continuous_assignments(code):
        lhs_width = declared["widths"].get(item["lhs"])
        rhs_literal = re.search(r"\b(\d+)'[bBdDhHoO]([0-9a-fA-F_xzXZ]+)\b", item["rhs"])
        if lhs_width and rhs_literal and _literal_width_mismatch(lhs_width, int(rhs_literal.group(1))):
            findings.append({
                "type": "WIDTH",
                "location": f"{item['lhs']} at line {item['line_no']}",
                "problem": f"{item['lhs']} is assigned a {rhs_literal.group(1)}-bit literal that does not match its declared width [{lhs_width}].",
                "impact": "The assignment can truncate or extend data unintentionally.",
                "fix": f"Match the literal width to {item['lhs']}'s declared width or resize the signal intentionally.",
            })
    return findings


def _literal_width_mismatch(lhs_width: str, literal_bits: int) -> bool:
    match = re.match(r"\s*(\d+)\s*:\s*(\d+)\s*$", lhs_width)
    if not match:
        return False
    msb, lsb = int(match.group(1)), int(match.group(2))
    return abs(msb - lsb) + 1 != literal_bits


def static_timing_findings(code: str) -> list[dict]:
    issues = []
    for bug in static_bug_findings(code):
        if "Blocking assignment" in bug["problem"] or bug["type"] == "LATCH":
            issues.append({
                "type": "BLOCKING" if "Blocking assignment" in bug["problem"] else bug["type"],
                "location": bug["location"],
                "evidence": bug["problem"],
                "confidence": "HIGH",
                "problem": bug["problem"],
                "risk": "Can produce incorrect timing-dependent simulation or inferred storage.",
                "fix": bug["fix"],
            })

    declared = extract_declared_identifiers(code)
    for block in _find_always_blocks(code):
        match = re.search(r"@\s*\(([^*)][^)]*)\)", block["header"])
        if not match or "posedge" in match.group(1) or "negedge" in match.group(1):
            continue
        sensitivity = identifiers_in_text(match.group(1))
        body_refs = identifiers_in_text(block["text"]) & set(declared["signals"])
        lhs = {a["lhs"] for a in _assignments(block["text"])}
        missing = sorted((body_refs - lhs) - sensitivity)
        if missing:
            issues.append({
                "type": "SENSITIVITY",
                "location": f"always block starting line {block['line']}",
                "evidence": f"manual sensitivity list omits {', '.join(missing[:4])}",
                "confidence": "HIGH",
                "problem": "Combinational always block has an incomplete manual sensitivity list.",
                "risk": "Simulation can use stale values and disagree with synthesized combinational logic.",
                "fix": "Use always_comb or always @(*) for combinational logic.",
            })
    return issues


def static_assertions(code: str) -> list[dict]:
    meta = extract_declared_identifiers(code)
    clk = meta["clocks"][0] if meta["clocks"] else None
    rst = meta["resets"][0] if meta["resets"] else None
    if not clk:
        return []

    assertions = []
    active_low = bool(rst and rst.endswith("_n"))
    reset_active = f"!{rst}" if active_low else rst
    reset_disable = reset_active if rst else "1'b0"

    # Find candidate signals for assertions.
    # We prefer signals containing count/state/ptr/valid/ready/empty/full/out/data,
    # but fall back to ANY declared signal that is not clock/reset.
    candidate_signals = []
    for sig in meta["signals"]:
        if sig not in {clk, rst}:
            candidate_signals.append(sig)

    if not candidate_signals:
        return []

    if rst:
        # Find best reset check target
        reset_target = None
        for sig in candidate_signals:
            if re.search(r"(count|state|ptr|valid|ready|empty|full|out|data)", sig, re.I):
                reset_target = sig
                break
        if not reset_target:
            reset_target = candidate_signals[0]

        assertions.append({
            "type": "RESET",
            "signal": reset_target,
            "sva_code": f"assert property (@(posedge {clk}) {reset_active} |=> !$isunknown({reset_target}));",
            "description": f"Checks that {reset_target} is known immediately after reset is active.",
        })

    # Range check assertion
    range_target = None
    for sig in candidate_signals:
        if re.search(r"(count|ptr|state)", sig, re.I):
            range_target = sig
            break
    if not range_target:
        # Use a different signal than reset target if possible
        for sig in candidate_signals:
            if sig != (assertions[0]["signal"] if assertions else None):
                range_target = sig
                break
        if not range_target:
            range_target = candidate_signals[0]

    assertions.append({
        "type": "RANGE",
        "signal": range_target,
        "sva_code": f"assert property (@(posedge {clk}) disable iff ({reset_disable}) !$isunknown({range_target}));",
        "description": f"Checks that {range_target} never becomes X/Z during normal operation.",
    })

    return assertions[:3]


def static_optimizations(code: str) -> list[dict]:
    opts = []
    for line_no, line in numbered_lines(code):
        if re.search(r"\b\d+'[bdhoBDHO][0-9a-fA-F_xzXZ]+\b", line):
            continue
        if re.search(r"(?<![\w'])\d{2,}(?!\w)", line):
            opts.append({
                "type": "HARDCODED",
                "location": f"line {line_no}",
                "issue": "Large decimal literal is hardcoded in RTL.",
                "benefit": "A named parameter makes the design intent and future resizing safer.",
                "suggestion": "Replace the literal with a declared parameter or localparam if it is a design constant.",
            })
            break
    return opts
