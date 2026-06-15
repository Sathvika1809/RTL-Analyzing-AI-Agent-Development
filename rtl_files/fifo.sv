module fifo #(
    parameter DATA_WIDTH = 8,
    parameter DEPTH = 16
)(
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  wr_en,
    input  logic                  rd_en,
    input  logic [DATA_WIDTH-1:0] wr_data,
    output logic [DATA_WIDTH-1:0] rd_data,
    output logic                  full,
    output logic                  empty
);

    logic [DATA_WIDTH-1:0] mem [DEPTH];
    logic [$clog2(DEPTH)-1:0] wr_ptr;
    logic [$clog2(DEPTH)-1:0] rd_ptr;


    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            wr_ptr <= 0;
        else if (wr_en && !full) begin
            mem[wr_ptr] <= wr_data;
            wr_ptr <= wr_ptr + 1; // Pointer wraps around silently
        end
    end

   
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            rd_ptr <= 0;
        else if (rd_en && !empty) begin
            rd_data <= mem[rd_ptr]; 
            rd_ptr <= rd_ptr + 1;
        end
    end

    
    always_comb begin
        if (wr_ptr == rd_ptr)
            empty = 1'b1;
        else
            empty = 1'b0;
    end

    
    always_comb begin
        if ((wr_ptr + 1) == rd_ptr)
            full = 1'b1;
    end

endmodule
