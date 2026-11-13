"""
src/core/pipeline.py - project-level runner (scales to many modules / thousands of lines).

    python -m src.core.pipeline rtl_files --model qwen2.5-coder:7b
    python -m src.core.pipeline rtl_files --static-only          # seconds, no LLM
    python -m src.core.pipeline big_design/ --agents bug,assertion --no-cache

What it does differently from running the agents on whole files:
  * one analysis unit per MODULE (project_scan), so every prompt stays small and the
    semantic chunker is rarely needed;
  * modules are processed leaves first; each module's prompt carries the port lists
    of the modules it instantiates (as comments - comments are never accepted as
    evidence), instead of their bodies;
  * results are cached by hash of (model, agent, module text, child interfaces,
    source fingerprint of the analysis code), so a re-run only analyses what changed;
  * reported line numbers are mapped back to the ORIGINAL file.

Agents are used unchanged (agent.analyze(path) -> dict). For tests, pass your own
`agent_factories` to analyze_project().
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from src.core.project_scan import (ResultCache, ModuleUnit, bottom_up_order,
                                   interface_summary, scan_project)

ROOT = Path(__file__).resolve().parents[2]
AGENT_KEYS = {          # agent -> (result key holding the item list, report title)
    "bug": ("bugs", "Bugs"),
    "timing": ("timing_issues", "Timing"),
    "assertion": ("assertions", "Assertions"),
    "optimizer": ("optimizations", "Optimizations"),
}
_FP_FILES = ["src/core/rtl_parser.py", "src/core/evidence.py", "src/core/base_agent.py",
             "src/agents/bug_agent.py", "src/agents/timing_agent.py",
             "src/agents/assertion_agent.py", "src/agents/optimize_agent.py"]


def code_fingerprint() -> str:
    """Changes whenever the analysis code changes, so stale cache entries are never reused."""
    h = hashlib.sha256()
    for rel in _FP_FILES:
        p = ROOT / rel
        h.update(p.read_bytes() if p.exists() else b"-")
    return h.hexdigest()[:16]


def default_factories(model: str) -> dict:
    from src.agents.bug_agent import BugAgent
    from src.agents.timing_agent import TimingAgent
    from src.agents.assertion_agent import AssertionAgent
    from src.agents.optimize_agent import OptimizerAgent
    return {"bug": lambda: BugAgent(model=model), "timing": lambda: TimingAgent(model=model),
            "assertion": lambda: AssertionAgent(model=model), "optimizer": lambda: OptimizerAgent(model=model)}


def disable_llm() -> None:
    from src.core.base_agent import BaseAgent
    BaseAgent.call_ollama = lambda self, *a, **k: {"success": False, "error": "LLM disabled", "elapsed": 0.0}


# ---------------------------------------------------------------- line mapping
_LINE = re.compile(r"(?i)\bline\s+(\d+)")


def _shift_item(item: dict, offset: int) -> dict:
    out = dict(item)
    for key in ("location", "evidence"):
        if isinstance(out.get(key), str):
            out[key] = _LINE.sub(lambda m: f"line {int(m.group(1)) + offset}", out[key])
    if isinstance(out.get("line"), int):
        out["line"] += offset
    return out


def _context_prefix(unit: ModuleUnit, by_name: dict) -> str:
    lines = []
    for c in sorted(unit.children)[:8]:
        if c in by_name:
            lines.append(f"// instantiated module {c}: {interface_summary(by_name[c], 400)}")
    return ("\n".join(lines) + "\n") if lines else ""


# ---------------------------------------------------------------- main entry
def analyze_project(path: str, model: str, agents=("bug", "timing", "assertion", "optimizer"),
                    use_cache: bool = True, agent_factories: dict | None = None,
                    cache_path: str | None = None) -> dict:
    t0 = time.time()
    units = scan_project(path)
    if not units:
        return {"modules": [], "elapsed_s": 0.0, "error": f"no modules found in {path}"}
    ordered = bottom_up_order(units)
    by_name = {u.name: u for u in units}
    factories = agent_factories or default_factories(model)
    live = {name: factories[name]() for name in agents}
    cache = ResultCache(cache_path or str(ROOT / ".cache" / "analysis_cache.json")) if use_cache else None
    fp = code_fingerprint()

    out_modules = []
    with tempfile.TemporaryDirectory() as tmp:
        for n, u in enumerate(ordered, 1):
            prefix = _context_prefix(u, by_name)
            text = prefix + u.text
            offset = u.start_line - 1 - len(prefix.splitlines())
            tmp_path = Path(tmp) / f"{u.name}.sv"
            tmp_path.write_text(text, encoding="utf-8")
            print(f"[{n}/{len(ordered)}] {u.name} ({u.loc} lines, {Path(u.file).name}:{u.start_line})")
            entry = {"module": u.name, "file": u.file, "start_line": u.start_line,
                     "end_line": u.end_line, "loc": u.loc, "children": sorted(u.children), "agents": {}}
            for name, agent in live.items():
                key = cache.key(model, name, text, fp) if cache else None
                res = cache.get(key) if cache else None
                cached = res is not None
                if res is None:
                    res = agent.analyze(str(tmp_path))
                    if cache and res.get("success"):
                        cache.put(key, json.loads(json.dumps(res, default=str)))
                items_key = AGENT_KEYS[name][0]
                items = [_shift_item(i, offset) for i in res.get(items_key, [])] if res.get("success") else []
                entry["agents"][name] = {
                    "success": bool(res.get("success")), "error": res.get("error"), "cached": cached,
                    "items": items,
                    "static": sum(1 for i in items if i.get("source") == "static"),
                    "llm": sum(1 for i in items if i.get("source") == "llm"),
                    "llm_stats": res.get("llm_stats"), "llm_error": res.get("llm_error"),
                }
            out_modules.append(entry)
    return {"path": path, "model": model, "generated": datetime.now().isoformat(timespec="seconds"),
            "elapsed_s": round(time.time() - t0, 1), "modules": out_modules}


# ---------------------------------------------------------------- reporting
def _item_line(it: dict) -> str:
    text = it.get("problem") or it.get("issue") or it.get("description") or it.get("sva_code", "")
    return f"- [{it.get('source', '?')}] **{it.get('type', '?')}** {it.get('location') or it.get('signal', '')} - {text}"


def write_reports(result: dict, out_dir: str) -> tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    stem = Path(result["path"]).name or "project"
    md_path, js_path = os.path.join(out_dir, f"{stem}_project_report.md"), os.path.join(out_dir, f"{stem}_project_report.json")
    with open(js_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, default=str)

    lines = [f"# Project report: {result['path']}", "",
             f"Model: `{result['model']}` | modules: {len(result['modules'])} | time: {result['elapsed_s']}s | {result['generated']}", "",
             "Count format: static+llm (`ERR` = agent failed, `c` = served from cache)", "",
             "| Module | LOC | Bugs | Timing | SVA | Opts |", "|---|---|---|---|---|---|"]
    for m in result["modules"]:
        cells = []
        for a in AGENT_KEYS:
            r = m["agents"].get(a)
            if r is None:
                cells.append("-")
            elif not r["success"]:
                cells.append("ERR")
            else:
                cells.append(f"{r['static']}+{r['llm']}" + ("c" if r["cached"] else ""))
        lines.append(f"| {m['module']} | {m['loc']} | " + " | ".join(cells) + " |")
    lines.append("")
    for m in result["modules"]:
        lines += [f"## {m['module']}  ({Path(m['file']).name}:{m['start_line']}-{m['end_line']})", ""]
        if m["children"]:
            lines += [f"Instantiates: {', '.join(m['children'])}", ""]
        for a, (_, title) in AGENT_KEYS.items():
            r = m["agents"].get(a)
            if r is None:
                continue
            lines.append(f"### {title}")
            if not r["success"]:
                lines.append(f"Agent failed: {str(r['error'])[:300]}")
            elif not r["items"]:
                lines.append("None.")
            else:
                lines += [_item_line(i) for i in r["items"]]
            lines.append("")
    Path(md_path).write_text("\n".join(lines), encoding="utf-8")
    return md_path, js_path


def main():
    sys.path.insert(0, str(ROOT))
    ap = argparse.ArgumentParser(description="Per-module RTL analysis for large projects")
    ap.add_argument("path", help="file or folder (recursive)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--agents", default="bug,timing,assertion,optimizer")
    ap.add_argument("--static-only", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "reports"))
    a = ap.parse_args()
    from src.core.config import DEFAULT_MODEL
    model = a.model or DEFAULT_MODEL
    if a.static_only:
        disable_llm()
    names = [x.strip() for x in a.agents.split(",") if x.strip()]
    bad = [x for x in names if x not in AGENT_KEYS]
    if bad:
        sys.exit(f"unknown agent(s): {bad}; choose from {list(AGENT_KEYS)}")
    res = analyze_project(a.path, model, names, use_cache=not a.no_cache)
    md, js = write_reports(res, a.out)
    print(f"\n{len(res['modules'])} modules in {res['elapsed_s']}s\nreport: {md}\njson:   {js}")


if __name__ == "__main__":
    main()