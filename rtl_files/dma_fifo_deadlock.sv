module dma_fifo_deadlock #(
    parameter DATA_WIDTH = 64,
    parameter DEPTH      = 16,
    parameter ADDR_WIDTH = 4
)(
    input  logic                   clk,
    input  logic                   rst_n,

    // Write Interface
    input  logic                   wr_en,
    input  logic [DATA_WIDTH-1:0]  wr_data,
    output logic                   fifo_full,

    // Read Interface
    input  logic                   rd_en,
    output logic [DATA_WIDTH-1:0]  rd_data,
    output logic                   fifo_empty,

    // Credit-based Flow Control
    input  logic                   credit_return, // Remote node returns a credit
    output logic                   credit_avail   // Locally available credits to transmit
);

    logic [DATA_WIDTH-1:0] mem [DEPTH];
    logic [ADDR_WIDTH:0]   wr_ptr, rd_ptr;
    logic [ADDR_WIDTH:0]   fifo_count;
    
    // Credit tracking variables
    logic [ADDR_WIDTH:0]   max_credits;
    logic [ADDR_WIDTH:0]   active_credits;
    logic                  credit_dec;
    logic                  credit_inc;

    assign max_credits = DEPTH;

    
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr     <= '0;
            rd_ptr     <= '0;
            fifo_count <= '0;
        end else begin
            if (wr_en && !fifo_full) begin
                mem[wr_ptr[ADDR_WIDTH-1:0]] <= wr_data;
                wr_ptr                      <= wr_ptr + 1;
            end
            if (rd_en && !fifo_empty) begin
                rd_ptr <= rd_ptr + 1;
            end
            
            
            case ({wr_en && !fifo_full, rd_en && !fifo_empty})
                2'b10: fifo_count <= fifo_count + 1;
                2'b01: fifo_count <= fifo_count - 1;
                default: ; 
            endcase
        end
    end

   
  
    assign fifo_full  = (fifo_count == DEPTH);
    assign fifo_empty = (fifo_count == 0);
    assign rd_data    = mem[rd_ptr[ADDR_WIDTH-1:0]];

  
    assign credit_dec = wr_en && !fifo_full; 
    assign credit_inc = credit_return;       

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            active_credits <= DEPTH;
        end else begin
           
            if (credit_inc && credit_dec) begin
                active_credits <= active_credits;
            end else if (credit_inc) begin
                active_credits <= active_credits + 1;
            end else if (credit_dec) begin
                active_credits <= active_credits - 1;
            end
        end
    end

    assign credit_avail = (active_credits > 0);

endmodule
