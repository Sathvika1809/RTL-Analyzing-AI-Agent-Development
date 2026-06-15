# Phase 3 RTL Reference Report: alu.sv

---

## Bug Analysis

**Total bugs found:** 3
**Severity:** CRITICAL

### Findings

BUG #1
Type: LATCH
Location: result inside always_comb block
Problem: Incomplete case statement inside `always_comb` block. Case statement does not cover all possible values of `op` (only `3'b000` to `3'b100` are defined, leaving `3'b101` to `3'b111` unassigned) and lacks a `default` case.
Impact: Incurs latch inference during hardware synthesis, which violates synchronous design principles and causes timing/functional bugs in silicon.
Fix: Add a default assignment `result = '0;` at the beginning of the `always_comb` block or include a `default:` branch inside the `case` statement.

BUG #2
Type: WIDTH
Location: zero_flag checking condition (line 28)
Problem: The zero_flag comparison logic `result == 9'b0` compares the 8-bit `result` vector (parameterized by `WIDTH = 8` by default) against a 9-bit literal zero value.
Impact: Triggers compiler width mismatches and sign/zero extension warnings during synthesis and linting.
Fix: Change the comparison to `result == '0` or match the literal width to the parameter width: `result == {WIDTH{1'b0}}`.

BUG #3
Type: FUNCTIONAL
Location: overflow output port
Problem: The output port `overflow` is declared in the module header but is never driven or assigned any value inside the module body.
Impact: Results in an undriven/floating output pin on the synthesized block, which will be optimized away or cause logic faults downstream.
Fix: Add logic inside `always_comb` to calculate overflow for signed arithmetic ops (e.g., matching sign bit overflows on addition and subtraction).

---

## Timing Analysis

**Total issues found:** 2
**Risk level:** MEDIUM

### Findings

TIMING ISSUE #1
Type: LATCH
Location: result logic
Problem: Incomplete assignment in combinational block for op operations. Latch propagation delay acts as a combination loop.
Risk: Introduces setup and hold time violations, creating unstable simulation and timing closure failures.
Fix: Assign default value `result = '0;` prior to the case statement.

TIMING ISSUE #2
Type: COMBO_PATH
Location: zero_flag output logic
Problem: Zero flag generation relies on a long cascade of comparison operators (`result == 9'b0`) right after the adder/subtractor combination logic.
Risk: Increases the combinational path delay to `zero_flag`, potentially violating setup timing if the clock frequency is high.
Fix: Register the zero flag using a sequential block if latency permits, or optimize the comparator tree.

---

## Generated SVA Assertions

**Total assertions generated:** 3
**Coverage level:** HIGH

### Findings

ASSERTION #1
Type: RANGE
Signal: result
SVA Code:
assert property (@(posedge clk) (op <= 3'b100) -> !$isunknown(result));
Description: Ensure that result is never unknown (X-state) when a valid op is selected.

ASSERTION #2
Type: INPUT
Signal: zero_flag
SVA Code:
assert property (@(posedge clk) (result == '0) -> zero_flag === 1'b1);
Description: Ensure zero_flag is asserted if and only if result is zero.

ASSERTION #3
Type: OVERFLOW
Signal: overflow
SVA Code:
assert property (@(posedge clk) (op == 3'b000 && a[WIDTH-1] == b[WIDTH-1] && result[WIDTH-1] != a[WIDTH-1]) -> overflow === 1'b1);
Description: Verify that signed addition overflow triggers the overflow signal correctly.

---

## Code Optimization Suggestions

**Total suggestions:** 2
**Code quality:** MEDIUM

### Findings

OPTIMIZATION #1
Type: HARDCODED
Location: zero_flag condition (line 28)
Problem: Hardcoded 9-bit literal `9'b0` is used for zero checking instead of referencing the `WIDTH` parameter.
Benefit: Reusability and cleanliness. If `WIDTH` changes, the logic updates dynamically.
Suggestion: Use `result == '0` instead of `result == 9'b0`.

OPTIMIZATION #2
Type: STYLE
Location: indentation and module definition
Problem: Inconsistent indentation between the parameters, module port declaration, and internal logic blocks.
Benefit: Improves code readability and developer maintenance.
Suggestion: Clean up blank lines at the top of the module and consistently indent logical blocks.
