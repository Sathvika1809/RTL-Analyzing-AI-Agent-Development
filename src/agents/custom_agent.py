import os
from datetime import datetime
from pathlib import Path
from src.core.base_agent import BaseAgent

CUSTOM_PROMPT = """You are a senior RTL and SystemVerilog verification/design engineer.
Your task is to analyze the following SystemVerilog/Verilog module and address the user's specific request.

RTL Code (File: {filename}):
```systemverilog
{code}
```

User's Request:
{query}

Provide a detailed, technical, and accurate response. If you suggest code changes or rewrites, ensure the code is valid SystemVerilog and syntactically correct. Respond in Markdown format.
"""

class CustomAgent(BaseAgent):
    """
    Specialized agent for answering custom user queries or instructions on RTL files.
    """
    def __init__(self, model: str = None):
        super().__init__(agent_name="custom_agent", model=model)

    def analyze(self, filepath: str, query: str) -> dict:
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {filepath}"}

        code = path.read_text(encoding="utf-8", errors="replace")
        print(f"  Custom agent addressing query for: {path.name}")

        # Semantic chunking for fewer irrelevant tokens and fewer hallucinations.
        from src.core.semantic_chunker import (
            chunk_sv,
            select_relevant_chunks,
            chunks_to_prompt_text,
        )

        chunks = chunk_sv(code)
        # For custom prompts, route using the user's query (not the whole prompt).
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
            query=query
        )


        # We request markdown instead of JSON
        result = self.call_ollama(prompt, json_mode=False, max_tokens=2500)
        if not result["success"]:
            return {"success": False, "error": result["error"]}

        # Log run
        self.log_run(path.name, {
            "query": query[:100],
            "response_length": len(result["response"])
        })

        return {
            "success": True,
            "filename": path.name,
            "filepath": str(path),
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
            "response": result["response"],
            "elapsed_s": result["elapsed"]
        }
