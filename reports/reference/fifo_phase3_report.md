# Phase 3 RTL Reference Report: fifo.sv

---

## Bug Analysis

**Total bugs found:** 2
**Severity:** HIGH

### Findings

BUG #1
Type: LATCH
Location: full inside always_comb (line 46)
Problem: Combinational assignment to `full` lacks an `else` branch and has no default assignment.
Impact: Infers a latch on `full` signal, leading to glitchy FIFO full status and timing violations.
Fix: Add a default `full = 1'b0;` at the start of the `always_comb` block.

BUG #2
Type: FUNCTIONAL
Location: empty generation
Problem: The status flag `empty = (wr_ptr == rd_ptr)` does not distinguish between a completely empty FIFO and a completely full FIFO (where both pointers are also equal).
Impact: Causes read operations on a full FIFO to be ignored, or write operations to overwrite data under pointer wrap-around.
Fix: Use a counter or extra pointer bit (wrap bit) to distinguish empty and full pointer collisions.
