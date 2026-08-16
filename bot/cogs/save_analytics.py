"""
Save Analytics Cog
Provides commands for analyzing ARK save file data
"""

import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from typing import Optional
from datetime import datetime
import logging
import asyncio

from bot.ark_data_parser import ArkSaveReader
from bot.asa_parser_adapter import ASAAdapter
from bot.utils.config import Config
from bot.database.server_config_db import is_self_hosted

logger = logging.getLogger(__name__)


class SaveAnalytics(commands.Cog):
    """Commands for ARK save file analytics"""

    def __init__(self, bot):
        self.bot = bot
        # Configurable cluster root (env: ASA_CLUSTER_ROOT). Defaults to C:/ARK
        self.cluster_root = (
            Path(Config.ASA_CLUSTER_ROOT) if Config.ASA_CLUSTER_ROOT else Path(r"C:/ARK")
        )
        self.cache = {}
        self.cache_time = None

    async def cog_load(self):
        """Called when cog is loaded"""
        logger.info("SaveAnalytics cog loaded")

    def _scan_servers(self) -> dict:
        """Scan all servers and return adapters per server"""
        try:
            adapters = ASAAdapter.scan_cluster_adapters(self.cluster_root)
            return adapters
        except Exception as e:
            logger.error(f"Error scanning servers: {e}")
            return {}

    @app_commands.command(name="serverstats", description="Show statistics for all ARK servers")
    async def server_stats(self, interaction: discord.Interaction):
        """Display statistics for all servers in the cluster"""
        # Check if self-hosted (requires local file access)
        if not await is_self_hosted(interaction.guild_id):
            await interaction.response.send_message(
                "❌ This command requires self-hosted servers with local file access.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)

        try:
            # Scan all servers
            adapters = self._scan_servers()

            if not adapters:
                await interaction.followup.send(
                    "❌ No active servers found or unable to access save files."
                )
                return

            # Create embed
            embed = discord.Embed(
                title="📊 ARK Cluster Save Statistics",
                description=f"Statistics from {len(adapters)} active servers",
                color=discord.Color.blue(),
            )

            total_players = 0
            total_tribes = 0
            total_objects = 0
            total_size = 0

            # Process all servers concurrently for better performance
            async def process_server(server_name: str, adapter: ASAAdapter):
                # Use internal reader only for DB info (world .ark SQLite)
                info_reader = ArkSaveReader(adapter.save_dir)
                info = info_reader.get_database_info()

                # Use async methods for non-blocking I/O
                players = await adapter.async_get_players()
                tribes = await adapter.async_get_tribes()

                size_mb = info.get("file_size", 0) / (1024 * 1024)
                objects = info.get("tables", {}).get("game", 0)

                return {
                    "name": server_name,
                    "players": len(players),
                    "tribes": len(tribes),
                    "objects": objects,
                    "size": info.get("file_size", 0),
                    "size_mb": size_mb,
                    "modified": info.get("file_modified", "Unknown"),
                }

            # Process all servers concurrently
            tasks = [process_server(name, adapter) for name, adapter in adapters.items()]
            server_stats = await asyncio.gather(*tasks, return_exceptions=True)

            # Build embed from results
            for stat in server_stats:
                if isinstance(stat, Exception):
                    continue

                total_players += stat["players"]
                total_tribes += stat["tribes"]
                total_objects += stat["objects"]
                total_size += stat["size"]

                modified_str = (
                    stat["modified"].strftime("%Y-%m-%d %H:%M")
                    if isinstance(stat["modified"], datetime)
                    else str(stat["modified"])
                )

                embed.add_field(
                    name=f"🗺️ {stat['name'].upper()}",
                    value=(
                        f"**Players:** {stat['players']}\n"
                        f"**Tribes:** {stat['tribes']}\n"
                        f"**Objects:** {stat['objects']:,}\n"
                        f"**Size:** {stat['size_mb']:.1f} MB\n"
                        f"**Updated:** {modified_str}"
                    ),
                    inline=True,
                )

            # Add totals
            embed.add_field(
                name="📈 Cluster Totals",
                value=(
                    f"**Total Players:** {total_players}\n"
                    f"**Total Tribes:** {total_tribes}\n"
                    f"**Total Objects:** {total_objects:,}\n"
                    f"**Total Size:** {total_size / (1024**3):.2f} GB"
                ),
                inline=False,
            )

            embed.set_footer(text="💾 Data from ARK save files")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in server_stats command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error retrieving server statistics: {str(e)}")

    @app_commands.command(
        name="playerlist", description="List players on a specific server (with level)"
    )
    @app_commands.describe(server="Server name (e.g., astraeos, island, ragnarok)")
    async def player_list(self, interaction: discord.Interaction, server: str):
        """List all players on a specific server"""
        await interaction.response.defer(thinking=True)

        try:
            adapters = self._scan_servers()
            server_lower = server.lower()

            adapter = None
            for name, a in adapters.items():
                if name.lower() == server_lower:
                    adapter = a
                    break

            if not adapter:
                available = ", ".join(sorted(adapters.keys()))
                await interaction.followup.send(
                    f"❌ Server '{server}' not found.\n" f"Available servers: {available}"
                )
                return

            # Use async method for non-blocking I/O
            players = await adapter.async_get_players()

            if not players:
                await interaction.followup.send(f"No player data found for **{server.upper()}**")
                return

            players.sort(key=lambda p: p.last_seen if p.last_seen else datetime.min, reverse=True)

            embed = discord.Embed(
                title=f"👥 Players on {server.upper()}",
                description=f"Found {len(players)} player profiles",
                color=discord.Color.green(),
            )

            for i, player in enumerate(players[:25]):
                last_seen = (
                    player.last_seen.strftime("%Y-%m-%d %H:%M") if player.last_seen else "Unknown"
                )
                level_part = f"Lvl {player.level}" if getattr(player, "level", 0) else "Lvl ?"
                xp_part = (
                    f" | XP {int(player.experience)}" if getattr(player, "experience", 0) else ""
                )

                embed.add_field(
                    name=f"{player.character_name or player.player_name or 'Player'}",
                    value=(
                        f"**{level_part}{xp_part}**\n"
                        f"EOS: `{player.eos_id[:16]}...`\n"
                        f"Last Seen: {last_seen}"
                    ),
                    inline=True,
                )

            if len(players) > 25:
                embed.set_footer(text=f"Showing 25 of {len(players)} players")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in player_list command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error retrieving player list: {str(e)}")

    @app_commands.command(
        name="tribelist",
        description="List tribes on a specific server (with dino counts if available)",
    )
    @app_commands.describe(server="Server name (e.g., astraeos, island, ragnarok)")
    async def tribe_list(self, interaction: discord.Interaction, server: str):
        """List all tribes on a specific server"""
        await interaction.response.defer(thinking=True)

        try:
            adapters = self._scan_servers()
            server_lower = server.lower()

            adapter = None
            for name, a in adapters.items():
                if name.lower() == server_lower:
                    adapter = a
                    break

            if not adapter:
                available = ", ".join(sorted(adapters.keys()))
                await interaction.followup.send(
                    f"❌ Server '{server}' not found.\n" f"Available servers: {available}"
                )
                return

            # Use async method for non-blocking I/O
            tribes = await adapter.async_get_tribes()

            if not tribes:
                await interaction.followup.send(f"No tribe data found for **{server.upper()}**")
                return

            tribes.sort(
                key=lambda t: t.last_active if t.last_active else datetime.min, reverse=True
            )

            embed = discord.Embed(
                title=f"🏛️ Tribes on {server.upper()}",
                description=f"Found {len(tribes)} tribes",
                color=discord.Color.gold(),
            )

            for tribe in tribes[:25]:
                last_active = (
                    tribe.last_active.strftime("%Y-%m-%d %H:%M") if tribe.last_active else "Unknown"
                )
                file_kb = Path(tribe.file_path).stat().st_size / 1024 if tribe.file_path else 0
                dino_part = (
                    f" | Dinos: {tribe.dino_count}" if getattr(tribe, "dino_count", 0) else ""
                )

                embed.add_field(
                    name=f"{tribe.tribe_name or 'Tribe'} ({tribe.tribe_id})",
                    value=(
                        f"Members: {tribe.member_count}{dino_part}\n"
                        f"Last Active: {last_active}\n"
                        f"Data Size: {file_kb:.1f} KB"
                    ),
                    inline=True,
                )

            if len(tribes) > 25:
                embed.set_footer(text=f"Showing 25 of {len(tribes)} tribes")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in tribe_list command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error retrieving tribe list: {str(e)}")

    @app_commands.command(name="playerinv", description="Show a player's inventory (prototype)")
    @app_commands.describe(server="Server name", eos_id="Player EOS ID")
    async def player_inventory(self, interaction: discord.Interaction, server: str, eos_id: str):
        await interaction.response.defer(thinking=True)
        try:
            adapters = self._scan_servers()
            server_lower = server.lower()

            adapter = None
            for name, a in adapters.items():
                if name.lower() == server_lower:
                    adapter = a
                    break
            if not adapter:
                available = ", ".join(sorted(adapters.keys()))
                await interaction.followup.send(
                    f"❌ Server '{server}' not found.\nAvailable: {available}"
                )
                return

            players = adapter.get_players()
            target = next((p for p in players if p.eos_id.lower() == eos_id.lower()), None)
            if not target or not target.file_path:
                await interaction.followup.send("❌ Player not found or missing profile file path.")
                return

            items = adapter.read_player_inventory(Path(target.file_path))
            if not items:
                await interaction.followup.send("No inventory data found (prototype parser).")
                return

            embed = discord.Embed(
                title=f"🎒 Inventory for {target.character_name or target.player_name or target.eos_id[:8]}",
                description=f"Showing up to 20 items",
                color=discord.Color.purple(),
            )
            for entry in items[:20]:
                name = str(entry.get("item_name", "Unknown"))
                qty = int(entry.get("quantity", 0))
                embed.add_field(name=name, value=f"x{qty}", inline=True)

            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in player_inventory: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error retrieving inventory: {str(e)}")


async def setup(bot):
    await bot.add_cog(SaveAnalytics(bot))
