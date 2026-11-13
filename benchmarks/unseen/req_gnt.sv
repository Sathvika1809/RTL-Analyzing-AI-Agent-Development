module req_gnt (
    input  logic       clk_a,
    input  logic       arst,
    input  logic [1:0] req_i,
    output logic [1:0] gnt_q,
    output logic       busy_o
);
    always_ff @(posedge clk_a or posedge arst) begin
        if (arst) begin
            gnt_q  <= 2'b00;
            busy_o <= 1'b0;
        end else begin
            if (req_i[0])
                gnt_q = 2'b01;   // BUG (BLOCKING / FUNCTIONAL): blocking assignment to sequential state
            else if (req_i[1])
                gnt_q = 2'b10;
            else
                gnt_q = 2'b00;

            busy_o <= |gnt_q;    // Reads updated gnt_q immediately due to blocking '='
        end
    end
endmodule