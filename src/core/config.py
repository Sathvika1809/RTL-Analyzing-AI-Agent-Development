import os
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "settings.json")

DEFAULTS = {
    "ollama_url": "http://localhost:11434",
    "default_model": "qwen2.5-coder:7b",
    "timeout": 800,
    "temperature": 0.1,
    # Ollama's own default context is small (2048-4096 depending on version).
    # Without setting this, long prompts are silently truncated.
    "num_ctx": 8192,
}


def load_config() -> dict:
    """Loads config/settings.json, filling any missing key from DEFAULTS."""
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
        for key, val in DEFAULTS.items():
            config.setdefault(key, val)
        return config
    except Exception as e:
        print(f"Warning: failed to load {CONFIG_PATH}: {e}. Using defaults.")
        return dict(DEFAULTS)


SETTINGS = load_config()
OLLAMA_URL = SETTINGS["ollama_url"]
DEFAULT_MODEL = SETTINGS["default_model"]
TIMEOUT = SETTINGS["timeout"]
TEMPERATURE = SETTINGS["temperature"]
NUM_CTX = SETTINGS["num_ctx"]