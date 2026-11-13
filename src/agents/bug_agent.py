import json
from datetime import datetime
from pathlib import Path

from src.core.base_agent import BaseAgent
from src.core.rtl_parser import extract_declared_identifiers, static_bug_findings
from src.core import evidence as ev

BUG_TYPES = {"LATCH", "RESET", "FUNCTIONAL", "WIDTH"}

BUG_SCHEMA = {
    "type": "object",
    "properties": {
        "bugs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": sorted(BUG_TYPES)},
                    "signal": {"type": "string"},
                    "evidence": {"type": "string"},
                    "problem": {"type": "string"},
                    "impact": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["type", "signal", "evidence", "problem", "impact", "fix"],
            },
        }
    },
    "required": ["bugs"],
}

PROMPT = """You are an RTL reviewer. Find functional bugs in the SystemVerilog below that you can prove from the code.

Rules:
- "evidence" must be an exact snippet copied from the code (one or two lines, without the line-number prefix).
- "signal" must be a name declared in the module.
- Do not repeat issues listed under ALREADY FOUND.
- Look for what pattern checks miss: wrong state transitions, off-by-one or wrong full/empty/credit logic, mask or shift width errors, data and control misaligned, parameter assumptions.
- Do not report style, naming or timing constraints. Do not guess about protocols that are not in the code.
- If nothing is provable, return {{"bugs": []}}.

ALREADY FOUND (static analysis):
{static}

FILE {filename}:
{code}
"""


class BugAgent(BaseAgent):
    """Static findings are the source of truth; the LLM may add grounded extras."""

    def __init__(self, model: str = None):
        super().__init__(agent_name="bug_agent", model=model)

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}
        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Bug agent analyzing: {path.name}")

        static = ev.safe_static(static_bug_findings, code)
        for b in static:
            b["source"] = "static"

        try:
            declared = ev.declared_names(extract_declared_identifiers(code))
        except Exception:  # noqa: BLE001
            declared = set()

        llm, stats, err, elapsed = self._run_llm(code, path, static, declared)
        if err and not static:
            return {"success": False, "error": err}

        merged = ev.merge_dedupe(static, llm, lambda b: (b["type"].upper(), ev.first_token(b.get("location", ""))))

        llm_n = sum(1 for x in merged if x.get('source') == 'llm')
        severity = "LOW" if not merged else ("HIGH" if any(b["type"] in {"FUNCTIONAL", "WIDTH"} for b in merged) else "MEDIUM")
        raw = self._format(merged, severity)

        self.log_run(path.name, {
            "bugs_found": len(merged), "severity": severity,
            "static_count": len(static), "llm_count": llm_n,
            "llm_stats": stats, "llm_error": err, "response_length": len(raw),
        })
        return {
            "success": True, "filename": path.name, "filepath": str(path),
            "timestamp": datetime.now().isoformat(), "model": self.model,
            "bugs": merged, "total_bugs": len(merged), "severity": severity,
            "raw_response": raw, "elapsed_s": elapsed,
            "static_count": len(static), "llm_count": llm_n,
            "llm_stats": stats, "llm_error": err,
        }

    def _run_llm(self, code, path, static, declared):
        static_txt = json.dumps(
            [{"type": b.get("type"), "location": b.get("location")} for b in static], indent=1
        ) if static else "(none)"
        prompt = PROMPT.format(static=static_txt, filename=path.name, code=ev.build_code_context(code))
        parsed, err, call = self.llm_json(prompt, BUG_SCHEMA, max_tokens=1200)
        if err:
            return [], {"returned": 0, "kept": 0, "rejected": {}}, err, 0.0

        items = ev.extract_list(parsed, "bugs")
        kept, stats = ev.validate_llm_findings(items, code, declared, BUG_TYPES)
        for b in kept:
            b["location"] = f"{b.get('signal') or 'module'} at line {b['line']}"
        ev.print_stats(self.agent_name, stats, call)
        return kept, stats, None, call.get("elapsed", 0.0)

    @staticmethod
    def _format(bugs, severity):
        if not bugs:
            return "NO BUGS DETECTED\n\nTOTAL BUGS: 0\nSEVERITY: LOW\n"
        body = ev.format_items(bugs, "BUG", [("Type", "type"), ("Location", "location"),
                                              ("Problem", "problem"), ("Impact", "impact"), ("Fix", "fix")])
        return f"{body}\nTOTAL BUGS: {len(bugs)}\nSEVERITY: {severity}"