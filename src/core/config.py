import os
import json

# Get the project root directory path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "settings.json")

def load_config() -> dict:
    """Loads settings from config/settings.json, falling back to defaults if not found."""
    defaults = {
        "ollama_url": "http://localhost:11434",
        "default_model": "qwen2.5:3b",
        "timeout": 250,
        "temperature": 0.1
    }
    
    if not os.path.exists(CONFIG_PATH):
        return defaults
        
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
            # Merge defaults for any missing keys
            for key, val in defaults.items():
                if key not in config:
                    config[key] = val
            return config
    except Exception as e:
        print(f"Warning: Failed to load config from {CONFIG_PATH}: {e}. Using defaults.")
        return defaults

# Global config instances
SETTINGS = load_config()
OLLAMA_URL = SETTINGS["ollama_url"]
DEFAULT_MODEL = SETTINGS["default_model"]
TIMEOUT = SETTINGS["timeout"]
TEMPERATURE = SETTINGS["temperature"]
