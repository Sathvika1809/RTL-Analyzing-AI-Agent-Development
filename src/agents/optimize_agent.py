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

# Files at or below this size get the FULL module passed to the LLM with no
# chunking, so it can reason about repeated patterns across the whole module
# (needed for REDUNDANT/STYLE checks that span multiple blocks).
SMALL_FILE_CHAR_THRESHOLD = 6000


class OptimizerAgent(BaseAgent):
    """
    Specialized agent for style, readability, and optimization recommendations.

    Both tiers now ALWAYS run and their findings are merged:
      Tier 1: rtl_parser static analysis (pyslang-backed) - detects HARDCODED
              literal values only.
      Tier 2: Ollama LLM - the only tier that can flag NAMING, REDUNDANT,
              MISSING_COMMENTS, and STYLE issues, per the prompt.

    Previously tier 2 was skipped entirely whenever tier 1 found anything,
    which for most real files (very common to have at least one bare integer
    literal) meant NAMING/REDUNDANT/STYLE/COMMENT feedback never ran at all.

    NOTE (flagged, not silently changed): validate_optimization_against_rtl()
    in rtl_parser.py currently only accepts an LLM optimization if it matches
    a *static* finding, and static_optimizations() only ever produces
    HARDCODED findings. That means, even with tier-merging fixed here, LLM
    optimizations of type NAMING / REDUNDANT / MISSING_COMMENTS / STYLE will
    still be filtered out by that validator every time. If you want those
    categories to actually surface, the validator needs a second acceptance
    path (e.g. declared-identifiers-only check via references_only_declared,
    similar to how bug/timing agents validate LLM output) rather than
    requiring a matching static finding. I left rtl_parser.py untouched
    pending your call on this.
    """

    def __init__(self, model: str = None):
        super().__init__(agent_name="optimizer_agent", model=model)

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Optimizer agent analyzing: {path.name}")

        # ---- Tier 1: static analysis (always runs) ----
        static_opts = static_optimizations(code)
        for o in static_opts:
            o["source"] = "static"

        # ---- Tier 2: LLM analysis (always runs) ----
        llm_opts, llm_error, llm_elapsed = self._run_llm_analysis(code, path)

        if llm_error and not static_opts:
            return {"success": False, "error": llm_error}

        # ---- Merge + dedupe ----
        merged_opts = self._merge_and_dedupe(static_opts, llm_opts)
        total_optimizations = len(merged_opts)
        quality_score = "HIGH" if not merged_opts else "MEDIUM"
        raw_response = self._format_markdown_response(merged_opts, total_optimizations, quality_score)

        self.log_run(path.name, {
            "optimizations_found": total_optimizations,
            "quality_score": quality_score,
            "static_count": len(static_opts),
            "llm_count": len(llm_opts),
            "response_length": len(raw_response),
            "source": "merged",
        })

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "optimizations": merged_opts,
            "total_optimizations": total_optimizations,
            "quality_score": quality_score,
            "raw_response": raw_response,
            "elapsed_s": llm_elapsed,
        }

    def _run_llm_analysis(self, code: str, path: Path):
        """Runs the LLM tier and returns (optimizations, error, elapsed).

        On any failure, returns ([], error_message, 0.0) so the caller can
        still fall back to static-only results instead of failing outright.
        """
        if len(code) <= SMALL_FILE_CHAR_THRESHOLD:
            code_ctx = code
        else:
            from src.core.semantic_chunker import chunk_sv, select_relevant_chunks, chunks_to_prompt_text
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
            return [], result["error"], 0.0

        parsed_json = self.parse_json_response(result["response"])
        parse_error = self.json_parse_error(parsed_json)
        if parse_error:
            return [], parse_error, result.get("elapsed", 0.0)

        if isinstance(parsed_json, list):
            optimizations = parsed_json
        else:
            optimizations = parsed_json.get("optimizations", []) if isinstance(parsed_json, dict) else []

        # See class docstring NOTE: this validator currently only passes
        # optimizations that match an existing static (HARDCODED) finding.
        optimizations = [
            opt for opt in optimizations
            if validate_optimization_against_rtl(code, opt)
        ]
        for o in optimizations:
            if isinstance(o, dict):
                o["source"] = "llm"

        return optimizations, None, result.get("elapsed", 0.0)

    def _merge_and_dedupe(self, static_opts: list, llm_opts: list) -> list:
        """Merge both tiers, dropping LLM findings that duplicate a static
        finding on the same type + location.
        """
        def key(o):
            loc = str(o.get("location", "")).lower()
            first_tok = loc.split()[0] if loc.split() else loc
            return (str(o.get("type", "")).upper(), first_tok)

        seen = {key(o) for o in static_opts}
        merged = list(static_opts)
        for o in llm_opts:
            if key(o) not in seen:
                merged.append(o)
                seen.add(key(o))
        return merged

    def _format_markdown_response(
        self, optimizations: list, total_optimizations: int, quality_score: str
    ) -> str:
        if not optimizations:
            return "NO OPTIMIZATIONS SUGGESTED\n\nTOTAL OPTIMIZATIONS: 0\nQUALITY SCORE: HIGH\n"
        md = []
        for i, opt in enumerate(optimizations, 1):
            md.append(f"OPTIMIZATION #{i} [{opt.get('source', 'unknown')}]")
            md.append(f"Type: {opt.get('type', 'UNKNOWN')}")
            md.append(f"Location: {opt.get('location', 'UNKNOWN')}")
            md.append(f"Issue: {opt.get('issue', '')}")
            md.append(f"Benefit: {opt.get('benefit', '')}")
            md.append(f"Suggestion: {opt.get('suggestion', '')}")
            md.append("")
        md.append(f"TOTAL OPTIMIZATIONS: {total_optimizations}")
        md.append(f"QUALITY SCORE: {quality_score}")
        return "\n".join(md)
