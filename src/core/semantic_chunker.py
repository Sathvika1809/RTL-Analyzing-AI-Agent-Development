"""Semantic chunking utilities for SystemVerilog RTL prompts.

Design goals:
- Use semantic extraction where possible (rtl_parser + pyslang)
- Gracefully fall back to regex extraction when parsing fails
- Keep chunk selection generic (works across different SV files)
- Provide deterministic, explainable chunk filtering (keyword routing)

This module is intentionally lightweight (no embeddings) because the project
already has strong anti-hallucination guardrails using rtl_parser's
references_only_declared() filtering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import re

from src.core import rtl_parser


@dataclass(frozen=True)
class Chunk:
    id: str
    kind: str
    header: str
    text: str
    line_start: int | None = None
    line_end: int | None = None

    def as_prompt_block(self) -> str:
        loc = ""
        if self.line_start is not None and self.line_end is not None:
            loc = f" (lines {self.line_start}-{self.line_end})"
        return (
            f"### Chunk {self.id} [{self.kind}]{loc}\n"
            f"{self.header.strip()}\n"
            f"```systemverilog\n{self.text.strip()}\n```\n"
        )


def _collapse_ws(s: str) -> str:
    # Keep newlines for code, but normalize excessive spaces.
    return re.sub(r"[ \t]+", " ", s)


def chunk_sv(code: str, *, prefer_always_blocks: bool = True) -> list[Chunk]:
    """Extract semantic chunks from RTL code.

    Currently implemented:
    - always-block chunks (from rtl_parser._find_always_blocks)

    Note:
    rtl_parser's best-effort block extraction relies on comments-stripped code.
    """

    # rtl_parser keeps many helpers private; however we can rely on its public
    # semantics by calling its internal always-block discovery via a private
    # function is not ideal. Instead, we replicate the call through behavior:
    # static_bug_findings() and others already depend on these, so we'll use
    # the same private helpers by importing module and accessing.
    #
    # If upstream refactors rtl_parser, update this module accordingly.

    chunks: list[Chunk] = []

    # 1) Always blocks
    always_blocks: list[dict] = []
    try:
        # Access the internal helper; we do this because it already performs
        # semantic + fallback extraction robustly.
        always_blocks = rtl_parser._find_always_blocks(code)  # type: ignore[attr-defined]
    except Exception:
        always_blocks = []

    if prefer_always_blocks and always_blocks:
        for i, b in enumerate(always_blocks, 1):
            kind = b.get("kind", "always")
            header = b.get("header", "") or ""
            text = b.get("text", "") or ""
            if not text.strip():
                continue
            chunks.append(
                Chunk(
                    id=str(i),
                    kind=str(kind),
                    header=str(header),
                    text=str(text),
                    line_start=b.get("line"),
                    line_end=None,
                )
            )

    # 2) Continuous assign chunks (best-effort regex)
    #    This helps agents reason about driven signals even when always blocks
    #    are absent.
    assign_chunks: list[Chunk] = []
    try:
        clean = rtl_parser._strip_comments(code)  # type: ignore[attr-defined]
    except Exception:
        clean = code

    # Conservative: one-line assign statements ending in ';'
    # (if RTL uses multi-line assigns, they won't be captured here).
    pat = re.compile(r"\bassign\s+[^;]*;", re.MULTILINE | re.DOTALL)
    assigns = pat.findall(clean)
    for j, stmt in enumerate(assigns, 1):
        s = stmt.strip()
        if not s:
            continue
        # Try to estimate line number for diagnostics.
        # (Not strictly needed for prompt selection)
        line_start = None
        try:
            line_start = clean[: clean.find(stmt)].count("\n") + 1
        except Exception:
            line_start = None

        assign_chunks.append(
            Chunk(
                id=f"a{j}",
                kind="assign",
                header="continuous assign",
                text=_collapse_ws(s),
                line_start=line_start,
                line_end=None,
            )
        )

    # If always-block chunks weren't found, return assign chunks (or both).
    if not chunks:
        return assign_chunks

    # Otherwise, append assign chunks too (bounded later by selection).
    return chunks + assign_chunks


def _tokenize_query(q: str) -> set[str]:
    q = q.lower()
    # Keep meaningful tokens only.
    toks = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", q))
    return toks


def _chunk_score(chunk: Chunk, query_tokens: set[str]) -> int:
    # Keyword routing. Generic, does not require specific signal names.
    kind = chunk.kind.lower()
    header = (chunk.header or "").lower()
    text = chunk.text.lower()

    score = 0

    # Strong routing by chunk kind.
    if kind in {"ff", "always_ff"}:
        score += 6
    if kind in {"comb", "always_comb", "latch", "always_latch"}:
        score += 5
    if kind == "assign":
        score += 3

    # Query token matches.
    for t in query_tokens:
        if t in {"reset", "rst", "rst_n", "areset", "areset_n"}:
            if "rst" in text or "reset" in text or "rst_n" in text:
                score += 3
        if t in {"clock", "clk"}:
            if "posedge" in text or "negedge" in text or "clk" in text or "clock" in text:
                score += 3
        if t in {"latch"}:
            if "if" in text and "else" not in text:
                score += 2
            if kind in {"comb", "latch"}:
                score += 2
        if t in {"width", "bit", "truncation", "sign"}:
            if "'" in text or "[" in text or "$unsigned" in text or "$signed" in text:
                score += 2
        if t in {"sva", "assert", "property"}:
            # Assertions themselves aren't in chunks (unless user file contains SVA).
            # Still helps focus on clock/reset structures.
            if "posedge" in text or "disable iff" in text:
                score += 2
        if t in {"cdc", "cross"}:
            if "posedge" in text or "always" in text:
                score += 1

    # Also match a few structural keywords regardless of query tokens.
    if "always_ff" in text or kind == "ff":
        score += 1
    if "always_comb" in text or kind in {"comb"}:
        score += 1
    if "always_latch" in text or kind in {"latch"}:
        score += 1

    return score


def select_relevant_chunks(
    chunks: Iterable[Chunk],
    query: str,
    *,
    top_k: int = 8,
    max_total_chars: int = 12000,
) -> list[Chunk]:
    """Select top-K chunks relevant to the query.

    Uses keyword routing + a simple scoring function.
    """
    ch_list = list(chunks)
    if not ch_list:
        return []

    toks = _tokenize_query(query)

    scored = []
    for c in ch_list:
        s = _chunk_score(c, toks)
        scored.append((s, c))

    # If query has no tokens (e.g., empty), keep stable order by kind/position.
    scored.sort(key=lambda x: (x[0], x[1].kind), reverse=True)

    selected: list[Chunk] = []
    total = 0
    for s, c in scored:
        if c.text.strip() == "":
            continue
        projected = len(c.text)
        if selected and (len(selected) >= top_k):
            break
        if total + projected > max_total_chars:
            break
        selected.append(c)
        total += projected

    # If everything scored 0, still return first top_k for minimal context.
    if not selected:
        return ch_list[:top_k]

    return selected


def chunks_to_prompt_text(chunks: Iterable[Chunk]) -> str:
    out = []
    for c in chunks:
        out.append(c.as_prompt_block())
    return "\n".join(out)

