"""
Baseline test: Send raw RTL to LLM and measure output quality.
Run this BEFORE building any agent infrastructure.
"""
import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "deepseek-coder-v2:7b"

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