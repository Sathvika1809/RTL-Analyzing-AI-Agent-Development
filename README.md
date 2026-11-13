<div align="center">

## RTL Analysis AI Agent Development

**A hybrid static-analysis and local-LLM multi-agent framework for
Verilog/SystemVerilog verification, bug detection, assertion generation,
and automated repair.**

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![RTL](https://img.shields.io/badge/RTL-Verilog%20%2F%20SystemVerilog-blueviolet?style=flat-square)
![Ollama](https://img.shields.io/badge/LLM-Ollama%20(Local)-black?style=flat-square&logo=ollama)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
:::
</div>
------------------------------------------------------------------------

## Overview

**RTL Analysis AI Agent Development** is a local-first, multi-agent
framework for analyzing Verilog and SystemVerilog designs. It combines
deterministic parsing and structural checks with locally hosted large
language models (LLMs) through **Ollama**.

The framework is designed to make LLM-assisted RTL analysis more
reliable. Static checks identify concrete structural issues, while
specialized agents use LLM reasoning to investigate functional behavior,
timing concerns, and code quality. Before findings are included in
reports, an evidence-grounding layer checks source snippets and declared
identifiers, and applies available syntax/lint validation.

The pipeline supports both individual RTL files and multi-module
projects, with dependency-aware analysis, report generation, and
optional automated repair.

## Key Features

-   **Hierarchical multi-module analysis** --- Discovers `.v` and `.sv`
    modules, builds an instantiation dependency graph, analyzes child
    modules before their parents, and passes child-port context into
    parent analysis.
-   **Bug detection** --- Combines deterministic checks for reset
    omissions, blocking assignments in sequential logic, inferred
    latches, width mismatches, and undriven outputs with LLM-assisted
    functional analysis.
-   **Timing and CDC analysis** --- Checks for clock-domain crossing
    risks, multi-bit unsynchronized transfers, blocking assignments in
    clocked processes, and combinational sensitivity issues.
-   **SystemVerilog Assertion (SVA) generation** --- Generates reset and
    unknown-value checks, along with behavioral assertions for state,
    mutual exclusion, handshakes, and functional properties. Generated
    assertions are checked against declared identifiers and available
    lint tools.
-   **RTL optimization guidance** --- Flags hardcoded constants and
    provides suggestions for naming, redundancy, readability, and
    maintainability.
-   **Closed-loop repair** --- Uses detected bug and timing findings to
    propose RTL patches, then runs verification on the repaired design.
-   **Evidence-grounded findings** --- Validates reported source
    snippets and identifiers to reduce fabricated signals, unsupported
    line references, and irrelevant LLM output.
-   **Interactive RTL Q&A** --- Answers targeted questions about a
    design's architecture and behavior.
-   **CLI and web dashboard** --- Supports command-line analysis, batch
    execution, and a FastAPI-based web interface.
-   **Analysis caching** --- Uses SHA-256 content fingerprints to avoid
    repeating analysis when source files have not changed.

## Architecture

``` mermaid
flowchart TD
    A["RTL Project<br/>.v / .sv Files"] --> B["Module Scanner & Dependency DAG<br/>project_scan.py"]
    B --> C["Semantic Chunker<br/>semantic_chunker.py"]
    C --> D["Deterministic Static Analysis<br/>rtl_parser.py + extra_check.py"]
    C --> E["Local LLM Analysis<br/>Ollama / base_agent.py"]
    D --> F["Specialized Agents<br/>Bug · Timing · SVA · Optimizer · Fixer"]
    E --> F
    F --> G["Evidence Grounding & Lint Validation<br/>evidence.py"]
    G --> H["Reports & Telemetry<br/>Markdown · JSON · JSONL"]
```

### Analysis flow

1.  **Discover modules:** Scan the input file or directory and identify
    module declarations and instantiations.
2.  **Resolve dependencies:** Build a module dependency graph and
    determine a bottom-up analysis order.
3.  **Prepare context:** Split large RTL files into semantic chunks and
    provide relevant child-module interfaces to parent analysis.
4.  **Analyze:** Run deterministic structural checks and, when enabled,
    local-LLM analysis through specialized agents.
5.  **Validate findings:** Match evidence against source code, check
    referenced identifiers, and apply available lint validation.
6.  **Generate outputs:** Write consolidated reports and structured
    execution logs. If repair is requested, re-analyze the patched RTL.

## Technology Stack

  -----------------------------------------------------------------------
  Area                                Technologies
  ----------------------------------- -----------------------------------
  Programming language                Python 3.10+

  Hardware description languages      Verilog, SystemVerilog

  Local LLM runtime                   Ollama

  Tested LLM                          `qwen2.5-coder:7b`

  RTL parsing and analysis            `pyslang`, structural/token-based
                                      checkers

  External validation                 Verilator and/or Icarus Verilog
                                      (`iverilog`)

  Web backend                         FastAPI

  Web frontend                        HTML, CSS, JavaScript

  Outputs                             Markdown reports, JSON reports,
                                      JSONL logs
  -----------------------------------------------------------------------

> External lint tools are optional. Installing Verilator or Icarus
> Verilog enables additional syntax and assertion checks where
> supported.

## Repository Structure

``` text
.
├── config/
│   └── settings.json             # Ollama endpoint, model, context and timeout settings
├── src/
│   ├── agents/
│   │   ├── bug_agent.py          # Functional, reset, width, latch and undriven-signal analysis
│   │   ├── timing_agent.py       # CDC and sequential/combinational timing checks
│   │   ├── assertion_agent.py    # SVA generation and validation
│   │   ├── optimize_agent.py     # RTL maintainability and optimization suggestions
│   │   ├── fixer_agent.py        # RTL repair and post-fix verification
│   │   └── custom_agent.py       # Interactive RTL architectural Q&A
│   ├── core/
│   │   ├── base_agent.py         # Ollama client, structured output extraction and JSONL logging
│   │   ├── config.py             # Runtime configuration loader
│   │   ├── evidence.py           # Evidence matching, identifier checks and lint gating
│   │   ├── extra_check.py        # Additional structural and CDC heuristics
│   │   ├── pipeline.py           # Hierarchical project pipeline and report generation
│   │   ├── project_scan.py       # Module discovery, dependency ordering and SHA-256 cache
│   │   ├── rtl_parser.py         # pyslang AST and fallback structural analysis
│   │   └── semantic_chunker.py   # Context-aware chunking for large RTL files
│   ├── web/
│   │   ├── static/               # Dashboard HTML, CSS and JavaScript
│   │   └── server.py             # FastAPI web server
│   └── main.py                   # CLI and web entry point
├── benchmarks/
│   ├── run_benchmark.py          # Precision/recall and multi-agent evaluation
│   ├── unseen/                   # Held-out clean and buggy RTL modules
│   ├── real_world/               # Multi-clock CDC FIFO and FSM test designs
│   ├── labels_unseen.json        # Ground-truth labels for unseen benchmarks
│   └── labels_real.json          # Ground-truth labels for real-world benchmarks
├── rtl_files/                    # RTL regression designs: ALU, FIFO, FSM, arbiter and CDC
├── reports/                      # Generated Markdown and JSON reports
├── logs/                         # Agent execution and LLM-filter JSONL logs
├── docs/                         # Evaluation notes and design documentation
├── run_all_agents.py             # Batch multi-agent runner
└── requirements.txt              # Python dependencies
```

## Getting Started

### Prerequisites

-   Python 3.10 or later
-   [Ollama](https://ollama.com/) installed and running locally
-   Git
-   Optional: [Verilator](https://verilator.org/) or [Icarus
    Verilog](https://steveicarus.github.io/iverilog/) for external RTL
    syntax/lint checks

### 1. Clone the repository

``` bash
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_REPOSITORY_FOLDER>
```

### 2. Create and activate a virtual environment

**Windows PowerShell**

``` powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Linux / macOS**

``` bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

``` bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Set up the local LLM

Make sure Ollama is running, then pull the model:

``` bash
ollama pull qwen2.5-coder:7b
```

The model and Ollama connection settings can be adjusted in
`config/settings.json`.

## Usage

### 1. Hierarchical project analysis

The project pipeline is the recommended entry point for analyzing a
complete RTL directory or a single design.

**Run the multi-agent pipeline:**

``` bash
python -m src.core.pipeline benchmarks/real_world --model qwen2.5-coder:7b
```

**Run deterministic static analysis only (no LLM calls):**

``` bash
python -m src.core.pipeline rtl_files --static-only
```

**Force a fresh analysis without using the analysis cache:**

``` bash
python -m src.core.pipeline benchmarks/real_world --no-cache
```

### 2. Run the benchmark suite

Evaluate the framework against labeled RTL designs.

**Held-out unseen designs:**

``` bash
python benchmarks/run_benchmark.py \
    --rtl-folder benchmarks/unseen \
    --labels benchmarks/labels_unseen.json
```

**Real-world CDC and FSM designs:**

``` bash
python benchmarks/run_benchmark.py \
    --rtl-folder benchmarks/real_world \
    --labels benchmarks/labels_real.json
```

The benchmark harness evaluates detection performance using the supplied
ground-truth labels. Review the generated benchmark output for the
measured precision and recall.

### 3. Launch the web dashboard

``` bash
python src/main.py --web
```

Open the dashboard in your browser:

<http://127.0.0.1:8000>

### 4. Run single-file or batch analysis

**Analyze one RTL file:**

``` bash
python src/main.py --cli --file rtl_files/counter.sv
```

**Run agents over a directory:**

``` bash
python run_all_agents.py \
    --rtl-folder rtl_files \
    --output-folder reports \
    --model qwen2.5-coder:7b
```

## Design Highlights

### Hybrid static analysis and LLM reasoning

LLMs can provide useful behavioral insight, but using an LLM alone to
review RTL can lead to fabricated signal names, incorrect line
references, and unsupported timing warnings. This project combines two
complementary approaches:

-   **Static analysis** provides repeatable checks for structural and
    common RTL coding issues.
-   **LLM analysis** adds contextual reasoning for functional behavior
    and design-level questions.

This division helps keep deterministic checks independent of model
output while still benefiting from LLM-assisted analysis.

### Evidence-grounded validation

The evidence layer (`src/core/evidence.py`) validates candidate findings
before they are reported. Depending on the finding and available tools,
it checks:

-   Whether the cited source snippet exists in the RTL.
-   Whether referenced ports, signals, and parameters are declared.
-   Whether generated assertions use valid module identifiers.
-   Whether external syntax or lint checks accept the generated output.

These checks are intended to reduce unsupported findings; they do not
guarantee that every reported issue is a real design bug or that every
generated assertion is functionally complete.

### Local-first execution

RTL source can contain proprietary or sensitive design information. The
framework uses Ollama for local model inference, so prompts and RTL can
be processed on the developer's machine rather than being sent to a
hosted LLM API. Network access may still be required for initial setup,
dependency installation, or model downloads.

### Hierarchical analysis and caching

For multi-module projects, the scanner builds a dependency graph and
analyzes instantiated child modules before their parents. SHA-256
content fingerprints support cache reuse when source files remain
unchanged.

## Evaluation

The repository includes two labeled RTL benchmark suites:

-   **Unseen suite:** Held-out clean and buggy modules for evaluating
    generalization.
-   **Real-world suite:** More involved designs, including multi-clock
    CDC FIFO and FSM scenarios.

Run the benchmark commands above to calculate performance against the
checked-in labels. Reported precision and recall depend on the benchmark
contents, label quality, tool configuration, and selected model.

## Limitations

-   LLM-generated findings and repairs require engineering review before
    use in a hardware project.
-   Static checks are heuristic and cannot prove the absence of
    functional, timing, or CDC defects.
-   CDC verification in particular depends on design intent, clock
    relationships, reset strategy, and constraints that may not be fully
    inferable from RTL alone.
-   External lint and simulation tools provide additional checks, but
    lint success is not equivalent to functional verification or formal
    proof.
-   Automated repair should be treated as a proposed patch; review and
    test the resulting RTL before integration.

## Contributing

Contributions, bug reports, and suggestions are welcome. When submitting
a change, include a concise description of the issue or enhancement and,
where possible, a small RTL example or benchmark case that demonstrates
it.

## License

This project is licensed under the [MIT License](LICENSE).
