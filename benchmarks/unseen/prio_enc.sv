module prio_enc (
    input  logic [3:0] valid_i,
    output logic [1:0] idx
);
    always_comb begin
        // BUG (LATCH): when valid_i == 4'b0000, idx retains its previous value
        if (valid_i[3])
            idx = 2'd3;
        else if (valid_i[2])
            idx = 2'd2;
        else if (valid_i[1])
            idx = 2'd1;
        else if (valid_i[0])
            idx = 2'd0;
    end
endmodule