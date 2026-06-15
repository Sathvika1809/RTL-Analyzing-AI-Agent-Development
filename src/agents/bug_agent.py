import os
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent

BUG_ANALYSIS_PROMPT = """You are a senior RTL verification engineer specializing in finding hardware bugs in SystemVerilog code.

Analyze the following SystemVerilog module for BUGS ONLY.
Check specifically for:
1. LATCH INFERENCE:
    - Signals assigned inside always_comb or always @(*) without a complete if-else
    - Variables not assigned in all branches
    - Missing default assignments before conditional logic
    
2. RESET PROBLEMS:
    - Flip-flops (always_ff blocks) where signals are not reset
    - Inconsistent reset polarity (mixing active-high and active-low)
    - Signals only reset in some conditions but not others

3. FUNCTIONAL BUGS:
    - Counter overflow not handled
    - Multiple drivers on the same signal
    - Blocking assignments (=) used inside always_ff instead of non-blocking (<=)
    - Race conditions between concurrent always blocks
    
4. WIDTH MISMATCHES:
    - Hardcoded bit widths that don't match parameter sizes
    - Truncation or sign extension issues

RTL Code to analyze (File: {filename}):
```systemverilog
{code}
```

You MUST respond in a VALID JSON format matching the following JSON schema. Do not add any text outside the JSON.

JSON Schema:
{{
  "bugs": [
    {{
      "type": "LATCH", "RESET", "FUNCTIONAL", or "WIDTH",
      "location": "string detailing the signal name, block, or line numbers",
      "problem": "Clear explanation of what is wrong (2 sentences max)",
      "impact": "RTL consequence in simulation or silicon (1 sentence max)",
      "fix": "Exact code change required to resolve the issue"
    }}
  ],
  "total_bugs": 0,
  "severity": "CRITICAL", "HIGH", "MEDIUM", or "LOW"
}}

If no bugs are found, return:
{{
  "bugs": [],
  "total_bugs": 0,
  "severity": "LOW"
}}
"""

class BugAgent(BaseAgent):
    """
    Specialized agent for identifying RTL bugs, latches, and resets.
    """
    def __init__(self, model: str = None):
        super().__init__(agent_name="bug_agent", model=model)

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f" Bug agent analyzing: {path.name}")

        prompt = BUG_ANALYSIS_PROMPT.format(
            filename=path.name,
            code=code
        )

        result = self.call_ollama(prompt, json_mode=True)
        if not result["success"]:
            return {"success": False, "error": result["error"]}

        parsed_json = self.parse_json_response(result["response"])
        
        # Ensure fallback for fields
        bugs = parsed_json.get("bugs", [])
        total_bugs = parsed_json.get("total_bugs", len(bugs))
        severity = parsed_json.get("severity", "LOW" if not bugs else "MEDIUM")

        # Format backward-compatible markdown raw_response
        raw_response = self._format_markdown_response(bugs, total_bugs, severity)

        # Log run
        self.log_run(path.name, {
            "bugs_found": total_bugs,
            "severity": severity,
            "response_length": len(result["response"])
        })

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "bugs": bugs,
            "total_bugs": total_bugs,
            "severity": severity,
            "raw_response": raw_response,
            "elapsed_s": result["elapsed"]
        }

    def _format_markdown_response(self, bugs: list, total_bugs: int, severity: str) -> str:
        if not bugs:
            return "NO BUGS DETECTED\n\nTOTAL BUGS: 0\nSEVERITY: LOW\n"

        md = []
        for i, bug in enumerate(bugs, 1):
            md.append(f"BUG #{i}")
            md.append(f"Type: {bug.get('type', 'UNKNOWN')}")
            md.append(f"Location: {bug.get('location', 'UNKNOWN')}")
            md.append(f"Problem: {bug.get('problem', '')}")
            md.append(f"Impact: {bug.get('impact', '')}")
            md.append(f"Fix: {bug.get('fix', '')}")
            md.append("")

        md.append(f"TOTAL BUGS: {total_bugs}")
        md.append(f"SEVERITY: {severity}")
        return "\n".join(md)
