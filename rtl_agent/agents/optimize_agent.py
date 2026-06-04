"""
agents/optimizer_agent.py
Author: H.Sathvika  Date: 04-06-2026
Phase 3 - Specialized Code Optimization Agent

What this does:
- Reads a SystemVerilog file
- Suggests code quality improvements and optimizations
- Checks naming, parameters, readability, redundant logic
- Logs every run for consistency tracking

How to use:
    from agents.optimizer_agent import OptimizerAgent
    agent = OptimizerAgent()
    result = agent.analyze("rtl_files/counter.sv")
    print(result["raw_response"])
"""

import requests
import json
import os
from pathlib import Path
from datetime import datetime

OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "mistral"

OPTIMIZER_ANALYSIS_PROMPT = """You are a senior RTL design engineer
specializing in code quality, readability, and optimization.

Analyze the following SystemVerilog module for code quality issues ONLY.
Do NOT report bugs or timing issues - only optimization and style concerns.

Check specifically for:
1. HARDCODED VALUES: Numbers that should be parameters
2. NAMING: Poor signal or module names that reduce readability
3. REDUNDANT LOGIC: Logic that can be simplified or removed
4. MISSING COMMENTS: Complex logic blocks without explanation
5. STYLE: Inconsistent formatting or coding style violations

FILE: {filename}

CODE:
{code}

Respond in this EXACT format:

OPTIMIZATION #1
Type: [HARDCODED / NAMING / REDUNDANT / COMMENT / STYLE]
Location: [signal name or line]
Issue: [what can be improved]
Benefit: [why this improvement matters]
Suggestion: [exact improved code or description]

OPTIMIZATION #2
...

TOTAL OPTIMIZATIONS: [number]
QUALITY SCORE: [HIGH / MEDIUM / LOW] - overall code quality
"""


class OptimizerAgent:
    """
    The Code Optimization Agent.
    Suggests improvements for code quality and readability.

    Usage:
        agent = OptimizerAgent(model="mistral")
        result = agent.analyze("rtl_files/counter.sv")
    """

    def __init__(self, model: str = MODEL_NAME):
        self.model = model
        self.logs_dir = "logs"
        os.makedirs(self.logs_dir, exist_ok=True)

    def analyze(self, filepath: str) -> dict:
        """
        Analyzes one .sv file for optimization opportunities.

        Returns a dict:
        {
            "success": True/False,
            "filename": "counter.sv",
            "optimizations": [...],
            "total_optimizations": 3,
            "quality_score": "MEDIUM",
            "raw_response": "..."
        }
        """
        path = Path(filepath)

        # Read file
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")

        print(f"  Optimizer agent analyzing: {path.name}")
        print(f"  Checking: hardcoded values, naming, redundancy, comments, style")

        # Build prompt
        prompt = OPTIMIZER_ANALYSIS_PROMPT.format(
            filename=path.name,
            code=code
        )

        # Call Ollama
        result = self.call_ollama(prompt)

        if not result["success"]:
            return {"success": False, "error": result["error"]}

        response_text = result["response"]

        # Parse response
        parsed = self._parse_optimizations(response_text)

        # Log for observations
        self._log(path.name, prompt, response_text, parsed)

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "optimizations": parsed["optimizations"],
            "total_optimizations": parsed["total_optimizations"],
            "quality_score": parsed["quality_score"],
            "raw_response": response_text,
            "elapsed_s": result["elapsed"]
        }

    def call_ollama(self, prompt: str) -> dict:
        """
        Sends prompt to Ollama server.
        Returns success/error dict.
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
                        "num_predict": 1500
                    }
                },
                timeout=150
            )
            elapsed = time.time() - start

            if resp.status_code != 200:
                return {"success": False, "error": f"HTTP {resp.status_code}", "elapsed": elapsed}

            return {
                "success": True,
                "response": resp.json().get("response", ""),
                "elapsed": round(elapsed, 1)
            }
        except Exception as e:
            return {"success": False, "error": str(e), "elapsed": elapsed}

    def _parse_optimizations(self, response_text: str) -> dict:
        """
        Extracts structured optimization data from model response.
        Looks for OPTIMIZATION # markers we told the model to use.
        """
        optimizations = []
        lines = response_text.split("\n")
        current_opt = None

        for line in lines:
            line = line.strip()

            # Detect start of a new optimization block
            if line.startswith("OPTIMIZATION #") or line.startswith("Optimization #"):
                if current_opt:
                    optimizations.append(current_opt)
                current_opt = {
                    "number": len(optimizations) + 1,
                    "type": "",
                    "location": "",
                    "issue": "",
                    "benefit": "",
                    "suggestion": ""
                }

            elif current_opt:
                if line.startswith("Type:"):
                    current_opt["type"] = line.replace("Type:", "").strip()
                elif line.startswith("Location:"):
                    current_opt["location"] = line.replace("Location:", "").strip()
                elif line.startswith("Issue:"):
                    current_opt["issue"] = line.replace("Issue:", "").strip()
                elif line.startswith("Benefit:"):
                    current_opt["benefit"] = line.replace("Benefit:", "").strip()
                elif line.startswith("Suggestion:"):
                    current_opt["suggestion"] = line.replace("Suggestion:", "").strip()

        # Don't forget the last optimization
        if current_opt and current_opt.get("issue"):
            optimizations.append(current_opt)

        # Extract totals from end of response
        total_optimizations = len(optimizations)
        quality_score = "UNKNOWN"

        for line in lines:
            if "TOTAL OPTIMIZATIONS:" in line:
                try:
                    total_optimizations = int(line.split(":")[1].strip())
                except:
                    pass
            if "QUALITY SCORE:" in line:
                for q in ["HIGH", "MEDIUM", "LOW"]:
                    if q in line.upper():
                        quality_score = q
                        break

        return {
            "optimizations": optimizations,
            "total_optimizations": total_optimizations,
            "quality_score": quality_score
        }

    def _log(self, filename: str, prompt: str, response: str, parsed: dict):
        """
        Saves every analysis run to a log file.
        Used to study consistency across multiple runs.
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": "optimizer_agent",
            "model": self.model,
            "filename": filename,
            "optimizations_found": parsed["total_optimizations"],
            "quality_score": parsed["quality_score"],
            "response_length": len(response),
        }
        log_path = os.path.join(self.logs_dir, "optimizer_agent_log.jsonl")
        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")


# RUN (for testing)
if __name__ == "__main__":
    import sys

    filepath = sys.argv[1] if len(sys.argv) > 1 else "rtl_files/counter.sv"

    agent = OptimizerAgent()
    result = agent.analyze(filepath)

    if result["success"]:
        print(f"\n{'='*50}")
        print(f"Optimization Analysis: {result['filename']}")
        print(f"{'='*50}")
        print(f"Total optimizations found: {result['total_optimizations']}")
        print(f"Code quality score: {result['quality_score']}")
        print(f"Time taken: {result['elapsed_s']}s")
        print(f"\nSuggestions:")
        print(result["raw_response"])
    else:
        print(f"Error: {result['error']}")

