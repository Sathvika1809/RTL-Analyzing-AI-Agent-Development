"""
agents/assertion_agent.py
Author: H.Sathvika  Date: 04-06-2026
Phase 3 - Specialized Assertion Generation Agent

What this does:
- Reads a SystemVerilog file
- Generates SVA (SystemVerilog Assertions) for the module
- Returns structured assertion data
- Logs every run for consistency tracking

How to use:
    from agents.assertion_agent import AssertionAgent
    agent = AssertionAgent()
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

ASSERTION_ANALYSIS_PROMPT = """You are a senior RTL verification engineer
specializing in writing SystemVerilog Assertions (SVA).

Analyze the following SystemVerilog module and generate SVA assertions.

Generate ONLY assertions that can be directly inferred
from the RTL.

Do not invent signals.

Do not create assertions for logic not present in code.

Prefer concrete assertions over generic recommendations.
1. RESET BEHAVIOR: After reset, outputs should reach known values
2. SIGNAL RANGES: Outputs should stay within valid bit ranges
3. STATE TRANSITIONS: Valid state changes only
4. OVERFLOW PROTECTION: Counters/accumulators should be checked
5. INPUT VALIDITY: Critical inputs behave as expected

FILE: {filename}

CODE:
{code}

Respond in this EXACT format:

ASSERTION #1
Type: [RESET / RANGE / TRANSITION / OVERFLOW / INPUT]
Signal: [signal name this covers]
SVA Code:
assert property (@(posedge clk) [your assertion here]);
Description: [what this assertion checks]

ASSERTION #2
...

End with:
TOTAL ASSERTIONS: [number]
COVERAGE LEVEL: [HIGH / MEDIUM / LOW]
"""

class AssertionAgent:
    """
    The Assertion Generation Agent.
    Generates SVA assertions for a given SystemVerilog module.

    Usage:
        agent = AssertionAgent(model="mistral")
        result = agent.analyze("rtl_files/counter.sv")
    """

    def __init__(self, model: str = MODEL_NAME):
        self.model = model
        self.logs_dir = "logs"
        os.makedirs(self.logs_dir, exist_ok=True)

    def analyze(self, filepath: str) -> dict:
        """
        Analyzes one .sv file and generates SVA assertions.

        Returns a dict:
        {
             "success": True/False,
            "filename": "counter.sv",
            "assertions": [...],
            "total_assertions": 3,
            "coverage": "MEDIUM",
            "raw_response": "..."
        }
        
        """
        path = Path(filepath)

        # Read file
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")

        print(f"  Assertion agent analyzing: {path.name}")
        print(f"  Generating SVA for: reset, ranges, transitions, overflow")

        # Build prompt
        prompt = ASSERTION_ANALYSIS_PROMPT.format(
            filename=path.name,
            code=code
        )

        # Call Ollama
        result = self.call_ollama(prompt)

        if not result["success"]:
            return {"success": False, "error": result["error"]}

        response_text = result["response"]

        # Parse response
        parsed = self._parse_assertions(response_text)

        # Log for observations
        self._log(path.name, prompt, response_text, parsed)

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "assertions": parsed["assertions"],
            "total_assertions": parsed["total_assertions"],
            "coverage": parsed["coverage"],
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

    def _parse_assertions(self, response_text: str) -> dict:
        """
        Extracts structured assertion data from model response.
        Looks for ASSERTION # markers we told the model to use.
        """
        assertions = []
        lines = response_text.split("\n")

        current_assertion = None
        collecting_sva = False

        for line in lines:
            line = line.strip()

            # Start of a new assertion
            if line.startswith("ASSERTION #") or line.startswith("Assertion #"):

                # Save previous assertion if valid
                if current_assertion and current_assertion.get("signal"):
                    assertions.append(current_assertion)

                current_assertion = {
                    "number": len(assertions) + 1,
                    "type": "",
                    "signal": "",
                    "sva_code": "",
                    "description": ""
                }

                collecting_sva = False

            elif current_assertion:

                if line.startswith("Type:"):
                    current_assertion["type"] = (
                        line.replace("Type:", "").strip()
                    )

                elif line.startswith("Signal:"):
                    current_assertion["signal"] = (
                        line.replace("Signal:", "").strip()
                    )

                elif line.startswith("SVA Code:"):
                    collecting_sva = True

                    current_assertion["sva_code"] = ""

                    sva_line = (
                        line.replace("SVA Code:", "").strip()
                    )

                    if sva_line:
                        current_assertion["sva_code"] += (
                            sva_line + "\n"
                        )

                elif line.startswith("Description:"):
                    collecting_sva = False

                    current_assertion["description"] = (
                        line.replace("Description:", "").strip()
                    )

                elif collecting_sva:
                    current_assertion["sva_code"] += (
                        line + "\n"
                    )

        # Save last assertion
        if current_assertion and current_assertion.get("signal"):
            assertions.append(current_assertion)

        # Remove duplicate assertions
        seen = set()
        unique_assertions = []

        for assertion in assertions:
            key = (
                assertion["type"],
                assertion["signal"],
                assertion["sva_code"].strip()
            )

            if key not in seen:
                seen.add(key)
                unique_assertions.append(assertion)

        assertions = unique_assertions

        # Extract totals and coverage
        total_assertions = len(assertions)
        coverage = "UNKNOWN"

        for line in lines:

            if "TOTAL ASSERTIONS:" in line:
                try:
                    total_assertions = int(
                        line.split(":")[1].strip()
                    )
                except:
                    pass

            if "COVERAGE LEVEL:" in line:
                for level in ["HIGH", "MEDIUM", "LOW"]:
                    if level in line.upper():
                        coverage = level
                        break

        return {
            "assertions": assertions,
            "total_assertions": total_assertions,
            "coverage": coverage
        }

    def _log(self, filename: str, prompt: str, response: str, parsed: dict):
        """
        Saves every analysis run to a log file.
        Used to study consistency across multiple runs.
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": "assertion_agent",
            "model": self.model,
            "filename": filename,
            "assertions_generated": parsed["total_assertions"],
            "coverage": parsed["coverage"],
            "response_length": len(response),
        }
        log_path = os.path.join(self.logs_dir, "assertion_agent_log.jsonl")
        with open(log_path, "a") as f:
            f.write(json.dumps(log_entry) + "\n")


# RUN (for testing)
if __name__ == "__main__":
    import sys

    filepath = sys.argv[1] if len(sys.argv) > 1 else "rtl_files/counter.sv"

    agent = AssertionAgent()
    result = agent.analyze(filepath)

    if result["success"]:
        print(f"\n{'='*50}")
        print(f"Assertion Generation: {result['filename']}")
        print(f"{'='*50}")
        print(f"Total assertions generated: {result['total_assertions']}")
        print(f"Coverage level: {result['coverage']}")
        print(f"Time taken: {result['elapsed_s']}s")
        print(f"\nGenerated SVA:")
        print(result["raw_response"])
    else:
        print(f"Error: {result['error']}")

