import os
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent

ASSERTION_ANALYSIS_PROMPT = """You are a senior RTL verification engineer specializing in writing SystemVerilog Assertions (SVA).

Analyze the following SystemVerilog module and generate SVA assertions.
Generate ONLY assertions that can be directly inferred from the RTL. Do not invent signals or behaviors.

Prefer concrete assertions over generic recommendations:
1. RESET BEHAVIOR: After reset, outputs should reach known values
2. SIGNAL RANGES: Outputs should stay within valid bit ranges
3. STATE TRANSITIONS: Valid state changes only (e.g. for FSMs)
4. OVERFLOW PROTECTION: Counters/accumulators should be checked
5. INPUT VALIDITY: Critical inputs behave as expected

RTL Code to analyze (File: {filename}):
```systemverilog
{code}
```

You MUST respond in a VALID JSON format matching the following JSON schema. Do not add any text outside the JSON.

JSON Schema:
{{
  "assertions": [
    {{
      "type": "RESET", "RANGE", "TRANSITION", "OVERFLOW", or "INPUT",
      "signal": "string containing name of the signal covered",
      "sva_code": "assert property (@(posedge clk) ... );",
      "description": "Clear explanation of what this assertion checks"
    }}
  ],
  "total_assertions": 0,
  "coverage": "HIGH", "MEDIUM", or "LOW"
}}

If no assertions can be generated, return:
{{
  "assertions": [],
  "total_assertions": 0,
  "coverage": "LOW"
}}
"""

class AssertionAgent(BaseAgent):
    """
    Specialized agent for generating SystemVerilog Assertions (SVA) based on module design logic.
    """
    def __init__(self, model: str = None):
        super().__init__(agent_name="assertion_agent", model=model)

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Assertion agent analyzing: {path.name}")

        prompt = ASSERTION_ANALYSIS_PROMPT.format(
            filename=path.name,
            code=code
        )

        result = self.call_ollama(prompt, json_mode=True)
        if not result["success"]:
            return {"success": False, "error": result["error"]}

        parsed_json = self.parse_json_response(result["response"])
        
        # Ensure fallback for fields
        assertions = parsed_json.get("assertions", [])
        total_assertions = parsed_json.get("total_assertions", len(assertions))
        coverage = parsed_json.get("coverage", "LOW" if not assertions else "MEDIUM")

        # Format backward-compatible markdown raw_response
        raw_response = self._format_markdown_response(assertions, total_assertions, coverage)

        # Log run
        self.log_run(path.name, {
            "assertions_generated": total_assertions,
            "coverage": coverage,
            "response_length": len(result["response"])
        })

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "assertions": assertions,
            "total_assertions": total_assertions,
            "coverage": coverage,
            "raw_response": raw_response,
            "elapsed_s": result["elapsed"]
        }

    def _format_markdown_response(self, assertions: list, total_assertions: int, coverage: str) -> str:
        if not assertions:
            return "NO ASSERTIONS GENERATED\n\nTOTAL ASSERTIONS: 0\nCOVERAGE LEVEL: LOW\n"

        md = []
        for i, assertion in enumerate(assertions, 1):
            md.append(f"ASSERTION #{i}")
            md.append(f"Type: {assertion.get('type', 'UNKNOWN')}")
            md.append(f"Signal: {assertion.get('signal', 'UNKNOWN')}")
            md.append(f"SVA Code:\n{assertion.get('sva_code', '')}")
            md.append(f"Description: {assertion.get('description', '')}")
            md.append("")

        md.append(f"TOTAL ASSERTIONS: {total_assertions}")
        md.append(f"COVERAGE LEVEL: {coverage}")
        return "\n".join(md)
