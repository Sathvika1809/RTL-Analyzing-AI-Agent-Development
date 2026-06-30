# Phase 3 RTL Analysis Report: counter.sv

**Generated:** 2026-06-30 14:28:56

---

## Bug Analysis

**Total bugs found:** 3
**Severity:** HIGH
**Time taken:** 0.0s

BUG #1
Type: FUNCTIONAL
Location: count at line 14
Problem: Blocking assignment (=) used inside always_ff sequential block.
Impact: Can cause simulation/synthesis mismatch; flip-flop behaviour is undefined.
Fix: Replace '=' with '<=' for count in this always_ff block.

BUG #2
Type: FUNCTIONAL
Location: count at line 16
Problem: Blocking assignment (=) used inside always_ff sequential block.
Impact: Can cause simulation/synthesis mismatch; flip-flop behaviour is undefined.
Fix: Replace '=' with '<=' for count in this always_ff block.

BUG #3
Type: LATCH
Location: carry_out in combinational block at line 21
Problem: carry_out is assigned under conditional logic with no complete else or default.
Impact: Synthesis infers a latch to hold the previous value of carry_out.
Fix: Add a default assignment for carry_out before the conditional, or add else/default.

TOTAL BUGS: 3
SEVERITY: HIGH

---

## Timing Analysis

**Total issues found:** 3
**Risk level:** MEDIUM
**Time taken:** 0.0s

TIMING ISSUE #1
Type: BLOCKING
Location: count at line 14
Problem: Blocking assignment (=) used inside always_ff sequential block.
Risk: Can produce timing-dependent simulation mismatch or inferred latch storage.
Fix: Replace '=' with '<=' for count in this always_ff block.

TIMING ISSUE #2
Type: BLOCKING
Location: count at line 16
Problem: Blocking assignment (=) used inside always_ff sequential block.
Risk: Can produce timing-dependent simulation mismatch or inferred latch storage.
Fix: Replace '=' with '<=' for count in this always_ff block.

TIMING ISSUE #3
Type: LATCH
Location: carry_out in combinational block at line 21
Problem: carry_out is assigned under conditional logic with no complete else or default.
Risk: Can produce timing-dependent simulation mismatch or inferred latch storage.
Fix: Add a default assignment for carry_out before the conditional, or add else/default.

TOTAL TIMING ISSUES: 3
RISK LEVEL: MEDIUM

---

## Generated SVA Assertions

**Total assertions generated:** 2
**Coverage level:** MEDIUM
**Time taken:** 0.0016915000014705583s

ASSERTION #1
Type: RESET
Signal: carry_out
SVA Code:
assert property (@(posedge clk) disable iff (!(!rst_n)) !rst_n |=> !$isunknown(carry_out));
Description: Verifies carry_out is known immediately after reset is asserted.

ASSERTION #2
Type: RANGE
Signal: count
SVA Code:
assert property (@(posedge clk) disable iff (!rst_n) !$isunknown(count));
Description: Checks count never becomes X/Z during normal operation.

TOTAL ASSERTIONS: 2
COVERAGE LEVEL: MEDIUM

---

## Code Optimization Suggestions

**Total suggestions:** 0
**Code quality:** HIGH
**Time taken:** 212.9s

NO OPTIMIZATIONS SUGGESTED

TOTAL OPTIMIZATIONS: 0
QUALITY SCORE: HIGH


---

