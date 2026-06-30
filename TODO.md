# TODO

## Step 1: Validate root cause
- [x] Read `rtl_files/alu.sv` and confirm hardcoded sized literal (`9'b0`) and latch issue.
- [x] Read `src/core/rtl_parser.py` and identify missing checks for width mismatches in procedural expressions.
- [x] Read `src/agents/assertion_agent.py` and confirm semantic filtering exists for LLM assertion outputs.

## Step 2: Harden deterministic analyzer (no LLM)
- [x] Update `src/core/rtl_parser.py`:
  - Add procedural sized-literal width mismatch detection (e.g. `if (result == 9'b0)`), comparing literal bit-count to declared width of the signal.
  - Improve undriven output port detection / driven-LHS extraction inside `always_comb` + `case`.

## Step 3: Wire new finding type into report
- [x] Ensure new findings surface through `static_bug_findings()` and are included in `bug_agent` markdown.

## Step 4: Regression
- [x] Run the parser/agent path for `rtl_files/alu.sv` and confirm:
  - Width mismatch is reported.
  - Any “unassigned port” issue is detected.
  - No spurious hallucinated names appear.

