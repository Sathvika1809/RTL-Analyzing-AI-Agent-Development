#!/usr/bin/env python3
"""
phase2_agent.py
===============
Phase 2: Core RTL Analysis Agent

PURPOSE:
    This is the main automation engine. It:
      1. Scans a folder for all .sv (SystemVerilog) files
      2. Reads each file's content
      3. Builds a carefully crafted prompt for the LLM
      4. Calls the Ollama API to get analysis
      5. Parses and structures the response
      6. Saves a markdown report for each file
      7. Creates a final summary report across all files

HOW TO RUN:
    python3 phase2_agent.py                        # analyzes ./sample_rtl/
    python3 phase2_agent.py --folder my_rtl_code   # analyzes a custom folder
    python3 phase2_agent.py --file counter.sv      # analyzes a single file

WHAT YOU NEED:
    - Ollama running (ollama serve)
    - A model pulled (ollama pull codellama)
"""

import os
import json
import time
import argparse           # For --folder and --file command-line flags
import requests
from datetime import datetime
from pathlib import Path   # Modern Python way to handle file paths


# ─────────────────────────────────────────────
# CONFIGURATION
# Edit these to match your setup
# ─────────────────────────────────────────────
OLLAMA_URL      = "http://localhost:11434"
MODEL_NAME      = "codellama"          # Change if you have a different model
REPORTS_DIR     = "reports"            # Where to save the output reports
MAX_FILE_SIZE   = 50_000               # Skip files larger than 50KB (too big for context)
REQUEST_TIMEOUT = 180                  # Seconds to wait for model response


# ─────────────────────────────────────────────
# THE PROMPT TEMPLATE
# This is the most important part of the whole agent.
# A good prompt = good analysis. A vague prompt = vague output.
# ─────────────────────────────────────────────
ANALYSIS_PROMPT_TEMPLATE = """You are an expert RTL (Register Transfer Level) design engineer and verification specialist with 10+ years of experience reviewing SystemVerilog code for ASIC and FPGA designs.

Analyze the following SystemVerilog file named '{filename}' and provide a thorough code review.

═══════════════════════════════
FILE CONTENT:
═══════════════════════════════
{rtl_code}
═══════════════════════════════

Provide your analysis in EXACTLY this structured format (use these exact section headers):

## SUMMARY
Brief 2-3 sentence overview of what this module does and its overall code quality.

## BUGS FOUND
List each bug with:
- Line reference (approximate)
- Description of the bug
- Why it is a problem
- Suggested fix

If no bugs found, write: "No critical bugs detected."

## LATCH INFERENCE RISKS
List any signals that may infer latches due to:
- Incomplete if-else branches
- Signals not assigned in all code paths
- Missing default assignments in always_comb blocks

If none, write: "No latch inference risks detected."

## RESET ISSUES
List any flip-flops or registers that:
- Are not reset
- Have incorrect reset polarity
- Use both synchronous and asynchronous reset inconsistently

## TIMING AND PIPELINE CONCERNS
List any:
- Combinational loops
- Long combinational paths
- Clock domain crossing (CDC) issues
- Signals used across multiple clock domains without synchronizers

## CODE QUALITY ISSUES
List issues with:
- Naming conventions
- Magic numbers (hardcoded values that should be parameters)
- Missing comments on complex logic
- Non-synthesizable constructs

## SUGGESTED SVA ASSERTIONS
Write 3-5 SystemVerilog Assertions (SVA) that should be added to this module to catch bugs during simulation. Format each as:
```systemverilog
// Description of what this assertion checks
assert property (@(posedge clk) ...);
```

## OVERALL RATING
Rate the code: POOR / FAIR / GOOD / EXCELLENT
Justification: One sentence explaining the rating.
"""


# ─────────────────────────────────────────────
# UTILITY: CALL OLLAMA API
# ─────────────────────────────────────────────
def call_ollama(prompt: str, model: str = MODEL_NAME) -> dict:
    """
    Sends a prompt to the Ollama API and returns the full result.

    Returns a dict with:
        'success'  → True/False
        'response' → The text response from the model
        'elapsed'  → How many seconds it took
        'error'    → Error message if something went wrong
    """
    payload = {
        "model":  model,
        "prompt": prompt,
        "stream": False,
        # Optional: tune model behavior
        "options": {
            "temperature": 0.1,    # Low = more deterministic, less creative (better for analysis)
            "top_p":       0.9,    # Nucleus sampling
            "num_predict": 2000,   # Max tokens in response (increase for very detailed output)
        }
    }

    start = time.time()

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=REQUEST_TIMEOUT
        )
        elapsed = time.time() - start

        if response.status_code != 200:
            return {
                "success":  False,
                "response": "",
                "elapsed":  elapsed,
                "error":    f"HTTP {response.status_code}: {response.text[:200]}"
            }

        data = response.json()
        return {
            "success":  True,
            "response": data.get("response", "").strip(),
            "elapsed":  elapsed,
            "error":    None,
            "tokens":   data.get("eval_count", 0)
        }

    except requests.exceptions.ConnectionError:
        return {
            "success":  False,
            "response": "",
            "elapsed":  time.time() - start,
            "error":    "Cannot connect to Ollama. Is it running? (ollama serve)"
        }
    except requests.exceptions.Timeout:
        return {
            "success":  False,
            "response": "",
            "elapsed":  REQUEST_TIMEOUT,
            "error":    f"Request timed out after {REQUEST_TIMEOUT}s. Try a smaller model."
        }
    except Exception as e:
        return {
            "success":  False,
            "response": "",
            "elapsed":  time.time() - start,
            "error":    str(e)
        }


# ─────────────────────────────────────────────
# CORE: ANALYZE A SINGLE RTL FILE
# ─────────────────────────────────────────────
def analyze_file(filepath: Path) -> dict:
    """
    Reads one .sv file, sends it to the LLM, and returns structured results.

    Returns a dict with all the analysis info.
    """
    print(f"\n{'─'*50}")
    print(f" Analyzing: {filepath.name}")
    print(f"{'─'*50}")

    # ── READ THE FILE ──────────────────────────────
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            rtl_code = f.read()
    except Exception as e:
        return {
            "file":    str(filepath),
            "success": False,
            "error":   f"Could not read file: {e}"
        }

    # Check file size - very large files exceed the model's context window
    if len(rtl_code) > MAX_FILE_SIZE:
        print(f"   File too large ({len(rtl_code)} chars). Truncating to {MAX_FILE_SIZE} chars.")
        rtl_code = rtl_code[:MAX_FILE_SIZE] + "\n\n// ... [truncated] ..."

    file_stats = {
        "lines":      rtl_code.count("\n"),
        "characters": len(rtl_code),
        "size_kb":    round(len(rtl_code) / 1024, 1)
    }

    print(f"  File stats: {file_stats['lines']} lines | {file_stats['size_kb']} KB")

    # ── BUILD THE PROMPT ───────────────────────────
    # We insert the filename and code into our template
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        filename=filepath.name,
        rtl_code=rtl_code
    )

    print(f"  Sending to {MODEL_NAME}... (please wait)")

    # ── CALL THE MODEL ─────────────────────────────
    result = call_ollama(prompt)

    if not result["success"]:
        print(f"  Model call failed: {result['error']}")
        return {
            "file":    str(filepath),
            "success": False,
            "error":   result["error"]
        }

    print(f"  Done in {result['elapsed']:.1f}s | {result.get('tokens', '?')} tokens")

    # ── RETURN EVERYTHING ─────────────────────────
    return {
        "file":       str(filepath),
        "filename":   filepath.name,
        "success":    True,
        "timestamp":  datetime.now().isoformat(),
        "model":      MODEL_NAME,
        "stats":      file_stats,
        "elapsed_s":  round(result["elapsed"], 1),
        "tokens":     result.get("tokens", 0),
        "raw_response": result["response"],
        "rtl_content":  rtl_code
    }


# ─────────────────────────────────────────────
# REPORT WRITER: SAVE MARKDOWN REPORT
# ─────────────────────────────────────────────
def save_markdown_report(analysis: dict, output_dir: str = REPORTS_DIR):
    """
    Converts an analysis result into a nicely formatted Markdown file.
    Markdown is great because it's readable as plain text AND
    renders nicely in VSCode, GitHub, Obsidian, etc.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Filename: "counter_analysis.md" for "counter.sv"
    base_name   = Path(analysis["filename"]).stem
    report_path = os.path.join(output_dir, f"{base_name}_analysis.md")

    # Build the markdown content
    md_lines = [
        f"# RTL Analysis Report: `{analysis['filename']}`",
        f"",
        f"| Property | Value |",
        f"|----------|-------|",
        f"| **File** | `{analysis['filename']}` |",
        f"| **Model** | `{analysis['model']}` |",
        f"| **Timestamp** | {analysis['timestamp']} |",
        f"| **Lines** | {analysis['stats']['lines']} |",
        f"| **File size** | {analysis['stats']['size_kb']} KB |",
        f"| **Analysis time** | {analysis['elapsed_s']}s |",
        f"",
        f"---",
        f"",
        f"##  Analysis",
        f"",
        analysis["raw_response"],   # The model's full structured response
        f"",
        f"---",
        f"",
        f"##  Original Source Code",
        f"",
        f"```systemverilog",
        analysis["rtl_content"],
        f"```",
        f"",
        f"---",
        f"*Report generated by RTL Analysis Agent (Phase 2)*"
    ]

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"  Report saved → {report_path}")
    return report_path


# ─────────────────────────────────────────────
# REPORT WRITER: SAVE JSON RESULT (for Phase 3)
# ─────────────────────────────────────────────
def save_json_result(analysis: dict, output_dir: str = REPORTS_DIR):
    """
    Saves the full analysis as JSON.
    Phase 3 agents will read these JSON files to do further specialized analysis.
    """
    os.makedirs(output_dir, exist_ok=True)

    base_name  = Path(analysis["filename"]).stem
    json_path  = os.path.join(output_dir, f"{base_name}_result.json")

    # Don't save the raw RTL content in JSON (it's already in the .md file)
    json_data = {k: v for k, v in analysis.items() if k != "rtl_content"}

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2)

    return json_path


# ─────────────────────────────────────────────
# SUMMARY REPORT: ACROSS ALL FILES
# ─────────────────────────────────────────────
def save_summary_report(all_results: list, output_dir: str = REPORTS_DIR):
    """
    Creates a single summary.md that lists all analyzed files,
    their ratings, and key findings at a glance.
    """
    os.makedirs(output_dir, exist_ok=True)

    summary_path = os.path.join(output_dir, "SUMMARY.md")
    timestamp    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    successful = [r for r in all_results if r.get("success")]
    failed     = [r for r in all_results if not r.get("success")]

    md_lines = [
        f"# RTL Analysis Summary Report",
        f"",
        f"**Generated:** {timestamp}  ",
        f"**Model:** {MODEL_NAME}  ",
        f"**Files analyzed:** {len(successful)} succeeded, {len(failed)} failed",
        f"",
        f"---",
        f"",
        f"## Files Analyzed",
        f"",
    ]

    total_lines  = 0
    total_tokens = 0
    total_time   = 0.0

    for r in successful:
        total_lines  += r["stats"]["lines"]
        total_tokens += r.get("tokens", 0)
        total_time   += r.get("elapsed_s", 0)

        md_lines += [
            f"### `{r['filename']}`",
            f"- Lines: {r['stats']['lines']} | Analysis time: {r['elapsed_s']}s",
            f"",
        ]

        # Extract just the summary section from the response
        response = r.get("raw_response", "")
        if "## SUMMARY" in response:
            start  = response.find("## SUMMARY") + len("## SUMMARY")
            end    = response.find("##", start)
            if end == -1:
                end = start + 400
            summary_text = response[start:end].strip()
            md_lines += [f"> {summary_text[:300]}...", f""]

        # Link to the detailed report
        base_name = Path(r["filename"]).stem
        md_lines += [f" [Full report]({base_name}_analysis.md)", f"", f"---", f""]

    if failed:
        md_lines += [f"##  Failed Files", f""]
        for r in failed:
            md_lines += [f"- `{r['file']}` — {r.get('error', 'Unknown error')}"]
        md_lines += [f""]

    md_lines += [
        f"## Overall Statistics",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total lines analyzed | {total_lines} |",
        f"| Total tokens generated | {total_tokens} |",
        f"| Total analysis time | {total_time:.1f}s |",
        f"| Average time per file | {total_time/max(len(successful),1):.1f}s |",
        f"",
        f"---",
        f"*Generated by RTL Analysis Agent (Phase 2)*"
    ]

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n Summary report saved → {summary_path}")
    return summary_path


# ─────────────────────────────────────────────
# MAIN FUNCTION: SCAN FOLDER OR SINGLE FILE
# ─────────────────────────────────────────────
def run_agent(target_folder: str = None, single_file: str = None):
    """
    Main entry point. Either:
      - Scans a folder for all .sv files and analyzes each one
      - Analyzes a single file if --file is given
    """
    print("=" * 60)
    print("  RTL Analysis Agent — Phase 2")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Ollama: {OLLAMA_URL}")
    print("=" * 60)

    # ── COLLECT FILES TO ANALYZE ──────────────────
    files_to_analyze = []

    if single_file:
        # User specified a single file
        p = Path(single_file)
        if not p.exists():
            print(f" File not found: {single_file}")
            return
        files_to_analyze = [p]

    else:
        # Scan a folder for .sv files
        folder = Path(target_folder or "sample_rtl")
        if not folder.exists():
            print(f" Folder not found: {folder}")
            print(f"   Create the folder and put .sv files in it, or use --file to specify one.")
            return

        # Find all .sv files, including in sub-folders
        files_to_analyze = sorted(folder.rglob("*.sv"))

        if not files_to_analyze:
            print(f" No .sv files found in: {folder}")
            print(f"   Make sure your files have the .sv extension")
            return

    print(f"\n Found {len(files_to_analyze)} file(s) to analyze:")
    for f in files_to_analyze:
        size_kb = round(f.stat().st_size / 1024, 1)
        print(f"   • {f.name} ({size_kb} KB)")

    # ── VERIFY OLLAMA IS AVAILABLE ────────────────
    print(f"\n🔌 Checking Ollama connection...")
    try:
        requests.get(f"{OLLAMA_URL}/", timeout=3)
        print(f"  Connected")
    except:
        print(f"  Cannot reach Ollama at {OLLAMA_URL}")
        print(f"  Run: ollama serve")
        return

    # ── ANALYZE EACH FILE ─────────────────────────
    all_results = []
    report_paths = []

    for i, filepath in enumerate(files_to_analyze, 1):
        print(f"\n[{i}/{len(files_to_analyze)}]", end="")
        result = analyze_file(filepath)
        all_results.append(result)

        if result["success"]:
            md_path   = save_markdown_report(result)
            json_path = save_json_result(result)
            report_paths.append(md_path)
        else:
            print(f"  Skipping report for failed analysis")

        # Small delay between files to avoid hammering the model
        if i < len(files_to_analyze):
            time.sleep(1)

    # ── WRITE SUMMARY ─────────────────────────────
    if len(all_results) > 1:
        save_summary_report(all_results)

    # ── FINAL SUMMARY ─────────────────────────────
    succeeded = sum(1 for r in all_results if r.get("success"))
    print(f"\n{'='*60}")
    print(f" Analysis complete!")
    print(f"   {succeeded}/{len(all_results)} files analyzed successfully")
    print(f"   Reports saved in: {REPORTS_DIR}/")
    print(f"{'='*60}")

    return all_results


# ─────────────────────────────────────────────
# COMMAND LINE INTERFACE
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="RTL Analysis Agent — Phase 2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 phase2_agent.py                          # analyze ./sample_rtl/ folder
  python3 phase2_agent.py --folder my_designs      # analyze custom folder
  python3 phase2_agent.py --file counter.sv        # analyze single file
  python3 phase2_agent.py --model mistral          # use a different model
        """
    )
    parser.add_argument("--folder", type=str, default=None,
                        help="Path to folder containing .sv files")
    parser.add_argument("--file",   type=str, default=None,
                        help="Path to a single .sv file to analyze")
    parser.add_argument("--model",  type=str, default=MODEL_NAME,
                        help=f"Ollama model name (default: {MODEL_NAME})")

    args = parser.parse_args()

    # Override model if user specified one
    if args.model != MODEL_NAME:
        MODEL_NAME = args.model
        print(f"Using model: {MODEL_NAME}")

    run_agent(target_folder=args.folder, single_file=args.file)