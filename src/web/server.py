import os
import glob
import time
import requests
import concurrent.futures
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

# Core Agents
from src.core.config import OLLAMA_URL
from src.agents.bug_agent import BugAgent
from src.agents.timing_agent import TimingAgent
from src.agents.assertion_agent import AssertionAgent
from src.agents.optimize_agent import OptimizerAgent
from src.agents.fixer_agent import FixerAgent
from src.agents.custom_agent import CustomAgent

# Resolve paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RTL_FOLDER = os.path.join(PROJECT_ROOT, "rtl_files")
REPORTS_FOLDER = os.path.join(PROJECT_ROOT, "reports")

app = FastAPI(title="RTL AI Verification Assistant")

# Request Models
class AnalyzeRequest(BaseModel):
    filename: str
    model: str
    parallel: Optional[bool] = False

class FixRequest(BaseModel):
    filename: str
    model: str
    bugs: List[dict]
    timing_issues: List[dict]
    optimizations: List[dict]

class SaveRequest(BaseModel):
    code: str

class CustomQueryRequest(BaseModel):
    filename: str
    model: str
    query: str

class CreateFileRequest(BaseModel):
    filename: str
    code: Optional[str] = ""

# API Endpoints
@app.get("/api/models")
def get_models():
    """Fetches list of models installed locally in Ollama."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            models_data = resp.json().get("models", [])
            model_names = [m["name"] for m in models_data]
            return {"success": True, "models": model_names}
        return {"success": False, "models": [], "error": f"Ollama HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "models": [], "error": str(e)}

@app.get("/api/files")
def list_files():
    """Lists all SystemVerilog/Verilog files in the RTL directory."""
    os.makedirs(RTL_FOLDER, exist_ok=True)
    files = glob.glob(os.path.join(RTL_FOLDER, "*.sv")) + glob.glob(os.path.join(RTL_FOLDER, "*.v"))
    file_names = [os.path.basename(f) for f in files]
    return {"success": True, "files": file_names}

@app.get("/api/file/{filename}")
def read_file(filename: str):
    """Gets the contents of a specific RTL file."""
    filepath = os.path.join(RTL_FOLDER, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return {"success": True, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/file/{filename}")
def save_file(filename: str, request: SaveRequest):
    """Saves updated RTL code back to the file."""
    filepath = os.path.join(RTL_FOLDER, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(request.code)
        return {"success": True, "message": f"Successfully updated {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/file/create")
def create_file(request: CreateFileRequest):
    """Creates a new Verilog/SystemVerilog file."""
    if not request.filename.endswith(".sv") and not request.filename.endswith(".v"):
        raise HTTPException(status_code=400, detail="Filename must end with .sv or .v")
    
    filepath = os.path.join(RTL_FOLDER, request.filename)
    if os.path.exists(filepath):
        raise HTTPException(status_code=400, detail="File already exists")
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(request.code)
        return {"success": True, "message": f"Created {request.filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/file/{filename}")
def delete_file(filename: str):
    """Deletes an RTL file from the folder."""
    filepath = os.path.join(RTL_FOLDER, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        os.remove(filepath)
        return {"success": True, "message": f"Successfully deleted {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze")
def analyze_rtl(request: AnalyzeRequest):
    """Runs sequential or parallel analysis across all 4 specialized agents."""
    filepath = os.path.join(RTL_FOLDER, request.filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    start_time = time.time()
    
    # Initialize agents
    bug_agent = BugAgent(model=request.model)
    timing_agent = TimingAgent(model=request.model)
    assertion_agent = AssertionAgent(model=request.model)
    optimizer_agent = OptimizerAgent(model=request.model)

    print(f"Running analysis on {request.filename} (Mode: {'Parallel' if request.parallel else 'Sequential'}) using model: {request.model}")
    
    if request.parallel:
        # Run in parallel using a ThreadPool
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
        # Run sequentially (safer for CPU-based local Ollama)
        bug_result = bug_agent.analyze(filepath)
        timing_result = timing_agent.analyze(filepath)
        assertion_result = assertion_agent.analyze(filepath)
        optimizer_result = optimizer_agent.analyze(filepath)

    elapsed = time.time() - start_time
    
    # Save combined report in reports directory
    os.makedirs(REPORTS_FOLDER, exist_ok=True)
    report_name = os.path.splitext(request.filename)[0] + "_report.md"
    report_path = os.path.join(REPORTS_FOLDER, report_name)
    
    # Helper to print response or execution errors
    def get_section_content(res, title, default_err):
        if res.get("success"):
            return res.get("raw_response", "")
        else:
            return f"### [ERROR] {title} Agent Execution Failed\n\nReason: {res.get('error', default_err)}\n"

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# RTL Verification Analysis Report: {request.filename}\n\n")
            f.write(f"- **Model Used:** {request.model}\n")
            f.write(f"- **Execution Mode:** {'Parallel' if request.parallel else 'Sequential'}\n")
            f.write(f"- **Execution Time:** {elapsed:.2f} seconds\n\n")
            f.write("---\n\n")
            f.write("## 1. Bug Analysis\n\n")
            f.write(get_section_content(bug_result, "Bug", "Error analyzing bugs."))
            f.write("\n\n---\n\n")
            f.write("## 2. Timing Analysis\n\n")
            f.write(get_section_content(timing_result, "Timing", "Error analyzing timing."))
            f.write("\n\n---\n\n")
            f.write("## 3. Generated Assertions (SVA)\n\n")
            f.write(get_section_content(assertion_result, "Assertion", "Error generating assertions."))
            f.write("\n\n---\n\n")
            f.write("## 4. Code Optimizations\n\n")
            f.write(get_section_content(optimizer_result, "Optimizer", "Error analyzing optimizations."))
    except Exception as e:
        print(f"Warning: Failed to save markdown report: {e}")

    # Build response list with success status checks
    return {
        "success": True,
        "filename": request.filename,
        "elapsed_s": round(elapsed, 2),
        "results": {
            "bugs": bug_result.get("bugs", []) if bug_result.get("success") else [],
            "total_bugs": bug_result.get("total_bugs", 0) if bug_result.get("success") else 0,
            "severity": bug_result.get("severity", "LOW") if bug_result.get("success") else "ERROR",
            "bug_error": None if bug_result.get("success") else bug_result.get("error", "Failed execution"),
            
            "timing_issues": timing_result.get("timing_issues", []) if timing_result.get("success") else [],
            "total_timing_issues": timing_result.get("total_issues", 0) if timing_result.get("success") else 0,
            "risk": timing_result.get("risk", "LOW") if timing_result.get("success") else "ERROR",
            "timing_error": None if timing_result.get("success") else timing_result.get("error", "Failed execution"),
            
            "assertions": assertion_result.get("assertions", []) if assertion_result.get("success") else [],
            "total_assertions": assertion_result.get("total_assertions", 0) if assertion_result.get("success") else 0,
            "coverage": assertion_result.get("coverage", "LOW") if assertion_result.get("success") else "ERROR",
            "assertion_error": None if assertion_result.get("success") else assertion_result.get("error", "Failed execution"),
            
            "optimizations": optimizer_result.get("optimizations", []) if optimizer_result.get("success") else [],
            "total_optimizations": optimizer_result.get("total_optimizations", 0) if optimizer_result.get("success") else 0,
            "quality_score": optimizer_result.get("quality_score", "HIGH") if optimizer_result.get("success") else "ERROR",
            "optimization_error": None if optimizer_result.get("success") else optimizer_result.get("error", "Failed execution"),
        }
    }

@app.post("/api/custom-query")
def custom_query(request: CustomQueryRequest):
    """Addresses a custom prompt about the active SV file using CustomAgent."""
    filepath = os.path.join(RTL_FOLDER, request.filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    agent = CustomAgent(model=request.model)
    res = agent.analyze(filepath, request.query)
    
    if res.get("success"):
        return {
            "success": True,
            "response": res.get("response"),
            "elapsed_s": res.get("elapsed_s")
        }
    else:
        raise HTTPException(status_code=500, detail=res.get("error", "Agent query failed"))

@app.post("/api/fix")
def fix_rtl(request: FixRequest):
    """Calls the FixerAgent to automatically repair code issues."""
    filepath = os.path.join(RTL_FOLDER, request.filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    fixer = FixerAgent(model=request.model)
    res = fixer.refactor(
        filepath=filepath,
        bugs=request.bugs,
        timing=request.timing_issues,
        optimizations=request.optimizations
    )
    
    if res["success"]:
        return {
            "success": True,
            "fixed_code": res["fixed_code"],
            "explanation": res["explanation"],
            "elapsed_s": res["elapsed_s"]
        }
    else:
        raise HTTPException(status_code=500, detail=res.get("error", "Fixer failed"))

# Serve frontend static files
static_dir = os.path.join(PROJECT_ROOT, "src", "web", "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_gui():
    """Serves the main single-page application GUI."""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Welcome to RTL Analysis Assistant. Static web assets are being initialized."}
