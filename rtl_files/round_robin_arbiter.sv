module round_robin_arbiter #(
    parameter NUM_REQS = 4
)(
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic [NUM_REQS-1:0]   req,
    output logic [NUM_REQS-1:0]   gnt
);

    logic [NUM_REQS-1:0] req_masked;
    logic [NUM_REQS-1:0] mask, next_mask;
    logic [NUM_REQS-1:0] gnt_raw, gnt_masked;

    // Mask generation for round robin
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mask <= {NUM_REQS{1'b1}};
        end else if (|gnt) begin
            
            mask <= next_mask;
        end
    end

    
    always_comb begin
        next_mask = mask;
        for (int i = 0; i < NUM_REQS; i++) begin
            if (gnt[i]) begin
                next_mask = ~((1'b1 << (i + 1)) - 1);
            end
        end
    end

    
    always_comb begin
        gnt_raw = '0;
        for (int i = 0; i < NUM_REQS; i++) begin
            if (req[i] && !(|gnt_raw)) begin
                gnt_raw[i] = 1'b1;
            end
        end
    end

   
    assign req_masked = req & mask;
    always_comb begin
        gnt_masked = '0;
        for (int i = 0; i < NUM_REQS; i++) begin
            if (req_masked[i] && !(|gnt_masked)) begin
                gnt_masked[i] = 1'b1;
            end
        end
    end

 
 
    assign gnt = (|req_masked) ? gnt_masked : (gnt_raw & ~mask); 
    
endmodule
