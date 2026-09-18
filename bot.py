"""
Unified Discord Bot and Web Dashboard Runner.
Initializes discord.py client, synchronizes slash commands, hooks incoming messages into the
temporary in-memory evaluation buffer, and runs the FastAPI dashboard concurrently.
"""

import sys
import logging
import asyncio
import discord
from discord.ext import commands
import uvicorn

import database
from config import DISCORD_BOT_TOKEN, WEB_HOST, WEB_PORT, MODEL_NAME
from analyzer import DebertaAnalyzer
from message_buffer import InMemoryMessageQueue
from server import app

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("bot.main")

# Configure Discord Intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class DebertaBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        self.analyzer = DebertaAnalyzer.get_instance()
        self.queue = InMemoryMessageQueue.get_instance(self)

    async def setup_hook(self):
        # 1. Initialize SQLite Database
        await database.init_db()

        # 2. Load Setup & Diagnostics Cog
        await self.load_extension("cogs.setup_commands")
        logger.info("Loaded extension: cogs.setup_commands")

        # 3. Synchronize application slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synchronized {len(synced)} application slash commands globally.")
        except Exception as e:
            logger.error(f"Failed to synchronize slash commands: {e}")

        # 4. Start in-memory queue evaluation worker
        self.queue.start_worker()

        # 5. Initialize DeBERTa-v3 analyzer in background
        asyncio.create_task(self.analyzer.initialize())

    async def on_ready(self):
        logger.info("=" * 60)
        logger.info(f"🤖 Bot is ONLINE as {self.user} (ID: {self.user.id})")
        logger.info(f"🌐 Web Dashboard is live at: http://{WEB_HOST}:{WEB_PORT}")
        logger.info(f"🧠 DeBERTa-v3 Model Target: {MODEL_NAME}")
        logger.info(f"🛡️ Connected to {len(self.guilds)} Discord server(s)")
        logger.info("=" * 60)

        # Set presence activity
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="messages for evil content (DeBERTa-v3)"
        )
        await self.change_presence(activity=activity)

    async def on_message(self, message: discord.Message):
        # Ignore bots and webhook messages
        if message.author.bot:
            return

        # Store temporarily in memory and queue for DeBERTa-v3 evaluation
        await self.queue.enqueue(message)

        # Allow standard prefix commands if any
        await self.process_commands(message)

    async def close(self):
        await self.queue.stop_worker()
        await super().close()

bot = DebertaBot()

async def run_web_server():
    """Runs the FastAPI Web Dashboard using Uvicorn."""
    config = uvicorn.Config(
        app=app,
        host=WEB_HOST,
        port=WEB_PORT,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)
    logger.info(f"Starting FastAPI Web Dashboard on http://{WEB_HOST}:{WEB_PORT}")
    await server.serve()

async def main():
    # If bot token is not yet provided, we can still start the web dashboard and model engine!
    tasks = [asyncio.create_task(run_web_server())]

    if DISCORD_BOT_TOKEN and DISCORD_BOT_TOKEN != "your_discord_bot_token_here":
        tasks.append(asyncio.create_task(bot.start(DISCORD_BOT_TOKEN)))
    else:
        logger.warning("=" * 60)
        logger.warning("⚠️  DISCORD_BOT_TOKEN is not configured in .env!")
        logger.warning(f"⚠️  FastAPI Web Dashboard is running at http://{WEB_HOST}:{WEB_PORT}")
        logger.warning("⚠️  You can test the DeBERTa-v3 model playground and settings immediately.")
        logger.warning("⚠️  Add your token to .env to connect the live Discord bot.")
        logger.warning("=" * 60)

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("DeBERTa-v3 bot shutting down.")
