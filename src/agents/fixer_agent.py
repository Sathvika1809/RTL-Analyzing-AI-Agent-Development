import os
import json
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent

FIXER_PROMPT = """You are a senior RTL verification engineer. Your task is to refactor and fix a SystemVerilog module based on a set of identified issues.

Original SystemVerilog Code (File: {filename}):
```systemverilog
{code}
```

Bugs found:
{bugs}

Timing issues found:
{timing}

Optimization suggestions:
{optimizations}

Please rewrite the SystemVerilog code to:
1. Fix all identified bugs (blocking assignments in always_ff, latch inferences in always_comb, reset mismatches, etc.).
2. Resolve all timing/pipeline issues.
3. Apply code style and parameterization optimizations.
4. Ensure the output module is complete, valid, syntactically correct, and synthesizable SystemVerilog.
5. Preserve the overall functionality, module name, and pin interface. Do not add non-existent ports or remove existing ones.

You MUST respond in a VALID JSON format matching the following JSON schema. Do not add any text outside the JSON.

JSON Schema:
{{
  "fixed_code": "The complete, refactored, and compilable SystemVerilog code as a single string",
  "explanation": "A short summary (2-3 sentences) explaining the key fixes applied"
}}
"""

class FixerAgent(BaseAgent):
    """
    Specialized agent to automatically refactor and fix SystemVerilog files based on analysis reports.
    """
    def __init__(self, model: str = None):
        super().__init__(agent_name="fixer_agent", model=model)

    def refactor(self, filepath: str, bugs: list, timing: list, optimizations: list) -> dict:
        """
        Reads original SV file, compiles prompt with analysis results,
        and requests rewritten code from Ollama in JSON format.
        """
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f" Fixer agent repairing: {path.name}")

        # Format lists for prompt
        bugs_str = json.dumps(bugs, indent=2) if bugs else "No bugs reported."
        timing_str = json.dumps(timing, indent=2) if timing else "No timing issues reported."
        opts_str = json.dumps(optimizations, indent=2) if optimizations else "No optimizations reported."

        prompt = FIXER_PROMPT.format(
            filename=path.name,
            code=code,
            bugs=bugs_str,
            timing=timing_str,
            optimizations=opts_str
        )

        # We request max_predict=2000 to ensure complete code output
        result = self.call_ollama(prompt, json_mode=True, max_tokens=2500)
        if not result["success"]:
            return {"success": False, "error": result["error"]}

        parsed_json = self.parse_json_response(result["response"])
        fixed_code = parsed_json.get("fixed_code", "")
        explanation = parsed_json.get("explanation", "RTL code repaired.")

        if not fixed_code:
            return {
                "success": False,
                "error": "Failed to parse fixed_code from LLM response",
                "raw_response": result["response"]
            }

        # Log run
        self.log_run(path.name, {
            "fixed_length": len(fixed_code),
            "explanation": explanation,
            "response_length": len(result["response"])
        })

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "fixed_code": fixed_code,
            "explanation": explanation,
            "elapsed_s": result["elapsed"]
        }
