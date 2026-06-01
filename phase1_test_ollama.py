#!/usr/bin/env python3
"""
phase1_test_ollama.py
=====================
Phase 1: Environment Setup and Baseline Evaluation

PURPOSE:
    This script is your very first test. It checks:
      1. Is Ollama installed and running?
      2. Which models do you have available?
      3. Can the model actually understand and analyze RTL code?

HOW TO RUN:
    python3 phase1_test_ollama.py

BEFORE RUNNING:
    1. Install Ollama from https://ollama.com
    2. Start Ollama:        ollama serve
    3. Pull a model:        ollama pull codellama
       (or)                 ollama pull mistral
       (or)                 ollama pull llama3

WHAT THIS SCRIPT DOES:
    - Connects to Ollama at http://localhost:11434
    - Lists all models you have downloaded
    - Sends a tiny RTL snippet as a test
    - Prints the model's response so you can judge quality
"""

import requests      # For making HTTP calls to Ollama's REST API
import json          # For reading/writing JSON data
import sys           # For exiting if something goes wrong
import time          # For measuring how long the model takes to respond

# ─────────────────────────────────────────────
# CONFIGURATION
# Change OLLAMA_URL if you run Ollama on a different port
# Change MODEL_NAME to whichever model you have pulled
# ─────────────────────────────────────────────
OLLAMA_URL  = "http://localhost:11434"   # Default Ollama address
MODEL_NAME  = "codellama"               # Change to: mistral, llama3, deepseek-coder, etc.


# ─────────────────────────────────────────────
# STEP 1: CHECK IF OLLAMA IS RUNNING
# ─────────────────────────────────────────────
def check_ollama_running():
    """
    Sends a GET request to Ollama's root endpoint.
    If Ollama is running, it responds with "Ollama is running".
    If not, we get a ConnectionRefusedError.
    """
    print("=" * 60)
    print("STEP 1: Checking if Ollama is running...")
    print("=" * 60)

    try:
        response = requests.get(f"{OLLAMA_URL}/", timeout=5)
        # If we get here, Ollama responded
        print(f"✅ Ollama is running at {OLLAMA_URL}")
        print(f"   Response: {response.text.strip()}")
        return True

    except requests.exceptions.ConnectionError:
        # This means Ollama is NOT running
        print(f"❌ Cannot connect to Ollama at {OLLAMA_URL}")
        print()
        print("  TO FIX THIS:")
        print("  1. Make sure Ollama is installed: https://ollama.com")
        print("  2. Open a terminal and run:  ollama serve")
        print("  3. Then run this script again")
        return False

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


# ─────────────────────────────────────────────
# STEP 2: LIST AVAILABLE MODELS
# ─────────────────────────────────────────────
def list_available_models():
    """
    Calls /api/tags which returns all locally downloaded models.
    This tells you which model names you can use in MODEL_NAME above.
    """
    print()
    print("=" * 60)
    print("STEP 2: Listing available models on your machine...")
    print("=" * 60)

    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        data = response.json()

        models = data.get("models", [])

        if not models:
            # No models downloaded yet
            print("⚠️  No models found! You need to pull one first.")
            print()
            print("  Run one of these commands in your terminal:")
            print("  → ollama pull codellama        (best for code)")
            print("  → ollama pull mistral          (general purpose)")
            print("  → ollama pull deepseek-coder   (great for code)")
            print("  → ollama pull llama3           (latest Meta model)")
            return []

        print(f"✅ Found {len(models)} model(s):\n")
        for model in models:
            name    = model.get("name", "unknown")
            size_gb = model.get("size", 0) / 1e9   # Convert bytes → GB
            print(f"   • {name}  ({size_gb:.1f} GB)")

        return [m["name"] for m in models]

    except Exception as e:
        print(f"❌ Error listing models: {e}")
        return []


# ─────────────────────────────────────────────
# STEP 3: SEND A TEST RTL PROMPT TO THE MODEL
# ─────────────────────────────────────────────
def test_rtl_analysis(model_name: str):
    """
    Sends a simple SystemVerilog snippet to the model with a focused question.
    We use /api/generate which is Ollama's main text generation endpoint.

    The payload has:
        model  → which model to use
        prompt → the text we send (our question + code)
        stream → False means wait for the full answer (not word-by-word)
    """
    print()
    print("=" * 60)
    print(f"STEP 3: Testing RTL analysis with model: {model_name}")
    print("=" * 60)

    # A minimal RTL snippet with a deliberate bug (missing else on overflow)
    test_rtl_code = """
module simple_counter (
    input  logic clk,
    input  logic rst_n,
    input  logic en,
    output logic [3:0] count,
    output logic overflow
);
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            count <= 4'b0;
            // overflow is NOT reset here
        end else if (en) begin
            count <= count + 1;
        end

        if (count == 4'hF)
            overflow <= 1'b1;
        // No else: overflow never clears = LATCH RISK
    end
endmodule
"""

    # Our prompt: we tell the model exactly what to look for
    prompt = f"""You are an expert RTL (Register Transfer Level) hardware design reviewer.

Analyze the following SystemVerilog code and identify:
1. Any bugs or functional errors
2. Latch inference risks (signals assigned without a complete if-else)
3. Signals not reset properly
4. Any missing else branches that could cause simulation/synthesis mismatches

Here is the code:
{test_rtl_code}

Provide a clear, structured analysis."""

    # Build the JSON body for the POST request
    payload = {
        "model":  model_name,
        "prompt": prompt,
        "stream": False          # False = wait for complete response
    }

    print(f"Sending test RTL code to {model_name}...")
    print("(This may take 10-60 seconds depending on your machine)\n")

    start_time = time.time()

    try:
        # POST to /api/generate
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=120    # Wait up to 2 minutes for the model to respond
        )

        elapsed = time.time() - start_time

        if response.status_code != 200:
            print(f"❌ Model returned error status: {response.status_code}")
            print(response.text)
            return None

        result = response.json()
        answer = result.get("response", "").strip()

        print(f"✅ Model responded in {elapsed:.1f} seconds\n")
        print("-" * 60)
        print("MODEL RESPONSE:")
        print("-" * 60)
        print(answer)
        print("-" * 60)

        # Also show some performance stats from the response
        tokens_per_sec = result.get("eval_count", 0) / max(result.get("eval_duration", 1), 1) * 1e9
        print(f"\n📊 Stats: ~{tokens_per_sec:.1f} tokens/sec | "
              f"Total tokens: {result.get('eval_count', '?')}")

        return answer

    except requests.exceptions.Timeout:
        print("❌ Request timed out. The model is taking too long.")
        print("   Try a smaller model like 'mistral' or 'phi3'")
        return None

    except Exception as e:
        print(f"❌ Error calling model: {e}")
        return None


# ─────────────────────────────────────────────
# STEP 4: SAVE BASELINE RESULT
# ─────────────────────────────────────────────
def save_baseline_result(model_name: str, response_text: str):
    """
    Saves the test response to a JSON file so you can compare
    results between different models later.
    """
    import os
    from datetime import datetime

    os.makedirs("reports", exist_ok=True)

    result = {
        "timestamp":  datetime.now().isoformat(),
        "model":      model_name,
        "test":       "baseline_counter_analysis",
        "response":   response_text
    }

    filename = f"reports/baseline_{model_name.replace(':', '_').replace('/', '_')}.json"

    with open(filename, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n💾 Baseline result saved to: {filename}")


# ─────────────────────────────────────────────
# MAIN: RUN ALL STEPS IN ORDER
# ─────────────────────────────────────────────
if __name__ == "__main__":

    # Step 1: Is Ollama even running?
    if not check_ollama_running():
        print("\n⛔ Cannot proceed. Start Ollama first (run: ollama serve)")
        sys.exit(1)

    # Step 2: What models are available?
    available_models = list_available_models()

    # Decide which model to test
    if MODEL_NAME in available_models:
        model_to_test = MODEL_NAME
    elif available_models:
        model_to_test = available_models[0]
        print(f"\n⚠️  Model '{MODEL_NAME}' not found. Using '{model_to_test}' instead.")
        print(f"   To use a specific model, edit MODEL_NAME at the top of this file.")
    else:
        print("\n⛔ No models available. Run: ollama pull codellama")
        sys.exit(1)

    # Step 3: Test RTL analysis
    response = test_rtl_analysis(model_to_test)

    # Step 4: Save the result
    if response:
        save_baseline_result(model_to_test, response)
        print("\n✅ Phase 1 complete! Your environment is working.")
        print("   Next step: Run phase2_agent.py")
    else:
        print("\n⚠️  Model responded but with issues. Try a different model.")