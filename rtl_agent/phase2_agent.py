"""
phase2_agent.py
Author: H.Sathvika   Date:04-06-2026
Phase 2 - Core RTL Analysis Pipeline

What this does:
- Scans a folder for all .sv files
- Sends each file to a local LLM via Ollama
- Saves a markdown report for each file
- Prints a summary at the end

How to run:
    python phase2_agent.py
"""

import os
import time
import requests
import glob
def build_prompt(code):
    prompt = f"""You are a senior RTL Verification Engineer.
    Analyze ONLY the SystemVerilog code provided below.

    Rules:
    1. Report an issue ONLY if it can be directly observed in the code.
    2. Do NOT suggest generic HDL best practices.
    3. Do NOT recommend timing constraints, clock constraints,
    delays, or synthesis directives unless they are directly
    related to a bug in the code.
    4. Do NOT speculate about missing functionality.
    5. If a parameter, signal, or register is used anywhere in
    the code, do NOT claim it is unused.
    6. For every issue:
    - Quote the exact code snippet.
    - Explain why it is a problem.
    - Explain the RTL consequence.
    7.Do not place style suggestions under BUGS.
    BUGS = functionality, synthesis, simulation, reset,
    latch, CDC, overflow, race-condition, width mismatch.
    BAD PRACTICES = maintainability concerns only.
   
   Output format:

    ## BUGS
    ## BAD PRACTICES
    ## TIMING
    ## FIXES
    For every bug provide:
        LINE:
        CODE:
        ISSUE:
        IMPACT:
        FIX:

    If no issues are found, return:

    ## BUGS
    No RTL bugs found.

    ## BAD PRACTICES
    None.

    ## TIMING
    No timing issues observable from RTL.

    ## FIXES
    None.

    Code to analyze:
    ```systemverilog
    {code}
    ```
    Be specific and explain WHY each issue is a problem. """
    return prompt


def query_ollama(prompt,model):
    """
    Sends prompt to local Ollama server.
    Returns response text or error string.
    """
    print("Sending to model... Please wait\n")
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                "temperature": 0.1,
                "top_p": 0.8
                }
            },
            timeout = 300
        )
        response.raise_for_status()
        return response.json()["response"]
    except Exception as e:
         return f"Error: {e}"



def analyze_file(filepath,model):
    """
    Reads one .sv file and runs LLM analysis on it.
    Returns a dictionary with filename, result, elapsed time.
    """
    start = time.time()
    if not os.path.exists(filepath):
        return {"filename": os.path.basename(filepath),
                "filepath": filepath,
                "model": model,
                "result": "File not found",
                "elapsed": 0}
    with open(filepath, "r") as f:
        code = f.read()
    
    prompt = build_prompt(code)
    result = query_ollama(prompt,model)
    elapsed = time.time()-start
    
    return {
        "filename": os.path.basename(filepath),      # just the filename, not full path
        "filepath": filepath,
        "model": model,
        "result": result,        # the llm output
        "elapsed": elapsed        # time taken
    }

def save_report(result_dict, output_folder):
    """
    Saves analysis result as a markdown file.
    Filename is based on the RTL file name.
    Example: counter.sv -> reports/counter_report.md
    """
    name = os.path.splitext(result_dict["filename"])[0]
   
    report_path = os.path.join(output_folder,name+"_report.md")
     
    with open(report_path, "w") as f:
        f.write(f"# RTL Analysis Report: {result_dict['filename']}\n\n")
        f.write(f"\n\n## Model: {result_dict['model']}\n") 
        f.write(f"Elapsed time: {result_dict['elapsed']:.2f} seconds\n\n")
        f.write("----\n\n");
        f.write(result_dict["result"])

def run_pipeline(filename,output_folder,model):
    """
    Main pipeline function.
    Finds all .sv files, analyzes each one, saves reports.
    """
    start = time.time()
    files = glob.glob(filename+"/*.sv")
    if not files:  # if glob returned empty list, no .sv files found
        print(f"No .sv files found in {filename}")
        return
    os.makedirs(output_folder, exist_ok=True)
    for file in files:
        result = analyze_file(file,model)
        save_report(result,output_folder)
    elapsed =time.time()-start
    print(f"\n--- Pipeline Complete ---")
    print(f"Files analyzed: {len(files)}")
    print(f"Reports saved to: {output_folder}")
    print(f"Total time: {time.time() - start:.2f} seconds")


 
if __name__ == "__main__":
    run_pipeline("rtl_files","reports","qwen2.5:3b")

    