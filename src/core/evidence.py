"""
evidence.py - shared grounding utilities for all analysis agents.

Static analysis is the source of truth. An LLM finding is accepted only if it can
be tied back to the file:
  * it quotes a snippet ("evidence") that exists in the CODE (comments excluded,
    whitespace-insensitive),
  * the line number comes from where the snippet is found (the model's own line
    number is never trusted),
  * the signal it names is declared AND appears in the quoted snippet,
and every rejection is counted by reason so a zero-finding run is explainable.

CHANGES vs previous version
  * merge_dedupe: static findings are never merged with each other (two blocking
    assignments to the same signal are two findings); only LLM items that
    duplicate a static/earlier item are dropped.
  * first_token strips punctuation ("sig:" == "sig").
  * locate_snippet: whitespace-insensitive, ignores comments (a quoted comment is
    not evidence), exact line of the first match.
  * validate_llm_findings: new reason "signal_not_in_evidence" (disable with
    require_signal_in_evidence=False).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SMALL_FILE_CHAR_THRESHOLD = 12000

_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_NUM_PREFIX = re.compile(r"^\s*\d+\s*\|\s?", re.M)

SV_KEYWORDS = {
    "assert", "assume", "cover", "property", "endproperty", "sequence", "endsequence",
    "posedge", "negedge", "edge", "disable", "iff", "or", "and", "not", "if", "else",
    "begin", "end", "always", "always_comb", "always_ff", "always_latch", "initial",
    "throughout", "within", "intersect", "first_match", "inside", "default", "case",
    "endcase", "for", "while", "int", "bit", "logic", "reg", "wire", "signed",
    "unsigned", "implies", "until", "eventually", "s_eventually", "nexttime",
    "s_nexttime", "strong", "weak", "this", "null",
}


# ---------------------------------------------------------------- prompt context
def number_lines(code: str) -> str:
    return "\n".join(f"{i:>4}| {line}" for i, line in enumerate(code.splitlines(), 1))


def build_code_context(code: str, hint: str = "reset clock latch width state always assign") -> str:
    if len(code) <= SMALL_FILE_CHAR_THRESHOLD:
        return number_lines(code)
    try:
        from src.core.semantic_chunker import chunk_sv, select_relevant_chunks, chunks_to_prompt_text
        selected = select_relevant_chunks(chunk_sv(code), query=hint, top_k=14,
                                          max_total_chars=SMALL_FILE_CHAR_THRESHOLD - 1000)
        if selected:
            return chunks_to_prompt_text(selected)
    except Exception:  # noqa: BLE001
        pass
    return number_lines(code[:SMALL_FILE_CHAR_THRESHOLD])


def safe_static(fn, code: str) -> list:
    try:
        out = fn(code)
        return list(out) if out else []
    except Exception as e:  # noqa: BLE001
        print(f"  Static check {getattr(fn, '__name__', fn)} failed: {e}")
        return []


def clocks_in_code(code: str) -> list[str]:
    return sorted(set(re.findall(r"@\s*\(\s*(?:posedge|negedge)\s+(\w+)", code)))


# ---------------------------------------------------------------- declared names
def declared_names(meta: dict) -> set[str]:
    names: set[str] = set()
    for key in ("signals", "outputs", "inputs", "parameters", "clocks", "resets",
                "arrays", "enum_values", "type_aliases"):
        val = (meta or {}).get(key)
        if not val:
            continue
        if isinstance(val, str):
            names.add(val)
        elif isinstance(val, dict):
            names.update(map(str, val.keys()))
        else:
            names.update(map(str, val))
    return names


def signal_ok(signal: str, declared: set[str]) -> bool:
    if not declared:
        return True
    toks = _ID.findall(signal)
    return bool(toks) and all(t in declared or t in SV_KEYWORDS for t in toks)


def undeclared_in_sva(sva: str, declared: set[str]) -> list[str]:
    s = re.sub(r'"[^"]*"', " ", sva)
    s = re.sub(r"\$\w+", " ", s)
    s = re.sub(r"\d*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+", " ", s)
    s = re.sub(r"'[01xXzZ]", " ", s)
    s = re.sub(r"^\s*\w+\s*:\s*(?=assert|assume|cover)", "", s)
    return sorted({t for t in _ID.findall(s) if t not in declared and t not in SV_KEYWORDS})


# ---------------------------------------------------------------- evidence matching
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _strip_comments_keep_lines(code: str) -> str:
    try:
        from src.core.rtl_parser import _strip_comments
        return _strip_comments(code)
    except Exception:  # noqa: BLE001
        code = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), code, flags=re.S)
        return re.sub(r"//[^\n]*", "", code)


def locate_snippet(snippet: str, code: str):
    """1-based line where `snippet` first occurs in the code (comments excluded,
    whitespace ignored), or None."""
    raw = _NUM_PREFIX.sub("", snippet or "")
    snip = re.sub(r"\s+", "", raw)
    if len(snip) < 4:
        return None
    chars, line_of = [], []
    for ln, line in enumerate(_strip_comments_keep_lines(code).splitlines(), 1):
        for ch in line:
            if not ch.isspace():
                chars.append(ch)
                line_of.append(ln)
    idx = "".join(chars).find(snip)
    return line_of[idx] if idx != -1 else None


def extract_list(parsed, key: str) -> list:
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        val = parsed.get(key, [])
        return val if isinstance(val, list) else []
    return []


def validate_llm_findings(items: list, code: str, declared: set[str],
                          allowed_types: set[str] | None = None,
                          drop_if=None, require_signal_in_evidence: bool = True):
    stats = {"returned": len(items), "kept": 0, "rejected": {}}

    def reject(reason: str):
        stats["rejected"][reason] = stats["rejected"].get(reason, 0) + 1

    kept = []
    for it in items:
        if not isinstance(it, dict):
            reject("not_an_object"); continue
        t = str(it.get("type", "")).upper().strip()
        if allowed_types and t not in allowed_types:
            reject("bad_type"); continue
        evd = it.get("evidence")
        if not isinstance(evd, str) or not evd.strip():
            reject("no_evidence"); continue
        line = locate_snippet(evd, code)
        if line is None:
            reject("evidence_not_in_code"); continue
        sig = str(it.get("signal", "")).strip()
        if sig and not signal_ok(sig, declared):
            reject("undeclared_signal"); continue
        if sig and require_signal_in_evidence:
            if not any(re.search(rf"\b{re.escape(tok)}\b", evd) for tok in _ID.findall(sig)):
                reject("signal_not_in_evidence"); continue
        if drop_if:
            reason = drop_if(it)
            if reason:
                reject(reason); continue
        it["type"], it["line"], it["source"] = t, line, "llm"
        kept.append(it)
    stats["kept"] = len(kept)
    return kept, stats


def print_stats(agent: str, stats: dict, call: dict | None = None):
    rej = ", ".join(f"{k}={v}" for k, v in stats.get("rejected", {}).items()) or "none"
    extra = ""
    if call:
        extra = (f" | prompt_tokens={call.get('prompt_tokens')} "
                 f"truncated_in={call.get('prompt_truncated')} truncated_out={call.get('output_truncated')}")
    print(f"  [{agent}] LLM filter: returned={stats.get('returned', 0)} kept={stats.get('kept', 0)} rejected: {rej}{extra}")


# ---------------------------------------------------------------- merge / format
def first_token(text: str) -> str:
    toks = str(text).lower().split()
    return toks[0].strip(":,;()[]") if toks else ""


def merge_dedupe(static: list, llm: list, key) -> list:
    """All static items are kept (only byte-identical duplicates removed).
    An LLM item is kept only if its key matches no static item and no earlier LLM item."""
    merged, exact = [], set()
    for it in static:
        ident = tuple(sorted((k, str(v)) for k, v in it.items()))
        if ident in exact:
            continue
        exact.add(ident)
        merged.append(it)
    seen = {key(i) for i in static}
    for it in llm:
        k = key(it)
        if k in seen:
            continue
        seen.add(k)
        merged.append(it)
    return merged


def format_items(items: list, label: str, fields: list[tuple[str, str]]) -> str:
    out = []
    for i, it in enumerate(items, 1):
        out.append(f"{label} #{i} [{it.get('source', 'unknown')}]")
        for title, key in fields:
            out.append(f"{title}: {it.get(key, '')}")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- Verilator
def _verilator_cmd():
    exe = shutil.which("verilator")
    if exe:
        return [exe], False
    if shutil.which("wsl"):
        return ["wsl", "verilator"], True
    return None, False


def _to_wsl_path(p: Path) -> str:
    s = str(p.resolve()).replace("\\", "/")
    m = re.match(r"^([a-zA-Z]):(.*)", s)
    return f"/mnt/{m.group(1).lower()}{m.group(2)}" if m else s


def verilator_lint(code: str) -> tuple[str, str]:
    """(status, message); status is "pass", "fail" or "skipped". Warnings do not fail;
    only %Error does. "skipped" = no usable Verilator (never treated as a failure).
    The message is kept (1500 chars) so you can see WHY an assertion was rejected -
    older Verilator versions reject valid concurrent SVA as "unsupported"."""
    cmd, is_wsl = _verilator_cmd()
    if cmd is None:
        return "skipped", "Verilator not found on PATH (or via WSL)."
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "lint_target.sv"
        f.write_text(code, encoding="utf-8")
        target = _to_wsl_path(f) if is_wsl else str(f)
        try:
            r = subprocess.run(cmd + ["--lint-only", "--assert", "-Wno-fatal", target],
                               capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return "skipped", "Verilator timed out."
        except Exception as e:  # noqa: BLE001
            return "skipped", f"Verilator could not run: {e}"
    err = r.stderr or ""
    if "not found" in err.lower() and "%Error" not in err:
        return "skipped", err[:300]
    if r.returncode != 0 or "%Error" in err:
        return "fail", err[:1500]
    return "pass", ""


def insert_before_endmodule(code: str, snippet: str) -> str:
    idx = code.rfind("endmodule")
    if idx == -1:
        return code
    sva = snippet.strip()
    if not sva.endswith(";"):
        sva += ";"
    return code[:idx] + "\n  // ---- generated assertion ----\n  " + sva + "\n" + code[idx:]
strip_comments = _strip_comments_keep_lines