import requests
import time
import os
import json
from pathlib import Path
from datetime import datetime
TIMING_ANALYSIS_PROMPT = """You are a senior RTL verification engineer
    specialising in checking timing and pipeline problems
    Analyse the following SystemVerilog code for timings issues ONLY.

    Check specifically for:
    1.Blocking assignments in always_ff blocks
    2.Signals missing from sensitivity lists in always @(*)
    3.Clock domain crossings without synchronizers
    4.Long combinational chains between registers
    5.Incomplete case statements causing latch inference

    FILE: {filename}

    CODE:
    {code}

    Respond in the following format:
    TIMING ISSUE #1
    Type: [BLOCKING / CDC / SENSITIVITY / LATCH / COMBO_PATH]
    Location: [line or signal name]
    Problem: [what is wrong]
    Risk: [what fails at silicon]
    Fix: [exact fix]

    TOTAL TIMING ISSUES: [number]
    RISK LEVEL: [HIGH / MEDIUM / LOW]

    """
OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "mistral"

class TimingAgent:
    def __init__(self, model=MODEL_NAME):
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
        print(f" Timing agent analyzing: {path.name}")

        # Build Prompt
        prompt = TIMING_ANALYSIS_PROMPT.format(
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
        parsed = self.parse_timing(response_text)

        #Log for observations

        self._log(path.name, prompt, response_text, parsed)
        print(f"  Model: {self.model} | Temperature: 0.1\n")
        print(f"  Checking: blocking assignments, CDC, sensitivity lists, latches")
        return {
            "success": True,
            "filename": path.name,
            "model": self.model,
            "timing_issues": parsed["issues"],
            "total_issues": parsed["total_issues"],
            "risk": parsed["risk"],
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

                        "num_predict":1500
                    }
                },
                timeout=150
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
        
    def parse_timing(self, response_text: str) -> dict:
        issues = []
        lines = response_text.split("\n")
        current_issue = None

        for line in lines:
            line = line.strip()
            if line.startswith("TIMING ISSUE #"):
                if current_issue:
                    issues.append(current_issue)
                current_issue = {
                    "number": len(issues) + 1,
                    "type": "",
                    "location": "",
                    "problem": "",
                    "risk": "",
                    "fix": ""
                }
            elif current_issue:
                if line.startswith("Type:"):
                    current_issue["type"] = line.replace("Type:", "").strip()
                elif line.startswith("Location:"):
                    current_issue["location"] = line.replace("Location:", "").strip()
                elif line.startswith("Problem:"):
                    current_issue["problem"] = line.replace("Problem:", "").strip()
                elif line.startswith("Risk:"):
                    current_issue["risk"] = line.replace("Risk:", "").strip()
                elif line.startswith("Fix:"):
                    current_issue["fix"] = line.replace("Fix:", "").strip()

        if current_issue and current_issue.get("problem"):
            issues.append(current_issue)

        total_issues = len(issues)
        risk = "UNKNOWN"

        for line in lines:
            if "TOTAL TIMING ISSUES:" in line:
                try:
                    total_issues = int(line.split(":")[1].strip())
                except:
                    pass
            if "RISK LEVEL:" in line:
                for r in ["HIGH", "MEDIUM", "LOW"]:
                    if r in line.upper():
                        risk = r
                        break

        return {
            "issues": issues,
            "total_issues": total_issues,
            "risk": risk
        }
    
    def _log(self, filename: str, prompt: str, response: str, parsed: dict):
        """
        Saves every analysis to a log file.
        This is how you study consistency across multiple runs.
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent":     "timing_agent",
            "model":     self.model,
            "filename":  filename,
            "issues_found": parsed["total_issues"],
            "severity":  parsed["risk"],
            "response_length": len(response),
        }
        log_path = os.path.join(self.logs_dir, "timing_agent_log.jsonl")
        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
 
 

# RUN (for testing)
if __name__ == "__main__":
    import sys
 
    filepath = sys.argv[1] if len(sys.argv) > 1 else "rtl_files/alu.sv"
 
    agent  = TimingAgent()
    result = agent.analyze(filepath)
 
    if result["success"]:
        print(f"\n{'='*50}")
        print(f"Timing Analysis: {result['filename']}")
        print(f"{'='*50}")
        print(f"Total issues found: {result['total_issues']}")
        print(f"Risk level: {result['risk']}")
        print(f"\nDetailed findings:")
        print(result["raw_response"])
    else:
        print(f"Error: {result['error']}")