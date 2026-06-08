# RTL Analysis Report: counter.sv



## Model: qwen2.5:3b
Elapsed time: 51.08 seconds

----

```systemverilog
module counter #(
    parameter WIDTH = 8
)(
    input  logic             clk,
    input  logic             rst_n,
    input  logic             en,
    input  logic             load,
    input  logic [WIDTH-1:0] load_val,
    output logic [WIDTH-1:0] count,
    output logic             overflow
);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            count <= '0;
           
        end else if (en) begin
            if (load) begin
                count <= load_val;
            end else begin
                count <= count + 1;
            end
        end

        
        if (count == {WIDTH{1'b1}})
            overflow <= 1'b1;
    end

  

endmodule
```

## BUGS: 
- None found.

## BAD PRACTICES:
- **None found**.

## TIMING:  
- None found.

## FIXES:  
- No fixes are needed as the code does not have any issues.