import os
import json
from datetime import datetime
from pathlib import Path

from src.core.base_agent import BaseAgent
from src.core.rtl_parser import (
    extract_declared_identifiers,
    is_concrete_finding,
    references_only_declared,
    static_bug_findings,
)

# Small RTL files are passed to the LLM in full so that it can reason
# about relationships between all declarations and procedural blocks.
SMALL_FILE_CHAR_THRESHOLD = 6000


BUG_ANALYSIS_PROMPT = """You are a senior RTL verification engineer specializing in
SystemVerilog bug analysis and semantic RTL reasoning.

Analyze the provided SystemVerilog module for BUGS and meaningful RTL design
problems that can be proven from the provided code.

The deterministic static analyzer has already checked common structural
patterns. Your job is NOT to blindly repeat those checks. Your main purpose is
to reason about the RTL as a complete design and identify issues that require
understanding relationships between signals, sequential/combinational blocks,
state transitions, conditions, and data flow.

CRITICAL RULES:

1. IDENTIFY DECLARED IDENTIFIERS:
   First inspect the RTL and identify all ports, signals, registers, and
   parameters. You MUST only reference identifiers that are explicitly
   declared in the provided module.

2. DO NOT HALLUCINATE:
   Never invent signals, registers, parameters, interfaces, clocks, resets,
   modules, or external logic that are not present in the provided RTL.

3. DO NOT SPECULATE:
   Only report an issue when the provided RTL gives sufficient evidence that
   the behavior can actually occur.

4. WHOLE-MODULE REASONING:
   Reason about relationships between different always blocks, assignments,
   state variables, control signals, counters, valid/ready signals, enables,
   resets, and data paths.

5. STATIC FINDINGS ARE EVIDENCE, NOT TRUTH:
   The deterministic static analyzer findings provided later in this prompt
   are additional evidence.
   
   You MUST verify each static finding against the actual RTL.
   
   Do not blindly copy static findings.
   
   You may:
   - confirm a valid static finding,
   - improve its explanation,
   - provide a more precise fix,
   - determine that a static finding is not supported by the RTL,
   - identify an additional issue that the static analyzer missed.

6. LLM-SPECIFIC REASONING:
   Look for meaningful problems that require semantic reasoning rather than
   merely pattern matching.

   In particular examine:

   A. STATE AND CONTROL FLOW
      - Incorrect state transitions
      - Conditions that make a state unreachable
      - Missing state transitions
      - Incorrect use of previous-state versus next-state values
      - State variables updated under inconsistent conditions

   B. DATA AND CONTROL ALIGNMENT
      - Data and control signals becoming misaligned
      - Valid/control signals being delayed differently from associated data
      - Enables affecting related signals inconsistently
      - One signal being updated while a dependent signal is held

   C. COUNTERS AND BOUNDARIES
      - Off-by-one conditions
      - Incorrect terminal-count behavior
      - Counter comparisons inconsistent with counter width
      - Counters continuing when they should stop
      - Counter/state interactions producing incorrect behavior

   D. RESET AND INITIALIZATION SEMANTICS
      - Reset behavior inconsistent with how state is subsequently used
      - Some related state being reset while dependent state is not
      - Reset causing an invalid transition or stale-data condition
      - Incorrect interaction between reset and enable/state logic

   E. SEQUENTIAL / COMBINATIONAL INTERACTION
      - Incorrect assumptions about old versus newly assigned values
      - Signals consumed before they are updated as intended
      - Multiple procedural blocks creating unintended behavior
      - Combinational logic depending on incompletely controlled state

   F. FUNCTIONAL DATAFLOW
      - A signal being calculated correctly in isolation but used incorrectly
      - A condition that prevents required data from propagating
      - A result being overwritten unexpectedly
      - A dependency between signals that is violated by the control flow

   G. PARAMETER AND WIDTH SEMANTICS
      - Parameter values causing invalid ranges
      - Expressions whose width/sign behavior changes the intended result
      - Parameterization that works only for one particular value

   H. VALID/READY OR HANDSHAKE LOGIC
      If such signals actually exist in the module:
      - Incorrect handshake conditions
      - Data changing while valid is held
      - Ready/valid dependency causing a transaction to be lost
      - Incorrect acceptance or completion conditions

7. DO NOT REPORT STYLE ISSUES AS BUGS:
   Do not report formatting, naming preferences, readability preferences,
   synthesis optimization suggestions, or general coding-style opinions as
   functional bugs.

8. NO TIMING SPECULATION:
   Do not claim a timing violation unless the RTL itself provides enough
   information to establish the issue. Do not invent clock frequency,
   technology, delays, or physical implementation details.

9. FIXES MUST MATCH THE PROVIDED RTL:
   Every proposed fix must refer only to identifiers and structures that
   actually exist in the RTL.

10. NO BUGS:
   If no concrete bug can be established, return an empty bugs array and
   severity LOW.

STATIC ANALYSIS FINDINGS:

The deterministic analyzer will provide findings after the RTL.

Treat them as evidence that must be verified against the RTL.

Your analysis should produce useful LLM reasoning even when static findings
already exist. Do not simply reproduce the same finding. If the same issue is
confirmed, improve the explanation, impact, or fix where appropriate.

RTL CODE TO ANALYZE (File: {filename}):

```systemverilog
{code}

You MUST respond with VALID JSON only.

JSON SCHEMA:

{{
"declared_ports_and_signals": [
"list of all exact port and signal names declared in the RTL module"
],
"declared_parameters": [
"list of all parameter names declared in the RTL module"
],
"bugs": [
{{
"type": "LATCH" | "RESET" | "FUNCTIONAL" | "WIDTH",
"location": "exact signal/register/port name and line number where the issue occurs",
"problem": "Clear explanation of what is wrong. Maximum 2 sentences.",
"impact": "RTL consequence in simulation or silicon. Maximum 1 sentence.",
"fix": "Exact code change required to resolve the issue."
}}
],
"total_bugs": 0,
"severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
}}

If no bugs are found:

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
    Specialized RTL bug-analysis agent.

    Two analysis tiers are executed:

    Tier 1:
        Deterministic static analysis from rtl_parser.py.

    Tier 2:
        Local Ollama LLM analysis using whole-module/contextual reasoning.

    The LLM receives the static findings as evidence but performs its own
    analysis of the RTL.

    Final output:
        static findings + unique LLM findings
    """

def __init__(self, model: str = None):
    super().__init__(
        agent_name="bug_agent",
        model=model
    )

def analyze(self, filepath: str) -> dict:
    path = Path(filepath)

    if not path.exists():
        return {
            "success": False,
            "error": f"File not found: {filepath}"
        }

    code = path.read_text(
        encoding="utf-8",
        errors="replace"
    )

    print(f"Bug agent analyzing: {path.name}")

    # ============================================================
    # TIER 1: DETERMINISTIC STATIC ANALYSIS
    # ============================================================

    static_bugs = static_bug_findings(code)

    for bug in static_bugs:
        bug["source"] = "static"

    # ============================================================
    # TIER 2: LLM ANALYSIS
    #
    # IMPORTANT:
    # Static findings are passed into the LLM.
    # The LLM does NOT simply replace static analysis.
    # ============================================================

    llm_bugs, llm_error, llm_elapsed = self._run_llm_analysis(
        code,
        path,
        static_bugs
    )

    # If LLM fails but static analysis produced findings,
    # return the deterministic findings rather than failing
    # the complete analysis.
    if llm_error and not static_bugs:
        return {
            "success": False,
            "error": llm_error
        }

    # ============================================================
    # MERGE STATIC + LLM FINDINGS
    # ============================================================

    merged_bugs = self._merge_and_dedupe(
        static_bugs,
        llm_bugs
    )

    total_bugs = len(merged_bugs)

    severity = self._compute_severity(
        merged_bugs
    )

    raw_response = self._format_markdown_response(
        merged_bugs,
        total_bugs,
        severity
    )

    # ============================================================
    # LOGGING
    # ============================================================

    self.log_run(
        path.name,
        {
            "bugs_found": total_bugs,
            "severity": severity,
            "static_count": len(static_bugs),
            "llm_count": len(llm_bugs),
            "response_length": len(raw_response),
            "source": "static_plus_llm",
            "llm_error": llm_error,
        }
    )

    # ============================================================
    # FINAL RESULT
    # ============================================================

    return {
        "success": True,
        "filename": path.name,
        "filepath": str(path),
        "timestamp": datetime.now().isoformat(),
        "model": self.model,

        "bugs": merged_bugs,

        "total_bugs": total_bugs,
        "severity": severity,

        "raw_response": raw_response,

        "elapsed_s": llm_elapsed,

        # Useful for debugging/testing the architecture.
        "static_count": len(static_bugs),
        "llm_count": len(llm_bugs),
        "llm_error": llm_error,
    }

def _run_llm_analysis(
    self,
    code: str,
    path: Path,
    static_bugs: list
):
    """
    Run the LLM analysis.

    Returns:
        (bugs, error, elapsed)
    """

    # ============================================================
    # PREPARE RTL CONTEXT
    # ============================================================

    if len(code) <= SMALL_FILE_CHAR_THRESHOLD:

        # For small modules, ALWAYS give the complete module.
        # This is important for semantic reasoning because the LLM
        # needs to see all declarations and all procedural blocks.
        code_ctx = code

    else:

        # For large RTL files, use the existing semantic chunker.
        from src.core.semantic_chunker import (
            chunk_sv,
            select_relevant_chunks,
            chunks_to_prompt_text,
        )

        chunks = chunk_sv(code)

        selected = select_relevant_chunks(
            chunks,
            query=BUG_ANALYSIS_PROMPT,
            top_k=12,
            max_total_chars=9000,
        )

        if selected:
            code_ctx = chunks_to_prompt_text(
                selected
            )
        else:
            code_ctx = code

    # ============================================================
    # PREPARE STATIC FINDINGS
    # ============================================================

    static_findings_text = json.dumps(
        static_bugs,
        indent=2,
        ensure_ascii=False
    )

    # ============================================================
    # BUILD ORIGINAL PROMPT
    # ============================================================

    prompt = BUG_ANALYSIS_PROMPT.format(
        filename=path.name,
        code=code_ctx
    )

    # ============================================================
    # ADD STATIC ANALYSIS AS EVIDENCE
    # ============================================================

    prompt += f"""
============================================================
DETERMINISTIC STATIC ANALYSIS RESULTS

The deterministic RTL analyzer produced the following findings:

{static_findings_text}

These findings are NOT automatically correct.

Verify each finding against the RTL before using it.

For each static finding, determine whether:

It is genuinely supported by the RTL.
Its explanation can be improved.
Its proposed fix can be made more precise.
It appears to be a false positive.

You should also independently reason about the RTL and identify
additional semantic or cross-block bugs that the deterministic
analyzer may not detect.

IMPORTANT:

Do not simply repeat the static findings.

The purpose of the LLM layer is to provide additional reasoning
and identify issues that require understanding the behavior of
the complete RTL module.

Return ONLY the final JSON object using the schema specified
above.
"""

    # ============================================================
    # CALL OLLAMA
    # ============================================================

    result = self.call_ollama(
        prompt,
        json_mode=True,
        max_tokens=1200
    )

    if not result["success"]:
        return (
            [],
            result["error"],
            0.0
        )

    # ============================================================
    # PARSE RESPONSE
    # ============================================================

    parsed_json = self.parse_json_response(
        result["response"]
    )

    parse_error = self.json_parse_error(
        parsed_json
    )

    if parse_error:
        return (
            [],
            parse_error,
            result.get("elapsed", 0.0)
        )

    # ============================================================
    # EXTRACT BUGS
    # ============================================================

    if isinstance(parsed_json, list):

        bugs = parsed_json

    elif isinstance(parsed_json, dict):

        bugs = parsed_json.get(
            "bugs",
            []
        )

    else:

        bugs = []

    if not isinstance(bugs, list):
        bugs = []

    # ============================================================
    # VALIDATE LLM FINDINGS
    # ============================================================

    identifiers = extract_declared_identifiers(
        code
    )

    declared = (
        set(identifiers.get("signals", []))
        |
        set(identifiers.get("parameters", []))
    )

    validated_bugs = []

    for bug in bugs:

        if not isinstance(bug, dict):
            continue

        if not references_only_declared(
            bug,
            declared
        ):
            continue

        if not is_concrete_finding(
            bug,
            declared
        ):
            continue

        bug["source"] = "llm"

        validated_bugs.append(
            bug
        )

    return (
        validated_bugs,
        None,
        result.get("elapsed", 0.0)
    )

def _merge_and_dedupe(
    self,
    static_bugs: list,
    llm_bugs: list
) -> list:
    """
    Merge deterministic static findings with LLM findings.

    Static findings are retained as the deterministic baseline.

    LLM findings are added when they represent a distinct issue.

    If both tiers identify the same issue, only one finding is kept.
    The static finding takes priority because the static analyzer
    provides deterministic structural evidence.
    """

    def normalize_location(location):

        location = str(
            location
        ).strip().lower()

        # Normalize common separators.
        location = (
            location
            .replace(":", " ")
            .replace(",", " ")
            .replace("(", " ")
            .replace(")", " ")
        )

        parts = location.split()

        cleaned = []

        for part in parts:

            # Ignore standalone numbers.
            if part.isdigit():
                continue

            # Ignore common line-number tokens.
            if part.startswith("line"):
                continue

            cleaned.append(part)

        return " ".join(cleaned)

    def key(bug):

        bug_type = str(
            bug.get("type", "")
        ).strip().upper()

        location = normalize_location(
            bug.get("location", "")
        )

        return (
            bug_type,
            location
        )

    merged = []
    seen = set()

    # ============================================================
    # STATIC FINDINGS FIRST
    # ============================================================

    for bug in static_bugs:

        k = key(bug)

        if k not in seen:

            merged.append(bug)
            seen.add(k)

    # ============================================================
    # ADD UNIQUE LLM FINDINGS
    # ============================================================

    for bug in llm_bugs:

        k = key(bug)

        if k not in seen:

            merged.append(bug)
            seen.add(k)

    return merged

def _compute_severity(
    self,
    bugs: list
) -> str:

    if not bugs:
        return "LOW"

    if any(
        bug.get("type") in {
            "FUNCTIONAL",
            "WIDTH"
        }
        for bug in bugs
    ):
        return "HIGH"

    return "MEDIUM"

def _format_markdown_response(
    self,
    bugs: list,
    total_bugs: int,
    severity: str
) -> str:

    if not bugs:

        return (
            "NO BUGS DETECTED\n\n"
            "TOTAL BUGS: 0\n"
            "SEVERITY: LOW\n"
        )

    md = []

    for i, bug in enumerate(
        bugs,
        1
    ):

        md.append(
            f"BUG #{i} [{bug.get('source', 'unknown')}]"
        )

        md.append(
            f"Type: {bug.get('type', 'UNKNOWN')}"
        )

        md.append(
            f"Location: {bug.get('location', 'UNKNOWN')}"
        )

        md.append(
            f"Problem: {bug.get('problem', '')}"
        )

        md.append(
            f"Impact: {bug.get('impact', '')}"
        )

        md.append(
            f"Fix: {bug.get('fix', '')}"
        )

        md.append("")

    md.append(
        f"TOTAL BUGS: {total_bugs}"
    )

    md.append(
        f"SEVERITY: {severity}"
    )

    return "\n".join(md)