import os
import json
import time
import requests
from datetime import datetime
from src.core.config import OLLAMA_URL, DEFAULT_MODEL, TIMEOUT, TEMPERATURE, NUM_CTX


class BaseAgent:
    """
    Base agent for Ollama calls, JSON parsing and JSONL logging.

    Changes vs the original:
      * num_ctx is now sent on every request (the original relied on Ollama's
        small default, so long prompts were silently truncated).
      * `schema` lets the caller pass a JSON schema as Ollama's `format`
        (structured outputs). The model is then forced into the exact shape,
        instead of being asked politely via prose. Falls back to plain
        `format: json` if the server rejects the schema.
      * The result reports prompt_tokens / prompt_truncated / output_truncated
        so a silent context overflow is visible instead of looking like
        "the model found nothing".
    """

    def __init__(self, agent_name: str, model: str = None):
        self.agent_name = agent_name
        self.model = model if model else DEFAULT_MODEL
        self.project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.logs_dir = os.path.join(self.project_root, "logs")
        os.makedirs(self.logs_dir, exist_ok=True)

    # ------------------------------------------------------------------ errors
    def _ollama_error(self, message: str) -> str:
        return (
            f"{message}\n"
            f"Ollama URL: {OLLAMA_URL}\n"
            f"Model: {self.model}\n"
            "Checks: `ollama serve` is running, the model is pulled "
            f"(`ollama pull {self.model}`), and config/settings.json `timeout` is large enough."
        )

    @staticmethod
    def _fail(message: str, error_type: str, start: float) -> dict:
        return {
            "success": False,
            "error": message,
            "error_type": error_type,
            "elapsed": round(time.time() - start, 1),
        }

    # ------------------------------------------------------------------ calls
    def _post(self, payload: dict):
        return requests.post(
            f"{OLLAMA_URL}/api/generate", json=payload, timeout=(10, TIMEOUT)
        )

    def call_ollama(
        self,
        prompt: str,
        json_mode: bool = True,
        max_tokens: int = 1500,
        schema: dict = None,
    ) -> dict:
        start = time.time()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": TEMPERATURE,
                "num_predict": max_tokens,
                "num_ctx": NUM_CTX,
            },
        }
        if schema:
            payload["format"] = schema
        elif json_mode:
            payload["format"] = "json"

        try:
            resp = self._post(payload)
            if resp.status_code == 400 and schema:
                # Older Ollama builds do not accept a schema; degrade to plain JSON mode.
                payload["format"] = "json"
                resp = self._post(payload)

            if resp.status_code != 200:
                return self._fail(
                    self._ollama_error(f"Ollama returned HTTP {resp.status_code}: {resp.text[:500]}"),
                    "ollama_http_error", start,
                )
            try:
                body = resp.json()
            except ValueError as e:
                return self._fail(
                    f"Ollama returned a non-JSON HTTP response: {e}. Preview: {resp.text[:500]}",
                    "ollama_invalid_http_json", start,
                )

            prompt_tokens = body.get("prompt_eval_count")
            prompt_truncated = bool(prompt_tokens and prompt_tokens >= int(NUM_CTX * 0.98))
            if prompt_truncated:
                print(
                    f"  WARNING [{self.agent_name}]: prompt used {prompt_tokens} tokens, "
                    f"which hits num_ctx={NUM_CTX}. The input was probably truncated. "
                    "Raise num_ctx in config/settings.json or shorten the input."
                )
            return {
                "success": True,
                "response": body.get("response", ""),
                "elapsed": round(time.time() - start, 1),
                "prompt_tokens": prompt_tokens,
                "prompt_truncated": prompt_truncated,
                "output_truncated": body.get("done_reason") == "length",
            }

        except requests.exceptions.ReadTimeout:
            return self._fail(self._ollama_error(f"Ollama read timed out after {TIMEOUT}s."),
                              "ollama_read_timeout", start)
        except requests.exceptions.ConnectTimeout:
            return self._fail(self._ollama_error("Timed out connecting to Ollama."),
                              "ollama_connect_timeout", start)
        except requests.exceptions.ConnectionError as e:
            return self._fail(self._ollama_error(f"Could not connect to Ollama: {e}"),
                              "ollama_connection_error", start)
        except requests.exceptions.RequestException as e:
            return self._fail(self._ollama_error(f"Ollama request failed: {e}"),
                              "ollama_request_error", start)
        except Exception as e:  # noqa: BLE001
            return self._fail(f"Unexpected error calling Ollama: {e}", "unexpected_ollama_error", start)

    # ------------------------------------------------------------------ parsing
    def parse_json_response(self, raw_response: str):
        cleaned = (raw_response or "").strip()
        try:
            return json.loads(cleaned)
        except Exception:
            pass
        for fence in ("```json", "```"):
            if fence in cleaned:
                try:
                    block = cleaned.split(fence, 1)[1].split("```", 1)[0]
                    return json.loads(block.strip())
                except Exception:
                    pass
        first, last = cleaned.find("{"), cleaned.rfind("}")
        if first != -1 and last > first:
            try:
                return json.loads(cleaned[first:last + 1])
            except Exception:
                pass
        msg = f"Failed to parse model output as JSON. Preview: {cleaned[:500]}"
        print(f"Error: {msg}")
        return {"__parse_error__": msg, "raw_response": raw_response}

    def json_parse_error(self, parsed) -> str:
        if isinstance(parsed, dict):
            return parsed.get("__parse_error__", "")
        return ""

    def llm_json(self, prompt: str, schema: dict, max_tokens: int = 1200):
        """Call + parse in one step. Returns (parsed, error, call_result)."""
        result = self.call_ollama(prompt, json_mode=True, max_tokens=max_tokens, schema=schema)
        if not result["success"]:
            return None, result["error"], result
        parsed = self.parse_json_response(result["response"])
        err = self.json_parse_error(parsed)
        if err:
            return None, err, result
        return parsed, None, result

    # ------------------------------------------------------------------ logging
    def log_run(self, filename: str, log_data: dict):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.agent_name,
            "model": self.model,
            "filename": filename,
        }
        entry.update(log_data)
        path = os.path.join(self.logs_dir, f"{self.agent_name}_log.jsonl")
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception as e:  # noqa: BLE001
            print(f"Error writing agent log: {e}")