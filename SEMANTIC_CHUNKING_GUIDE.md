# Semantic Chunking in This Project (End-to-End Guide)

## 1) What your project does (from scratch)
This repository is an **RTL analysis assistant** for SystemVerilog/Verilog designs.

### Pipeline (overall)
1. **Input RTL**: you point the tool at one file or a folder in `rtl_files/`.
2. **Run specialized agents**:
   - `BugAgent` — finds functional/latch/reset/width bugs
   - `TimingAgent` — checks timing-related hazards (blocking, sensitivity, CDC, etc.)
   - `AssertionAgent` — generates SVA assertions for behavior inferred from RTL
   - `OptimizerAgent` — suggests readability/maintainability/style optimizations
3. **Two-tier analysis per agent**:
   - **Tier 1: static analysis** using `src/core/rtl_parser.py` (pyslang-backed) functions such as `static_bug_findings`, `static_timing_findings`, etc.
   - **Tier 2: LLM fallback** if Tier 1 produces nothing (or for user queries in `CustomAgent`).
4. **Reports** are written into `reports/` as markdown.

### Where LLM hallucinations came from
Before this change, the LLM fallback prompts generally included:
- the **entire RTL file** (full `{code}` content)

When the prompt contains a lot of irrelevant/unrelated code, models tend to:
- guess signal names that are not actually declared
- invent protocols/conditions
- describe behavior that is not clearly supported

You already had anti-hallucination safeguards like:
- `references_only_declared(...)`
- `is_concrete_finding(...)`

…but chunking improves the situation earlier by giving the model **only the most relevant semantic regions**.

---

## 2) What “semantic chunking” means here
Semantic chunking = **split the RTL into meaningful pieces** (semantic units), then provide the LLM with only the pieces relevant to the current task.

In this project, “semantic units” come primarily from `src/core/rtl_parser.py`:
- always-block regions (procedural logic)
- (best-effort) continuous assignments

Then we apply **relevance selection**:
- score chunks by keyword routing (reset/clock/latch/always_ff/etc.)
- take **top‑K** chunks

No embeddings/vector DB are required for this implementation.

---

## 3) New module: `src/core/semantic_chunker.py`
This is the core chunking logic.

### 3.1 Chunk extraction
Implemented in `chunk_sv(code: str)`:
- Attempts to extract **always-block chunks** using the existing capabilities in `src/core/rtl_parser.py` (best-effort).
- Creates additional **assign chunks** using conservative regex matching:
  - one-line `assign ...;` style

It returns a list of `Chunk` objects:
- `id`
- `kind` (e.g., `ff`, `comb`, `latch`, `assign`)
- `header`
- `text`
- optional line metadata

### 3.2 Relevance scoring (semantic routing)
Implemented in `select_relevant_chunks(chunks, query, top_k, max_total_chars)`:
- tokenizes the query into identifiers/keywords
- scores each chunk based on:
  - chunk kind (ff/comb/latch/assign)
  - presence of task-related keywords inside chunk text

### 3.3 Prompt assembly
Implemented in `chunks_to_prompt_text(chunks)`:
- formats each selected chunk into a prompt-friendly block:
  - header + fenced SystemVerilog snippet

---

## 4) How the agents were changed
The key idea: **replace `{code}` (full file)** with **`{code_ctx}` (selected chunks)** in LLM prompts.

### Agents updated
1. **`src/agents/bug_agent.py`**
   - Static analysis still runs first.
   - If static produces no bugs, the LLM fallback now does:
     - `chunks = chunk_sv(code)`
     - `selected = select_relevant_chunks(..., query=BUG_ANALYSIS_PROMPT, ...)`
     - `code_ctx = chunks_to_prompt_text(selected)`
     - `prompt = BUG_ANALYSIS_PROMPT.format(code=code_ctx)`

2. **`src/agents/custom_agent.py`**
   - User’s `query` is used as the relevance signal.
   - Only the relevant portions of the RTL are sent to the model.

3. **`src/agents/assertion_agent.py`**
   - LLM path uses selected semantic chunks.
   - Static assertions remain unchanged.
   - This reduces assertion hallucinations because the model is grounded in relevant sequential/combinational/reset behavior.

4. **`src/agents/timing_agent.py`**
   - LLM path now sees only timing-relevant semantic pieces.

5. **`src/agents/optimize_agent.py`**
   - LLM path now sees only optimization-relevant semantic pieces.

---

## 5) Why this reduces hallucinations (practically)
Compared to “full file in prompt”, chunking improves:

1. **Context focus**
   - The model sees only the always-block(s) and/or assign regions relevant to the task.

2. **Declared-signal correctness improves**
   - Even though you already filter output using `references_only_declared`, chunking reduces the model’s temptation to mention irrelevant identifiers.

3. **Fewer contradictions**
   - With less irrelevant context, models are less likely to merge ideas from unrelated parts of the RTL.

---

## 6) How you can validate success
Run:

```bash
python run_all_agents.py --model <your_model>
```

Then inspect phase3 report markdown files under `reports/`.

### What to look for
- Fewer assertion objects that reference non-declared identifiers
- Reduced “vague” findings that fail `is_concrete_finding`
- Lower volume of nonsensical outputs

---

## 7) Optional next upgrades (if you want even better chunking)
This implementation uses keyword routing.

You can improve further by adding:
- **better chunking granularity**
  - split by module header / reset block / each always_ff block individually
- **LLM-assisted selection**
  - show only chunk headers to an LLM to pick best chunks
- **embeddings + vector retrieval**
  - store chunks in a vector index and retrieve by similarity

---

## 8) Files checklist (for your reference)
- `src/core/semantic_chunker.py` (new)
- `src/agents/bug_agent.py` (LLM fallback uses chunked context)
- `src/agents/custom_agent.py` (LLM query uses chunked context)
- `src/agents/assertion_agent.py` (LLM path uses chunked context)
- `src/agents/timing_agent.py` (LLM path uses chunked context)
- `src/agents/optimize_agent.py` (LLM fallback uses chunked context)

