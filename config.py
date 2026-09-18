"""
Configuration settings for DeBERTa-v3 Discord Bot and Web Dashboard.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Discord Bot Settings
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

# DeBERTa-v3 Model Settings
# MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli provides state-of-the-art zero-shot NLI
# MoritzLaurer/DeBERTa-v3-xsmall-mnli-fever-anli is an ultra-fast, lightweight alternative
MODEL_NAME = os.getenv("MODEL_NAME", "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli")
MODEL_FALLBACK_XSMALL = "MoritzLaurer/DeBERTa-v3-xsmall-mnli-fever-anli"

# Evaluation Thresholds & Category Labels
DEFAULT_THRESHOLD = float(os.getenv("DEFAULT_THRESHOLD", "0.70"))  # 70% certainty
DEFAULT_LABELS = [
    "evil, malicious, or toxic content",
    "safe and benign casual conversation"
]
PRIMARY_EVIL_LABEL = "evil, malicious, or toxic content"

# Buffer & Moderation Defaults
BUFFER_MAX_SIZE = int(os.getenv("BUFFER_MAX_SIZE", "2000"))
EVALUATION_BATCH_SIZE = int(os.getenv("EVALUATION_BATCH_SIZE", "8"))
DEFAULT_ACTION = os.getenv("DEFAULT_ACTION", "log_only")  # log_only, delete_and_log, warn_and_log

# Database Path
DB_PATH = str(BASE_DIR / "data.sqlite3")

# Web Dashboard Settings
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))
DASHBOARD_SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "deberta-secret-key-change-me")
