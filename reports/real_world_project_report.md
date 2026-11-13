# Project report: benchmarks/real_world

Model: `qwen2.5-coder:7b` | modules: 2 | time: 513.0s | 2026-11-13T13:16:46

Count format: static+llm (`ERR` = agent failed, `c` = served from cache)

| Module | LOC | Bugs | Timing | SVA | Opts |
|---|---|---|---|---|---|
| async_fifo_cdc | 71 | 0+2 | 0+1 | 2+8 | 0+0 |
| tx_burst_ctrl | 45 | 1+0 | 0+0 | 2+0 | 0+0 |

## async_fifo_cdc  (async_fifo_cdc.sv:1-71)

### Bugs
- [llm] **FUNCTIONAL** full_o at line 47 - The full condition checks if the write pointer equals the read pointer, which is incorrect. It should check if the write pointer is one step ahead of the read pointer to indicate that the FIFO is full. The missing MSB inversion in the comparison leads to incorrect full condition detection.
- [llm] **FUNCTIONAL** empty_o at line 70 - The empty condition checks if the read pointer equals the write pointer, which is incorrect. It should check if the read pointer is one step ahead of the write pointer to indicate that the FIFO is empty. The missing MSB inversion in the comparison leads to incorrect empty condition detection.

### Timing
- [llm] **CDC** rd_ptr_bin at line 36 - The signal rd_ptr_bin is driven by rd_clk and captured by wr_clk without any synchronization. This can lead to metastability issues if rd_ptr_bin changes while being captured by wr_clk.

### Assertions
- [static] **RESET** wr_ptr_bin - Verifies wr_ptr_bin is known one cycle after reset is asserted.
- [static] **RANGE** rd_ptr_sync1 - Checks rd_ptr_sync1 never becomes X/Z once reset is released.
- [llm] **FUNCTIONAL** full_o - Full condition should not be true when the write pointer is not equal to the read pointer.
- [llm] **FUNCTIONAL** empty_o - Empty condition should not be true when the read pointer is not equal to the write pointer.
- [llm] **STATE** wr_ptr_bin - Write pointer should always be in the range of 0 to DEPTH-1.
- [llm] **STATE** rd_ptr_bin - Read pointer should always be in the range of 0 to DEPTH-1.
- [llm] **STATE** wr_ptr_sync1 - Synchronized write pointer should always be in the range of 0 to DEPTH-1.
- [llm] **STATE** wr_ptr_sync2 - Synchronized write pointer should always be in the range of 0 to DEPTH-1.
- [llm] **STATE** rd_ptr_sync1 - Synchronized read pointer should always be in the range of 0 to DEPTH-1.
- [llm] **STATE** rd_ptr_sync2 - Synchronized read pointer should always be in the range of 0 to DEPTH-1.

### Optimizations
None.

## tx_burst_ctrl  (tx_burst_ctrl.sv:1-45)

### Bugs
- [static] **RESET** wr_data_o in sequential block at line 15 - wr_data_o is updated in a reset-aware block but absent from the reset branch.

### Timing
None.

### Assertions
- [static] **RESET** state - Verifies state is known one cycle after reset is asserted.
- [static] **RANGE** pkt_cnt - Checks pkt_cnt never becomes X/Z once reset is released.

### Optimizations
None.
