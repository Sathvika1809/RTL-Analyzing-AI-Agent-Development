import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent

ASSERTION_ANALYSIS_PROMPT = """You are a senior RTL verification engineer specializing in writing SystemVerilog Assertions (SVA).

Analyze the following SystemVerilog module and generate SVA assertions.

CRITICAL RULES FOR GENERALIZED SVA GENERATION:
1. STRICT VARIABLE BINDING: First, inspect the RTL code and identify the exact names of the clock, reset, and all declared signals. Every variable, signal, parameter, clock, or reset used in your generated SVA code MUST match one of these declared names exactly. Do NOT assume generic signals (like an 'enable' or 'ready' signal) or parameters (like 'WIDTH') if they are not explicitly present in the provided RTL code.
2. SYNTACTIC ACCURACY: Write complete, syntactically correct SVA properties using the declared clock and reset. Ensure correct implication operators (e.g. `|=>` or `|->`) are used.
3. ADAPTIVE RESET BEHAVIOR: Detect whether the reset signal is active-high or active-low, synchronous or asynchronous, and write the reset assertions matching that exact behavior and signal name.
4. If no assertions can be safely generated, you MUST return: {{"declared_clocks_and_resets": [], "declared_signals": [], "assertions": [], "total_assertions": 0, "coverage": "LOW"}}.

Prefer concrete assertions over generic recommendations:
1. RESET BEHAVIOR: After reset, outputs should reach known values
2. SIGNAL RANGES: Outputs should stay within valid bit ranges
3. STATE TRANSITIONS: Valid state changes only (e.g. for FSMs)
4. OVERFLOW PROTECTION: Counters/accumulators should be checked
5. INPUT VALIDITY: Critical inputs behave as expected

RTL Code to analyze (File: {filename}):
```systemverilog
{code}
```

You MUST respond in a VALID JSON format matching the following JSON schema. Do not add any text outside the JSON.

JSON Schema:
{{
  "declared_clocks_and_resets": [
    "exact names of clock and reset signals in the module"
  ],
  "declared_signals": [
    "list of all valid signals declared in the module"
  ],
  "assertions": [
    {{
      "type": "RESET" | "RANGE" | "TRANSITION" | "OVERFLOW" | "INPUT",
      "signal": "exact name of the signal covered",
      "sva_code": "assert property (@(posedge clk) ... );",
      "description": "Clear explanation of what this assertion checks"
    }}
  ],
  "total_assertions": 0,
  "coverage": "HIGH" | "MEDIUM" | "LOW"
}}

If no assertions can be generated, return:
{{
  "declared_clocks_and_resets": [],
  "declared_signals": [],
  "assertions": [],
  "total_assertions": 0,
  "coverage": "LOW"
}}
"""

class AssertionAgent(BaseAgent):
    """
    Specialized agent for generating SystemVerilog Assertions (SVA) based on module design logic.
    """
    def __init__(self, model: str = None):
        super().__init__(agent_name="assertion_agent", model=model)
        self.temp_sva_file = Path(__file__).resolve().parents[2] / "temp_verilator_sandox.sv"
        self.max_attempts = 3
    
    def _to_wsl_path(self, win_path: Path)->str:
        abs_path = str(win_path.resolve()).replace('\\','/')
        match = re.match(r'^([a-zA-Z]):(.*)', abs_path)
        if match:
            drive = match.group(1).lower()
            rest = match.group(2)
            return f"/mnt/{drive}{rest}"
        return abs_path
    
    def _compile_via_wsl_verilator(self, original_rtl_code: str, assertions: list) -> tuple[bool, str]:
        """
        Assembles a validation file containing the user's RTL and the LLM's generated assertions,
        then schedules it against the WSL Verilator package execution subshell.
        """
        # Build standard SystemVerilog testing block combining design and assertions
        sb_content = []
        sb_content.append(original_rtl_code)
        sb_content.append("\n// ====== AUTOMATED AGENT GENERATED SVA PROPERTIES ======")
        for item in assertions:
            sva = item.get("sva_code", "").strip()
            if sva:
                # Append inline assertion checking directly inside or outside module blocks
                if not sva.endswith(";"):
                    sva += ";"
                sb_content.append(sva)
        
        # Flash the text layout into the local Windows hard drive space
        self.temp_sva_file.write_text("\n".join(sb_content), encoding="utf-8")
        
        # Translate file location pointers for the Linux environment shell
        wsl_target_path = self._to_wsl_path(self.temp_sva_file)
        
        try:
            # Command execution crossing the OS bridge via built-in Windows wsl.exe redirection
            result = subprocess.run(
                ["wsl", "verilator", "--lint-only", "-Wall", wsl_target_path],
                capture_output=True,
                text=True,
                shell=True
            )
            return result.returncode == 0, result.stderr
        except Exception as e:
            return False, f"Windows Subprocess error connecting to WSL: {str(e)}"
    

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Assertion agent analyzing: {path.name}")

        prompt = ASSERTION_ANALYSIS_PROMPT.format(
            filename=path.name,
            code=code
        )

        attempt = 1
        success = False
        final_parsed_json = {}
        elapsed_cumulative = 0.0
        last_compilation_error = ""

        attempt = 1
        success = False
        final_parsed_json = {}
        elapsed_cumulative = 0.0
        last_compilation_error = ""

        while attempt <= self.max_attempts:
            print(f"   [Verilator Verification Loop] Attempt {attempt}/{self.max_attempts}")
            
            # Send structured query to Ollama engine
            result = self.call_ollama(prompt, json_mode=True, max_tokens=800)
            if not result["success"]:
                return {"success": False, "error": result["error"]}

            elapsed_cumulative += result.get("elapsed", 0.0)
            parsed_json = self.parse_json_response(result["response"])
            
            # Canonical normalization tracking fields
            if isinstance(parsed_json, list):
                assertions = parsed_json
            else:
                assertions = parsed_json.get("assertions", []) if isinstance(parsed_json, dict) else []

            # Execute validation via WSL Verilator linter
            is_valid_syntax, last_compilation_error = self._compile_via_wsl_verilator(code, assertions)

            if is_valid_syntax:
                print("   ✅ SVA syntax verification passed cleanly via WSL Verilator!")
                final_parsed_json = parsed_json
                success = True
                break
            else:
                print("   ❌ WSL Verilator caught syntax structural anomalies.")
                # Feed the compilation logs *back* into the prompt context for the next loop
                prompt = (
                    f"Your previously generated SVA JSON structure failed Verilator compilation tests.\n\n"
                    f"### Error Diagnostics Encountered:\n{last_compilation_error}\n\n"
                    f"### Target Code to Fix:\n{result['response']}\n\n"
                    f"Modify the code statements, fix any unmapped identifiers, and output a completely corrected JSON object "
                    f"conforming rigidly to the original schema specification."
                )
                attempt += 1

        # Safeguard disk space and eliminate trace workspace components
        if self.temp_sva_file.exists():
            try:
                self.temp_sva_file.unlink()
            except:
                pass

        # If the self-correction loop exhausted all tries without passing syntax check
        if not success:
            return {
                "success": False, 
                "error": f"SVA generation failed compilation checks within loop bounds. Verilator Error:\n{last_compilation_error}"
            }

        # Pull schema properties cleanly out of the verified JSON configuration block
        if isinstance(final_parsed_json, list):
            assertions = final_parsed_json
            total_assertions = len(assertions)
            coverage = "MEDIUM" if assertions else "LOW"
        else:
            assertions = final_parsed_json.get("assertions", []) if isinstance(final_parsed_json, dict) else []
            total_assertions = final_parsed_json.get("total_assertions", len(assertions)) if isinstance(final_parsed_json, dict) else len(assertions)
            coverage = final_parsed_json.get("coverage", "LOW" if not assertions else "MEDIUM") if isinstance(final_parsed_json, dict) else ("LOW" if not assertions else "MEDIUM")

        # Format markdown response output for dashboard generation integration
        raw_response = self._format_markdown_response(assertions, total_assertions, coverage)

        # Log running metrics using BaseAgent hooks
        self.log_run(path.name, {
            "assertions_generated": total_assertions,
            "coverage": coverage,
            "response_length": len(str(final_parsed_json))
        })

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "assertions": assertions,
            "total_assertions": total_assertions,
            "coverage": coverage,
            "raw_response": raw_response,
            "elapsed_s": elapsed_cumulative
        }


    def _format_markdown_response(self, assertions: list, total_assertions: int, coverage: str) -> str:
        if not assertions:
            return "NO ASSERTIONS GENERATED\n\nTOTAL ASSERTIONS: 0\nCOVERAGE LEVEL: LOW\n"

        md = []
        for i, assertion in enumerate(assertions, 1):
            md.append(f"ASSERTION #{i}")
            md.append(f"Type: {assertion.get('type', 'UNKNOWN')}")
            md.append(f"Signal: {assertion.get('signal', 'UNKNOWN')}")
            md.append(f"SVA Code:\n{assertion.get('sva_code', '')}")
            md.append(f"Description: {assertion.get('description', '')}")
            md.append("")

        md.append(f"TOTAL ASSERTIONS: {total_assertions}")
        md.append(f"COVERAGE LEVEL: {coverage}")
        return "\n".join(md)
