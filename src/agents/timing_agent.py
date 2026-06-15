import os
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent

TIMING_ANALYSIS_PROMPT = """You are a senior RTL verification engineer specializing in checking timing and pipeline problems.

Analyze the following SystemVerilog code for timing issues ONLY.
Check specifically for:
1. Blocking assignments in always_ff blocks
2. Signals missing from sensitivity lists in always @(*)
3. Clock domain crossings (CDC) without synchronizers
4. Long combinational chains between registers (timing bottleneck)
5. Incomplete case statements or conditional branches causing latch inference

RTL Code to analyze (File: {filename}):
```systemverilog
{code}
```

You MUST respond in a VALID JSON format matching the following JSON schema. Do not add any text outside the JSON.

JSON Schema:
{{
  "timing_issues": [
    {{
      "type": "BLOCKING", "CDC", "SENSITIVITY", "LATCH", or "COMBO_PATH",
      "location": "string detailing the signal name, block, or line numbers",
      "problem": "Clear explanation of what is wrong (2 sentences max)",
      "risk": "Silicon failure risk or timing violation description (1 sentence max)",
      "fix": "Exact code change required to resolve the issue"
    }}
  ],
  "total_issues": 0,
  "risk": "HIGH", "MEDIUM", or "LOW"
}}

If no issues are found, return:
{{
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

        result = self.call_ollama(prompt, json_mode=True)
        if not result["success"]:
            return {"success": False, "error": result["error"]}

        parsed_json = self.parse_json_response(result["response"])
        
        # Ensure fallback for fields
        issues = parsed_json.get("timing_issues", [])
        total_issues = parsed_json.get("total_issues", len(issues))
        risk = parsed_json.get("risk", "LOW" if not issues else "MEDIUM")

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
