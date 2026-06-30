import os
import re
import subprocess
from datetime import datetime
import time
from pathlib import Path
from src.core.base_agent import BaseAgent
from src.core.rtl_parser import extract_declared_identifiers, static_assertions, references_only_declared, is_concrete_finding  # ← was rtl_static

ASSERTION_ANALYSIS_PROMPT = """You are a senior RTL verification engineer specializing in writing SystemVerilog Assertions (SVA).

Analyze the following SystemVerilog module and generate SVA assertions.

CRITICAL RULES FOR GENERALIZED SVA GENERATION:
1. STRICT VARIABLE BINDING: First, inspect the RTL code and identify the exact names of the clock, reset, and all declared signals. Every variable, signal, parameter, clock, or reset used in your generated SVA code MUST match one of these declared names exactly. Do NOT assume generic signals (like an 'enable' or 'ready' signal) or parameters (like 'WIDTH') if they are not explicitly present in the provided RTL code.
2. SYNTACTIC ACCURACY: Write complete, syntactically correct SVA properties using the declared clock and reset. Ensure correct implication operators (e.g. `|=>` or `|->`) are used.
3. ADAPTIVE RESET BEHAVIOR: Detect whether the reset signal is active-high or active-low, synchronous or asynchronous, and write the reset assertions matching that exact behavior and signal name.
4. If no assertions can be safely generated, you MUST return: {{"declared_clocks_and_resets": [], "declared_signals": [], "assertions": [], "total_assertions": 0, "coverage": "LOW"}}.
5. SYNTAX RULE: Always use `assert property (@(posedge <clk>) disable iff (<reset_condition>) <property>);`. Never emit bare `(posedge ...) assert` — that is illegal SystemVerilog.

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
      "sva_code": "assert property (@(posedge rd_clk) disable iff (!rd_rst_n) <your_condition>);",
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
    Specialized agent for generating SystemVerilog Assertions (SVA).

    Fixes applied vs original:
      1. SVA code is inserted BEFORE endmodule, not after it.
      2. shell=True removed from subprocess.run (was silently dropping WSL args).
      3. Retry prompt now includes the original RTL so the LLM has context.
      4. Prompt sva_code example uses correct concurrent SVA syntax.
      5. Double comma in JSON schema example removed.
      6. Duplicate variable initialisation block removed.
      7. Comment indentation normalised.
    """

    def __init__(self, model: str = None):
        super().__init__(agent_name="assertion_agent", model=model)
        self.temp_sva_file = Path(__file__).resolve().parents[2] / "temp_verilator_sandbox.sv"
        self.max_attempts  = 3

    def _to_wsl_path(self, win_path: Path) -> str:
        abs_path = str(win_path.resolve()).replace("\\", "/")
        match = re.match(r"^([a-zA-Z]):(.*)", abs_path)
        if match:
            drive = match.group(1).lower()
            rest  = match.group(2)
            return f"/mnt/{drive}{rest}"
        return abs_path

    def _compile_via_wsl_verilator(
        self, original_rtl_code: str, assertions: list
    ) -> tuple[bool, str]:
        """
        Assembles RTL + SVA into a temp file and lints it with WSL Verilator.

        FIX 1: SVA is inserted BEFORE endmodule so properties live inside the
                module scope (the old code appended them after endmodule, which
                is a syntax error for concurrent assertions).

        FIX 2: shell=True removed.  On Windows, subprocess.run with shell=True
                and a list argument passes only the first element to cmd.exe and
                silently drops the rest, meaning Verilator was never actually run.
        """
        sb_content = []

        # Split at endmodule so assertions are placed INSIDE the module scope
        rtl_parts = original_rtl_code.rstrip().rsplit("endmodule", 1)
        sb_content.append(rtl_parts[0])
        sb_content.append("\n// ====== AUTOMATED AGENT GENERATED SVA PROPERTIES ======")
        for item in assertions:
            sva = item.get("sva_code", "").strip()
            if sva:
                if not sva.endswith(";"):
                    sva += ";"
                sb_content.append(sva)
        sb_content.append("\nendmodule")

        # Write assembled content to temp file
        self.temp_sva_file.write_text("\n".join(sb_content), encoding="utf-8")

        # Translate path for WSL
        wsl_target_path = self._to_wsl_path(self.temp_sva_file)

        try:
            # FIX 2: no shell=True — args are passed correctly to WSL
            result = subprocess.run(
                ["wsl", "verilator", "--lint-only", "-Wall", wsl_target_path],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0, result.stderr
        except Exception as e:
            return False, f"Subprocess error connecting to WSL: {str(e)}"

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        ...
        code = path.read_text(encoding="utf-8", errors="replace")
        
        t_start = time.monotonic()   # ← start timing immediately

        meta                     = extract_declared_identifiers(code)
        deterministic_assertions = static_assertions(code)

        # FIX 1: check static assertions BEFORE bailing on missing clock
        if deterministic_assertions:
            elapsed = time.monotonic() - t_start
            total   = len(deterministic_assertions)
            coverage = "MEDIUM" if total else "LOW"
            return {
                "success": True,
                "filename": path.name,
                "filepath": str(path),
                "timestamp": datetime.now().isoformat(),
                "model": self.model,
                "assertions": deterministic_assertions,
                "total_assertions": total,
                "coverage": coverage,
                "raw_response": self._format_markdown_response(deterministic_assertions, total, coverage),
                "elapsed_s": elapsed,
            }

        if not meta["clocks"]:
            
            # Fallback: if clock detection fails, do not ask the LLM to invent
            # clocked assertions; return no assertions.
            immediate = []
            elapsed   = time.monotonic() - t_start
            if immediate:
                return {
                    "success": True,
                    "filename": path.name,
                    "filepath": str(path),
                    "timestamp": datetime.now().isoformat(),
                    "model": self.model,
                    "assertions": immediate,
                    "total_assertions": len(immediate),
                    "coverage": "MEDIUM" if immediate else "LOW",
                    "raw_response": self._format_markdown_response(immediate, len(immediate), "MEDIUM" if immediate else "LOW"),
                    "elapsed_s": elapsed,
                }

            # Genuinely nothing to do — log it clearly
            print(f"  [AssertionAgent] {path.name} is combinational with no static checks — skipping.")
            return {
                "success": True,
                "filename": path.name,
                "filepath": str(path),
                "timestamp": datetime.now().isoformat(),
                "model": self.model,
                "assertions": [],
                "total_assertions": 0,
                "coverage": "LOW",
                "raw_response": self._format_markdown_response([], 0, "LOW"),
                "elapsed_s": elapsed,
            }

        # existing LLM path...

        prompt = ASSERTION_ANALYSIS_PROMPT.format(filename=path.name, code=code)

        # FIX 5: single initialisation block (duplicate removed)
        attempt              = 1
        success              = False
        final_parsed_json    = {}
        elapsed_cumulative   = 0.0
        last_compilation_error = ""

        while attempt <= self.max_attempts:
            print(f"    [Verilator Verification Loop] Attempt {attempt}/{self.max_attempts}")

            result = self.call_ollama(prompt, json_mode=True, max_tokens=800)
            if not result["success"]:
                return {"success": False, "error": result["error"]}

            elapsed_cumulative += result.get("elapsed", 0.0)
            parsed_json = self.parse_json_response(result["response"])
            parse_error = self.json_parse_error(parsed_json)
            if parse_error:
                return {"success": False, "error": parse_error}

            if isinstance(parsed_json, list):
                assertions = parsed_json
            else:
                assertions = parsed_json.get("assertions", []) if isinstance(parsed_json, dict) else []

            is_valid_syntax, last_compilation_error = self._compile_via_wsl_verilator(code, assertions)

            if is_valid_syntax:
                print("    SVA syntax verification passed via WSL Verilator.")
                final_parsed_json = parsed_json
                success = True
                break
            else:
                print("    WSL Verilator caught syntax errors — retrying with error context.")
                # FIX 3: retry prompt includes the original RTL so the LLM
                #         knows which signal names are valid
                prompt = (
                    f"Your previously generated SVA JSON failed Verilator compilation.\n\n"
                    f"### Original RTL (only use signals declared here — do NOT invent new ones):\n"
                    f"```systemverilog\n{code}\n```\n\n"
                    f"### Your Previous Broken Output:\n{result['response']}\n\n"
                    f"### Verilator Errors:\n{last_compilation_error}\n\n"
                    f"Fix the assertions and return valid JSON matching the original schema exactly."
                )
                attempt += 1

        # Clean up temp file
        if self.temp_sva_file.exists():
            try:
                self.temp_sva_file.unlink()
            except Exception:
                pass

        if not success:
            return {
                "success": False,
                "error":   f"SVA generation failed all {self.max_attempts} Verilator attempts.\n{last_compilation_error}",
            }

        if isinstance(final_parsed_json, list):
            assertions       = final_parsed_json
        else:
            assertions       = final_parsed_json.get("assertions", []) if isinstance(final_parsed_json, dict) else []

        # Semantic filtering (anti-hallucination): drop assertions that reference
        # identifiers not declared in this RTL module.
        declared_meta = extract_declared_identifiers(code)
        declared_names = (
            set(declared_meta.get("signals", []))
            | set(declared_meta.get("parameters", []))
            | set(declared_meta.get("clocks", []))
            | set(declared_meta.get("resets", []))
        )

        # references_only_declared() checks identifiers in both `signal` and
        # `sva_code` fields (and filters out known SV keywords).
        from src.core.rtl_parser import references_only_declared, is_concrete_finding
        assertions = [
            a for a in assertions
            if isinstance(a, dict)
            and references_only_declared(a, declared_names)
            and is_concrete_finding(a, declared_names)
        ]

        total_assertions = len(assertions)
        coverage         = "MEDIUM" if assertions else "LOW"

        raw_response = self._format_markdown_response(assertions, total_assertions, coverage)

        self.log_run(path.name, {
            "assertions_generated": total_assertions,
            "coverage":             coverage,
            "response_length":      len(str(final_parsed_json)),
        })

        return {
            "success":          True,
            "filename":         path.name,
            "filepath":         str(path),
            "timestamp":        datetime.now().isoformat(),
            "model":            self.model,
            "assertions":       assertions,
            "total_assertions": total_assertions,
            "coverage":         coverage,
            "raw_response":     raw_response,
            "elapsed_s":        elapsed_cumulative,
        }

    def _format_markdown_response(
        self, assertions: list, total_assertions: int, coverage: str
    ) -> str:
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
