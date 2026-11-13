import os
import re
import glob
import time
import concurrent.futures
from typing import List, Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.core.config import OLLAMA_URL, DEFAULT_MODEL
from src.agents.bug_agent import BugAgent
from src.agents.timing_agent import TimingAgent
from src.agents.assertion_agent import AssertionAgent
from src.agents.optimize_agent import OptimizerAgent
from src.agents.fixer_agent import FixerAgent
from src.agents.custom_agent import CustomAgent

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RTL_FOLDER = os.path.join(PROJECT_ROOT, "rtl_files")
REPORTS_FOLDER = os.path.join(PROJECT_ROOT, "reports")

app = FastAPI(title="RTL AI Verification Assistant")

# Only plain file names, no directories: blocks "../../etc/passwd" style paths.
SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-]+\.(sv|v)$")


def rtl_path(filename: str) -> str:
    if not SAFE_NAME.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename (use letters, digits, _ or -, ending in .sv or .v)")
    return os.path.join(RTL_FOLDER, filename)


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


@app.get("/api/models")
def get_models():
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            names = [m["name"] for m in resp.json().get("models", [])]
            return {"success": True, "models": names, "default": DEFAULT_MODEL}
        return {"success": False, "models": [], "default": DEFAULT_MODEL, "error": f"Ollama HTTP {resp.status_code}"}
    except Exception as e:  # noqa: BLE001
        return {"success": False, "models": [], "default": DEFAULT_MODEL, "error": str(e)}


@app.get("/api/files")
def list_files():
    os.makedirs(RTL_FOLDER, exist_ok=True)
    files = glob.glob(os.path.join(RTL_FOLDER, "*.sv")) + glob.glob(os.path.join(RTL_FOLDER, "*.v"))
    return {"success": True, "files": sorted(os.path.basename(f) for f in files)}


# NOTE: the literal "/api/file/create" route MUST be declared before "/api/file/{filename}".
# In the original it came after, so POST /api/file/create was captured by the {filename}
# route (filename="create") and failed with a 422 validation error.
@app.post("/api/file/create")
def create_file(request: CreateFileRequest):
    filepath = rtl_path(request.filename)
    if os.path.exists(filepath):
        raise HTTPException(status_code=400, detail="File already exists")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(request.code or "")
        return {"success": True, "message": f"Created {request.filename}"}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/file/{filename}")
def read_file(filename: str):
    filepath = rtl_path(filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return {"success": True, "content": f.read()}


@app.post("/api/file/{filename}")
def save_file(filename: str, request: SaveRequest):
    filepath = rtl_path(filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(request.code)
        return {"success": True, "message": f"Updated {filename}"}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/file/{filename}")
def delete_file(filename: str):
    filepath = rtl_path(filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(filepath)
    return {"success": True, "message": f"Deleted {filename}"}


def _run_agents(filepath: str, model: str, parallel: bool):
    agents = [BugAgent(model=model), TimingAgent(model=model),
              AssertionAgent(model=model), OptimizerAgent(model=model)]

    def safe(agent):
        try:
            return agent.analyze(filepath)
        except Exception as e:  # noqa: BLE001
            return {"success": False, "error": f"Exception in {type(agent).__name__}: {e}"}

    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            return [f.result() for f in [ex.submit(safe, a) for a in agents]]
    return [safe(a) for a in agents]


def _section(res, title):
    if res.get("success"):
        return res.get("raw_response", "")
    return f"### [ERROR] {title} agent failed\n\nReason: {res.get('error', 'unknown')}\n"


@app.post("/api/analyze")
def analyze_rtl(request: AnalyzeRequest):
    filepath = rtl_path(request.filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    start = time.time()
    print(f"Analyzing {request.filename} ({'parallel' if request.parallel else 'sequential'}) with {request.model}")
    bug, timing, sva, opt = _run_agents(filepath, request.model, bool(request.parallel))
    elapsed = time.time() - start

    os.makedirs(REPORTS_FOLDER, exist_ok=True)
    report = os.path.join(REPORTS_FOLDER, os.path.splitext(request.filename)[0] + "_report.md")
    try:
        with open(report, "w", encoding="utf-8") as f:
            f.write(f"# RTL Verification Analysis Report: {request.filename}\n\n"
                    f"- **Model:** {request.model}\n- **Mode:** {'Parallel' if request.parallel else 'Sequential'}\n"
                    f"- **Time:** {elapsed:.2f}s\n\n---\n\n")
            for n, (title, res) in enumerate([("Bug", bug), ("Timing", timing), ("Assertion", sva), ("Optimizer", opt)], 1):
                f.write(f"## {n}. {title}\n\n{_section(res, title)}\n\n---\n\n")
    except Exception as e:  # noqa: BLE001
        print(f"Warning: could not save report: {e}")

    def err(res):
        return None if res.get("success") else res.get("error", "Failed execution")

    ok = lambda r: r.get("success")  # noqa: E731
    return {
        "success": True,
        "filename": request.filename,
        "elapsed_s": round(elapsed, 2),
        "results": {
            "bugs": bug.get("bugs", []) if ok(bug) else [],
            "total_bugs": bug.get("total_bugs", 0) if ok(bug) else 0,
            "severity": bug.get("severity", "LOW") if ok(bug) else "ERROR",
            "bug_error": err(bug),
            "timing_issues": timing.get("timing_issues", []) if ok(timing) else [],
            "total_timing_issues": timing.get("total_issues", 0) if ok(timing) else 0,
            "risk": timing.get("risk", "LOW") if ok(timing) else "ERROR",
            "timing_error": err(timing),
            "assertions": sva.get("assertions", []) if ok(sva) else [],
            "total_assertions": sva.get("total_assertions", 0) if ok(sva) else 0,
            "coverage": sva.get("coverage", "LOW") if ok(sva) else "ERROR",
            "assertion_error": err(sva),
            "optimizations": opt.get("optimizations", []) if ok(opt) else [],
            "total_optimizations": opt.get("total_optimizations", 0) if ok(opt) else 0,
            "quality_score": opt.get("quality_score", "HIGH") if ok(opt) else "ERROR",
            "optimization_error": err(opt),
            # Why the LLM tier returned what it did (kept / rejected-by-reason) per agent.
            "llm_stats": {"bug": bug.get("llm_stats"), "timing": timing.get("llm_stats"),
                          "assertion": sva.get("llm_stats"), "optimizer": opt.get("llm_stats")},
        },
    }


@app.post("/api/custom-query")
def custom_query(request: CustomQueryRequest):
    filepath = rtl_path(request.filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    res = CustomAgent(model=request.model).analyze(filepath, request.query)
    if res.get("success"):
        return {"success": True, "response": res.get("response"), "elapsed_s": res.get("elapsed_s")}
    raise HTTPException(status_code=500, detail=res.get("error", "Agent query failed"))


@app.post("/api/fix")
def fix_rtl(request: FixRequest):
    filepath = rtl_path(request.filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    res = FixerAgent(model=request.model).refactor(
        filepath=filepath, bugs=request.bugs,
        timing=request.timing_issues, optimizations=request.optimizations)
    if res["success"]:
        return {"success": True, "fixed_code": res["fixed_code"], "explanation": res["explanation"],
                "verified": res.get("verified", False), "verification_notes": res.get("verification_notes", ""),
                "elapsed_s": res["elapsed_s"]}
    raise HTTPException(status_code=500, detail=res.get("error", "Fixer failed"))


static_dir = os.path.join(PROJECT_ROOT, "src", "web", "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def serve_gui():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "RTL Analysis Assistant: static assets not found."}