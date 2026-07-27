module counter_4bit (
    input wire clk,
    input wire rst,
    input wire enable,
    output reg [3:0] count
);

always @(posedge clk or posedge rst) begin
    if (rst) begin
        count <= 4'b0000;
    end else if (enable) begin
        count <= count + 1'b1; 
    end else begin
        count <= count; 
    end
end

endmodule
