from datetime import datetime
from pathlib import Path

from src.core.base_agent import BaseAgent
from src.core.rtl_parser import extract_declared_identifiers, static_optimizations
from src.core import evidence as ev

OPT_TYPES = {"HARDCODED", "NAMING", "REDUNDANT", "STYLE", "COMMENTS"}

OPT_SCHEMA = {
    "type": "object",
    "properties": {
        "optimizations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": sorted(OPT_TYPES)},
                    "signal": {"type": "string"},
                    "evidence": {"type": "string"},
                    "issue": {"type": "string"},
                    "benefit": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["type", "signal", "evidence", "issue", "benefit", "suggestion"],
            },
        }
    },
    "required": ["optimizations"],
}

PROMPT = """You review SystemVerilog for readability and maintainability only. Do not report bugs or timing.

Report an item only if the code clearly shows one of:
- HARDCODED: a literal that should use a declared parameter (for example a width written as a number).
- REDUNDANT: logic that has no effect (for example an assignment of a signal to itself).
- NAMING: names that are misleading or inconsistent with neighbouring names.
- STYLE: inconsistent coding style across similar blocks.
- COMMENTS: a non-obvious block with no comment.

Rules:
- "evidence" must be an exact snippet copied from the code (no line-number prefix).
- "signal" must be declared in the module.
- Do not repeat these already-found items: {static}
- If the code is clean, return {{"optimizations": []}}. Do not invent suggestions to have output.

FILE {filename}:
{code}
"""


class OptimizerAgent(BaseAgent):
    """
    Static HARDCODED findings + LLM suggestions for NAMING/REDUNDANT/STYLE/COMMENTS.
    The old validator accepted an LLM item only if it matched a static HARDCODED finding,
    so every other category was dropped. Now an LLM item is accepted when it quotes real
    code and names a declared signal (same rule as the other agents).
    """

    def __init__(self, model: str = None):
        super().__init__(agent_name="optimizer_agent", model=model)

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}
        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Optimizer agent analyzing: {path.name}")

        static = ev.safe_static(static_optimizations, code)
        for o in static:
            o["source"] = "static"
        try:
            declared = ev.declared_names(extract_declared_identifiers(code))
        except Exception:  # noqa: BLE001
            declared = set()

        llm, stats, err, elapsed = self._run_llm(code, path, static, declared)
        if err and not static:
            return {"success": False, "error": err}

        merged = ev.merge_dedupe(static, llm, lambda o: (str(o.get("type", "")).upper(), ev.first_token(o.get("location", ""))))

        llm_n = sum(1 for x in merged if x.get('source') == 'llm')
        quality = "HIGH" if len(merged) == 0 else ("MEDIUM" if len(merged) <= 5 else "LOW")
        raw = self._format(merged, quality)

        self.log_run(path.name, {
            "optimizations_found": len(merged), "quality_score": quality,
            "static_count": len(static), "llm_count": llm_n,
            "llm_stats": stats, "llm_error": err, "response_length": len(raw),
        })
        return {
            "success": True, "filename": path.name, "filepath": str(path),
            "timestamp": datetime.now().isoformat(), "model": self.model,
            "optimizations": merged, "total_optimizations": len(merged), "quality_score": quality,
            "raw_response": raw, "elapsed_s": elapsed,
            "static_count": len(static), "llm_count": llm_n,
            "llm_stats": stats, "llm_error": err,
        }

    def _run_llm(self, code, path, static, declared):
        static_txt = "; ".join(str(o.get("location", "")) for o in static) or "none"
        prompt = PROMPT.format(static=static_txt, filename=path.name,
                               code=ev.build_code_context(code, "parameter assign always style"))
        parsed, err, call = self.llm_json(prompt, OPT_SCHEMA, max_tokens=900)
        if err:
            return [], {"returned": 0, "kept": 0, "rejected": {}}, err, 0.0
        kept, stats = ev.validate_llm_findings(ev.extract_list(parsed, "optimizations"), code, declared, OPT_TYPES)
        for o in kept:
            o["location"] = f"{o.get('signal') or 'module'} at line {o['line']}"
        ev.print_stats(self.agent_name, stats, call)
        return kept, stats, None, call.get("elapsed", 0.0)

    @staticmethod
    def _format(opts, quality):
        if not opts:
            return "NO OPTIMIZATIONS SUGGESTED\n\nTOTAL OPTIMIZATIONS: 0\nQUALITY SCORE: HIGH\n"
        body = ev.format_items(opts, "OPTIMIZATION", [("Type", "type"), ("Location", "location"),
                                                       ("Issue", "issue"), ("Benefit", "benefit"),
                                                       ("Suggestion", "suggestion")])
        return f"{body}\nTOTAL OPTIMIZATIONS: {len(opts)}\nQUALITY SCORE: {quality}"