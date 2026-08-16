"""
Player Cache Cog - Manages the background player caching service.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from datetime import datetime, timedelta, timezone

from bot.services.player_cache_service import PlayerCacheService
from bot.database import players_db, server_config_db
from bot.rcon.client import RCONManager

logger = logging.getLogger("PlayerCacheCog")


class PlayerCache(commands.Cog):
    """Background service for caching player data."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = None
        self.rcon_manager = None

    async def cog_load(self):
        """Called when cog is loaded."""
        # Get RCON manager from server_monitor cog if available
        server_monitor = self.bot.get_cog("ServerMonitor")
        if server_monitor and hasattr(server_monitor, "rcon_manager"):
            self.rcon_manager = server_monitor.rcon_manager

        # Start the background task
        self.player_cache_task.start()
        logger.info("Player cache cog loaded")

    async def cog_unload(self):
        """Called when cog is unloaded."""
        if self.service:
            self.service.stop()
        self.player_cache_task.cancel()
        logger.info("Player cache cog unloaded")

    @tasks.loop(minutes=30)
    async def player_cache_task(self):
        """Background task that runs every 30 minutes."""
        try:
            if not self.service:
                self.service = PlayerCacheService(self.bot, self.rcon_manager)

            await self.service.scan_and_cache_players()

        except Exception as e:
            logger.error(f"Error in player cache task: {e}", exc_info=True)

    @player_cache_task.before_loop
    async def before_player_cache_task(self):
        """Wait for bot to be ready before starting task."""
        await self.bot.wait_until_ready()
        logger.info("Player cache task started")

    async def is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user is admin."""
        if interaction.user.guild_permissions.administrator:
            return True

        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_role_id"):
            admin_role = interaction.guild.get_role(config["admin_role_id"])
            if admin_role and admin_role in interaction.user.roles:
                return True

        return False

    @app_commands.command(
        name="playercache", description="🔄 Manage player cache system (admin only)"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Status - View cache statistics", value="status"),
            app_commands.Choice(name="Scan Now - Force immediate scan", value="scan"),
            app_commands.Choice(name="Purge Old - Remove 90+ day inactive players", value="purge"),
            app_commands.Choice(name="Auto-Link - Run Discord auto-linking", value="autolink"),
        ]
    )
    async def player_cache(self, interaction: discord.Interaction, action: str):
        """Manage the player cache system."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        if action == "status":
            await self._show_status(interaction)
        elif action == "scan":
            await self._force_scan(interaction)
        elif action == "purge":
            await self._purge_old(interaction)
        elif action == "autolink":
            await self._auto_link(interaction)

    async def _show_status(self, interaction: discord.Interaction):
        """Show player cache statistics."""
        await interaction.response.defer(ephemeral=True)

        try:
            # Get cached players
            all_players = await players_db.get_cached_players(days_since_seen=365)
            recent_players = await players_db.get_cached_players(days_since_seen=90)
            active_players = await players_db.get_cached_players(days_since_seen=7)

            # Count linked vs unlinked
            linked_count = sum(1 for p in recent_players if p.get("discord_user_id"))
            auto_linked_count = sum(1 for p in recent_players if p.get("is_auto_linked") == 1)
            manual_linked_count = linked_count - auto_linked_count

            embed = discord.Embed(
                title="📊 Player Cache Statistics",
                description="Current state of the player cache system",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc),
            )

            embed.add_field(
                name="📈 Player Counts",
                value=(
                    f"**Active (7 days):** {len(active_players)}\n"
                    f"**Recent (90 days):** {len(recent_players)}\n"
                    f"**All time:** {len(all_players)}"
                ),
                inline=True,
            )

            embed.add_field(
                name="🔗 Discord Linking",
                value=(
                    f"**Total Linked:** {linked_count}\n"
                    f"**Auto-linked:** {auto_linked_count}\n"
                    f"**Manual:** {manual_linked_count}"
                ),
                inline=True,
            )

            embed.add_field(
                name="⚙️ Service Status",
                value=(
                    f"**Task Running:** {'✅ Yes' if self.player_cache_task.is_running() else '❌ No'}\n"
                    f"**Scan Interval:** 30 minutes\n"
                    f"**Retention:** 90 days"
                ),
                inline=False,
            )

            # Show top players by level
            top_players = sorted(
                [p for p in recent_players if p.get("level", 0) > 0],
                key=lambda x: x.get("level", 0),
                reverse=True,
            )[:5]

            if top_players:
                top_list = "\n".join(
                    [
                        f"**{p.get('character_name') or p.get('player_name', 'Unknown')}** - "
                        f"Lvl {p.get('level', 0)} ({p.get('last_server', 'Unknown')})"
                        for p in top_players
                    ]
                )
                embed.add_field(name="🏆 Top Players (by level)", value=top_list, inline=False)

            embed.set_footer(text="Use /playercache scan to force an immediate cache update")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error showing status: {e}")
            await interaction.followup.send(f"❌ Error retrieving status: {e}", ephemeral=True)

    async def _force_scan(self, interaction: discord.Interaction):
        """Force an immediate cache scan."""
        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.followup.send(
                "🔄 Starting player cache scan... This may take a minute.", ephemeral=True
            )

            if not self.service:
                self.service = PlayerCacheService(self.bot, self.rcon_manager)

            await self.service.scan_and_cache_players()

            # Get updated stats
            cached = await players_db.get_cached_players(days_since_seen=90)

            await interaction.followup.send(
                f"✅ Player cache scan completed!\n"
                f"📊 {len(cached)} players cached (active in last 90 days)",
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"Error forcing scan: {e}")
            await interaction.followup.send(f"❌ Error during scan: {e}", ephemeral=True)

    async def _purge_old(self, interaction: discord.Interaction):
        """Purge players inactive for 90+ days."""
        await interaction.response.defer(ephemeral=True)

        try:
            count = await players_db.purge_old_players(days_threshold=90)

            await interaction.followup.send(
                f"✅ Purged {count} inactive players (90+ days old)", ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error purging old players: {e}")
            await interaction.followup.send(f"❌ Error during purge: {e}", ephemeral=True)

    async def _auto_link(self, interaction: discord.Interaction):
        """Run auto-linking process."""
        await interaction.response.defer(ephemeral=True)

        try:
            linked = await players_db.auto_link_by_name(interaction.guild, days_since_seen=90)

            if linked:
                link_list = "\n".join(
                    [
                        f"• {p.get('character_name') or p.get('player_name', 'Unknown')} → "
                        f"<@{p.get('discord_user_id')}>"
                        for p in linked[:10]  # Show first 10
                    ]
                )

                message = f"✅ Auto-linked {len(linked)} players:\n\n{link_list}"
                if len(linked) > 10:
                    message += f"\n\n...and {len(linked) - 10} more"
            else:
                message = "ℹ️ No new auto-links found. All matching players are already linked."

            await interaction.followup.send(message, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in auto-linking: {e}")
            await interaction.followup.send(f"❌ Error during auto-linking: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    await bot.add_cog(PlayerCache(bot))
