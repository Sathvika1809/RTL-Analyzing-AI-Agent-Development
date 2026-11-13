"""
run_all_agents.py - batch runner.

The original duplicated src/main.py's CLI logic (and had a different default model).
This is now a thin wrapper so both entry points behave identically.

    python run_all_agents.py --rtl-folder rtl_files --model qwen2.5-coder:7b [--parallel]
"""
import argparse

from src.core.config import DEFAULT_MODEL
from src.main import run_cli_analysis

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Run all RTL agents on a folder or file.")
    p.add_argument("--rtl-folder", default="rtl_files", help="Folder (or single file) to analyze")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name")
    p.add_argument("--parallel", action="store_true", help="Run the four agents in threads")
    a = p.parse_args()
    run_cli_analysis(a.rtl_folder, a.model, parallel=a.parallel)