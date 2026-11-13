module shift_reg #(
    parameter int DEPTH = 4
) (
    input  logic             clk_a,
    input  logic             rstb,
    input  logic             en_i,
    input  logic             din_i,
    output logic [DEPTH-1:0] data_q,
    output logic             dout_o
);
    always_ff @(posedge clk_a or negedge rstb) begin
        if (!rstb) begin
            data_q <= '0;
        end else if (en_i) begin
            data_q <= {data_q[DEPTH-2:0], din_i};
        end
    end

    assign dout_o = data_q[DEPTH-1];
endmodule