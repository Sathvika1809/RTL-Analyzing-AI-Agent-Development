import os
import re
import shutil
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

Never invent signals, clocks, resets, parameters, or ports that are not present in the RTL.

Return zero assertions ONLY if none of the above are applicable.

====================================================
RTL MODULE
====================================================

Filename:
{filename}

```systemverilog
{code}

"""

# Files at or below this size get the FULL module passed to the LLM with no
# chunking, so it retains cross-block context needed for behavioral
# reasoning (e.g. FIFO full/empty logic spanning multiple always blocks).
SMALL_FILE_CHAR_THRESHOLD = 6000


class AssertionAgent(BaseAgent):
    """
    Specialized agent for generating SystemVerilog Assertions (SVA).

    Both tiers ALWAYS run and their assertions are merged:
      Tier 1: rtl_parser.static_assertions() - deterministic template-based
              RESET / RANGE ($isunknown) assertions.
      Tier 2: Ollama LLM - capable of behavioral assertions.
    
    Syntax validation is executed natively using Icarus Verilog (iverilog).
    """

    def __init__(self, model: str = None):
        super().__init__(agent_name="assertion_agent", model=model)
        self.temp_sva_file = Path(__file__).resolve().parents[2] / "temp_iverilog_sandbox.sv"
        self.max_attempts = 3

    def _compile_via_iverilog(
        self, original_rtl_code: str, assertions: list
    ) -> tuple[bool, str]:
        """
        Assembles RTL + SVA into a temp file and syntax checks it with Icarus Verilog (iverilog).
        SVA is inserted BEFORE endmodule so properties live inside the module scope.
        """
        iverilog_bin = shutil.which("iverilog")
        if not iverilog_bin:
            return False, "TOOLCHAIN_MISSING: 'iverilog' was not found in system PATH."

        sb_content = []
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

        try:
            self.temp_sva_file.write_text("\n".join(sb_content), encoding="utf-8")
            
            # Construct iverilog command (-g2012 enables SystemVerilog features)
            cmd = [iverilog_bin, "-g2012", "-o", os.devnull, str(self.temp_sva_file)]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15
            )
            return result.returncode == 0, result.stderr
        except subprocess.TimeoutExpired:
            return False, "TOOLCHAIN_TIMEOUT: Verification timed out after 15 seconds."
        except Exception as e:
            return False, f"Subprocess error running iverilog: {str(e)}"

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Assertion agent analyzing: {path.name}")

        t_start = time.monotonic()

        meta = extract_declared_identifiers(code)

        # ---- Tier 1: static deterministic assertions (always computed) ----
        static_assertions_list = static_assertions(code)
        for a in static_assertions_list:
            a["source"] = "static"

        # ---- Tier 2: LLM behavioral assertions (always attempted) ----
        comb_only_mode = not meta["clocks"]
        llm_assertions, llm_error, llm_elapsed = self._run_llm_analysis(
            code, path, meta, comb_only_mode
        )

        elapsed = time.monotonic() - t_start

        if llm_error and not static_assertions_list:
            # Only hard-fail if static tier also produced nothing.
            return {"success": False, "error": llm_error}

        # ---- Merge + dedupe ----
        assertions = self._merge_and_dedupe(static_assertions_list, llm_assertions)
        total_assertions = len(assertions)
        coverage = self._compute_coverage(static_assertions_list, llm_assertions)

        raw_response = self._format_markdown_response(assertions, total_assertions, coverage)

        self.log_run(path.name, {
            "assertions_generated": total_assertions,
            "coverage": coverage,
            "static_count": len(static_assertions_list),
            "llm_count": len(llm_assertions),
            "response_length": len(raw_response),
            "source": "merged",
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
            "elapsed_s": elapsed,
        }

    def _run_llm_analysis(self, code: str, path: Path, meta: dict, comb_only_mode: bool):
        """Runs the LLM tier (with iverilog syntax-verification retry loop)
        and returns (assertions, error, elapsed). On failure after all
        retries, returns ([], error_message, elapsed) so the caller can fall
        back to static-only results instead of failing outright.
        """
        if len(code) <= SMALL_FILE_CHAR_THRESHOLD:
            code_ctx = code
        else:
            from src.core.semantic_chunker import chunk_sv, select_relevant_chunks, chunks_to_prompt_text
            chunks = chunk_sv(code)
            selected = select_relevant_chunks(
                chunks,
                query=ASSERTION_ANALYSIS_PROMPT,
                top_k=14,
                max_total_chars=8500,
            )
            code_ctx = chunks_to_prompt_text(selected) if selected else code

        if comb_only_mode:
            comb_prompt = (
                "COMBINATIONAL-MODULE ASSERTION MODE (NO CLOCK)\n"
                "You MUST output immediate assertions only (SystemVerilog `assert (...)`), "
                "suitable for an `always_comb` context. Do NOT output `assert property` "
                "concurrent properties.\n"
                "Each assertion must only reference identifiers declared in the RTL.\n"
            )
            prompt = (
                ASSERTION_ANALYSIS_PROMPT.format(filename=path.name, code=code_ctx)
                + "\n" + comb_prompt
            )
        else:
            prompt = ASSERTION_ANALYSIS_PROMPT.format(filename=path.name, code=code_ctx)

        attempt = 1
        success = False
        final_parsed_json = {}
        elapsed_cumulative = 0.0
        last_compilation_error = ""

        while attempt <= self.max_attempts:
            print(f"    [Icarus Verilog Verification Loop] Attempt {attempt}/{self.max_attempts}")

            result = self.call_ollama(prompt, json_mode=True, max_tokens=800)
            if not result["success"]:
                return [], result["error"], elapsed_cumulative

            elapsed_cumulative += result.get("elapsed", 0.0)
            parsed_json = self.parse_json_response(result["response"])
            parse_error = self.json_parse_error(parsed_json)
            if parse_error:
                return [], parse_error, elapsed_cumulative

            if isinstance(parsed_json, list):
                assertions = parsed_json
            else:
                assertions = parsed_json.get("assertions", []) if isinstance(parsed_json, dict) else []

            # Combinational immediate assertions skip the iverilog round-trip
            # check and go through validate_immediate_assertions_against_rtl below.
            if comb_only_mode:
                final_parsed_json = parsed_json
                success = True
                break

            is_valid_syntax, last_compilation_error = self._compile_via_iverilog(code, assertions)

            if is_valid_syntax:
                print("    SVA syntax verification passed via Icarus Verilog.")
                final_parsed_json = parsed_json
                success = True
                break
            else:
                print("    Icarus Verilog caught syntax errors — retrying with error context.")
                prompt = (
                    f"Your previously generated SVA JSON failed Icarus Verilog compilation.\n\n"
                    f"### Original RTL (only use signals declared here — do NOT invent new ones):\n"
                    f"```systemverilog\n{code}\n```\n\n"
                    f"### Your Previous Broken Output:\n{result['response']}\n\n"
                    f"### Icarus Verilog Errors:\n{last_compilation_error}\n\n"
                    f"Fix the assertions and return valid JSON matching the original schema exactly."
                )
                attempt += 1

        if self.temp_sva_file.exists():
            try:
                self.temp_sva_file.unlink()
            except Exception:
                pass

        if not success:
            return [], f"SVA generation failed all {self.max_attempts} Icarus Verilog attempts.\n{last_compilation_error}", elapsed_cumulative

        if isinstance(final_parsed_json, list):
            assertions = final_parsed_json
        else:
            assertions = final_parsed_json.get("assertions", []) if isinstance(final_parsed_json, dict) else []

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

        for a in assertions:
            if isinstance(a, dict):
                a["source"] = "llm"

        return assertions, None, elapsed_cumulative

    def _merge_and_dedupe(self, static_assertions_list: list, llm_assertions: list) -> list:
        """Merge both tiers, dropping LLM assertions that duplicate a static
        one on the same (type, signal) pair. Static wins on conflicts.
        """
        def key(a):
            return (str(a.get("type", "")).upper(), str(a.get("signal", "")).lower())

        seen = {key(a) for a in static_assertions_list}
        merged = list(static_assertions_list)
        for a in llm_assertions:
            if key(a) not in seen:
                merged.append(a)
                seen.add(key(a))
        return merged

    def _compute_coverage(self, static_assertions_list: list, llm_assertions: list) -> str:
        total = len(static_assertions_list) + len(llm_assertions)
        if total == 0:
            return "LOW"
        if llm_assertions:
            # Behavioral (LLM-derived) coverage present -> higher confidence
            return "HIGH" if len(llm_assertions) >= 2 else "MEDIUM"
        return "MEDIUM"

    def _format_markdown_response(
        self, assertions: list, total_assertions: int, coverage: str
    ) -> str:
        if not assertions:
            return "NO ASSERTIONS GENERATED\n\nTOTAL ASSERTIONS: 0\nCOVERAGE LEVEL: LOW\n"
        md = []
        for i, assertion in enumerate(assertions, 1):
            md.append(f"ASSERTION #{i} [{assertion.get('source', 'unknown')}]")
            md.append(f"Type: {assertion.get('type', 'UNKNOWN')}")
            md.append(f"Signal: {assertion.get('signal', 'UNKNOWN')}")
            md.append(f"SVA Code:\n{assertion.get('sva_code', '')}")
            md.append(f"Description: {assertion.get('description', '')}")
            md.append("")
        md.append(f"TOTAL ASSERTIONS: {total_assertions}")
        md.append(f"COVERAGE LEVEL: {coverage}")
        return "\n".join(md)