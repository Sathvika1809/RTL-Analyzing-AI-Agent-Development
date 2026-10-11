# Phase 3 RTL Analysis Report: fsm.sv

**Generated:** 2026-08-08 20:52:28

---

## Bug Analysis

**Total bugs found:** 4
**Source breakdown:** 4 static / 0 llm
**Severity:** HIGH
**Time taken:** 0.0s

BUG #1 [static]
Type: FUNCTIONAL
Location: current_state at line 22
Problem: Blocking assignment (=) used inside always_ff sequential block.
Impact: Can cause simulation/synthesis mismatch; flip-flop behaviour is undefined.
Fix: Replace '=' with '<=' for current_state in this always_ff block.

BUG #2 [static]
Type: LATCH
Location: green in combinational block at line 36
Problem: green is assigned under conditional logic with no complete else or default.
Impact: Synthesis infers a latch to hold the previous value of green.
Fix: Add a default assignment for green before the conditional, or add else/default.

BUG #3 [static]
Type: LATCH
Location: red in combinational block at line 36
Problem: red is assigned under conditional logic with no complete else or default.
Impact: Synthesis infers a latch to hold the previous value of red.
Fix: Add a default assignment for red before the conditional, or add else/default.

BUG #4 [static]
Type: LATCH
Location: yellow in combinational block at line 36
Problem: yellow is assigned under conditional logic with no complete else or default.
Impact: Synthesis infers a latch to hold the previous value of yellow.
Fix: Add a default assignment for yellow before the conditional, or add else/default.

TOTAL BUGS: 4
SEVERITY: HIGH

---

## Timing Analysis

**Total issues found:** 4
**Source breakdown:** 4 static / 0 llm
**Risk level:** HIGH
**Time taken:** 0.0s

TIMING ISSUE #1 [static]
Type: BLOCKING
Location: current_state at line 22
Problem: Blocking assignment (=) used inside always_ff sequential block.
Risk: Can produce timing-dependent simulation mismatch or inferred latch storage.
Fix: Replace '=' with '<=' for current_state in this always_ff block.

TIMING ISSUE #2 [static]
Type: LATCH
Location: green in combinational block at line 36
Problem: green is assigned under conditional logic with no complete else or default.
Risk: Can produce timing-dependent simulation mismatch or inferred latch storage.
Fix: Add a default assignment for green before the conditional, or add else/default.

TIMING ISSUE #3 [static]
Type: LATCH
Location: red in combinational block at line 36
Problem: red is assigned under conditional logic with no complete else or default.
Risk: Can produce timing-dependent simulation mismatch or inferred latch storage.
Fix: Add a default assignment for red before the conditional, or add else/default.

TIMING ISSUE #4 [static]
Type: LATCH
Location: yellow in combinational block at line 36
Problem: yellow is assigned under conditional logic with no complete else or default.
Risk: Can produce timing-dependent simulation mismatch or inferred latch storage.
Fix: Add a default assignment for yellow before the conditional, or add else/default.

TOTAL TIMING ISSUES: 4
RISK LEVEL: HIGH

---

## Generated SVA Assertions

**Total assertions generated:** 2
**Source breakdown:** 2 static / 0 llm
**Coverage level:** MEDIUM
**Time taken:** 2.033908799989149s

ASSERTION #1 [static]
Type: RESET
Signal: green
SVA Code:
assert property (@(posedge clk) disable iff (!(!rst_n)) !rst_n |=> !$isunknown(green));
Description: Verifies green is known immediately after reset is asserted.

ASSERTION #2 [static]
Type: RANGE
Signal: red
SVA Code:
assert property (@(posedge clk) disable iff (!rst_n) !$isunknown(red));
Description: Checks red never becomes X/Z during normal operation.

TOTAL ASSERTIONS: 2
COVERAGE LEVEL: MEDIUM

---

## Code Optimization Suggestions

Error: Ollama returned HTTP 404: {"error":"model 'qwen2.5:3b' not found"}
Ollama URL: http://localhost:11434
Model: qwen2.5:3b
Checks: make sure `ollama serve` is running, the selected model is pulled, and the model can finish this prompt on your machine. If the model is just slow, increase config/settings.json `timeout` or use a smaller model.


---

