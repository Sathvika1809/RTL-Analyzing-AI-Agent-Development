module edge_detect (
    input  logic clk_a,
    input  logic reset_n,
    input  logic sig_i,
    output logic rise_o,
    output logic fall_o
);
    logic sig_q;

    always_ff @(posedge clk_a or negedge reset_n) begin
        if (!reset_n) begin
            sig_q <= 1'b0;
        end else begin
            sig_q <= sig_i;
        end
    end

    assign rise_o =  sig_i & ~sig_q;
    assign fall_o = ~sig_i &  sig_q;
endmodule