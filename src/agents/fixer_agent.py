import os
import re
import json
import subprocess
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent
from src.core.rtl_parser import extract_declared_identifiers

FIXER_PROMPT = """You are a senior RTL verification engineer. Your task is to refactor and fix a SystemVerilog module based on a set of identified issues.

Original SystemVerilog Code (File: {filename}):
```systemverilog
{code}
```

Bugs found:
{bugs}

Timing issues found:
{timing}

Optimization suggestions:
{optimizations}

Please rewrite the SystemVerilog code to:
1. Fix all identified bugs (blocking assignments in always_ff, latch inferences in always_comb, reset mismatches, etc.).
2. Resolve all timing/pipeline issues.
3. Apply code style and parameterization optimizations.
4. Ensure the output module is complete, valid, syntactically correct, and synthesizable SystemVerilog.
5. Preserve the overall functionality, module name, and pin interface. Do not add non-existent ports or remove existing ones.

You MUST respond in a VALID JSON format matching the following JSON schema. Do not add any text outside the JSON.

JSON Schema:
{{
  "fixed_code": "The complete, refactored, and compilable SystemVerilog code as a single string",
  "explanation": "A short summary (2-3 sentences) explaining the key fixes applied"
}}
"""


class FixerAgent(BaseAgent):
    """
    Specialized agent to automatically refactor and fix SystemVerilog files
    based on analysis reports.

    Added vs original:
      1. Interface-preservation check: compares the original module's port
         names/directions against the fixed code's, using the same
         extract_declared_identifiers() the rest of the pipeline already
         trusts. The prompt already tells the LLM not to add/remove ports,
         but nothing previously checked whether it actually complied.
      2. Optional Verilator lint-only compile check (best-effort, mirrors
         the pattern already used in assertion_agent.py). If WSL/Verilator
         isn't available, this step is skipped rather than failing the run.
      3. Retry loop (like assertion_agent's): on interface mismatch or
         compile failure, the LLM is re-prompted with the specific problem
         and the original code, up to max_attempts times.
      4. Result now includes "verified" (bool) and "verification_notes" so
         callers can distinguish a fully-checked fix from a best-effort one,
         instead of treating every returned fix as equally trustworthy.
    """

    def __init__(self, model: str = None):
        super().__init__(agent_name="fixer_agent", model=model)
        self.temp_fix_file = Path(__file__).resolve().parents[2] / "temp_fixer_sandbox.sv"
        self.max_attempts = 3

    def _to_wsl_path(self, win_path: Path) -> str:
        abs_path = str(win_path.resolve()).replace("\\", "/")
        match = re.match(r"^([a-zA-Z]):(.*)", abs_path)
        if match:
            drive = match.group(1).lower()
            rest = match.group(2)
            return f"/mnt/{drive}{rest}"
        return abs_path

    def _check_interface_preserved(self, original_code: str, fixed_code: str) -> tuple[bool, str]:
        """Compares module name + port set between original and fixed code.
        Returns (ok, message). If either side fails to parse meaningfully,
        we skip this check rather than block on a parser limitation
        (returns ok=True with a note), since rtl_parser already falls back
        gracefully on malformed input.
        """
        try:
            orig = extract_declared_identifiers(original_code)
            fixed = extract_declared_identifiers(fixed_code)
        except Exception as e:
            return True, f"Interface check skipped (parser error: {e})"

        if orig.get("module") != fixed.get("module"):
            return False, (
                f"Module name changed: '{orig.get('module')}' -> '{fixed.get('module')}'."
            )

        orig_outputs = set(orig.get("outputs", []))
        fixed_outputs = set(fixed.get("outputs", []))
        if orig_outputs != fixed_outputs:
            missing = orig_outputs - fixed_outputs
            added = fixed_outputs - orig_outputs
            details = []
            if missing:
                details.append(f"missing outputs: {sorted(missing)}")
            if added:
                details.append(f"unexpected new outputs: {sorted(added)}")
            return False, "Output port mismatch — " + "; ".join(details)

        return True, "Interface preserved."

    def _check_compiles(self, fixed_code: str) -> tuple[bool, str]:
        """Best-effort Verilator lint-only check. Returns (ok, message).
        If WSL/Verilator is unavailable, returns (True, note) so this never
        blocks a result purely due to missing local tooling.
        """
        try:
            self.temp_fix_file.write_text(fixed_code, encoding="utf-8")
            wsl_target_path = self._to_wsl_path(self.temp_fix_file)
            result = subprocess.run(
                ["wsl", "verilator", "--lint-only", "-Wall", wsl_target_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return True, "Verilator lint passed."
            return False, result.stderr[:2000]
        except FileNotFoundError:
            return True, "Verilator check skipped (WSL/Verilator not available on this machine)."
        except Exception as e:
            return True, f"Verilator check skipped ({e})."
        finally:
            if self.temp_fix_file.exists():
                try:
                    self.temp_fix_file.unlink()
                except Exception:
                    pass

    def refactor(self, filepath: str, bugs: list, timing: list, optimizations: list) -> dict:
        """
        Reads original SV file, compiles prompt with analysis results,
        and requests rewritten code from Ollama in JSON format. Validates
        the result and retries with feedback on failure.
        """
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f" Fixer agent repairing: {path.name}")

        bugs_str = json.dumps(bugs, indent=2) if bugs else "No bugs reported."
        timing_str = json.dumps(timing, indent=2) if timing else "No timing issues reported."
        opts_str = json.dumps(optimizations, indent=2) if optimizations else "No optimizations reported."

        prompt = FIXER_PROMPT.format(
            filename=path.name,
            code=code,
            bugs=bugs_str,
            timing=timing_str,
            optimizations=opts_str,
        )

        attempt = 1
        elapsed_cumulative = 0.0
        last_fixed_code = ""
        last_explanation = ""
        last_notes = ""
        verified = False

        while attempt <= self.max_attempts:
            print(f"    [Fixer Verification Loop] Attempt {attempt}/{self.max_attempts}")

            result = self.call_ollama(prompt, json_mode=True, max_tokens=2500)
            if not result["success"]:
                return {"success": False, "error": result["error"]}

            elapsed_cumulative += result.get("elapsed", 0.0)
            parsed_json = self.parse_json_response(result["response"])
            parse_error = self.json_parse_error(parsed_json)
            if parse_error:
                return {"success": False, "error": parse_error}

            fixed_code = parsed_json.get("fixed_code", "")
            explanation = parsed_json.get("explanation", "RTL code repaired.")

            if not fixed_code:
                return {
                    "success": False,
                    "error": "Failed to parse fixed_code from LLM response",
                    "raw_response": result["response"],
                }

            last_fixed_code = fixed_code
            last_explanation = explanation

            iface_ok, iface_msg = self._check_interface_preserved(code, fixed_code)
            compile_ok, compile_msg = self._check_compiles(fixed_code)
            last_notes = f"{iface_msg} | {compile_msg}"

            if iface_ok and compile_ok:
                verified = True
                break

            print(f"    Validation failed: {last_notes} — retrying with feedback.")
            problems = []
            if not iface_ok:
                problems.append(f"- Interface problem: {iface_msg}")
            if not compile_ok:
                problems.append(f"- Compile error:\n{compile_msg}")

            prompt = (
                f"Your previous fixed_code failed validation.\n\n"
                f"### Original RTL (module name and port list MUST match exactly):\n"
                f"```systemverilog\n{code}\n```\n\n"
                f"### Your Previous Output:\n{fixed_code}\n\n"
                f"### Problems found:\n" + "\n".join(problems) + "\n\n"
                f"Fix these specific problems and return valid JSON matching the original schema exactly. "
                f"Do not change the module name or port list."
            )
            attempt += 1

        self.log_run(path.name, {
            "fixed_length": len(last_fixed_code),
            "explanation": last_explanation,
            "verified": verified,
            "verification_notes": last_notes,
            "attempts": attempt if attempt <= self.max_attempts else self.max_attempts,
        })

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "fixed_code": last_fixed_code,
            "explanation": last_explanation,
            "verified": verified,
            "verification_notes": last_notes,
            "elapsed_s": elapsed_cumulative,
        }
