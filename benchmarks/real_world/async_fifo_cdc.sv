module async_fifo_cdc #(
    parameter int DATA_W = 8,
    parameter int ADDR_W = 4
) (
    input  logic              wr_clk,
    input  logic              wr_rst_n,
    input  logic              wr_en_i,
    input  logic [DATA_W-1:0] wr_data_i,
    output logic              full_o,

    input  logic              rd_clk,
    input  logic              rd_rst_n,
    input  logic              rd_en_i,
    output logic [DATA_W-1:0] rd_data_o,
    output logic              empty_o
);
    localparam int DEPTH = 1 << ADDR_W;

    logic [DATA_W-1:0] mem [0:DEPTH-1];
    logic [ADDR_W:0]   wr_ptr_bin;
    logic [ADDR_W:0]   rd_ptr_bin;
    logic [ADDR_W:0]   wr_ptr_sync1, wr_ptr_sync2;
    logic [ADDR_W:0]   rd_ptr_sync1, rd_ptr_sync2;

    // Write domain
    always_ff @(posedge wr_clk or negedge wr_rst_n) begin
        if (!wr_rst_n) begin
            wr_ptr_bin <= '0;
        end else if (wr_en_i && !full_o) begin
            mem[wr_ptr_bin[ADDR_W-1:0]] <= wr_data_i;
            wr_ptr_bin <= wr_ptr_bin + 1'b1;
        end
    end

    // BUG 1 (CDC): Raw binary pointer rd_ptr_bin crosses directly into wr_clk without Gray coding
    always_ff @(posedge wr_clk or negedge wr_rst_n) begin
        if (!wr_rst_n) begin
            rd_ptr_sync1 <= '0;
            rd_ptr_sync2 <= '0;
        end else begin
            rd_ptr_sync1 <= rd_ptr_bin;
            rd_ptr_sync2 <= rd_ptr_sync1;
        end
    end

    // BUG 2 (FUNCTIONAL): Full condition checks all bits equal (which is empty), missing MSB inversion
    assign full_o = (wr_ptr_bin == rd_ptr_sync2);

    // Read domain
    always_ff @(posedge rd_clk or negedge rd_rst_n) begin
        if (!rd_rst_n) begin
            rd_ptr_bin <= '0;
            rd_data_o  <= '0;
        end else if (rd_en_i && !empty_o) begin
            rd_data_o  <= mem[rd_ptr_bin[ADDR_W-1:0]];
            rd_ptr_bin <= rd_ptr_bin + 1'b1;
        end
    end

    always_ff @(posedge rd_clk or negedge rd_rst_n) begin
        if (!rd_rst_n) begin
            wr_ptr_sync1 <= '0;
            wr_ptr_sync2 <= '0;
        end else begin
            wr_ptr_sync1 <= wr_ptr_bin;
            wr_ptr_sync2 <= wr_ptr_sync1;
        end
    end

    assign empty_o = (rd_ptr_bin == wr_ptr_sync2);
endmodule