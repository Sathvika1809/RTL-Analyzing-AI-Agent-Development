
module counter #(
    parameter WIDTH = 8
)(
    input  logic              clk,
    input  logic              rst_n,
    input  logic              enable,
    output logic [WIDTH-1:0]  count,
    output logic              carry_out
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count = 8'b0;       
        end else if (enable) begin
            count = count + 1;   
        end
    end

    
    always_comb begin
        if (count == {WIDTH{1'b1}})
            carry_out = 1'b1;
      
    end

endmodule