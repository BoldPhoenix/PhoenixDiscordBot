"""
Bot Control - Utility commands for the Phoenix ARK bot.
Bot service management (restart/stop) is intentionally NOT exposed via Discord —
use SSH + systemctl on the Pi 5 directly.
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging

logger = logging.getLogger("BotControl")


class BotControl(commands.Cog):
    """Utility commands for the Phoenix ARK bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="🏓 Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Check bot response latency."""
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"🏓 Pong! Latency: **{latency}ms**", ephemeral=True
        )


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(BotControl(bot))
