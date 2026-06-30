# RTL Analysis AI Agent — Complete Steering Document
**Task 5 | SystemVerilog Intelligence Framework**

---

## How to Use This Document

Read **top to bottom**. Each phase builds on the previous one. Skipping ahead will cause dependency failures. Every step has:
- **What you're doing** — the goal of the step
- **Why you're doing it** — the reasoning behind it
- **How to do it** — exact commands and code
- **Resources** — where to learn more

Estimated total effort: **4–6 weeks** for a working prototype.

---

## Architecture Overview

```
RTL Files (.sv/.v)
       │
       ▼
┌─────────────────────┐
│  Python Parser Layer │  ← PyVerilog / regex-based AST extraction
└─────────┬───────────┘
          │ structured context
          ▼
┌─────────────────────┐
│  Agent Orchestrator  │  ← LangChain / custom Python dispatcher
└─────────┬───────────┘
          │ prompts + context
          ▼
┌─────────────────────┐
│   Ollama LLM Server  │  ← DeepSeek-Coder / CodeLlama / Mistral
└─────────┬───────────┘
          │ structured response
          ▼
┌─────────────────────┐
│   Report Generator   │  ← Markdown / JSON / HTML output
└─────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| LLM Runtime | Ollama | Local model serving |
| Primary Model | DeepSeek-Coder-V2 or CodeLlama-34B | RTL analysis tasks |
| Fallback Model | Mistral-7B or Qwen2.5-Coder | Lighter tasks |
| RTL Parsing | PyVerilog | Module/port/signal extraction |
| Agent Framework | LangChain + custom Python | Multi-agent orchestration |
| Output | JSON + Markdown | Reports and structured data |
| Linting (optional) | Verilator | Pre-validation before LLM |
| Language | Python 3.10+ | All agent code |

---

# PHASE 0 — Prerequisites and Learning Foundation
**Duration: 3–5 days**

Before writing any code, you need baseline knowledge in three areas. Do not skip this phase.

---

## Step 0.1 — Understand SystemVerilog RTL Fundamentals

### What you're doing
Building mental context so you can write good prompts and evaluate whether the LLM output is correct or hallucinated.

### What to study

**RTL Concepts to Know:**
- Combinational vs Sequential logic (always_comb, always_ff)
- Clocking: posedge/negedge, multi-clock domains
- Latch inference: when an `if` without `else` in always_comb creates a latch
- Pipeline stages: registers between logic stages, hazards (RAW, WAW, WAR)
- Reset strategies: synchronous vs asynchronous reset
- Parameterized modules: `parameter`, `localparam`, `generate`
- SystemVerilog Assertions (SVA): `assert property`, `assume`, `cover`

**Resources:**
- **Book:** *SystemVerilog for Design* — Stuart Sutherland (best reference for RTL coding)
- **Book:** *Writing Testbenches Using SystemVerilog* — Janick Bergeron
- **Free:** https://www.asic-world.com/systemverilog/ — compact SV reference
- **Free:** https://verificationacademy.com/topics/systemverilog/ — SVA and verification focus
- **Free:** IEEE Std 1800-2017 (SystemVerilog LRM) — authoritative, but dense

**RTL Anti-patterns to memorize (these are what your agent will detect):**

```systemverilog
// ANTI-PATTERN 1: Latch Inference
always_comb begin
    if (enable)
        out = in;   // No else! Creates a latch.
end

// ANTI-PATTERN 2: Incomplete sensitivity list (in Verilog-2001)
always @(a)       // Missing b — simulation/synthesis mismatch
    out = a & b;

// ANTI-PATTERN 3: Blocking assignment in sequential logic
always_ff @(posedge clk) begin
    a = b;         // Should be <= (nonblocking)
    c = a;         // Race condition
end

// ANTI-PATTERN 4: Async reset without synchronizer
always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) data <= 0;  // OK if single domain, risky across domains
end

// ANTI-PATTERN 5: Magic numbers (no parameter)
if (count == 8'd255)  // What does 255 mean? Use a parameter.
```

---

## Step 0.2 — Understand LLM Agent Concepts

### What you're doing
Learning how LLM-based agents work so you can design your system correctly.

### Key concepts

**Prompt Engineering:**
- System prompts: set the LLM's role and constraints
- Few-shot examples: show the model examples of desired input/output pairs
- Chain-of-thought: ask the model to reason step by step before giving an answer
- Structured output: ask for JSON with a defined schema

**Agents:**
- A "tool-using" LLM that can call functions (e.g., read a file, run a linter)
- ReAct pattern: Reason → Act → Observe → Repeat
- In your project: each specialized agent is a Python function that sends a focused prompt

**Resources:**
- https://python.langchain.com/docs/ — LangChain documentation
- https://www.promptingguide.ai/ — free prompt engineering guide
- https://ollama.com/docs — Ollama official docs
- Paper: *ReAct: Synergizing Reasoning and Acting in Language Models* (arXiv:2210.03629)

---

## Step 0.3 — Understand PyVerilog

### What you're doing
Learning the parsing library that will convert your .sv files into structured data.

### Key concepts
- PyVerilog parses Verilog/SV into an Abstract Syntax Tree (AST)
- You extract: module names, ports, parameters, always blocks, assign statements
- This structured data becomes the context you feed to the LLM

**Resources:**
- https://github.com/PyHDI/Pyverilog — GitHub repo with examples
- https://pyverilog.readthedocs.io/ — API reference

---

# PHASE 1 — Environment Setup and Baseline Evaluation
**Duration: 5–7 days**

---

## Step 1.1 — Set Up Your Development Environment

### What you're doing
Creating an isolated Python environment and installing all dependencies so your project is reproducible.

### Why
Python dependency conflicts are the #1 cause of wasted time. Always use virtual environments.

### How to do it

```bash
# 1. Create project directory structure
mkdir rtl_ai_agent
cd rtl_ai_agent
mkdir -p {agents,parsers,prompts,reports,rtl_samples,tests,utils}

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate          # Linux/Mac
# venv\Scripts\activate           # Windows

# 3. Install core dependencies
pip install langchain langchain-community langchain-ollama
pip install pyverilog
pip install rich                  # Beautiful terminal output
pip install jinja2                # Report templating
pip install pytest                # Testing
pip install python-dotenv         # Config management

# 4. Save your dependencies
pip freeze > requirements.txt
```

**Project structure you're building:**
```
rtl_ai_agent/
├── agents/
│   ├── __init__.py
│   ├── bug_agent.py
│   ├── timing_agent.py
│   ├── assertion_agent.py
│   └── optimizer_agent.py
├── parsers/
│   ├── __init__.py
│   └── sv_parser.py
├── prompts/
│   ├── bug_analysis.txt
│   ├── timing_review.txt
│   ├── assertion_gen.txt
│   └── optimization.txt
├── reports/
│   └── templates/
│       └── report.md.j2
├── rtl_samples/
│   └── sample_counter.sv
├── tests/
│   └── test_parser.py
├── utils/
│   ├── __init__.py
│   └── output_parser.py
├── main.py
├── orchestrator.py
├── config.py
└── requirements.txt
```

---

## Step 1.2 — Install and Configure Ollama

### What you're doing
Setting up Ollama, the local LLM runtime that serves your AI models.

### Why
Ollama abstracts away GPU/CPU model loading, provides an OpenAI-compatible API, and lets you run models completely offline. This is critical for RTL work where code confidentiality matters.

### How to do it

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh

# macOS
brew install ollama

# Windows: Download installer from https://ollama.com/download
```

**Start the Ollama server:**
```bash
ollama serve   # Run this in a separate terminal, keep it running
```

**Pull models (run these one at a time — they are large):**
```bash
# Primary model: best for code tasks (16B parameters, ~10GB)
ollama pull deepseek-coder-v2:16b

# Lightweight alternative (~4GB, faster)
ollama pull codellama:13b

# General reasoning (good for assertions and analysis)
ollama pull mistral:7b

# Verify models are loaded
ollama list
```

**Test Ollama is working:**
```bash
ollama run deepseek-coder-v2:16b "What is a latch in RTL design?"
# You should get a coherent explanation. If not, check GPU memory.
```

**Hardware requirements:**
| Model | VRAM (GPU) | RAM (CPU) | Speed |
|-------|-----------|----------|-------|
| 7B model | 6–8 GB | 16 GB | Fast |
| 13B model | 10–12 GB | 24 GB | Medium |
| 16B model | 14–16 GB | 32 GB | Slower |
| 34B model | 24+ GB | 64 GB | Slow |

If you don't have enough VRAM, Ollama offloads to CPU (slow but functional). Start with a 7B model if hardware is limited.

---

## Step 1.3 — Write a Baseline RTL Test File

### What you're doing
Creating a known-buggy SystemVerilog file to use as ground truth for testing your agent.

### Why
You need a controlled test case with known problems to verify your agent is actually detecting real issues, not hallucinating.

**Create `rtl_samples/sample_counter.sv`:**
```systemverilog
// sample_counter.sv — Intentionally contains multiple issues for testing
// Issues planted:
// 1. Latch inference (missing else in always_comb)
// 2. Blocking assignment in sequential block
// 3. Magic number (no parameter)
// 4. No SVA assertions
// 5. Missing default in case statement

module counter #(
    parameter WIDTH = 8
)(
    input  logic        clk,
    input  logic        rst_n,
    input  logic        enable,
    input  logic        load,
    input  logic [7:0]  load_val,
    output logic [7:0]  count,
    output logic        overflow
);

    // Issue 1: Blocking assignment in sequential block
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count = 8'd0;      // BUG: Should be <=
            overflow = 1'b0;   // BUG: Should be <=
        end else if (enable) begin
            if (load)
                count <= load_val;
            else
                count <= count + 1;
        end
    end

    // Issue 2: Latch inference — no else branch
    logic next_overflow;
    always_comb begin
        if (count == 8'd255)   // Issue 3: Magic number
            next_overflow = 1'b1;
        // Missing else: latch created!
    end

    // Issue 4: Case without default
    logic [1:0] state;
    always_comb begin
        case (state)
            2'b00: overflow = next_overflow;
            2'b01: overflow = 1'b0;
            2'b10: overflow = 1'b1;
            // Missing: 2'b11 case — synthesis warning
        endcase
    end

endmodule
```

---

## Step 1.4 — Baseline Prompt Testing (Manual)

### What you're doing
Before writing automation code, manually test prompts against your LLM to understand what it can and can't do.

### Why
This calibrates your expectations. LLMs behave differently on RTL tasks depending on model size and prompt quality. Establish a baseline before building agents.

**Write a test script `tests/baseline_test.py`:**
```python
"""
Baseline test: Send raw RTL to LLM and measure output quality.
Run this BEFORE building any agent infrastructure.
"""
import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "deepseek-coder-v2:16b"

def query_ollama(prompt: str, model: str = MODEL) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,  # Low temp = more deterministic
            "top_p": 0.9,
            "num_predict": 2048
        }
    }
    response = requests.post(OLLAMA_URL, json=payload)
    return response.json()["response"]

# Load the test RTL file
with open("rtl_samples/sample_counter.sv", "r") as f:
    rtl_code = f.read()

# Test 1: Basic bug detection
prompt_v1 = f"""You are an expert RTL design engineer reviewing SystemVerilog code.
Analyze the following code and list all bugs and coding issues you find.

```systemverilog
{rtl_code}
```

Format your response as:
BUG 1: [description]
LINE: [line number if known]
SEVERITY: [CRITICAL/WARNING/INFO]
FIX: [suggested correction]
"""

print("=== Test 1: Basic Bug Detection ===")
result = query_ollama(prompt_v1)
print(result)
print("\n" + "="*50 + "\n")

# Test 2: Structured JSON output
prompt_v2 = f"""Analyze this SystemVerilog code for bugs. 
Return ONLY a JSON array (no other text, no markdown) with this schema:
[
  {{
    "issue_type": "latch|blocking_assign|missing_default|magic_number|other",
    "description": "brief description",
    "line_hint": "approximate location",
    "severity": "critical|warning|info",
    "fix": "corrected code snippet"
  }}
]

CODE:
{rtl_code}"""

print("=== Test 2: JSON Structured Output ===")
result = query_ollama(prompt_v2)
print(result)

# Try to parse as JSON
try:
    issues = json.loads(result)
    print(f"\n✓ Successfully parsed {len(issues)} issues as JSON")
except json.JSONDecodeError as e:
    print(f"\n✗ JSON parse failed: {e}")
    print("The model returned non-JSON — prompt engineering needed")
```

**Run it:**
```bash
python tests/baseline_test.py
```

**What to look for in results:**
- Does it catch the latch inference? (Most models do)
- Does it catch the blocking assignment? (Harder)
- Is the JSON parseable? (Critical for automation)
- Does it hallucinate issues that don't exist? (Note these)

**Record your findings** in a file `tests/baseline_results.md`. This becomes your benchmark.

---

## Step 1.5 — Evaluate Model Suitability

### What you're doing
Running a structured comparison of different models on the same RTL tasks.

### Evaluation Criteria
Create a score for each model (0–5 per category):

| Category | What to check |
|----------|--------------|
| Bug detection accuracy | Did it find the planted bugs? |
| False positive rate | Did it invent bugs that aren't there? |
| JSON adherence | Did structured output parse cleanly? |
| SVA quality | Are generated assertions syntactically valid? |
| Speed | Time to first token + total response time |

**Quick comparison test:**
```bash
# Time the response from different models
time ollama run codellama:13b "$(cat tests/baseline_prompt.txt)"
time ollama run deepseek-coder-v2:16b "$(cat tests/baseline_prompt.txt)"
time ollama run mistral:7b "$(cat tests/baseline_prompt.txt)"
```

Choose your primary model based on this evaluation. For most hardware setups, `deepseek-coder-v2:16b` gives the best quality/speed tradeoff for code tasks.

---

# PHASE 2 — RTL Analysis Agent Development
**Duration: 10–14 days**

---

## Step 2.1 — Build the RTL Parser

### What you're doing
Creating a Python module that reads .sv files and extracts structural metadata before sending anything to the LLM.

### Why
Sending raw RTL to an LLM with no context is like asking someone to review code with no description. Pre-parsing lets you:
- Extract only the relevant section (e.g., one always block)
- Tell the LLM the module name, ports, and parameters upfront
- Stay within context window limits (RTL files can be huge)

**Create `parsers/sv_parser.py`:**
```python
"""
sv_parser.py — SystemVerilog structural parser using PyVerilog
Extracts metadata without needing to send full file to LLM every time.
"""
import re
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path

# PyVerilog imports (install: pip install pyverilog)
try:
    import pyverilog.vparser.parser as vparser
    from pyverilog.vparser.ast import (
        ModuleDef, Portlist, Port, Decl, Input, Output, Inout,
        Always, AlwaysFF, AlwaysComb, Assign, IfStatement, CaseStatement
    )
    PYVERILOG_AVAILABLE = True
except ImportError:
    PYVERILOG_AVAILABLE = False
    print("WARNING: PyVerilog not installed. Falling back to regex parser.")


@dataclass
class PortInfo:
    name: str
    direction: str   # input, output, inout
    width: str       # e.g., "[7:0]" or "1-bit"
    data_type: str   # logic, wire, reg


@dataclass
class SignalInfo:
    name: str
    width: str
    signal_type: str  # logic, wire, reg, parameter


@dataclass
class AlwaysBlockInfo:
    block_type: str    # always_ff, always_comb, always_latch, always
    sensitivity: str   # e.g., "posedge clk or negedge rst_n"
    line_number: int
    raw_code: str


@dataclass
class ModuleInfo:
    name: str
    file_path: str
    parameters: Dict[str, str] = field(default_factory=dict)
    ports: List[PortInfo] = field(default_factory=list)
    signals: List[SignalInfo] = field(default_factory=list)
    always_blocks: List[AlwaysBlockInfo] = field(default_factory=list)
    raw_code: str = ""
    line_count: int = 0


class RTLParser:
    """
    Parses SystemVerilog files and extracts structural information.
    Falls back to regex-based parsing if PyVerilog is not available.
    """

    def parse_file(self, filepath: str) -> List[ModuleInfo]:
        """Parse an RTL file and return list of modules found."""
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"RTL file not found: {filepath}")

        with open(filepath, 'r') as f:
            raw_code = f.read()

        if PYVERILOG_AVAILABLE:
            return self._parse_with_pyverilog(str(filepath), raw_code)
        else:
            return self._parse_with_regex(str(filepath), raw_code)

    def _parse_with_pyverilog(self, filepath: str, raw_code: str) -> List[ModuleInfo]:
        """Use PyVerilog AST for accurate parsing."""
        try:
            ast, _ = vparser.parse([filepath])
            modules = []
            for item in ast.description.definitions:
                if isinstance(item, ModuleDef):
                    mod = ModuleInfo(
                        name=item.name,
                        file_path=filepath,
                        raw_code=raw_code,
                        line_count=len(raw_code.splitlines())
                    )
                    # Extract ports, parameters, always blocks
                    # (walk the AST — see PyVerilog docs for full visitor pattern)
                    modules.append(mod)
            return modules
        except Exception as e:
            print(f"PyVerilog parse error: {e}. Falling back to regex.")
            return self._parse_with_regex(filepath, raw_code)

    def _parse_with_regex(self, filepath: str, raw_code: str) -> List[ModuleInfo]:
        """Regex-based fallback parser — less accurate but always works."""
        modules = []
        lines = raw_code.splitlines()

        # Find all module definitions
        module_pattern = re.compile(
            r'^\s*module\s+(\w+)\s*(?:#\s*\(([^)]*)\))?\s*\(', re.MULTILINE
        )

        for match in module_pattern.finditer(raw_code):
            mod_name = match.group(1)
            mod = ModuleInfo(
                name=mod_name,
                file_path=filepath,
                raw_code=raw_code,
                line_count=len(lines)
            )

            # Extract parameters
            param_pattern = re.compile(
                r'parameter\s+(?:\w+\s+)?(\w+)\s*=\s*([^,;)]+)'
            )
            for p in param_pattern.finditer(raw_code):
                mod.parameters[p.group(1).strip()] = p.group(2).strip()

            # Extract ports (simplified)
            port_pattern = re.compile(
                r'(input|output|inout)\s+(?:logic|wire|reg)?\s*'
                r'(\[[\d\s:\w-]+\])?\s*(\w+)'
            )
            for p in port_pattern.finditer(raw_code):
                mod.ports.append(PortInfo(
                    name=p.group(3),
                    direction=p.group(1),
                    width=p.group(2) or "1-bit",
                    data_type="logic"
                ))

            # Extract always blocks
            always_pattern = re.compile(
                r'(always_ff|always_comb|always_latch|always)\s*'
                r'(?:@\s*\(([^)]+)\))?\s*begin',
                re.MULTILINE
            )
            for a in always_pattern.finditer(raw_code):
                line_num = raw_code[:a.start()].count('\n') + 1
                mod.always_blocks.append(AlwaysBlockInfo(
                    block_type=a.group(1),
                    sensitivity=a.group(2) or "combinational",
                    line_number=line_num,
                    raw_code=self._extract_block(raw_code, a.start())
                ))

            modules.append(mod)

        return modules

    def _extract_block(self, code: str, start_pos: int, 
                        max_lines: int = 50) -> str:
        """Extract a begin/end block starting at start_pos."""
        depth = 0
        i = start_pos
        start_found = False
        block_start = start_pos

        while i < len(code) and (i - start_pos) < max_lines * 80:
            if code[i:i+5] == 'begin':
                if not start_found:
                    start_found = True
                    block_start = i
                depth += 1
                i += 5
            elif code[i:i+3] == 'end' and code[i+3:i+4] not in ['c','m']:
                depth -= 1
                i += 3
                if depth == 0:
                    return code[start_pos:i]
            else:
                i += 1

        # Fallback: return first max_lines lines
        lines = code[start_pos:].splitlines()[:max_lines]
        return '\n'.join(lines)

    def get_summary(self, module: ModuleInfo) -> str:
        """
        Generate a human-readable summary of a module.
        This is what gets sent to the LLM as context (not the full file).
        """
        summary = f"""MODULE: {module.name}
FILE: {module.file_path}
LINES: {module.line_count}

PARAMETERS:
{chr(10).join(f'  - {k} = {v}' for k, v in module.parameters.items()) or '  None'}

PORTS ({len(module.ports)} total):
{chr(10).join(f'  - {p.direction:8} {p.width:12} {p.name}' for p in module.ports) or '  None'}

ALWAYS BLOCKS ({len(module.always_blocks)} total):
{chr(10).join(f'  - {a.block_type} @({a.sensitivity}) [line {a.line_number}]' for a in module.always_blocks) or '  None'}
"""
        return summary


# Test the parser
if __name__ == "__main__":
    parser = RTLParser()
    modules = parser.parse_file("rtl_samples/sample_counter.sv")
    for mod in modules:
        print(parser.get_summary(mod))
        print("\nFull code snippet (first 20 lines):")
        print('\n'.join(mod.raw_code.splitlines()[:20]))
```

**Test the parser:**
```bash
python parsers/sv_parser.py
```

---

## Step 2.2 — Build the Ollama Client Wrapper

### What you're doing
Creating a reusable client that handles all communication with the Ollama API, including error handling, retries, and response parsing.

### Why
Every agent will need to talk to Ollama. Centralizing this avoids duplicating error-handling code and lets you swap the model in one place.

**Create `utils/ollama_client.py`:**
```python
"""
ollama_client.py — Clean wrapper for Ollama API calls.
Handles retries, timeouts, and JSON extraction from LLM responses.
"""
import json
import re
import time
import requests
from typing import Optional, Dict, Any


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "deepseek-coder-v2:16b",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout: int = 300
    ):
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        expect_json: bool = False
    ) -> str:
        """
        Send a prompt to Ollama and return the text response.
        
        Args:
            prompt: The user message
            system_prompt: Optional system message to set context/role
            expect_json: If True, attempt to extract and validate JSON
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": 0.9,
                "num_predict": self.max_tokens,
                "repeat_penalty": 1.1
            }
        }

        for attempt in range(3):
            try:
                response = requests.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()
                content = response.json()["message"]["content"]

                if expect_json:
                    return self._extract_json(content)
                return content

            except requests.exceptions.Timeout:
                print(f"Timeout on attempt {attempt+1}/3. Retrying...")
                time.sleep(5)
            except requests.exceptions.ConnectionError:
                raise RuntimeError(
                    "Cannot connect to Ollama. Is 'ollama serve' running?"
                )
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f"Ollama query failed: {e}")
                time.sleep(2)

        raise RuntimeError("All retry attempts exhausted")

    def _extract_json(self, text: str) -> str:
        """
        Extract JSON from LLM response, which may contain markdown fences.
        Returns the JSON string (caller should parse it).
        """
        # Remove markdown code fences
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'(\[[\s\S]*\])',     # Raw JSON array
            r'(\{[\s\S]*\})',     # Raw JSON object
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                candidate = match.group(1).strip()
                try:
                    json.loads(candidate)  # Validate it parses
                    return candidate
                except json.JSONDecodeError:
                    continue

        # Return original text if no JSON found — caller handles it
        return text

    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return r.status_code == 200
        except:
            return False

    def list_models(self) -> list:
        """Return list of available models."""
        r = requests.get(f"{self.base_url}/api/tags", timeout=10)
        return [m["name"] for m in r.json().get("models", [])]


# Test the client
if __name__ == "__main__":
    client = OllamaClient()
    if client.is_available():
        print("✓ Ollama is running")
        print(f"Available models: {client.list_models()}")
        
        # Quick sanity check
        result = client.query(
            "What is a latch in digital design? Answer in one sentence."
        )
        print(f"\nTest response: {result[:200]}")
    else:
        print("✗ Ollama is not running. Start it with: ollama serve")
```

---

## Step 2.3 — Build Prompt Templates

### What you're doing
Writing the actual prompts that each agent will use. Good prompts are the most important factor in output quality.

### Why
A bad prompt with a good model produces bad results. A good prompt with a medium model often outperforms a bad prompt with a large model.

**Create `prompts/bug_analysis.txt`:**
```
You are a senior RTL design engineer at a chip company with 15 years of experience in SystemVerilog design.
Your job is to perform a rigorous code review of the RTL code provided.

You are looking specifically for:
1. Latch inference (missing else in always_comb, incomplete case coverage)
2. Blocking assignments (=) used in always_ff sequential blocks (should be <=)  
3. Missing default cases in case/casex/casez statements
4. Magic numbers (hardcoded constants that should be parameters)
5. Incomplete sensitivity lists (in older always blocks)
6. Clock domain crossing (CDC) risks
7. Reset strategy issues (async reset without synchronizer, missing reset)
8. Potential simulation-synthesis mismatches
9. Signal width mismatches

IMPORTANT RULES:
- Only report issues you can actually see in the code
- Do NOT invent issues that are not present
- Be specific about line numbers or code snippets
- Provide concrete fix examples

MODULE CONTEXT:
{module_summary}

FULL CODE:
{rtl_code}

Respond with ONLY a valid JSON array. No markdown, no explanation, just the JSON:
[
  {{
    "issue_id": "BUG-001",
    "category": "latch|blocking_assign|missing_default|magic_number|cdc|reset|width_mismatch|other",
    "severity": "critical|warning|info",
    "description": "Clear description of the problem",
    "location": "approximate line number or code snippet",
    "impact": "What can go wrong if not fixed",
    "fix_code": "Corrected code snippet",
    "confidence": "high|medium|low"
  }}
]
```

**Create `prompts/assertion_gen.txt`:**
```
You are an expert in SystemVerilog Assertions (SVA) and formal verification.
Your task is to generate useful SVA assertions for the given RTL module.

Generate assertions for:
1. Data integrity: outputs are valid when enable is asserted
2. Reset behavior: all outputs reset to known values
3. Overflow/underflow conditions
4. Protocol compliance (if applicable)
5. Timing relationships between signals
6. Mutual exclusion constraints

ASSERTION TYPES TO USE:
- Immediate assertions: assert (expr)
- Concurrent properties: assert property (@(posedge clk) ...)
- Assume constraints for formal tools: assume property (...)
- Cover points: cover property (...)

MODULE CONTEXT:
{module_summary}

FULL CODE:
{rtl_code}

Generate assertions as a JSON array:
[
  {{
    "assertion_id": "SVA-001",
    "type": "immediate|concurrent|assume|cover",
    "description": "What this assertion checks",
    "code": "Complete SystemVerilog assertion code",
    "placement": "Where in the module to place this (e.g., after always_ff block)"
  }}
]

Respond with ONLY the JSON array.
```

**Create `prompts/timing_review.txt`:**
```
You are an expert in digital design timing analysis and pipeline architecture.
Analyze the provided RTL for timing and pipeline concerns.

Look for:
1. Long combinational paths (many logic levels between registers)
2. Pipeline hazards: Read-After-Write (RAW), Write-After-Read (WAR), Write-After-Write (WAW)
3. Missing pipeline registers in long data paths
4. Multi-cycle path violations (signals that need more than one clock cycle)
5. False path opportunities (signals that never change simultaneously)
6. Clock enable usage (should use CE instead of gated clocks)
7. Critical path estimation

MODULE CONTEXT:
{module_summary}

FULL CODE:
{rtl_code}

Respond with ONLY a JSON array:
[
  {{
    "concern_id": "TIM-001",
    "type": "long_combo_path|pipeline_hazard|missing_register|multi_cycle|gated_clock|other",
    "severity": "critical|warning|info",
    "description": "Description of the timing concern",
    "location": "Where in the code",
    "recommendation": "How to fix or mitigate"
  }}
]
```

---

## Step 2.4 — Build the File-Level Analysis Pipeline

### What you're doing
Creating the main analysis engine that ties parser + prompts + LLM together for a single file.

**Create `agents/base_agent.py`:**
```python
"""
base_agent.py — Abstract base class for all analysis agents.
"""
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any

from parsers.sv_parser import RTLParser, ModuleInfo
from utils.ollama_client import OllamaClient


class BaseRTLAgent(ABC):
    """Base class that all specialized agents inherit from."""

    def __init__(self, client: OllamaClient, prompt_file: str):
        self.client = client
        self.parser = RTLParser()
        self.prompt_template = self._load_prompt(prompt_file)

    def _load_prompt(self, prompt_file: str) -> str:
        path = Path("prompts") / prompt_file
        if path.exists():
            return path.read_text()
        raise FileNotFoundError(f"Prompt file not found: {path}")

    def analyze_module(self, module: ModuleInfo) -> List[Dict[str, Any]]:
        """Run analysis on a single parsed module."""
        prompt = self.prompt_template.format(
            module_summary=self.parser.get_summary(module),
            rtl_code=module.raw_code
        )

        raw_response = self.client.query(
            prompt=prompt,
            expect_json=True
        )

        return self._parse_response(raw_response)

    def analyze_file(self, filepath: str) -> Dict[str, Any]:
        """Parse file and run analysis on all modules in it."""
        modules = self.parser.parse_file(filepath)
        results = {}

        for module in modules:
            print(f"  Analyzing module: {module.name}")
            findings = self.analyze_module(module)
            results[module.name] = {
                "module": module.name,
                "file": filepath,
                "findings": findings,
                "agent": self.__class__.__name__
            }

        return results

    def _parse_response(self, raw: str) -> List[Dict[str, Any]]:
        """Parse JSON from LLM response with graceful fallback."""
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return [data]
        except json.JSONDecodeError:
            # Return error as structured finding
            return [{
                "issue_id": "PARSE-ERR",
                "category": "parse_error",
                "severity": "info",
                "description": "LLM returned non-parseable output",
                "raw_response": raw[:500]
            }]
        return []

    @abstractmethod
    def agent_name(self) -> str:
        pass
```

**Create `agents/bug_agent.py`:**
```python
from agents.base_agent import BaseRTLAgent

class BugAnalysisAgent(BaseRTLAgent):
    """Agent specialized in detecting RTL coding bugs."""

    def __init__(self, client):
        super().__init__(client, "bug_analysis.txt")

    def agent_name(self) -> str:
        return "Bug Analysis Agent"
```

**Create `agents/assertion_agent.py`:**
```python
from agents.base_agent import BaseRTLAgent

class AssertionGenerationAgent(BaseRTLAgent):
    """Agent specialized in generating SVA assertions."""

    def __init__(self, client):
        super().__init__(client, "assertion_gen.txt")

    def agent_name(self) -> str:
        return "Assertion Generation Agent"
```

**Create `agents/timing_agent.py`:**
```python
from agents.base_agent import BaseRTLAgent

class TimingReviewAgent(BaseRTLAgent):
    """Agent specialized in timing and pipeline analysis."""

    def __init__(self, client):
        super().__init__(client, "timing_review.txt")

    def agent_name(self) -> str:
        return "Timing Review Agent"
```

---

## Step 2.5 — Build the Report Generator

### What you're doing
Converting raw JSON findings from all agents into a readable Markdown report.

**Create `reports/report_generator.py`:**
```python
"""
report_generator.py — Converts agent findings to human-readable reports.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List


class ReportGenerator:
    SEVERITY_ICONS = {
        "critical": "🔴",
        "warning": "🟡",
        "info": "🔵"
    }

    def generate(
        self,
        all_results: Dict[str, Any],
        output_path: str = "reports/analysis_report.md"
    ) -> str:
        """Generate a Markdown report from all agent results."""
        
        report_lines = [
            "# RTL Analysis Report",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
            "## Executive Summary",
            ""
        ]

        # Count findings by severity
        all_findings = []
        for module_data in all_results.values():
            for agent_result in module_data.values():
                if isinstance(agent_result, dict) and "findings" in agent_result:
                    all_findings.extend(agent_result["findings"])

        critical = sum(1 for f in all_findings 
                      if f.get("severity") == "critical")
        warnings = sum(1 for f in all_findings 
                      if f.get("severity") == "warning")
        info = sum(1 for f in all_findings 
                  if f.get("severity") == "info")

        report_lines += [
            f"| Severity | Count |",
            f"|----------|-------|",
            f"| 🔴 Critical | {critical} |",
            f"| 🟡 Warning | {warnings} |",
            f"| 🔵 Info | {info} |",
            f"| **Total** | **{len(all_findings)}** |",
            "",
            "---",
            ""
        ]

        # Per-file detailed findings
        for filepath, modules in all_results.items():
            report_lines.append(f"## File: `{filepath}`")
            report_lines.append("")

            for module_name, agent_data in modules.items():
                if not isinstance(agent_data, dict):
                    continue

                agent = agent_data.get("agent", "Unknown Agent")
                findings = agent_data.get("findings", [])

                report_lines.append(f"### Module: `{module_name}` — {agent}")
                report_lines.append(f"*{len(findings)} finding(s)*")
                report_lines.append("")

                if not findings:
                    report_lines.append("✅ No issues found.")
                    report_lines.append("")
                    continue

                for finding in findings:
                    icon = self.SEVERITY_ICONS.get(
                        finding.get("severity", "info"), "⚪"
                    )
                    issue_id = finding.get(
                        "issue_id", 
                        finding.get("concern_id", 
                        finding.get("assertion_id", "N/A"))
                    )
                    report_lines += [
                        f"#### {icon} {issue_id}",
                        f"**Category:** {finding.get('category', finding.get('type', 'N/A'))}  ",
                        f"**Severity:** {finding.get('severity', 'N/A')}  ",
                        f"**Location:** {finding.get('location', finding.get('placement', 'N/A'))}",
                        "",
                        f"**Description:** {finding.get('description', 'N/A')}",
                        ""
                    ]

                    if finding.get("impact"):
                        report_lines.append(
                            f"**Impact:** {finding['impact']}"
                        )
                        report_lines.append("")

                    if finding.get("fix_code") or finding.get("code"):
                        code = finding.get("fix_code") or finding.get("code")
                        report_lines += [
                            "**Suggested Fix/Code:**",
                            "```systemverilog",
                            code,
                            "```",
                            ""
                        ]

                    if finding.get("recommendation"):
                        report_lines.append(
                            f"**Recommendation:** {finding['recommendation']}"
                        )
                        report_lines.append("")

                    report_lines.append("---")
                    report_lines.append("")

        report_content = "\n".join(report_lines)

        # Write to file
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report_content)

        print(f"✓ Report written to: {output_path}")
        return report_content


    def generate_json(
        self,
        all_results: Dict,
        output_path: str = "reports/analysis_results.json"
    ):
        """Also save raw JSON for downstream tooling."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, 'w') as f:
            json.dump(all_results, f, indent=2)
        print(f"✓ JSON results written to: {output_path}")
```

---

## Step 2.6 — Build the Main Orchestrator

### What you're doing
Creating the top-level script that takes a list of RTL files and runs all agents on them.

**Create `orchestrator.py`:**
```python
"""
orchestrator.py — Main analysis orchestrator.
Usage: python orchestrator.py --files rtl_samples/*.sv --agents bug timing assertion
"""
import argparse
import glob
import sys
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, TaskID

from utils.ollama_client import OllamaClient
from agents.bug_agent import BugAnalysisAgent
from agents.timing_agent import TimingReviewAgent
from agents.assertion_agent import AssertionGenerationAgent
from reports.report_generator import ReportGenerator

console = Console()

AVAILABLE_AGENTS = {
    "bug": BugAnalysisAgent,
    "timing": TimingReviewAgent,
    "assertion": AssertionGenerationAgent,
}


def run_analysis(
    rtl_files: list,
    agent_names: list,
    model: str = "deepseek-coder-v2:16b",
    output_dir: str = "reports"
):
    console.rule("[bold blue]RTL AI Analysis Agent")

    # Initialize Ollama client
    client = OllamaClient(model=model)
    if not client.is_available():
        console.print("[red]ERROR: Ollama is not running. Start with: ollama serve")
        sys.exit(1)

    console.print(f"[green]✓ Ollama connected | Model: {model}")
    console.print(f"[cyan]Files to analyze: {len(rtl_files)}")
    console.print(f"[cyan]Agents: {', '.join(agent_names)}\n")

    # Initialize agents
    agents = {
        name: AVAILABLE_AGENTS[name](client)
        for name in agent_names
        if name in AVAILABLE_AGENTS
    }

    all_results = {}

    with Progress() as progress:
        file_task = progress.add_task(
            "[cyan]Analyzing files...", total=len(rtl_files)
        )

        for filepath in rtl_files:
            console.print(f"\n[bold]Processing: {filepath}")
            file_results = {}

            agent_task = progress.add_task(
                f"  Running agents...", total=len(agents)
            )

            for agent_name, agent in agents.items():
                console.print(f"  → Running {agent.agent_name()}...")
                try:
                    result = agent.analyze_file(filepath)
                    for module_name, module_result in result.items():
                        if module_name not in file_results:
                            file_results[module_name] = {}
                        file_results[module_name][agent_name] = module_result
                except Exception as e:
                    console.print(f"  [red]Error in {agent_name}: {e}")
                    file_results[f"error_{agent_name}"] = {"error": str(e)}

                progress.advance(agent_task)

            all_results[filepath] = file_results
            progress.advance(file_task)

    # Generate reports
    console.rule("[bold green]Generating Reports")
    reporter = ReportGenerator()
    reporter.generate(all_results, f"{output_dir}/analysis_report.md")
    reporter.generate_json(all_results, f"{output_dir}/analysis_results.json")

    console.rule("[bold green]Analysis Complete")
    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="RTL AI Analysis Agent"
    )
    parser.add_argument(
        "--files", nargs="+", required=True,
        help="RTL files to analyze (supports glob: rtl/*.sv)"
    )
    parser.add_argument(
        "--agents", nargs="+",
        default=["bug", "timing", "assertion"],
        choices=list(AVAILABLE_AGENTS.keys()),
        help="Which agents to run"
    )
    parser.add_argument(
        "--model", default="deepseek-coder-v2:16b",
        help="Ollama model to use"
    )
    parser.add_argument(
        "--output", default="reports",
        help="Output directory for reports"
    )

    args = parser.parse_args()

    # Expand globs
    files = []
    for pattern in args.files:
        expanded = glob.glob(pattern)
        files.extend(expanded if expanded else [pattern])

    if not files:
        console.print("[red]No files found matching the patterns provided.")
        sys.exit(1)

    run_analysis(files, args.agents, args.model, args.output)


if __name__ == "__main__":
    main()
```

**Run it:**
```bash
# Run all three agents on the sample file
python orchestrator.py \
    --files rtl_samples/sample_counter.sv \
    --agents bug timing assertion \
    --model deepseek-coder-v2:16b \
    --output reports/

# View the report
cat reports/analysis_report.md
```

---

# PHASE 3 — Agent Specialization and Hardening
**Duration: 7–10 days**

---

## Step 3.1 — Add the Optimization Agent

### What you're doing
Adding a fourth agent focused on code quality, readability, and PPA optimization suggestions.

**Create `prompts/optimization.txt`:**
```
You are an expert RTL architect focused on PPA (Power, Performance, Area) optimization 
and coding best practices for ASIC/FPGA design.

Review the RTL code for:
1. Redundant logic (gates that can be simplified or eliminated)
2. Power optimization opportunities (clock gating, operand isolation)
3. Area reduction (shared resources, one-hot vs binary encoding)
4. Performance improvements (pipeline restructuring, critical path shortening)
5. Coding style: naming conventions, readability, maintainability
6. Use of generate blocks where parametrization is missing
7. Fan-out issues (signals driving too many loads)

MODULE CONTEXT:
{module_summary}

FULL CODE:
{rtl_code}

Respond with ONLY a JSON array:
[
  {{
    "opt_id": "OPT-001",
    "category": "power|area|performance|style|fanout|parametrization",
    "severity": "high_impact|medium_impact|low_impact",
    "description": "What can be improved",
    "location": "Where in the code",
    "current_code": "Current code snippet",
    "optimized_code": "Improved version",
    "estimated_benefit": "Estimated improvement (e.g., ~20% area reduction)"
  }}
]
```

**Create `agents/optimizer_agent.py`:**
```python
from agents.base_agent import BaseRTLAgent

class OptimizationAgent(BaseRTLAgent):
    """Agent for PPA optimization and code quality suggestions."""

    def __init__(self, client):
        super().__init__(client, "optimization.txt")

    def agent_name(self) -> str:
        return "Optimization Agent"
```

Then add `"optimization": OptimizationAgent` to `AVAILABLE_AGENTS` in `orchestrator.py`.

---

## Step 3.2 — Implement Output Validation

### What you're doing
Adding a validation layer that checks LLM outputs for correctness and filters hallucinations.

### Why
LLMs can confidently produce wrong answers. Especially for SVA assertions, generated code must be checked for basic syntactic validity.

**Create `utils/output_validator.py`:**
```python
"""
output_validator.py — Validates and filters LLM-generated RTL/SVA.
"""
import re
from typing import List, Dict, Any, Tuple


class RTLOutputValidator:
    """
    Validates LLM-generated findings and assertions.
    Filters out likely hallucinations and syntactically invalid code.
    """

    # SVA keywords that should appear in valid assertions
    SVA_KEYWORDS = [
        'assert', 'assume', 'cover', 'property',
        'posedge', 'negedge', '|->',  '|=>', '##'
    ]

    # Common hallucination patterns to filter
    HALLUCINATION_PATTERNS = [
        r'line\s+\d{3,}',      # Claims line numbers > 99 in a short file
        r'module\s+\w+\s+does not exist',  # Non-existent module references
    ]

    def validate_findings(
        self,
        findings: List[Dict[str, Any]],
        module_info
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Separate valid findings from suspected hallucinations.
        Returns: (valid_findings, suspect_findings)
        """
        valid = []
        suspect = []

        total_lines = module_info.line_count

        for finding in findings:
            issues = []

            # Check: Does it reference a valid port/signal name?
            description = finding.get("description", "").lower()
            location = str(finding.get("location", ""))

            # Check: Line number plausibility
            line_match = re.search(r'line\s*:?\s*(\d+)', location, re.I)
            if line_match:
                claimed_line = int(line_match.group(1))
                if claimed_line > total_lines:
                    issues.append(
                        f"Line {claimed_line} exceeds file length ({total_lines})"
                    )

            # Check: Fix code is not empty (for critical issues)
            if finding.get("severity") == "critical":
                if not finding.get("fix_code") and not finding.get("code"):
                    issues.append("Critical finding has no fix provided")

            # Check: SVA code has required keywords
            code = finding.get("code", "")
            if finding.get("type") in ["concurrent", "immediate"]:
                if not any(kw in code for kw in self.SVA_KEYWORDS):
                    issues.append("Generated SVA does not contain assertion keywords")

            if issues:
                finding["validation_warnings"] = issues
                suspect.append(finding)
            else:
                valid.append(finding)

        return valid, suspect

    def validate_sva_syntax(self, sva_code: str) -> bool:
        """Basic syntax check for generated SVA."""
        # Must have assertion keyword
        if not re.search(r'\b(assert|assume|cover)\b', sva_code):
            return False
        # Concurrent assertions must have property
        if '|->` in sva_code or '|=>' in sva_code:
            if 'property' not in sva_code and '@(' not in sva_code:
                return False
        return True
```

---

## Step 3.3 — Add Configuration Management

### What you're doing
Moving hardcoded values (model name, temperature, file paths) into a config file so the system is easy to tune.

**Create `config.py`:**
```python
"""
config.py — Central configuration for the RTL AI Agent.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    # Ollama settings
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    PRIMARY_MODEL: str = os.getenv("PRIMARY_MODEL", "deepseek-coder-v2:16b")
    FAST_MODEL: str = os.getenv("FAST_MODEL", "mistral:7b")
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.1"))
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4096"))
    TIMEOUT_SECONDS: int = int(os.getenv("TIMEOUT_SECONDS", "300"))

    # Analysis settings
    # How many lines of context to send per always block
    MAX_BLOCK_LINES: int = 100
    # Minimum confidence to include in report
    MIN_CONFIDENCE: str = "low"

    # Output settings
    REPORT_DIR: str = "reports"
    JSON_OUTPUT: bool = True
    MARKDOWN_OUTPUT: bool = True

    # Agent enable/disable
    RUN_BUG_AGENT: bool = True
    RUN_TIMING_AGENT: bool = True
    RUN_ASSERTION_AGENT: bool = True
    RUN_OPTIMIZER_AGENT: bool = False  # Disabled by default (slow)

config = Config()
```

**Create `.env`:**
```bash
OLLAMA_URL=http://localhost:11434
PRIMARY_MODEL=deepseek-coder-v2:16b
FAST_MODEL=mistral:7b
TEMPERATURE=0.1
MAX_TOKENS=4096
```

---

## Step 3.4 — Write Tests

### What you're doing
Creating automated tests to verify your agents detect the known bugs you planted in your sample file.

**Create `tests/test_bug_agent.py`:**
```python
"""
tests/test_bug_agent.py — Ground truth tests for Bug Analysis Agent.
Tests are designed around the known bugs in rtl_samples/sample_counter.sv.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from agents.bug_agent import BugAnalysisAgent
from utils.ollama_client import OllamaClient


# Mock response for unit testing (no LLM needed)
MOCK_BUG_RESPONSE = json.dumps([
    {
        "issue_id": "BUG-001",
        "category": "blocking_assign",
        "severity": "critical",
        "description": "Blocking assignment in always_ff block",
        "location": "line 22",
        "fix_code": "count <= 8'd0;"
    },
    {
        "issue_id": "BUG-002",
        "category": "latch",
        "severity": "critical",
        "description": "Missing else creates latch for next_overflow",
        "location": "always_comb block",
        "fix_code": "else next_overflow = 1'b0;"
    }
])


class TestBugAgent:
    """Unit tests for Bug Analysis Agent (mocked LLM)."""

    def test_detects_blocking_assignment(self):
        """Verifies agent reports blocking assignment in always_ff."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.query.return_value = MOCK_BUG_RESPONSE

        agent = BugAnalysisAgent(mock_client)
        modules = agent.parser.parse_file("rtl_samples/sample_counter.sv")
        findings = agent.analyze_module(modules[0])

        categories = [f.get("category") for f in findings]
        assert "blocking_assign" in categories, \
            "Agent must detect blocking assignments in always_ff"

    def test_detects_latch(self):
        """Verifies agent reports latch inference."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.query.return_value = MOCK_BUG_RESPONSE

        agent = BugAnalysisAgent(mock_client)
        modules = agent.parser.parse_file("rtl_samples/sample_counter.sv")
        findings = agent.analyze_module(modules[0])

        categories = [f.get("category") for f in findings]
        assert "latch" in categories, \
            "Agent must detect latch inference"

    def test_response_is_valid_json(self):
        """Verifies agent returns parseable findings list."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.query.return_value = MOCK_BUG_RESPONSE

        agent = BugAnalysisAgent(mock_client)
        modules = agent.parser.parse_file("rtl_samples/sample_counter.sv")
        findings = agent.analyze_module(modules[0])

        assert isinstance(findings, list)
        assert len(findings) > 0

    def test_critical_findings_have_fix(self):
        """Critical findings must include fix code."""
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.query.return_value = MOCK_BUG_RESPONSE

        agent = BugAnalysisAgent(mock_client)
        modules = agent.parser.parse_file("rtl_samples/sample_counter.sv")
        findings = agent.analyze_module(modules[0])

        critical = [f for f in findings if f.get("severity") == "critical"]
        for finding in critical:
            assert finding.get("fix_code"), \
                f"Critical finding {finding.get('issue_id')} must have fix_code"


# Integration test — requires Ollama running
@pytest.mark.integration
class TestBugAgentIntegration:
    def test_live_analysis(self):
        """Run against real LLM — requires ollama serve."""
        client = OllamaClient(model="deepseek-coder-v2:16b")
        if not client.is_available():
            pytest.skip("Ollama not running")

        agent = BugAnalysisAgent(client)
        result = agent.analyze_file("rtl_samples/sample_counter.sv")

        assert len(result) > 0
        for module_name, data in result.items():
            findings = data.get("findings", [])
            severities = [f.get("severity") for f in findings]
            # Should find at least one critical or warning issue
            assert any(s in ["critical", "warning"] for s in severities), \
                f"No significant issues found in {module_name}"
```

**Run tests:**
```bash
# Unit tests (no LLM needed)
pytest tests/ -v -k "not integration"

# Integration tests (requires Ollama)
pytest tests/ -v -m integration
```

---

# PHASE 4 — Integration and Delivery
**Duration: 3–5 days**

---

## Step 4.1 — Build a Simple CLI Interface

**Create `main.py`:**
```python
#!/usr/bin/env python3
"""
main.py — Entry point for RTL AI Analysis Agent.
"""
from orchestrator import main

if __name__ == "__main__":
    main()
```

```bash
# Make it executable
chmod +x main.py

# Example usage
python main.py --files rtl_samples/*.sv --agents bug assertion

# Analyze an entire directory
python main.py --files designs/**/*.sv --agents bug timing assertion optimization

# Use a faster model for quick review
python main.py --files design.sv --agents bug --model codellama:13b
```

---

## Step 4.2 — Document Known Limitations

Create `LIMITATIONS.md` alongside your code:

```markdown
# Known Limitations of Local LLM-Based RTL Analysis

## Accuracy Limitations
- **False Positives:** ~15–30% of findings may be incorrect on complex modules
- **Context Window:** Files > 2000 lines may be truncated — split into modules
- **Hallucinated Line Numbers:** LLM does not have true line-number awareness

## SVA Limitation
- Generated assertions are syntactically approximate — validate with a formal tool
- Concurrent properties may not account for multi-cycle timing

## Performance
- A 7B model: ~30 sec/file | 16B model: ~90 sec/file (GPU) / 5–15 min (CPU)
- Large codebases (>50 files) should use batch processing with queuing

## RTL Coverage Gaps
- No cross-file/hierarchy analysis (each file analyzed independently)
- No netlist-level reasoning (purely RTL behavioral)
- No timing information (cannot access STA results)
```

---

# Resources Reference

## SystemVerilog and RTL
| Resource | URL | Type |
|----------|-----|------|
| IEEE 1800-2017 (SV LRM) | ieee.org/standards | Official standard |
| ASIC World SV Tutorial | asic-world.com/systemverilog | Free web guide |
| ChipVerify SV Reference | chipverify.com/systemverilog | Free web guide |
| Sutherland SV for Design | sutherland-hdl.com | Book |
| Verification Academy | verificationacademy.com | Free courses |
| Yosys RTL Synthesizer | github.com/YosysHQ/yosys | Open source tool |
| Verilator Simulator | verilator.org | Open source linter |

## LLM / Agent Frameworks
| Resource | URL | Type |
|----------|-----|------|
| Ollama Documentation | ollama.com/docs | Official docs |
| LangChain Python | python.langchain.com | Framework docs |
| Prompt Engineering Guide | promptingguide.ai | Free guide |
| DeepSeek Coder on Ollama | ollama.com/library/deepseek-coder-v2 | Model page |
| PyVerilog | github.com/PyHDI/Pyverilog | Python library |
| ReAct Paper | arxiv.org/abs/2210.03629 | Research paper |

## Python Tools Used
| Package | Purpose | Install |
|---------|---------|---------|
| pyverilog | RTL parsing | `pip install pyverilog` |
| langchain | Agent framework | `pip install langchain-ollama` |
| rich | Terminal UI | `pip install rich` |
| requests | HTTP client | `pip install requests` |
| pytest | Testing | `pip install pytest` |
| python-dotenv | Config | `pip install python-dotenv` |

---

# Execution Checklist

Use this to track your progress:

```
PHASE 0 — FOUNDATIONS
[ ] Step 0.1 — Read SV fundamentals, memorize 5 anti-patterns
[ ] Step 0.2 — Read LangChain docs and prompt engineering guide
[ ] Step 0.3 — Run PyVerilog examples from GitHub

PHASE 1 — ENVIRONMENT
[ ] Step 1.1 — Python venv + all packages installed
[ ] Step 1.2 — Ollama installed, 2+ models pulled, ollama list works
[ ] Step 1.3 — sample_counter.sv with planted bugs created
[ ] Step 1.4 — Baseline prompt tests run, results documented
[ ] Step 1.5 — Model comparison completed, primary model chosen

PHASE 2 — AGENT DEVELOPMENT
[ ] Step 2.1 — sv_parser.py working on sample file
[ ] Step 2.2 — ollama_client.py tested, JSON extraction working
[ ] Step 2.3 — All prompt templates created (bug, timing, assertion)
[ ] Step 2.4 — base_agent.py + all 3 agent files created
[ ] Step 2.5 — report_generator.py outputs valid Markdown
[ ] Step 2.6 — orchestrator.py runs end-to-end on sample file

PHASE 3 — SPECIALIZATION
[ ] Step 3.1 — optimizer_agent.py added
[ ] Step 3.2 — output_validator.py filtering suspect findings
[ ] Step 3.3 — config.py + .env in use
[ ] Step 3.4 — All unit tests passing (no Ollama needed)

PHASE 4 — DELIVERY
[ ] Step 4.1 — CLI working (python main.py --files ... --agents ...)
[ ] Step 4.2 — LIMITATIONS.md written
[ ] Final integration test on 3+ different RTL files
[ ] Report output validated (Markdown renders correctly)
```

---

*Document version 1.0 — RTL AI Agent Steering Guide*