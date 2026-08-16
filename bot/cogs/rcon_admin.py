"""
RCON Admin Commands - ARK Server Management via RCON

Provides comprehensive admin commands for ARK server management including:
- Player management (kick, ban, whitelist)
- Server control (broadcast, save, dino wipe)
- Item/dino spawning
- Admin utilities
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
import re
from typing import Optional, List
import asyncio

from bot.rcon.client import RCONManager
from bot.database import server_config_db, players_db
from bot.utils.subscription_checker import check_feature

logger = logging.getLogger("RconAdmin")


class RconAdmin(commands.Cog):
    """Advanced ARK server management via RCON."""

    def __init__(self, bot):
        self.bot = bot
        self.rcon_manager = None

    async def cog_load(self):
        """Initialize RCON manager when cog loads."""
        logger.info("RCON Admin cog loaded")
        # RCON manager will be initialized per-command with current server config

    async def get_servers_for_guild(self, guild_id: int):
        """Get ARK servers configured for a guild."""
        servers = await server_config_db.get_ark_servers(guild_id)
        if servers and len(servers) > 0:
            return servers
        return []

    async def is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions."""
        if interaction.user.guild_permissions.administrator:
            return True

        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_role_id"):
            admin_role = interaction.guild.get_role(config["admin_role_id"])
            if admin_role and admin_role in interaction.user.roles:
                return True

        return False

    async def execute_rcon(self, server_config: dict, command: str) -> tuple[bool, str]:
        """Execute RCON command on a server."""
        try:
            rcon_manager = RCONManager([server_config])
            response = await rcon_manager.execute_command(server_config.get("name"), command)
            return True, response if response else "Command executed successfully"
        except Exception as e:
            logger.error(f"RCON command failed: {e}")
            return False, str(e)

    async def get_server_choices(self, interaction: discord.Interaction) -> List[app_commands.Choice[str]]:
        """Get list of servers for autocomplete."""
        servers = await self.get_servers_for_guild(interaction.guild_id)
        return [
            app_commands.Choice(name=server.get("name", "Unknown"), value=server.get("name", "")) for server in servers
        ]

    # ==================== PLAYER MANAGEMENT ====================

    @app_commands.command(name="whitelistplayer", description="📋 Add player to whitelist")
    @app_commands.describe(steam_id="Player's Steam ID", server_name="Server name")
    async def whitelist_player(self, interaction: discord.Interaction, steam_id: str, server_name: str):
        """Add a player to the server whitelist."""
        await interaction.response.defer(ephemeral=True)

        if not await check_feature(interaction, "rcon_advanced"):
            return
        if not await self.is_admin(interaction):
            await interaction.followup.send("❌ You need admin permissions to use this command.", ephemeral=True)
            return

        servers = await self.get_servers_for_guild(interaction.guild_id)
        server = next((s for s in servers if s.get("name", "").lower() == server_name.lower()), None)

        if not server:
            await interaction.followup.send(f"❌ Server '{server_name}' not found.", ephemeral=True)
            return

        command = f"AllowPlayerToJoinNoCheck {steam_id}"
        success, response = await self.execute_rcon(server, command)

        embed = discord.Embed(
            title="📋 Player Whitelisted",
            description=f"**Steam ID:** {steam_id}\n**Server:** {server_name}\n**Result:** {response}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log to admin channel
        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_log_channel_id"):
            log_channel = self.bot.get_channel(config["admin_log_channel_id"])
            if log_channel:
                await log_channel.send(embed=embed)

    # ==================== SERVER CONTROL ====================

    @app_commands.command(name="saveworld", description="💾 Force save the world")
    @app_commands.describe(server_name="Server name (leave empty for all servers)")
    async def save_world(self, interaction: discord.Interaction, server_name: Optional[str] = None):
        """Force a world save."""
        await interaction.response.defer(ephemeral=True)

        if not await self.is_admin(interaction):
            await interaction.followup.send("❌ You need admin permissions to use this command.", ephemeral=True)
            return

        servers = await self.get_servers_for_guild(interaction.guild_id)

        if server_name:
            servers = [s for s in servers if s.get("name", "").lower() == server_name.lower()]
            if not servers:
                await interaction.followup.send(f"❌ Server '{server_name}' not found.", ephemeral=True)
                return

        results = []
        for server in servers:
            success, response = await self.execute_rcon(server, "SaveWorld")
            status = "✅" if success else "❌"
            # Handle various response formats
            if isinstance(response, str):
                # Remove any tuple-like artifacts and clean up
                clean_response = response.strip()
                # Handle patterns like "(True, 'World Saved \n ')"
                if clean_response.startswith("(") and ")" in clean_response:
                    # Extract just the message part
                    parts = clean_response.split(",", 1)
                    if len(parts) > 1:
                        clean_response = parts[1].strip(" '\"")
                # Handle newlines in response
                clean_response = clean_response.replace("\\n", " ").replace("\n", " ").replace("  ", " ")
            else:
                clean_response = "Saved successfully" if success else "Failed"
            results.append(f"{status} **{server.get('name')}**: {clean_response[:50]}")

        embed = discord.Embed(
            title="💾 World Save Executed",
            description="\n".join(results),
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"By {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log to admin channel
        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_log_channel_id"):
            log_channel = self.bot.get_channel(config["admin_log_channel_id"])
            if log_channel:
                await log_channel.send(embed=embed)

    @app_commands.command(name="destroywilddinos", description="🦖 Destroy all wild dinosaurs")
    @app_commands.describe(server_name="Server name (leave empty for all servers)")
    async def destroy_wild_dinos(self, interaction: discord.Interaction, server_name: Optional[str] = None):
        """Destroy all wild dinosaurs for respawn."""
        await interaction.response.defer(ephemeral=True)

        if not await check_feature(interaction, "rcon_advanced"):
            return
        if not await self.is_admin(interaction):
            await interaction.followup.send("❌ You need admin permissions to use this command.", ephemeral=True)
            return

        servers = await self.get_servers_for_guild(interaction.guild_id)

        if server_name:
            servers = [s for s in servers if s.get("name", "").lower() == server_name.lower()]
            if not servers:
                await interaction.followup.send(f"❌ Server '{server_name}' not found.", ephemeral=True)
                return

        results = []
        for server in servers:
            success, response = await self.execute_rcon(server, "DestroyWildDinos")
            status = "✅" if success else "❌"
            results.append(f"{status} **{server.get('name')}**: {response[:50]}")

        embed = discord.Embed(
            title="🦖 Wild Dinos Destroyed",
            description="\n".join(results),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"By {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log to admin channel
        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_log_channel_id"):
            log_channel = self.bot.get_channel(config["admin_log_channel_id"])
            if log_channel:
                await log_channel.send(embed=embed)

    # ==================== ITEM & DINO MANAGEMENT ====================

    @app_commands.command(name="giveexptoplayer", description="⭐ Give XP to a player")
    @app_commands.describe(
        player_name="Player name or Steam ID",
        xp_amount="Amount of XP to give",
        tribe_share="Share with tribe (default: false)",
        server_name="Server name",
    )
    async def give_xp(
        self,
        interaction: discord.Interaction,
        player_name: str,
        xp_amount: int,
        server_name: str,
        tribe_share: bool = False,
    ):
        """Give XP to a player."""
        await interaction.response.defer(ephemeral=True)

        if not await check_feature(interaction, "rcon_advanced"):
            return
        if not await self.is_admin(interaction):
            await interaction.followup.send("❌ You need admin permissions to use this command.", ephemeral=True)
            return

        servers = await self.get_servers_for_guild(interaction.guild_id)
        server = next((s for s in servers if s.get("name", "").lower() == server_name.lower()), None)

        if not server:
            await interaction.followup.send(f"❌ Server '{server_name}' not found.", ephemeral=True)
            return

        # Validate player name to prevent RCON command injection
        if not re.match(r'^[a-zA-Z0-9_ .\-]+$', player_name) or len(player_name) > 100:
            await interaction.followup.send("❌ Invalid player name. Only alphanumeric characters, underscores, hyphens, and dots are allowed.", ephemeral=True)
            return

        tribe_flag = "1" if tribe_share else "0"
        command = f"GiveExpToPlayer {player_name} {xp_amount} {tribe_flag} 0"

        success, response = await self.execute_rcon(server, command)

        embed = discord.Embed(
            title="⭐ XP Given",
            description=(
                f"**Player:** {player_name}\n"
                f"**XP Amount:** {xp_amount:,}\n"
                f"**Tribe Share:** {tribe_share}\n"
                f"**Server:** {server_name}\n"
                f"**Result:** {response}"
            ),
            color=discord.Color.gold() if success else discord.Color.red(),
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==================== ADMIN UTILITIES ====================

    @app_commands.command(name="getchat", description="💬 Get recent chat messages")
    @app_commands.describe(server_name="Server name")
    async def get_chat(self, interaction: discord.Interaction, server_name: str):
        """Get recent chat messages from server."""
        await interaction.response.defer(ephemeral=True)

        if not await check_feature(interaction, "rcon_advanced"):
            return
        if not await self.is_admin(interaction):
            await interaction.followup.send("❌ You need admin permissions to use this command.", ephemeral=True)
            return

        servers = await self.get_servers_for_guild(interaction.guild_id)
        server = next((s for s in servers if s.get("name", "").lower() == server_name.lower()), None)

        if not server:
            await interaction.followup.send(f"❌ Server '{server_name}' not found.", ephemeral=True)
            return

        success, response = await self.execute_rcon(server, "GetChat")

        if len(response) > 1900:
            response = response[-1900:]
            response = "...\n" + response

        embed = discord.Embed(
            title=f"💬 Recent Chat - {server_name}",
            description=f"```\n{response}\n```" if response else "No recent chat",
            color=discord.Color.blue(),
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # Autocomplete for server selection
    @whitelist_player.autocomplete("server_name")
    @save_world.autocomplete("server_name")
    @destroy_wild_dinos.autocomplete("server_name")
    @give_xp.autocomplete("server_name")
    @get_chat.autocomplete("server_name")
    async def server_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for server selection."""
        servers = await self.get_servers_for_guild(interaction.guild_id)

        choices = [
            app_commands.Choice(name=server.get("name", "Unknown"), value=server.get("name", "")) for server in servers
        ]

        if current:
            choices = [choice for choice in choices if current.lower() in choice.name.lower()]

        return choices[:25]


async def setup(bot):
    """Load the RconAdmin cog."""
    await bot.add_cog(RconAdmin(bot))
