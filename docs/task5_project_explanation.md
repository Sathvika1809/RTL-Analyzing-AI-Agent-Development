# Task 5: RTL Analysis AI Agent Development

## 1. Project Overview

This project focuses on developing an AI-based assistant that can analyze RTL/SystemVerilog code and generate useful engineering feedback. The assistant should help RTL designers and verification engineers review large hardware design codebases more efficiently.

Modern RTL projects often contain many modules, pipeline stages, clock/reset domains, parameters, assertions, and verification requirements. Manual review of such code takes time and may miss issues related to coding style, synthesis risks, timing, pipeline hazards, or missing verification checks.

The goal of this task is to build a prototype AI-agent framework that can read RTL files, understand the design context, identify possible issues, suggest improvements, and generate verification guidance such as SystemVerilog Assertions (SVA).

The project should use a locally deployable LLM framework such as Ollama so that RTL analysis can be performed without depending on cloud-based tools.

## 2. Problem Statement

Traditional RTL tools such as simulators, linters, and synthesis tools are good at detecting syntax errors, structural problems, and some rule violations. However, they usually do not provide deep contextual reasoning about the design intent.

They may not fully explain:

- Why a piece of RTL may create timing problems.
- Whether a pipeline stage is missing valid/ready handling.
- Whether reset behavior is consistent across modules.
- Whether a design has latch inference risk.
- Whether assertions are missing for important protocol behavior.
- Whether the code is readable and maintainable.
- Whether the implementation matches the expected architecture.

Because of this, engineers still spend a lot of effort manually reviewing RTL. This project proposes an AI-agent-based RTL assistant that can support engineers by performing automated contextual analysis.

## 3. Main Objective

The main objective is to design and develop a prototype RTL analysis AI agent that can:

- Accept one or more RTL/SystemVerilog files as input.
- Parse and organize the files for analysis.
- Use a local LLM backend to review the RTL.
- Identify possible design and coding issues.
- Detect latch inference risks and weak coding patterns.
- Comment on timing and pipeline concerns.
- Suggest possible RTL improvements.
- Generate useful SVA assertion ideas.
- Produce structured Markdown or JSON analysis reports.
- Support future extension into EDA workflows.

The expected result is not a perfect replacement for simulators or lint tools. Instead, it should act as an intelligent assistant that helps engineers review RTL faster and more systematically.

## 4. What Needs To Be Done

The project should be completed in a staged manner. Each stage should produce a clear output that can be tested and documented.

## 5. Phase 1: Environment Setup and Baseline Evaluation

### 5.1 Install Required Tools

Set up the development environment needed for the project.

Recommended tools:

- Python 3.x
- Ollama
- A local LLM model suitable for code analysis
- SystemVerilog sample files
- Git for version control
- Markdown or JSON report generation support

### 5.2 Configure Ollama

Install Ollama and download one or more local models. The model should be tested using simple RTL-related prompts.

Example tasks for model testing:

- Explain a small Verilog module.
- Identify a missing reset condition.
- Suggest an assertion for a counter.
- Detect possible latch inference in an always_comb block.

### 5.3 Baseline Model Evaluation

Before building the full agent, evaluate how well the model performs on basic RTL analysis tasks.

The baseline evaluation should check:

- Accuracy of bug identification.
- Quality of explanations.
- Ability to understand SystemVerilog syntax.
- Ability to generate useful assertions.
- Consistency of responses.
- Hallucination risk.

### 5.4 Expected Output of Phase 1

At the end of Phase 1, the following should be available:

- Working local LLM setup.
- Notes on selected model behavior.
- Example RTL prompts and responses.
- Initial observations on strengths and limitations.

## 6. Phase 2: RTL Analysis Agent Development

This phase focuses on building the core Python automation framework.

### 6.1 Input File Handling

The tool should accept RTL files as input. It should support:

- Single-file analysis.
- Multi-file folder-based analysis.
- Common RTL extensions such as `.v`, `.sv`, and `.svh`.

The tool should scan the input path, collect RTL files, and prepare them for analysis.

### 6.2 RTL Parsing and Preprocessing

The system should extract useful information from the RTL files before sending them to the LLM.

Important information to extract:

- Module names.
- Port lists.
- Parameters.
- Always blocks.
- Assign statements.
- Clock and reset signals.
- Instantiated submodules.
- Comments, if useful for understanding design intent.

The first prototype can use lightweight parsing with Python. Later, the project can be extended to use proper parsers such as Surelog, Slang, PyVerilog, or tree-sitter.

### 6.3 Prompt Design

The quality of the AI agent depends heavily on prompt structure. The prompt should guide the model to behave like an RTL review assistant.

The prompt should ask the model to report:

- Functional bugs.
- Latch inference risks.
- Reset and clocking issues.
- Pipeline and timing concerns.
- Coding style problems.
- Missing assertions.
- Suggested improvements.
- Confidence level for each issue.

The model should be instructed to avoid making unsupported claims and to clearly separate confirmed issues from possible concerns.

### 6.4 File-Level Analysis

Each RTL file should be analyzed independently first.

For every file, the agent should generate:

- Summary of module functionality.
- List of detected issues.
- Severity of each issue.
- Explanation of why the issue matters.
- Suggested fix or improvement.
- Suggested assertions, if applicable.

### 6.5 Structured Report Generation

The analysis output should be stored in a structured format.

Recommended formats:

- Markdown report for human reading.
- JSON output for future automation.

A good Markdown report should include:

- Project name.
- Date of analysis.
- Files analyzed.
- Module summaries.
- Issues found.
- Suggested fixes.
- SVA suggestions.
- Limitations of the analysis.

### 6.6 Expected Output of Phase 2

At the end of Phase 2, the following should be available:

- Python-based RTL analysis script or package.
- Ability to analyze multiple RTL files.
- LLM integration through Ollama.
- Markdown report generation.
- Basic issue classification.
- Example reports generated from sample RTL files.

## 7. Phase 3: Agent Specialization

After the basic agent works, the next step is to divide the analysis into specialized agents. Each agent should focus on one engineering task.

### 7.1 Bug Analysis Agent

This agent should focus on functional correctness.

It should check for:

- Missing assignments.
- Incorrect conditional logic.
- Width mismatch risks.
- Uninitialized signals.
- Incorrect reset behavior.
- Possible combinational loops.
- Incorrect state machine transitions.

### 7.2 Timing and Pipeline Review Agent

This agent should focus on performance and timing risks.

It should check for:

- Long combinational paths.
- Deep arithmetic logic in one cycle.
- Missing pipeline registers.
- Valid/ready misalignment.
- Backpressure handling issues.
- Clock-domain crossing concerns.
- Reset-domain consistency.

### 7.3 Assertion Generation Agent

This agent should suggest SystemVerilog Assertions.

It should generate assertions for:

- Reset behavior.
- Handshake protocols.
- FIFO full/empty rules.
- Counter bounds.
- State machine legal transitions.
- Request/acknowledge behavior.
- Data stability during stall cycles.

The generated assertions should be reviewed carefully because LLM-generated SVA may be incomplete or syntactically incorrect.

### 7.4 Code Optimization Agent

This agent should suggest improvements for readability, synthesis quality, and maintainability.

It should check for:

- Repeated logic that can be simplified.
- Unclear signal naming.
- Overly complex always blocks.
- Inefficient case statements.
- Missing default assignments.
- Poor separation of combinational and sequential logic.

### 7.5 Final Agent Orchestration

The main framework should coordinate all specialized agents and combine their results into a final report.

The recommended flow is:

1. Collect RTL files.
2. Extract module-level information.
3. Run Bug Analysis Agent.
4. Run Timing and Pipeline Review Agent.
5. Run Assertion Generation Agent.
6. Run Code Optimization Agent.
7. Merge results.
8. Generate final Markdown and JSON reports.

## 8. Suggested System Architecture

The proposed architecture can be organized as follows:

```text
User Input
   |
   v
RTL File Collector
   |
   v
RTL Parser / Preprocessor
   |
   v
Context Builder
   |
   v
Agent Orchestrator
   |
   +--> Bug Analysis Agent
   +--> Timing/Pipeline Agent
   +--> Assertion Generation Agent
   +--> Optimization Agent
   |
   v
Result Merger
   |
   v
Markdown / JSON Report Generator
```

## 9. Expected Features

The prototype should support the following features:

- Command-line execution.
- Input path selection.
- Automatic RTL file discovery.
- Local LLM inference using Ollama.
- File-level analysis.
- Multi-agent review flow.
- Markdown report generation.
- Optional JSON report generation.
- Clear issue severity classification.
- Suggested RTL fixes.
- Suggested SVA properties.
- Documentation of limitations.

## 10. Example Command-Line Usage

The final tool may be used like this:

```bash
python rtl_ai_agent.py --input ./rtl --output ./reports
```

Expected generated files:

```text
reports/
  rtl_analysis_report.md
  rtl_analysis_report.json
```

## 11. Expected Final Deliverables

At the end of the project, the following deliverables are expected:

- Prototype AI-agent RTL assistant.
- Python automation framework.
- Ollama/local LLM integration.
- RTL file collection and preprocessing flow.
- Bug analysis capability.
- Timing and pipeline review capability.
- SVA suggestion capability.
- Code improvement suggestion capability.
- Multi-file analysis support.
- Markdown report generation.
- JSON structured output support, if possible.
- Sample RTL test cases.
- Example generated reports.
- Final project documentation explaining design, usage, results, and limitations.

## 12. Testing Plan

The tool should be tested using small RTL examples with known issues.

Recommended test cases:

- A combinational block with missing default assignment.
- A sequential block without reset.
- A counter with overflow risk.
- A finite state machine with missing state transition.
- A valid/ready pipeline with stall handling issue.
- A module with width mismatch.
- A FIFO-like module requiring assertions.

For each test case, compare the AI agent output with the expected issue list.

## 13. Evaluation Criteria

The project can be evaluated using the following criteria:

- Correctness of detected RTL issues.
- Usefulness of suggested fixes.
- Quality of generated assertions.
- Clarity of generated reports.
- Ability to process multiple files.
- Consistency of LLM responses.
- Practicality of local LLM execution.
- Extensibility of the software architecture.

## 14. Important Limitations

The project must clearly mention the limitations of LLM-based RTL analysis.

Important limitations include:

- LLMs may hallucinate issues.
- Generated SVA may need manual correction.
- The model may miss subtle bugs.
- The model may not understand complete multi-module behavior.
- Local models may have limited context length.
- Results may vary across models and prompts.
- AI analysis should not replace simulation, linting, formal verification, or synthesis.

The final report should clearly state that the AI agent is an assistant for engineering review, not a fully trusted verification tool.

## 15. Step-by-Step Work Plan

### Step 1: Study the Problem

Understand why RTL review is difficult and what kind of problems engineers usually check manually.

### Step 2: Study Existing Tools

Briefly study simulators, lint tools, formal tools, and AI-based code assistants to understand where this project fits.

### Step 3: Set Up Ollama

Install Ollama and test at least one local model using RTL prompts.

### Step 4: Create Sample RTL Files

Prepare small SystemVerilog examples with known bugs and known expected behavior.

### Step 5: Build File Collection Script

Write Python code that scans a folder and collects `.v`, `.sv`, and `.svh` files.

### Step 6: Build RTL Preprocessing

Extract module names, ports, parameters, always blocks, and other useful context.

### Step 7: Design Prompts

Create structured prompts for RTL review, bug analysis, timing review, assertion generation, and optimization.

### Step 8: Connect Python With Ollama

Send RTL context to the local model and collect the response automatically.

### Step 9: Generate File-Level Reports

Save the model response for each file in a readable report format.

### Step 10: Add Specialized Agents

Split the analysis into separate agents for bugs, timing, assertions, and optimization.

### Step 11: Merge Agent Results

Combine all agent outputs into one final report.

### Step 12: Validate Using Test RTL

Run the tool on known examples and compare the result with expected findings.

### Step 13: Improve Prompts and Output Format

Refine prompts to reduce hallucination and improve consistency.

### Step 14: Document Practical Observations

Record what worked well, what failed, and where local LLMs are useful or limited.

### Step 15: Prepare Final Submission

Submit the code, reports, sample RTL files, architecture explanation, and final documentation.

## 16. Final Expected Outcome

The final outcome should be a working prototype of an RTL Analysis AI Agent. It should demonstrate that local LLM-based agents can assist in RTL review by identifying common bugs, suggesting improvements, and generating verification ideas.

The project should prove the practicality of an AI-assisted RTL engineering workflow while also clearly explaining that expert human review and standard EDA tools are still required for final signoff.
