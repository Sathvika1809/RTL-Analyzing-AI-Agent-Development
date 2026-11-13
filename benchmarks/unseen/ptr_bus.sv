module ptr_bus (
    input  logic       clk_a,
    input  logic       reset_n,
    input  logic       inc_i,
    input  logic [3:0] limit_i,
    output logic [2:0] ptr,
    output logic       err_o
);
    always_ff @(posedge clk_a or negedge reset_n) begin
        if (!reset_n) begin
            ptr   <= 3'd0;
            err_o <= 1'b0;
        end else if (inc_i) begin
            // BUG (FUNCTIONAL): 3-bit ptr wraps at 8, so ptr > limit_i (4-bit up to 15) can be unreachable
            ptr   <= ptr + 3'd1;
            err_o <= ({1'b0, ptr} > limit_i) ? 1'b0 : 1'b1; // BUG (FUNCTIONAL): inverted error polarity
        end
    end
endmodule