"""
Monitor persistence cog.
Ensures voice_channel_id is persisted per server (by rcon_port) and cleans up stale mappings.
This avoids duplicate channels even if names change later.
"""

import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands, tasks

from bot.utils.config import Config
from bot.database import server_config_db

logger = logging.getLogger("MonitorPersistence")


class MonitorPersistence(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reconcile_loop.start()

    def cog_unload(self):
        self.reconcile_loop.cancel()

    async def _get_status_category(self, guild: discord.Guild) -> Optional[discord.CategoryChannel]:
        for category in guild.categories:
            if category.name == "Server Status":
                return category
        return None

    @tasks.loop(seconds=90.0)
    async def reconcile_loop(self):
        """Periodically reconcile DB voice_channel_id with actual Discord channels."""
        # TEMPORARILY DISABLED: ServerMonitor handles all voice channel management
        # This cog was causing race conditions during bot startup
        return

        guild_id = Config.DISCORD_GUILD_ID
        if not guild_id:
            return
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        category = await self._get_status_category(guild)
        if not category:
            return

        try:
            servers = await server_config_db.get_ark_servers(guild_id)
        except Exception as e:
            logger.error(f"Failed to load servers for reconciliation: {e}")
            return

        # Build quick lookup of existing channels by name
        channel_by_name = {}
        for ch in category.channels:
            if isinstance(ch, discord.VoiceChannel):
                channel_by_name[ch.name.lower()] = ch

        for s in servers:
            name = s.get("name")
            rcon_port = s.get("rcon_port")
            vcid = s.get("voice_channel_id")
            if not name or not rcon_port:
                continue

            # If we have a stored ID, verify it exists; else clear
            if vcid:
                ch = guild.get_channel(int(vcid))
                if ch and isinstance(ch, discord.VoiceChannel):
                    continue
                # NOTE: ServerMonitor handles clearing stale channels in its before_loop
                # We don't clear here to avoid race conditions during bot startup
                # If the channel truly doesn't exist, ServerMonitor will handle it
                if ch:
                    logger.warning(
                        f"Channel {vcid} for {name} exists but is type {type(ch).__name__}, not VoiceChannel"
                    )
                else:
                    logger.debug(
                        f"Channel {vcid} for {name} (port {rcon_port}) not found - ServerMonitor will handle cleanup"
                    )
                continue

            # No stored ID: try to find existing channel by name pattern
            for prefix in ("🟢 ", "🔴 "):
                key = f"{prefix}{name.lower()}"
                # channel names include " - X/Y" suffix; match startswith
                match = next((ch for nm, ch in channel_by_name.items() if nm.startswith(key)), None)
                if match:
                    try:
                        await server_config_db.set_server_voice_channel_id(
                            guild_id, int(rcon_port), int(match.id)
                        )
                        logger.info(
                            f"Linked voice channel from name for {name} (port {rcon_port}): {match.id}"
                        )
                    except Exception as e:
                        logger.error(f"Error persisting voice_channel_id for {name}: {e}")
                    break

    @reconcile_loop.before_loop
    async def before_reconcile(self):
        await self.bot.wait_until_ready()
        # Wait longer to ensure ServerMonitor creates voice channels first
        # Voice channels are created in the voice_channel_update_loop which runs at bot startup
        await asyncio.sleep(30)


async def setup(bot: commands.Bot):
    await bot.add_cog(MonitorPersistence(bot))
