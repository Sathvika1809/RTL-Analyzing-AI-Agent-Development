# Phase 3 RTL Analysis Report: fsm.sv

**Generated:** 2026-06-30 14:52:06

---

## Bug Analysis

**Total bugs found:** 4
**Severity:** HIGH
**Time taken:** 0.0s

BUG #1
Type: FUNCTIONAL
Location: current_state at line 22
Problem: Blocking assignment (=) used inside always_ff sequential block.
Impact: Can cause simulation/synthesis mismatch; flip-flop behaviour is undefined.
Fix: Replace '=' with '<=' for current_state in this always_ff block.

BUG #2
Type: LATCH
Location: green in combinational block at line 36
Problem: green is assigned under conditional logic with no complete else or default.
Impact: Synthesis infers a latch to hold the previous value of green.
Fix: Add a default assignment for green before the conditional, or add else/default.

BUG #3
Type: LATCH
Location: red in combinational block at line 36
Problem: red is assigned under conditional logic with no complete else or default.
Impact: Synthesis infers a latch to hold the previous value of red.
Fix: Add a default assignment for red before the conditional, or add else/default.

BUG #4
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
**Risk level:** MEDIUM
**Time taken:** 0.0s

TIMING ISSUE #1
Type: BLOCKING
Location: current_state at line 22
Problem: Blocking assignment (=) used inside always_ff sequential block.
Risk: Can produce timing-dependent simulation mismatch or inferred latch storage.
Fix: Replace '=' with '<=' for current_state in this always_ff block.

TIMING ISSUE #2
Type: LATCH
Location: green in combinational block at line 36
Problem: green is assigned under conditional logic with no complete else or default.
Risk: Can produce timing-dependent simulation mismatch or inferred latch storage.
Fix: Add a default assignment for green before the conditional, or add else/default.

TIMING ISSUE #3
Type: LATCH
Location: red in combinational block at line 36
Problem: red is assigned under conditional logic with no complete else or default.
Risk: Can produce timing-dependent simulation mismatch or inferred latch storage.
Fix: Add a default assignment for red before the conditional, or add else/default.

TIMING ISSUE #4
Type: LATCH
Location: yellow in combinational block at line 36
Problem: yellow is assigned under conditional logic with no complete else or default.
Risk: Can produce timing-dependent simulation mismatch or inferred latch storage.
Fix: Add a default assignment for yellow before the conditional, or add else/default.

TOTAL TIMING ISSUES: 4
RISK LEVEL: MEDIUM

---

## Generated SVA Assertions

**Total assertions generated:** 2
**Coverage level:** MEDIUM
**Time taken:** 0.00228169999900274s

ASSERTION #1
Type: RESET
Signal: green
SVA Code:
assert property (@(posedge clk) disable iff (!(!rst_n)) !rst_n |=> !$isunknown(green));
Description: Verifies green is known immediately after reset is asserted.

ASSERTION #2
Type: RANGE
Signal: red
SVA Code:
assert property (@(posedge clk) disable iff (!rst_n) !$isunknown(red));
Description: Checks red never becomes X/Z during normal operation.

TOTAL ASSERTIONS: 2
COVERAGE LEVEL: MEDIUM

---

## Code Optimization Suggestions

**Total suggestions:** 2
**Code quality:** MEDIUM
**Time taken:** 235.4s

OPTIMIZATION #1
Type: HARDCODED
Location: always_comb block in case (current_state)
Issue: Hardcoded values for state transitions can be made more flexible with parameters.
Benefit: Improves code maintainability and reusability.
Suggestion: Add a parameter to define the states and their corresponding next states.

OPTIMIZATION #2
Type: STYLE
Location: always_comb block in case (current_state)
Issue: The logic for each state is duplicated. Simplify the combinatorial blocks.
Benefit: Reduces code duplication and improves readability.
Suggestion: Combine the always_comb blocks into a single block with conditional statements.

TOTAL OPTIMIZATIONS: 2
QUALITY SCORE: MEDIUM

---

