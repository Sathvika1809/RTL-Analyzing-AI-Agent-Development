# Phase1 - Environment Setup and Baseline Evaluation Report
## Author - H.Sathvika
## Date: June 8 2026
## RTL ANALYSING AI AGENT DEVELOPMENT

# Objective
Evaluate the capability of locally deployed llms via Ollama to analyze SystemVerilog RTL Code. Three models were tested on a deliberately buggy RTL file to establish a baseline before building specialized agents.

# Environment Setup
# Component Details
- OS - Windows 11
- CPU
- Intel Core Ultra 5 125U - 12cores
- RAM 16GB
# LLM Frameworks
Ollama v0.24.0
Python 3.12
Libraries - requests,time,os,glob
Models tested - mistral,codellama,tinyllama

## Test File — `counter.sv`

```systemverilog
module counter (
    input clk,
    input rst,
    output reg [3:0] count
);
    always @(posedge clk) begin
        if (rst)
            count = 0;      
        else
            count = count + 1;
    end
endmodule
```
## Known  bugs

- Blocking assignment `=`
inside
'always @(posedge clk)`
Should be `<=`
- Reason: 
Blocking assignments in sequential blocks cause race conditions when multiple always blocks share signals. Simulation behavior may differ from synthesized hardware. 

## Model: mistral
Elapsed time: 139.38 seconds

 1. BUGS: None found. The code for the counter is correct and functional.

2. BAD PRACTICES: The code does not have any bad practices that directly affect its functionality, but it might be worth considering adding a clock enable (ce) to prevent counting when clk is low. This would make the design more robust against clock glitches.

3. TIMING: The given code does not include any explicit timing constraints. As a result, the synthesis tool will generate default timing assumptions based on its library. This may lead to unexpected delays in the implemented hardware. To address this issue, consider adding appropriate timing constraints using the `create_clock` and `create_port` commands from the SystemVerilog built-in package `scscope`.

4. FIXES: To improve the design's robustness against clock glitches, you could add a clock enable (ce) signal and modify the always block as follows:

```systemverilog
module counter (
    input clk,
    input rst,
    input ce,
    output reg [3:0] count
);
always @(posedge clk when ce) begin
    if (rst)
        count = 0;
    else
        count = count + 1;
end
```
In this modified version of the code, counting only occurs on positive clock edges when the `ce` signal is high. This can help prevent problems caused by unexpectedly low or glitchy clocks.

## Model: tinyllama
Elapsed time: 21.64 seconds

I am not able to provide specific issues for a specific code provided below, but here's an example of how to analyze the systemverilog code based on the given requirements:

1. Bugs: there are no bugs found in the given code as it is written only in systemverilog and has no issues related to signal, module or behavior.

2. Bad practices: no bad practices have been identified in this code.

3. Timing: since there are no timing constraints specified in the provided code, there are no issues with respect to the timing requirements of a verification design.

4. Fixes: there are no issues related to fixing bugs or addressing concerns raised during verification.

in summary, the above analysis will show that the given code has passed all the necessary checks for bugs, bad practices, and timing constraints in systemverilog.

## Model: codellama
Elapsed time: 112.23 seconds


BUGS:
No bugs found.

BAD PRACTICES:
* The "count" output signal should be declared as a wire instead of a reg. This is because the counter is not supposed to change its value at any time other than when the clock edge occurs, and using a wire would help enforce this property.

TIMING:
The counter can get stuck in an infinite loop if the reset signal is asserted for more than one cycle. This can occur if the reset signal is asserted while the counter is still incrementing its count value. To fix this, it may be necessary to add a condition to check whether the reset signal has been deasserted before incrementing the count value.

FIXES:
Add the following line of code after the "else" clause to avoid the infinite loop:
```systemverilog
if (!rst) begin
    count = count + 1;
end
```
## Observation:
- "codellama caught the blocking assignment bug but hallucinated — it claimed the register size was not specified when it clearly was in the code. mistral partially caught it but in one run said the module had no flip flops at all, which is factually wrong for a clocked counter. tinyllama was the fastest at 22 seconds but invented a signal called RST_N that doesn't exist anywhere in the code and claimed the module had no input or output pins — completely wrong. All three models hallucinated at least one non-existent issue."
## Conclusion
"All the three llm models failed to detect a blocking assignment bug in the file. Instead they hallunicated non existent bugs and suggested invalid fixes. Codellama recommended changing a register to a wire - which would break the design entirely since wires cannot store state.This proves that general prompts with general models are insufficient for RTL Analysis and motivated the specialized agent approach in Phase3 where explicit step by step checks forced the model to check specific patterns like blocking assignments in sequential blocks"