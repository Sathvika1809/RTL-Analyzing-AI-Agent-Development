# Phase 3 RTL Reference Report: dma_fifo_deadlock.sv

---

## Bug Analysis

**Total bugs found:** 3
**Severity:** CRITICAL

### Findings

BUG #1
Type: FUNCTIONAL
Location: active_credits update (line 81)
Problem: Counter underflow checking is missing when decrementing `active_credits`. If `active_credits` is `0` and a decrement is requested, it rolls over to the maximum representable value.
Impact: Allows the DMA channel to continue writing even when no buffer slots are available, overwriting unread data and corrupting the stream.
Fix: Protect the decrement branch: `else if (credit_dec && active_credits > 0) active_credits <= active_credits - 1;`.

BUG #2
Type: FUNCTIONAL
Location: credit_inc check (line 74)
Problem: Credit increment lacks overflow checking against `max_credits` (DEPTH).
Impact: A glitched credit return can increment credits past the physical depth, leaking credits.
Fix: Ensure `active_credits < max_credits` before incrementing.

BUG #3
Type: RESET
Location: active_credits register
Problem: Reset polarity uses `negedge rst_n`, but reset value is hardcoded as `DEPTH` rather than referencing parameter sizes or using proper bounds checking on startup.
Impact: Minor startup latency variations under parameter override.
Fix: Assign `active_credits <= DEPTH` on reset.
