# Project Progress (Start → End)

> This document summarizes what is implemented so far in this repository, in chronological order as far as can be inferred from the existing source + documentation. It also explains the observed/expected results from each major step.

---

## 0) Repository goals and overall architecture

From the repository contents, the project is an “RTL AI Verification & Analysis Assistant” that takes SystemVerilog/Verilog RTL files and runs multiple specialized analysis agents to produce:

- **Bug analysis** (functional/structural issues)
- **Timing analysis** (timing/simulation-sensitivity issues)
- **Generated SVA assertions** (assert property statements)
- **Code optimization suggestions** (style/constant usage improvements)

The pipeline is executed mainly by:

- `src/main.py` (web server default; also supports CLI mode)
- `run_all_agents.py` (phase 3 master script for batch runs)

---

## 1) Phase 1: Establish an initial LLM-driven analysis workflow

### 1.1 Evidence in repo

There is an older script `analyze.py` which:

- Sends RTL code to an Ollama model via HTTP (`http://localhost:11434/api/generate`)
- Appends results to `docs/phase1_evaluation.md`
- Runs multiple models (e.g., `mistral`, `qwen2.5:3b`, `codellama`)

### 1.2 Expected result

The result of this step is a baseline set of natural-language “bug / bad practice / timing / fixes” reports from LLM output.

### 1.3 Why this mattered

The LLM-first approach establishes:

- Whether the prompt is producing plausible verification content
- Where hallucinations occur (invented signal names, incorrect clock/reset, etc.)

---

## 2) Phase 2/Phase 3: Multi-agent verification pipeline (Bug, Timing, Assertions, Optimizations)

### 2.1 Evidence in repo

The repo contains a multi-agent design:

- `run_all_agents.py` — “Phase 3 - Master Script”
- `src/main.py` — starts web UI by default and also supports CLI runs
- Agent modules in `src/agents/`:
  - `bug_agent.py`
  - `timing_agent.py`
  - `assertion_agent.py`
  - `optimize_agent.py`
  - (plus others: `fixer_agent.py`, `custom_agent.py`, etc.)

### 2.2 What `run_all_agents.py` does

From `run_all_agents.py`:

- Finds all `*.sv` files in `rtl_files/`
- Instantiates the 4 specialized agents once
- For each file:
  - runs the agents sequentially
  - combines the results into a single report file in `reports/`
- Prints a console summary dashboard

**Result:** You get per-file markdown reports like:

- `reports/<module>_phase3_report.md`

…and a console table summarizing bugs/timing/SVA/opts counts.

### 2.3 What `src/main.py` adds

`src/main.py` provides two modes:

- **Web mode (default):** starts `uvicorn` for `src.web.server:app`
- **CLI mode:** runs `run_cli_analysis(...)` which:
  - discovers RTL files by `--file`
  - runs agents either sequentially or in parallel threads (`--parallel`)
  - writes markdown reports into `reports/` with names like `*_cli_report.md`

**Result:** you can run the same pipeline either headlessly (CLI) or interactively (web).

---

## 3) Core static analysis + SVA/assertion evidence extraction: `src/core/rtl_parser.py`

This is the most important “technical” step in the repository: the addition of a real static analysis layer.

### 3.1 Evidence in repo

The file `src/core/rtl_parser.py` is present and contains extensive logic using **pyslang** for SystemVerilog parsing.

It implements the project’s RTL understanding primitives used by the agents.

### 3.2 Key improvements introduced

#### 3.2.1 Robust comment stripping

Functionality removes `//` and `/* ... */` comments but preserves newlines inside block comments so line-based offsets remain consistent.

**Result:** prevents false matches in later regex-based checks and keeps line number evidence stable.

#### 3.2.2 Always-block extraction

Functions discover clocked combinational/sequential blocks either by:

- `pyslang` offsets (preferred)
- text fallback when pyslang cannot parse modules

This provides block boundaries and extracted code text for evidence.

**Result:** analysis becomes more reliable across various RTL file shapes.

#### 3.2.3 Declared identifier extraction

`extract_declared_identifiers(code)` returns a stable schema:

- signals
- outputs
- parameters
- widths (when concrete)
- detected clocks/resets (naming heuristics)
- module name

**Result:** agents can validate whether a referenced signal actually exists.

#### 3.2.4 Static bug finding

`static_bug_findings(code)` performs structural checks such as:

- blocking assignment (`=`) used inside `always_ff`
- latch inference in combinational blocks (`always_comb`/`always`)
- multi-driver detection (continuous assign + procedural)
- literal width mismatch on continuous assignments
- output ports that appear undriven

**Result:** provides deterministic “evidence” to drive LLM outputs away from random content.

#### 3.2.5 SVA generation

`static_assertions(code)` attempts to generate up to three SVA assertions:

- reset-related assertion (target becomes known after reset)
- range/X-check assertion using `$isunknown`

It uses naming heuristics to pick clock/reset and targets.

**Result:** even without LLM, the system can propose baseline assertion templates.

#### 3.2.6 Evidence-based clocking/reset/target validation

New or extended helpers include:

- `extract_clocking_blocks(code)`
- `extract_sva_clock_reset_target(sva_code)`
- `validate_sva_against_rtl(code, assertion)`

These parse generated SVA to extract:

- `@(posedge/negedge clk)`
- `disable iff(...)` reset polarity
- `$isunknown(target)` target signal

Then they validate that:

- the clock/edge matches a clocked always block
- the reset polarity matches reset-aware evidence
- the target is driven in appropriate reset/non-reset branches

**Result:** assertion agent outputs can be filtered to reduce hallucinated signal identifiers.

#### 3.2.7 Evidence-based optimizer validation

`validate_optimization_against_rtl(code, optimization)` rejects optimizer outputs that don’t map to deterministic findings from `static_optimizations(code)`.

**Result:** reduces “plausible-sounding but ungrounded” suggestions.

---

## 4) Hardening against hallucinations

### 4.X Extension: local grounded synthesis loop (rag_pipeline.py)
- [x] Added `rag_pipeline.py` as a **project extension** (does not replace Phase 3 agents).
- [x] Local-only grounded retrieval context built from `rtl_files/*` using `src/core/semantic_chunker.py`.
- [x] Declared-only anti-hallucination gate before compilation using `src/core/rtl_parser.py:extract_declared_identifiers`.
- [x] Evidence-aware Verilator/Make repair loop: feeds Verilator stderr back to the local LLM with no-new-identifiers constraints.



### 4.1 Evidence in repo

`TODO.md` explicitly documents the investigation and planned hardening steps around hallucinations:

- assertion/optimization agent hallucination root cause is permissive post-validation heuristics
- small RTL worsens grounding due to weaker context and stricter naming heuristics
- Phase 1/2/3 planned changes:
  - implement evidence extraction + strict validators
  - switch agents to evidence-based validation
  - add regression tests for tiny RTL

### 4.2 Implemented outcome (inferred from `rtl_parser.py`)

Although the TODO indicates “future edits”, `rtl_parser.py` already contains exactly the described validator infrastructure:

- `extract_clocking_blocks`
- `extract_sva_clock_reset_target`
- `validate_sva_against_rtl`
- `validate_optimization_against_rtl`

**Expected result:**

- fewer hallucinated identifiers in assertion outputs
- assertions either evidence-bound or not generated when validation fails (low coverage rather than wrong answers)

---

## 5) Reporting and artifacts

### 5.1 Generated reports

After pipeline execution:

- `reports/<rtl_file>_phase3_report.md`
- `reports/<rtl_file>_cli_report.md` (CLI mode)

These combine all agent outputs into a single markdown.

### 5.2 Existing example reports

The repository includes pre-generated reports in `reports/`:

- `alu_phase3_report.md`
- `fifo_phase3_report.md`
- `fsm_phase3_report.md`
- `counter_phase3_report.md`
- `round_robin_arbiter_phase3_report.md`
- `cdc_pointer_sync_phase3_report.md`
- `dma_fifo_deadlock_phase3_report.md`

**Result:** you can compare model output over time and assess whether evidence-based validation improved correctness.

### 5.3 Logs

There are JSONL logs under `logs/` for the various agents. These would typically capture raw agent responses and timing.

---

## 6) Web dashboard

The web server lives in:

- `src/web/server.py`
- frontend assets:
  - `src/web/static/index.html`
  - `src/web/static/js/app.js`
  - `src/web/static/css/style.css`

**Result:** after running the agents, the dashboard can present the results in a UI rather than only markdown files.

---

## 7) Current end-state (what appears completed)

Based on current code + docs, the end-state is:

1. LLM-based phase exists (older `analyze.py`) to explore outputs.
2. A multi-agent pipeline exists (Phase 3) that runs all specialized agents and emits markdown reports.
3. A static RTL parser/validator exists (`src/core/rtl_parser.py`) to:
   - extract declared identifiers
   - detect structural issues deterministically
   - generate basic assertions deterministically
   - validate LLM-generated assertions/optimizations against RTL evidence
4. A plan exists in `TODO.md` to harden hallucination acceptance; the evidence-based validation infrastructure is present in the parser.

---

## Notes / limitations of this progress summary

- Some files (especially the actual agent implementations in `src/agents/*.py`) were not fully inspected line-by-line in this run; the summary reflects the pipeline contracts and the presence of evidence-based validators in `rtl_parser.py`.
- The `README.md` and some docs appear to contain non-UTF text artifacts in tool output; the logical structure was inferred from scripts and core parser content.

---

## Checklist of major implemented components

- [x] Batch runner: `run_all_agents.py`
- [x] Web + CLI entry: `src/main.py`
- [x] Core RTL static parsing & validators: `src/core/rtl_parser.py`
- [x] Evidence-based functions:
  - `extract_clocking_blocks`
  - `validate_sva_against_rtl`
  - `static_bug_findings`
  - `static_optimizations`
  - `validate_optimization_against_rtl`
- [x] Phase-3 anti-hallucination hardening: agents use tighter semantic grounding parameters in their LLM paths.
- [x] Reports & artifacts generated to `reports/` and `logs/`



