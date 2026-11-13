"""Extra deterministic checks that rtl_parser.py did not cover.

These are regex-based (comment-stripped source) and intentionally conservative.
Each finding carries `evidence` (the real source line) and source="static".
Longer term: replace with `verilator --lint-only -Wall` output.
"""
import re
from src.core.evidence import _strip_comments_keep_lines
strip_comments = _strip_comments_keep_lines

PORT_RE = re.compile(
    r"\b(input|output|inout)\b\s*(?:(?:logic|wire|reg|var)\b\s*)?"
    r"(?:(?:signed|unsigned)\b\s*)?(\[[^\]]+\])?\s*([A-Za-z_]\w*)")
DECL_RE = re.compile(
    r"\b(?:logic|reg|wire)\b\s*(?:(?:signed|unsigned)\b\s*)?(\[[^\]]+\])?\s*([A-Za-z_]\w*)")
PARAM_RE = re.compile(r"\b(?:parameter|localparam)\b\s*(?:\w+\s+)?([A-Za-z_]\w*)\s*=\s*(\d+)")
LIT_RE = re.compile(r"\b([A-Za-z_]\w*)\b(?:\[[^\]]*\])?\s*(?:==|!=|<=|=)\s*(\d+)'[sS]?[bBdDhHoO]")


def _line(clean, pos):
    return clean.count("\n", 0, pos) + 1


def _src_line(clean, n):
    lines = clean.splitlines()
    return lines[n - 1].strip() if 0 < n <= len(lines) else ""


def _f(type_, loc, problem, impact, fix, evidence):
    return {"type": type_, "location": loc, "problem": problem, "impact": impact,
            "risk": impact, "fix": fix, "evidence": evidence, "source": "static"}


def parse_ports(code):
    clean = strip_comments(code)
    out = []
    for m in PORT_RE.finditer(clean):
        out.append({"dir": m.group(1), "width": m.group(2), "name": m.group(3),
                    "line": _line(clean, m.start())})
    return out


def _params(clean):
    return {n: int(v) for n, v in PARAM_RE.findall(clean)}


def eval_width(expr, params):
    """'[WIDTH-1:0]' -> 8 using parameter defaults. None if not resolvable."""
    if not expr:
        return 1
    m = re.match(r"\[\s*([^:\]]+)\s*:\s*([^\]]+)\s*\]$", expr.strip())
    if not m:
        return None
    vals = []
    for part in m.groups():
        for k, v in params.items():
            part = re.sub(rf"\b{k}\b", str(v), part)
        if not re.fullmatch(r"[\d\s\+\-\*\(\)]+", part):
            return None
        try:
            vals.append(eval(part, {"__builtins__": {}}, {}))
        except Exception:
            return None
    return abs(vals[0] - vals[1]) + 1


def unused_inputs(code):
    clean = strip_comments(code)
    res = []
    for p in parse_ports(code):
        if p["dir"] == "input" and len(re.findall(rf"\b{re.escape(p['name'])}\b", clean)) == 1:
            res.append(_f("UNUSED", f"{p['name']} at line {p['line']}",
                          f"Input {p['name']} is declared but never used in the module.",
                          "Dead port: the module ignores it, so the interface does not match the intent.",
                          f"Use {p['name']} in the logic, or remove it from the port list.",
                          _src_line(clean, p["line"])))
    return res


def case_without_default(code):
    clean = strip_comments(code)
    res = []
    for m in re.finditer(r"\b(?:case|casez|casex)\b\s*\(", clean):
        end = clean.find("endcase", m.end())
        if end == -1:
            continue
        if re.search(r"\bdefault\b", clean[m.end():end]):
            continue
        expr = clean[m.end():].split(")")[0].strip()
        n = _line(clean, m.start())
        res.append(_f("CASE_DEFAULT", f"case ({expr}) at line {n}",
                      f"case on {expr} has no default branch.",
                      "Unlisted values leave the assigned signals unchanged: latch in combinational "
                      "logic, undefined behaviour for illegal FSM states.",
                      "Add a default branch that assigns every signal driven in this case.",
                      _src_line(clean, n)))
    return res


def width_literals(code):
    clean = strip_comments(code)
    params = _params(clean)
    widths = {p["name"]: p["width"] for p in parse_ports(code) if p["width"]}
    widths.update({name: w for w,name in DECL_RE.findall(clean) if w})

    res, seen = [], set()
    for m in LIT_RE.finditer(clean):
        sig, lit_w = m.group(1), int(m.group(2))
        expr = widths.get(sig)
        if not expr:
            continue
        sig_w = eval_width(expr, params)
        parametric = bool(re.search(r"[A-Za-z_]", expr))
        if sig_w is not None and sig_w != lit_w:
            kind = "mismatch"
        elif parametric:
            kind = "hardcoded"
        else:
            continue
        n = _line(clean, m.start())
        if (sig, n) in seen:
            continue
        seen.add((sig, n))
        if kind == "mismatch":
            problem = f"{sig} is declared {expr} ({sig_w} bits) but is combined with a {lit_w}-bit literal."
            impact = "Width mismatch: truncation or zero-extension changes the compared/assigned value."
        else:
            problem = f"{sig} is declared {expr} but a fixed {lit_w}-bit literal is used."
            impact = "Correct only for the default parameter value; breaks when the parameter changes."
        res.append(_f("WIDTH", f"{sig} at line {n}", problem, impact,
                      "Use a parameter-sized value such as '0 or {WIDTH{1'b0}} instead of a fixed-width literal.",
                      _src_line(clean, n)))
    return res


def cdc_multibit(code):
    """Heuristic: a multi-bit input whose name prefix matches clock A (e.g. wr_ / wr_clk)
    is sampled by flops clocked by a different clock B without Gray coding."""
    clean = strip_comments(code)
    params = _params(clean)
    ports = parse_ports(code)
    clk_ports = [p["name"] for p in ports if p["dir"] == "input" and re.search(r"clk|clock", p["name"], re.I)]
    if len(clk_ports) < 2 or re.search(r">>\s*1\b|gray", clean, re.I):
        return []
    pre = lambda s: s.split("_")[0].lower()
    res = []
    for blk in re.finditer(r"\balways\w*\s*@\s*\(([^)]*)\)", clean):
        m = re.search(r"(?:posedge|negedge)\s+(\w+)", blk.group(1))
        if not m or m.group(1) not in clk_ports:
            continue
        dst = m.group(1)
        nxt = re.search(r"\balways\w*\s*@|\bendmodule\b", clean[blk.end():])
        body = clean[blk.end(): blk.end() + (nxt.start() if nxt else len(clean))]
        for p in ports:
            if p["dir"] != "input" or p["name"] in clk_ports or eval_width(p["width"], params) in (1, None):
                continue
            src_clks = [c for c in clk_ports if c != dst and pre(c) == pre(p["name"])]
            if not src_clks or pre(p["name"]) == pre(dst):
                continue
            um = re.search(rf"\b{re.escape(p['name'])}\b", body)
            if um:
                n = _line(clean, blk.end() + um.start())
                res.append(_f("CDC", f"{p['name']} at line {n}",
                              f"Multi-bit bus {p['name']} (domain {src_clks[0]}) is sampled in the {dst} domain "
                              "through plain flops without Gray coding or a handshake.",
                              "Bits can be captured at different times, so the receiver can see a value that "
                              "never existed (e.g. a wrong FIFO pointer).",
                              "Gray-encode the pointer before crossing (bin ^ (bin >> 1)) or use a handshake/async FIFO.",
                              _src_line(clean, n)))
    return res


def bug_extras(code):
    out = []
    for fn in (unused_inputs, width_literals, cdc_multibit):
        try:
            out += fn(code)
        except Exception as e:  # never let a heuristic crash the pipeline
            print(f"extra check {fn.__name__} failed: {e}")
    return out


def timing_extras(code):
    out = []
    for fn in (cdc_multibit,):
        try:
            out += fn(code)
        except Exception as e:
            print(f"extra check {fn.__name__} failed: {e}")
    return out
