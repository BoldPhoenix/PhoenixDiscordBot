"""
[Self-Hosted] Crash monitoring and diagnostics cog.

Monitors ARK servers for crashes and collects diagnostic information:
- Detects when servers go offline
- Captures log snippets at crash time
- Tracks crash history and patterns
- Sends alerts to Discord
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from pathlib import Path
import re
import subprocess

from bot.rcon.client import RCONManager
from bot.utils.config import Config
from bot.utils.validation import validate_service_name
from bot.database import server_config_db

logger = logging.getLogger("CrashMonitorCog")

# Lines in logs to ignore from diagnostics (noisy third‑party tools/mods)
IGNORE_PATTERNS = [
    "Awesome ARK Tools",  # Third-party tool connection messages
    "[AATb]",  # Tag used by Awesome ARK Tools bot
    "AATB",  # Alternate casing/tag
    "connection to awesome ark tools bot",  # Disconnect lines
    "reason: (1006)",  # WebSocket closed code often from external bot
]


class CrashMonitor(commands.Cog):
    """[Self-Hosted] Monitor servers for crashes and collect diagnostics."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Multi-guild support: Per-guild state
        self.guild_rcon_managers: Dict[int, RCONManager] = {}  # guild_id -> RCONManager
        self.guild_server_states: Dict[int, Dict[str, dict]] = {}  # guild_id -> {server_name -> state}
        # How many consecutive failures before declaring a crash
        self.failure_threshold = 2
        # Start monitoring loop
        self.crash_monitor_loop.start()

    def cog_unload(self):
        """Clean up when cog is unloaded."""
        self.crash_monitor_loop.cancel()

    async def is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions."""
        # Server administrators always have access
        if interaction.user.guild_permissions.administrator:
            return True

        # Check database config for admin role
        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_role_id"):
            admin_role = interaction.guild.get_role(config["admin_role_id"])
            if admin_role and admin_role in interaction.user.roles:
                return True

        # Fallback to .env config
        if Config.ADMIN_ROLE_ID:
            admin_role = interaction.guild.get_role(Config.ADMIN_ROLE_ID)
            if admin_role and admin_role in interaction.user.roles:
                return True

        return False

    async def _get_server_list(self, guild_id: int) -> List[dict]:
        """Get server list from database for a specific guild."""
        all_servers = await server_config_db.get_ark_servers(guild_id)
        # Filter to only enabled servers
        servers = [s for s in all_servers if s.get("enabled", True)]
        return servers if servers else []

    async def _get_crash_alert_channel(self, guild_id: int) -> Optional[discord.TextChannel]:
        """Get the channel to send crash alerts to (uses status channel)."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            logger.warning(f"Guild {guild_id} not found")
            return None

        # Get status channel from config
        config = await server_config_db.get_server_config(guild_id)
        if not config:
            logger.debug(f"No config found for guild {guild_id}")
            return None
        
        channel_id = config.get("status_channel_id")
        if not channel_id:
            logger.warning(f"status_channel_id not configured for guild {guild_id}")
            return None

        channel = guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        
        logger.warning(f"Channel {channel_id} is not a text channel")
        return None

    def _read_log_tail(self, log_path: Path, lines: int = 100) -> str:
        """Read the last N lines of a log file."""
        try:
            if not log_path.exists():
                return f"Log file not found: {log_path}"

            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                return "".join(tail_lines)
        except Exception as e:
            return f"Error reading log: {e}"

    def _extract_crash_indicators(self, log_content: str) -> Dict[str, any]:
        """Extract crash-related information from log content."""
        indicators = {
            "errors": [],
            "warnings": [],
            "mod_issues": [],
            "network_issues": [],
            "memory_issues": [],
            "possible_cause": "Unknown",
        }

        lines = log_content.split("\n")

        for line in lines:
            # Skip noisy lines that match known ignore patterns
            if any(pat.lower() in line.lower() for pat in IGNORE_PATTERNS):
                continue
            line_lower = line.lower()

            # Check for errors
            if "error" in line_lower or "fatal" in line_lower or "exception" in line_lower:
                indicators["errors"].append(line.strip()[:200])  # Truncate long lines

            # Check for warnings
            elif "warning" in line_lower or "warn" in line_lower:
                indicators["warnings"].append(line.strip()[:200])

            # Check for mod issues
            if "mod" in line_lower and (
                "fail" in line_lower or "error" in line_lower or "missing" in line_lower
            ):
                indicators["mod_issues"].append(line.strip()[:200])

            # Check for network issues
            if any(
                term in line_lower
                for term in ["timeout", "connection", "network", "socket", "disconnect"]
            ):
                indicators["network_issues"].append(line.strip()[:200])

            # Check for memory issues
            if any(
                term in line_lower for term in ["out of memory", "memory allocation", "heap", "oom"]
            ):
                indicators["memory_issues"].append(line.strip()[:200])

        # Determine most likely cause
        if indicators["memory_issues"]:
            indicators["possible_cause"] = "Memory/RAM exhaustion"
        elif indicators["mod_issues"]:
            indicators["possible_cause"] = "Mod loading/compatibility issue"
        elif indicators["network_issues"]:
            indicators["possible_cause"] = "Network connectivity issue"
        elif indicators["errors"]:
            indicators["possible_cause"] = "Application error (see errors below)"

        # Limit arrays to last 10 entries each
        for key in ["errors", "warnings", "mod_issues", "network_issues", "memory_issues"]:
            indicators[key] = indicators[key][-10:]

        return indicators

    async def _record_crash_event(
        self, guild_id: int, server_name: str, rcon_port: int, log_snippet: str, indicators: dict
    ):
        """Record a crash event to the database."""
        try:
            await server_config_db.record_crash_event(
                guild_id=guild_id,
                server_name=server_name,
                rcon_port=rcon_port,
                crash_time=datetime.now(),
                log_snippet=log_snippet[-5000],  # Limit storage size
                possible_cause=indicators["possible_cause"],
                errors="\n".join(indicators["errors"][-5]),
            )
        except Exception as e:
            logger.error(f"Failed to record crash event for guild {guild_id}: {e}")

    async def _send_crash_alert(
        self, guild_id: int, server_name: str, server_config: dict, log_snippet: str, indicators: dict
    ):
        """Send a crash alert to Discord."""
        channel = await self._get_crash_alert_channel(guild_id)
        if not channel:
            logger.debug(f"No crash alert channel configured for guild {guild_id}")
            return

        embed = discord.Embed(
            title=f"🔴 Server Offline Detected: {server_name}",
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )

        embed.add_field(name="⚠️ Possible Cause", value=indicators["possible_cause"], inline=False)

        # Add error summary if present
        if indicators["errors"]:
            error_text = "\n".join(f"• {e[:100]}" for e in indicators["errors"][:3])
            embed.add_field(
                name="❌ Recent Errors", value=f"```{error_text[:1000]}```", inline=False
            )

        # Add mod issues if present
        if indicators["mod_issues"]:
            mod_text = "\n".join(f"• {m[:100]}" for m in indicators["mod_issues"][:3])
            embed.add_field(name="🧩 Mod Issues", value=f"```{mod_text[:1000]}```", inline=False)

        # Add network issues if present
        if indicators["network_issues"]:
            net_text = "\n".join(f"• {n[:100]}" for n in indicators["network_issues"][:3])
            embed.add_field(
                name="🌐 Network Issues", value=f"```{net_text[:1000]}```", inline=False
            )

        # Server info
        embed.add_field(
            name="📋 Server Details",
            value=f"**RCON Port:** {server_config.get('rcon_port')}\n**Service:** {server_config.get('service_name', 'N/A')}",
            inline=True,
        )

        # Recovery note
        if server_config.get("service_name"):
            embed.add_field(
                name="🔄 Auto-Recovery", value="Phoenix service wrapper will auto-restart this server", inline=True
            )

        embed.set_footer(text="Use /crashhistory to view crash patterns")

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send crash alert: {e}")

    @tasks.loop(seconds=30)
    async def crash_monitor_loop(self):
        """Monitor servers for crashes every 30 seconds - multi-guild aware."""
        if not self.bot.is_ready():
            return

        # Monitor servers for all guilds
        for guild in self.bot.guilds:
            guild_id = guild.id
            
            server_list = await self._get_server_list(guild_id)
            if not server_list:
                continue

            # Initialize RCON manager for this guild if needed
            if guild_id not in self.guild_rcon_managers:
                self.guild_rcon_managers[guild_id] = RCONManager(server_list)
            
            # Initialize server states for this guild if needed
            if guild_id not in self.guild_server_states:
                self.guild_server_states[guild_id] = {}
            
            server_states = self.guild_server_states[guild_id]
            rcon_manager = self.guild_rcon_managers[guild_id]

            for server_config in server_list:
                server_name = server_config["name"]
                rcon_port = server_config["rcon_port"]

                # Initialize state tracking if new server
                if server_name not in server_states:
                    server_states[server_name] = {
                        "online": None,  # Unknown initially
                        "last_change": datetime.now(),
                        "consecutive_failures": 0,
                    }

                state = server_states[server_name]

                # Prefer Windows service status over RCON for uptime
                service_name = server_config.get("service_name")
                service_running = None
                if service_name and validate_service_name(service_name):
                    try:
                        # Query Windows service state: returns RUNNING/STOPPED/etc
                        # Use 'sc query' to check Windows service state
                        result = subprocess.run(
                            ["sc", "query", service_name], capture_output=True, text=True, timeout=5
                        )
                        output = result.stdout.lower()
                        if "state" in output and "running" in output:
                            service_running = True
                        elif "state" in output:
                            service_running = False
                    except Exception as e:
                        logger.debug(f"Service status check failed for {service_name}: {e}")

                if service_running is True:
                    # Service says server is up. Do not mark offline based on RCON.
                    if state["online"] is False:
                        logger.info(f"Server {server_name} is back online (service RUNNING)")
                    state["online"] = True
                    state["consecutive_failures"] = 0
                    continue

                # Fallback: if no service_name configured, use lightweight RCON ping
                try:
                    client = rcon_manager.clients.get(server_name)
                    if client:
                        await client.get_player_list()
                        if state["online"] is False:
                            logger.info(f"Server {server_name} is back online (RCON)")
                        state["online"] = True
                        state["consecutive_failures"] = 0
                    else:
                        raise Exception("No RCON client")
                except Exception as e:
                    state["consecutive_failures"] += 1
                    logger.debug(
                        f"Server {server_name} unreachable (attempt {state['consecutive_failures']}): {e}"
                    )

                    # Only trigger crash detection after threshold failures
                    # and only if server was previously known to be online.
                    # If a service is configured and not RUNNING, treat as crash; otherwise be conservative.
                    if (
                        state["consecutive_failures"] >= self.failure_threshold
                        and state["online"] is True
                        and (service_name and service_running is False or not service_name)
                    ):
                        logger.warning(f"Server {server_name} appears to have crashed!")
                        state["online"] = False
                        state["last_change"] = datetime.now()

                        # Get server path and collect diagnostics
                        server_path = await server_config_db.get_server_path(
                            guild_id, rcon_port
                        )

                        log_snippet = ""
                        indicators = {
                            "possible_cause": "Unknown",
                            "errors": [],
                            "mod_issues": [],
                            "network_issues": [],
                            "memory_issues": [],
                            "warnings": [],
                        }

                        if server_path:
                            log_path = server_config_db.get_server_log_path(server_path)
                            if log_path:
                                log_snippet = self._read_log_tail(log_path, lines=150)
                                indicators = self._extract_crash_indicators(log_snippet)

                        # Only alert if we found actual crash indicators (ignore graceful shutdowns)
                        if indicators.get("possible_cause", "Unknown") != "Unknown":
                            # Record and alert
                            await self._record_crash_event(
                                guild_id, server_name, rcon_port, log_snippet, indicators
                            )
                            await self._send_crash_alert(
                                guild_id, server_name, server_config, log_snippet, indicators
                            )
                        else:
                            logger.info(
                                f"Server {server_name} went offline (graceful/unknown). No alert sent."
                            )

                    elif state["online"] is None:
                        # First check, server was already offline
                        if state["consecutive_failures"] >= self.failure_threshold:
                            state["online"] = False

    @crash_monitor_loop.before_loop
    async def before_crash_monitor(self):
        """Wait until bot is ready."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(10)  # Give other systems time to initialize

    # ==========================================================================
    # Commands
    # ==========================================================================

    @app_commands.command(
        name="crashhistory", description="[Self-Hosted] View recent crash history for servers"
    )
    @app_commands.describe(
        server_name="Optional: Filter by server name",
        days="Number of days to look back (default: 7)",
    )
    async def crash_history(
        self, interaction: discord.Interaction, server_name: Optional[str] = None, days: int = 7
    ):
        """View crash history for servers."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need admin permissions to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            crashes = await server_config_db.get_crash_history(
                guild_id=interaction.guild_id, server_name=server_name, days=days
            )

            if not crashes:
                await interaction.followup.send(
                    f"✅ No crashes recorded in the last {days} days"
                    + (f" for {server_name}" if server_name else ""),
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title="📊 Server Crash History",
                description=f"Last {days} days" + (f" • {server_name}" if server_name else ""),
                color=discord.Color.orange(),
            )

            # Group by server
            server_crashes: Dict[str, List[dict]] = {}
            for crash in crashes:
                name = crash["server_name"]
                if name not in server_crashes:
                    server_crashes[name] = []
                server_crashes[name].append(crash)

            for srv_name, srv_crashes in server_crashes.items():
                crash_times = [c["crash_time"] for c in srv_crashes]
                causes = [c["possible_cause"] for c in srv_crashes]

                # Most common cause
                cause_counts = {}
                for c in causes:
                    cause_counts[c] = cause_counts.get(c, 0) + 1
                top_cause = (
                    max(cause_counts.keys(), key=lambda x: cause_counts[x])
                    if cause_counts
                    else "Unknown"
                )

                value = f"**Crashes:** {len(srv_crashes)}\n"
                value += f"**Most Common Cause:** {top_cause}\n"
                # Use Discord timestamp format for automatic timezone conversion
                last_crash_ts = int(crash_times[0].timestamp())
                value += f"**Last Crash:** <t:{last_crash_ts}:f>"

                embed.add_field(name=f"🔴 {srv_name}", value=value, inline=True)

            embed.set_footer(text="Use /crashdetails <server> for more info")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error fetching crash history: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(
        name="crashdetails",
        description="[Self-Hosted] View details of the most recent crash for a server",
    )
    @app_commands.describe(server_name="Server name to check")
    async def crash_details(self, interaction: discord.Interaction, server_name: str):
        """View detailed crash information."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need admin permissions to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            crash = await server_config_db.get_latest_crash(
                guild_id=interaction.guild_id, server_name=server_name
            )

            if not crash:
                await interaction.followup.send(
                    f"✅ No crashes recorded for {server_name}", ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"🔍 Crash Details: {server_name}",
                color=discord.Color.red(),
                timestamp=crash["crash_time"],
            )

            embed.add_field(name="⚠️ Possible Cause", value=crash["possible_cause"], inline=False)

            if crash.get("errors"):
                embed.add_field(
                    name="❌ Errors", value=f"```{crash['errors'][:1000]}```", inline=False
                )

            if crash.get("log_snippet"):
                # Show last portion of log
                snippet = crash["log_snippet"][-1500:]
                embed.add_field(name="📜 Log Snippet (end)", value=f"```{snippet}```", inline=False)

            embed.set_footer(text=f"Crash occurred at")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error fetching crash details: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(
        name="crashstatus",
        description="[Self-Hosted] Check current crash monitor status of all servers",
    )
    async def server_status_check(self, interaction: discord.Interaction):
        """Show current server status with diagnostics."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need admin permissions to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title="🖥️ Server Status Overview", color=discord.Color.blue(), timestamp=datetime.now()
        )

        online_count = 0
        offline_count = 0

        guild_id = interaction.guild_id
        server_states = self.guild_server_states.get(guild_id, {})

        for server_name, state in server_states.items():
            if state["online"]:
                online_count += 1
                status = "🟢 Online"
            elif state["online"] is False:
                offline_count += 1
                # Use Discord timestamp format for automatic timezone conversion
                offline_ts = int(state['last_change'].timestamp())
                status = f"🔴 Offline (since <t:{offline_ts}:t>)"
            else:
                status = "⚪ Unknown"

            embed.add_field(name=server_name, value=status, inline=True)

        embed.description = f"**Online:** {online_count} | **Offline:** {offline_count}"
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="checklog", description="[Self-Hosted] View the tail of a server's log file"
    )
    @app_commands.describe(
        server_name="Server to check logs for",
        lines="Number of lines to show (default: 50, max: 200)",
    )
    async def check_log(self, interaction: discord.Interaction, server_name: str, lines: int = 50):
        """View recent log entries for a server."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need admin permissions to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Limit lines
        lines = min(max(lines, 10), 200)

        try:
            # Find server
            server_list = await self._get_server_list(interaction.guild_id)
            server_config = next(
                (s for s in server_list if s["name"].lower() == server_name.lower()), None
            )

            if not server_config:
                await interaction.followup.send(
                    f"❌ Server '{server_name}' not found", ephemeral=True
                )
                return

            # Get server path
            server_path = await server_config_db.get_server_path(
                interaction.guild_id, server_config["rcon_port"]
            )

            if not server_path:
                await interaction.followup.send(
                    f"❌ No server path configured for {server_name}.\n"
                    f"Use `/editserver` to set the `server_path` for this server.",
                    ephemeral=True,
                )
                return

            log_path = server_config_db.get_server_log_path(server_path)
            if not log_path:
                await interaction.followup.send(
                    f"❌ Log file not found at expected location:\n"
                    f"`{server_path}\\ShooterGame\\Saved\\Logs\\ShooterGame.log`",
                    ephemeral=True,
                )
                return

            log_content = self._read_log_tail(log_path, lines)

            # Split into chunks for Discord (max 2000 chars per message)
            chunks = [log_content[i : i + 1900] for i in range(0, len(log_content), 1900)]

            await interaction.followup.send(
                f"📜 **Log tail for {server_name}** (last {lines} lines):", ephemeral=True
            )

            for i, chunk in enumerate(chunks[:5]):  # Max 5 chunks
                await interaction.followup.send(f"```\n{chunk}\n```", ephemeral=True)

        except Exception as e:
            logger.error(f"Error reading log: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @check_log.autocomplete("server_name")
    @crash_details.autocomplete("server_name")
    @crash_history.autocomplete("server_name")
    async def server_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for server names."""
        server_list = await self._get_server_list(interaction.guild_id)
        choices = [
            app_commands.Choice(name=s["name"], value=s["name"])
            for s in server_list
            if current.lower() in s["name"].lower()
        ]
        return choices[:25]


async def setup(bot: commands.Bot):
    """Add the cog to the bot."""
    await bot.add_cog(CrashMonitor(bot))
