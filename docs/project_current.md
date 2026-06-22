

## Current Project Snapshot

This project is an offline RTL analysis and verification assistant for Verilog/SystemVerilog files. It uses a local Ollama model, specialized Python agents, a CLI pipeline, and a FastAPI web dashboard to inspect RTL, generate evidence-backed findings, create SVA assertions, suggest optimizations, and optionally apply fixes.

The guiding principle is conservative, evidence-backed RTL review. Reports should be useful for any RTL file placed in `rtl_files/`, not tuned to the sample modules already in the repository.

## Work Completed So Far

### Phase 1 - Baseline LLM Analysis

- Added a simple analysis utility in `analyze.py`.
- Documented baseline evaluation in `docs/phase1_evaluation.md`.
- Tested local Ollama-based RTL review behavior on sample SystemVerilog files.
- Identified that a broad single prompt can miss real RTL issues or produce weak explanations.

### Phase 2 - Single-Agent Folder Pipeline

- Added `phase2_agent.py` for a more structured single-agent RTL analysis flow.
- Added `docs/phase2_evaluation.md`.
- Improved report generation for files in `rtl_files/`.
- Confirmed that single-agent analysis still had limitations, especially hallucinated or missed bug claims.

### Phase 3 - Specialized Multi-Agent Framework

- Added specialized agents under `src/agents/`:
  - `bug_agent.py` for functional RTL bugs.
  - `timing_agent.py` for timing-related RTL hazards.
  - `assertion_agent.py` for SystemVerilog Assertion generation.
  - `optimize_agent.py` for concrete optimization suggestions.
  - `fixer_agent.py` for applying targeted RTL fixes.
  - `custom_agent.py` for user-defined RTL questions.
- Added a common `BaseAgent` in `src/core/base_agent.py`.
- Added centralized configuration in `src/core/config.py` and `config/settings.json`.
- Added runtime JSONL logs under `logs/`.
- Added `run_all_agents.py` as a batch Phase 3 runner.
- Added CLI and web orchestration in `src/main.py`.
- Added Phase 3 evaluation and steering docs:
  - `docs/phase3_evaluation.md`
  - `docs/phase3_agent_steering.md`

### Static Evidence Layer

- Added `src/core/rtl_static.py` to extract RTL structure and produce deterministic checks.
- Static analysis currently tracks:
  - module names
  - declared ports and signals
  - parameters/localparams
  - widths
  - arrays/memories
  - enum values and typedef aliases
  - clock/reset candidates
  - always blocks
  - procedural assignments
  - continuous assignments
- Bug and timing agents now prefer deterministic static findings over unsupported LLM-only findings.
- The LLM call is retained for compatibility and logging, but final bug/timing reports should not surface unsupported claims.

### Web Dashboard

- Added FastAPI backend in `src/web/server.py`.
- Added static frontend files under `src/web/static/`.
- Implemented API endpoints for:
  - listing Ollama models
  - listing RTL files
  - reading, saving, creating, and deleting RTL files
  - running sequential or parallel multi-agent analysis
  - applying fixer-agent output
  - asking custom RTL questions
- Reports are written to `reports/`.

## Current Architecture

```text
User
  |
  +-- CLI: src/main.py --cli
  |
  +-- Web UI: src/main.py --web
          |
          v
FastAPI backend: src/web/server.py
          |
          v
Specialized agents: src/agents/
          |
          +-- Static checks: src/core/rtl_static.py
          |
          +-- Ollama calls: src/core/base_agent.py
          |
          v
Reports and logs: reports/, logs/
```

## Current Agent Steering

### Bug Agent

The Bug Agent should report only deterministic, evidence-backed functional RTL bugs.

Accepted bug categories:

- blocking assignment in clocked/sequential logic
- latch inference from incomplete combinational assignment
- missing reset assignment where reset-aware sequential logic proves the issue
- multiple drivers on the same signal
- simple literal width mismatch where the width can be proven

The final report should say `NO EVIDENCE-BACKED BUGS DETECTED` when no static finding is available.

### Timing Agent

The Timing Agent should report only timing-related RTL issues that are visible in the code.

Accepted timing categories:

- blocking assignment in clocked logic
- latch inference in combinational logic
- incomplete manual sensitivity lists
- only highly concrete combinational-path or CDC findings when the RTL evidence is clear

The final report should say `NO EVIDENCE-BACKED TIMING ISSUES DETECTED` when no static finding is available.

### Assertion Agent

The Assertion Agent should generate safe, simple SVA using only declared clocks, resets, ports, and signals.

Do not invent:

- protocol signals
- external handshakes
- unavailable clock/reset names
- expected values not implied by the RTL

Returning no assertions is acceptable when the module does not provide enough design intent.

### Optimizer Agent

The Optimizer Agent should give concrete, low-risk suggestions tied to exact RTL evidence.

Prefer:

- parameterization suggestions
- duplicated logic reduction
- clear constant/width cleanup
- maintainability improvements that do not change behavior

Avoid broad or speculative PPA claims.

### Fixer Agent

The Fixer Agent should apply targeted RTL edits based on already reported findings.

Fixes should:

- preserve module interfaces unless the user explicitly asks for interface changes
- keep edits minimal
- avoid changing unrelated formatting or behavior
- return synthesizable SystemVerilog/Verilog

## Report Rules

Every reported issue should include:

- issue type
- signal/block/location
- concrete RTL evidence or line/block reference
- impact/risk
- actionable fix

Reports must avoid:

- undeclared signal names
- assumed protocols
- module-name-based guesses
- setup/hold claims without constraints
- CDC claims based only on multiple clocks
- overflow/underflow claims unless arithmetic and bounds are visible

## Current Runtime Configuration

Current local settings are stored in `config/settings.json`:

```json
{
  "ollama_url": "http://localhost:11434",
  "default_model": "qwen2.5-coder:7b",
  "timeout": 600,
  "temperature": 0.1
}
```

## How To Continue Development

When adding future features:

- Keep the analyzer general-purpose.
- Use `rtl_files/` samples as regression tests, not hardcoded targets.
- Extend `src/core/rtl_static.py` before trusting LLM-only findings.
- Add or update docs when behavior changes.
- Keep CLI and web results consistent.
- Preserve offline operation through local Ollama.

Recommended next improvements:

- Improve expression width evaluation for parameterized widths.
- Add stronger branch-coverage analysis for combinational logic.
- Detect undriven outputs.
- Improve CDC detection using source/destination clock-domain evidence.
- Add optional open-source parser/linter integration.
- Add regression tests for clean RTL, known-bug RTL, enums, memories, parameterized modules, and manual sensitivity lists.

## Success Criteria

The project is successful when:

- clean RTL files remain clean
- real structural issues are detected consistently
- reports contain no invented signals
- every issue has concrete RTL evidence
- the system still works when Ollama is slow, unavailable, or returns invalid JSON
- users can run analysis from both CLI and web dashboard
- generated fixes are narrow, readable, and synthesizable
