import re
from datetime import datetime
from pathlib import Path

from src.core.base_agent import BaseAgent
from src.core.rtl_parser import extract_declared_identifiers, static_timing_findings
from src.core import evidence as ev

# Static analysis already covers BLOCKING and LATCH. The LLM is only asked for
# things that need cross-signal reasoning.
LLM_TYPES = {"CDC", "COMBO_PATH", "SENSITIVITY"}

TIMING_SCHEMA = {
    "type": "object",
    "properties": {
        "timing_issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": sorted(LLM_TYPES)},
                    "signal": {"type": "string"},
                    "evidence": {"type": "string"},
                    "problem": {"type": "string"},
                    "risk": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["type", "signal", "evidence", "problem", "risk", "fix"],
            },
        }
    },
    "required": ["timing_issues"],
}

PROMPT = """You are an RTL timing reviewer. Report only issues provable from the code below.

Allowed types:
- CDC: a signal driven from one clock domain and captured in another with no synchronizer visible in the code. Clocks used in this file: {clocks}.
- SENSITIVITY: a hand-written sensitivity list that misses a signal read in the block.
- COMBO_PATH: a clearly excessive combinational chain. Never report simple muxes, comparators or adders.

Rules:
- "evidence" must be an exact snippet copied from the code (no line-number prefix).
- "signal" must be declared in the module.
- Do not report blocking assignments, latches or setup/hold; those are handled elsewhere.
- Do not invent clocks, constraints or frequencies. If nothing is provable, return {{"timing_issues": []}}.

FILE {filename}:
{code}
"""


class TimingAgent(BaseAgent):
    """Static tier for BLOCKING/LATCH/SENSITIVITY, grounded LLM tier for CDC and combo paths."""

    def __init__(self, model: str = None):
        super().__init__(agent_name="timing_agent", model=model)

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}
        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Timing agent analyzing: {path.name}")

        static = ev.safe_static(static_timing_findings, code)
        for i in static:
            i["source"] = "static"

        try:
            declared = ev.declared_names(extract_declared_identifiers(code))
        except Exception:  # noqa: BLE001
            declared = set()

        llm, stats, err, elapsed = self._run_llm(code, path, declared)
        if err and not static:
            return {"success": False, "error": err}

        merged = ev.merge_dedupe(static, llm, lambda i: (i["type"].upper(), ev.first_token(i.get("location", ""))))

        llm_n = sum(1 for x in merged if x.get('source') == 'llm')
        risk = "LOW" if not merged else ("HIGH" if any(i["type"] in {"CDC", "BLOCKING"} for i in merged) else "MEDIUM")
        raw = self._format(merged, risk)

        self.log_run(path.name, {
            "issues_found": len(merged), "risk": risk,
            "static_count": len(static), "llm_count": llm_n,
            "llm_stats": stats, "llm_error": err, "response_length": len(raw),
        })
        return {
            "success": True, "filename": path.name, "filepath": str(path),
            "timestamp": datetime.now().isoformat(), "model": self.model,
            "timing_issues": merged, "total_issues": len(merged), "risk": risk,
            "raw_response": raw, "elapsed_s": elapsed,
            "static_count": len(static), "llm_count": llm_n,
            "llm_stats": stats, "llm_error": err,
        }

    def _run_llm(self, code, path, declared):
        clocks = ev.clocks_in_code(code)
        prompt = PROMPT.format(clocks=", ".join(clocks) or "none", filename=path.name,
                               code=ev.build_code_context(code, "clock always posedge sensitivity assign"))
        parsed, err, call = self.llm_json(prompt, TIMING_SCHEMA, max_tokens=1000)
        if err:
            return [], {"returned": 0, "kept": 0, "rejected": {}}, err, 0.0

        # Structural gate, not name-based: CDC needs at least two distinct clocks in the file.
        def gate(item):
            t = str(item.get("type", "")).upper()
            if t == "CDC" and len(clocks) < 2:
                return "cdc_needs_two_clocks"
            if t == "SENSITIVITY" and re.search(r"\b(always_ff|posedge|negedge)\b", item.get("evidence", "")):
                return "sensitivity_in_sequential_block"
            if t == "COMBO_PATH":
                evd = item.get("evidence", "")
                ops = re.findall(r"(\+|\-|\*|/|==|!=|<=|>=|<|>|&&|\|\||\?|:|&|\||\^|<<|>>)", evd)
                if len(ops) < 3:
                    return "trivial_combo_path"
            return None
        kept, stats = ev.validate_llm_findings(
            ev.extract_list(parsed, "timing_issues"), code, declared, LLM_TYPES, drop_if=gate)
        for i in kept:
            i["location"] = f"{i.get('signal') or 'module'} at line {i['line']}"
        ev.print_stats(self.agent_name, stats, call)
        return kept, stats, None, call.get("elapsed", 0.0)

    @staticmethod
    def _format(issues, risk):
        if not issues:
            return "NO TIMING ISSUES DETECTED\n\nTOTAL TIMING ISSUES: 0\nRISK LEVEL: LOW\n"
        body = ev.format_items(issues, "TIMING ISSUE", [("Type", "type"), ("Location", "location"),
                                                        ("Problem", "problem"), ("Risk", "risk"), ("Fix", "fix")])
        return f"{body}\nTOTAL TIMING ISSUES: {len(issues)}\nRISK LEVEL: {risk}"