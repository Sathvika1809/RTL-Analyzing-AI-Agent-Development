# Phase 3 RTL Reference Report: fsm.sv

---

## Bug Analysis

**Total bugs found:** 4
**Severity:** CRITICAL

### Findings

BUG #1
Type: FUNCTIONAL
Location: always_ff block (line 24)
Problem: Blocking assignment (`current_state = next_state;`) is used in the sequential state register block instead of non-blocking (`<=`).
Impact: Synthesizer-simulator mismatches, causing race conditions in state transition tracking during simulation.
Fix: Use non-blocking assignment: `current_state <= next_state;`.

BUG #2
Type: LATCH
Location: next_state inside always_comb block (line 28)
Problem: Latch inferred on `next_state` variable. The `case` statement does not cover all possible states for the 2-bit type variable `current_state` (state `2'b11` is not defined in the enum or the case, and there is no default statement).
Impact: Creates latches during synthesis, violating synchronous timing paths and making timing closure extremely difficult.
Fix: Add a `default: next_state = RED_STATE;` case statement.

BUG #3
Type: LATCH
Location: red, green, and yellow outputs inside always_comb (line 38)
Problem: Latch inferred on output signals `red`, `green`, and `yellow`. For instance, `yellow` is not assigned in `RED_STATE` or `GREEN_STATE`. Additionally, the case statement lacks a default branch, meaning the 2-bit state `2'b11` remains completely unhandled.
Impact: Severe latch inference on all three output logic ports, causing hold and timing errors in hardware.
Fix: Add default assignments: `red = 1'b0; yellow = 1'b0; green = 1'b0;` at the beginning of the `always_comb` block.

BUG #4
Type: RESET
Location: outputs (lines 7-9)
Problem: The outputs `red`, `yellow`, and `green` are combinational and have no direct reset logic, but because of latch inference, they can hold arbitrary state on startup prior to reset completion.
Impact: System initialization glitches on startup or reset assertion.
Fix: Resolve the latch inference by assigning defaults in the combinational block.

---

## Timing Analysis

**Total issues found:** 2
**Risk level:** HIGH

### Findings

TIMING ISSUE #1
Type: BLOCKING
Location: always_ff block (line 24)
Problem: Blocking assignment (`current_state = next_state`) updates the register immediately.
Risk: Propagates state updates too early to downstream combinational logic, causing hold-time violations.
Fix: Change the assignment to `<=` (non-blocking).

TIMING ISSUE #2
Type: LATCH
Location: outputs combinational block (line 38)
Problem: Unassigned outputs in some branches and missing default cases infer physical latches.
Risk: Latch enable paths are combinational and subject to glitches, leading to unpredictable timing behavior and potential clock/data race conditions.
Fix: Declare default values for `red`, `yellow`, and `green` at the top of the block.

---

## Generated SVA Assertions

**Total assertions generated:** 4
**Coverage level:** HIGH

### Findings

ASSERTION #1
Type: RESET
Signal: current_state
SVA Code:
assert property (@(posedge clk) (!rst_n) -> current_state === RED_STATE);
Description: Verify that the FSM transitions to RED_STATE when active-low reset is asserted.

ASSERTION #2
Type: TRANSITION
Signal: current_state
SVA Code:
assert property (@(posedge clk) disable iff (!rst_n) (current_state == GREEN_STATE) -> (next_state == YELLOW_STATE));
Description: Verify that GREEN_STATE always transitions directly to YELLOW_STATE on the next clock.

ASSERTION #3
Type: RANGE
Signal: next_state
SVA Code:
assert property (@(posedge clk) next_state != 2'b11);
Description: Ensure that the FSM never enters the undefined state 2'b11.

ASSERTION #4
Type: INPUT
Signal: red
SVA Code:
assert property (@(posedge clk) disable iff (!rst_n) (current_state == RED_STATE) -> (red === 1'b1 && green === 1'b0 && yellow === 1'b0));
Description: Ensure output states are mutually exclusive and correct for RED_STATE.

---

## Code Optimization Suggestions

**Total suggestions:** 2
**Code quality:** MEDIUM

### Findings

OPTIMIZATION #1
Type: NAMING
Location: current_state, next_state
Problem: The naming `current_state` and `next_state` is fine, but enum values like `RED_STATE` can be simplified to just `RED`, `GREEN`, `YELLOW` to improve readability.
Benefit: Makes the code more compact and aligns with standard EDA FSM coding guidelines.
Suggestion: Update enum declaration values.

OPTIMIZATION #2
Type: STYLE
Location: multiple always blocks
Problem: Having separate always blocks for FSM transitions and FSM outputs is valid, but merging FSM next-state and outputs into a single, clean block or using a single-always FSM style can sometimes improve timing.
Benefit: Avoids splitting state dependencies across multiple places.
Suggestion: Document the dual combinational block style with descriptive block labels.
