import os
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent
from src.core.rtl_parser import (
    extract_declared_identifiers,
    static_optimizations,
    validate_optimization_against_rtl,
)

OPTIMIZER_ANALYSIS_PROMPT = """You are a senior RTL verification engineer specializing in code quality, readability, and optimization.

Analyze the following SystemVerilog module for code quality issues ONLY.
Do NOT report bugs, functional issues, or timing issues.
Focus only on optimization, maintainability, readability, and coding style.

CRITICAL RULES FOR GENERALIZED DESIGN OPTIMIZATION:

1. DECLARED ENTITIES ONLY:
First inspect the RTL and identify the exact names of all declared ports, signals, registers, wires, and parameters.
Every optimization MUST refer only to these declared identifiers.

2. DO NOT INVENT LOGIC:
Do not assume missing functionality.
Do not invent clocks, resets, parameters, signals, states, loops, protocols, or architectural intent that is not explicitly present.

3. REASON BEFORE SUGGESTING:
Evaluate whether the RTL actually contains optimization opportunities.

Only report an optimization if it provides a clear improvement in one of the following:

• Readability
• Maintainability
• Parameterization
• Removal of redundant logic
• Coding style consistency

If the implementation is already clean, parameterized, readable, and efficient, return

{{
  "declared_signals_and_parameters": [],
  "optimizations": [],
  "total_optimizations": 0,
  "quality_score": "HIGH"
}}

Never invent optimization suggestions simply to produce output.

Evaluate ONLY whether any of the following actually exist:

• HARDCODED VALUES
• NAMING ISSUES
• REDUNDANT LOGIC
• MISSING COMMENTS
• STYLE INCONSISTENCIES

If none of these are present, return an empty optimization list.

RTL Code to analyze (File: {filename}):

```systemverilog
{code}
"""


class OptimizerAgent(BaseAgent):
    """
    Specialized agent for style, readability, and optimization recommendations.
    Tier 1: rtl_parser static analysis (pyslang-backed).
    Tier 2: Ollama LLM fallback when static analysis finds nothing.

   
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

      

        from src.core.semantic_chunker import chunk_sv, select_relevant_chunks, chunks_to_prompt_text

        # Semantic chunking to focus optimization checks on relevant RTL regions.
        chunks = chunk_sv(code)
        selected = select_relevant_chunks(
            chunks,
            query=OPTIMIZER_ANALYSIS_PROMPT,
            top_k=12,
            max_total_chars=9000,
        )
        code_ctx = chunks_to_prompt_text(selected) if selected else code

        prompt = OPTIMIZER_ANALYSIS_PROMPT.format(filename=path.name, code=code_ctx)

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
            if validate_optimization_against_rtl(code, opt)
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
