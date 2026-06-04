// alu.sv
// Arithmetic Logic Unit - 4 operation ALU
// Intentional bugs planted for agent testing

module alu #(
    parameter WIDTH = 8
)(
    input  logic [WIDTH-1:0]  a,
    input  logic [WIDTH-1:0]  b,
    input  logic [1:0]        op,       // 00=ADD 01=SUB 10=AND 11=OR
    input  logic              clk,
    input  logic              rst_n,
    output logic [WIDTH-1:0]  result,
    output logic              zero_flag,
    output logic              carry_out
);

    // BUG 1: result is assigned in always_comb without a default
    // If op is not 00,01,10,11 (impossible for 2-bit but still bad practice)
    // and more critically: carry_out is never assigned for AND/OR → LATCH
    always_comb begin
        case (op)
            2'b00: begin
                result    = a + b;
                carry_out = (a + b) > {WIDTH{1'b1}};  // BUG: width mismatch risk
            end
            2'b01: begin
                result    = a - b;
                carry_out = (a < b);
            end
            2'b10: begin
                result    = a & b;
                // BUG 2: carry_out not assigned here → LATCH INFERENCE
            end
            2'b11: begin
                result    = a | b;
                // BUG 3: carry_out not assigned here → LATCH INFERENCE
            end
        endcase
    end

    // BUG 4: zero_flag uses blocking assignment inside always_ff
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            zero_flag = 1'b0;   // BUG: should be <= (non-blocking)
        end else begin
            zero_flag = (result == '0);  // BUG: blocking in always_ff
        end
    end

    // BUG 5: No assertion to catch when op is used before reset
    // Missing: no SVA coverage for all op codes

endmodule