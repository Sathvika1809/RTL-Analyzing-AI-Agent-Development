import os
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent
from src.core.rtl_parser import (          # ← was rtl_static
    extract_declared_identifiers,
    is_concrete_finding,
    references_only_declared,
    static_optimizations,
)

OPTIMIZER_ANALYSIS_PROMPT = """You are a senior RTL verification engineer specializing in code quality, readability, and optimization.

Analyze the following SystemVerilog module for code quality issues ONLY.
Do NOT report bugs or timing issues - only optimization and style concerns.

CRITICAL RULES FOR GENERALIZED DESIGN OPTIMIZATION:
1. DECLARED ENTITIES ONLY: First, inspect the RTL code and identify the exact names of all declared signals, registers, ports, and parameters. Any optimization, refactoring, or renaming suggestions you report MUST strictly refer only to these declared signals and parameters.
2. DO NOT INVENT LOGIC: Do not suggest optimizing code, clocks, resets, parameters, or structures that are not explicitly present in the provided file.
3. STYLE AND PPA FOCUS: Suggestions should focus on improving readability, parameterizing hardcoded values, or simplifying redundant logic paths.
4. If no optimizations are suggested, you MUST return: {{"declared_signals_and_parameters": [], "optimizations": [], "total_optimizations": 0, "quality_score": "HIGH"}}.

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
  "declared_signals_and_parameters": [
    "exact names of all signals, registers, ports, and parameters in the module"
  ],
  "optimizations": [
    {{
      "type": "HARDCODED" | "NAMING" | "REDUNDANT" | "COMMENT" | "STYLE",
      "location": "exact line number or block name",
      "issue": "Clear description of what can be improved (2 sentences max)",
      "benefit": "Why this improvement matters (1 sentence max)",
      "suggestion": "Exact improved code or description of change"
    }}
  ],
  "total_optimizations": 0,
  "quality_score": "HIGH" | "MEDIUM" | "LOW"
}}

If no optimizations are suggested, return:
{{
  "declared_signals_and_parameters": [],
  "optimizations": [],
  "total_optimizations": 0,
  "quality_score": "HIGH"
}}
"""


class OptimizerAgent(BaseAgent):
    """
    Specialized agent for style, readability, and optimization recommendations.
    Tier 1: rtl_parser static analysis (pyslang-backed).
    Tier 2: Ollama LLM fallback when static analysis finds nothing.

    FIX: the Ollama fallback path was previously unreachable dead code because
    an unconditional early return fired whenever static_opts was empty.
    That return has been removed so Ollama is now actually called.
    """

    def __init__(self, model: str = None):
        super().__init__(agent_name="optimizer_agent", model=model)

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Optimizer agent analyzing: {path.name}")

        static_opts = static_optimizations(code)
        if static_opts:
            total_optimizations = len(static_opts)
            quality_score       = "MEDIUM"
            raw_response        = self._format_markdown_response(static_opts, total_optimizations, quality_score)
            self.log_run(path.name, {
                "optimizations_found": total_optimizations,
                "quality_score":       quality_score,
                "response_length":     len(raw_response),
                "source":              "static",
            })
            return {
                "success":            True,
                "filename":           path.name,
                "filepath":           str(path),
                "timestamp":          datetime.now().isoformat(),
                "model":              self.model,
                "optimizations":      static_opts,
                "total_optimizations": total_optimizations,
                "quality_score":      quality_score,
                "raw_response":       raw_response,
                "elapsed_s":          0.0,
            }

        # ── No static findings — fall through to Ollama ──────────────────────
        # (Previously this path was dead code: an unconditional return above
        #  prevented the prompt from ever being built or Ollama being called.)
        prompt = OPTIMIZER_ANALYSIS_PROMPT.format(filename=path.name, code=code)
        result = self.call_ollama(prompt, json_mode=True, max_tokens=800)
        if not result["success"]:
            return {"success": False, "error": result["error"]}

        parsed_json = self.parse_json_response(result["response"])
        parse_error = self.json_parse_error(parsed_json)
        if parse_error:
            return {"success": False, "error": parse_error}

        if isinstance(parsed_json, list):
            optimizations       = parsed_json
            total_optimizations = len(optimizations)
            quality_score       = "MEDIUM" if optimizations else "HIGH"
        else:
            optimizations       = parsed_json.get("optimizations", []) if isinstance(parsed_json, dict) else []
            total_optimizations = parsed_json.get("total_optimizations", len(optimizations)) if isinstance(parsed_json, dict) else len(optimizations)
            quality_score       = parsed_json.get("quality_score", "HIGH" if not optimizations else "MEDIUM") if isinstance(parsed_json, dict) else ("HIGH" if not optimizations else "MEDIUM")

        declared = (
            set(extract_declared_identifiers(code)["signals"])
            | set(extract_declared_identifiers(code)["parameters"])
        )
        optimizations = [
            opt for opt in optimizations
            if references_only_declared(opt, declared) and is_concrete_finding(opt, declared)
        ]
        total_optimizations = len(optimizations)
        quality_score       = "HIGH" if not optimizations else quality_score
        raw_response        = self._format_markdown_response(optimizations, total_optimizations, quality_score)

        self.log_run(path.name, {
            "optimizations_found": total_optimizations,
            "quality_score":       quality_score,
            "response_length":     len(result["response"]),
        })

        return {
            "success":             True,
            "filename":            path.name,
            "filepath":            str(path),
            "timestamp":           datetime.now().isoformat(),
            "model":               self.model,
            "optimizations":       optimizations,
            "total_optimizations": total_optimizations,
            "quality_score":       quality_score,
            "raw_response":        raw_response,
            "elapsed_s":           result["elapsed"],
        }

    def _format_markdown_response(
        self, optimizations: list, total_optimizations: int, quality_score: str
    ) -> str:
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
