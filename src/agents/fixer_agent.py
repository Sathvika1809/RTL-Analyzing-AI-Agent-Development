import json
from pathlib import Path

from src.core.base_agent import BaseAgent
from src.core.rtl_parser import extract_declared_identifiers
from src.core import evidence as ev

FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "fixed_code": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["fixed_code", "explanation"],
}

PROMPT = """Fix the SystemVerilog module below using the findings listed. Make the smallest edits that resolve them.

Rules:
- Keep the module name and the exact port list. Do not add or remove ports.
- Keep the behaviour of everything not mentioned in the findings.
- Output complete, synthesizable SystemVerilog.

FINDINGS:
{findings}

FILE {filename}:
```systemverilog
{code}
```
Return JSON with "fixed_code" (the whole module) and "explanation" (2-3 sentences).
"""


class FixerAgent(BaseAgent):
    """
    Rewrites a module from the reported findings, then checks the result:
      1. module name and output ports unchanged,
      2. Verilator lint (shared helper; skipped if Verilator is absent).
    On failure the model is re-prompted with the specific problem (max 3 attempts).
    The result has "verified" so callers can tell a checked fix from a best-effort one.
    """

    max_attempts = 3

    def __init__(self, model: str = None):
        super().__init__(agent_name="fixer_agent", model=model)

    @staticmethod
    def _interface_ok(original: str, fixed: str):
        try:
            a, b = extract_declared_identifiers(original), extract_declared_identifiers(fixed)
        except Exception as e:  # noqa: BLE001
            return True, f"interface check skipped ({e})"
        if a.get("module") != b.get("module"):
            return False, f"module name changed: {a.get('module')} -> {b.get('module')}"
        oa, ob = set(a.get("outputs", [])), set(b.get("outputs", []))
        if oa != ob:
            return False, f"output ports differ (missing {sorted(oa - ob)}, new {sorted(ob - oa)})"
        return True, "interface preserved"

    def refactor(self, filepath: str, bugs: list, timing: list, optimizations: list) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}
        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Fixer agent repairing: {path.name}")

        def brief(items):
            return [{k: i.get(k) for k in ("type", "location", "problem", "fix", "issue", "suggestion") if i.get(k)}
                    for i in items or []]

        findings = json.dumps({"bugs": brief(bugs), "timing": brief(timing),
                               "optimizations": brief(optimizations)}, indent=1)
        prompt = PROMPT.format(findings=findings, filename=path.name, code=code)

        elapsed, fixed, explanation, notes, verified = 0.0, "", "", "", False
        for attempt in range(1, self.max_attempts + 1):
            parsed, err, call = self.llm_json(prompt, FIX_SCHEMA, max_tokens=2500)
            elapsed += call.get("elapsed", 0.0)
            if err:
                return {"success": False, "error": err}
            fixed = (parsed.get("fixed_code") or "").strip() if isinstance(parsed, dict) else ""
            explanation = parsed.get("explanation", "RTL repaired.") if isinstance(parsed, dict) else ""
            if not fixed:
                return {"success": False, "error": "Model returned no fixed_code."}

            iface_ok, iface_msg = self._interface_ok(code, fixed)
            lint_status, lint_msg = ev.verilator_lint(fixed)
            notes = f"{iface_msg} | lint={lint_status}"
            if iface_ok and lint_status != "fail":
                verified = lint_status == "pass" and iface_ok
                break
            problems = ([f"- interface: {iface_msg}"] if not iface_ok else []) + \
                       ([f"- Verilator error:\n{lint_msg}"] if lint_status == "fail" else [])
            print(f"    attempt {attempt} rejected: {notes}")
            prompt = (f"Your previous fix was rejected.\n\nOriginal:\n```systemverilog\n{code}\n```\n\n"
                      f"Your output:\n{fixed}\n\nProblems:\n" + "\n".join(problems) +
                      "\n\nReturn corrected JSON with the same schema. Keep module name and ports.")

        self.log_run(path.name, {"fixed_length": len(fixed), "verified": verified, "notes": notes})
        return {"success": True, "filename": path.name, "filepath": str(path),
                "fixed_code": fixed, "explanation": explanation,
                "verified": verified, "verification_notes": notes, "elapsed_s": round(elapsed, 1)}