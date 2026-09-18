# DeBERTa-v3 Discord Bot & Control Panel

A real-time message analysis bot for Discord powered by Hugging Face's **DeBERTa-v3** zero-shot classification model, accompanied by an elegant, efficient, single-page **Control Panel**.

Incoming messages on monitored channels are **temporarily stored in volatile RAM** while evaluated on a continuous probability scale (0% to 100%). If the certainty of evil/malicious content exceeds the configured threshold (default: **70%**), the bot dispatches an alert with a detailed analysis embed to the **designated log channel**, with optional auto-moderation actions. Once evaluated, messages are evicted from memory.

---

## ⚡ Quick Start

### 1. Run the One-Click Automated Setup
Execute the automated setup script to install all dependencies, pre-cache the DeBERTa-v3 neural pipeline, and initialize the database:
```bash
python setup_environment.py
```
*(On Windows, you can also double-click `setup.bat`)*

### 2. Configure Discord Bot Token
Edit `.env` in this directory:
```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
MODEL_NAME=MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli
DEFAULT_THRESHOLD=0.70
WEB_HOST=127.0.0.1
WEB_PORT=8000
```
> **Important**: In the [Discord Developer Portal](https://discord.com/developers/applications), ensure **Message Content Intent** is enabled under the **Bot** tab.

### 3. Launch the Bot & Control Panel
```bash
python run.py
```
- **Control Panel**: Open [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Discord Bot**: Connects to the gateway and registers slash commands.

---

## 🖥️ Simple Control Panel

The web interface is a streamlined single-page console with zero clutter, zero emojis, and pure efficiency:
- **System Status Strip**: Real-time telemetry indicators for WebSocket feed, Discord gateway state, DeBERTa-v3 pipeline, and active RAM buffer queue.
- **Server Safety Configuration**: Select guild, designate log channels, tune the certainty threshold slider (10% to 99%), and configure auto-actions (`log_only`, `delete_and_log`, `warn_and_log`).
- **Inference Tester**: Test any sentence against the DeBERTa-v3 pipeline and view instant class probabilities and certainty bars.
- **Real-Time Stream**: Live table of evaluated messages updating in real time via WebSockets with status tags (`FLAGGED` / `PASS`), user tags, channel names, and latency.
- **Search & CSV Export**: Instant client-side message filtering and one-click CSV export.

---

## 🤖 Discord Slash Commands

| Command | Permission | Description |
|---|---|---|
| `/setup` | Administrator | Interactive setup to configure log channel, certainty threshold, and auto-actions. |
| `/config` | Administrator | Inspect active configuration, model status, and memory buffer depth. |
| `/set_log_channel <#channel>` | Administrator | Designate channel where messages exceeding the threshold are logged. |
| `/set_threshold <percent>` | Administrator | Set certainty threshold percentage (e.g. `70` for 70%). |
| `/set_action <action>` | Administrator | Set auto-action (`log_only`, `delete_and_log`, `warn_and_log`). |
| `/analyze <text>` | Everyone | Manually run DeBERTa-v3 on text to inspect certainty breakdown. |
| `/stats` | Everyone | View server safety statistics and processed message counts. |
| `/dashboard` | Everyone | Obtain the direct link to the Control Panel. |

---

## 🧪 Automated Testing
Run the automated test suite anytime:
```bash
python test_suite.py
```
Verified passing with 5/5 unit and integration tests.
