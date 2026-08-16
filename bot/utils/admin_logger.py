"""
Admin action logger - provides a reusable interface for logging admin actions
to both Discord and database with automatic notifications.
"""

import discord
from datetime import datetime
from typing import List, Optional, Dict, Any
import logging

from bot.database import admin_logs_db
from bot.database import server_config_db
from bot.utils.config import Config

logger = logging.getLogger("AdminLogger")


class AdminLogger:
    """Logs admin actions to Discord channel and database with notifications."""

    def __init__(self, bot: discord.Client):
        self.bot = bot

    async def log_action(
        self,
        interaction: discord.Interaction,
        action_type: str,
        servers_affected: List[str],
        details: Dict[str, Any],
        target_player: Optional[str] = None,
        target_player_id: Optional[str] = None,
    ) -> int:
        """
        Log an admin action and send notifications.
        
        Args:
            interaction: Discord interaction for context
            action_type: Type of action (kick, ban, update, etc)
            servers_affected: List of server names affected
            details: Dict with command details (command, parameters, etc)
            target_player: Name of player affected
            target_player_id: ID of player affected
        
        Returns:
            Log entry ID
        """
        admin_id = interaction.user.id
        admin_name = interaction.user.display_name
        guild_id = interaction.guild_id

        # Create initial log entry
        log_id = await admin_logs_db.log_admin_action(
            admin_id=admin_id,
            admin_name=admin_name,
            action_type=action_type,
            servers_affected=servers_affected,
            guild_id=guild_id,
            target_player=target_player,
            target_player_id=target_player_id,
            details=details,
            status="pending",
        )

        # Send notification embed to admin
        notification_embed = self._create_notification_embed(
            admin_name,
            action_type,
            servers_affected,
            target_player,
        )

        try:
            # Send as ephemeral message to admin
            await interaction.followup.send(embed=notification_embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error sending notification to admin: {e}")

        return log_id

    async def log_result(
        self,
        log_id: int,
        status: str,
        results: str,
        interaction: Optional[discord.Interaction] = None,
    ):
        """
        Update log entry with action results and send to admin log channel.
        
        Args:
            log_id: ID of the log entry to update
            status: Final status (success/failed/partial)
            results: String with results details
            interaction: Optional interaction for follow-up notification
        """
        # Update database
        await admin_logs_db.update_admin_action(
            log_id=log_id,
            status=status,
            results=results,
        )

        # Get full log entry for channel posting
        log_entry = await admin_logs_db.get_log_by_id(log_id)
        if not log_entry:
            logger.error(f"Could not find log entry {log_id}")
            return

        # Post to admin log channel
        await self._post_to_log_channel(log_entry)

        # Send result notification to admin if interaction provided
        if interaction:
            result_embed = self._create_result_embed(log_entry, status, results)
            try:
                await interaction.followup.send(embed=result_embed, ephemeral=True)
            except Exception as e:
                logger.error(f"Error sending result notification: {e}")

    async def _post_to_log_channel(self, log_entry: Dict[str, Any]):
        """Post admin action to the admin log channel (DB first, env fallback)."""
        try:
            log_channel_id = None

            # Try DB-based channel first (per guild)
            guild_id = log_entry.get("guild_id")
            if guild_id:
                try:
                    config = await server_config_db.get_server_config(guild_id)
                    log_channel_id = config.get("admin_log_channel_id") if config else None
                except Exception as e:
                    logger.error(f"Failed to read admin_log_channel_id from DB: {e}")

            # Fallback to env/Config
            if not log_channel_id:
                log_channel_id = Config.ADMIN_LOG_CHANNEL_ID

            if not log_channel_id:
                logger.warning("Admin log channel not configured (DB and env were empty)")
                return

            log_channel = self.bot.get_channel(log_channel_id)
            if not log_channel:
                logger.warning(f"Admin log channel {log_channel_id} not found")
                return

            # Create rich embed for channel
            embed = discord.Embed(
                title=f"🔐 Admin Action: {log_entry['action_type'].upper()}",
                description=f"Admin: {log_entry['admin_name']}",
                color=self._get_color_for_status(log_entry["status"]),
                timestamp=datetime.fromisoformat(log_entry["timestamp"]),
            )

            # Add fields
            embed.add_field(
                name="Servers Affected",
                value=", ".join(log_entry["servers_affected"]) or "None",
                inline=False,
            )

            if log_entry["target_player"]:
                embed.add_field(name="Target Player", value=log_entry["target_player"], inline=True)

            if log_entry["target_player_id"]:
                embed.add_field(
                    name="Player ID", value=f"`{log_entry['target_player_id']}`", inline=True
                )

            if log_entry["details"]:
                details_text = "\n".join(
                    [f"**{k}**: {v}" for k, v in log_entry["details"].items()]
                )
                if len(details_text) > 1024:
                    details_text = details_text[:1021] + "..."
                embed.add_field(name="Details", value=details_text, inline=False)

            embed.add_field(name="Status", value=log_entry["status"].upper(), inline=True)

            if log_entry["results"]:
                results_text = log_entry["results"]
                if len(results_text) > 1024:
                    results_text = results_text[:1021] + "..."
                embed.add_field(name="Results", value=f"```{results_text}```", inline=False)

            embed.set_footer(text=f"Log ID: {log_entry['id']}")

            await log_channel.send(embed=embed)

        except Exception as e:
            logger.error(f"Error posting to admin log channel: {e}")

    @staticmethod
    def _create_notification_embed(
        admin_name: str,
        action_type: str,
        servers: List[str],
        target_player: Optional[str] = None,
    ) -> discord.Embed:
        """Create a notification embed for the admin."""
        embed = discord.Embed(
            title="📤 Action Sent to Servers",
            description=f"Sending **{action_type}** command to servers...",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="Servers",
            value=", ".join(servers) if servers else "All servers",
            inline=False,
        )

        if target_player:
            embed.add_field(name="Target", value=target_player, inline=True)

        embed.set_footer(text=f"Initiated by {admin_name}")

        return embed

    @staticmethod
    def _create_result_embed(
        log_entry: Dict[str, Any], status: str, results: str
    ) -> discord.Embed:
        """Create a result embed for the admin."""
        color = discord.Color.green() if status == "success" else discord.Color.red()
        emoji = "✅" if status == "success" else "❌"

        embed = discord.Embed(
            title=f"{emoji} Action Completed",
            description=f"**{log_entry['action_type'].upper()}** - {status.upper()}",
            color=color,
        )

        embed.add_field(
            name="Servers",
            value=", ".join(log_entry["servers_affected"]) or "N/A",
            inline=False,
        )

        if results:
            results_text = results if len(results) <= 1024 else results[:1021] + "..."
            embed.add_field(name="Results", value=f"```{results_text}```", inline=False)

        return embed

    @staticmethod
    def _get_color_for_status(status: str) -> discord.Color:
        """Get Discord color based on status."""
        if status == "success":
            return discord.Color.green()
        elif status == "failed":
            return discord.Color.red()
        elif status == "partial":
            return discord.Color.orange()
        else:
            return discord.Color.blue()
