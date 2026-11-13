"""
run_benchmark.py - measure recall, precision, and agent quality across all 4 RTL agents.

    python benchmarks/run_benchmark.py --model qwen2.5-coder:7b
    python benchmarks/run_benchmark.py --static-only      # no LLM, tests the deterministic tier
    python benchmarks/run_benchmark.py --skip-gen         # run BugAgent & TimingAgent only

Recall    = labelled issues found / labelled issues.
Precision = findings matching a label / all findings. Findings that match no label are
            "unlabelled": they may be false positives OR real bugs missing from labels.json,
            so read them by hand and extend the labels.
Numbers are reported separately for the static tier and the LLM tier.
"""
import argparse
from collections import Counter
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.core.base_agent import BaseAgent  # noqa: E402
from src.core.config import DEFAULT_MODEL  # noqa: E402
from src.agents.bug_agent import BugAgent  # noqa: E402
from src.agents.timing_agent import TimingAgent  # noqa: E402
from src.agents.assertion_agent import AssertionAgent  # noqa: E402

try:
    from src.agents.optimizer_agent import OptimizerAgent  # noqa: E402
except ImportError:
    from src.agents.optimize_agent import OptimizerAgent  # type: ignore  # noqa: E402

# Allow specific subtype classifications to satisfy broader ground-truth labels
TYPE_COMPAT = {
    "FUNCTIONAL": {"FUNCTIONAL", "WIDTH", "OVERFLOW", "LOGIC"},
}


def matches(finding: dict, label: dict) -> bool:
    ftype = str(finding.get("type", "")).upper()
    ltype = label["type"].upper()
    if ftype not in TYPE_COMPAT.get(ltype, {ltype}):
        return False
    text = f"{finding.get('location', '')} {finding.get('problem', '')}"
    return re.search(rf"\b{re.escape(label['signal'])}\b", text) is not None


def score(findings: list, labels: list) -> dict:
    found = [any(matches(f, l) for f in findings) for l in labels]
    matched = [f for f in findings if any(matches(f, l) for l in labels)]
    return {"labels": len(labels), "found": sum(found), "findings": len(findings), "matched": len(matched)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--rtl-folder", default=os.path.join(ROOT, "rtl_files"))
    ap.add_argument("--labels", default=os.path.join(ROOT, "benchmarks", "labels.json"))
    ap.add_argument("--static-only", action="store_true")
    ap.add_argument("--skip-gen", action="store_true", help="Skip AssertionAgent and OptimizerAgent")
    args = ap.parse_args()

    if args.static_only:
        BaseAgent.call_ollama = lambda self, *a, **k: {"success": False, "error": "LLM disabled", "elapsed": 0.0}

    with open(args.labels, encoding="utf-8") as f:
        labels = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

    bug_agent = BugAgent(model=args.model)
    timing_agent = TimingAgent(model=args.model)
    assertion_agent = None if args.skip_gen else AssertionAgent(model=args.model)
    optimizer_agent = None if args.skip_gen else OptimizerAgent(model=args.model)

    tot = {t: {"labels": 0, "found": 0, "findings": 0, "matched": 0} for t in ("static", "llm", "all")}
    rows = []
    gen_rows = []

    assert_stats = {
        "files": 0, "total": 0, "static": 0, "llm": 0,
        "lint_pass": 0, "behavioral": 0, "coverage": Counter(), "types": Counter(),
    }
    opt_stats = {
        "files": 0, "total": 0, "static": 0, "llm": 0,
        "quality": Counter(), "types": Counter(),
    }

    for fname, truth in labels.items():
        path = os.path.join(args.rtl_folder, fname)
        if not os.path.exists(path):
            print(f"skip (missing): {fname}")
            continue

        # 1. Detection Agents (BugAgent & TimingAgent)
        b, t = bug_agent.analyze(path), timing_agent.analyze(path)
        findings = (b.get("bugs", []) if b.get("success") else []) + (t.get("timing_issues", []) if t.get("success") else [])
        expected = truth.get("bugs", []) + truth.get("timing", [])

        for tier in ("static", "llm", "all"):
            subset = findings if tier == "all" else [f for f in findings if f.get("source") == tier]
            s = score(subset, expected)
            for k in s:
                tot[tier][k] += s[k]
            if tier == "all":
                rows.append((fname, s, [f for f in findings if not any(matches(f, l) for l in expected)]))

        # 2. AssertionAgent & OptimizerAgent
        if not args.skip_gen:
            a_res = assertion_agent.analyze(path)
            a_info = {"total": 0, "static": 0, "llm": 0, "cov": "ERR", "types": []}
            if a_res.get("success"):
                a_items = a_res.get("assertions", [])
                a_types = [str(a.get("type", "OTHER")).upper() for a in a_items]
                assert_stats["files"] += 1
                assert_stats["total"] += len(a_items)
                assert_stats["static"] += a_res.get("static_count", 0)
                assert_stats["llm"] += a_res.get("llm_count", 0)
                assert_stats["lint_pass"] += sum(1 for a in a_items if a.get("lint") == "pass")
                assert_stats["behavioral"] += sum(1 for a in a_items if "$isunknown" not in a.get("sva_code", ""))
                assert_stats["coverage"][a_res.get("coverage", "UNKNOWN")] += 1
                for tp in a_types:
                    assert_stats["types"][tp] += 1
                a_info = {
                    "total": len(a_items),
                    "static": a_res.get("static_count", 0),
                    "llm": a_res.get("llm_count", 0),
                    "cov": a_res.get("coverage", "UNKNOWN"),
                    "types": a_types,
                }

            o_res = optimizer_agent.analyze(path)
            o_info = {"total": 0, "static": 0, "llm": 0, "qual": "ERR", "types": []}
            if o_res.get("success"):
                o_items = o_res.get("optimizations", [])
                o_types = [str(o.get("type", "OTHER")).upper() for o in o_items]
                opt_stats["files"] += 1
                opt_stats["total"] += len(o_items)
                opt_stats["static"] += o_res.get("static_count", 0)
                opt_stats["llm"] += o_res.get("llm_count", 0)
                opt_stats["quality"][o_res.get("quality_score", "UNKNOWN")] += 1
                for tp in o_types:
                    opt_stats["types"][tp] += 1
                o_info = {
                    "total": len(o_items),
                    "static": o_res.get("static_count", 0),
                    "llm": o_res.get("llm_count", 0),
                    "qual": o_res.get("quality_score", "UNKNOWN"),
                    "types": o_types,
                }

            gen_rows.append((fname, a_info, o_info))

    print("\n=== Per file (Bug & Timing - all tiers) ===")
    for fname, s, extra in rows:
        print(f"{fname:<26} recall {s['found']}/{s['labels']}   findings {s['findings']} (matched {s['matched']}, unlabelled {s['findings'] - s['matched']})")
        for f in extra:
            print(f"    unlabelled [{f.get('source')}] {f.get('type')} {f.get('location')}")

    print("\n=== Totals (Bug & Timing) ===")
    for tier, s in tot.items():
        rec = s["found"] / s["labels"] if s["labels"] else 0
        prec = s["matched"] / s["findings"] if s["findings"] else 0
        print(f"{tier:<7} recall {s['found']}/{s['labels']} = {rec:.0%}   precision {s['matched']}/{s['findings']} = {prec:.0%}")

    if not args.skip_gen:
        print("\n=== Per file (Assertion & Optimizer) ===")
        for fname, a_info, o_info in gen_rows:
            a_t_str = f" [{', '.join(a_info['types'])}]" if a_info["types"] else ""
            o_t_str = f" [{', '.join(o_info['types'])}]" if o_info["types"] else ""
            print(
                f"{fname:<26} assertions: {a_info['total']} (static={a_info['static']}, llm={a_info['llm']}, cov={a_info['cov']}){a_t_str}"
                f"   |   optimizations: {o_info['total']} (static={o_info['static']}, llm={o_info['llm']}, qual={o_info['qual']}){o_t_str}"
            )

        print("\n=== AssertionAgent Summary ===")
        a_tot = assert_stats["total"]
        print(
            f"files={assert_stats['files']}  total={a_tot} "
            f"(static={assert_stats['static']}, llm={assert_stats['llm']})  "
            f"lint_pass={assert_stats['lint_pass']}/{a_tot}  "
            f"behavioral={assert_stats['behavioral']}/{a_tot}"
        )
        print(f"coverage={dict(assert_stats['coverage'])}  types={dict(assert_stats['types'])}")

        print("\n=== OptimizerAgent Summary ===")
        o_tot = opt_stats["total"]
        print(
            f"files={opt_stats['files']}  total={o_tot} "
            f"(static={opt_stats['static']}, llm={opt_stats['llm']})"
        )
        print(f"quality={dict(opt_stats['quality'])}  types={dict(opt_stats['types'])}")


if __name__ == "__main__":
    main()