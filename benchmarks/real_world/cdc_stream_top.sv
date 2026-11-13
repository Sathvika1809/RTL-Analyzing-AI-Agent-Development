module tx_burst_ctrl #(
    parameter int DATA_W = 8
) (
    input  logic              clk,
    input  logic              rst_n,
    input  logic              start_i,
    input  logic              fifo_full_i,
    output logic              wr_en_o,
    output logic [DATA_W-1:0] wr_data_o
);
    typedef enum logic [1:0] {IDLE, SEND, DONE} state_t;
    state_t state, next_state;
    logic [3:0] pkt_cnt;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state   <= IDLE;
            pkt_cnt <= 4'd0;
            // BUG (RESET): wr_data_o is omitted from the reset branch
        end else begin
            state <= next_state;
            if (wr_en_o) begin
                pkt_cnt   <= pkt_cnt + 4'd1;
                wr_data_o <= {4'hA, pkt_cnt};
            end
        end
    end

    always_comb begin
        next_state = state;
        wr_en_o    = 1'b0;
        case (state)
            IDLE: if (start_i) next_state = SEND;
            SEND: begin
                if (!fifo_full_i) begin
                    wr_en_o = 1'b1;
                    if (pkt_cnt == 4'd7)
                        next_state = DONE;
                end
            end
            DONE: if (!start_i) next_state = IDLE;
            default: next_state = IDLE;
        endcase
    end
endmodule