import ollama

# Define a snippet of buggy RTL to test the model
rtl_code = """
module bad_mux (
    input logic [1:0] sel,
    input logic a, b, c,
    output logic y
);
    // Intentional bug: Missing case '2'b11' resulting in latch inference
    always_comb begin
        case (sel)
            2'b00: y = a;
            2'b01: y = b;
            2'b10: y = c;
        endcase
    end
endmodule
"""

print("Sending RTL to local Ollama agent...")

response = ollama.chat(
    model='deepseek-coder:6.7b', 
    messages=[
        {
            'role': 'system',
            'content': 'You are an expert RTL design engineer. Analyze the code for hardware flaws like unintended latches.'
        },
        {
            'role': 'user',
            'content': f"Review this code:\n{rtl_code}"
        }
    ]
)

print("\n--- Agent Review ---")
print(response['message']['content'])