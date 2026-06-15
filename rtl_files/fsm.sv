

module fsm (
    input  logic clk,
    input  logic rst_n,
    input  logic sensor,
    output logic red,
    output logic yellow,
    output logic green
);

    typedef enum logic [1:0] {
        RED_STATE    = 2'b00,
        GREEN_STATE  = 2'b01,
        YELLOW_STATE = 2'b10
    } state_t;

    state_t current_state, next_state;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            current_state <= RED_STATE;
        else
            current_state = next_state;  
    end

    
    always_comb begin
        case (current_state)
            RED_STATE:    next_state = sensor ? GREEN_STATE : RED_STATE;
            GREEN_STATE:  next_state = YELLOW_STATE;
            YELLOW_STATE: next_state = RED_STATE;
            
        endcase
    end

    
    always_comb begin
        case (current_state)
            RED_STATE:    begin
                red    = 1'b1;
                green  = 1'b0;
                
            end
            GREEN_STATE:  begin
                green  = 1'b1;
                red    = 1'b0;
                
            end
            YELLOW_STATE: begin
                yellow = 1'b1;
                red    = 1'b0;
                green  = 1'b0;
            end
        endcase
    end

endmodule