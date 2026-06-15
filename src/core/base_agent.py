import os
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from src.core.config import OLLAMA_URL, DEFAULT_MODEL, TIMEOUT, TEMPERATURE

class BaseAgent:
    """
    Base Agent for interacting with Ollama.
    Handles Ollama POST requests, structured JSON modes, and logging.
    """
    def __init__(self, agent_name: str, model: str = None):
        self.agent_name = agent_name
        self.model = model if model else DEFAULT_MODEL
        
        # Resolve project root for logging
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.logs_dir = os.path.join(self.project_root, "logs")
        os.makedirs(self.logs_dir, exist_ok=True)

    def call_ollama(self, prompt: str, json_mode: bool = True, max_tokens: int = 1500) -> dict:
        """
        Sends the prompt to Ollama.
        If json_mode is True, Ollama is instructed to return a valid JSON object.
        Returns a dict indicating success status, LLM response, and elapsed time.
        """
        start_time = time.time()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": TEMPERATURE,
                "num_predict": max_tokens
            }
        }
        
        if json_mode:
            payload["format"] = "json"

        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json=payload,
                timeout=TIMEOUT
            )
            elapsed = time.time() - start_time
            
            if resp.status_code != 200:
                return {
                    "success": False,
                    "error": f"HTTP Error {resp.status_code}: {resp.text}",
                    "elapsed": round(elapsed, 1)
                }
            
            response_json = resp.json()
            response_text = response_json.get("response", "")
            
            return {
                "success": True,
                "response": response_text,
                "elapsed": round(elapsed, 1)
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                "success": False,
                "error": str(e),
                "elapsed": round(elapsed, 1)
            }

    def parse_json_response(self, raw_response: str) -> dict:
        """Helper to parse JSON string responses safely."""
        cleaned = raw_response.strip()
        try:
            return json.loads(cleaned)
        except Exception:
            # Try to extract content inside ```json ... ```
            if "```json" in cleaned:
                try:
                    block = cleaned.split("```json", 1)[1].split("```", 1)[0]
                    return json.loads(block.strip())
                except Exception:
                    pass
            # Try to extract content inside ``` ... ```
            if "```" in cleaned:
                try:
                    block = cleaned.split("```", 1)[1].split("```", 1)[0]
                    return json.loads(block.strip())
                except Exception:
                    pass
            
            # Find the first '{' and last '}'
            first_brace = cleaned.find('{')
            last_brace = cleaned.rfind('}')
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                try:
                    block = cleaned[first_brace:last_brace+1]
                    return json.loads(block.strip())
                except Exception as inner_e:
                    print(f"Error parsing extracted JSON block: {inner_e}")
            
            print(f"Error: Failed to parse LLM response as JSON. Content: {raw_response}")
            return {}

    def log_run(self, filename: str, log_data: dict):
        """Centralized logging in JSONL format for tracking agent runs."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.agent_name,
            "model": self.model,
            "filename": filename
        }
        log_entry.update(log_data)
        
        log_path = os.path.join(self.logs_dir, f"{self.agent_name}_log.jsonl")
        try:
            with open(log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            print(f"Error writing agent log: {e}")
