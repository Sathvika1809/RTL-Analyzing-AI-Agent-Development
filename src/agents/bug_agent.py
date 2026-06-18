import os
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent

BUG_ANALYSIS_PROMPT = """You are a senior RTL verification engineer specializing in finding hardware bugs in SystemVerilog code.

Analyze the following SystemVerilog module for BUGS ONLY.

CRITICAL RULES FOR GENERALIZED ANALYSIS:
1. IDENTIFY DECLARED IDENTIFIERS: First, inspect the RTL code and list all ports, signals, registers, and parameters. You are strictly forbidden from referencing, assuming, or using any signal or parameter names that are not explicitly declared in this module.
2. DO NOT SPECULATE: Only report bugs that can be mathematically or logically proven from the provided RTL code.
3. CONTEXT INTEGRITY: Do not assume the existence of external logic, clock enables, or interfaces unless they are explicitly declared in the inputs/outputs of the module.
4. NO RESET CONFUSION: Analyze the exact active reset signal and active polarity (e.g. check if it is active-high 'rst' or active-low 'rst_n' or asynchronous/synchronous) and only report reset bugs matching the actual reset signal name.
5. NO SYNTHESIS SPECULATION: Do not report timing or logic optimization concerns as functional bugs.
6. If no bugs are found, you MUST return the empty JSON block: {{"declared_ports_and_signals": [], "declared_parameters": [], "bugs": [], "total_bugs": 0, "severity": "LOW"}}.

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
  "declared_ports_and_signals": [
    "list of all exact port and signal names declared in the RTL module"
  ],
  "declared_parameters": [
    "list of all parameter names declared in the RTL module (leave empty if none)"
  ],
  "bugs": [
    {{
      "type": "LATCH" | "RESET" | "FUNCTIONAL" | "WIDTH",
      "location": "exact signal/register/port name and line number where the issue occurs",
      "problem": "Clear explanation of what is wrong (2 sentences max)",
      "impact": "RTL consequence in simulation or silicon (1 sentence max)",
      "fix": "Exact code change required to resolve the issue"
    }}
  ],
  "total_bugs": 0,
  "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
}}

If no bugs are found, return:
{{
  "declared_ports_and_signals": [],
  "declared_parameters": [],
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

        result = self.call_ollama(prompt, json_mode=True, max_tokens=800)
        if not result["success"]:
            return {"success": False, "error": result["error"]}

        parsed_json = self.parse_json_response(result["response"])
        
        # Ensure fallback for fields
        if isinstance(parsed_json, list):
            bugs = parsed_json
            total_bugs = len(bugs)
            severity = "MEDIUM" if bugs else "LOW"
        else:
            bugs = parsed_json.get("bugs", []) if isinstance(parsed_json, dict) else []
            total_bugs = parsed_json.get("total_bugs", len(bugs)) if isinstance(parsed_json, dict) else len(bugs)
            severity = parsed_json.get("severity", "LOW" if not bugs else "MEDIUM") if isinstance(parsed_json, dict) else ("LOW" if not bugs else "MEDIUM")


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
