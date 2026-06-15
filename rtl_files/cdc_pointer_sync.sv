module cdc_pointer_sync #(
    parameter ADDR_WIDTH = 4
)(
    input  logic                  wr_clk,
    input  logic                  wr_rst_n,
    input  logic                  rd_clk,
    input  logic                  rd_rst_n,
    input  logic [ADDR_WIDTH:0]   wr_ptr_bin, 
    output logic [ADDR_WIDTH:0]   rd_ptr_bin 
);

    

    logic [ADDR_WIDTH:0] sync_reg_0;
    logic [ADDR_WIDTH:0] sync_reg_1;

    always_ff @(posedge rd_clk or negedge rd_rst_n) begin
        if (!rd_rst_n) begin
            sync_reg_0 <= '0;
            sync_reg_1 <= '0;
        end else begin
            sync_reg_0 <= wr_ptr_bin;
            sync_reg_1 <= sync_reg_0;
        end
    end

    assign rd_ptr_bin = sync_reg_1;

endmodule
