"""
In-Memory Message Buffer and Evaluation Worker.
Stores incoming Discord messages temporarily in memory until they are evaluated
by DeBERTa-v3 on a probability scale. If certainty exceeds the configured threshold
(e.g., > 70% certainty of being evil), the bot logs them to the designated channel.
"""

import time
import asyncio
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Callable, List
import discord

from analyzer import DebertaAnalyzer
import database

logger = logging.getLogger("bot.buffer")

@dataclass
class BufferedMessage:
    message_id: int
    guild_id: int
    guild_name: str
    channel_id: int
    channel_name: str
    author_id: int
    author_name: str
    author_avatar: str
    content: str
    jump_url: str
    created_at: float

class InMemoryMessageQueue:
    _instance: Optional["InMemoryMessageQueue"] = None

    def __init__(self, bot_client: Optional[discord.Client] = None):
        self.bot = bot_client
        self._queue: asyncio.Queue[BufferedMessage] = asyncio.Queue()
        self._active_buffer: Dict[int, BufferedMessage] = {}
        self.ws_broadcast_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self._is_running = False
        self._worker_task: Optional[asyncio.Task] = None

        # Live Queue & Buffer Metrics
        self.total_received = 0
        self.total_processed = 0
        self.total_flagged_evil = 0
        self.last_processed_time = time.time()

    @classmethod
    def get_instance(cls, bot_client: Optional[discord.Client] = None) -> "InMemoryMessageQueue":
        if cls._instance is None:
            cls._instance = InMemoryMessageQueue(bot_client)
        elif bot_client is not None:
            cls._instance.bot = bot_client
        return cls._instance

    def set_ws_broadcast_callback(self, callback: Callable[[Dict[str, Any]], Any]):
        """Sets the callback used to push real-time events to the web dashboard."""
        self.ws_broadcast_callback = callback

    async def enqueue(self, message: discord.Message) -> bool:
        """Stores message temporarily in memory and queues it for DeBERTa evaluation."""
        if message.author.bot or not message.content.strip():
            return False

        buffered = BufferedMessage(
            message_id=message.id,
            guild_id=message.guild.id if message.guild else 0,
            guild_name=message.guild.name if message.guild else "Direct Message",
            channel_id=message.channel.id,
            channel_name=getattr(message.channel, "name", "DM"),
            author_id=message.author.id,
            author_name=str(message.author),
            author_avatar=message.author.display_avatar.url if hasattr(message.author, "display_avatar") else "",
            content=message.content,
            jump_url=message.jump_url,
            created_at=time.time()
        )

        self._active_buffer[message.id] = buffered
        await self._queue.put(buffered)
        self.total_received += 1
        return True

    def start_worker(self):
        """Starts background worker that continuously pops and evaluates messages."""
        if not self._is_running:
            self._is_running = True
            self._worker_task = asyncio.create_task(self._process_loop())
            logger.info("DeBERTa-v3 In-Memory buffer worker started.")

    async def stop_worker(self):
        """Gracefully halts worker."""
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _process_loop(self):
        """Infinite loop processing messages from the temporary in-memory queue."""
        analyzer = DebertaAnalyzer.get_instance()

        while self._is_running:
            try:
                # Wait for next buffered message
                msg = await self._queue.get()
                buffer_wait_ms = round((time.time() - msg.created_at) * 1000, 1)

                guild_settings = await database.get_guild_settings(msg.guild_id)
                threshold = float(guild_settings.get("threshold", 0.70))
                labels = guild_settings.get("labels", [])
                evil_label = guild_settings.get("evil_label", "evil, malicious, or toxic content")
                log_channel_id = guild_settings.get("log_channel_id")
                auto_action = guild_settings.get("auto_action", "log_only")

                # Run DeBERTa-v3 evaluation
                analysis = await analyzer.evaluate_async(
                    text=msg.content,
                    candidate_labels=labels,
                    evil_label=evil_label
                )

                evil_prob = float(analysis["evil_probability"])
                is_evil = (evil_prob >= threshold)
                action_taken = "none"

                # If probability >= threshold (e.g. 70%), execute action and log to designated channel
                if is_evil:
                    self.total_flagged_evil += 1
                    action_taken = auto_action
                    await self._handle_evil_message(msg, analysis, threshold, log_channel_id, auto_action)

                # Persist to database
                await database.log_evaluated_message(
                    message_id=msg.message_id,
                    guild_id=msg.guild_id,
                    guild_name=msg.guild_name,
                    channel_id=msg.channel_id,
                    channel_name=msg.channel_name,
                    author_id=msg.author_id,
                    author_name=msg.author_name,
                    content=msg.content,
                    evil_probability=evil_prob,
                    top_label=analysis["top_label"],
                    all_scores=analysis["scores"],
                    flagged=is_evil,
                    action_taken=action_taken,
                    jump_url=msg.jump_url,
                    latency_ms=analysis["latency_ms"]
                )

                # Evict from temporary active memory buffer
                self._active_buffer.pop(msg.message_id, None)
                self.total_processed += 1
                self.last_processed_time = time.time()
                self._queue.task_done()

                # Broadcast live event to Web Dashboard via WebSocket
                if self.ws_broadcast_callback:
                    payload = {
                        "type": "message_evaluated",
                        "data": {
                            "message_id": msg.message_id,
                            "guild_id": msg.guild_id,
                            "guild_name": msg.guild_name,
                            "channel_id": msg.channel_id,
                            "channel_name": msg.channel_name,
                            "author_name": msg.author_name,
                            "author_avatar": msg.author_avatar,
                            "content": msg.content,
                            "evil_probability": evil_prob,
                            "top_label": analysis["top_label"],
                            "scores": analysis["scores"],
                            "flagged": is_evil,
                            "threshold": threshold,
                            "action_taken": action_taken,
                            "latency_ms": analysis["latency_ms"],
                            "buffer_wait_ms": buffer_wait_ms,
                            "timestamp": time.time()
                        }
                    }
                    try:
                        res = self.ws_broadcast_callback(payload)
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as e:
                        logger.debug(f"Error notifying websocket client: {e}")

            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error(f"Error in DeBERTa in-memory evaluation loop: {err}", exc_info=True)
                await asyncio.sleep(0.5)

    async def _handle_evil_message(
        self,
        msg: BufferedMessage,
        analysis: Dict[str, Any],
        threshold: float,
        log_channel_id: Optional[int],
        auto_action: str
    ):
        """Dispatches alerts to the designated log channel and performs auto-moderation."""
        if not self.bot:
            return

        evil_pct = round(analysis["evil_probability"] * 100, 1)
        threshold_pct = round(threshold * 100, 1)

        # 1. Optional action on original message
        if auto_action in ("delete_and_log", "delete"):
            try:
                ch = self.bot.get_channel(msg.channel_id)
                if ch:
                    target_msg = await ch.fetch_message(msg.message_id)
                    if target_msg:
                        await target_msg.delete()
                        logger.info(f"Auto-deleted message {msg.message_id} from {msg.author_name}")
            except Exception as e:
                logger.warning(f"Failed to auto-delete message {msg.message_id}: {e}")

        # 2. Log to designated channel
        if log_channel_id:
            try:
                log_chan = self.bot.get_channel(log_channel_id)
                if log_chan:
                    embed = discord.Embed(
                        title="🚨 Evil Content Detected (DeBERTa-v3)",
                        description=f"Message exceeded configured certainty threshold (**{evil_pct}%** $\\ge$ **{threshold_pct}%**).",
                        color=discord.Color.red(),
                        timestamp=discord.utils.utcnow()
                    )
                    embed.add_field(name="👤 Author", value=f"<@{msg.author_id}> (`{msg.author_name}`)", inline=True)
                    embed.add_field(name="📍 Channel", value=f"<#{msg.channel_id}>", inline=True)
                    embed.add_field(name="⚡ Evil Certainty", value=f"**{evil_pct}%**", inline=True)
                    embed.add_field(name="💬 Message Content", value=f"```{msg.content[:1000]}```", inline=False)
                    embed.add_field(name="🏷️ Top Classification", value=f"`{analysis['top_label']}`", inline=True)
                    embed.add_field(name="⚙️ Action Taken", value=f"`{auto_action}`", inline=True)
                    embed.add_field(name="🔗 Jump to Message", value=f"[Open Message Link]({msg.jump_url})", inline=True)

                    # Display top probability distribution
                    scores_summary = "\n".join(f"• **{k}**: `{round(v * 100, 1)}%`" for k, v in list(analysis.get("scores", {}).items())[:4])
                    if scores_summary:
                        embed.add_field(name="📊 Probability Scale Breakdown", value=scores_summary, inline=False)

                    embed.set_footer(text=f"Model: {analysis.get('model_used', 'DeBERTa-v3')} | Latency: {analysis.get('latency_ms', 0)}ms")
                    await log_chan.send(embed=embed)
                    logger.info(f"Logged evil message {msg.message_id} ({evil_pct}%) to designated channel {log_channel_id}")
            except Exception as e:
                logger.error(f"Failed to log evil message to designated channel {log_channel_id}: {e}")

    def get_queue_stats(self) -> Dict[str, Any]:
        """Returns live metrics of the in-memory buffer."""
        return {
            "current_buffer_size": len(self._active_buffer),
            "queue_pending_size": self._queue.qsize(),
            "total_received": self.total_received,
            "total_processed": self.total_processed,
            "total_flagged_evil": self.total_flagged_evil,
            "is_running": self._is_running
        }
