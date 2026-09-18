"""
Discord Slash Commands Cog: Setup, Configuration, and Diagnostics.
Provides commands to set designated log channels, adjust certainty thresholds,
inspect model status, and trigger manual DeBERTa-v3 analysis.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Literal
import database
from analyzer import DebertaAnalyzer
from message_buffer import InMemoryMessageQueue
from config import WEB_HOST, WEB_PORT, PRIMARY_EVIL_LABEL

class SetupCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.analyzer = DebertaAnalyzer.get_instance()
        self.queue = InMemoryMessageQueue.get_instance()

    @app_commands.command(
        name="setup",
        description="Quickly set up the DeBERTa-v3 message analysis bot for this server"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        log_channel="Channel where evil messages (> threshold certainty) will be logged",
        threshold_percent="Certainty threshold percentage (e.g. 70 for 70%)",
        auto_action="Action to execute when threshold is exceeded"
    )
    async def setup_command(
        self,
        interaction: discord.Interaction,
        log_channel: discord.TextChannel,
        threshold_percent: Optional[app_commands.Range[int, 10, 99]] = 70,
        auto_action: Optional[Literal["log_only", "delete_and_log", "warn_and_log"]] = "log_only"
    ):
        await interaction.response.defer(ephemeral=True)

        if not interaction.guild:
            await interaction.followup.send("This command must be used within a server.", ephemeral=True)
            return

        threshold_val = float(threshold_percent) / 100.0
        guild_name = interaction.guild.name

        settings = await database.update_guild_settings(
            guild_id=interaction.guild.id,
            guild_name=guild_name,
            log_channel_id=log_channel.id,
            threshold=threshold_val,
            auto_action=auto_action,
            is_enabled=1
        )

        embed = discord.Embed(
            title="🛡️ DeBERTa-v3 AI Setup Complete",
            description=f"Server analysis is now configured and active!",
            color=discord.Color.green()
        )
        embed.add_field(name="📢 Designated Log Channel", value=log_channel.mention, inline=False)
        embed.add_field(name="🎯 Evil Certainty Threshold", value=f"**{threshold_percent}%** ({threshold_val:.2f})", inline=True)
        embed.add_field(name="⚡ Action on Detection", value=f"`{auto_action}`", inline=True)
        embed.add_field(name="🧠 AI Model", value=f"`{self.analyzer.model_name}`", inline=False)
        embed.add_field(name="🌐 Web Dashboard", value=f"[Open Dashboard](http://{WEB_HOST}:{WEB_PORT})", inline=False)
        embed.set_footer(text="Messages are buffered in memory and evaluated in real-time.")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="config",
        description="View the current DeBERTa-v3 configuration and model status"
    )
    @app_commands.default_permissions(administrator=True)
    async def config_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Must be run inside a guild.", ephemeral=True)
            return

        settings = await database.get_guild_settings(interaction.guild.id)
        model_status = self.analyzer.get_status_summary()
        queue_stats = self.queue.get_queue_stats()

        log_ch_text = f"<#{settings.get('log_channel_id')}>" if settings.get("log_channel_id") else "*Not configured (use /set_log_channel)*"
        threshold_pct = int(settings.get("threshold", 0.70) * 100)

        embed = discord.Embed(
            title="⚙️ Current DeBERTa-v3 Configuration",
            color=discord.Color.blue()
        )
        embed.add_field(name="📢 Designated Log Channel", value=log_ch_text, inline=True)
        embed.add_field(name="🎯 Evil Threshold", value=f"**{threshold_pct}%**", inline=True)
        embed.add_field(name="⚡ Auto Action", value=f"`{settings.get('auto_action', 'log_only')}`", inline=True)

        status_emoji = "🟢" if model_status["status"] == "ready" else "🟡" if model_status["status"] == "loading" else "🔵"
        embed.add_field(
            name="🤖 Model Diagnostics",
            value=f"{status_emoji} Status: `{model_status['status']}`\n"
                  f"• Model: `{model_status['model_name']}`\n"
                  f"• Device: `{model_status['device']}`\n"
                  f"• Avg Inference: `{model_status['avg_latency_ms']} ms`",
            inline=False
        )
        embed.add_field(
            name="📦 Memory Buffer Status",
            value=f"• Active In-Memory Messages: `{queue_stats['current_buffer_size']}`\n"
                  f"• Queue Pending: `{queue_stats['queue_pending_size']}`\n"
                  f"• Total Processed: `{queue_stats['total_processed']}`\n"
                  f"• Evil Caught: `{queue_stats['total_flagged_evil']}`",
            inline=False
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="set_log_channel",
        description="Configure the designated channel where evil messages (> 70% certainty) are logged"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel="The channel where detection alerts will be sent")
    async def set_log_channel_command(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        await database.set_log_channel(interaction.guild.id, channel.id, interaction.guild.name)
        await interaction.response.send_message(
            f"✅ Designated log channel set to {channel.mention}. Messages with evil certainty $\\ge$ threshold will be posted here.",
            ephemeral=True
        )

    @app_commands.command(
        name="set_threshold",
        description="Set the certainty threshold percentage for logging evil messages (e.g. 70 for 70%)"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(percent="Threshold percentage (10 to 99)")
    async def set_threshold_command(self, interaction: discord.Interaction, percent: app_commands.Range[int, 10, 99]):
        if not interaction.guild:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        float_val = percent / 100.0
        await database.set_threshold(interaction.guild.id, float_val)
        await interaction.response.send_message(
            f"✅ Evil certainty threshold updated to **{percent}%** (`{float_val:.2f}`). Messages exceeding this certainty will be logged.",
            ephemeral=True
        )

    @app_commands.command(
        name="set_action",
        description="Choose what action is taken when an evil message is detected"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(action="The action to take")
    async def set_action_command(
        self,
        interaction: discord.Interaction,
        action: Literal["log_only", "delete_and_log", "warn_and_log"]
    ):
        if not interaction.guild:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        await database.update_guild_settings(interaction.guild.id, auto_action=action)
        await interaction.response.send_message(
            f"✅ Detection action updated to: `{action}`",
            ephemeral=True
        )

    @app_commands.command(
        name="analyze",
        description="Run DeBERTa-v3 on any text to inspect its probability scale in real-time"
    )
    @app_commands.describe(text="The message text to analyze with DeBERTa-v3")
    async def analyze_command(self, interaction: discord.Interaction, text: str):
        await interaction.response.defer(ephemeral=False)

        settings = await database.get_guild_settings(interaction.guild.id) if interaction.guild else {}
        labels = settings.get("labels", [])
        threshold = settings.get("threshold", 0.70)

        result = await self.analyzer.evaluate_async(
            text=text,
            candidate_labels=labels
        )

        evil_prob = result["evil_probability"]
        evil_pct = round(evil_prob * 100, 1)
        threshold_pct = round(threshold * 100, 1)
        is_evil = evil_prob >= threshold

        color = discord.Color.red() if is_evil else discord.Color.green()
        status_tag = "🚨 EVIL / MALICIOUS" if is_evil else "✅ SAFE / BENIGN"

        embed = discord.Embed(
            title=f"DeBERTa-v3 Message Analysis: {status_tag}",
            description=f"Evaluated text:\n```{text[:800]}```",
            color=color
        )
        embed.add_field(name="⚡ Evil Certainty", value=f"**{evil_pct}%**", inline=True)
        embed.add_field(name="🎯 Server Threshold", value=f"{threshold_pct}%", inline=True)
        embed.add_field(name="⏱️ Latency", value=f"{result.get('latency_ms', 0)} ms", inline=True)
        embed.add_field(name="🏷️ Top Prediction", value=f"`{result['top_label']}`", inline=True)
        embed.add_field(name="🤖 Model", value=f"`{result.get('model_used', 'DeBERTa-v3')}`", inline=True)

        scores_str = "\n".join(f"• **{k}**: `{round(v * 100, 1)}%`" for k, v in result.get("scores", {}).items())
        embed.add_field(name="📊 Probability Distribution", value=scores_str or "N/A", inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="stats",
        description="View live server message analytics and detection statistics"
    )
    async def stats_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        guild_id = interaction.guild.id if interaction.guild else None
        summary = await database.get_analytics_summary(guild_id)
        queue_stats = self.queue.get_queue_stats()

        embed = discord.Embed(
            title="📊 DeBERTa-v3 Message Analytics",
            color=discord.Color.purple()
        )
        embed.add_field(name="📨 Total Messages Analyzed", value=f"**{summary['total_analyzed']}**", inline=True)
        embed.add_field(name="🚨 Flagged Evil Messages", value=f"**{summary['flagged_count']}**", inline=True)
        embed.add_field(name="🛡️ Safe Content Rate", value=f"**{summary['safe_rate_pct']}%**", inline=True)
        embed.add_field(name="🔥 Messages Certainty $\\ge$ 70%", value=f"**{summary['evil_over_70_count']}**", inline=True)
        embed.add_field(name="⚡ Avg DeBERTa Latency", value=f"**{summary['avg_latency_ms']} ms**", inline=True)
        embed.add_field(name="📦 Current Memory Buffer", value=f"**{queue_stats['current_buffer_size']}** items", inline=True)

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="dashboard",
        description="Get the link to access the DeBERTa-v3 Web Dashboard"
    )
    async def dashboard_command(self, interaction: discord.Interaction):
        url = f"http://{WEB_HOST}:{WEB_PORT}"
        embed = discord.Embed(
            title="🌐 DeBERTa-v3 Web Dashboard",
            description=f"Monitor real-time live evaluations, view analytics charts, inspect queue buffer, and configure server settings:\n\n🔗 **[Click here to open Web Dashboard]({url})**",
            color=discord.Color.teal()
        )
        embed.add_field(name="Host", value=f"`{WEB_HOST}`", inline=True)
        embed.add_field(name="Port", value=f"`{WEB_PORT}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCommands(bot))
