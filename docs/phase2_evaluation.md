# Phase 2 - Core RTL Analysis Pipeline Evaluation Report
## Author: H.Sathvika
## Date: June 15, 2026
## RTL ANALYSING AI AGENT DEVELOPMENT

# 1. Objective
Evaluate the automated Phase 2 single-agent RTL analysis pipeline. The pipeline scans a directory of SystemVerilog/Verilog files, queries a locally deployed `qwen2.5:3b` model using a highly constrained single prompt (incorporating strict design verification guidelines), and outputs structured markdown reports.

---

# 2. Environment & System Setup
- **OS**: Windows 11
- **CPU**: Intel Core Ultra 5 125U (12 Cores)
- **RAM**: 16 GB
- **LLM Engine**: Ollama v0.24.0
- **Model**: `qwen2.5:3b` (locally served)
- **Python Pipeline**: `phase2_agent.py`
  - Automated file globbing (`rtl_files/*.sv`)
  - Configured structured prompting with strict rules to prevent general text hallucinations
  - Saved outputs to `reports/*_phase2_report.md`
  - Execution: Sequential file analysis

---

# 3. Prompt Engineering Strategy
Phase 2 introduced a structured prompt system with explicit verification guidelines to prevent the massive hallucination rates seen in Phase 1. The key rules injected into the prompt were:
1. Report issues **ONLY** if directly observed in the code.
2. Do **NOT** suggest generic HDL best practices.
3. Do **NOT** recommend timing/clock constraints unless directly related to a bug.
4. Do **NOT** speculate about missing functionality.
5. If a signal/register is used, do **NOT** claim it is unused.
6. Enforce strict output format (`## BUGS`, `## BAD PRACTICES`, `## TIMING`, `## FIXES`).

---

# 4. Phase 2 Evaluation Results

The pipeline was executed on 7 deliberately buggy SystemVerilog files in `rtl_files/`. Below is the summary of the findings, elapsed times, and verification accuracy:

| File Name | Model Used | Analysis Time (s) | Bugs Detected | Missed Real Bugs | False Positives / Hallucinations |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **`alu.sv`** | `qwen2.5:3b` | 61.01 | None | 1. Incomplete `case` statement causing latch on `result`. <br>2. Undriven output port `overflow`. <br>3. Bit-width mismatch on `zero_flag` (`result == 9'b0` vs 8-bit parameter). | None |
| **`cdc_pointer_sync.sv`** | `qwen2.5:3b` | 56.93 | Suggested converting combinational `assign rd_ptr_bin = sync_reg_1;` to clocked `always_ff`. | None (synchronizer chain itself was correct). | Flawed recommendation; converting this to a clocked block changes the output timing and violates design intent. |
| **`counter.sv`** | `qwen2.5:3b` | 113.97 | None | 1. Blocking assignments (`=`) inside sequential `always_ff`. <br>2. Latch on `carry_out` (missing `else` in `always_comb`). <br>3. Hardcoded reset width mismatch (`8'b0` instead of parameter `WIDTH`). | None |
| **`dma_fifo_deadlock.sv`** | `qwen2.5:3b` | 24.18 | Flagged constant credit assignment `assign max_credits = DEPTH;` | Missed actual handshake and credit-count logic flaws. | Proposed fixing this with `assign max_credits = {DEPTH{1'b1}};`, which is syntactically invalid and logically wrong (results in all ones of length DEPTH). |
| **`fifo.sv`** | `qwen2.5:3b` | 12.02 | Claimed `wr_ptr` doesn't wrap around and will overflow. | 1. Latch on `full` (missing assignment when pointer difference is not 1). <br>2. Flawed `full` and `empty` detection logic. | Modulo operator suggestion (`wr_ptr <= (wr_ptr + 1) % DEPTH;`) is unnecessary (4-bit pointers wrap naturally at 16) and is generally bad practice/non-synthesizable for non-power-of-2 depths. |
| **`fsm.sv`** | `qwen2.5:3b` | 51.47 | None | 1. Latch on next state output. <br>2. Missing default transition branches. | None |
| **`round_robin_arbiter.sv`** | `qwen2.5:3b` | 240.87 | 1. Flagged mask reset assignment. <br>2. Flagged `for` loop in `always_comb`. | Missed priority encoder and grant feedback issues. | 1. Suggested resetting the `mask` to all zeros (`{NUM_REQS{1'b0}}`) which disables the arbiter. <br>2. Claimed a `for` loop inside `always_comb` causes race conditions (a basic misunderstanding of Verilog unrolled logic). |

---

# 5. Critical Observations
1. **The Strictness Trade-off (False Negatives)**:
   By restricting the model to *only* report issues it was 100% sure of, it became extremely conservative. It failed to report **critical RTL bugs** (such as blocking assignments in sequential blocks in `counter.sv` and latches in `alu.sv`) that are obvious to a human engineer.
2. **Synthesizability & Logic Hallucinations**:
   When the model attempted to propose fixes, it suggested non-synthesizable constructs (like modulo `%` operators in `fifo.sv`) or mathematically incorrect expressions (like `{DEPTH{1'b1}}` in `dma_fifo_deadlock.sv`). This indicates that a base model lacks a deep, structured understanding of synthesizable hardware design principles.
3. **Misunderstanding of Verilog Semantics**:
   The model hallucinated that `for` loops in combinational blocks cause simultaneous race conditions, showing a lack of understanding of Verilog's sequential-in-combinational unrolled behavior.
4. **Execution Overhead**:
   Sequential analysis of all 7 files took **410.60 seconds** (~6.8 minutes) due to serial LLM execution on CPU/GPU.

---

# 6. Conclusion
The Phase 2 single-agent pipeline succeeded in enforcing **report structure** and eliminating **general document hallucinations**, but it failed at **verification accuracy**. It missed the most severe hardware bugs and suggested functionally dangerous modifications.

This baseline proved that **a single LLM agent, regardless of prompt constraints, cannot simultaneously check for functional bugs, timing errors, optimization potentials, and write SystemVerilog Assertions**. This directly motivated **Phase 3 (Agent Specialization)**, where the workload is split across multiple specialized agents operating under targeted roles.
