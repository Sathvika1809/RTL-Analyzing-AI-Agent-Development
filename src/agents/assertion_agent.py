import os
import re
import subprocess
from datetime import datetime
import time
from pathlib import Path
from src.core.base_agent import BaseAgent
from src.core.rtl_parser import extract_declared_identifiers, static_assertions, validate_sva_against_rtl, validate_immediate_assertions_against_rtl


ASSERTION_ANALYSIS_PROMPT = """You are a senior RTL Verification Engineer specializing in SystemVerilog Assertions (SVA).

Your task is to analyze the RTL module and generate meaningful, behavior-based SystemVerilog Assertions.

Your goal is NOT to maximize the number of assertions.
Your goal is to verify the actual functionality implemented by the RTL.

====================================================
STEP 1 : UNDERSTAND THE RTL
====================================================

Before generating any assertion, internally analyze the RTL and determine:

• What is the purpose of this module?
• Which signals are inputs?
• Which signals are outputs?
• Which signals are sequential registers?
• Which signals are combinational?
• Which signals control behavior?
• Which signals are clocks?
• Which signals are resets?
• What functionality is implemented?

Do NOT output this reasoning.

====================================================
STEP 2 : IDENTIFY VERIFIABLE BEHAVIOR
====================================================

Based only on the RTL implementation, identify behaviors that should always hold.

Examples include (when applicable):

• Reset behavior
• One-hot or mutual exclusion properties
• Input-output relationships
• State transitions
• Counter limits
• FIFO behavior
• Arbitration correctness
• Handshake protocol correctness
• Pipeline ordering
• Register update behavior
• Memory access legality
• Overflow/underflow protection
• Parameter-dependent constraints
• Combinational output correctness

Do NOT assume functionality that does not exist.

====================================================
STEP 3 : GENERATE ASSERTIONS
====================================================

Generate assertions ONLY for behaviors that can be logically inferred from the RTL.

Prefer behavioral assertions over generic assertions.

Good assertions verify functionality.

Weak assertions merely check unknown values.

Examples of LOW PRIORITY assertions:

• !$isunknown(...)
• Signal width checks
• Constant comparisons without behavioral meaning

Generate these ONLY if no stronger behavioral property exists.

====================================================
STEP 4 : USE ONLY DECLARED SIGNALS
====================================================

Inspect the RTL carefully.

Every identifier appearing anywhere inside the generated assertion MUST already exist in the RTL.

Never invent:

enable
ready
valid
count
state
WIDTH
DEPTH
data
address

or any other identifier.

Use ONLY declared ports, parameters, registers and wires.

====================================================
STEP 5 : RESET HANDLING
====================================================

Automatically determine

• active-high or active-low reset
• synchronous or asynchronous reset

Use the proper

disable iff(...)

condition.

Do not assume reset names.

====================================================
STEP 6 : BEFORE RETURNING ZERO ASSERTIONS
====================================================

Before deciding that no assertions can be generated, you MUST check whether the RTL allows assertions for:

✓ Reset behavior
✓ Sequential registers
✓ Outputs
✓ Combinational logic
✓ Protocol behavior
✓ State transitions
✓ Parameters
✓ Mutual exclusion
✓ Input-output relationships

If at least ONE meaningful behavioral assertion can be derived,
generate it.

Return zero assertions ONLY if none of the above are applicable.

====================================================
RTL MODULE
====================================================

Filename:
{filename}

```systemverilog
{code}

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

        # If the module is combinational-only, allow an LLM fallback to
        # generate *immediate* assertions (not concurrent properties).
        if not meta["clocks"]:
            print(f"  [AssertionAgent] {path.name} has no detected clock — generating combinational immediate assertions via LLM.")
            comb_only_mode = True
        else:
            comb_only_mode = False

        # When no clock is present, we still run the LLM path but require it
        # to emit immediate assertions (not concurrent assert property).
        if comb_only_mode:
            comb_prompt = (
                "COMBINATIONAL-MODULE ASSERTION MODE (NO CLOCK)\n"
                "You MUST output immediate assertions only (SystemVerilog `assert (...)`), "
                "suitable for an `always_comb` context. Do NOT output `assert property` "
                "concurrent properties.\n"
                "Each assertion must only reference identifiers declared in the RTL.\n"
            )
            prompt = ASSERTION_ANALYSIS_PROMPT + "\n" + comb_prompt
        else:
            prompt = None

        # existing LLM path...


        from src.core.semantic_chunker import chunk_sv, select_relevant_chunks, chunks_to_prompt_text

        # Semantic chunking to ground assertions in the most relevant RTL regions.
        chunks = chunk_sv(code)
        selected = select_relevant_chunks(
            chunks,
            query=ASSERTION_ANALYSIS_PROMPT,
            top_k=14,
            max_total_chars=8500,
        )
        code_ctx = chunks_to_prompt_text(selected) if selected else code

        if comb_only_mode:
            prompt = prompt if prompt is not None else (ASSERTION_ANALYSIS_PROMPT.format(filename=path.name, code=code_ctx))
            # append code context after the base prompt, since prompt currently includes comb_prompt
            prompt = prompt + "\n\n" + "```systemverilog\n" + code_ctx + "\n```"
        else:
            prompt = ASSERTION_ANALYSIS_PROMPT.format(filename=path.name, code=code_ctx)


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

        # Evidence-based semantic filtering (anti-hallucination).
        # - Clocked modules: validate concurrent `assert property` via clock/reset evidence.
        # - Combinational-only modules: validate immediate assertions via declared-only token evidence.
        if meta["clocks"]:
            assertions = [
                a for a in assertions
                if isinstance(a, dict) and validate_sva_against_rtl(code, a)
            ]
        else:
            assertions = [
                a for a in assertions
                if isinstance(a, dict) and validate_immediate_assertions_against_rtl(code, a)
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
