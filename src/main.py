import os
import sys
import glob
import time
import argparse
import concurrent.futures
from datetime import datetime

# Add root project path to system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.config import DEFAULT_MODEL
from src.agents.bug_agent import BugAgent
from src.agents.timing_agent import TimingAgent
from src.agents.assertion_agent import AssertionAgent
from src.agents.optimize_agent import OptimizerAgent

def run_cli_analysis(file_path: str, model: str, parallel: bool = False):
    """Runs parallel or sequential multi-agent analysis on a file or folder and prints CLI reports."""
    # Resolve files
    if os.path.isdir(file_path):
        files = glob.glob(os.path.join(file_path, "*.sv")) + glob.glob(os.path.join(file_path, "*.v"))
    else:
        files = [file_path] if os.path.exists(file_path) else []

    if not files:
        print(f"Error: No SystemVerilog/Verilog (*.sv, *.v) files found at '{file_path}'")
        return

    print("=" * 80)
    print(f"🌟 RTL MULTI-AGENT COMPILER & VERIFIER - MODEL: {model}")
    print(f"⚙️  Execution Scheme: {'Parallel Threads' if parallel else 'Sequential Pipeline'}")
    print("=" * 80)

    # Initialize agents
    bug_agent = BugAgent(model=model)
    timing_agent = TimingAgent(model=model)
    assertion_agent = AssertionAgent(model=model)
    optimizer_agent = OptimizerAgent(model=model)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reports_dir = os.path.join(project_root, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    summary = []
    start_total = time.time()

    for path in files:
        filename = os.path.basename(path)
        print(f"\nAnalyzing: {filename}...")
        print("-" * 50)
        
        file_start = time.time()

        if parallel:
            # Run agents in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                bug_future = executor.submit(bug_agent.analyze, path)
                timing_future = executor.submit(timing_agent.analyze, path)
                assertion_future = executor.submit(assertion_agent.analyze, path)
                optimizer_future = executor.submit(optimizer_agent.analyze, path)

                try:
                    bug_res = bug_future.result()
                except Exception as e:
                    bug_res = {"success": False, "error": f"Exception in agent thread: {str(e)}"}
                    
                try:
                    timing_res = timing_future.result()
                except Exception as e:
                    timing_res = {"success": False, "error": f"Exception in agent thread: {str(e)}"}
                    
                try:
                    assertion_res = assertion_future.result()
                except Exception as e:
                    assertion_res = {"success": False, "error": f"Exception in agent thread: {str(e)}"}
                    
                try:
                    optimizer_res = optimizer_future.result()
                except Exception as e:
                    optimizer_res = {"success": False, "error": f"Exception in agent thread: {str(e)}"}

        else:
            # Run agents sequentially
            bug_res = bug_agent.analyze(path)
            timing_res = timing_agent.analyze(path)
            assertion_res = assertion_agent.analyze(path)
            optimizer_res = optimizer_agent.analyze(path)

        file_elapsed = time.time() - file_start

        # Check success and capture errors
        def get_section_content(res, title, default_err):
            if res.get("success"):
                return res.get("raw_response", "No output returned.")
            else:
                return f"### [ERROR] {title} Agent Execution Failed\n\nReason: {res.get('error', default_err)}\n"

        # Save markdown report
        report_name = os.path.splitext(filename)[0] + "_cli_report.md"
        report_path = os.path.join(reports_dir, report_name)
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Phase 3 RTL CLI Report: {filename}\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Model:** {model}\n")
            f.write(f"**Execution Mode:** {'Parallel' if parallel else 'Sequential'}\n")
            f.write(f"**Time Taken:** {file_elapsed:.1f}s\n\n")
            f.write("---\n\n")
            f.write("## Bug Analysis\n\n")
            f.write(get_section_content(bug_res, "Bug", "Unknown error analyzing bugs."))
            f.write("\n\n---\n\n")
            f.write("## Timing Analysis\n\n")
            f.write(get_section_content(timing_res, "Timing", "Unknown error analyzing timing."))
            f.write("\n\n---\n\n")
            f.write("## Generated SVA Assertions\n\n")
            f.write(get_section_content(assertion_res, "Assertion", "Unknown error generating assertions."))
            f.write("\n\n---\n\n")
            f.write("## Code Optimization Suggestions\n\n")
            f.write(get_section_content(optimizer_res, "Optimizer", "Unknown error analyzing optimizations."))
            f.write("\n\n---\n\n")

        print(f"Report written to: {report_path}")
        
        # Track summary statistics
        summary.append({
            "filename": filename,
            "bugs": bug_res.get("total_bugs", 0) if bug_res.get("success") else "ERR",
            "severity": bug_res.get("severity", "LOW") if bug_res.get("success") else "ERR",
            "timing": timing_res.get("total_issues", 0) if timing_res.get("success") else "ERR",
            "risk": timing_res.get("risk", "LOW") if timing_res.get("success") else "ERR",
            "sva": assertion_res.get("total_assertions", 0) if assertion_res.get("success") else "ERR",
            "opts": optimizer_res.get("total_optimizations", 0) if optimizer_res.get("success") else "ERR",
            "time": round(file_elapsed, 1)
        })

    # Print summary dashboard to console
    total_elapsed = time.time() - start_total
    print(f"\n{'='*82}")
    print(f"📊 SUMMARY REPORT METRICS DASHBOARD")
    print(f"{'='*82}")
    print(f"{'RTL Design File':<22} {'Bugs':<6} {'Severity':<10} {'Timing':<8} {'Risk':<8} {'SVA':<6} {'Opts':<6} {'Time'}")
    print(f"{'-'*82}")
    for s in summary:
        print(f"{s['filename']:<22} {str(s['bugs']):<6} {str(s['severity']):<10} "
              f"{str(s['timing']):<8} {str(s['risk']):<8} "
              f"{str(s['sva']):<6} {str(s['opts']):<6} {s['time']}s")
    print(f"{'-'*82}")
    print(f"Total Files: {len(files)} | Total Time: {total_elapsed:.1f}s")
    print(f"All reports saved to: {reports_dir}/\n")

def main():
    parser = argparse.ArgumentParser(description="RTL AI Verification & Analysis Assistant")
    parser.add_argument("--web", action="store_true", help="Launch the interactive web dashboard server (default)")
    parser.add_argument("--cli", action="store_true", help="Run verification check via command line interface")
    parser.add_argument("--file", type=str, default="rtl_files", help="RTL file or directory path for CLI analysis")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Local Ollama model to use for analysis")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host address for Web Server")
    parser.add_argument("--port", type=int, default=8000, help="Port address for Web Server")
    parser.add_argument("--parallel", action="store_true", help="Run verification checks in parallel (higher resources/timeout risk)")
    
    args = parser.parse_args()

    # Default to web mode if neither is specified
    if not args.web and not args.cli:
        args.web = True

    if args.cli:
        run_cli_analysis(args.file, args.model, parallel=args.parallel)
    elif args.web:
        import uvicorn
        print("=" * 60)
        print(f"Starting RTL AI verification server on http://{args.host}:{args.port}")
        print("=" * 60)
        uvicorn.run("src.web.server:app", host=args.host, port=args.port, reload=True)

if __name__ == "__main__":
    main()
