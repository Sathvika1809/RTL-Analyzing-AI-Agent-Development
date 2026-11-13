"""
src/core/project_scan.py - module discovery, dependency ordering, and SHA-256 caching
for src/core/pipeline.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re

from src.core.rtl_parser import _strip_comments

_MOD_RE = re.compile(r"\bmodule\s+([A-Za-z_]\w*)\b.*?\bendmodule\b", re.DOTALL)
_INST_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?:#\s*\([^;]*?\)\s*)?([A-Za-z_]\w*)\s*\(", re.M | re.S)
_NON_INST = {
    "module", "endmodule", "if", "else", "case", "casez", "casex", "for", "while",
    "always", "always_ff", "always_comb", "always_latch", "assign", "initial",
    "begin", "end", "function", "task", "assert", "assume", "cover", "property",
}


@dataclass
class ModuleUnit:
    name: str
    file: str
    start_line: int
    end_line: int
    loc: int
    text: str
    children: set[str] = field(default_factory=set)


class ResultCache:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        except Exception:
            self._data = {}

    @staticmethod
    def key(*parts: str) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(str(p).encode("utf-8", errors="replace"))
            h.update(b"\x00")
        return h.hexdigest()

    def get(self, key: str):
        return self._data.get(key)

    def put(self, key: str, value) -> None:
        self._data[key] = value
        try:
            self.path.write_text(json.dumps(self._data, indent=1, default=str), encoding="utf-8")
        except Exception:
            pass


def scan_project(target: str) -> list[ModuleUnit]:
    p = Path(target)
    files = [p] if p.is_file() else sorted(
        f for f in p.rglob("*") if f.suffix.lower() in {".v", ".sv"}
    )
    units: list[ModuleUnit] = []
    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        # Preserve exact character offsets while blanking comments
        masked = re.sub(r"//[^\n]*", lambda m: " " * len(m.group(0)), raw)
        masked = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), masked, flags=re.S)
        for m in _MOD_RE.finditer(masked):
            name = m.group(1)
            start_line = raw[: m.start()].count("\n") + 1
            end_line = raw[: m.end()].count("\n") + 1
            mod_text = "\n".join(raw.splitlines()[start_line - 1 : end_line])
            units.append(ModuleUnit(
                name=name,
                file=str(f),
                start_line=start_line,
                end_line=end_line,
                loc=end_line - start_line + 1,
                text=mod_text,
            ))

    known_modules = {u.name for u in units}
    for u in units:
        body = _strip_comments(u.text)
        for im in _INST_RE.finditer(body):
            mod_type = im.group(1)
            if mod_type in known_modules and mod_type != u.name and mod_type not in _NON_INST:
                u.children.add(mod_type)
    return units


def bottom_up_order(units: list[ModuleUnit]) -> list[ModuleUnit]:
    by_name = {u.name: u for u in units}
    visited: set[str] = set()
    ordered: list[ModuleUnit] = []

    def dfs(name: str) -> None:
        if name in visited or name not in by_name:
            return
        visited.add(name)
        for child in sorted(by_name[name].children):
            dfs(child)
        ordered.append(by_name[name])

    for u in sorted(units, key=lambda x: x.name):
        dfs(u.name)
    return ordered


def interface_summary(unit: ModuleUnit, max_chars: int = 400) -> str:
    clean = _strip_comments(unit.text)
    m = re.search(r"\bmodule\s+\w+\s*(?:#\s*\([^;]*?\)\s*)?\((.*?)\)\s*;", clean, re.DOTALL)
    ports = " ".join(m.group(1).split()) if m else ""
    return ports[:max_chars] + ("..." if len(ports) > max_chars else "")