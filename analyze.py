import requests
import json
import time
import os
def query_ollama(prompt, model):
    print("Sending to model... Please wait\n")
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False
            },
            timeout = 600
        )
        response.raise_for_status()
        return response.json()["response"]
    except Exception as e:
        return f"Error: {e}"


def analyze_rtl_file(filepath,model):
    start = time.time()
    if not os.path.exists(filepath):
        return f"File {filepath} not found"
    with open(filepath, "r") as f:
        code = f.read()
    
    prompt = f"""You are an expert RTL and SystemVerilog verification engineer
    Analyze ONLY the SystemVerilog code provided below.

    If no issues are found, explicitly state:
    "No RTL bugs found."

    Do not invent signals, modules, or behaviors that are not present in the code.

    Respond in the following format

    1. BUGS: ...
    2. BAD PRACTICES: ...
    3. TIMING: ...
    4. FIXES: ...

    Code to analyze:
    ```systemverilog
    {code}
    ```
    Be specific and explain WHY each issue is a problem. """

    result = query_ollama(prompt,model)
    elapsed = time.time()-start
    print("Elapsed time : ",elapsed)
    with open("docs/phase1_evaluation.md", "a") as f: 
        f.write(f"\n\n## Model: {model}\n")
        f.write(f"Elapsed time: {elapsed:.2f} seconds\n\n")
        f.write(result)
    return result


if __name__ == "__main__":
    print("--- RTL Analysis Agent - Phase 1 ----\n")
    for model in ["mistral", "qwen2.5:3b", "codellama"]:
        print(f"\nTesting model: {model}")
        result = analyze_rtl_file("rtl_files/counter.sv", model)  # pass model in
        print(f"---- {model} Result ----\n")
        print(result)

