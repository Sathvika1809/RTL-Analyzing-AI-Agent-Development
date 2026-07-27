# TODO_INVESTIGATE_HALUCINATIONS (implementation)

## Goal
Identify concrete code paths allowing hallucinated signals/line numbers in agent outputs (small RTL), then harden pipeline to scale.

## Findings (current)
- AssertionAgent: no-clock fallback returns empty assertions; hallucinations come from LLM path.
- Post-generation filtering is heuristic:
  - `references_only_declared()` token/name-based allowlist checking.
  - `is_concrete_finding()` word-pattern-based “sounds concrete” detection.
- Small RTL makes grounding weaker (clock/reset heuristics + less chunk context).

## Implementation tasks
See top-level `TODO.md`.

