"""
Interactive Server Management GUI
Provides admins with buttons, dropdowns, and modals for easy ARK server management.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button, Modal, TextInput
from typing import Optional, List
import asyncio
import subprocess

from pathlib import Path

from bot.rcon.client import RCONManager
from bot.utils.config import Config
from bot.utils.validation import validate_service_name
from bot.database import server_config_db
from bot.database.server_config_db import (
    get_ark_servers,
    get_server_motd,
    set_server_motd,
    get_server_path,
    get_server_log_path,
    get_hosting_type,
    is_self_hosted,
)
from bot.database.players_db import get_all_linked_players, get_player_by_discord_id
from bot.database.store_db import get_all_items
from bot.utils.arkids_api import get_arkids_client
from bot.utils.admin_logger import AdminLogger
from bot.database import admin_logs_db


class ServerManagementView(View):
    """Main interactive server management interface."""

    def __init__(self, guild_id: int, user: discord.User, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.user = user
        self.selected_server = None
        self.servers = []
        self.is_self_hosted = True  # Default, will be updated

        # Load servers and hosting type
        asyncio.create_task(self._load_servers())

    async def _load_servers(self):
        """Load available servers for this guild."""
        try:
            servers = await get_ark_servers(self.guild_id)
            if not servers:
                servers = Config.ARK_SERVERS
            self.servers = servers
            # Check hosting type
            self.is_self_hosted = await is_self_hosted(self.guild_id)
        except Exception:
            self.servers = Config.ARK_SERVERS
            self.is_self_hosted = True  # Default to self-hosted

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This server management panel is not for you!", ephemeral=True
            )
            return False
        return True

    def create_main_embed(self) -> discord.Embed:
        """Create the main server management embed."""
        hosting_mode = "🏠 Self-Hosted" if self.is_self_hosted else "☁️ Nitrado"

        embed = discord.Embed(
            title="🎮 ARK Server Management Panel",
            description=(
                f"Welcome to the interactive server management system!\n"
                f"**Mode:** {hosting_mode}\n\n"
                "**Quick Guide:**\n"
                "1️⃣ Select a server from the dropdown below\n"
                "2️⃣ Choose an action category\n"
                "3️⃣ Fill out the simple form\n"
                "4️⃣ Confirm and execute!\n\n"
                f"**Currently Selected:** {self.selected_server['name'] if self.selected_server else 'None'}"
            ),
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="👥 Player Management",
            value="Kick, ban, whitelist, give XP, or view online players",
            inline=True,
        )

        embed.add_field(
            name="🖥️ Server Operations", value="Broadcast, save world, restart, MOTD", inline=True
        )

        if self.is_self_hosted:
            embed.add_field(
                name="⚙️ Server Control",
                value="Start, stop, restart server\n*NSSM Service Control*",
                inline=True,
            )

        embed.add_field(name="🔧 Advanced", value="Custom RCON, view chat", inline=True)

        if self.is_self_hosted:
            embed.add_field(
                name="🔍 Diagnostics",
                value="View logs, crash history\n*Local Server Logs*",
                inline=True,
            )

        embed.set_footer(text="💡 All actions are logged | ⚠️ Admin permissions required")
        return embed


# NSSM path for querying service parameters
NSSM_PATH = r"C:\nssm\win64\nssm.exe"

# Cache for map names to avoid repeated NSSM queries
_map_name_cache: dict = {}


def get_map_name_from_service(service_name: str) -> str:
    """Get the map name by querying the NSSM service's AppParameters."""
    if not service_name:
        return "Unknown Map"

    # Check cache first
    if service_name in _map_name_cache:
        return _map_name_cache[service_name]

    try:
        # Query NSSM for the AppParameters
        result = subprocess.run(
            [NSSM_PATH, "get", service_name, "AppParameters"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0 and result.stdout.strip():
            # AppParameters format: "MapName_WP?listen?SessionName=..."
            # Extract the map name (everything before _WP or _P)
            params = result.stdout.strip()

            # The map name is at the start, before "?" or "_WP" or "_P"
            if "_WP?" in params:
                map_name = params.split("_WP?")[0]
            elif "_P?" in params:
                map_name = params.split("_P?")[0]
            elif "?" in params:
                map_name = params.split("?")[0]
            else:
                map_name = params

            # Clean up common suffixes and format nicely
            map_name = map_name.replace("_WP", "").replace("_P", "")

            # Cache the result
            _map_name_cache[service_name] = map_name
            return map_name
    except Exception:
        pass

    # Fallback: try to derive from service name (e.g., asa_amissa -> Amissa)
    if service_name.startswith("asa_"):
        fallback = service_name[4:].title()
        _map_name_cache[service_name] = fallback
        return fallback

    return "Unknown Map"


def get_map_name(server: dict) -> str:
    """Get the map name for a server - tries service query first, then fallback."""
    service_name = server.get("service_name")
    if service_name:
        return get_map_name_from_service(service_name)

    # Fallback to server name if no service_name
    return server.get("name", "Unknown Map")


class UpdateAllServersButton(Button):
    """Button to update all servers via SteamCMD."""

    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Update All Servers",
            emoji="📥",
            custom_id="update_all_servers",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(UpdateAllServersModal())


class UpdateAllServersConfirmView(View):
    """Confirmation view for updating all servers."""

    def __init__(self, servers: list, do_validate: bool, user: discord.User):
        super().__init__(timeout=300)
        self.servers = servers
        self.do_validate = do_validate
        self.user = user
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This confirmation is not for you!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm Update", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm the update."""
        self.confirmed = True
        await interaction.response.defer()
        # Run update process as background task to avoid blocking the bot
        asyncio.create_task(start_update_process(interaction, self.servers, self.do_validate))
        
        # Acknowledge immediately
        embed = discord.Embed(
            title="🚀 Server Update Started",
            description=f"Updating {len(self.servers)} server(s) in the background.\n\nThe bot will remain responsive to other commands.",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Mode", value="🔍 Full Validation" if self.do_validate else "⚡ Quick Update", inline=True)
        embed.add_field(name="Servers", value=", ".join([s["name"] for s in self.servers]), inline=False)
        embed.set_footer(text="Updates will continue even if you close this message")
        await interaction.edit_original_response(embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the update."""
        embed = discord.Embed(
            title="❌ Update Cancelled",
            description="Server update has been cancelled.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


async def start_update_process(interaction: discord.Interaction, servers: list, do_validate: bool):
    """Start the server update process."""
    import subprocess
    import asyncio
    from bot.rcon.client import RCONManager

    server_count = len(servers)
    nssm_path = r"C:\nssm\win64\nssm.exe"

    results = []
    completed = 0
    
    # Resolve admin log channel from database (per guild), not from .env
    import logging
    logger = logging.getLogger(__name__)
    admin_log_channel = None
    try:
        config = await server_config_db.get_server_config(interaction.guild_id)
        log_channel_id = config.get("admin_log_channel_id") if config else None

        if log_channel_id:
            admin_log_channel = interaction.client.get_channel(log_channel_id)
            if admin_log_channel:
                logger.info(f"Posting update queue start to admin log channel {log_channel_id}")
                queue_start_embed = discord.Embed(
                    title="📥 Server Update Queue Started",
                    description=f"Updating {server_count} server(s) sequentially",
                    color=discord.Color.blue(),
                )
                queue_start_embed.add_field(name="Mode", value="🔍 Full Validation" if do_validate else "⚡ Quick Update", inline=True)
                queue_start_embed.add_field(name="Servers", value=", ".join([s["name"] for s in servers]), inline=False)
                queue_start_embed.set_footer(text=f"Initiated by {interaction.user.display_name}")
                await admin_log_channel.send(embed=queue_start_embed)
                logger.info("Posted queue start message to admin log channel")
            else:
                logger.warning(f"Admin log channel {log_channel_id} not accessible")
        else:
            logger.warning("Admin log channel not configured in database (admin_log_channel_id is NULL)")
    except Exception as e:
        logger.error(f"Failed to resolve admin log channel: {type(e).__name__}: {str(e)}")

    # Announce update start to chat channel
    try:
        from bot.utils.config import Config
        chat_channel_id = Config.CHAT_CHANNEL_ID
        if chat_channel_id:
            chat_channel = interaction.client.get_channel(chat_channel_id)
            if chat_channel:
                start_embed = discord.Embed(
                    title="🔔 Server Update Started",
                    description=f"Admin {interaction.user.mention} is starting server updates",
                    color=discord.Color.gold(),
                )
                start_embed.add_field(
                    name="Servers",
                    value=", ".join([s["name"] for s in servers]),
                    inline=False,
                )
                start_embed.add_field(
                    name="Mode",
                    value="🔍 Full Validation" if do_validate else "⚡ Quick Update",
                    inline=True,
                )
                await chat_channel.send(embed=start_embed)
    except Exception:
        pass  # Silently fail if chat channel broadcast doesn't work

    for idx, server in enumerate(servers, 1):
        service_name = server.get("service_name")
        if not service_name:
            results.append(f"⏭️ {server['name']}: Skipped (no service_name)")
            completed += 1
            continue
        if not validate_service_name(service_name):
            results.append(f"❌ {server['name']}: Invalid service name format")
            completed += 1
            continue

        try:
            # Log update start to admin channel (if configured)
            try:
                if admin_log_channel:
                    logger.info(f"Sending update start message to admin log channel for {server['name']}")
                    start_embed = discord.Embed(
                        title=f"🔄 Starting Update: {server['name']}",
                        description=f"Server {idx}/{server_count}",
                        color=discord.Color.blue(),
                    )
                    start_embed.add_field(name="Mode", value="🔍 Validation" if do_validate else "⚡ Quick", inline=True)
                    start_embed.set_footer(text=f"By {interaction.user.display_name}")
                    msg = await admin_log_channel.send(embed=start_embed)
                    logger.info(f"Successfully sent message {msg.id} to admin log channel")
                else:
                    logger.debug("Admin log channel not available; skipping admin log send")
            except Exception as e:
                logger.error(f"Failed to send to admin log channel: {type(e).__name__}: {str(e)}")
            
            # Check if server is running via RCON (source of truth for online status)
            logger.info(f"Checking if {server['name']} is online via RCON...")
            server_monitor = interaction.client.get_cog("ServerMonitor")
            is_running = False
            
            if server_monitor and server_monitor.rcon_manager:
                try:
                    # Check RCON connectivity - this is the real indicator of server being online
                    rcon_client = server_monitor.rcon_manager.clients.get(server["name"])
                    if rcon_client:
                        # Try a simple command to verify connectivity
                        response = await server_monitor.rcon_manager.execute_command(server["name"], "ListPlayers")
                        is_running = response is not None
                        logger.info(f"RCON check: {server['name']} is {'online' if is_running else 'offline'}")
                    else:
                        logger.info(f"No RCON client found for {server['name']}, assuming offline")
                except Exception as e:
                    logger.info(f"RCON check failed for {server['name']}: {e}, assuming offline")
                    is_running = False
            else:
                logger.warning(f"No ServerMonitor cog available, cannot check RCON status for {server['name']}")
            
            logger.info(f"Determined is_running={is_running} for {server['name']}")
            
            if is_running:
                # Server is running - send countdown broadcasts
                progress_text = f"Server {idx}/{server_count}: **{server['name']}**\n\n"
                progress_text += "📋 Steps:\n"
                progress_text += "1. Sending countdown broadcasts...\n"

                embed = discord.Embed(
                    title="📥 Server Update In Progress",
                    description=f"Updating {server_count} server(s) sequentially",
                    color=discord.Color.blue(),
                )
                embed.add_field(name="Progress", value=progress_text, inline=False)
                if results:
                    embed.add_field(name="Completed", value="\n".join(results[-5:]), inline=False)
                embed.add_field(name="⚠️ Note", value="Close this message to cancel remaining updates", inline=False)
                embed.set_footer(text=f"Working on: {server['name']}")

                await interaction.edit_original_response(embed=embed)
                
                # Log countdown start to admin channel
                try:
                    if admin_log_channel:
                        countdown_embed = discord.Embed(
                            title=f"📢 Countdown Started: {server['name']}",
                            description="Broadcasting shutdown warnings to players",
                            color=discord.Color.orange(),
                        )
                        await admin_log_channel.send(embed=countdown_embed)
                except Exception:
                    pass

                # Send countdown warnings via RCON
                try:
                    # Accurate countdown sequence: 10, 8, 6, 5, 3, 1 min, 30s, 10-1s
                    warnings = [
                        (600, "🔄 Server rebooting for updates in 10 MINUTES"),
                        (480, "🔄 Server rebooting for updates in 8 MINUTES"),
                        (360, "🔄 Server rebooting for updates in 6 MINUTES"),
                        (300, "🔄 Server rebooting for updates in 5 MINUTES"),
                        (180, "🔄 Server rebooting for updates in 3 MINUTES"),
                        (60, "🔄 Server rebooting for updates in 1 MINUTE"),
                        (30, "🔄 Server rebooting for updates in 30 SECONDS"),
                    ]

                    server_monitor = interaction.client.get_cog("ServerMonitor")
                    if not server_monitor or not server_monitor.rcon_manager:
                        logger.warning(f"No RCON manager available for {server['name']}, skipping countdown")
                    else:
                        rcon_manager = server_monitor.rcon_manager
                        logger.info(f"Using existing RCON manager for {server['name']} countdown broadcasts")

                        for wait_seconds, message in warnings:
                            try:
                                await rcon_manager.execute_command(server["name"], f"ServerChat {message}")
                                logger.info(f"Sent countdown: {message}")
                            except Exception as e:
                                logger.error(f"Failed to send countdown message: {e}")
                            await asyncio.sleep(wait_seconds)

                        # Final 10-second countdown
                        for i in range(10, 0, -1):
                            try:
                                await rcon_manager.execute_command(
                                    server["name"], f"ServerChat 🔄 Server going down in {i} SECONDS..."
                                )
                            except Exception as e:
                                logger.error(f"Failed to send {i}s countdown: {e}")
                            await asyncio.sleep(1)

                        # Send shutdown
                        try:
                            await rcon_manager.execute_command(server["name"], "DoExit")
                            logger.info(f"Sent DoExit command to {server['name']}")
                            await asyncio.sleep(15)
                        except Exception as e:
                            logger.error(f"Failed to send DoExit: {e}")

                except Exception as e:
                    logger.error(f"Countdown broadcast error: {e}", exc_info=True)

                # Update progress - stopping
                progress_text = f"Server {idx}/{server_count}: **{server['name']}**\n\n"
                progress_text += "📋 Steps:\n"
                progress_text += "1. ✅ Countdown broadcasts sent\n"
                progress_text += "2. Stopping server...\n"

                embed = discord.Embed(
                    title="📥 Server Update In Progress",
                    color=discord.Color.blue(),
                )
                embed.add_field(name="Progress", value=progress_text, inline=False)
                if results:
                    embed.add_field(name="Completed", value="\n".join(results[-5:]), inline=False)
                embed.add_field(name="⚠️ Note", value="Close this message to cancel remaining updates", inline=False)
                embed.set_footer(text=f"Working on: {server['name']}")

                await interaction.edit_original_response(embed=embed)

                # NSSM stop
                subprocess.run(
                    [nssm_path, "stop", service_name], capture_output=True, text=True, timeout=30
                )
                await asyncio.sleep(3)
            else:
                # Server appears stopped - still attempt countdown broadcasts for any players that might be online
                progress_text = f"Server {idx}/{server_count}: **{server['name']}**\n\n"
                progress_text += "📋 Steps:\n"
                progress_text += "1. Attempting countdown broadcasts (server appears offline)...\n"

                embed = discord.Embed(
                    title="📥 Server Update In Progress",
                    description=f"Updating {server_count} server(s) sequentially",
                    color=discord.Color.blue(),
                )
                embed.add_field(name="Progress", value=progress_text, inline=False)
                if results:
                    embed.add_field(name="Completed", value="\n".join(results[-5:]), inline=False)
                embed.add_field(name="⚠️ Note", value="Close this message to cancel remaining updates", inline=False)
                embed.set_footer(text=f"Working on: {server['name']}")

                await interaction.edit_original_response(embed=embed)
                
                # Log countdown attempt to admin channel
                try:
                    if admin_log_channel:
                        attempt_embed = discord.Embed(
                            title=f"📢 Attempting Countdown: {server['name']}",
                            description="Server appears offline but attempting countdown broadcasts for any online players",
                            color=discord.Color.orange(),
                        )
                        await admin_log_channel.send(embed=attempt_embed)
                except Exception:
                    pass

                # Still attempt countdown broadcasts even if server appears offline
                try:
                    # Accurate countdown sequence: 10, 8, 6, 5, 3, 1 min, 30s, 10-1s
                    warnings = [
                        (600, "🔄 Server rebooting for updates in 10 MINUTES"),
                        (480, "🔄 Server rebooting for updates in 8 MINUTES"),
                        (360, "🔄 Server rebooting for updates in 6 MINUTES"),
                        (300, "🔄 Server rebooting for updates in 5 MINUTES"),
                        (180, "🔄 Server rebooting for updates in 3 MINUTES"),
                        (60, "🔄 Server rebooting for updates in 1 MINUTE"),
                        (30, "🔄 Server rebooting for updates in 30 SECONDS"),
                    ]

                    server_monitor = interaction.client.get_cog("ServerMonitor")
                    if not server_monitor or not server_monitor.rcon_manager:
                        logger.warning(f"No RCON manager available for {server['name']}, skipping countdown")
                    else:
                        rcon_manager = server_monitor.rcon_manager
                        logger.info(f"Using existing RCON manager for {server['name']} countdown broadcasts (server appeared offline)")

                        for wait_seconds, message in warnings:
                            try:
                                await rcon_manager.execute_command(server["name"], f"ServerChat {message}")
                                logger.info(f"Sent countdown (attempt): {message}")
                            except Exception as e:
                                logger.info(f"Failed to send countdown message (server may be offline): {e}")
                            await asyncio.sleep(wait_seconds)

                        # Final 10-second countdown
                        for i in range(10, 0, -1):
                            try:
                                await rcon_manager.execute_command(
                                    server["name"], f"ServerChat 🔄 Server going down in {i} SECONDS..."
                                )
                            except Exception as e:
                                logger.info(f"Failed to send {i}s countdown (server may be offline): {e}")
                            await asyncio.sleep(1)

                        # Send shutdown
                        try:
                            await rcon_manager.execute_command(server["name"], "DoExit")
                            logger.info(f"Sent DoExit command to {server['name']} (attempt)")
                            await asyncio.sleep(15)
                        except Exception as e:
                            logger.info(f"Failed to send DoExit (server may be offline): {e}")

                except Exception as e:
                    logger.error(f"Countdown broadcast error: {e}", exc_info=True)
                
                await asyncio.sleep(1)

            # Update progress - updating
            progress_text = f"Server {idx}/{server_count}: **{server['name']}**\n\n"
            progress_text += "📋 Steps:\n"
            if is_running:
                progress_text += "1. ✅ Countdown broadcasts sent\n"
                progress_text += "2. ✅ Server stopped\n"
                progress_text += f"{'3'}. 🔄 Running SteamCMD update (this may take 10-30 minutes)...\n"
            else:
                progress_text += "1. ✅ Countdown broadcasts attempted (server appeared offline)\n"
                progress_text += f"{'2'}. 🔄 Running SteamCMD update (this may take 10-30 minutes)...\n"

            embed = discord.Embed(
                title="📥 Server Update In Progress",
                color=discord.Color.blue(),
            )
            embed.add_field(name="Progress", value=progress_text, inline=False)
            if results:
                embed.add_field(name="Completed", value="\n".join(results[-5:]), inline=False)
            embed.add_field(name="⚠️ Note", value="Close this message to cancel remaining updates", inline=False)
            embed.set_footer(text=f"Updating: {server['name']} (may take a while...)")

            await interaction.edit_original_response(embed=embed)
            
            # Log SteamCMD start to admin channel
            try:
                if admin_log_channel:
                    steamcmd_embed = discord.Embed(
                        title=f"🔄 Running SteamCMD: {server['name']}",
                        description="Downloading/validating game files (may take 10-30 minutes)",
                        color=discord.Color.blue(),
                    )
                    await admin_log_channel.send(embed=steamcmd_embed)
            except Exception:
                pass

            # Get server_path and steamcmd_directory from database
            server_install_path = server.get("server_path")
            steamcmd_directory = server.get("steamcmd_path")  # This field stores the steam directory (not the exe)
            
            # For the agent, we send the steam directory, not the full path to steamcmd.exe
            # The Windows agent will handle steamcmd.exe construction
            server_steamcmd_path = steamcmd_directory  # Send directory only
            
            logger.info(f"DEBUG: Bot sending paths for {server['name']}:")
            logger.info(f"  server_path: {server_install_path}")
            logger.info(f"  steamcmd_path: {server_steamcmd_path}")
            logger.info(f"  steamcmd_directory: {steamcmd_directory}")
            logger.info(f"  Full params being sent: {{")
            logger.info(f"    steamcmd_path: {server_steamcmd_path},")
            logger.info(f"    server_path: {server_install_path},")
            logger.info(f"    use_custom_script: True,")
            logger.info(f"    validate: {do_validate}")
            logger.info(f"  }}")
            
            if not server_install_path:
                results.append(f"❌ {server['name']}: No server_path configured (use /editserver to set)")
                completed += 1
                
                # Only restart if server was running before
                if is_running:
                    try:
                        subprocess.run(
                            [nssm_path, "start", service_name],
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                    except Exception:
                        pass
                continue
            
            if not server_steamcmd_path:
                results.append(f"❌ {server['name']}: No steamcmd_path configured (run configure_server_paths.py)")
                completed += 1
                
                # Only restart if server was running before
                if is_running:
                    try:
                        subprocess.run(
                            [nssm_path, "start", service_name],
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                    except Exception:
                        pass
                continue

            # Check if server has remote agent configured
            agent_id = server.get("agent_id")
            if not agent_id:
                results.append(f"❌ {server['name']}: No remote agent configured")
                completed += 1
                continue

            # Get agent manager from bot
            agent_manager = interaction.client.agent_manager
            
            # Send update command to remote agent
            try:
                logger.info(f"Sending update_server to agent {agent_id} for {server['name']}")
                update_result = await agent_manager.send_command(
                    agent_id,
                    "update_server",
                    server["name"],
                    params={
                        "steamcmd_path": server_steamcmd_path,
                        "server_path": server_install_path,
                        "ark_appid": server.get("ark_appid", 2430930),
                        "use_custom_script": True,
                        "validate": do_validate,
                    },
                    timeout=1800,
                )

                if update_result and update_result.get("type") == "complete":
                    results.append(f"✅ {server['name']}: Updated via remote agent")
                    completed += 1
                else:
                    error = update_result.get("error", "Unknown error") if update_result else "No response from agent"
                    results.append(f"❌ {server['name']}: {error}")
                    completed += 1
            except Exception as e:
                results.append(f"❌ {server['name']}: Failed to send update command - {str(e)}")
                completed += 1

            # Only restart if server was running before and update succeeded
            if is_running and results[-1].startswith("✅"):
                try:
                    # Restart server via agent
                    await agent_manager.send_command(
                        agent_id, "start_server", server["name"], timeout=60
                    )
                    results[-1] = f"✅ {server['name']}: Updated & restarted via remote agent"
                except Exception as e:
                    results[-1] = f"⚠️ {server['name']}: Updated but failed to restart - {str(e)}"

        except Exception as e:
            results.append(f"❌ {server['name']}: {str(e)}")
            completed += 1

    # Send final results
    final_embed = discord.Embed(
        title="📥 Server Update Queue Complete",
        description=f"✅ {completed}/{server_count} servers processed",
        color=discord.Color.green(),
    )
    final_embed.add_field(name="Results", value="\n".join(results), inline=False)
    final_embed.add_field(
        name="Next Steps", value="Monitor server status with `/servers status`", inline=False
    )
    final_embed.set_footer(text=f"Completed for {interaction.user.display_name}")

    await interaction.edit_original_response(embed=final_embed)

    # Log to admin log channel
    try:
        cog = interaction.client.get_cog("ServerManagementGUI")
        if cog and cog.admin_logger:
            admin_logger = cog.admin_logger
            status = "success" if completed == server_count else "partial"
            log_id = await admin_logger.log_action(
                interaction=interaction,
                action_type="update_all_servers",
                servers_affected=[s["name"] for s in servers],
                details={
                    "mode": "Full Validation" if do_validate else "Quick Update",
                    "server_count": server_count,
                    "validate": do_validate,
                },
            )
            
            results_text = "\n".join(results)
            await admin_logger.log_result(
                log_id=log_id,
                status=status,
                results=results_text,
            )
    except Exception:
        pass  # Silent fail for logging

    # Also announce to chat channel if configured
    try:
        from bot.utils.config import Config
        chat_channel_id = Config.CHAT_CHANNEL_ID
        if chat_channel_id:
            chat_channel = interaction.client.get_channel(chat_channel_id)
            if chat_channel:
                announcement_embed = discord.Embed(
                    title="🔔 Server Update Complete",
                    description=f"Admin {interaction.user.mention} has completed updating {completed}/{server_count} server(s)",
                    color=discord.Color.gold(),
                )
                announcement_embed.add_field(name="Details", value="\n".join(results[:10]), inline=False)
                await chat_channel.send(embed=announcement_embed)
    except Exception:
        pass  # Silently fail if chat channel broadcast doesn't work


class UpdateAllServersModal(Modal, title="Update All Servers"):
    """Modal to configure updating all servers."""

    validate = TextInput(
        label="Full Validation? (yes/no)",
        placeholder="yes = validate all files (slower), no = quick update",
        required=False,
        default="no",
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        do_validate = self.validate.value.lower().strip() in ["yes", "true", "1", "y"]

        # Get all servers from database first, fallback to Config
        try:
            servers = await get_ark_servers(interaction.guild_id)
            if not servers:
                servers = Config.ARK_SERVERS
        except Exception:
            servers = Config.ARK_SERVERS
        
        servers = sorted(servers, key=lambda s: s["name"])
        server_count = len(servers)

        # Create confirmation embed
        embed = discord.Embed(
            title="⚠️ Confirm Server Update",
            description=f"You are about to update {server_count} server(s) sequentially.",
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="Mode", value="🔍 Full Validation" if do_validate else "⚡ Quick Update", inline=True
        )
        embed.add_field(
            name="Servers",
            value=", ".join([s["name"] for s in servers]),
            inline=False,
        )
        embed.add_field(
            name="⏱️ Timeline",
            value="• 5 min countdown broadcasts\n• Server shutdown & update (10-30 min each)\n• 30 sec wait between servers\n• **Total: 30+ minutes**",
            inline=False,
        )
        embed.add_field(
            name="🛑 Cancel",
            value="You can cancel remaining updates by closing this message during the process.",
            inline=False,
        )
        embed.set_footer(text=f"Initiated by {interaction.user.display_name}")

        # Create confirmation view
        view = UpdateAllServersConfirmView(servers, do_validate, interaction.user)

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class ServerSelectDropdown(Select):
    """Dropdown to select which server to manage."""

    def __init__(self, servers: List[dict]):
        options = [
            discord.SelectOption(
                label=server["name"],
                description=f"{get_map_name(server)} | {server.get('host', 'localhost')}",
                value=server["name"],
                emoji="🖥️",
            )
            for server in servers
        ]

        super().__init__(
            placeholder="Select an ARK server to manage...",
            options=options,
            custom_id="server_select",
        )

    async def callback(self, interaction: discord.Interaction):
        view: ServerManagementView = self.view
        server_name = self.values[0]

        # Find the selected server
        view.selected_server = next((s for s in view.servers if s["name"] == server_name), None)

        # Update the embed
        embed = view.create_main_embed()

        # Add action buttons if they don't exist
        if not any(isinstance(item, ActionCategoryButton) for item in view.children):
            view.add_item(ActionCategoryButton("Player Management", "👥", "player"))
            view.add_item(ActionCategoryButton("Server Operations", "🖥️", "operations"))
            # Only show Server Control for self-hosted setups
            if view.is_self_hosted:
                view.add_item(ActionCategoryButton("Server Control", "⚙️", "control"))
            view.add_item(ActionCategoryButton("Advanced Tools", "🔧", "advanced"))
            # Only show Diagnostics for self-hosted setups
            if view.is_self_hosted:
                view.add_item(ActionCategoryButton("Diagnostics", "🔍", "diagnostics"))

        await interaction.response.edit_message(embed=embed, view=view)


class ActionCategoryButton(Button):
    """Button for different action categories."""

    def __init__(self, label: str, emoji: str, category: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=label,
            emoji=emoji,
            custom_id=f"category_{category}",
        )
        self.category = category

    async def callback(self, interaction: discord.Interaction):
        view: ServerManagementView = self.view

        if not view.selected_server:
            await interaction.response.send_message(
                "❌ Please select a server first!", ephemeral=True
            )
            return

        # Create action selection menu based on category
        action_view = ActionSelectionView(
            view.guild_id, view.selected_server, self.category, view.user
        )

        embed = action_view.create_embed()
        await interaction.response.send_message(embed=embed, view=action_view, ephemeral=True)


class ActionSelectionView(View):
    """View for selecting specific actions within a category."""

    def __init__(self, guild_id: int, server: dict, category: str, user: discord.User):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.server = server
        self.category = category
        self.user = user

        # Add action buttons based on category
        if category == "player":
            self.add_item(ActionButton("List Online Players", "list_players", "🟢"))
            self.add_item(ActionButton("Kick Player", "kick_player", "🚪"))
            self.add_item(ActionButton("Ban Player", "ban_player", "🔨"))
            self.add_item(ActionButton("Unban Player", "unban_player", "✅"))
            self.add_item(ActionButton("Whitelist Player", "whitelist_player", "⭐"))
            self.add_item(ActionButton("Give XP", "give_xp", "⭐"))
        elif category == "operations":
            self.add_item(ActionButton("Broadcast Message", "broadcast", "📢"))
            self.add_item(ActionButton("Save World", "save_world", "💾"))
            self.add_item(ActionButton("Destroy Wild Dinos", "destroy_dinos", "💥"))
            self.add_item(ActionButton("Set MOTD", "set_motd", "📝"))
        elif category == "control":
            # RCON-based (works everywhere including Nitrado)
            self.add_item(ActionButton("Shutdown (RCON)", "shutdown_rcon", "🚫"))
            # NSSM-based (self-hosted only)
            self.add_item(ActionButton("Start (NSSM)", "start_server", "▶️"))
            self.add_item(ActionButton("Stop (NSSM)", "stop_server", "⏹️"))
            self.add_item(ActionButton("Restart (NSSM)", "restart_server", "🔄"))
            self.add_item(ActionButton("Status (NSSM)", "server_status", "📊"))
        elif category == "advanced":
            self.add_item(ActionButton("Custom RCON", "custom_rcon", "⚙️"))
            self.add_item(ActionButton("Update Server", "update_server", "📥"))
            self.add_item(ActionButton("Get Chat Log", "get_chat", "💬"))
        elif category == "diagnostics":
            self.add_item(ActionButton("View Server Log", "view_log", "📜"))
            self.add_item(ActionButton("View Errors Only", "view_errors", "❌"))
            self.add_item(ActionButton("Crash History", "crash_history", "💥"))



    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ This panel is not for you!", ephemeral=True)
            return False
        return True

    def create_embed(self) -> discord.Embed:
        """Create embed for this action category."""
        category_names = {
            "player": "👥 Player Management",
            "operations": "🖥️ Server Operations",
            "control": "⚙️ Server Control (Self-Hosted Only)",
            "advanced": "🔧 Advanced Tools",
            "diagnostics": "🔍 Diagnostics (Self-Hosted Only)",
        }

        embed = discord.Embed(
            title=category_names.get(self.category, "Actions"),
            description=f"**Server:** {self.server['name']}\n\nSelect an action below:",
            color=discord.Color.green(),
        )

        embed.set_footer(text="Click a button to open the action form")
        return embed


class ActionButton(Button):
    """Button for specific actions."""

    def __init__(self, label: str, action: str, emoji: str):
        super().__init__(
            style=discord.ButtonStyle.success,
            label=label,
            emoji=emoji,
            custom_id=f"action_{action}",
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        view: ActionSelectionView = self.view

        # Special handling for set_motd - show current MOTD first
        if self.action == "set_motd":
            await self.show_motd_preview(interaction, view.server, view.user)
            return

        # Create and show the appropriate modal
        modal = self.create_modal(view.server, self.action)
        if modal:
            await interaction.response.send_modal(modal)
        else:
            # Some actions don't need parameters
            await self.execute_action(interaction, view.server, {})

    async def show_motd_preview(
        self, interaction: discord.Interaction, server: dict, user: discord.User
    ):
        """Show current MOTD before allowing changes."""
        await interaction.response.defer(ephemeral=True)

        # Get guild_id from interaction
        guild_id = interaction.guild_id
        rcon_port = server.get("rcon_port")

        # Fetch current MOTD and duration from database
        current_motd, current_duration = await get_server_motd(guild_id, rcon_port)

        embed = discord.Embed(
            title="📝 Message of the Day",
            description=f"**Server:** {server['name']}",
            color=discord.Color.blue(),
        )

        if current_motd:
            embed.add_field(name="Current MOTD", value=f"```{current_motd}```", inline=False)
            embed.add_field(name="Duration", value=f"{current_duration} seconds", inline=True)
        else:
            embed.add_field(name="Current MOTD", value="*No MOTD has been set yet*", inline=False)

        embed.set_footer(text="Click the button below to change the MOTD")

        # Create view with "Change MOTD" button
        motd_view = MOTDPreviewView(server, user, guild_id, current_duration or 30)
        await interaction.followup.send(embed=embed, view=motd_view, ephemeral=True)

    def create_modal(self, server: dict, action: str) -> Optional[Modal]:
        """Create the appropriate modal for the action."""
        # Get admin logger from cog
        cog = self.view.children[0] if hasattr(self, 'view') and self.view else None
        # Try to get from interaction's client
        admin_logger = None
        
        if action == "list_players":
            return None  # No parameters needed
        elif action == "kick_player":
            return KickPlayerModal(server, admin_logger)
        elif action == "ban_player":
            return BanPlayerModal(server, admin_logger)
        elif action == "unban_player":
            return UnbanPlayerModal(server, admin_logger)
        elif action == "whitelist_player":
            return WhitelistPlayerModal(server, admin_logger)
        elif action == "broadcast":
            return BroadcastModal(server, admin_logger)
        elif action == "save_world":
            return None  # No parameters needed
        elif action == "destroy_dinos":
            return None  # No parameters needed
        elif action == "set_motd":
            return None  # Handled specially in callback to show preview first
        elif action == "start_server":
            return None  # No parameters needed
        elif action == "stop_server":
            return None  # No parameters needed
        elif action == "restart_server":
            return None  # No parameters needed
        elif action == "server_status":
            return None  # No parameters needed
        elif action == "give_xp":
            return GiveXPModal(server, admin_logger)
        elif action == "custom_rcon":
            return CustomRCONModal(server, admin_logger)
        elif action == "update_server":
            return UpdateServerModal(server, admin_logger)
        elif action == "get_chat":
            return None  # No parameters needed
        elif action == "view_log":
            return ViewLogModal(server, admin_logger)
        elif action == "view_errors":
            return None  # Uses default 100 lines
        elif action == "crash_history":
            return None  # No parameters needed
        return None

    async def execute_action(self, interaction: discord.Interaction, server: dict, params: dict):
        """Execute the action (for parameter-less actions)."""
        await interaction.response.defer(ephemeral=True)

        # Get the cog for logging
        cog = interaction.client.get_cog("ServerManagementGUI")
        admin_logger = cog.admin_logger if cog else None

        # Check if this is a server control action
        if self.action in ["start_server", "stop_server", "restart_server", "server_status"]:
            success, response = await self._execute_server_control(server, self.action)
        elif self.action in ["view_errors", "crash_history"]:
            success, response = await self._execute_diagnostics(
                interaction, server, self.action, params
            )
        else:
            # Execute RCON command based on action
            success, response = await self._execute_rcon(server, self.action, params)

        embed = discord.Embed(
            title="✅ Action Complete" if success else "❌ Action Failed",
            description=f"**Server:** {server['name']}\n**Action:** {self.label}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        # Truncate response if too long
        if len(response) > 1024:
            response = response[:1021] + "..."

        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log the action if admin logger is available
        if admin_logger:
            try:
                status = "success" if success else "failed"
                log_id = await admin_logger.log_action(
                    interaction=interaction,
                    action_type=self.action,
                    servers_affected=[server["name"]],
                    details={
                        "action": self.action,
                        "label": self.label,
                        "command": self.label.lower(),
                    },
                )
                
                # Update with results
                await admin_logger.log_result(
                    log_id=log_id,
                    status=status,
                    results=response,
                )
            except Exception as e:
                pass  # Silent fail - logging shouldn't break functionality

    async def _execute_rcon(self, server: dict, action: str, params: dict) -> tuple[bool, str]:
        """Execute RCON command."""
        try:
            rcon_manager = RCONManager([server])

            if action == "list_players":
                command = "ListPlayers"
            elif action == "save_world":
                command = "SaveWorld"
            elif action == "destroy_dinos":
                command = "DestroyWildDinos"
            elif action == "get_chat":
                # Import chat history module
                from bot.database import chat_history_db
                
                # Get last 50 messages from the server
                messages = await chat_history_db.get_chat_history(server["name"], limit=50, hours=24)
                
                if not messages:
                    return True, "📭 No chat messages found in the last 24 hours."
                
                # Format messages (most recent first, so reverse for chronological order)
                chat_lines = []
                for msg in reversed(messages):  # Reverse to show oldest first
                    # Use Discord timestamp format for automatic timezone conversion
                    ts = int(msg["timestamp"])
                    player = msg["player_name"]
                    text = msg["message"]
                    chat_lines.append(f"<t:{ts}:t> {player}: {text}")
                
                # Truncate if too long
                chat_text = "\n".join(chat_lines)
                if len(chat_text) > 1900:
                    chat_text = chat_text[:1900] + "\n... (truncated)"
                
                response = f"💬 **Chat History (Last 24h)**\n```\n{chat_text}\n```"
                return True, response
            elif action == "shutdown_rcon":
                command = "DoExit"
            else:
                return False, "Unknown action"

            success, response = await rcon_manager.execute_command(server["name"], command)

            # Special message for shutdown
            if action == "shutdown_rcon" and success:
                response = "🛑 Server shutdown command sent.\nIf auto-restart is configured (NSSM/Nitrado), the server will restart automatically."

            return success, response

        except Exception as e:
            return False, str(e)

    async def _execute_server_control(self, server: dict, action: str) -> tuple[bool, str]:
        """Execute server control action via NSSM."""
        service_name = server.get("service_name")

        if not service_name:
            return (
                False,
                "Server has no service_name configured. Server control only works for local servers.",
            )

        if not validate_service_name(service_name):
            return (False, "❌ Invalid service name format. Cannot perform this action.")

        try:
            nssm_path = r"C:\nssm\win64\nssm.exe"

            if action == "start_server":
                result = subprocess.run(
                    [nssm_path, "start", service_name], capture_output=True, text=True, timeout=30
                )
                success = result.returncode == 0
                response = f"Server starting...\n{result.stdout or result.stderr}"

            elif action == "stop_server":
                # Send graceful shutdown via RCON first
                from bot.rcon.client import RCONManager
                
                try:
                    # Send DoExit command for graceful shutdown
                    rcon_manager = RCONManager([server])
                    shutdown_success, _ = await rcon_manager.execute_command(server["name"], "DoExit")
                    
                    if shutdown_success:
                        # Wait for server to save and exit gracefully
                        await asyncio.sleep(15)
                        success = True
                        response = "✅ Server shutdown gracefully via RCON.\nWorld saved and server stopped."
                    else:
                        # Fallback to NSSM stop if RCON fails
                        result = subprocess.run(
                            [nssm_path, "stop", service_name], capture_output=True, text=True, timeout=30
                        )
                        success = result.returncode == 0
                        response = f"⚠️ RCON failed, used service stop:\n{result.stdout or result.stderr}"
                        
                except Exception as e:
                    # Fallback to NSSM stop on any error
                    result = subprocess.run(
                        [nssm_path, "stop", service_name], capture_output=True, text=True, timeout=30
                    )
                    success = result.returncode == 0
                    response = f"⚠️ RCON unavailable, used service stop:\n{result.stdout or result.stderr}"

            elif action == "restart_server":
                # For ARK servers, send RCON shutdown first for graceful shutdown
                from bot.rcon.client import RCONManager
                
                try:
                    # Send graceful shutdown via RCON
                    rcon_manager = RCONManager([server])
                    shutdown_success, _ = await rcon_manager.execute_command(server["name"], "DoExit")
                    
                    if shutdown_success:
                        # Wait for server to shutdown (ARK takes 10-30 seconds to save and exit)
                        await asyncio.sleep(15)
                    
                    # Now restart the service (which will start the server again)
                    start_result = subprocess.run(
                        [nssm_path, "start", service_name], capture_output=True, text=True, timeout=30
                    )
                    
                    if start_result.returncode == 0 or "already started" in start_result.stdout.lower():
                        success = True
                        response = "✅ Server shutdown via RCON and service restarted.\nThe server will be online in 5-10 minutes."
                    else:
                        success = False
                        response = f"⚠️ Server shutdown but service failed to start:\n{start_result.stdout or start_result.stderr}"
                        
                except Exception as e:
                    # Fallback to stop/start if RCON fails
                    stop_result = subprocess.run(
                        [nssm_path, "stop", service_name], capture_output=True, text=True, timeout=30
                    )
                    
                    if stop_result.returncode == 0:
                        await asyncio.sleep(3)

                        start_result = subprocess.run(
                            [nssm_path, "start", service_name], capture_output=True, text=True, timeout=30
                        )
                        
                        if start_result.returncode == 0:
                            success = True
                            response = "✅ Server stopped and restarted successfully (fallback method).\nThe server will be online in 5-10 minutes."
                        else:
                            success = False
                            response = f"⚠️ Server stopped but failed to restart:\n{start_result.stdout or start_result.stderr}"
                    else:
                        success = False
                        response = f"❌ Failed to stop server:\n{stop_result.stdout or stop_result.stderr}"

            elif action == "server_status":
                result = subprocess.run(
                    [nssm_path, "status", service_name], capture_output=True, text=True, timeout=30
                )
                success = True
                status = result.stdout.strip().upper()

                if "RUNNING" in status or "SERVICE_RUNNING" in status:
                    response = "🟢 Server is RUNNING"
                elif "STOPPED" in status or "SERVICE_STOPPED" in status:
                    response = "🔴 Server is STOPPED"
                elif "PAUSED" in status or "SERVICE_PAUSED" in status:
                    response = "🟡 Server is PAUSED"
                else:
                    response = f"⚪ Server status: {status}"
            else:
                return False, "Unknown server control action"

            return success, response

        except subprocess.TimeoutExpired:
            return False, "Command timed out after 30 seconds"
        except FileNotFoundError:
            return False, f"NSSM not found at {nssm_path}"
        except Exception as e:
            return False, f"Error executing command: {str(e)}"

    async def _execute_diagnostics(
        self, interaction: discord.Interaction, server: dict, action: str, params: dict
    ) -> tuple[bool, str]:
        """Execute diagnostic actions (log viewing, crash history)."""
        from bot.database import server_config_db

        guild_id = interaction.guild_id
        rcon_port = server.get("rcon_port")

        try:
            if action == "view_errors":
                # Get server path and read log
                server_path = await get_server_path(guild_id, rcon_port)

                if not server_path:
                    return (
                        False,
                        "No server_path configured for this server.\nUse /editserver to set the server path.",
                    )

                log_path = get_server_log_path(server_path)
                if not log_path:
                    return (
                        False,
                        f"Log file not found at expected location:\n{server_path}\\ShooterGame\\Saved\\Logs\\ShooterGame.log",
                    )

                # Read log and filter for errors
                try:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()

                    error_lines = []
                    for line in lines[-500:]:  # Check last 500 lines
                        line_lower = line.lower()
                        if any(
                            term in line_lower
                            for term in ["error", "fatal", "exception", "crash", "fail"]
                        ):
                            error_lines.append(line.strip()[:150])

                    if error_lines:
                        # Take last 15 errors
                        errors = error_lines[-15:]
                        return True, "\n".join(errors)
                    else:
                        return True, "✅ No errors found in the last 500 lines of the log."

                except Exception as e:
                    return False, f"Error reading log: {e}"

            elif action == "crash_history":
                # Get crash history from database
                crashes = await server_config_db.get_crash_history(
                    guild_id=guild_id, server_name=server["name"], days=7
                )

                if not crashes:
                    return True, f"✅ No crashes recorded for {server['name']} in the last 7 days."

                # Format crash history
                lines = [f"📊 Crash History for {server['name']} (last 7 days):\n"]
                for crash in crashes[:10]:  # Last 10 crashes
                    crash_time = crash["crash_time"]
                    # Use Discord timestamp format for automatic timezone conversion
                    if hasattr(crash_time, "timestamp"):
                        ts = int(crash_time.timestamp())
                        time_str = f"<t:{ts}:f>"
                    else:
                        time_str = str(crash_time)[:16]
                    cause = crash.get("possible_cause", "Unknown")
                    lines.append(f"• {time_str} - {cause}")

                return True, "\n".join(lines)

            return False, "Unknown diagnostic action"

        except Exception as e:
            return False, f"Error: {str(e)}"


# Modal Forms
class KickPlayerModal(Modal, title="Kick Player"):
    player_name = TextInput(
        label="Player Name",
        placeholder="Enter the player's in-game name...",
        required=True,
        max_length=100,
    )
    reason = TextInput(
        label="Reason (optional)",
        placeholder="Why are you kicking this player?",
        required=False,
        max_length=200,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, server: dict, admin_logger=None):
        super().__init__()
        self.server = server
        self.admin_logger = admin_logger

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Execute RCON command
        command = f"KickPlayer {self.player_name.value}"
        success, response = await self._execute_rcon(command)

        embed = discord.Embed(
            title="🚪 Player Kicked" if success else "❌ Kick Failed",
            description=f"**Server:** {self.server['name']}\n**Player:** {self.player_name.value}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        if self.reason.value:
            embed.add_field(name="Reason", value=self.reason.value, inline=False)

        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log the action
        if self.admin_logger:
            try:
                status = "success" if success else "failed"
                log_id = await self.admin_logger.log_action(
                    interaction=interaction,
                    action_type="kick_player",
                    servers_affected=[self.server["name"]],
                    details={
                        "command": "KickPlayer",
                        "reason": self.reason.value or "No reason provided",
                    },
                    target_player=self.player_name.value,
                )
                
                await self.admin_logger.log_result(
                    log_id=log_id,
                    status=status,
                    results=response,
                )
            except Exception as e:
                pass  # Silent fail

    async def _execute_rcon(self, command: str) -> tuple[bool, str]:
        """Execute RCON command."""
        try:
            rcon_manager = RCONManager([self.server])
            success, response = await rcon_manager.execute_command(self.server["name"], command)
            return success, response
        except Exception as e:
            return False, str(e)


class BanPlayerModal(Modal, title="Ban Player"):
    player_name = TextInput(
        label="Player Name",
        placeholder="Enter the player's in-game name...",
        required=True,
        max_length=100,
    )
    reason = TextInput(
        label="Reason",
        placeholder="Why are you banning this player?",
        required=True,
        max_length=200,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, server: dict, admin_logger=None):
        super().__init__()
        self.server = server
        self.admin_logger = admin_logger

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        command = f"BanPlayer {self.player_name.value}"
        success, response = await self._execute_rcon(command)

        embed = discord.Embed(
            title="🔨 Player Banned" if success else "❌ Ban Failed",
            description=f"**Server:** {self.server['name']}\n**Player:** {self.player_name.value}",
            color=discord.Color.orange() if success else discord.Color.red(),
        )

        embed.add_field(name="Reason", value=self.reason.value, inline=False)

        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log the action
        if self.admin_logger:
            try:
                status = "success" if success else "failed"
                log_id = await self.admin_logger.log_action(
                    interaction=interaction,
                    action_type="ban_player",
                    servers_affected=[self.server["name"]],
                    details={
                        "command": "BanPlayer",
                        "reason": self.reason.value,
                    },
                    target_player=self.player_name.value,
                )
                await self.admin_logger.log_result(
                    log_id=log_id,
                    status=status,
                    results=response,
                )
            except Exception:
                pass

    async def _execute_rcon(self, command: str) -> tuple[bool, str]:
        try:
            rcon_manager = RCONManager([self.server])
            success, response = await rcon_manager.execute_command(self.server["name"], command)
            return success, response
        except Exception as e:
            return False, str(e)


class UnbanPlayerModal(Modal, title="Unban Player"):
    player_id = TextInput(
        label="Player Steam ID or EOS ID",
        placeholder="Enter the player's ID...",
        required=True,
        max_length=100,
    )

    def __init__(self, server: dict, admin_logger=None):
        super().__init__()
        self.server = server
        self.admin_logger = admin_logger

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        command = f"UnbanPlayer {self.player_id.value}"
        success, response = await self._execute_rcon(command)

        embed = discord.Embed(
            title="✅ Player Unbanned" if success else "❌ Unban Failed",
            description=f"**Server:** {self.server['name']}\n**Player ID:** {self.player_id.value}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log admin action
        if self.admin_logger:
            try:
                log_id = await self.admin_logger.log_action(
                    action_type="unban_player",
                    admin_id=interaction.user.id,
                    admin_name=interaction.user.display_name,
                    server_name=self.server.get("name", "Unknown"),
                    details=f"Player ID: {self.player_id.value}",
                    interaction=interaction,
                )
                await self.admin_logger.log_result(
                    log_id=log_id,
                    success=success,
                    result=response[:500] if len(response) > 500 else response,
                )
            except Exception:
                pass

    async def _execute_rcon(self, command: str) -> tuple[bool, str]:
        try:
            rcon_manager = RCONManager([self.server])
            success, response = await rcon_manager.execute_command(self.server["name"], command)
            return success, response
        except Exception as e:
            return False, str(e)


class WhitelistPlayerModal(Modal, title="Whitelist Player"):
    steam_id = TextInput(
        label="Player Steam ID",
        placeholder="Enter the player's Steam ID...",
        required=True,
        max_length=100,
    )

    def __init__(self, server: dict, admin_logger=None):
        super().__init__()
        self.server = server
        self.admin_logger = admin_logger

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        command = f"AllowPlayerToJoinNoCheck {self.steam_id.value}"
        success, response = await self._execute_rcon(command)

        embed = discord.Embed(
            title="⭐ Player Whitelisted" if success else "❌ Whitelist Failed",
            description=f"**Server:** {self.server['name']}\n**Steam ID:** {self.steam_id.value}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log admin action
        if self.admin_logger:
            try:
                log_id = await self.admin_logger.log_action(
                    action_type="whitelist_player",
                    admin_id=interaction.user.id,
                    admin_name=interaction.user.display_name,
                    server_name=self.server.get("name", "Unknown"),
                    details=f"Steam ID: {self.steam_id.value}",
                    interaction=interaction,
                )
                await self.admin_logger.log_result(
                    log_id=log_id,
                    success=success,
                    result=response[:500] if len(response) > 500 else response,
                )
            except Exception:
                pass

    async def _execute_rcon(self, command: str) -> tuple[bool, str]:
        try:
            rcon_manager = RCONManager([self.server])
            success, response = await rcon_manager.execute_command(self.server["name"], command)
            return success, response
        except Exception as e:
            return False, str(e)


class BroadcastModal(Modal, title="Broadcast Message"):
    message = TextInput(
        label="Message",
        placeholder="Enter the message to broadcast...",
        required=True,
        max_length=200,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, server: dict, admin_logger=None):
        super().__init__()
        self.server = server
        self.admin_logger = admin_logger

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        command = f"ServerChat {self.message.value}"
        success, response = await self._execute_rcon(command)

        embed = discord.Embed(
            title="📢 Message Broadcast" if success else "❌ Broadcast Failed",
            description=f"**Server:** {self.server['name']}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        embed.add_field(name="Message Sent", value=self.message.value, inline=False)

        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log admin action
        if self.admin_logger:
            try:
                log_id = await self.admin_logger.log_action(
                    action_type="broadcast_message",
                    admin_id=interaction.user.id,
                    admin_name=interaction.user.display_name,
                    server_name=self.server.get("name", "Unknown"),
                    details=f"Message: {self.message.value[:100]}",
                    interaction=interaction,
                )
                await self.admin_logger.log_result(
                    log_id=log_id,
                    success=success,
                    result=response[:500] if len(response) > 500 else response,
                )
            except Exception:
                pass

    async def _execute_rcon(self, command: str) -> tuple[bool, str]:
        try:
            rcon_manager = RCONManager([self.server])
            success, response = await rcon_manager.execute_command(self.server["name"], command)
            return success, response
        except Exception as e:
            return False, str(e)


class MOTDPreviewView(View):
    """View showing current MOTD with button to change it."""

    def __init__(
        self,
        server: dict,
        user: discord.User,
        guild_id: int,
        current_duration: int = 30,
        timeout: int = 120,
    ):
        super().__init__(timeout=timeout)
        self.server = server
        self.user = user
        self.guild_id = guild_id
        self.current_duration = current_duration

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ This is not your panel!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Change MOTD", style=discord.ButtonStyle.primary, emoji="✏️")
    async def change_motd(self, interaction: discord.Interaction, button: Button):
        modal = SetMOTDModal(self.server, self.guild_id, self.current_duration)
        await interaction.response.send_modal(modal)


class SetMOTDModal(Modal, title="Set Message of the Day"):
    motd = TextInput(
        label="Message of the Day",
        placeholder="Enter the new MOTD...",
        required=True,
        max_length=200,
        style=discord.TextStyle.paragraph,
    )

    duration = TextInput(
        label="Duration (seconds)",
        placeholder="How long to display on login (default: 30)",
        required=False,
        default="30",
        max_length=5,
    )

    def __init__(self, server: dict, guild_id: int = None, current_duration: int = 30):
        super().__init__()
        self.server = server
        self.guild_id = guild_id
        # Pre-fill the duration with current value
        self.duration.default = str(current_duration)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Parse duration (default to 30 if invalid)
        try:
            duration_val = int(self.duration.value) if self.duration.value else 30
            duration_val = max(5, min(300, duration_val))  # Clamp between 5-300 seconds
        except ValueError:
            duration_val = 30

        # ARK uses two commands: SetMessageOfTheDay and SetMOTDDuration
        motd_cmd = f"SetMessageOfTheDay {self.motd.value}"
        duration_cmd = f"SetMOTDDuration {duration_val}"

        success1, response1 = await self._execute_rcon(motd_cmd)
        success2, response2 = await self._execute_rcon(duration_cmd)

        success = success1  # Main success is setting the message

        # Store MOTD in database if successful
        if success and self.guild_id:
            try:
                await set_server_motd(
                    self.guild_id, self.server.get("rcon_port"), self.motd.value, duration_val
                )
            except Exception:
                pass  # Non-critical, continue

        embed = discord.Embed(
            title="📝 MOTD Updated" if success else "❌ MOTD Update Failed",
            description=f"**Server:** {self.server['name']}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        embed.add_field(name="New MOTD", value=self.motd.value, inline=False)
        embed.add_field(name="Duration", value=f"{duration_val} seconds", inline=True)

        response = response1 if response1 else "Command executed successfully"
        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _execute_rcon(self, command: str) -> tuple[bool, str]:
        try:
            rcon_manager = RCONManager([self.server])
            success, response = await rcon_manager.execute_command(self.server["name"], command)
            return success, response
        except Exception as e:
            return False, str(e)


class GiveItemModal(Modal, title="Give Item to Player"):
    player_id = TextInput(
        label="Player ID or Name",
        placeholder="Steam ID or character name...",
        required=True,
        max_length=100,
    )
    item_blueprint = TextInput(
        label="Item Blueprint ID",
        placeholder="e.g., PrimalItemResource_Metal_C",
        required=True,
        max_length=200,
    )
    quantity = TextInput(
        label="Quantity",
        placeholder="How many to give (default: 1)",
        required=False,
        default="1",
        max_length=10,
    )
    quality = TextInput(
        label="Quality",
        placeholder="Item quality (default: 1)",
        required=False,
        default="1",
        max_length=10,
    )

    def __init__(self, server: dict):
        super().__init__()
        self.server = server

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        qty = self.quantity.value or "1"
        qual = self.quality.value or "1"

        command = f"GiveItemToPlayer {self.player_id.value} {self.item_blueprint.value} {qty} {qual} false"
        success, response = await self._execute_rcon(command)

        embed = discord.Embed(
            title="📦 Item Given" if success else "❌ Give Item Failed",
            description=f"**Server:** {self.server['name']}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        embed.add_field(name="Player", value=self.player_id.value, inline=True)
        embed.add_field(name="Item", value=self.item_blueprint.value, inline=True)
        embed.add_field(name="Quantity", value=qty, inline=True)
        embed.add_field(name="Quality", value=qual, inline=True)

        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _execute_rcon(self, command: str) -> tuple[bool, str]:
        try:
            rcon_manager = RCONManager([self.server])
            success, response = await rcon_manager.execute_command(self.server["name"], command)
            return success, response
        except Exception as e:
            return False, str(e)


class GiveDinoModal(Modal, title="Give Dino to Player"):
    player_id = TextInput(
        label="Player ID or Name",
        placeholder="Steam ID or character name...",
        required=True,
        max_length=100,
    )
    dino_type = TextInput(
        label="Dino Type", placeholder="e.g., Rex_Character_BP_C", required=True, max_length=200
    )
    level = TextInput(
        label="Dino Level",
        placeholder="Level (default: 150)",
        required=False,
        default="150",
        max_length=10,
    )

    def __init__(self, server: dict):
        super().__init__()
        self.server = server

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        lvl = self.level.value or "150"

        command = f"GiveDinoToPlayer {self.player_id.value} {self.dino_type.value} {lvl}"
        success, response = await self._execute_rcon(command)

        embed = discord.Embed(
            title="🦖 Dino Given" if success else "❌ Give Dino Failed",
            description=f"**Server:** {self.server['name']}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        embed.add_field(name="Player", value=self.player_id.value, inline=True)
        embed.add_field(name="Dino", value=self.dino_type.value, inline=True)
        embed.add_field(name="Level", value=lvl, inline=True)

        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _execute_rcon(self, command: str) -> tuple[bool, str]:
        try:
            rcon_manager = RCONManager([self.server])
            success, response = await rcon_manager.execute_command(self.server["name"], command)
            return success, response
        except Exception as e:
            return False, str(e)


class GiveXPModal(Modal, title="Give XP to Player"):
    player_id = TextInput(
        label="Player ID or Name",
        placeholder="Steam ID or character name...",
        required=True,
        max_length=100,
    )
    xp_amount = TextInput(
        label="XP Amount", placeholder="Experience points to give...", required=True, max_length=20
    )
    share_with_tribe = TextInput(
        label="Share with Tribe? (yes/no)",
        placeholder="yes or no",
        required=False,
        default="no",
        max_length=3,
    )

    def __init__(self, server: dict, admin_logger=None):
        super().__init__()
        self.server = server
        self.admin_logger = admin_logger

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        share = "true" if self.share_with_tribe.value.lower() == "yes" else "false"

        command = f"GiveExpToPlayer {self.player_id.value} {self.xp_amount.value} {share} false"
        success, response = await self._execute_rcon(command)

        embed = discord.Embed(
            title="⭐ XP Given" if success else "❌ Give XP Failed",
            description=f"**Server:** {self.server['name']}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        embed.add_field(name="Player", value=self.player_id.value, inline=True)
        embed.add_field(name="XP Amount", value=self.xp_amount.value, inline=True)
        embed.add_field(name="Share with Tribe", value=share, inline=True)

        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log admin action
        if self.admin_logger:
            try:
                log_id = await self.admin_logger.log_action(
                    action_type="give_xp",
                    admin_id=interaction.user.id,
                    admin_name=interaction.user.display_name,
                    server_name=self.server.get("name", "Unknown"),
                    details=f"Player: {self.player_id.value}, XP: {self.xp_amount.value}, Share: {share}",
                    interaction=interaction,
                )
                await self.admin_logger.log_result(
                    log_id=log_id,
                    success=success,
                    result=response[:500] if len(response) > 500 else response,
                )
            except Exception:
                pass

    async def _execute_rcon(self, command: str) -> tuple[bool, str]:
        try:
            rcon_manager = RCONManager([self.server])
            success, response = await rcon_manager.execute_command(self.server["name"], command)
            return success, response
        except Exception as e:
            return False, str(e)


class CustomRCONModal(Modal, title="Execute Custom RCON Command"):
    command = TextInput(
        label="RCON Command",
        placeholder="Enter any RCON command...",
        required=True,
        max_length=500,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, server: dict, admin_logger=None):
        super().__init__()
        self.server = server
        self.admin_logger = admin_logger

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        success, response = await self._execute_rcon(self.command.value)

        embed = discord.Embed(
            title="⚙️ Custom RCON Executed" if success else "❌ RCON Failed",
            description=f"**Server:** {self.server['name']}",
            color=discord.Color.blue() if success else discord.Color.red(),
        )

        embed.add_field(name="Command", value=f"```{self.command.value}```", inline=False)

        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log admin action
        if self.admin_logger:
            try:
                log_id = await self.admin_logger.log_action(
                    action_type="custom_rcon",
                    admin_id=interaction.user.id,
                    admin_name=interaction.user.display_name,
                    server_name=self.server.get("name", "Unknown"),
                    details=f"Command: {self.command.value[:100]}",
                    interaction=interaction,
                )
                await self.admin_logger.log_result(
                    log_id=log_id,
                    success=success,
                    result=response[:500] if len(response) > 500 else response,
                )
            except Exception:
                pass

    async def _execute_rcon(self, command: str) -> tuple[bool, str]:
        try:
            rcon_manager = RCONManager([self.server])
            success, response = await rcon_manager.execute_command(self.server["name"], command)
            return success, response
        except Exception as e:
            return False, str(e)


class ViewLogModal(Modal, title="View Server Log"):
    """Modal for viewing server log files."""

    lines = TextInput(
        label="Number of Lines",
        placeholder="50",
        default="50",
        min_length=1,
        max_length=3,
        required=True,
    )

    filter_text = TextInput(
        label="Filter (optional)",
        placeholder="Leave empty for all, or enter: error, warning, mod, etc.",
        required=False,
        max_length=50,
    )

    def __init__(self, server: dict, admin_logger=None):
        super().__init__()
        self.server = server
        self.admin_logger = admin_logger

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            num_lines = int(self.lines.value)
            num_lines = min(max(num_lines, 10), 200)  # Clamp between 10-200
        except ValueError:
            num_lines = 50

        filter_term = self.filter_text.value.strip().lower() if self.filter_text.value else None

        guild_id = interaction.guild_id
        rcon_port = self.server.get("rcon_port")

        # Get server path
        server_path = await get_server_path(guild_id, rcon_port)

        if not server_path:
            embed = discord.Embed(
                title="❌ Server Path Not Configured",
                description=f"Cannot view logs for **{self.server['name']}** because the server path is not set.",
                color=discord.Color.red(),
            )
            embed.add_field(
                name="How to Fix",
                value="1. Run `/servercfg`\n"
                      "2. Select the server\n"
                      "3. Click **Edit Server**\n"
                      "4. Fill in the **Server Path** field (e.g., `R:\\PhoenixArk\\asaserver_island`)\n"
                      "5. Save the changes",
                inline=False,
            )
            embed.set_footer(text="The server path is required to locate log files")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        log_path = get_server_log_path(server_path)
        if not log_path:
            await interaction.followup.send(
                f"❌ Log file not found at expected location:\n"
                f"`{server_path}\\ShooterGame\\Saved\\Logs\\ShooterGame.log`",
                ephemeral=True,
            )
            return

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()

            # Apply filter if specified
            if filter_term:
                filtered = [l for l in all_lines if filter_term in l.lower()]
                lines_to_show = filtered[-num_lines:]
                header = f"📜 **Log for {self.server['name']}** (last {len(lines_to_show)} lines matching '{filter_term}'):"
            else:
                lines_to_show = all_lines[-num_lines:]
                header = f"📜 **Log for {self.server['name']}** (last {num_lines} lines):"

            log_content = "".join(lines_to_show)

            # Split into chunks for Discord (max 1900 chars per message to be safe)
            await interaction.followup.send(header, ephemeral=True)

            chunks = [log_content[i : i + 1900] for i in range(0, len(log_content), 1900)]
            for i, chunk in enumerate(chunks[:5]):  # Max 5 chunks
                await interaction.followup.send(f"```\n{chunk}\n```", ephemeral=True)

            if len(chunks) > 5:
                await interaction.followup.send(
                    f"*... truncated ({len(chunks) - 5} more chunks)*", ephemeral=True
                )

            # Log admin action
            if self.admin_logger:
                try:
                    log_id = await self.admin_logger.log_action(
                        action_type="view_log",
                        admin_id=interaction.user.id,
                        admin_name=interaction.user.display_name,
                        server_name=self.server.get("name", "Unknown"),
                        details=f"Lines: {num_lines}, Filter: {filter_term or 'None'}",
                        interaction=interaction,
                    )
                    await self.admin_logger.log_result(
                        log_id=log_id,
                        success=True,
                        result=f"Displayed {len(lines_to_show)} log lines",
                    )
                except Exception:
                    pass

        except Exception as e:
            await interaction.followup.send(f"❌ Error reading log: {e}", ephemeral=True)

            # Log failure
            if self.admin_logger:
                try:
                    log_id = await self.admin_logger.log_action(
                        action_type="view_log",
                        admin_id=interaction.user.id,
                        admin_name=interaction.user.display_name,
                        server_name=self.server.get("name", "Unknown"),
                        details=f"Lines: {num_lines}, Filter: {filter_term or 'None'}",
                        interaction=interaction,
                    )
                    await self.admin_logger.log_result(
                        log_id=log_id,
                        success=False,
                        result=str(e)[:500],
                    )
                except Exception:
                    pass


class ServerManagementGUI(commands.Cog):
    """Interactive server management GUI commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.admin_logger = AdminLogger(bot)

    @app_commands.command(
        name="servermgmt",
        description="📊 Open the interactive server management panel (Admin Only)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def server_mgmt(self, interaction: discord.Interaction):
        """Open the interactive server management GUI."""
        # Create the main view
        view = ServerManagementView(interaction.guild_id, interaction.user)

        # Wait for servers to load
        await asyncio.sleep(0.5)

        # Add update all servers button first
        view.add_item(UpdateAllServersButton())

        # Add server selector
        if view.servers:
            view.add_item(ServerSelectDropdown(view.servers))

        # Create and send main embed
        embed = view.create_main_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class GiveItemView(View):
    """Interactive view for giving items to players with arkids.net integration."""

    def __init__(self, server: dict, user: discord.User, guild_id: int, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.server = server
        self.user = user
        self.guild_id = guild_id
        self.selected_player = None
        self.selected_item = None

        # Add player selector
        self.player_select = PlayerSelectDropdown()
        self.add_item(self.player_select)

        # Add item search button
        self.add_item(ItemSearchButton())

        # Add quantity/quality button
        self.add_item(ConfirmItemButton())

        # Add close button


    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ This panel is not for you!", ephemeral=True)
            return False
        return True


class PlayerSelectDropdown(Select):
    """Dropdown to select a player from Discord members."""

    def __init__(self):
        super().__init__(
            placeholder="Select a player...", custom_id="player_select", min_values=1, max_values=1
        )
        # Will be populated dynamically
        asyncio.create_task(self._load_players())

    async def _load_players(self):
        """Load players with linked accounts."""
        try:
            linked_players = await get_all_linked_players()

            options = []
            for player in linked_players[:25]:  # Discord limit
                discord_id = player.get("discord_user_id")
                eos_id = player.get("eos_id", "Unknown")

                # Get Discord user
                try:
                    user = (
                        await self.view.user.guild.fetch_member(discord_id)
                        if hasattr(self.view, "user")
                        else None
                    )
                    display_name = user.display_name if user else f"User {discord_id}"
                except:
                    display_name = f"User {discord_id}"

                options.append(
                    discord.SelectOption(
                        label=display_name[:100],
                        description=f"EOS: {eos_id[:50]}",
                        value=str(discord_id),
                        emoji="👤",
                    )
                )

            # Add option for manual entry
            options.append(
                discord.SelectOption(
                    label="Manual Entry (Steam ID/Name)",
                    description="For players not linked to Discord",
                    value="manual",
                    emoji="✏️",
                )
            )

            self.options = options[:25]  # Discord limit
        except Exception as e:
            self.options = [
                discord.SelectOption(
                    label="Error loading players", description=str(e)[:100], value="error"
                )
            ]

    async def callback(self, interaction: discord.Interaction):
        view: GiveItemView = self.view

        if self.values[0] == "manual":
            # Show manual entry modal
            await interaction.response.send_modal(ManualPlayerEntryModal(view))
        elif self.values[0] == "error":
            await interaction.response.send_message(
                "❌ Error loading players. Please try again.", ephemeral=True
            )
        else:
            # Store selected player
            discord_id = int(self.values[0])
            player_data = await get_player_by_discord_id(discord_id)
            view.selected_player = player_data

            await interaction.response.send_message(
                f"✅ Selected player: <@{discord_id}> (EOS: `{player_data.get('eos_id', 'Unknown')}`)",
                ephemeral=True,
            )


class ManualPlayerEntryModal(Modal, title="Manual Player Entry"):
    """Modal for entering player ID/name manually."""

    player_id = TextInput(
        label="Player ID or Name",
        placeholder="Steam ID, EOS ID, or character name...",
        required=True,
        max_length=100,
    )

    def __init__(self, parent_view: GiveItemView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.selected_player = {"manual": self.player_id.value}
        await interaction.response.send_message(
            f"✅ Selected player: `{self.player_id.value}`", ephemeral=True
        )


class ItemSearchButton(Button):
    """Button to search for items."""

    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Search Items",
            emoji="🔍",
            custom_id="item_search",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ItemSearchModal(self.view))


class ItemSearchModal(Modal, title="Search for Items"):
    """Modal for searching items."""

    search_term = TextInput(
        label="Item Name",
        placeholder="e.g., Metal, Stone, Gun, etc.",
        required=True,
        max_length=100,
    )

    def __init__(self, parent_view: GiveItemView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        query = self.search_term.value

        # Try arkids.net first
        arkids_client = get_arkids_client()
        items = await arkids_client.search_items(query, limit=25)

        # Fallback to shop database if no results
        if not items:
            shop_items = await get_all_items(enabled_only=False)
            items = [
                type(
                    "Item",
                    (),
                    {
                        "name": item["name"],
                        "blueprint": item["ark_command"],
                        "category": item.get("category", "Shop"),
                        "type": "item",
                    },
                )()
                for item in shop_items
                if query.lower() in item["name"].lower()
            ][:25]

        if not items:
            await interaction.followup.send(f"❌ No items found matching '{query}'", ephemeral=True)
            return

        # Show results
        view = ItemResultsView(self.parent_view, items, query)
        embed = discord.Embed(
            title=f"🔍 Search Results: {query}",
            description=f"Found {len(items)} items",
            color=discord.Color.blue(),
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class ItemResultsView(View):
    """View showing item search results."""

    def __init__(self, parent_view: GiveItemView, items: list, query: str, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.parent_view = parent_view
        self.items = items
        self.query = query

        # Create dropdown with results
        self.add_item(ItemResultsDropdown(items))



class ItemResultsDropdown(Select):
    """Dropdown showing item search results."""

    def __init__(self, items: list):
        options = []
        for i, item in enumerate(items[:25]):  # Discord limit
            options.append(
                discord.SelectOption(
                    label=item.name[:100],
                    description=f"{item.category} | {item.blueprint[:50]}",
                    value=str(i),
                    emoji="📦",
                )
            )

        super().__init__(placeholder="Select an item...", options=options, custom_id="item_results")
        self.items = items

    async def callback(self, interaction: discord.Interaction):
        view: ItemResultsView = self.view
        idx = int(self.values[0])
        selected_item = self.items[idx]

        view.parent_view.selected_item = selected_item

        await interaction.response.send_message(
            f"✅ Selected: **{selected_item.name}**\n`{selected_item.blueprint}`", ephemeral=True
        )


class ConfirmItemButton(Button):
    """Button to confirm and give item."""

    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Give Item",
            emoji="✅",
            custom_id="confirm_item",
        )

    async def callback(self, interaction: discord.Interaction):
        view: GiveItemView = self.view

        if not view.selected_player:
            await interaction.response.send_message(
                "❌ Please select a player first!", ephemeral=True
            )
            return

        if not view.selected_item:
            await interaction.response.send_message(
                "❌ Please search and select an item first!", ephemeral=True
            )
            return

        # Show quantity/quality modal
        await interaction.response.send_modal(ItemQuantityModal(view))


class ItemQuantityModal(Modal, title="Item Quantity & Quality"):
    """Modal for entering quantity and quality."""

    quantity = TextInput(
        label="Quantity",
        placeholder="How many to give (default: 1)",
        required=False,
        default="1",
        max_length=10,
    )
    quality = TextInput(
        label="Quality",
        placeholder="Item quality (default: 1)",
        required=False,
        default="1",
        max_length=10,
    )

    def __init__(self, parent_view: GiveItemView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        view = self.parent_view
        player = view.selected_player
        item = view.selected_item
        qty = self.quantity.value or "1"
        qual = self.quality.value or "1"

        # Determine player identifier
        if isinstance(player, dict) and "manual" in player:
            player_id = player["manual"]
        elif isinstance(player, dict) and "eos_id" in player:
            player_id = player["eos_id"]
        else:
            player_id = str(player)

        # Get blueprint
        blueprint = item.blueprint if hasattr(item, "blueprint") else str(item)

        # Execute command - auto-detect server
        success, response, server_used = await self._give_item_auto_server(
            player_id, blueprint, qty, qual, view.guild_id
        )

        embed = discord.Embed(
            title="📦 Item Given" if success else "❌ Give Item Failed",
            description=f"**Server:** {server_used if server_used else 'Unknown'}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        embed.add_field(name="Player", value=player_id, inline=True)
        embed.add_field(
            name="Item", value=item.name if hasattr(item, "name") else blueprint, inline=True
        )
        embed.add_field(name="Quantity", value=qty, inline=True)
        embed.add_field(name="Quality", value=qual, inline=True)

        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _give_item_auto_server(
        self, player_id: str, blueprint: str, qty: str, qual: str, guild_id: int
    ) -> tuple:
        """Give item to player, auto-detecting which server they're on."""
        try:
            servers = await get_ark_servers(guild_id)
            if not servers:
                servers = Config.ARK_SERVERS

            rcon_manager = RCONManager(servers)

            # Try to find player on a server
            player_found = False
            for server in servers:
                try:
                    # Check if player is online
                    success, players_response = await rcon_manager.execute_command(
                        server["name"], "ListPlayers"
                    )

                    if success and player_id.lower() in players_response.lower():
                        player_found = True
                        # Give item on this server
                        command = f"GiveItemToPlayer {player_id} {blueprint} {qty} {qual} false"
                        success, response = await rcon_manager.execute_command(
                            server["name"], command
                        )
                        return success, response, server["name"]
                except:
                    continue

            if not player_found:
                return False, f"Player '{player_id}' not found on any server", None

            return False, "Failed to give item", None
        except Exception as e:
            return False, str(e), None


class GiveCreatureView(View):
    """Interactive view for giving creatures to players with arkids.net integration."""

    def __init__(self, server: dict, user: discord.User, guild_id: int, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.server = server
        self.user = user
        self.guild_id = guild_id
        self.selected_player = None
        self.selected_creature = None

        # Add player selector
        self.player_select = CreaturePlayerSelectDropdown()
        self.add_item(self.player_select)

        # Add creature search button
        self.add_item(CreatureSearchButton())

        # Add confirm button
        self.add_item(ConfirmCreatureButton())

        # Add close button


    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ This panel is not for you!", ephemeral=True)
            return False
        return True


class CreaturePlayerSelectDropdown(Select):
    """Dropdown to select a player for creature spawning."""

    def __init__(self):
        super().__init__(
            placeholder="Select a player...",
            custom_id="creature_player_select",
            min_values=1,
            max_values=1,
        )
        asyncio.create_task(self._load_players())

    async def _load_players(self):
        """Load players with linked accounts."""
        try:
            linked_players = await get_all_linked_players()

            options = []
            for player in linked_players[:25]:
                discord_id = player.get("discord_user_id")
                eos_id = player.get("eos_id", "Unknown")

                try:
                    user = (
                        await self.view.user.guild.fetch_member(discord_id)
                        if hasattr(self.view, "user")
                        else None
                    )
                    display_name = user.display_name if user else f"User {discord_id}"
                except:
                    display_name = f"User {discord_id}"

                options.append(
                    discord.SelectOption(
                        label=display_name[:100],
                        description=f"EOS: {eos_id[:50]}",
                        value=str(discord_id),
                        emoji="👤",
                    )
                )

            options.append(
                discord.SelectOption(
                    label="Manual Entry (Steam ID/Name)",
                    description="For players not linked to Discord",
                    value="manual",
                    emoji="✏️",
                )
            )

            self.options = options[:25]
        except Exception as e:
            self.options = [
                discord.SelectOption(
                    label="Error loading players", description=str(e)[:100], value="error"
                )
            ]

    async def callback(self, interaction: discord.Interaction):
        view: GiveCreatureView = self.view

        if self.values[0] == "manual":
            await interaction.response.send_modal(ManualCreaturePlayerEntryModal(view))
        elif self.values[0] == "error":
            await interaction.response.send_message(
                "❌ Error loading players. Please try again.", ephemeral=True
            )
        else:
            discord_id = int(self.values[0])
            player_data = await get_player_by_discord_id(discord_id)
            view.selected_player = player_data

            await interaction.response.send_message(
                f"✅ Selected player: <@{discord_id}> (EOS: `{player_data.get('eos_id', 'Unknown')}`)",
                ephemeral=True,
            )


class ManualCreaturePlayerEntryModal(Modal, title="Manual Player Entry"):
    """Modal for entering player ID/name manually."""

    player_id = TextInput(
        label="Player ID or Name",
        placeholder="Steam ID, EOS ID, or character name...",
        required=True,
        max_length=100,
    )

    def __init__(self, parent_view: GiveCreatureView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.selected_player = {"manual": self.player_id.value}
        await interaction.response.send_message(
            f"✅ Selected player: `{self.player_id.value}`", ephemeral=True
        )


class CreatureSearchButton(Button):
    """Button to search for creatures."""

    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Search Creatures",
            emoji="🦖",
            custom_id="creature_search",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CreatureSearchModal(self.view))


class CreatureSearchModal(Modal, title="Search for Creatures"):
    """Modal for searching creatures."""

    search_term = TextInput(
        label="Creature Name",
        placeholder="e.g., Rex, Raptor, Giga, etc.",
        required=True,
        max_length=100,
    )

    def __init__(self, parent_view: GiveCreatureView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        query = self.search_term.value

        # Search arkids.net
        arkids_client = get_arkids_client()
        creatures = await arkids_client.search_creatures(query, limit=25)

        if not creatures:
            await interaction.followup.send(
                f"❌ No creatures found matching '{query}'", ephemeral=True
            )
            return

        # Show results
        view = CreatureResultsView(self.parent_view, creatures, query)
        embed = discord.Embed(
            title=f"🔍 Search Results: {query}",
            description=f"Found {len(creatures)} creatures",
            color=discord.Color.green(),
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class CreatureResultsView(View):
    """View showing creature search results."""

    def __init__(
        self, parent_view: GiveCreatureView, creatures: list, query: str, timeout: int = 120
    ):
        super().__init__(timeout=timeout)
        self.parent_view = parent_view
        self.creatures = creatures
        self.query = query

        self.add_item(CreatureResultsDropdown(creatures))



class CreatureResultsDropdown(Select):
    """Dropdown showing creature search results."""

    def __init__(self, creatures: list):
        options = []
        for i, creature in enumerate(creatures[:25]):
            options.append(
                discord.SelectOption(
                    label=creature.name[:100],
                    description=creature.blueprint[:100],
                    value=str(i),
                    emoji="🦖",
                )
            )

        super().__init__(
            placeholder="Select a creature...", options=options, custom_id="creature_results"
        )
        self.creatures = creatures

    async def callback(self, interaction: discord.Interaction):
        view: CreatureResultsView = self.view
        idx = int(self.values[0])
        selected_creature = self.creatures[idx]

        view.parent_view.selected_creature = selected_creature

        await interaction.response.send_message(
            f"✅ Selected: **{selected_creature.name}**\n`{selected_creature.blueprint}`",
            ephemeral=True,
        )


class ConfirmCreatureButton(Button):
    """Button to confirm and spawn creature."""

    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Spawn Creature",
            emoji="✅",
            custom_id="confirm_creature",
        )

    async def callback(self, interaction: discord.Interaction):
        view: GiveCreatureView = self.view

        if not view.selected_player:
            await interaction.response.send_message(
                "❌ Please select a player first!", ephemeral=True
            )
            return

        if not view.selected_creature:
            await interaction.response.send_message(
                "❌ Please search and select a creature first!", ephemeral=True
            )
            return

        # Show level modal
        await interaction.response.send_modal(CreatureLevelModal(view))


class CreatureLevelModal(Modal, title="Creature Level"):
    """Modal for entering creature level."""

    level = TextInput(
        label="Dino Level",
        placeholder="Level (default: 150)",
        required=False,
        default="150",
        max_length=10,
    )

    def __init__(self, parent_view: GiveCreatureView):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        view = self.parent_view
        player = view.selected_player
        creature = view.selected_creature
        level = self.level.value or "150"

        # Determine player identifier
        if isinstance(player, dict) and "manual" in player:
            player_id = player["manual"]
        elif isinstance(player, dict) and "eos_id" in player:
            player_id = player["eos_id"]
        else:
            player_id = str(player)

        # Get blueprint
        blueprint = creature.blueprint if hasattr(creature, "blueprint") else str(creature)

        # Execute command - auto-detect server
        success, response, server_used = await self._spawn_creature_auto_server(
            player_id, blueprint, level, view.guild_id
        )

        embed = discord.Embed(
            title="🦖 Creature Spawned" if success else "❌ Spawn Failed",
            description=f"**Server:** {server_used if server_used else 'Unknown'}",
            color=discord.Color.green() if success else discord.Color.red(),
        )

        embed.add_field(name="Player", value=player_id, inline=True)
        embed.add_field(
            name="Creature",
            value=creature.name if hasattr(creature, "name") else blueprint,
            inline=True,
        )
        embed.add_field(name="Level", value=level, inline=True)

        if len(response) > 1024:
            response = response[:1021] + "..."
        embed.add_field(name="Response", value=f"```{response}```", inline=False)
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _spawn_creature_auto_server(
        self, player_id: str, blueprint: str, level: str, guild_id: int
    ) -> tuple:
        """Spawn creature for player, auto-detecting which server they're on."""
        try:
            servers = await get_ark_servers(guild_id)
            if not servers:
                servers = Config.ARK_SERVERS

            rcon_manager = RCONManager(servers)

            # Try to find player on a server
            player_found = False
            for server in servers:
                try:
                    success, players_response = await rcon_manager.execute_command(
                        server["name"], "ListPlayers"
                    )

                    if success and player_id.lower() in players_response.lower():
                        player_found = True
                        # Spawn creature on this server
                        command = f"SpawnDino {player_id} {blueprint} {level}"
                        success, response = await rcon_manager.execute_command(
                            server["name"], command
                        )
                        return success, response, server["name"]
                except:
                    continue

            if not player_found:
                return False, f"Player '{player_id}' not found on any server", None

            return False, "Failed to spawn creature", None
        except Exception as e:
            return False, str(e), None


class UpdateServerModal(Modal, title="Update Server(s) via SteamCMD"):
    """Modal for selecting which server(s) to update via SteamCMD."""

    target = TextInput(
        label="Update Which? (single/all)",
        placeholder="'single' = this server only, 'all' = all servers alphabetically",
        required=False,
        default="single",
        max_length=10,
    )
    validate = TextInput(
        label="Full Validation? (yes/no)",
        placeholder="yes = validate all files (slower), no = quick update",
        required=False,
        default="no",
        max_length=10,
    )

    def __init__(self, server: dict, admin_logger=None):
        super().__init__()
        self.server = server
        self.admin_logger = admin_logger

    async def on_submit(self, interaction: discord.Interaction):
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"UpdateServerModal submitted by {interaction.user.display_name}")
        
        await interaction.response.defer(ephemeral=True)
        logger.info("Interaction deferred")

        target = self.target.value.lower().strip()
        validate = self.validate.value.lower().strip() in ["yes", "true", "1", "y"]
        update_all = target in ["all", "every", "*"]
        
        logger.info(f"Update parameters: target={target}, validate={validate}, update_all={update_all}")
        logger.info(f"DEBUG: interaction.guild_id={interaction.guild_id}, Config.DISCORD_GUILD_ID={Config.DISCORD_GUILD_ID}")

        try:
            from bot.database import server_config_db

            # Get server list
            if update_all:
                servers = await self._get_server_list(interaction.guild_id)
                logger.info(f"DEBUG: _get_server_list returned {len(servers) if servers else 0} servers for guild_id={interaction.guild_id}")
                if not servers:
                    await interaction.followup.send(
                        "❌ No servers configured in this guild.", ephemeral=True
                    )
                    return

                # Sort alphabetically by server name
                servers = sorted(servers, key=lambda s: s["name"])
            else:
                servers = [self.server]

            # Send initial status
            embed = discord.Embed(
                title="📥 Server Update Queue Started",
                description=f"Updating {len(servers)} server(s) sequentially",
                color=discord.Color.blue(),
            )
            embed.add_field(name="Mode", value="🔍 Full Validation" if validate else "⚡ Quick Update", inline=True)
            embed.add_field(name="Servers", value=", ".join([s["name"] for s in servers]), inline=False)
            embed.set_footer(text=f"Initiated by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed, ephemeral=True)

            # Log admin action
            if self.admin_logger:
                try:
                    log_id = await self.admin_logger.log_action(
                        action_type="update_server_steamcmd",
                        admin_id=interaction.user.id,
                        admin_name=interaction.user.display_name,
                        server_name="Multiple" if update_all else self.server.get("name", "Unknown"),
                        details=f"Mode: {'Validation' if validate else 'Quick'}, Servers: {len(servers)}",
                        interaction=interaction,
                    )
                except Exception as e:
                    logger.error(f"Failed to log admin action: {e}")
                    log_id = None
            else:
                log_id = None

            # Use the centralized update process function
            logger.info(f"Calling start_update_process with {len(servers)} servers")
            await start_update_process(interaction, servers, validate)

        except Exception as e:
            logger.error(f"Update modal error: {type(e).__name__}: {str(e)}", exc_info=True)
            embed = discord.Embed(
                title="❌ Update Error",
                color=discord.Color.red(),
            )
            embed.add_field(name="Error", value=f"```{str(e)}```", inline=False)
            embed.set_footer(text=f"Attempted by {interaction.user.display_name}")

    async def _get_server_list(self, guild_id: int) -> list:
        """Get sorted list of servers from database or config."""
        logger = logging.getLogger(__name__)
        logger.info(f"_get_server_list called with guild_id={guild_id}")
        
        try:
            from bot.database import server_config_db

            servers = await server_config_db.get_ark_servers(guild_id)
            logger.info(f"_get_server_list: Database returned {len(servers) if servers else 0} servers")
            if servers:
                logger.info(f"_get_server_list: Servers from DB: {[s.get('name') for s in servers]}")
                return servers
            else:
                logger.warning(f"_get_server_list: Database returned empty list for guild_id={guild_id}")
        except Exception as e:
            logger.error(f"_get_server_list: Exception from database: {e}", exc_info=True)
            pass

        # Fallback to Config.ARK_SERVERS
        from bot.config import Config
        logger.warning(f"_get_server_list: Falling back to Config.ARK_SERVERS")
        return Config.ARK_SERVERS or []


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(ServerManagementGUI(bot))
