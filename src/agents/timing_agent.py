
import os
import re
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent
from src.core.rtl_parser import (
    extract_declared_identifiers,
    is_concrete_finding,
    references_only_declared,
    static_timing_findings,
)

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
* Signals transferred between different clock domains without an obvious synchronizer structure.

D. LATCH
* Incomplete assignments in combinational logic causing latch inference.

E. COMBO_PATH
* Report ONLY when a clearly excessive combinational chain is visible in RTL.
* Do NOT report simple comparators, muxes, arithmetic, FIFO full/empty logic, or ordinary combinational logic.
* If uncertain, do NOT report.

RTL Code to analyze (File: {filename}):
```systemverilog
{code}
Return ONLY valid JSON.

JSON Schema:
{{
"declared_clocks_and_resets": ["exact names of all clock and reset signals declared in the module"],
"declared_signals": ["exact names of all internal and port signals declared in the module"],
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
#Files at or below this size get the FULL module passed to the LLM with no
#chunking, so it retains cross-block context (e.g. clock-domain signals
#used in one always block but declared/driven near another).

SMALL_FILE_CHAR_THRESHOLD = 6000

class TimingAgent(BaseAgent):

    """
    Specialized agent for identifying timing hazards, CDC, and blocking assignments.
    Both tiers ALWAYS run and their findings are merged:
    Tier 1: rtl_parser static analysis (pyslang-backed) - deterministic,
            catches BLOCKING/LATCH/SENSITIVITY issues.
    Tier 2: Ollama LLM - the only tier that can reasonably flag CDC issues
            (cross-domain signal reasoning) and COMBO_PATH.
    """ 

def __init__(self, model: str = None):
    super().__init__(agent_name="timing_agent", model=model)

def analyze(self, filepath: str) -> dict:
    path = Path(filepath)
    if not path.exists():
        return {"success": False, "error": f"File not found: {filepath}"}

    code = path.read_text(encoding="utf-8", errors="replace")
    print(f"  Timing agent analyzing: {path.name}")

    # ---- Tier 1: static analysis (always runs) ----
    static_issues = static_timing_findings(code)
    for i in static_issues:
        i["source"] = "static"

    # ---- Tier 2: LLM analysis (always runs) ----
    llm_issues, llm_error, llm_elapsed = self._run_llm_analysis(code, path)

    if llm_error and not static_issues:
        return {"success": False, "error": llm_error}

    # ---- Merge + dedupe ----
    merged_issues = self._merge_and_dedupe(static_issues, llm_issues)
    total_issues = len(merged_issues)
    risk = self._compute_risk(merged_issues)
    raw_response = self._format_markdown_response(merged_issues, total_issues, risk)

    self.log_run(path.name, {
        "issues_found": total_issues,
        "severity": risk,
        "static_count": len(static_issues),
        "llm_count": len(llm_issues),
        "response_length": len(raw_response),
        "source": "merged",
    })

    return {
        "success": True,
        "filename": path.name,
        "filepath": str(path),
        "timestamp": datetime.now().isoformat(),
        "model": self.model,
        "timing_issues": merged_issues,
        "total_issues": total_issues,
        "risk": risk,
        "raw_response": raw_response,
        "elapsed_s": llm_elapsed,
    }

def _run_llm_analysis(self, code: str, path: Path):
    """Runs the LLM tier and returns (issues, error, elapsed).

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
            query=TIMING_ANALYSIS_PROMPT,
            top_k=12,
            max_total_chars=9000,
        )
        code_ctx = chunks_to_prompt_text(selected) if selected else code

    prompt = TIMING_ANALYSIS_PROMPT.format(filename=path.name, code=code_ctx)
    result = self.call_ollama(prompt, json_mode=True, max_tokens=800)

    if not result["success"]:
        return [], result["error"], 0.0

    parsed_json = self.parse_json_response(result["response"])
    parse_error = self.json_parse_error(parsed_json)
    if parse_error:
        return [], parse_error, result.get("elapsed", 0.0)

    if isinstance(parsed_json, list):
        issues = parsed_json
    else:
        issues = parsed_json.get("timing_issues", []) if isinstance(parsed_json, dict) else []

    identifiers = extract_declared_identifiers(code)
    declared = (
        set(identifiers.get("signals", []))
        | set(identifiers.get("parameters", []))
    )
    total_lines = len(code.splitlines())

    validated_issues = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if not references_only_declared(issue, declared):
            continue
        if not is_concrete_finding(issue, declared):
            continue
        if not self._verify_line_evidence(issue.get("location", ""), total_lines):
            continue
        issue["source"] = "llm"
        validated_issues.append(issue)

    return validated_issues, None, result.get("elapsed", 0.0)

def _verify_line_evidence(self, location_str: str, total_lines: int) -> bool:
    """
    Validates that any line number cited in the 'location' field
    is within the boundary range of the module source code.
    """
    match = re.search(r"\bline\s*(\d+)\b|\b(\d+)\b", str(location_str), re.IGNORECASE)
    if match:
        line_num = int(match.group(1) or match.group(2))
        if line_num > total_lines + 10:
            return False
    return True

def _merge_and_dedupe(self, static_issues: list, llm_issues: list) -> list:
    """Merge both tiers, dropping LLM findings that duplicate a static
    finding on the same type + location (static wins on conflicts).
    """
    def key(i):
        loc = str(i.get("location", "")).lower()
        first_tok = loc.split()[0] if loc.split() else loc
        return (str(i.get("type", "")).upper(), first_tok)

    seen = {key(i) for i in static_issues}
    merged = list(static_issues)
    for i in llm_issues:
        if key(i) not in seen:
            merged.append(i)
            seen.add(key(i))
    return merged

def _compute_risk(self, issues: list) -> str:
    if not issues:
        return "LOW"
    if any(i.get("type") in {"CDC", "BLOCKING"} for i in issues):
        return "HIGH"
    return "MEDIUM"

def _format_markdown_response(self, issues: list, total_issues: int, risk: str) -> str:
    if not issues:
        return "NO TIMING ISSUES DETECTED\n\nTOTAL TIMING ISSUES: 0\nRISK LEVEL: LOW\n"
    md = []
    for i, issue in enumerate(issues, 1):
        md.append(f"TIMING ISSUE #{i} [{issue.get('source', 'unknown')}]")
        md.append(f"Type: {issue.get('type', 'UNKNOWN')}")
        md.append(f"Location: {issue.get('location', 'UNKNOWN')}")
        md.append(f"Problem: {issue.get('problem', '')}")
        md.append(f"Risk: {issue.get('risk', '')}")
        md.append(f"Fix: {issue.get('fix', '')}")
        md.append("")
    md.append(f"TOTAL TIMING ISSUES: {total_issues}")
    md.append(f"RISK LEVEL: {risk}")
    return "\n".join(md)