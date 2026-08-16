"""
Log Viewer Commands - ARK Server Log Management

Provides comprehensive log viewing and management functionality:
- Real-time log viewing with filtering
- Log file management (rotation, cleanup)
- Log search and analysis
- Remote log access via agent system
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional, List
import asyncio
import re
from datetime import datetime, timedelta

from bot.database import server_config_db
from bot.utils.subscription_checker import check_feature
from bot.utils.log_parser import parse_server_startup_info
from bot.utils.config import Config

logger = logging.getLogger("LogViewer")


class LogViewerView(discord.ui.View):
    """Pagination view for server logs."""

    def __init__(self, logs: list, server_name: str, lines_per_page: int, filter: str, level: str, user_id: int):
        super().__init__(timeout=None)
        self.logs = logs
        self.server_name = server_name
        self.lines_per_page = lines_per_page
        self.filter = filter
        self.level = level
        self.user_id = user_id
        self.current_page = 0
        self.total_pages = max(1, (len(logs) + lines_per_page - 1) // lines_per_page)

        # Create buttons
        self.prev_button = discord.ui.Button(label="◀️ Previous", style=discord.ButtonStyle.secondary, row=0)
        self.prev_button.callback = self.prev_page

        self.next_button = discord.ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, row=0)
        self.next_button.callback = self.next_page

        self.add_item(self.prev_button)
        self.add_item(self.next_button)

        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1

    def get_current_page(self) -> str:
        start = self.current_page * self.lines_per_page
        end = min(start + self.lines_per_page, len(self.logs))
        return "\n".join(self.logs[start:end])

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Not your command.", ephemeral=True)
            return
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await self.update_message(interaction)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Not your command.", ephemeral=True)
            return
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self.update_buttons()
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"📋 Server Logs - {self.server_name} (Page {self.current_page + 1}/{self.total_pages})",
            description="```\n" + self.get_current_page() + "\n```",
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"Lines {self.current_page * self.lines_per_page + 1}-{min((self.current_page + 1) * self.lines_per_page, len(self.logs))} of {len(self.logs)}")

        if self.filter or self.level:
            filters = []
            if self.filter:
                filters.append(f"Filter: `{self.filter}`")
            if self.level:
                filters.append(f"Level: `{self.level}`")
            embed.add_field(name="🔍 Filters", value="\n".join(filters), inline=False)

        await interaction.response.edit_message(embed=embed, view=self)


async def setup(bot):
    """Setup function for Discord.py cog loading."""
    await bot.add_cog(LogViewer(bot))


class LogViewer(commands.Cog):
    """Advanced ARK server log viewing and management."""

    def __init__(self, bot):
        self.bot = bot
        self.agent_manager = None  # Will be set by RemoteAgent cog

    async def cog_load(self):
        """Initialize log viewer when cog loads."""
        logger.info("Log Viewer cog loaded")

    def get_agent_manager(self):
        """Get agent manager from bot."""
        return getattr(self.bot, 'agent_manager', None)

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

    async def get_server_choices(self, interaction: discord.Interaction) -> List[app_commands.Choice[str]]:
        """Get list of servers for autocomplete."""
        servers = await self.get_servers_for_guild(interaction.guild_id)
        return [
            app_commands.Choice(name=server.get("name", "Unknown"), value=server.get("name", "")) for server in servers
        ]

    # ==================== LOG VIEWING ====================

    @app_commands.command(name="serverlogs", description="📋 View server logs (paginated)")
    @app_commands.describe(
        server_name="Server name",
        lines_per_page="Lines per page (max 30)",
        filter="Filter logs by keyword (optional)",
        level="Log level filter (ERROR, WARN, INFO, DEBUG)"
    )
    async def server_logs(
        self,
        interaction: discord.Interaction,
        server_name: str,
        lines_per_page: Optional[int] = 20,
        filter: Optional[str] = None,
        level: Optional[str] = None
    ):
        """View server logs with pagination."""
        if not await check_feature(interaction, "log_viewer"):
            return
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need admin permissions to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        servers = await self.get_servers_for_guild(interaction.guild_id)
        server = next((s for s in servers if s.get("name", "").lower() == server_name.lower()), None)

        if not server:
            await interaction.followup.send(f"❌ Server '{server_name}' not found.", ephemeral=True)
            return

        # Limit lines per page
        lines_per_page = min(max(lines_per_page, 5), 30)

        try:
            agent_manager = self.get_agent_manager()
            # Fetch more lines for pagination (500 max)
            fetch_lines = 500
            if agent_manager:
                logs = await self._get_remote_logs(agent_manager, server, fetch_lines, filter, level)
            else:
                logs = await self._get_local_logs(server, fetch_lines, filter, level)

            if not logs:
                await interaction.followup.send(
                    f"📋 Server Logs - {server_name}\n\n*No logs found or log file is empty*",
                    ephemeral=True
                )
                return

            # Store logs in a global dict for pagination
            # Use interaction token as key for ephemeral view state
            view = LogViewerView(logs, server_name, lines_per_page, filter, level, interaction.user.id)
            page = view.get_current_page()

            embed = discord.Embed(
                title=f"📋 Server Logs - {server_name}",
                description=page,
                color=discord.Color.blue(),
            )

            # Add pagination info
            total_pages = len(logs) // lines_per_page + (1 if len(logs) % lines_per_page > 0 else 0)
            embed.set_footer(text=f"Page 1/{total_pages} ({len(logs)} total lines) • {interaction.user.display_name}")

            if filter or level:
                filter_text = []
                if filter:
                    filter_text.append(f"Keyword: `{filter}`")
                if level:
                    filter_text.append(f"Level: `{level}`")
                embed.add_field(name="🔍 Filters", value="\n".join(filter_text), inline=False)

            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error reading server logs for {server_name}: {e}")
            await interaction.followup.send(f"❌ Failed to read server logs: {str(e)}", ephemeral=True)

    async def _get_remote_logs(self, agent_manager, server: dict, lines: int, filter: Optional[str], level: Optional[str]) -> List[str]:
        """Get logs from remote server via agent."""
        try:
            # Find agent that manages this server
            agent_id = await self._find_agent_for_server(agent_manager, server.get("name"))
            if not agent_id:
                logger.warning(f"No agent found for server: {server.get('name')}")
                return []

            # Request logs from agent
            command = "view_logs"
            params = {
                "lines": lines,
                "filter": filter,
                "level": level
            }

            result = await agent_manager.send_command(agent_id, command, server.get("name"), params, timeout=15)

            if result and result.get("data"):
                # Agent returns {"lines": [...], "log_path": "...", ...}
                data = result["data"]
                if isinstance(data, dict) and data.get("lines"):
                    return data["lines"]
                elif isinstance(data, list):
                    return data
            else:
                logger.warning(f"No log data received from agent for {server.get('name')}")
                return []

        except Exception as e:
            logger.error(f"Failed to get remote logs for {server.get('name')}: {e}")
            return []

    async def _get_local_logs(self, server: dict, lines: int, filter: Optional[str], level: Optional[str]) -> List[str]:
        """Get logs from local file system."""
        try:
            import os

            # Get log path from server config or construct default path like PowerShell bot
            log_path = server.get("log_path")
            if not log_path:
                # Construct log path from server_path like PowerShell bot does
                server_path = server.get("server_path")
                if server_path:
                    log_path = os.path.join(server_path, "ShooterGame", "Saved", "Logs", "ShooterGame.log")
                else:
                    logger.warning(f"No log path or server path configured for {server.get('name')}")
                    return []

            if not os.path.exists(log_path):
                logger.warning(f"Log file not found: {log_path}")
                return []

            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
                recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines

            # Apply filters
            filtered_lines = []
            for line in recent_lines:
                clean_line = line.strip()

                # Apply level filter
                if level:
                    level_pattern = f"[{level.upper()}]"
                    if level_pattern not in clean_line.upper():
                        continue

                # Apply keyword filter
                if filter and filter.lower() not in clean_line.lower():
                    continue

                # Clean up and format line
                if len(clean_line) > 100:
                    clean_line = clean_line[:97] + "..."
                filtered_lines.append(f"`{clean_line}`")

            return filtered_lines

        except Exception as e:
            logger.error(f"Failed to read local logs for {server.get('name')}: {e}")
            return []

    async def _find_agent_for_server(self, agent_manager, server_name: str) -> Optional[str]:
        """Find which agent manages a given server."""
        if not agent_manager:
            return None

        for agent_id, agent_info in agent_manager.agents.items():
            try:
                result = await agent_manager.send_command(agent_id, "discover_servers", "", timeout=5)
                if result and result.get("data"):
                    servers = result["data"]
                    for server in servers:
                        if server.get("name") == server_name:
                            return agent_id
            except:
                continue

        return None

    @app_commands.command(name="searchlogs", description="🔍 Search server logs for specific patterns")
    @app_commands.describe(
        server_name="Server name",
        query="Search query or regex pattern",
        max_results="Maximum results to return (max 50)",
        time_range="Time range: 1h, 6h, 24h, 7d"
    )
    async def search_logs(
        self,
        interaction: discord.Interaction,
        server_name: str,
        query: str,
        max_results: Optional[int] = 20,
        time_range: Optional[str] = "24h"
    ):
        """Search server logs for specific patterns."""
        if not await check_feature(interaction, "log_viewer"):
            return
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need admin permissions to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        servers = await self.get_servers_for_guild(interaction.guild_id)
        server = next((s for s in servers if s.get("name", "").lower() == server_name.lower()), None)

        if not server:
            await interaction.followup.send(f"❌ Server '{server_name}' not found.", ephemeral=True)
            return

        max_results = min(max(max_results, 5), 50)

        try:
            # Get more lines for searching (up to 1000)
            search_lines = min(1000, max_results * 20)

            agent_manager = self.get_agent_manager()
            if agent_manager:
                logs = await self._get_remote_logs(agent_manager, server, search_lines, None, None)
            else:
                logs = await self._get_local_logs(server, search_lines, None, None)

            if not logs:
                await interaction.followup.send("❌ No logs available to search.", ephemeral=True)
                return

            # Search for matches
            matches = []
            query_lower = query.lower()

            for i, line in enumerate(logs):
                line_text = line.strip("`").strip()
                if query_lower in line_text.lower():
                    matches.append(f"`{line_text}`")
                    if len(matches) >= max_results:
                        break

            if not matches:
                await interaction.followup.send(
                    f"🔍 Log Search - {server_name}\n\n*No matches found for '{query}'*",
                    ephemeral=True
                )
                return

            # Create embed with results
            embed = discord.Embed(
                title=f"🔍 Log Search Results - {server_name}",
                description=f"**Query:** `{query}`\n**Found:** {len(matches)} matches\n\n" + "\n".join(matches[:25]),
                color=discord.Color.gold(),
            )

            if len(matches) > 25:
                embed.set_footer(text=f"Showing first 25 of {len(matches)} matches")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error searching logs for {server_name}: {e}")
            await interaction.followup.send(f"❌ Failed to search logs: {str(e)}", ephemeral=True)

    @app_commands.command(name="logstats", description="📊 Get server log statistics")
    @app_commands.describe(
        server_name="Server name",
        time_range="Time range: 1h, 6h, 24h, 7d"
    )
    async def log_stats(
        self,
        interaction: discord.Interaction,
        server_name: str,
        time_range: Optional[str] = "24h"
    ):
        """Get server log statistics and analysis."""
        if not await check_feature(interaction, "log_viewer"):
            return
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need admin permissions to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        servers = await self.get_servers_for_guild(interaction.guild_id)
        server = next((s for s in servers if s.get("name", "").lower() == server_name.lower()), None)

        if not server:
            await interaction.followup.send(f"❌ Server '{server_name}' not found.", ephemeral=True)
            return

        try:
            # Get recent logs for analysis
            agent_manager = self.get_agent_manager()
            if agent_manager:
                logs = await self._get_remote_logs(agent_manager, server, 500, None, None)
            else:
                logs = await self._get_local_logs(server, 500, None, None)

            if not logs:
                await interaction.followup.send("❌ No logs available for analysis.", ephemeral=True)
                return

            # Analyze logs
            stats = self._analyze_logs(logs)

            # Create embed with statistics
            embed = discord.Embed(
                title=f"📊 Log Statistics - {server_name}",
                description=f"Analysis of last {len(logs)} log lines",
                color=discord.Color.purple(),
            )

            embed.add_field(name="📈 Total Lines", value=str(len(logs)), inline=True)
            embed.add_field(name="❌ Errors", value=str(stats.get("errors", 0)), inline=True)
            embed.add_field(name="⚠️ Warnings", value=str(stats.get("warnings", 0)), inline=True)
            embed.add_field(name="ℹ️ Info", value=str(stats.get("info", 0)), inline=True)
            embed.add_field(name="🔍 Debug", value=str(stats.get("debug", 0)), inline=True)

            # Add common patterns if found
            if stats.get("common_patterns"):
                patterns_text = "\n".join([f"• {pattern}: {count}" for pattern, count in stats["common_patterns"][:5]])
                embed.add_field(name="🔍 Common Patterns", value=patterns_text, inline=False)

            # Use Discord's automatic timestamp instead of strftime
            embed.timestamp = discord.utils.utcnow()
            embed.set_footer(text="Analysis completed")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error analyzing logs for {server_name}: {e}")
            await interaction.followup.send(f"❌ Failed to analyze logs: {str(e)}", ephemeral=True)

    def _analyze_logs(self, logs: List[str]) -> dict:
        """Analyze log lines and extract statistics."""
        stats = {
            "errors": 0,
            "warnings": 0,
            "info": 0,
            "debug": 0,
            "common_patterns": {}
        }

        for line in logs:
            line_text = line.strip("`").strip().upper()

            # Count log levels
            if "[ERROR]" in line_text:
                stats["errors"] += 1
            elif "[WARN]" in line_text or "[WARNING]" in line_text:
                stats["warnings"] += 1
            elif "[INFO]" in line_text:
                stats["info"] += 1
            elif "[DEBUG]" in line_text:
                stats["debug"] += 1

            # Look for common patterns
            common_patterns = ["PLAYER", "TRIBE", "DINO", "CHAT", "LOGIN", "LOGOUT", "KILLED", "DIED"]
            for pattern in common_patterns:
                if pattern in line_text:
                    stats["common_patterns"][pattern] = stats["common_patterns"].get(pattern, 0) + 1

        # Sort common patterns by frequency
        stats["common_patterns"] = dict(sorted(stats["common_patterns"].items(), key=lambda x: x[1], reverse=True))

        return stats

    # Autocomplete handlers
    @server_logs.autocomplete("server_name")
    @search_logs.autocomplete("server_name")
    @log_stats.autocomplete("server_name")
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

    @server_logs.autocomplete("level")
    async def level_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for log level selection."""
        levels = ["ERROR", "WARN", "INFO", "DEBUG"]
        choices = [app_commands.Choice(name=level, value=level) for level in levels]

        if current:
            choices = [choice for choice in choices if current.upper() in choice.name]

        return choices[:25]

    @search_logs.autocomplete("time_range")
    @log_stats.autocomplete("time_range")
    async def time_range_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for time range selection."""
        ranges = ["1h", "6h", "24h", "7d"]
        choices = [app_commands.Choice(name=range_name, value=range_name) for range_name in ranges]

        if current:
            choices = [choice for choice in choices if current.lower() in choice.name]

        return choices[:25]
