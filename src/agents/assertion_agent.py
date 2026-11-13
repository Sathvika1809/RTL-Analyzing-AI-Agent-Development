from datetime import datetime
from pathlib import Path

from src.core.base_agent import BaseAgent
from src.core.rtl_parser import extract_declared_identifiers, static_assertions
from src.core import evidence as ev

ASSERT_TYPES = ["RESET", "RANGE", "STATE", "MUTEX", "HANDSHAKE", "FUNCTIONAL", "OTHER"]

ASSERT_SCHEMA = {
    "type": "object",
    "properties": {
        "assertions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ASSERT_TYPES},
                    "signal": {"type": "string"},
                    "sva_code": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["type", "signal", "sva_code", "description"],
            },
        }
    },
    "required": ["assertions"],
}

PROMPT = """Write SystemVerilog assertions for the module below.

Module facts:
- clock nets used: {clocks}
- declared names you may use: {names}

Rules:
- Use only names from the list above. Never invent signals, parameters or protocols.
- Prefer behavioral properties (state transitions, full/empty never both set, counter bounds, one-hot, input-to-output relations) over `!$isunknown(...)` checks. Use `!$isunknown` only if nothing stronger can be derived.
- {style}
- Each "sva_code" is exactly one complete statement ending with a semicolon.
- Infer reset polarity from how the code tests the reset. Do not assume a reset name.
- If no meaningful assertion can be derived, return {{"assertions": []}}.

FILE {filename}:
{code}
"""

CLOCKED = "Clocked module: use `assert property (@(posedge CLK) disable iff (RESET_CONDITION) ...);` with a clock from the list."
COMB = "No clock in this module: use immediate assertions only, as `always_comb assert (CONDITION);`. Do not use `assert property`."


class AssertionAgent(BaseAgent):
    """
    Tier 1: static template assertions (reset known / no X).
    Tier 2: LLM behavioral assertions, each one checked by
            (a) identifier check: every name used is declared,
            (b) clock check: the clock in @(posedge X) is declared,
            (c) Verilator lint of the RTL with that single assertion inserted.
    Assertions are linted one at a time, so one bad assertion does not discard the rest.
    If Verilator is unavailable the check is skipped and the item is marked lint=skipped.
    """

    def __init__(self, model: str = None):
        super().__init__(agent_name="assertion_agent", model=model)

    def analyze(self, filepath: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}
        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Assertion agent analyzing: {path.name}")

        try:
            meta = extract_declared_identifiers(code)
        except Exception:  # noqa: BLE001
            meta = {}
        declared = ev.declared_names(meta)

        static = ev.safe_static(static_assertions, code)
        for a in static:
            a["source"] = "static"

        llm, stats, err, elapsed = self._run_llm(code, path, declared)
        if err and not static:
            return {"success": False, "error": err}

        merged = ev.merge_dedupe(static, llm, lambda a: (str(a.get("type", "")).upper(), str(a.get("signal", "")).lower()))

        llm_n = sum(1 for x in merged if x.get('source') == 'llm')
        if not merged:
            coverage = "LOW"
        else:
            coverage = "HIGH" if llm_n >= 2 else "MEDIUM"
        raw = self._format(merged, coverage)

        self.log_run(path.name, {
            "assertions_generated": len(merged), "coverage": coverage,
            "static_count": len(static), "llm_count": llm_n,
            "llm_stats": stats, "llm_error": err, "response_length": len(raw),
        })
        return {
            "success": True, "filename": path.name, "filepath": str(path),
            "timestamp": datetime.now().isoformat(), "model": self.model,
            "assertions": merged, "total_assertions": len(merged), "coverage": coverage,
            "raw_response": raw, "elapsed_s": elapsed,
            "static_count": len(static), "llm_count": llm_n,
            "llm_stats": stats, "llm_error": err,
        }

    def _run_llm(self, code, path, declared):
        clocks = ev.clocks_in_code(code)
        prompt = PROMPT.format(
            clocks=", ".join(clocks) or "none",
            names=", ".join(sorted(declared)) or "(see code)",
            style=CLOCKED if clocks else COMB,
            filename=path.name,
            code=ev.build_code_context(code, "reset clock state assert property"),
        )
        parsed, err, call = self.llm_json(prompt, ASSERT_SCHEMA, max_tokens=1200)
        if err:
            return [], {"returned": 0, "kept": 0, "rejected": {}}, err, 0.0

        items = ev.extract_list(parsed, "assertions")
        stats = {"returned": len(items), "kept": 0, "rejected": {}}

        def reject(reason):
            stats["rejected"][reason] = stats["rejected"].get(reason, 0) + 1

        candidates = []
        for a in items:
            if not isinstance(a, dict) or not str(a.get("sva_code", "")).strip():
                reject("empty_or_not_object"); continue
            sva = a["sva_code"].strip()
            if undeclared_ids := ev.undeclared_in_sva(sva, declared):
                reject("undeclared_identifier"); a["_why"] = undeclared_ids; continue
            if clocks and "assert property" in sva and "@" not in sva:
                reject("no_clock_in_property"); continue
            if not clocks and "assert property" in sva:
                reject("concurrent_in_comb_module"); continue
            a["type"] = str(a.get("type", "OTHER")).upper()
            a["source"] = "llm"
            candidates.append(a)

        kept = self._lint_each(code, candidates, stats)
        stats["kept"] = len(kept)
        ev.print_stats(self.agent_name, stats, call)
        return kept, stats, None, call.get("elapsed", 0.0)

    @staticmethod
    def _lint_each(code, candidates, stats):
        if not candidates:
            return []
        base_status, base_msg = ev.verilator_lint(code)
        if base_status != "pass":
            # The RTL itself does not lint cleanly (or no tool): do not blame the assertions.
            for a in candidates:
                a["lint"] = "skipped"
            stats["lint_note"] = f"baseline RTL lint = {base_status}"
            return candidates
        kept = []
        for a in candidates:
            status, msg = ev.verilator_lint(ev.insert_before_endmodule(code, a["sva_code"]))
            a["lint"] = status
            if status == "fail":
                stats["rejected"]["verilator_error"] = stats["rejected"].get("verilator_error", 0) + 1
                continue
            kept.append(a)
        return kept

    @staticmethod
    def _format(assertions, coverage):
        if not assertions:
            return "NO ASSERTIONS GENERATED\n\nTOTAL ASSERTIONS: 0\nCOVERAGE LEVEL: LOW\n"
        out = []
        for i, a in enumerate(assertions, 1):
            out += [f"ASSERTION #{i} [{a.get('source', 'unknown')}]",
                    f"Type: {a.get('type', 'UNKNOWN')}",
                    f"Signal: {a.get('signal', '')}",
                    f"SVA Code:\n{a.get('sva_code', '')}",
                    f"Description: {a.get('description', '')}", ""]
        out += [f"TOTAL ASSERTIONS: {len(assertions)}", f"COVERAGE LEVEL: {coverage}"]
        return "\n".join(out)