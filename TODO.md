# TODO (Agentic RTL Verifier / Anti-Hallucination)

## Active: Retrieval + Local-LLM Robust Synth Loop

### Additionally: Semantic-grounded anti-hallucination for Phase-3 Agents
- [x] Tighten semantic chunking (more/less chars) for Bug/Timing/Assertion/Optimize agents to reduce hallucinations.


### Step 1 — Replace `kb` TF-IDF retrieval in `rag_pipeline.py`
- [ ] Update `SemanticHardwareRetriever` to pull from actual project RTL sources (e.g. `rtl_files/*.sv` / `rtl_files/*.v`).
- [ ] Use `src/core/semantic_chunker.py` (`chunk_sv`, `select_relevant_chunks`, `chunks_to_prompt_text`) to build grounded context.
- [ ] Remove TF-IDF/KB dependency from generation path.

### Step 2 — Declared-only gating for generated synthesis outputs
- [ ] After LLM generation, validate that the generated modules only reference declared identifiers for that generated code.
- [ ] If non-declared identifiers are detected, re-prompt with a strict “fix only to use declared identifiers” instruction.

### Step 3 — Evidence-aware Verilator repair prompts
- [ ] Parse Verilator stderr and extract error summaries (e.g., undefined identifiers, latches, etc.).
- [ ] Provide the relevant previously-retrieved chunks + error summary in the repair prompt.
- [ ] Tighten retry loop stopping conditions (zero critical errors / no undefined identifiers).

### Step 4 — Update progress docs
- [ ] Update `PROJECT_PROGRESS.md` with completion markers for the above changes.
- [ ] Ensure done criteria for anti-hallucination are reflected.

## Notes
- The current repo already has evidence validators in `src/core/rtl_parser.py` for SVA and optimization.
- This task extends that philosophy to RTL synthesis/rewrite in `rag_pipeline.py`.

