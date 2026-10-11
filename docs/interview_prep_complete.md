# Interview Preparation — RTL AI Verification & Analysis Assistant

> Complete guide covering the project, tech stack, challenges, and likely interview questions with detailed answers.

---

## 1. THE PROJECT — EXPLAIN IN 60 SECONDS

**What it is:**
An **offline, multi-agent AI verification and analysis suite** for hardware designers. It takes **SystemVerilog/Verilog RTL files** and runs **multiple specialized AI agents** to detect bugs, flag timing hazards, generate functional assertions (SVA), and suggest code optimizations — all powered by a **local LLM (Ollama)**, so proprietary RTL never leaves the machine.

**The core problem it solves:**
Static analysis tools (linters, synthesis tools) catch *syntax* errors, but finding *functional* bugs, timing violations, CDC (clock-domain crossing) mismatches, and latch inferences usually requires complex commercial tools or extensive simulation. This project shows that a **local LLM + deterministic static analysis** can provide a meaningful, *evidence-backed* first pass — without sending sensitive RTL to the cloud.

**The architecture (high level):**
```
User
 ├── CLI (src/main.py --cli)
 └── Web GUI (FastAPI + HTML/CSS/JS)
          │
          ▼
   FastAPI backend (src/web/server.py)
          │
          ▼
   Specialized Agents (src/agents/)
   ├── Bug Agent        → functional/structural bugs
   ├── Timing Agent     → timing/CDC hazards
   ├── Assertion Agent  → generates SVA (SystemVerilog Assertions)
   ├── Optimizer Agent  → code-quality/optimization suggestions
   ├── Fixer Agent      → auto-repairs the RTL
   └── Custom Agent     → answers user questions about the file
          │
          ▼
   Core layer (src/core/)
   ├── BaseAgent        → GUI-less Ollama calls, JSON parsing, logging
   ├── rtl_parser       → pyslang AST static analysis + anti-hallucination validators
   └── semantic_chunker → chunks RTL into relevant regions for the LLM
          │
          ▼
   Local Ollama LLM (qwen2.5, mistral, codellama)
```

**Key design principle:** The project is deliberately **conservative and evidence-backed**. It would rather report *no* finding than invent a wrong one. Every LLM output is filtered against the set of *actually declared* signals/ports in the RTL, so hallucinated signal names are rejected.

---

## 2. TECH STACK (with rationale)

| Layer | Technology | Why |
|-------|-----------|-----|
| **Language** | Python 3.10+ | Rich ecosystem for LLM/HTTP, AST parsing, threading |
| **Backend/API** | **FastAPI** + **uvicorn** | Async, fast, auto-documented REST endpoints, serves the frontend |
| **LLM serving** | **Ollama** (local) | Runs models fully offline; keeps RTL private; `/api/generate` + `/api/tags` |
| **LLM models** | `qwen2.5:3b`, `mistral`, `codellama` | Small local models adequate for RTL analysis; chosen via config |
| **RTL parsing** | **pyslang** | Real SystemVerilog AST parser (ports, variables, procedural blocks, types) — far more reliable than regex |
| **HTTP client** | `requests` | Calls Ollama's `/api/generate` with structured JSON prompts |
| **Data validation** | **pydantic** | Defines request models (`AnalyzeRequest`, `FixRequest`, etc.) |
| **Concurrency** | `concurrent.futures.ThreadPoolExecutor` | Runs the 4 agents in parallel (or sequentially) |
| **SVA linting** | **WSL + Verilator** | Compiles generated SVA to catch syntax errors; a feedback loop retries the LLM |
| **Frontend** | HTML/CSS/JS (glassmorphic dark-mode SPA) | Interactive dashboard: file CRUD, model selector, run analysis, live logs, auto-fix |
| **RAG extension** | `numpy`, `semantic_chunker` | Builds a local grounded retrieval index for synthesis prompts |
| **Logging** | JSONL files in `logs/` | Tracks each agent execution for debugging/audit |
| **Config** | `config/settings.json` | Ollama URL, default model, timeout, temperature |

---

## 3. THE SPECIALIZED AGENTS (the heart of the project)

All agents inherit from **`BaseAgent`**, which handles:
- Calling Ollama with **structured JSON mode** (`"format": "json"`)
- **Robust JSON parsing** (handles markdown code fences, lone braces, trailing text)
- **Timeout & error handling** (connect timeouts, read timeouts, connection errors, non-JSON responses)
- **JSONL logging** to `logs/<agent>_log.jsonl`

### 3.1 Bug Agent
- **Goal:** Find only *provable* functional/structural bugs.
- **Two-tier approach:**
  - **Tier 1 (static):** `static_bug_findings()` from pyslang — deterministic findings:
    - Blocking assignment `=` inside `always_ff` (should be `<=`)
    - Latch inference (incomplete `else`/`default` in combinational logic)
    - Missing reset assignments in reset-aware sequential blocks
    - Multiple drivers on one signal
    - Literal width mismatches (e.g. comparing `8-bit` signal to `9'b0`)
    - Undriven output ports
  - **Tier 2 (LLM fallback):** If static finds nothing, query the LLM, then **filter** results through `references_only_declared()` and `is_concrete_finding()`.
- **Output:** If nothing is proven, it returns `"NO EVIDENCE-BACKED BUGS DETECTED"` — never speculation.

### 3.2 Timing Agent
- **Goal:** Timing hazards that are *visible in code* (no setup/hold claims without constraints).
- Checks: blocking assignments in clocked logic, latch inference, incomplete manual sensitivity lists, concrete CDC concerns, excessive combinational chains.
- Uses the same two-tier static → LLM-filtered flow.

### 3.3 Assertion Agent (SVA) — most complex
- **Goal:** Generate meaningful **SystemVerilog Assertions (SVA)** that verify actual behavior.
- **Verilator compilation loop:** Generated SVA is inserted *before* `endmodule` and linted via **WSL Verilator** (`--lint-only -Wall`). If it fails, the error is fed back to the LLM with the original RTL, and it retries (up to 3 attempts).
- **Combination-only modules:** If no clock is detected, it instructs the LLM to emit **immediate assertions** (`assert(...)` in `always_comb`) instead of concurrent `assert property`.
- **Anti-hallucination:** `validate_sva_against_rtl()` checks that the SVA's clock, edge, reset polarity, and target signal all match real clocking evidence extracted from the RTL.

### 3.4 Optimizer Agent
- **Goal:** Concrete, low-risk style/readability/parameterization improvements only.
- Static findings: hardcoded bare literals (`static_optimizations()`).
- LLM outputs are filtered by `validate_optimization_against_rtl()` so only evidence-backed suggestions pass.

### 3.5 Fixer Agent
- **Goal:** Auto-repair RTL based on the bugs/timing/optimization findings.
- Sends the original code + findings to the LLM, requests a rewritten complete + synthesizable module that **preserves the module interface**.
- Important constraints: keep edits minimal, don't add/remove ports, preserve functionality.

### 3.6 Custom Agent
- **Goal:** Answer arbitrary user questions about an active RTL file.
- Uses semantic chunking to select relevant code regions, then returns a Markdown response (not JSON).

---

## 4. ANTI-HALLUCINATION ENGINEERING (the differentiator)

This is the most impressive/important part to talk about in interviews. The project builds **multiple layers** of defense against LLMs inventing things:

1. **Declared-identifier extraction (pyslang):** `extract_declared_identifiers()` returns the exact set of ports, signals, parameters, and detected clocks/resets from the AST — not regex guesses.

2. **`references_only_declared()` filter:** Rejects any LLM finding whose `signal`/`sva_code`/`fix`/`suggestion` fields reference identifiers not in the declared set (nothing invented).

3. **`is_concrete_finding()`:** Rejects vague/phrased hedging ("may have issues", "needs improvement").

4. **Evidence-based SVA validation:** `validate_sva_against_rtl()` extracts the clock edge + reset polarity + target from the SVA and cross-checks against real clocking blocks. If the SVA's clock/reset/target don't match evidence, it's dropped.

5. **Verilator compile loop:** Even if it passes semantic filters, the SVA must *actually compile* with Verilator. Compile errors are fed back to the LLM for a retry.

6. **Static analysis as the source of truth:** For bug/timing/optimizer, the LLM is often a *fallback*; the deterministic static findings are preferred. Reports are phrased as "NO EVIDENCE-BACKED BUGS DETECTED" when there's nothing to prove.

7. **Semantic chunking:** Instead of sending the whole file, only the most relevant always-blocks/assigns are sent to the LLM — reducing noise and hallucination, and keeping prompts small.

---

## 5. CHALLENGES FACED (and how you solved them)

### Challenge 1: LLM hallucination of signal names
- **Symptom:** `qwen2.5:3b` invented `always_comb` blocks and signals like `rst_n` that didn't exist; `codellama` suggested converting outputs to wires (invalid syntax).
- **Solution:** Built the declared-identifier gate + `references_only_declared()` + evidence-based validators. The LLM is now only allowed to reference signals proven to exist.

### Challenge 2: Baseline models couldn't find real bugs
- **Symptom:** `mistral`, `codellama`, and `qwen2.5:3b` all reported **no bugs** in the `counter.sv` which actually uses blocking `=` inside `always_ff`.
- **Solution:** Canonicalized the design — **deterministic static analysis first** (pyslang), LLM as a secondary/explanation layer. Static now reliably catches the blocking-assignment bug.

### Challenge 3: SVA syntax errors (concurrent assertions)
- **Symptom:** Generating valid concurrent SVA is hard; LLMs produce syntactically wrong properties.
- **Solution:** Wrapped the RTL + SVA in a temp file, inserted SVA *before* `endmodule`, and ran it through **WSL Verilator** in a compile/lint loop that feeds errors back to the LLM for retries.

### Challenge 4: Windows + WSL subprocess bug
- **Symptom:** `subprocess.run([...], shell=True)` on Windows silently dropped all but the first argument to `cmd.exe`, so Verilator was never actually invoked.
- **Solution:** Removed `shell=True` and passed the argument list directly, then translated Windows paths to WSL `/mnt/c/...` paths.

### Challenge 5: Latch-inference false positives
- **Symptom:** `else if` chains were incorrectly counted as missing `else`, producing false latch warnings.
- **Solution:** Used a negative lookahead `else\s*(?!if\b)` so only a *bare* `else` satisfies the "all-paths-complete" check.

### Challenge 6: Setup/hold and CDC over-claiming
- **Symptom:** LLMs would claim setup/hold violations or CDC issues just because multiple clocks were present.
- **Solution:** Enforced strict rules: reject setup/hold claims without constraints; reject CDC claims based only on multiple clocks; require *visible* evidence in the code.

### Challenge 7: Parameterized width resolution
- **Symptom:** Widths like `[WIDTH-1:0]` can't be checked statically as numbers.
- **Solution:** Only flag width mismatches when the width is concrete (`[7:0]`), or when `WIDTH-1:0` with a knowable default parameter (e.g. `parameter WIDTH = 8`) can be resolved.

### Challenge 8: Robust JSON parsing
- **Symptom:** LLMs return JSON wrapped in markdown fences, with trailing text, or as a list vs dict.
- **Solution:** `parse_json_response()` progressively tries: direct `json.loads`, stripping `` ```json ```` fences, stripping generic fences, then extracting the first `{` … last `}` block.

### Challenge 9: Ollama being slow / offline / invalid responses
- **Symptom:** Models can be slow or time out; the web app must not crash.
- **Solution:** `_ollama_error()` produces actionable error messages; per-agent timeouts; graceful degradation — the system still works when Ollama is down by falling back to static analysis.

### Challenge 10: Keeping prompts small & relevant
- **Symptom:** Large RTL files blow up token usage and confuse the model.
- **Solution:** Implemented `semantic_chunker.py` — extracts always-block/assign chunks, scores them by relevance to the query using keyword routing, and only sends the top-K under a character budget.

---

## 6. LIKELY INTERVIEW QUESTIONS & MODEL ANSWERS

### Q1. Explain your project in simple terms.
**A:** "I built an offline AI assistant that analyzes hardware design code (SystemVerilog/Verilog). It uses multiple specialized AI agents — each powered by a local language model — to find bugs, check timing, generate functional assertions, and suggest optimizations. The key differentiator is that it runs completely offline using Ollama, so proprietary RTL stays local. To make the AI trustworthy, I combined deterministic static analysis (using the pyslang parser) with LLM reasoning, and I added anti-hallucination filters so the AI can only reference signals that actually exist in the code."

### Q2. Why did you choose a multi-agent architecture instead of one big prompt?
**A:** "A single broad prompt misses issues and produces weak, generic explanations. I saw this in Phase 1 where three different models all failed to find the real bug in a counter. By splitting into specialized agents — bug, timing, assertion, optimizer, fixer — each agent has a focused, well-engineered prompt and a specific validation path. This is like having a dedicated reviewer for each concern. They can also run in parallel via thread pools, improving throughput."

### Q3. How do you handle LLM hallucinations? This is the most important question.
**A:** "I have a multi-layered defense:
1. First, I extract the *exact* set of declared identifiers (ports, signals, parameters, clocks, resets) from the AST using pyslang.
2. Every LLM output is filtered so it can only reference those declared identifiers — `references_only_declared()`. Anything with an invented signal name is dropped.
3. For assertions, I validate the clock, reset polarity, and target signal against real clocking evidence in the RTL.
4. For SVA specifically, I compile the generated code with Verilator; if it doesn't compile, the error is fed back to the LLM for a retry.
5. For bugs/timing/optimizations, I use deterministic static analysis as the source of truth and the LLM as the explanation layer. If nothing is provable, the report says 'no evidence-backed findings' rather than guessing."

### Q4. What is the difference between blocking and non-blocking assignment, and why did your agent flag it?
**A:** "Blocking assignment (`=`) executes immediately and blocks the next statement; non-blocking (`<=`) schedules a concurrent update at the end of the time step. In an `always_ff` block, you must use non-blocking `<=` because all flip-flops should update simultaneously using the *old* values. Using blocking `=` inside clocked logic creates race conditions and simulation/synthesis mismatches — the classic 'counter' bug in the project. My static analyzer detects `=` inside `always_ff` and flags it as a FUNCTIONAL bug."

### Q5. What is a latch? Why is it bad? How did you detect it?
**A:** "A latch is level-sensitive storage inferred when a combinational block (`always_comb`/`always @(*)`) doesn't assign a signal in all paths — e.g. an `if` with no `else`, or a `case` with no default. Latches are usually unintended, cause timing surprises, and can be a synthesis hazard. My static analyzer detects when a signal is assigned under a conditional but there's no complete `else`/`default`, and no unconditional default assignment before the conditional. I specifically fixed the false-positive case where `else if` chains were incorrectly flagged."

### Q6. What is CDC (Clock-Domain Crossing), and why is it dangerous?
**A:** "CDC is when a signal transfers between two different clock domains (e.g. from a write clock to a read clock). If the signal is sampled while it's changing, metastability can occur — the receiving flop enters an undefined state that can propagate. The standard fix is a **synchronizer**: two or more flops in series in the destination clock domain. My sample `cdc_pointer_sync.sv` uses a two-stage sync chain (`sync_reg_0` → `sync_reg_1`). In the timing agent, I only report CDC when there's clear evidence of unsynchronized cross-domain transfer, not just because multiple clocks exist."

### Q7. What is SVA (SystemVerilog Assertion)? Why generate them?
**A:** "SVA is a formal language for specifying temporal properties of a design — 'this behavior must always hold'. Examples: after reset, the counter output must be known; the FIFO must never be full and written at the same time. Assertions are used in simulation and formal verification to catch bugs. My assertion agent generates these automatically from the RTL, then validates them by compiling with Verilator, so we get *correct*, *compilable* assertions that verify the actual implemented behavior rather than invented protocols."

### Q8. Why did you use pyslang instead of just regex?
**A:** "RTL is a real language with a complex grammar — parameterized ports, packed/unpacked arrays, structs, typedefs, multi-line declarations. Regex breaks on these and produces false positives. pyslang is a real SystemVerilog parser that gives me an AST: I can enumerate ports, variables, parameters, procedural blocks (`always_ff` vs `always_comb`), and even type/width information reliably. I still use regex as a *fallback* when pyslang can't parse a file (e.g. missing includes), but the primary evidence comes from the AST."

### Q9. How does parallel execution work in your project?
**A:** "I use `concurrent.futures.ThreadPoolExecutor` with `max_workers=4`. Each of the four analysis agents (bug, timing, assertion, optimizer) is submitted as a future on the same file. Because Ollama calls are I/O-bound (HTTP requests), threads are appropriate — they don't need the GIL and the parallelism is on waiting for the server. Each future's result is captured with try/except so one agent failing doesn't crash the whole run. Sequential mode is available for CPU-constrained local models."

### Q10. What did you learn from the Phase 1 baseline evaluation?
**A:** "Phase 1 was a raw experiment: I sent RTL directly to models (`mistral`, `codellama`, `qwen2.5:3b`) with no structure. The key finding was that **all three models failed to find the real bug** in the counter (the blocking assignment). Worse, they hallucinated — `qwen2.5` invented a non-existent `always_comb` block and `rst_n` signal, and `codellama` suggested invalid syntax. This directly motivated the whole anti-hallucination and static-analysis-first design in Phases 2 and 3."

### Q11. Why did you choose Ollama and offline operation?
**A:** "Two reasons: **security/privacy** and **cost**. RTL is proprietary IP — hardware companies won't send their designs to a cloud API. Ollama runs models fully on the local machine, so the code never leaves the environment. It's also free and works offline. The trade-off is that local models are smaller and less capable, which is exactly why I had to invest in strong static analysis and validation to compensate."

### Q12. What is the role of the Fixer agent, and how do you ensure it doesn't break things?
**A:** "The Fixer agent takes the original RTL plus the reported bugs/timing/optimization findings and asks the LLM to rewrite the module. To keep it safe, the prompt enforces constraints: preserve the module name and pin interface, keep edits minimal, don't add or remove ports, don't change unrelated formatting, and return complete synthesizable SystemVerilog. The output is a JSON `{fixed_code, explanation}`. This makes the fixer a *supported* suggestion rather than a blind rewrite."

### Q13. How do you validate the generated SVA actually compiles?
**A:** "I assemble a temp file with the RTL followed by the generated SVA inserted *before* `endmodule` (inside the module scope, which is required for concurrent assertions). Then I translate the Windows path to a WSL path (`/mnt/c/...`) and run `verilator --lint-only -Wall`. If the return code is non-zero, I feed the compiler stderr back to the LLM along with the original RTL and ask it to fix the assertions, then retry — up to 3 attempts. Only SVA that passes Verilator is accepted."

### Q14. What is the semantic chunker and why did you build it?
**A:** "It's a lightweight, embedding-free RTL chunker. It extracts semantic units — always blocks and continuous assigns — from the RTL, then scores each chunk's relevance to the current query using keyword routing (e.g. clock/reset/latch/width keywords). It returns the top-K chunks under a character budget. This serves two purposes: it keeps LLM prompts small (important for small local models), and it focuses the model on the most relevant code, which reduces hallucinations. It's used by both the agents and the RAG pipeline."

### Q15. What is the RAG pipeline (rag_pipeline.py)?
**A:** "It's an extension I added for **grounded synthesis & auto-repair**. It builds a local retriever index from the semantic chunks of all RTL files, then generates a processor (e.g. RV32I module) using only identifiers from that grounding context. It has a 'declared-only gate' that rejects any generated file referencing undeclared identifiers, and a Verilator/Make repair loop that feeds compile errors back to the LLM. It's a demonstration of how to make local LLMs produce *compilable*, *grounded* RTL rather than hallucinated code."

### Q16. What would you improve next?
**A:** "Several things:
1. **Expression width evaluation** for parameterized widths — resolve `WIDTH-1:0` more generally.
2. **Stronger branch-coverage analysis** for combinational logic, to catch more subtle latch cases.
3. **Better CDC detection** using source/destination clock-domain evidence.
4. **Integration with a real open-source linter** (e.g. Verilator `--lint-only` as a first-class step, or Yosys/Slang) for broader syntax coverage.
5. **Regression test suite** for clean RTL, known-bug RTL, enums, memories, parameterized modules, and manual sensitivity lists.
6. **More capable models** and automated model benchmarking to pick the best local model per task."

### Q17. How does the project handle errors gracefully (e.g. Ollama down)?
**A:** "The `BaseAgent.call_ollama()` catches specific exceptions — read timeout, connect timeout, connection error, generic request error, and parse errors — and returns a structured dict with `success: False` and a user-friendly `error` message suggesting fixes (check `ollama serve`, pull the model, increase timeout). The agents check `success` before proceeding. The web server and CLI wrap each agent future in try/except so one failure doesn't abort the whole pipeline. And crucially, the static-analysis tier means the system still produces *some* valuable output even when the LLM is completely unavailable."

### Q18. Why is JSON used for the LLM's structured output?
**A:** "JSON gives me a **schema-constrained, programmatically parseable** output. Ollama supports `format: json` which steers the model to emit valid JSON. Each agent defines a strict JSON schema (e.g. bug agent wants `{bugs: [{type, location, problem, impact, fix}], total_bugs, severity}`). This lets me reliably extract structured results, report counts, and apply filters. The downside is LLMs sometimes wrap JSON in markdown or add text, which is why I built the robust `parse_json_response()` helper."

### Q19. What is the role of the config file and how does it support the design?
**A:** "`config/settings.json` centralizes runtime configuration: `ollama_url`, `default_model`, `timeout`, and `temperature`. `src/core/config.py` loads it with defaults and merges missing keys. The low temperature (0.1) is intentional — it makes outputs deterministic and consistent, which is what you want for verification analysis. Centralizing config means users can switch models and tune timeouts without touching code."

### Q20. How is this project a good example of your engineering/ML skills?
**A:** "It demonstrates end-to-end system design: a real backend (FastAPI), a frontend (glassmorphic SPA), concurrency, LLM integration, and prompt engineering. The most differentiating part is the **engineering rigor around LLM reliability** — I treat the LLM as an unreliable component and build deterministic static analysis, validation, and compile loops around it. This is the kind of production-grade thinking that separates a demo from a deployable tool: graceful degradation, actionable errors, audit logging, and honest 'no evidence' reporting instead of confident hallucination."

---

## 7. QUICK REFERENCE — KEY FILE MAP

| File | Role |
|------|------|
| `src/main.py` | Entry point; CLI or web mode; orchestrates agents |
| `src/web/server.py` | FastAPI app; REST endpoints; serves frontend |
| `src/core/base_agent.py` | Ollama calls, JSON parsing, logging, error handling |
| `src/core/config.py` | Loads `config/settings.json` |
| `src/core/rtl_parser.py` | pyslang static analysis + anti-hallucination validators |
| `src/core/semantic_chunker.py` | Chunks RTL; relevance scoring for prompts |
| `src/agents/bug_agent.py` | Functional/structural bug detection |
| `src/agents/timing_agent.py` | Timing/CDC/sensitivity detection |
| `src/agents/assertion_agent.py` | SVA generation + Verilator compile loop |
| `src/agents/optimize_agent.py` | Code-quality/optimization suggestions |
| `src/agents/fixer_agent.py` | Auto-repair RTL |
| `src/agents/custom_agent.py` | Custom user Q&A |
| `rag_pipeline.py` | Grounded synthesis + auto-repair (RAG extension) |
| `run_all_agents.py` | Phase-3 batch runner |
| `rtl_files/` | Sample RTL modules (counter, fifo, alu, cdc, fsm, etc.) |
| `reports/` | Generated Markdown reports |
| `logs/` | JSONL execution logs |

---

## 8. COMMON TERMS TO KNOW COLD

- **RTL** — Register Transfer Level; describes how data flows between registers.
- **SVA** — SystemVerilog Assertions; temporal property checking.
- **CDC** — Clock-Domain Crossing; metastability risk when signals cross clock domains.
- **Latch** — Level-sensitive storage; often undesired accidental inference.
- **Blocking vs non-blocking** — `=` vs `<=`; critical for sequential vs combinational logic.
- **Metastability** — Flop output in an undefined state when setup/hold violated.
- **Synchronizer** — 2-flop chain to resolve CDC metastability.
- **Sensitivity list** — signals an `always @(...)` block reacts to; `always_comb`/`@(*)` auto-detect.
- **Formal verification** — mathematically proving a design meets its properties.
- **Prompt engineering** — structuring LLM prompts (system role, JSON schema, constraints) for reliable output.
- **Hallucination** — LLM confidently generating false/unsupported content.
- **AST** — Abstract Syntax Tree; structured representation of code.

---

## 9. TALKING POINTS / STRENGTHS TO EMIT

- **Offline + privacy-first** — solves the real IP-security problem in hardware.
- **Anti-hallucination rigor** — static-analysis-first + declared-identifier gating + compile validation.
- **Defense in depth** — multiple independent layers of validation.
- **Graceful degradation** — works (partially) even when the LLM is down.
- **Two interfaces** — CLI and web dashboard, consistent results.
- **Observability** — JSONL logs + Markdown reports for audits.
- **Real parser integration** — pyslang, not just regex.
- **Honest reporting** — "no evidence-backed bugs" rather than fabrication.
