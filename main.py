# main.py
import os
import json
from src.parser import scan_and_read_rtl
from src.agents import analyze_rtl_file

def main():
    benchmarks_dir = "./benchmarks"
    
    if not os.path.exists(benchmarks_dir):
        print(f"Creating {benchmarks_dir} directory. Add your .sv files here!")
        os.makedirs(benchmarks_dir)
        return

    print(f"Scanning directory: {benchmarks_dir} ...")
    files_to_analyze = scan_and_read_rtl(benchmarks_dir)
    
    if not files_to_analyze:
        print("No .v or .sv files found to analyze.")
        return

    all_reports = {}
    
    for file_name, data in files_to_analyze.items():
        print(f"\n Analyzing {file_name}...")
        try:
            report = analyze_rtl_file(data["path"], data["content"])
            all_reports[file_name] = report
            print(f" Finished {file_name}. Status: {report.get('overall_status')}")
            print(f"Found {len(report.get('issues', []))} issues.")
        except Exception as e:
            print(f" Failed to analyze {file_name}. Error: {e}")

    # Save the consolidated audit report to disk
    os.makedirs("./reports", exist_ok=True)
    with open("./reports/final_audit_report.json", "w") as f:
        json.dump(all_reports, f, indent=4)
    print("\n Consolidated audit report saved to ./reports/final_audit_report.json")

if __name__ == "__main__":
    main()