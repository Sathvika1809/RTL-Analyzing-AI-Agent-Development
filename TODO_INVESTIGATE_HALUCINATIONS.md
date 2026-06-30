# Investigation plan: why the LLM hallucinates on small RTL files

## Goal
Identify the concrete code paths that allow hallucinated signals/line numbers in agent outputs, especially for small RTL modules, then harden the pipeline to scale to 1000s lines industry-style RTL.

## Observed system behavior (from code review so far)
- `src/agents/bug_agent.py`
  - Uses deterministic tier: `static_bug_findings(code)` from `src/core/rtl_parser.py`
  - LLM tier output is filtered:
    - `references_only_declared(bug, declared)`
    - `is_concrete_finding(bug, declared)`
- `src/agents/assertion_agent.py`
  - Uses deterministic tier: `static_assertions(code)` from `rtl_parser.py`
  - If no clocks are found (`meta["clocks"]` empty), it calls `_generate_immediate_assertions(code, path.name)`
    - This function is suspected missing/not implemented in the file excerpt you provided.
  - The LLM tier path likely does not filter LLM-produced signals against declared identifiers (unlike bug agent).

## What “chip agents vs Siemens/industry” means in this project
- “chip agents” = internal deterministic parsing + targeted checks + strict name binding (no invented identifiers).
- “Siemens/industry-level” = scalable static analysis and robust partial parsing:
  - handle includes/macros gracefully,
  - avoid context loss,
  - chunk large modules,
  - keep line/region mappings,
  - validate generated assertions/code before reporting.

## Key hypotheses (most likely hallucination root causes)
1) Assertion agent LLM outputs are not filtered to declared symbols
2) Small RTL modules cause clock/reset extraction to fail
3) `_generate_immediate_assertions()` may be missing or incomplete
4) Output validation is only “syntax via Verilator” (not “semantic name binding”)

## Investigation steps
### Step A — Locate and verify every hallucination-enabling path
- `src/agents/assertion_agent.py`
  - Search for `_generate_immediate_assertions` definition and how it builds SVA.
  - Confirm whether any filtering like `references_only_declared()` is used.
- `src/agents/timing_agent.py`, `custom_agent.py`, `fixer_agent.py`, `optimize_agent.py`
  - Look for the same LLM-output filtering pattern or absence of it.

### Step B — Verify parser correctness on small RTL
- `src/core/rtl_parser.py`
  - Inspect:
    - `extract_declared_identifiers()`: does it actually return `clocks/resets/signals` for tiny modules?
    - `_find_clocks/_find_resets`: regex heuristics may be too naming-convention dependent.

### Step C — Validate “name binding” and scaling strategy
- Add semantic validation on LLM-generated SVA:
  - enforce that every token used as a signal in `sva_code` is present in declared signals/clocks/resets
  - reject or downgrade any assertion that violates strict binding
- For 1000s-line modules:
  - chunk analysis by always-block and generate assertions per-block region
  - never send whole file if not needed
  - keep deterministic tier first; only generate LLM assertions when static tier has high confidence.

## Files likely to require edits (depending on findings)
- `src/agents/assertion_agent.py`
- `src/core/rtl_parser.py` (only if clock/reset extraction is failing on small RTL)
- Potentially `src/agents/*_agent.py` other than bug/assertion if they also rely on unfiltered LLM outputs

## Follow-up (after root causes confirmed)
- Implement declared-name filtering for assertion agent LLM output using:
  - `references_only_declared()` (from `rtl_parser.py`)
  - plus additional checks specific to SVA (signal token extraction)
- Add regression tests:
  - tiny RTL module test (10–50 lines)
  - medium module test
  - ensure outputs contain zero hallucinated identifiers

## Done criteria
- On tiny RTL, agents return either:
  - correct assertions with only declared signal names, or
  - zero assertions (coverage LOW) without inventing signals.

