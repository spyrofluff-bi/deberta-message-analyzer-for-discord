"""
Lightweight FastAPI Control Panel Backend for DeBERTa-v3 Discord Bot.
Provides streamlined REST APIs and real-time WebSocket live feed for the control panel.
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field

import database
from analyzer import DebertaAnalyzer
from message_buffer import InMemoryMessageQueue
from config import WEB_HOST, WEB_PORT

logger = logging.getLogger("bot.server")

app = FastAPI(title="DeBERTa-v3 Control Panel", version="2.0.0")

# WebSocket Connection Manager
class ControlPanelConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)

manager = ControlPanelConnectionManager()

def broadcast_live_event(event_data: Dict[str, Any]):
    asyncio.create_task(manager.broadcast(event_data))

InMemoryMessageQueue.get_instance().set_ws_broadcast_callback(broadcast_live_event)

# Request Models
class GuildSettingsUpdate(BaseModel):
    guild_id: int
    threshold: Optional[float] = Field(None, ge=0.01, le=0.99)
    log_channel_id: Optional[int] = None
    auto_action: Optional[str] = None

class QuickInferenceRequest(BaseModel):
    text: str
    labels: Optional[List[str]] = None

# Static Files
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=FileResponse)
async def serve_control_panel():
    index_file = STATIC_DIR / "index.html"
    return FileResponse(str(index_file))

@app.get("/api/status")
async def get_system_status():
    analyzer = DebertaAnalyzer.get_instance()
    queue = InMemoryMessageQueue.get_instance()
    bot = queue.bot

    return {
        "bot": {
            "online": bot.is_ready() if bot else False,
            "username": str(bot.user) if (bot and bot.user) else "Offline",
            "guilds_count": len(bot.guilds) if (bot and bot.guilds) else 0
        },
        "model": analyzer.get_status_summary(),
        "engine": analyzer.get_status_summary(),
        "queue": queue.get_queue_stats()
    }

@app.get("/api/stats")
async def get_stats(guild_id: Optional[int] = None):
    return await database.get_analytics_summary(guild_id)

@app.get("/api/guilds")
async def get_guild_options():
    guilds = await database.get_all_guilds()
    queue = InMemoryMessageQueue.get_instance()
    bot = queue.bot

    if bot and bot.guilds:
        guild_dict = {g["guild_id"]: g for g in guilds}
        for g in bot.guilds:
            channels = [{"id": ch.id, "name": ch.name} for ch in g.text_channels]
            if g.id in guild_dict:
                guild_dict[g.id]["available_channels"] = channels
                guild_dict[g.id]["guild_name"] = g.name
            else:
                guilds.append({
                    "guild_id": g.id,
                    "guild_name": g.name,
                    "log_channel_id": None,
                    "threshold": 0.70,
                    "auto_action": "log_only",
                    "available_channels": channels
                })
    return guilds

@app.post("/api/settings")
async def update_settings(payload: GuildSettingsUpdate):
    update_data = {}
    if payload.threshold is not None:
        update_data["threshold"] = payload.threshold
    if payload.log_channel_id is not None:
        update_data["log_channel_id"] = payload.log_channel_id
    if payload.auto_action is not None:
        update_data["auto_action"] = payload.auto_action

    updated = await database.update_guild_settings(payload.guild_id, **update_data)
    return {"status": "success", "settings": updated}

@app.post("/api/test-analyze")
async def test_analyze(payload: QuickInferenceRequest):
    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    analyzer = DebertaAnalyzer.get_instance()
    return await analyzer.evaluate_async(text=payload.text, candidate_labels=payload.labels)

@app.get("/api/logs")
async def get_logs(limit: int = 50, flagged_only: bool = False):
    clamped = min(150, max(1, limit))
    return await database.get_recent_logs(limit=clamped, flagged_only=flagged_only)

@app.websocket("/ws/live")
async def websocket_live_feed(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        analyzer = DebertaAnalyzer.get_instance()
        queue = InMemoryMessageQueue.get_instance()
        await websocket.send_json({
            "type": "init",
            "engine": analyzer.get_status_summary(),
            "queue": queue.get_queue_stats()
        })
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
