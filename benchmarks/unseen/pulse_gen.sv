module pulse_gen #(
    parameter int WIDTH = 4
) (
    input  logic             clk_a,
    input  logic             rstb,
    input  logic             trig_i,
    output logic             pulse_o,
    output logic             done_o
);
    logic [WIDTH-1:0] cnt_r;

    always_ff @(posedge clk_a or negedge rstb) begin
        if (!rstb) begin
            cnt_r   <= '0;
            pulse_o <= 1'b0;
            // BUG (RESET): done_o is not reset
        end else begin
            if (trig_i) begin
                cnt_r   = 4'd5;      // BUG (BLOCKING / FUNCTIONAL): blocking assignment in sequential logic
                pulse_o <= 1'b1;
                done_o  <= 1'b0;
            end else if (cnt_r != '0) begin
                cnt_r   = cnt_r - 1'b1;
                pulse_o <= 1'b1;
                done_o  <= (cnt_r == '0);
            end else begin
                pulse_o <= 1'b0;
                done_o  <= 1'b0;
            end
        end
    end
endmodule