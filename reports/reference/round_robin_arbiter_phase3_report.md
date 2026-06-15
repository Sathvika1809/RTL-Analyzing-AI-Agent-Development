# Phase 3 RTL Reference Report: round_robin_arbiter.sv

---

## Bug Analysis

**Total bugs found:** 2
**Severity:** CRITICAL

### Findings

BUG #1
Type: FUNCTIONAL
Location: next_mask logic inside always_comb (line 32)
Problem: Mask calculation uses `next_mask = ~((1'b1 << (i + 1)) - 1)`. If `i` is `NUM_REQS - 1`, `i + 1` is equal to `NUM_REQS`. Shifting a 1-bit value by `NUM_REQS` is out of bounds or causes overflow issues when updating priority.
Impact: Incomplete or incorrect mask wrapping, leading to priority lockout where requests at certain indices are permanently ignored.
Fix: Wrap the shift using a modulo operation or use standard conditional subtraction: `next_mask = ~((1'b1 << ((i + 1) % NUM_REQS)) - 1);`.

BUG #2
Type: FUNCTIONAL
Location: gnt selection logic (line 61)
Problem: Fallback logic `gnt = (|req_masked) ? gnt_masked : (gnt_raw & ~mask)` is buggy. It applies `~mask` to `gnt_raw` when `req_masked` is zero.
Impact: If all requests are outside the mask, this logic can mask off valid requests in `gnt_raw`, causing a zero-grant lockout and deadlocking the bus.
Fix: If `req_masked` is zero, the arbiter must fall back to the raw fixed-priority grant: `assign gnt = (|req_masked) ? gnt_masked : gnt_raw;`.
