# Phase 3 RTL Analysis Report: fsm.sv

**Generated:** 2026-06-18 15:15:18

---

## Bug Analysis

**Total bugs found:** 1
**Severity:** HIGH
**Time taken:** 257.2s

BUG #1
Type: RESET
Location: always_ff @ (posedge clk or negedge rst_n) line 5
Problem: Reset signal 'rst_n' is not used in the reset path of flip-flops.
Impact: Current state will not be reset when 'rst_n' is asserted low.
Fix: Add a default assignment to set current_state to RED_STATE: current_state <= RED_STATE;

TOTAL BUGS: 1
SEVERITY: HIGH

---

## Timing Analysis

**Total issues found:** 0
**Risk level:** LOW
**Time taken:** 104.2s

NO TIMING ISSUES DETECTED

TOTAL TIMING ISSUES: 0
RISK LEVEL: LOW


---

## Generated SVA Assertions

Error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=300)


---

## Code Optimization Suggestions

Error: HTTPConnectionPool(host='localhost', port=11434): Read timed out. (read timeout=300)


---

