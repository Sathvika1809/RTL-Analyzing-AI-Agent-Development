import os
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent

OPTIMIZER_ANALYSIS_PROMPT = """You are a senior RTL design engineer specializing in code quality, readability, and optimization.

Analyze the following SystemVerilog module for code quality issues ONLY.
Do NOT report bugs or timing issues - only optimization and style concerns.

Check specifically for:
1. HARDCODED VALUES: Numbers that should be parameters
2. NAMING: Poor signal or module names that reduce readability
3. REDUNDANT LOGIC: Logic that can be simplified or removed
4. MISSING COMMENTS: Complex logic blocks without explanation
5. STYLE: Inconsistent formatting or coding style violations

RTL Code to analyze (File: {filename}):
```systemverilog
{code}
```

You MUST respond in a VALID JSON format matching the following JSON schema. Do not add any text outside the JSON.

JSON Schema:
{{
  "optimizations": [
    {{
      "type": "HARDCODED", "NAMING", "REDUNDANT", "COMMENT", or "STYLE",
      "location": "string detailing the signal name, line number, or block",
      "issue": "Clear description of what can be improved (2 sentences max)",
      "benefit": "Why this improvement matters (1 sentence max)",
      "suggestion": "Exact improved code or description of change"
    }}
  ],
  "total_optimizations": 0,
  "quality_score": "HIGH", "MEDIUM", or "LOW"
}}

If no optimizations are suggested, return:
{{
  "optimizations": [],
  "total_optimizations": 0,
  "quality_score": "HIGH"
}}
"""

class OptimizerAgent(BaseAgent):
    """
    Specialized agent for generating style, readability, and optimization recommendations.
    """
    def __init__(self, model: str = None):
        super().__init__(agent_name="optimizer_agent", model=model)

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Optimizer agent analyzing: {path.name}")

        prompt = OPTIMIZER_ANALYSIS_PROMPT.format(
            filename=path.name,
            code=code
        )

        result = self.call_ollama(prompt, json_mode=True)
        if not result["success"]:
            return {"success": False, "error": result["error"]}

        parsed_json = self.parse_json_response(result["response"])
        
        # Ensure fallback for fields
        optimizations = parsed_json.get("optimizations", [])
        total_optimizations = parsed_json.get("total_optimizations", len(optimizations))
        quality_score = parsed_json.get("quality_score", "HIGH" if not optimizations else "MEDIUM")

        # Format backward-compatible markdown raw_response
        raw_response = self._format_markdown_response(optimizations, total_optimizations, quality_score)

        # Log run
        self.log_run(path.name, {
            "optimizations_found": total_optimizations,
            "quality_score": quality_score,
            "response_length": len(result["response"])
        })

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "optimizations": optimizations,
            "total_optimizations": total_optimizations,
            "quality_score": quality_score,
            "raw_response": raw_response,
            "elapsed_s": result["elapsed"]
        }

    def _format_markdown_response(self, optimizations: list, total_optimizations: int, quality_score: str) -> str:
        if not optimizations:
            return "NO OPTIMIZATIONS SUGGESTED\n\nTOTAL OPTIMIZATIONS: 0\nQUALITY SCORE: HIGH\n"

        md = []
        for i, opt in enumerate(optimizations, 1):
            md.append(f"OPTIMIZATION #{i}")
            md.append(f"Type: {opt.get('type', 'UNKNOWN')}")
            md.append(f"Location: {opt.get('location', 'UNKNOWN')}")
            md.append(f"Issue: {opt.get('issue', '')}")
            md.append(f"Benefit: {opt.get('benefit', '')}")
            md.append(f"Suggestion: {opt.get('suggestion', '')}")
            md.append("")

        md.append(f"TOTAL OPTIMIZATIONS: {total_optimizations}")
        md.append(f"QUALITY SCORE: {quality_score}")
        return "\n".join(md)
