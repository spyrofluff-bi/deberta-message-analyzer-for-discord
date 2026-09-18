"""
Asynchronous SQLite database interface for DeBERTa-v3 Discord Bot.
Handles guild configurations, designated log channels, thresholds, and message evaluation history.
"""

import json
import logging
import aiosqlite
from datetime import datetime
from typing import Optional, Dict, Any, List
from config import DB_PATH, DEFAULT_THRESHOLD, DEFAULT_LABELS, PRIMARY_EVIL_LABEL, DEFAULT_ACTION

logger = logging.getLogger("bot.database")

async def init_db():
    """Initializes the database schema if tables do not exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                guild_name TEXT,
                log_channel_id INTEGER,
                threshold REAL DEFAULT 0.70,
                labels_json TEXT,
                evil_label TEXT,
                auto_action TEXT DEFAULT 'log_only',
                monitored_channels_json TEXT DEFAULT '[]',
                is_enabled INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS message_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                guild_id INTEGER,
                guild_name TEXT,
                channel_id INTEGER,
                channel_name TEXT,
                author_id INTEGER,
                author_name TEXT,
                content TEXT,
                evil_probability REAL,
                top_label TEXT,
                all_scores_json TEXT,
                flagged INTEGER DEFAULT 0,
                action_taken TEXT DEFAULT 'none',
                jump_url TEXT,
                latency_ms REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Indexes for fast search and analytics queries
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_guild ON message_logs(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_flagged ON message_logs(flagged)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_logs_created ON message_logs(created_at)")
        await db.commit()
    logger.info("Database initialized successfully at %s", DB_PATH)

async def get_guild_settings(guild_id: int) -> Dict[str, Any]:
    """Retrieves settings for a specific guild, inserting defaults if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                data = dict(row)
                data["labels"] = json.loads(data["labels_json"]) if data.get("labels_json") else DEFAULT_LABELS
                data["monitored_channels"] = json.loads(data["monitored_channels_json"]) if data.get("monitored_channels_json") else []
                return data

            # Insert default settings
            default_data = {
                "guild_id": guild_id,
                "guild_name": f"Guild {guild_id}",
                "log_channel_id": None,
                "threshold": DEFAULT_THRESHOLD,
                "labels_json": json.dumps(DEFAULT_LABELS),
                "evil_label": PRIMARY_EVIL_LABEL,
                "auto_action": DEFAULT_ACTION,
                "monitored_channels_json": "[]",
                "is_enabled": 1
            }
            await db.execute("""
                INSERT INTO guild_settings (guild_id, guild_name, log_channel_id, threshold, labels_json, evil_label, auto_action, monitored_channels_json, is_enabled)
                VALUES (:guild_id, :guild_name, :log_channel_id, :threshold, :labels_json, :evil_label, :auto_action, :monitored_channels_json, :is_enabled)
            """, default_data)
            await db.commit()

            default_data["labels"] = DEFAULT_LABELS
            default_data["monitored_channels"] = []
            return default_data

async def update_guild_settings(guild_id: int, **kwargs) -> Dict[str, Any]:
    """Updates specific settings for a guild."""
    # Ensure guild exists first
    await get_guild_settings(guild_id)

    allowed_fields = [
        "guild_name", "log_channel_id", "threshold", "labels_json",
        "evil_label", "auto_action", "monitored_channels_json", "is_enabled"
    ]
    updates = []
    params = []

    for key, value in kwargs.items():
        if key in allowed_fields:
            updates.append(f"{key} = ?")
            params.append(value)
        elif key == "labels":
            updates.append("labels_json = ?")
            params.append(json.dumps(value))
        elif key == "monitored_channels":
            updates.append("monitored_channels_json = ?")
            params.append(json.dumps(value))

    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(guild_id)
        sql = f"UPDATE guild_settings SET {', '.join(updates)} WHERE guild_id = ?"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(sql, params)
            await db.commit()

    return await get_guild_settings(guild_id)

async def set_log_channel(guild_id: int, channel_id: Optional[int], guild_name: Optional[str] = None) -> Dict[str, Any]:
    """Sets designated log channel for a guild."""
    kwargs: Dict[str, Any] = {"log_channel_id": channel_id}
    if guild_name:
        kwargs["guild_name"] = guild_name
    return await update_guild_settings(guild_id, **kwargs)

async def set_threshold(guild_id: int, threshold: float) -> Dict[str, Any]:
    """Sets evil certainty threshold (0.0 to 1.0) for a guild."""
    clamped = max(0.01, min(0.99, threshold))
    return await update_guild_settings(guild_id, threshold=clamped)

async def log_evaluated_message(
    message_id: int,
    guild_id: int,
    guild_name: str,
    channel_id: int,
    channel_name: str,
    author_id: int,
    author_name: str,
    content: str,
    evil_probability: float,
    top_label: str,
    all_scores: Dict[str, float],
    flagged: bool,
    action_taken: str,
    jump_url: str = "",
    latency_ms: float = 0.0
) -> int:
    """Inserts an evaluated message record into database."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO message_logs (
                message_id, guild_id, guild_name, channel_id, channel_name,
                author_id, author_name, content, evil_probability, top_label,
                all_scores_json, flagged, action_taken, jump_url, latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message_id, guild_id, guild_name, channel_id, channel_name,
            author_id, author_name, content, evil_probability, top_label,
            json.dumps(all_scores), 1 if flagged else 0, action_taken, jump_url, latency_ms
        ))
        await db.commit()
        return cursor.lastrowid

async def get_recent_logs(limit: int = 50, guild_id: Optional[int] = None, flagged_only: bool = False) -> List[Dict[str, Any]]:
    """Fetches recent analyzed message logs."""
    query = "SELECT * FROM message_logs WHERE 1=1"
    params = []
    if guild_id:
        query += " AND guild_id = ?"
        params.append(guild_id)
    if flagged_only:
        query += " AND flagged = 1"
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["scores"] = json.loads(item["all_scores_json"]) if item.get("all_scores_json") else {}
                results.append(item)
            return results

async def get_all_guilds() -> List[Dict[str, Any]]:
    """Retrieves all guild settings."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM guild_settings ORDER BY guild_name ASC") as cursor:
            rows = await cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["labels"] = json.loads(item["labels_json"]) if item.get("labels_json") else DEFAULT_LABELS
                item["monitored_channels"] = json.loads(item["monitored_channels_json"]) if item.get("monitored_channels_json") else []
                results.append(item)
            return results

async def get_analytics_summary(guild_id: Optional[int] = None) -> Dict[str, Any]:
    """Computes high-level analytics for the dashboard."""
    where_clause = "WHERE guild_id = ?" if guild_id else ""
    params = [guild_id] if guild_id else []

    async with aiosqlite.connect(DB_PATH) as db:
        # Total counts and flagged counts
        async with db.execute(f"SELECT COUNT(*), SUM(flagged), AVG(evil_probability), AVG(latency_ms) FROM message_logs {where_clause}", params) as cursor:
            total, flagged, avg_prob, avg_latency = await cursor.fetchone()
            total = total or 0
            flagged = flagged or 0
            avg_prob = avg_prob or 0.0
            avg_latency = avg_latency or 0.0

        # High risk threshold distribution
        async with db.execute(f"SELECT COUNT(*) FROM message_logs {where_clause and where_clause + ' AND' or 'WHERE'} evil_probability >= 0.70", params) as cursor:
            (evil_over_70,) = await cursor.fetchone()
            evil_over_70 = evil_over_70 or 0

        # Actions distribution
        async with db.execute(f"SELECT action_taken, COUNT(*) FROM message_logs {where_clause} GROUP BY action_taken", params) as cursor:
            action_rows = await cursor.fetchall()
            actions_breakdown = {row[0]: row[1] for row in action_rows}

        # Hourly / Recent timeline (last 24 hours buckets or last 10 entries)
        async with db.execute(f"""
            SELECT strftime('%H:00', created_at) as hour,
                   COUNT(*) as total_msgs,
                   SUM(flagged) as flagged_msgs,
                   AVG(evil_probability) as avg_evil
            FROM message_logs {where_clause}
            GROUP BY hour
            ORDER BY created_at ASC
            LIMIT 24
        """, params) as cursor:
            timeline_rows = await cursor.fetchall()
            timeline = [
                {"hour": r[0], "total": r[1], "flagged": r[2] or 0, "avg_prob": round(r[3] or 0.0, 3)}
                for r in timeline_rows
            ]

    safe_rate = round(((total - flagged) / total * 100) if total > 0 else 100.0, 1)
    return {
        "total_analyzed": total,
        "flagged_count": flagged,
        "evil_over_70_count": evil_over_70,
        "safe_rate_pct": safe_rate,
        "avg_evil_probability": round(avg_prob, 4),
        "avg_latency_ms": round(avg_latency, 1),
        "actions_breakdown": actions_breakdown,
        "timeline": timeline
    }
