# Phase 3 RTL Reference Report: cdc_pointer_sync.sv

---

## Bug Analysis

**Total bugs found:** 1
**Severity:** HIGH

### Findings

BUG #1
Type: FUNCTIONAL
Location: wr_ptr_bin inside rd_clk always_ff block (line 21)
Problem: The multi-bit binary value `wr_ptr_bin` is directly assigned to the synchronizer register `sync_reg_0` in the destination clock domain `rd_clk`.
Impact: CDC bug. Different bits of the binary write pointer will experience different propagation skews across clock boundaries, causing the synchronizer to capture invalid intermediate/corrupt pointer values.
Fix: Convert the binary write pointer to Gray code in the `wr_clk` domain, synchronize the Gray pointer using the 2-FF synchronizer chain, and convert it back to binary in the `rd_clk` domain.

---

## Timing Analysis

**Total issues found:** 1
**Risk level:** HIGH

### Findings

TIMING ISSUE #1
Type: CDC
Location: wr_ptr_bin to sync_reg_0 crossing
Problem: Direct asynchronous transfer of a multi-bit binary data bus (`wr_ptr_bin`) across clock domains.
Risk: Setup/hold time violations on individual bits lead to metastability and sampling of incorrect pointer states in the read clock domain.
Fix: Gray coding of the synchronized bus to guarantee that only 1 bit changes at any clock transition.
