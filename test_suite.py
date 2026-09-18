"""
Automated Test Suite for DeBERTa-v3 Discord Message Analysis Bot & Web Dashboard.
Tests Database operations, Analyzer inference logic, In-Memory Buffer, and FastAPI REST endpoints.
"""

import sys
import os
import asyncio
import unittest

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database
from analyzer import DebertaAnalyzer
from message_buffer import InMemoryMessageQueue, BufferedMessage
from server import app
from starlette.testclient import TestClient

class TestDebertaBotSuite(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Run async DB initialization
        asyncio.run(database.init_db())

    def test_01_database_guild_settings(self):
        """Test guild settings creation, default values, and updates."""
        import random
        async def run_test():
            test_guild_id = random.randint(100000000, 999999999)
            settings = await database.get_guild_settings(test_guild_id)
            self.assertEqual(settings["guild_id"], test_guild_id)
            self.assertEqual(settings["threshold"], 0.70)
            self.assertIsNone(settings["log_channel_id"])

            # Update threshold to 75%
            updated = await database.set_threshold(test_guild_id, 0.75)
            self.assertEqual(updated["threshold"], 0.75)

            # Designate log channel
            log_ch_id = 1234567890
            updated = await database.set_log_channel(test_guild_id, log_ch_id, "Test Server")
            self.assertEqual(updated["log_channel_id"], log_ch_id)
            self.assertEqual(updated["guild_name"], "Test Server")

        asyncio.run(run_test())

    def test_02_database_message_logging(self):
        """Test logging evaluated messages, both evil and safe."""
        async def run_test():
            row_id_evil = await database.log_evaluated_message(
                message_id=101,
                guild_id=999999123,
                guild_name="Test Server",
                channel_id=1234567890,
                channel_name="general",
                author_id=555,
                author_name="BadUser#0001",
                content="I will destroy and attack your server!",
                evil_probability=0.88,
                top_label="evil, malicious, or toxic content",
                all_scores={"evil, malicious, or toxic content": 0.88, "safe": 0.12},
                flagged=True,
                action_taken="log_only",
                jump_url="https://discord.com/channels/999/123/101",
                latency_ms=15.4
            )
            self.assertGreater(row_id_evil, 0)

            row_id_safe = await database.log_evaluated_message(
                message_id=102,
                guild_id=999999123,
                guild_name="Test Server",
                channel_id=1234567890,
                channel_name="general",
                author_id=666,
                author_name="GoodUser#0002",
                content="Hello everyone, have a great day!",
                evil_probability=0.03,
                top_label="safe and benign casual conversation",
                all_scores={"evil": 0.03, "safe": 0.97},
                flagged=False,
                action_taken="none",
                jump_url="https://discord.com/channels/999/123/102",
                latency_ms=12.1
            )
            self.assertGreater(row_id_safe, 0)

            # Retrieve logs
            logs = await database.get_recent_logs(limit=10, guild_id=999999123)
            self.assertGreaterEqual(len(logs), 2)

            # Check stats
            summary = await database.get_analytics_summary(guild_id=999999123)
            self.assertGreaterEqual(summary["total_analyzed"], 2)
            self.assertGreaterEqual(summary["flagged_count"], 1)
            self.assertGreaterEqual(summary["evil_over_70_count"], 1)

        asyncio.run(run_test())

    def test_03_analyzer_scoring(self):
        """Test DeBERTa-v3 analyzer scoring and discrimination between evil and safe messages."""
        analyzer = DebertaAnalyzer.get_instance()
        
        # Test evil text
        evil_result = analyzer.evaluate_sync("I will attack and murder everyone in this server, die!")
        self.assertIn("evil_probability", evil_result)
        self.assertGreater(evil_result["evil_probability"], 0.60)

        # Test safe text
        safe_result = analyzer.evaluate_sync("Good morning team! Hope you all have a wonderful day.")
        self.assertIn("evil_probability", safe_result)
        self.assertLess(safe_result["evil_probability"], 0.40)

    def test_04_message_buffer_lifecycle(self):
        """Test in-memory buffering and queue metrics."""
        queue = InMemoryMessageQueue.get_instance()
        stats = queue.get_queue_stats()
        self.assertIn("current_buffer_size", stats)
        self.assertIn("total_received", stats)

    def test_05_fastapi_endpoints(self):
        """Test Web Dashboard REST endpoints."""
        client = TestClient(app)

        # Root HTML
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("DeBERTa-v3", resp.text)

        # /api/status
        resp = client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("model", data)
        self.assertIn("queue", data)

        # /api/stats
        resp = client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)
        stats = resp.json()
        self.assertIn("total_analyzed", stats)
        self.assertIn("safe_rate_pct", stats)

        # /api/guilds
        resp = client.get("/api/guilds")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

        # /api/test-analyze (Playground)
        resp = client.post("/api/test-analyze", json={"text": "Test message to analyze"})
        self.assertEqual(resp.status_code, 200)
        result = resp.json()
        self.assertIn("evil_probability", result)
        self.assertIn("scores", result)

if __name__ == "__main__":
    unittest.main()
