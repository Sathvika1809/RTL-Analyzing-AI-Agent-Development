import os
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent

TIMING_ANALYSIS_PROMPT = """You are a senior RTL lint and verification engineer.

Your task is to identify ONLY RTL timing-related issues that can be PROVEN directly from the provided SystemVerilog code.

CRITICAL RULES FOR GENERALIZED TIMING ANALYSIS:
1. IDENTIFY DECLARED IDENTIFIERS: First, inspect the RTL code and identify the exact names of all clocks, resets, and internal/port signals. You are strictly forbidden from referencing, assuming, or using any signal or clock names that are not explicitly declared in this module.
2. DO NOT SPECULATE: Only report timing issues (such as blocking assignments in sequential blocks, manual sensitivity list issues, CDC issues, or latch inferences) that can be logically proven from the provided RTL code.
3. CONTEXT INTEGRITY: Do not assume the existence of external clocks, synchronization cells, or constraints unless they are explicitly declared in the RTL.
4. If no provable timing issues exist, you MUST return: {{"declared_clocks_and_resets": [], "declared_signals": [], "timing_issues": [], "total_issues": 0, "risk": "LOW"}}.

Check ONLY for the following:

A. BLOCKING

* Blocking assignment (=) inside always_ff blocks.

B. SENSITIVITY

* Incomplete/manual sensitivity lists that miss signals.
* Ignore always_comb.
* Ignore always @(*).

C. CDC

* Signals transferred between different clock domains
  without an obvious synchronizer structure.

D. LATCH

* Incomplete assignments in combinational logic causing
  latch inference.

E. COMBO_PATH

* Report ONLY when a clearly excessive combinational chain
  is visible in RTL.
* Do NOT report simple comparators, muxes, arithmetic,
  FIFO full/empty logic, or ordinary combinational logic.
* If uncertain, do NOT report.

RTL Code to analyze (File: {filename}):

```systemverilog
{code}
```

Return ONLY valid JSON.

JSON Schema:

{{
"declared_clocks_and_resets": [
  "exact names of all clock and reset signals declared in the module"
],
"declared_signals": [
  "exact names of all internal and port signals declared in the module"
],
"timing_issues": [
{{
"type": "BLOCKING | CDC | SENSITIVITY | LATCH | COMBO_PATH",
"location": "line number or block description",
"evidence": "exact RTL snippet proving the issue",
"confidence": "HIGH | MEDIUM | LOW",
"problem": "brief explanation",
"risk": "brief risk description",
"fix": "exact code change"
}}
],
"total_issues": 0,
"risk": "LOW | MEDIUM | HIGH"
}}

If no provable issues exist:

{{
"declared_clocks_and_resets": [],
"declared_signals": [],
"timing_issues": [],
"total_issues": 0,
"risk": "LOW"
}}
"""

class TimingAgent(BaseAgent):
    """
    Specialized agent for identifying timing hazards, CDC, and blocking assignments in sequential blocks.
    """
    def __init__(self, model: str = None):
        super().__init__(agent_name="timing_agent", model=model)

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f" Timing agent analyzing: {path.name}")

        prompt = TIMING_ANALYSIS_PROMPT.format(
            filename=path.name,
            code=code
        )

        result = self.call_ollama(prompt, json_mode=True, max_tokens=800)
        if not result["success"]:
            return {"success": False, "error": result["error"]}

        parsed_json = self.parse_json_response(result["response"])
        
        # Ensure fallback for fields
        if isinstance(parsed_json, list):
            issues = parsed_json
            total_issues = len(issues)
            risk = "MEDIUM" if issues else "LOW"
        else:
            issues = parsed_json.get("timing_issues", []) if isinstance(parsed_json, dict) else []
            total_issues = parsed_json.get("total_issues", len(issues)) if isinstance(parsed_json, dict) else len(issues)
            risk = parsed_json.get("risk", "LOW" if not issues else "MEDIUM") if isinstance(parsed_json, dict) else ("LOW" if not issues else "MEDIUM")


        # Format backward-compatible markdown raw_response
        raw_response = self._format_markdown_response(issues, total_issues, risk)

        # Log run
        self.log_run(path.name, {
            "issues_found": total_issues,
            "severity": risk,
            "response_length": len(result["response"])
        })

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "timing_issues": issues,
            "total_issues": total_issues,
            "risk": risk,
            "raw_response": raw_response,
            "elapsed_s": result["elapsed"]
        }

    def _format_markdown_response(self, issues: list, total_issues: int, risk: str) -> str:
        if not issues:
            return "NO TIMING ISSUES DETECTED\n\nTOTAL TIMING ISSUES: 0\nRISK LEVEL: LOW\n"

        md = []
        for i, issue in enumerate(issues, 1):
            md.append(f"TIMING ISSUE #{i}")
            md.append(f"Type: {issue.get('type', 'UNKNOWN')}")
            md.append(f"Location: {issue.get('location', 'UNKNOWN')}")
            md.append(f"Problem: {issue.get('problem', '')}")
            md.append(f"Risk: {issue.get('risk', '')}")
            md.append(f"Fix: {issue.get('fix', '')}")
            md.append("")

        md.append(f"TOTAL TIMING ISSUES: {total_issues}")
        md.append(f"RISK LEVEL: {risk}")
        return "\n".join(md)
