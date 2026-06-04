// counter.sv
// Parameterized up-counter with load and enable
// Contains intentional bugs for agent testing

module counter #(
    parameter WIDTH = 8
)(
    input  logic             clk,
    input  logic             rst_n,
    input  logic             en,
    input  logic             load,
    input  logic [WIDTH-1:0] load_val,
    output logic [WIDTH-1:0] count,
    output logic             overflow
);

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            count <= '0;
            // BUG 1: overflow not reset → undefined initial state
        end else if (en) begin
            if (load) begin
                count <= load_val;
            end else begin
                count <= count + 1;
            end
        end

        // BUG 2: overflow is inside always_ff but has no else
        // When count != MAX, overflow is never cleared → LATCH
        if (count == {WIDTH{1'b1}})
            overflow <= 1'b1;
    end

    // BUG 3: no assertions for overflow behavior
    // BUG 4: load and en can conflict — no priority documentation

endmodule