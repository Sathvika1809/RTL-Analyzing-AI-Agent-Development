

module alu #(
    parameter WIDTH = 8
)(
    input  logic signed [WIDTH-1:0] a,
    input  logic signed [WIDTH-1:0] b,
    input  logic [2:0]              op,
    output logic [WIDTH-1:0]        result,
    output logic                    zero_flag,
    output logic                    overflow
);

    always_comb begin
        case (op)
            3'b000: result = a + b;
            3'b001: result = a - b;
            3'b010: result = a & b;
            3'b011: result = a | b;
            3'b100: result = a ^ b;
            
        endcase
       
    end

    
    always_comb begin
        if (result == 9'b0)
            zero_flag = 1'b1;
        else
            zero_flag = 1'b0;
    end

endmodule