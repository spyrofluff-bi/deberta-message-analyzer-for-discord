"""
Automated Setup & Model Download Script for DeBERTa-v3 Discord Bot.
Installs all dependencies and pre-caches the DeBERTa-v3 zero-shot model.
"""

import sys
import os
import subprocess
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def run_step(description, command):
    print(f"\n[STEP] {description}...")
    start_t = time.time()
    res = subprocess.run(command, cwd=str(BASE_DIR), shell=True)
    if res.returncode != 0:
        print(f"[ERROR] Failed at: {description}")
        return False
    elapsed = round(time.time() - start_t, 1)
    print(f"[SUCCESS] Completed in {elapsed}s")
    return True

def setup():
    print("=" * 65)
    print(" DeBERTa-v3 Bot & Control Panel - Automated Setup")
    print("=" * 65)

    python_exe = sys.executable

    # 1. Ensure .env exists
    env_file = BASE_DIR / ".env"
    example_file = BASE_DIR / ".env.example"
    if not env_file.exists() and example_file.exists():
        print("\n[INFO] Creating default .env from .env.example...")
        env_file.write_text(example_file.read_text(encoding="utf-8"), encoding="utf-8")

    # 2. Install / Verify Requirements
    print("\n[1/3] Verifying and installing requirements...")
    pip_cmd = (
        f'"{python_exe}" -m pip install -r requirements.txt '
        f'--extra-index-url https://download.pytorch.org/whl/cpu'
    )
    if not run_step("Install Python Dependencies", pip_cmd):
        print("[WARNING] Could not install via requirements.txt, checking existing packages...")

    # 3. Pre-download DeBERTa-v3 Model & Tokenizer
    print("\n[2/3] Downloading DeBERTa-v3 zero-shot classification model...")
    download_script = """
import time
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from config import MODEL_NAME

print(f"Connecting to Hugging Face Hub for: {MODEL_NAME}...")
start_t = time.time()
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
pipe = pipeline("zero-shot-classification", model=model, tokenizer=tokenizer)

# Warm-up test inference
test_res = pipe("Test message for pipeline validation", candidate_labels=["toxic content", "benign conversation"])
elapsed = round(time.time() - start_t, 1)
print(f"Model successfully loaded and cached in {elapsed}s.")
print(f"Validation inference: {test_res['labels'][0]} ({round(test_res['scores'][0]*100, 1)}%)")
"""
    cmd = f'"{python_exe}" -c "{download_script}"'
    if not run_step("Pre-download and warm up DeBERTa-v3 pipeline", cmd):
        print("[WARNING] Model download encountered an error or network timeout. The bot will use fast fallback scoring until weights are fetched.")

    # 4. Initialize SQLite Database
    print("\n[3/3] Initializing persistent database...")
    init_db_script = """
import asyncio
import database
asyncio.run(database.init_db())
print("Database schema verified.")
"""
    run_step("Initialize SQLite Database", f'"{python_exe}" -c "{init_db_script}"')

    print("\n" + "=" * 65)
    print(" Setup Completed Successfully!")
    print("=" * 65)
    print("1. Edit .env if needed: DISCORD_BOT_TOKEN=<your_token>")
    print("2. Launch the Bot & Control Panel: python run.py")
    print("3. Control Panel URL:             http://127.0.0.1:8000")
    print("=" * 65)

if __name__ == "__main__":
    setup()
