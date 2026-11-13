module lane_mux (
    input  logic [1:0] sel_i,
    input  logic [7:0] lane0_i,
    input  logic [7:0] lane1_i,
    input  logic [7:0] lane2_i,
    output logic [7:0] dout
);
    always_comb begin
        // BUG (LATCH): sel_i == 2'b11 is unhandled and no default assignment exists
        case (sel_i)
            2'b00: dout = lane0_i;
            2'b01: dout = lane1_i;
            2'b10: dout = lane2_i;
        endcase
    end
endmodule