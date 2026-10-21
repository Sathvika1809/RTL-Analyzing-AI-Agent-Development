import os
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent

CUSTOM_PROMPT = """You are a senior RTL and SystemVerilog verification/design engineer.
Your task is to analyze the following SystemVerilog/Verilog module and address the user's specific request.

CRITICAL RULES:
1. IDENTIFY DECLARED IDENTIFIERS:
   Inspect the RTL module carefully. Any signals, ports, registers, parameters, or interfaces you reference in your explanation or code fixes MUST exist in the provided RTL.
2. DO NOT HALLUCINATE:
   Never invent signals, clocks, resets, parameters, or ports that are not present in the provided RTL.
3. CODE GENERATION:
   If you suggest code changes or rewrites, ensure the code is valid SystemVerilog, syntactically correct, and uses only declared identifiers.
   
RTL Code (File: {filename}):
```systemverilog
{code}
```

User's Request:
{query}

Provide a detailed, technical, and accurate response. If you suggest code changes or rewrites, ensure the code is valid SystemVerilog and syntactically correct. Respond in Markdown format.
"""

# Files at or below this size get the FULL module passed to the LLM with no
# chunking. Chunking exists to fit large files into context budget; on small
# files it only risks dropping context relevant to the user's query.
SMALL_FILE_CHAR_THRESHOLD = 6000


class CustomAgent(BaseAgent):
    """
    Specialized agent for answering custom user queries or instructions on RTL files.

    Unlike the other agents, this one already routes chunk selection using
    the user's actual query rather than a generic prompt template, which is
    the right approach for free-form questions. The only fix here is
    consistency with the rest of the pipeline: small files skip chunking
    entirely and get full-module context, since chunk-relevance scoring can
    still drop context the query implicitly depends on (e.g. a query about
    one signal's behavior may need to see an always block that doesn't
    score highly against the query's literal keywords).
    """

    def __init__(self, model: str = None):
        super().__init__(agent_name="custom_agent", model=model)

    def analyze(self, filepath: str, query: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Custom agent addressing query for: {path.name}")

        if len(code) <= SMALL_FILE_CHAR_THRESHOLD:
            code_ctx = code
        else:
            # Semantic chunking for fewer irrelevant tokens and fewer hallucinations.
            from src.core.semantic_chunker import (
                chunk_sv,
                select_relevant_chunks,
                chunks_to_prompt_text,
            )

            chunks = chunk_sv(code)
            # Route using the user's query (not the whole prompt) — this part
            # was already correct in the original implementation.
            selected = select_relevant_chunks(
                chunks,
                query=query,
                top_k=10,
                max_total_chars=14000,
            )
            code_ctx = chunks_to_prompt_text(selected) if selected else code

        prompt = CUSTOM_PROMPT.format(
            filename=path.name,
            code=code_ctx,
            query=query,
        )

        # We request markdown instead of JSON
        result = self.call_ollama(prompt, json_mode=False, max_tokens=2500)
        if not result["success"]:
            return {"success": False, "error": result["error"]}

        self.log_run(path.name, {
            "query": query[:100],
            "response_length": len(result["response"]),
        })

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "response": result["response"],
            "elapsed_s": result["elapsed"],
        }