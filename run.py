"""
Main launcher script for DeBERTa-v3 Discord Message Analysis Bot & Web Dashboard.
"""

import os
import sys
from pathlib import Path

def setup_environment():
    base_dir = Path(__file__).resolve().parent
    env_file = base_dir / ".env"
    example_file = base_dir / ".env.example"

    if not env_file.exists() and example_file.exists():
        print("[Setup] Creating default .env file from .env.example...")
        env_file.write_text(example_file.read_text(encoding="utf-8"), encoding="utf-8")

    print("=" * 70)
    print("🚀 DeBERTa-v3 Discord Bot & Web Dashboard Launcher")
    print("=" * 70)
    print("1. Web Dashboard:  http://127.0.0.1:8000")
    print("2. Discord Setup:   Edit .env to add your DISCORD_BOT_TOKEN")
    print("3. Slash Commands:  /setup, /config, /set_log_channel, /set_threshold, /analyze")
    print("=" * 70)

if __name__ == "__main__":
    setup_environment()
    # Import and run bot main loop
    import asyncio
    from bot import main
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user. Goodbye!")
