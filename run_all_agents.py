"""
run_all_agents.py
Author: H.Sathvika  Date: 04-06-2026
Phase 3 - Master Script

What this does:
- Finds all .sv files in rtl_files/
- Runs all 4 specialized agents on each file
- Combines results into one report per file
- Prints a summary dashboard at the end

How to run:
    python run_all_agents.py
    python run_all_agents.py --parallel
"""

import os
import glob
import time
import argparse
from datetime import datetime
import concurrent.futures

from src.agents.bug_agent import BugAgent
from src.agents.timing_agent import TimingAgent
from src.agents.assertion_agent import AssertionAgent
from src.agents.optimize_agent import OptimizerAgent
from src.core.config import DEFAULT_MODEL



def save_combined_report(filename, bug_result, timing_result,
                          assertion_result, optimizer_result,
                          output_folder):
    """
    Combines all 4 agent results into one markdown report.
    Saves to reports/filename_phase3_report.md
    """
    name = os.path.splitext(filename)[0]
    report_path = os.path.join(output_folder, name + "_phase3_report.md")

    with open(report_path, "w") as f:

        # Header
        f.write(f"# Phase 3 RTL Analysis Report: {filename}\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")

        # Bug Agent Section
        f.write("## Bug Analysis\n\n")
        if bug_result.get("success"):
            f.write(f"**Total bugs found:** {bug_result['total_bugs']}\n")
            f.write(f"**Severity:** {bug_result['severity']}\n")
            f.write(f"**Time taken:** {bug_result['elapsed_s']}s\n\n")
            f.write(bug_result["raw_response"])
        else:
            f.write(f"Error: {bug_result.get('error', 'Unknown error')}\n")
        f.write("\n\n---\n\n")

        # Timing Agent Section
        f.write("## Timing Analysis\n\n")
        if timing_result.get("success"):
            f.write(f"**Total issues found:** {timing_result['total_issues']}\n")
            f.write(f"**Risk level:** {timing_result['risk']}\n")
            f.write(f"**Time taken:** {timing_result['elapsed_s']}s\n\n")
            f.write(timing_result["raw_response"])
        else:
            f.write(f"Error: {timing_result.get('error', 'Unknown error')}\n")
        f.write("\n\n---\n\n")

        # Assertion Agent Section
        f.write("## Generated SVA Assertions\n\n")
        if assertion_result.get("success"):
            f.write(f"**Total assertions generated:** {assertion_result['total_assertions']}\n")
            f.write(f"**Coverage level:** {assertion_result['coverage']}\n")
            f.write(f"**Time taken:** {assertion_result['elapsed_s']}s\n\n")
            f.write(assertion_result["raw_response"])
        else:
            f.write(f"Error: {assertion_result.get('error', 'Unknown error')}\n")
        f.write("\n\n---\n\n")

        # Optimizer Agent Section
        f.write("## Code Optimization Suggestions\n\n")
        if optimizer_result.get("success"):
            f.write(f"**Total suggestions:** {optimizer_result['total_optimizations']}\n")
            f.write(f"**Code quality:** {optimizer_result['quality_score']}\n")
            f.write(f"**Time taken:** {optimizer_result['elapsed_s']}s\n\n")
            f.write(optimizer_result["raw_response"])
        else:
            f.write(f"Error: {optimizer_result.get('error', 'Unknown error')}\n")
        f.write("\n\n---\n\n")

    return report_path


def run_all_agents(rtl_folder="rtl_files",
                   output_folder="reports",
                   model="qwen2.5:3b",
                   parallel=False):
    """
    Main function. Runs all 4 agents on every .sv file.
    """
    model = model if model else DEFAULT_MODEL
    start_total = time.time()

    # Find all RTL files
    files = glob.glob(rtl_folder + "/*.sv")

    if not files:
        print(f"No .sv files found in {rtl_folder}/")
        return

    # Create output folder
    os.makedirs(output_folder, exist_ok=True)

    # Initialize all 4 agents once
    print("Initializing agents...")
    bug_agent       = BugAgent(model=model)
    timing_agent    = TimingAgent(model=model)
    assertion_agent = AssertionAgent(model=model)
    optimizer_agent = OptimizerAgent(model=model)

    print(f"Model: {model}")
    print(f"Execution mode: {'Parallel' if parallel else 'Sequential'}")
    print(f"Files to analyze: {len(files)}\n")
    print("=" * 50)

    # Summary tracking
    summary = []

    # Process each file
    for filepath in files:
        filename = os.path.basename(filepath)
        print(f"\nAnalyzing: {filename}")
        print("-" * 40)

        file_start = time.time()

        if parallel:
            # Run all 4 agents in parallel.
            # This is faster on strong hardware, but can overload local Ollama.
            print("Running all 4 specialized agents in parallel...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                bug_future = executor.submit(bug_agent.analyze, filepath)
                timing_future = executor.submit(timing_agent.analyze, filepath)
                assertion_future = executor.submit(assertion_agent.analyze, filepath)
                optimizer_future = executor.submit(optimizer_agent.analyze, filepath)

                try:
                    bug_result = bug_future.result()
                except Exception as e:
                    bug_result = {"success": False, "error": f"Exception in agent thread: {str(e)}"}

                try:
                    timing_result = timing_future.result()
                except Exception as e:
                    timing_result = {"success": False, "error": f"Exception in agent thread: {str(e)}"}

                try:
                    assertion_result = assertion_future.result()
                except Exception as e:
                    assertion_result = {"success": False, "error": f"Exception in agent thread: {str(e)}"}

                try:
                    optimizer_result = optimizer_future.result()
                except Exception as e:
                    optimizer_result = {"success": False, "error": f"Exception in agent thread: {str(e)}"}
        else:
            # Run agents sequentially to avoid timeout/resource contention.
            print("Running all 4 specialized agents sequentially...")
            try:
                bug_result = bug_agent.analyze(filepath)
            except Exception as e:
                bug_result = {"success": False, "error": f"Exception in BugAgent: {str(e)}"}

            try:
                timing_result = timing_agent.analyze(filepath)
            except Exception as e:
                timing_result = {"success": False, "error": f"Exception in TimingAgent: {str(e)}"}

            try:
                assertion_result = assertion_agent.analyze(filepath)
            except Exception as e:
                assertion_result = {"success": False, "error": f"Exception in AssertionAgent: {str(e)}"}

            try:
                optimizer_result = optimizer_agent.analyze(filepath)
            except Exception as e:
                optimizer_result = {"success": False, "error": f"Exception in OptimizerAgent: {str(e)}"}

        # Save combined report
        report_path = save_combined_report(
            filename,
            bug_result,
            timing_result,
            assertion_result,
            optimizer_result,
            output_folder
        )

        file_elapsed = time.time() - file_start

        # Track summary
        summary.append({
            "filename": filename,
            "bugs": bug_result.get("total_bugs", "N/A") if bug_result.get("success") else "ERR",
            "severity": bug_result.get("severity", "N/A") if bug_result.get("success") else "ERR",
            "timing_issues": timing_result.get("total_issues", "N/A") if timing_result.get("success") else "ERR",
            "risk": timing_result.get("risk", "N/A") if timing_result.get("success") else "ERR",
            "assertions": assertion_result.get("total_assertions", "N/A") if assertion_result.get("success") else "ERR",
            "optimizations": optimizer_result.get("total_optimizations", "N/A") if optimizer_result.get("success") else "ERR",
            "elapsed": round(file_elapsed, 1)
        })

        print(f"Report saved: {report_path}")
        print(f"File analysis time: {file_elapsed:.1f}s")

    # Print summary dashboard
    total_elapsed = time.time() - start_total
    print(f"\n{'='*60}")
    print(f"PHASE 3 ANALYSIS COMPLETE")
    print(f"{'='*60}")
    print(f"{'File':<15} {'Bugs':<6} {'Severity':<10} {'Timing':<8} {'Risk':<8} {'SVA':<6} {'Opts':<6} {'Time'}")
    print(f"{'-'*60}")
    for s in summary:
        print(f"{s['filename']:<15} {str(s['bugs']):<6} {s['severity']:<10} "
              f"{str(s['timing_issues']):<8} {s['risk']:<8} "
              f"{str(s['assertions']):<6} {str(s['optimizations']):<6} {s['elapsed']}s")
    print(f"{'-'*60}")
    print(f"Total files: {len(files)}")
    print(f"Total time: {total_elapsed:.1f}s")
    print(f"Reports saved to: {output_folder}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 3 RTL agents on all RTL files.")
    parser.add_argument("--rtl-folder", default="rtl_files", help="Folder containing .sv files")
    parser.add_argument("--output-folder", default="reports", help="Folder for generated reports")
    parser.add_argument("--model", default="qwen2.5:3b", help="Ollama model name")
    parser.add_argument("--parallel", action="store_true", help="Run agents in parallel. Faster, but may timeout on local CPU.")
    args = parser.parse_args()

    run_all_agents(
        rtl_folder=args.rtl_folder,
        output_folder=args.output_folder,
        model=args.model,
        parallel=args.parallel
    )
