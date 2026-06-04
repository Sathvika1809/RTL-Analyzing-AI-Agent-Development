// fsm.sv
// Simple 3-state Finite State Machine: IDLE → ACTIVE → DONE
// Contains intentional bugs for agent testing

module fsm (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic done_sig,
    output logic busy,
    output logic complete
);

    // State encoding
    typedef enum logic [1:0] {
        IDLE   = 2'b00,
        ACTIVE = 2'b01,
        DONE   = 2'b10
        // BUG 1: 2'b11 is an unhandled state → X-state risk
    } state_t;

    state_t current_state, next_state;

    // Sequential logic — state register
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            current_state <= IDLE;
        else
            current_state <= next_state;
    end

    // Combinational logic — next state
    // BUG 2: complete is assigned here (combinational) AND in the output block
    // This creates a multiple-driver situation
    always_comb begin
        case (current_state)
            IDLE:   next_state = start    ? ACTIVE : IDLE;
            ACTIVE: next_state = done_sig ? DONE   : ACTIVE;
            DONE:   next_state = IDLE;
            // BUG 3: default missing — latch for next_state on state 2'b11
        endcase
    end

    // Output logic
    // BUG 4: busy not assigned in DONE state → LATCH
    always_comb begin
        case (current_state)
            IDLE:   begin busy = 1'b0; complete = 1'b0; end
            ACTIVE: begin busy = 1'b1; complete = 1'b0; end
            DONE:   begin complete = 1'b1; end  // busy missing here
        endcase
    end

endmodule