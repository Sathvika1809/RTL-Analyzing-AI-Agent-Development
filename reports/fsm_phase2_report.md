# RTL Analysis Report: fsm.sv



## Model: qwen2.5:3b
Elapsed time: 53.74 seconds

----

## BUGS
### LINE: 6
### CODE:
```systemverilog
typedef enum logic [1:0] {
    RED_STATE    = 2'b00,
    GREEN_STATE  = 2'b01,
    YELLOW_STATE = 2'b10
} state_t;
```
### ISSUE: 
The `state_t` typedef is not used anywhere in the code. It does not contribute to any functionality and can be removed.

### IMPACT:
Removing unused types improves maintainability by reducing clutter and making the code cleaner.

### FIX:
Remove the `typedef enum logic [1:0] { ... } state_t;` line.

## BAD PRACTICES
None.

## TIMING
No timing issues observable from RTL.

## FIXES
None.