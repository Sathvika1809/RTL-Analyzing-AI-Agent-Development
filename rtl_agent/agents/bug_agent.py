"""
agents/bug_agent.py
Author: H.Sathvika Date: 02-06-2026
Phase3 - Specialized Bug Analysis Agent
Problem:
 This Agent works on finding bugs,latches,and reser problems
 how to use this:
 from agents.bug_agent import BugAgent
 
 agent = BugAgent()
 result = agent.analyze("path/to/counter.sv)
 print(result["bugs"])

"""

import requests
import json
import os
from pathlib import Path
from datetime import datetime

OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "qwen2.5:3b"

# --------------
# The Bug Focused Prompt
# Very specific - only asks about bugs
# Narrow prompts = better , more focused answers.
# -------------
BUG_ANALYSIS_PROMPT = """ You are a senior RTL verification engineer
specializing in finding hardware bugs in SystemVerilog code.

Analyze the following SystemVerilog module for BUGS ONLY.

Check specifically for:

1. LATCH INFERENCE:
    - Signals assigned inside always_comb or always @(*) without a 
    complete if-else
    - Variables not assigned in all branches
    - Missing default assignments before conditional logic
    
2. RESET PROBLEMS:
    - Flip-flops(always_ff blocks) where signals are not reset
    - Inconsistent reset polarity (mixing active-high and active-low)
    - Signals only reset in some conditions but not others

3. FUNCTIONAL BUGS:
    - Counter overflow not handled
    - Multiple drivers on the same signal
    - Blocking assignments (=) used inside always_ff instead of non-blocking (<=)
    - Race conditions between concurrent always blocks
    
4. WIDTH MISMATCHES:
    - Hardcoded bit widths that don't match parameter sizes
    - Truncation or sign extension issues

IMPORTANT CHECKLIST - Do this before responding:
Step 1: List ALL output signals and variables in every always_comb block.
Step 2: List ALL branches in every case statement and if-else block.
Step 3: For each signal from Step 1, verify it is assigned in EVERY branch from Step 2.
Step 4: If ANY signal is missing from ANY branch - that is a LATCH INFERENCE bug. Report it.
Step 5: Check if there is a default case. If missing - report it as LATCH INFERENCE.

Do this analysis even if the code looks clean and well written.
Keep each response field to 2-3 sentences maximum.

FILE: {filename}

CODE:
{code}

For EACH bug you find, respond in this EXACT format:

BUG #1
Type: [LATCH / RESET / FUNCTIONAL / WIDTH]
Location: [signal name or always_comb block]
Problem: [What is wrong - 2 sentences max]
Impact: [What goes wrong at simulation or silicon - 1 sentence]
Fix: [Exact code change]

If no bugs are found, write: NO BUGS DETECTED

TOTAL BUGS: [number]
SEVERITY: [CRITICAL / HIGH / MEDIUM / LOW]
"""
class BugAgent:
    """ 
    The Bug Analysis Agent

    Usage:
        agent = BugAgent(model="codellama")
        result = agent.analyze("counter.sv")
    """
    def __init__(self,model: str = MODEL_NAME):
        self.model = model
        self.logs_dir = "logs"
        os.makedirs(self.logs_dir, exist_ok=True)
    
    def analyze(self,filepath: str)->dict:
        """
        Analyzes one .sv file for bugs

        Returns a dict:
        {
        "success": True/False,
        "filename": "counter.sv",
        "bugs": [...],     #list of bug dicts
        "total_bugs":3,
        "severity": "HIGH",
        "raw_response":"..."
        }
        """
        path = Path(filepath)

        # Read File
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}
        
        code = path.read_text(encoding="utf-8", errors="replace")
        print(f" Bug agent analyzing: {path.name}")

        # Build Prompt
        prompt = BUG_ANALYSIS_PROMPT.format(
            filename=path.name,
            code=code
        )

        #------Call Ollama ------

        result = self.call_ollama(prompt)

        if not result["success"]:
            return {"success": False,"error": result["error"]}
        
        response_text = result["response"]

        #Parse Response
        #Extract structured bug data from the text response
        parsed = self.parse_bugs(response_text)

        #Log for observations

        self._log(path.name, prompt, response_text, parsed)
        print(f"  Model: {self.model} | Temperature: 0.1\n")
        print(f"  Analyzing for: latches, reset issues, functional bugs, width mismatches")
        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "bugs": parsed["bugs"],
            "total_bugs": parsed["total_bugs"],
            "severity": parsed["severity"],
            "raw_response": response_text,
            "elapsed_s": result["elapsed"]
        }
    def call_ollama(self, prompt: str) -> dict:
        """ Sends prompt to Ollama. Returns success/error dict
        """
        import time
        elapsed = 0
        start = time.time()
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,

                        "num_predict":800
                    }
                },
                timeout=250
            )
            elapsed = time.time()-start

            if resp.status_code!=200:
                return {"success": False, "error": f"HTTP{resp.status_code}", "elapsed": elapsed}
            
            return {
                "success": True,
                "response": resp.json().get("response",""),
                "elapsed": round(elapsed, 1)
            }
        except Exception as e:
            return {"success": False, "error":str(e), "elapsed": elapsed}
        

    def parse_bugs(self, response_text: str) -> dict:
        """
        Extracts structured bug info from the model's text response.

        This is simple text parsing - we look for the "BUG #N" markers
        we told the model to use in the prompt.
        """

        bugs = []
        lines = response_text.split("\n")
        current_bug = None

        for line in lines:
            line = line.strip()

            # Detect start of a new bug block
            if line.startswith("BUG #") or line.startswith("Bug #"):
                if current_bug:
                    bugs.append(current_bug)

                current_bug = {
                    "number": len(bugs) + 1,
                    "type": "",
                    "location": "",
                    "problem": "",
                    "impact": "",
                    "fix": ""
                }

            elif current_bug:
                if line.startswith("Type:"):
                    current_bug["type"] = line.replace("Type:", "").strip()

                elif line.startswith("Location:"):
                    current_bug["location"] = line.replace("Location:", "").strip()

                elif line.startswith("Problem:"):
                    current_bug["problem"] = line.replace("Problem:", "").strip()

                elif line.startswith("Impact:"):
                    current_bug["impact"] = line.replace("Impact:", "").strip()

                elif line.startswith("Fix:"):
                    current_bug["fix"] = line.replace("Fix:", "").strip()

        # Don't forget the last bug
        if current_bug and current_bug.get("problem"):
            bugs.append(current_bug)

        # Extract total bugs and severity from end of response
        total_bugs = len(bugs)
        severity = "UNKNOWN"

        for line in lines:
            if "TOTAL BUGS:" in line:
                try:
                    total_bugs = int(line.split(":")[1].strip())
                except:
                    pass

            if "SEVERITY:" in line and ":" in line:
                sev_part = line.split(":")[1].strip().upper()

                for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                    if s in sev_part:
                        severity = s
                        break

        return {
            "bugs": bugs,
            "total_bugs": total_bugs,
            "severity": severity
        }
    def _log(self, filename: str, prompt: str, response: str, parsed: dict):
        """
        Saves every analysis to a log file.
        This is how you study consistency across multiple runs.
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent":     "bug_agent",
            "model":     self.model,
            "filename":  filename,
            "bugs_found": parsed["total_bugs"],
            "severity":  parsed["severity"],
            "response_length": len(response),
        }
        log_path = os.path.join(self.logs_dir, "bug_agent_log.jsonl")
        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
 
 

# RUN (for testing)
if __name__ == "__main__":
    import sys
 
    filepath = sys.argv[1] if len(sys.argv) > 1 else "sample_rtl/counter.sv"
 
    agent  = BugAgent()
    result = agent.analyze(filepath)
 
    if result["success"]:
        print(f"\n{'='*50}")
        print(f"Bug Analysis: {result['filename']}")
        print(f"{'='*50}")
        print(f"Total bugs found: {result['total_bugs']}")
        print(f"Overall severity: {result['severity']}")
        print(f"\nDetailed findings:")
        print(result["raw_response"])
    else:
        print(f"Error: {result['error']}")


