"""
Server Management Console - /servermgmt command.

Hierarchical button-panel UI matching the PowerShell bot's server management console.
All navigation uses edit-in-place (editing the single ephemeral message) to preserve
server context and keep everything ephemeral.

Update flow matches the PowerShell bot's Invoke-ServerMaintenance:
  countdown warnings -> saveworld -> doexit -> stop service -> steamcmd -> start service
"""

import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput, Select
from discord import Embed, Interaction
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict

from bot.database.server_config_db import get_ark_servers, get_server_config
from bot.rcon.simple_client import SimpleRCONClient
from bot.utils.subscription_checker import check_feature

logger = logging.getLogger(__name__)

# ARK: Survival Ascended Steam App ID (hardcoded - ASA specific)
ASA_APP_ID = 2430930


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_server_options(servers: List[Dict]) -> List[discord.SelectOption]:
    """Create Discord select options from server list."""
    options: List[discord.SelectOption] = []
    for server in servers:
        if not isinstance(server, dict):
            continue

        raw_display = (server.get("display_name") or "").strip()
        raw_name = (server.get("name") or "").strip()

        label = raw_display or raw_name
        if not label:
            label = f"Server #{server.get('id', '?')}"
        label = label[:100]

        value = raw_name or raw_display or str(server.get("id", label))
        if not value:
            continue

        host = (server.get("host") or "Unknown Host").strip() or "Unknown Host"
        map_name = (server.get("map_name") or "").strip() or "Not set"
        description = f"Host: {host} | Map: {map_name}"[:100]

        options.append(
            discord.SelectOption(label=label, value=value, description=description)
        )
    return options


def _server_label(server: Dict) -> str:
    """Display-friendly server name."""
    return (
        (server.get("display_name") or "").strip()
        or (server.get("name") or "").strip()
        or f"Server #{server.get('id', '?')}"
    )


async def _get_server_by_identifier(
    guild_id: int, identifier: str, servers: List[Dict] = None
) -> Optional[Dict]:
    """Find a server by name, display_name, or id."""
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    data = servers if servers is not None else await get_ark_servers(guild_id)
    for server in data:
        if not isinstance(server, dict):
            continue
        name = (server.get("name") or "").strip()
        display = (server.get("display_name") or "").strip()
        sid = str(server.get("id")) if server.get("id") is not None else ""
        if identifier in {name, display, sid}:
            return server
    return None


async def _find_agent_for_guild(bot: commands.Bot, guild_id: int) -> Optional[str]:
    """Return the first connected agent_id for a guild, or None."""
    if not hasattr(bot, "agent_manager") or not bot.agent_manager:
        return None
    return await bot.agent_manager.get_connected_agent_for_guild(guild_id)


_job_id_counter = 0
_maintenance_jobs: Dict[str, dict] = {}  # job_id -> job dict (in-memory store)


def _next_job_id() -> int:
    global _job_id_counter
    _job_id_counter += 1
    return _job_id_counter


def _create_job(service_name: str, mode: str, validate: str, countdown: int, initiator: str) -> dict:
    """Create and register an in-memory maintenance job."""
    job_id = str(_next_job_id())
    job = {
        "id": job_id,
        "service_name": service_name,
        "mode": mode,
        "validate": validate,
        "countdown": countdown,
        "initiator": initiator,
        "status": "Running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "result_success": None,
        "result_message": None,
    }
    _maintenance_jobs[job_id] = job
    return job


def _complete_job(job: dict, success: bool, message: str):
    """Mark a job as completed or failed."""
    job["status"] = "Completed" if success else "Failed"
    job["result_success"] = success
    job["result_message"] = message
    job["completed_at"] = datetime.now(timezone.utc).isoformat()


async def _get_log_channel(bot: commands.Bot, guild_id: int):
    """Return the guild's configured server log channel, or None with warning."""
    try:
        config = await get_server_config(guild_id)
        if not config:
            logger.warning(f"No config found for guild {guild_id}")
            return None
        channel_id = config.get("server_log_channel_id")
        if not channel_id:
            logger.warning(f"server_log_channel_id not configured for guild {guild_id}")
            return None
        channel = bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Server log channel {channel_id} not found for guild {guild_id}")
            return None
        return channel
    except Exception as e:
        logger.error(f"Failed to get server log channel: {e}")
        return None


async def _send_to_log_channel(bot: commands.Bot, guild_id: int, embed: Embed):
    """Send an embed to the guild's configured log channel (best-effort)."""
    try:
        channel = await _get_log_channel(bot, guild_id)
        if channel:
            await channel.send(embed=embed)
    except Exception as e:
        logger.debug("Could not send embed to log channel: %s", e)


async def _log_text(bot: commands.Bot, guild_id: int, text: str):
    """Send a plain-text message to the guild's configured log channel (best-effort)."""
    try:
        channel = await _get_log_channel(bot, guild_id)
        if channel:
            await channel.send(text)
    except Exception as e:
        logger.debug("Could not send text to log channel: %s", e)


# ---------------------------------------------------------------------------
# Embed builders
# ---------------------------------------------------------------------------

def _main_panel_embed(server_count: int) -> Embed:
    embed = Embed(
        title="\U0001f5a5\ufe0f Server Management",
        description=(
            "Manage your ARK servers with ease.\n\n"
            f"Available Servers: {server_count}\n\n"
            "Select a server from the dropdown below..."
        ),
        color=discord.Color.blue(),
    )
    return embed


def _category_panel_embed(server: Dict) -> Embed:
    display = _server_label(server)
    service = server.get("service_name") or "N/A"
    hosting = server.get("hosting_type") or "Self-Hosted"
    if hosting == "self_hosted":
        hosting = "Self-Hosted"
    embed = Embed(
        title="\U0001f4cb Select Category",
        description=(
            f"**Server:** {display}\n"
            f"**Service:** `{service}`\n"
            f"**Hosting:** {hosting}\n\n"
            "Select a category below:"
        ),
        color=discord.Color.blue(),
    )
    return embed


def _server_ops_embed(server: Dict) -> Embed:
    display = _server_label(server)
    return Embed(
        title="\U0001f5a5\ufe0f Server Operations",
        description=f"**Server:** {display}\n\nSelect a server operation:",
        color=discord.Color.blue(),
    )


def _server_control_embed(server: Dict) -> Embed:
    display = _server_label(server)
    return Embed(
        title="\u2699\ufe0f Server Control",
        description=f"**Server:** {display}\n\nControl server lifecycle:",
        color=discord.Color.orange(),
    )


def _advanced_embed(server: Dict) -> Embed:
    display = _server_label(server)
    return Embed(
        title="\U0001f527 Advanced Tools",
        description=f"**Server:** {display}\n\nAccess advanced server tools:",
        color=discord.Color.purple(),
    )


def _diagnostics_embed(server: Dict) -> Embed:
    display = _server_label(server)
    return Embed(
        title="\U0001f50d Diagnostics",
        description=f"**Server:** {display}\n\nDiagnostic tools:",
        color=discord.Color.greyple(),
    )


def _updates_embed(servers: List[Dict]) -> Embed:
    return Embed(
        title="\U0001f4e5 Server Updates",
        description=(
            "Select servers to update, choose validation mode, and set countdown timer.\n\n"
            f"Available Servers: {len(servers)}"
        ),
        color=discord.Color.blue(),
    )


# ---------------------------------------------------------------------------
# Level 1 - Main Panel
# ---------------------------------------------------------------------------

class ServerManagementView(View):
    """Main panel: Updates button + server dropdown."""

    def __init__(self, guild_id: int, bot: commands.Bot, servers: List[Dict]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.bot = bot
        self.servers = servers
        self._message_ref = None  # Store message reference for auto-refresh

        updates_btn = Button(
            label="\U0001f4e5 Updates", style=discord.ButtonStyle.primary,
            custom_id="servermgmt_updates", row=0,
        )
        updates_btn.callback = self._updates_callback
        self.add_item(updates_btn)

        options = _build_server_options(servers)
        if options:
            select = Select(placeholder="Select a server...", options=options[:25], row=1)
            select.callback = self._server_select_callback
            self.add_item(select)
        
        # Subscribe to server change events
        from bot.utils.server_events import server_events
        server_events.subscribe(guild_id, self._on_servers_changed)

    async def _updates_callback(self, interaction: Interaction):
        view = ServerUpdatesView(self.guild_id, self.bot, self.servers)
        await interaction.response.edit_message(embed=_updates_embed(self.servers), view=view)

    async def _server_select_callback(self, interaction: Interaction):
        values = interaction.data.get("values", [])
        if not values:
            return
        server = await _get_server_by_identifier(self.guild_id, values[0], self.servers)
        if not server:
            await interaction.response.edit_message(
                embed=Embed(title="Error", description="Server not found.", color=discord.Color.red()),
                view=self,
            )
            return
        view = ServerSelectedView(self.guild_id, self.bot, server, self.servers)
        await interaction.response.edit_message(embed=_category_panel_embed(server), view=view)

    async def _on_servers_changed(self):
        """Called when servers are changed - auto-refresh the view."""
        try:
            # Store message reference if not already set
            if not self._message_ref and hasattr(self, 'message'):
                self._message_ref = self.message
            
            # Refresh server list
            self.servers = await get_ark_servers(self.guild_id)
            
            # Rebuild view components
            self.clear_items()
            
            # Re-add updates button
            updates_btn = Button(
                label="\U0001f4e5 Updates", style=discord.ButtonStyle.primary,
                custom_id="servermgmt_updates", row=0,
            )
            updates_btn.callback = self._updates_callback
            self.add_item(updates_btn)
            
            # Rebuild dropdown with fresh server list
            options = _build_server_options(self.servers)
            if options:
                select = Select(placeholder="Select a server...", options=options[:25], row=1)
                select.callback = self._server_select_callback
                self.add_item(select)
            
            # Update the message if we have a reference
            if self._message_ref:
                try:
                    await self._message_ref.edit(embed=_main_panel_embed(len(self.servers)), view=self)
                except Exception as e:
                    logger.warning(f"Failed to auto-refresh server management view: {e}")
        except Exception as e:
            logger.error(f"Error in auto-refresh: {e}")

    def on_timeout(self):
        """Cleanup when view times out."""
        from bot.utils.server_events import server_events
        server_events.unsubscribe(self.guild_id, self._on_servers_changed)
        super().on_timeout()

    def stop(self):
        """Cleanup when view is stopped."""
        from bot.utils.server_events import server_events
        server_events.unsubscribe(self.guild_id, self._on_servers_changed)
        super().stop()


# ---------------------------------------------------------------------------
# Level 2 - Category Panel
# ---------------------------------------------------------------------------

class ServerSelectedView(View):
    """Category selection after a server is chosen."""

    def __init__(self, guild_id: int, bot: commands.Bot, server: Dict, servers: List[Dict]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.bot = bot
        self.server = server
        self.servers = servers

    @discord.ui.button(label="\U0001f5a5\ufe0f Server Ops", style=discord.ButtonStyle.primary, row=0)
    async def server_ops_button(self, interaction: Interaction, button: Button):
        view = ServerOperationsView(self.guild_id, self.bot, self.server, self.servers)
        await interaction.response.edit_message(embed=_server_ops_embed(self.server), view=view)

    @discord.ui.button(label="\u2699\ufe0f Server Control", style=discord.ButtonStyle.primary, row=0)
    async def server_control_button(self, interaction: Interaction, button: Button):
        view = ServerControlView(self.guild_id, self.bot, self.server, self.servers)
        await interaction.response.edit_message(embed=_server_control_embed(self.server), view=view)

    @discord.ui.button(label="\U0001f527 Advanced", style=discord.ButtonStyle.primary, row=1)
    async def advanced_button(self, interaction: Interaction, button: Button):
        view = AdvancedToolsView(self.guild_id, self.bot, self.server, self.servers)
        await interaction.response.edit_message(embed=_advanced_embed(self.server), view=view)

    @discord.ui.button(label="\U0001f50d Diagnostics", style=discord.ButtonStyle.primary, row=1)
    async def diagnostics_button(self, interaction: Interaction, button: Button):
        view = DiagnosticsView(self.guild_id, self.bot, self.server, self.servers)
        await interaction.response.edit_message(embed=_diagnostics_embed(self.server), view=view)

    @discord.ui.button(label="\u00ab Back", style=discord.ButtonStyle.primary, row=2)
    async def back_button(self, interaction: Interaction, button: Button):
        servers = await get_ark_servers(self.guild_id)
        view = ServerManagementView(self.guild_id, self.bot, servers)
        await interaction.response.edit_message(embed=_main_panel_embed(len(servers)), view=view)


# ---------------------------------------------------------------------------
# Level 3A - Server Operations
# ---------------------------------------------------------------------------

class ServerOperationsView(View):
    """Broadcast, Save World, Destroy Wild Dinos, Set MOTD, Back."""

    def __init__(self, guild_id: int, bot: commands.Bot, server: Dict, servers: List[Dict]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.bot = bot
        self.server = server
        self.servers = servers

    @discord.ui.button(label="\U0001f4e2 Broadcast", style=discord.ButtonStyle.primary, row=0)
    async def broadcast_button(self, interaction: Interaction, button: Button):
        modal = BroadcastModal(self.server)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="\U0001f4be Save World", style=discord.ButtonStyle.success, row=0)
    async def saveworld_button(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        display = _server_label(self.server)
        try:
            async with SimpleRCONClient(
                host=self.server["host"], port=self.server["rcon_port"],
                password=self.server["rcon_password"], timeout=5.0,
            ) as rcon:
                await rcon.execute("saveworld")
            await interaction.followup.send(f"\U0001f4be World saved for **{display}**", ephemeral=True)
        except Exception as e:
            logger.error("Save world error for %s: %s", display, e)
            await interaction.followup.send(f"\u274c Failed to save world for **{display}**: {e}", ephemeral=True)

    @discord.ui.button(label="\U0001f996 Destroy Wild", style=discord.ButtonStyle.danger, row=1)
    async def destroywild_button(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        display = _server_label(self.server)
        try:
            async with SimpleRCONClient(
                host=self.server["host"], port=self.server["rcon_port"],
                password=self.server["rcon_password"], timeout=10.0,
            ) as rcon:
                await rcon.execute("destroywilddinos")
            await interaction.followup.send(f"\U0001f996 Wild dinos destroyed on **{display}**", ephemeral=True)
        except Exception as e:
            logger.error("Destroy wild dinos error for %s: %s", display, e)
            await interaction.followup.send(f"\u274c Failed: {e}", ephemeral=True)

    @discord.ui.button(label="\U0001f4dd Set MOTD", style=discord.ButtonStyle.secondary, row=1)
    async def setmotd_button(self, interaction: Interaction, button: Button):
        modal = MOTDModal(self.server)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="\u00ab Back", style=discord.ButtonStyle.primary, row=2)
    async def back_button(self, interaction: Interaction, button: Button):
        view = ServerSelectedView(self.guild_id, self.bot, self.server, self.servers)
        await interaction.response.edit_message(embed=_category_panel_embed(self.server), view=view)


# ---------------------------------------------------------------------------
# Level 3B - Server Control
# ---------------------------------------------------------------------------

class ServerControlView(View):
    """Stop, Start, Restart, Status, Back - uses lifecycle manager for hooks."""

    def __init__(self, guild_id: int, bot: commands.Bot, server: Dict, servers: List[Dict]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.bot = bot
        self.server = server
        self.servers = servers

    async def _get_agent_id(self) -> Optional[str]:
        return await _find_agent_for_guild(self.bot, self.guild_id)

    async def _saveworld(self):
        try:
            async with SimpleRCONClient(
                host=self.server["host"], port=self.server["rcon_port"],
                password=self.server["rcon_password"], timeout=10.0,
            ) as rcon:
                await rcon.execute("saveworld")
            logger.info("Saveworld sent to %s", _server_label(self.server))
        except Exception as e:
            logger.warning("Saveworld failed for %s: %s", _server_label(self.server), e)

    async def _apply_pending_changes(self) -> int:
        from bot.utils.lifecycle_manager import apply_pending_ini_changes
        return await apply_pending_ini_changes(
            self.guild_id, 
            self.server.get("name", ""), 
            self.bot.agent_manager
        )

    async def _log_to_channel(self, message: str):
        await _log_text(self.bot, self.guild_id, message)

    @discord.ui.button(label="\u23f9\ufe0f Stop", style=discord.ButtonStyle.danger, row=0)
    async def stop_button(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        display = _server_label(self.server)
        server_name = self.server.get("name", "")
        
        agent_id = await self._get_agent_id()
        if not agent_id:
            await interaction.followup.send(
                "\u274c Remote agent not available. Server control requires a connected remote agent.",
                ephemeral=True,
            )
            return

        await self._log_to_channel(f"[Server Control] Stopping {display}...")
        await self._saveworld()
        await asyncio.sleep(2)
        
        result = await self.bot.agent_manager.send_command(
            agent_id, "stop_server", server_name, timeout=60
        )
        
        if result.get("type") == "error":
            await self._log_to_channel(f"[Server Control] Failed to stop {display}: {result.get('error')}")
            await interaction.followup.send(f"\u274c Failed to stop **{display}**: {result.get('error')}", ephemeral=True)
            return
        
        await asyncio.sleep(5)
        
        pending_count = await self._apply_pending_changes()
        
        if pending_count > 0:
            from bot.database import ini_settings_db
            changes = await ini_settings_db.get_pending_changes(self.guild_id, server_name)
            change_details = []
            for c in changes:
                key = c.get("key_name", "?")
                old_val = c.get("old_value", "")
                new_val = c.get("new_value", "")
                change_details.append(f"  - {key}: {old_val} -> {new_val}")
            await self._log_to_channel(f"[Server Control] Applied {pending_count} INI change(s) for {display}:\n" + "\n".join(change_details))
            await interaction.followup.send(
                f"\u23f9\ufe0f Server **{display}** stopped.\n\u2705 Applied {pending_count} pending INI change(s).",
                ephemeral=True,
            )
        else:
            await self._log_to_channel(f"[Server Control] {display} stopped.")
            await interaction.followup.send(f"\u23f9\ufe0f Server **{display}** stopped.", ephemeral=True)

    @discord.ui.button(label="\u25b6\ufe0f Start", style=discord.ButtonStyle.success, row=0)
    async def start_button(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        display = _server_label(self.server)
        server_name = self.server.get("name", "")
        
        agent_id = await self._get_agent_id()
        if not agent_id:
            await interaction.followup.send(
                "\u274c Remote agent not available. Server control requires a connected remote agent.",
                ephemeral=True,
            )
            return

        await self._log_to_channel(f"[Server Control] Starting {display}...")
        
        result = await self.bot.agent_manager.send_command(
            agent_id, "start_server", server_name, timeout=120
        )
        
        if result.get("type") == "error":
            await self._log_to_channel(f"[Server Control] Failed to start {display}: {result.get('error')}")
            await interaction.followup.send(f"\u274c Failed to start **{display}**: {result.get('error')}", ephemeral=True)
        else:
            await self._log_to_channel(f"[Server Control] {display} started.")
            await interaction.followup.send(f"\u25b6\ufe0f Server **{display}** started.", ephemeral=True)

    @discord.ui.button(label="\U0001f504 Restart", style=discord.ButtonStyle.primary, row=1)
    async def restart_button(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        display = _server_label(self.server)
        server_name = self.server.get("name", "")
        
        agent_id = await self._get_agent_id()
        if not agent_id:
            await interaction.followup.send(
                "\u274c Remote agent not available. Server control requires a connected remote agent.",
                ephemeral=True,
            )
            return

        await self._log_to_channel(f"[Server Control] Restarting {display}...")
        await self._saveworld()
        await asyncio.sleep(2)
        
        stop_result = await self.bot.agent_manager.send_command(
            agent_id, "stop_server", server_name, timeout=60
        )
        
        if stop_result.get("type") == "error":
            await self._log_to_channel(f"[Server Control] Failed to stop {display}: {stop_result.get('error')}")
            await interaction.followup.send(f"\u274c Failed to stop **{display}**: {stop_result.get('error')}", ephemeral=True)
            return
        
        await asyncio.sleep(5)
        
        pending_count = await self._apply_pending_changes()
        
        if pending_count > 0:
            from bot.database import ini_settings_db
            changes = await ini_settings_db.get_pending_changes(self.guild_id, server_name)
            change_details = []
            for c in changes:
                key = c.get("key_name", "?")
                old_val = c.get("old_value", "")
                new_val = c.get("new_value", "")
                change_details.append(f"  - {key}: {old_val} -> {new_val}")
            await self._log_to_channel(f"[Server Control] Applied {pending_count} INI change(s) for {display}:\n" + "\n".join(change_details))
        
        await asyncio.sleep(5)
        
        start_result = await self.bot.agent_manager.send_command(
            agent_id, "start_server", server_name, timeout=120
        )
        
        if start_result.get("type") == "error":
            msg = f"\u274c Server stopped but failed to start **{display}**: {start_result.get('error')}"
            if pending_count > 0:
                msg += f"\n\u2705 Applied {pending_count} pending INI change(s)."
            await self._log_to_channel(f"[Server Control] {display} stopped but failed to start: {start_result.get('error')}")
            await interaction.followup.send(msg, ephemeral=True)
            return
        
        msg = f"\U0001f504 Server **{display}** restarted."
        if pending_count > 0:
            msg += f"\n\u2705 Applied {pending_count} pending INI change(s)."
        await self._log_to_channel(f"[Server Control] {display} restarted successfully.")
        await interaction.followup.send(msg, ephemeral=True)

    @discord.ui.button(label="\U0001f4ca Status", style=discord.ButtonStyle.secondary, row=2)
    async def status_button(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        display = _server_label(self.server)
        server_name = self.server.get("name", "")
        
        agent_id = await self._get_agent_id()
        if not agent_id:
            await interaction.followup.send(
                "\u274c Remote agent not available.",
                ephemeral=True,
            )
            return
        
        result = await self.bot.agent_manager.send_command(
            agent_id, "get_status", server_name, timeout=15
        )
        
        if result.get("type") == "error":
            await interaction.followup.send(f"\u274c Failed to get status: {result.get('error')}", ephemeral=True)
            return
        
        status_data = result.get("data", {})
        embed = Embed(title=f"\U0001f4ca Server Status - {display}", color=discord.Color.blue())
        if isinstance(status_data, dict):
            for key in ("service_state", "online", "ark_version", "rcon_port", "map_name", "path_exists"):
                val = status_data.get(key)
                if val is not None:
                    embed.add_field(name=key.replace("_", " ").title(), value=str(val), inline=True)
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="\u00ab Back", style=discord.ButtonStyle.primary, row=3)
    async def back_button(self, interaction: Interaction, button: Button):
        view = ServerSelectedView(self.guild_id, self.bot, self.server, self.servers)
        await interaction.response.edit_message(embed=_category_panel_embed(self.server), view=view)


# ---------------------------------------------------------------------------
# Level 3C - Advanced Tools
# ---------------------------------------------------------------------------

class AdvancedToolsView(View):
    """Custom RCON, Chat Log, Back."""

    def __init__(self, guild_id: int, bot: commands.Bot, server: Dict, servers: List[Dict]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.bot = bot
        self.server = server
        self.servers = servers

    @discord.ui.button(label="\u2328\ufe0f Custom RCON", style=discord.ButtonStyle.secondary, row=0)
    async def customrcon_button(self, interaction: Interaction, button: Button):
        modal = CustomRCONModal(self.server)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="\U0001f4ac Chat Log", style=discord.ButtonStyle.secondary, row=1)
    async def chatlog_button(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        display = _server_label(self.server)
        try:
            async with SimpleRCONClient(
                host=self.server["host"], port=self.server["rcon_port"],
                password=self.server["rcon_password"], timeout=10.0,
            ) as rcon:
                result = await rcon.execute("GetChat")
            if result and result.strip():
                lines = result.strip().split("\n")
                formatted = [f"`{l.strip()}`" for l in lines[-20:] if l.strip()]
                if formatted:
                    text = "\n".join(formatted)
                    if len(text) > 1900:
                        text = text[:1900] + "..."
                    embed = Embed(title=f"\U0001f4ac Chat Log - {display}", description=text, color=discord.Color.blue())
                    embed.timestamp = discord.utils.utcnow()
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
            await interaction.followup.send(f"No chat log available for **{display}**", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"\u274c Error: {e}", ephemeral=True)

    @discord.ui.button(label="\u00ab Back", style=discord.ButtonStyle.primary, row=2)
    async def back_button(self, interaction: Interaction, button: Button):
        view = ServerSelectedView(self.guild_id, self.bot, self.server, self.servers)
        await interaction.response.edit_message(embed=_category_panel_embed(self.server), view=view)


# ---------------------------------------------------------------------------
# Log Pagination View
# ---------------------------------------------------------------------------

class LogPaginationView(View):
    """Paginated log viewer with First / Previous / Next / Last navigation."""

    PAGE_SIZE = 30

    def __init__(self, lines: list, title: str, total_lines: int = 0):
        super().__init__(timeout=None)
        self.lines = lines
        self.title = title
        self.total_lines = total_lines or len(lines)
        self.page = 0
        self.total_pages = max(1, (len(lines) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._update_buttons()

    def _update_buttons(self):
        self.first_button.disabled = self.page == 0
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1
        self.last_button.disabled = self.page >= self.total_pages - 1

    def _build_embed(self) -> Embed:
        start = self.page * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        text = "\n".join(self.lines[start:end])
        if len(text) > 1900:
            text = text[-1900:]
        embed = Embed(
            title=f"{self.title} | Page {self.page + 1}/{self.total_pages}",
            description=f"```\n{text}\n```",
            color=discord.Color.greyple(),
        )
        footer = f"Lines {start + 1}–{min(end, len(self.lines))} of {len(self.lines)} fetched"
        if self.total_lines > len(self.lines):
            footer += f" · {self.total_lines:,} total in log"
        embed.set_footer(text=footer)
        return embed

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def first_button(self, interaction: Interaction, button: Button):
        self.page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(self, interaction: Interaction, button: Button):
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: Interaction, button: Button):
        self.page = min(self.total_pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def last_button(self, interaction: Interaction, button: Button):
        self.page = self.total_pages - 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)


# ---------------------------------------------------------------------------
# View Log Modal
# ---------------------------------------------------------------------------

class ViewLogModal(Modal):
    """Modal for configuring log line count before fetching."""

    lines_input = TextInput(
        label="Number of lines to fetch (10–1000)",
        placeholder="300",
        default="300",
        required=False,
        max_length=4,
    )

    def __init__(self, diagnostics_view: "DiagnosticsView"):
        super().__init__(title="📄 View Server Log")
        self.diagnostics_view = diagnostics_view

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            count = int(self.lines_input.value or "300")
            count = max(10, min(1000, count))
        except ValueError:
            count = 300

        display = _server_label(self.diagnostics_view.server)
        result = await self.diagnostics_view._fetch_logs(interaction, {"lines": count})
        if result is None:
            return
        if result.get("type") == "error":
            await interaction.followup.send(f"\u274c {result.get('error')}", ephemeral=True)
            return
        lines = result.get("data", {}).get("lines", [])
        total_lines = result.get("data", {}).get("total_lines", len(lines))
        if not lines:
            await interaction.followup.send(f"No log data for **{display}**", ephemeral=True)
            return
        view = LogPaginationView(lines, f"\U0001f4c4 Server Log - {display}", total_lines=total_lines)
        await interaction.followup.send(embed=view._build_embed(), view=view, ephemeral=True)


# ---------------------------------------------------------------------------
# Level 3D - Diagnostics
# ---------------------------------------------------------------------------

class DiagnosticsView(View):
    """View Log, View Errors, Crash History, Back."""

    def __init__(self, guild_id: int, bot: commands.Bot, server: Dict, servers: List[Dict]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.bot = bot
        self.server = server
        self.servers = servers

    async def _fetch_logs(self, interaction: Interaction, params: Dict = None):
        agent_id = await _find_agent_for_guild(self.bot, self.guild_id)
        if not agent_id:
            await interaction.followup.send("\u274c Remote agent not available.", ephemeral=True)
            return None
        try:
            return await self.bot.agent_manager.send_command(
                agent_id, "view_logs", self.server.get("name", ""),
                params=params or {}, timeout=15,
            )
        except Exception as e:
            await interaction.followup.send(f"\u274c Error fetching logs: {e}", ephemeral=True)
            return None

    @discord.ui.button(label="\U0001f4c4 View Log", style=discord.ButtonStyle.secondary, row=0)
    async def viewlog_button(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(ViewLogModal(self))

    @discord.ui.button(label="\u26a0\ufe0f View Errors", style=discord.ButtonStyle.danger, row=0)
    async def viewerrors_button(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        display = _server_label(self.server)
        result = await self._fetch_logs(interaction, {"lines": 200})
        if result is None:
            return
        if result.get("type") == "error":
            await interaction.followup.send(f"\u274c {result.get('error')}", ephemeral=True)
            return
        lines = result.get("data", {}).get("lines", [])
        error_lines = [l for l in lines if any(k in l.lower() for k in ("error", "fatal", "exception"))]
        if error_lines:
            text = "\n".join(error_lines[-20:])
            if len(text) > 1900:
                text = text[-1900:]
            embed = Embed(title=f"\u26a0\ufe0f Errors - {display}", description=f"```\n{text}\n```", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"No errors found for **{display}**", ephemeral=True)

    @discord.ui.button(label="\U0001f4a5 Crash History", style=discord.ButtonStyle.secondary, row=1)
    async def crashhistory_button(self, interaction: Interaction, button: Button):
        await interaction.response.defer()
        display = _server_label(self.server)
        result = await self._fetch_logs(interaction, {"lines": 500})
        if result is None:
            return
        if result.get("type") == "error":
            await interaction.followup.send(f"\u274c {result.get('error')}", ephemeral=True)
            return
        lines = result.get("data", {}).get("lines", [])
        crash_lines = [l for l in lines if any(k in l.lower() for k in ("crash", "assert"))]
        if crash_lines:
            text = "\n".join(crash_lines[-15:])
            if len(text) > 1900:
                text = text[-1900:]
            embed = Embed(title=f"\U0001f4a5 Crash History - {display}", description=f"```\n{text}\n```", color=discord.Color.dark_red())
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(f"No crash events found for **{display}**", ephemeral=True)

    @discord.ui.button(label="\u00ab Back", style=discord.ButtonStyle.primary, row=2)
    async def back_button(self, interaction: Interaction, button: Button):
        view = ServerSelectedView(self.guild_id, self.bot, self.server, self.servers)
        await interaction.response.edit_message(embed=_category_panel_embed(self.server), view=view)


# ---------------------------------------------------------------------------
# Updates Panel
# ---------------------------------------------------------------------------

class ServerUpdatesView(View):
    """Server update panel: server multi-select, validation mode, countdown, start."""

    def __init__(self, guild_id: int, bot: commands.Bot, servers: List[Dict]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.bot = bot
        self.servers = servers
        self.selected_servers: List[str] = []
        self.validation_mode: str = "quick"
        self.countdown_seconds: int = 300  # default 5 minutes

        options = _build_server_options(servers)
        if options:
            server_select = Select(
                placeholder="Select servers to update (or leave blank for all)...",
                options=options[:25], min_values=1,
                max_values=min(len(options), 25), row=0,
            )
            server_select.callback = self._server_select_callback
            self.add_item(server_select)

        validation_select = Select(
            placeholder="Validation Mode: Quick",
            options=[
                discord.SelectOption(label="Quick Validation", value="quick", default=True),
                discord.SelectOption(label="Full Validation", value="full"),
                discord.SelectOption(label="No Validation", value="none"),
            ],
            row=1,
        )
        validation_select.callback = self._validation_callback
        self.add_item(validation_select)

        countdown_select = Select(
            placeholder="Countdown: 5 Minutes",
            options=[
                discord.SelectOption(label="No Countdown", value="0"),
                discord.SelectOption(label="1 Minute", value="60"),
                discord.SelectOption(label="5 Minutes", value="300", default=True),
                discord.SelectOption(label="10 Minutes", value="600"),
                discord.SelectOption(label="15 Minutes", value="900"),
            ],
            row=2,
        )
        countdown_select.callback = self._countdown_callback
        self.add_item(countdown_select)

    async def _server_select_callback(self, interaction: Interaction):
        self.selected_servers = interaction.data.get("values", [])
        await interaction.response.defer()

    async def _validation_callback(self, interaction: Interaction):
        values = interaction.data.get("values", [])
        if values:
            self.validation_mode = values[0]
        await interaction.response.defer()

    async def _countdown_callback(self, interaction: Interaction):
        values = interaction.data.get("values", [])
        if values:
            self.countdown_seconds = int(values[0])
        await interaction.response.defer()

    @discord.ui.button(label="\U0001f680 Start Update", style=discord.ButtonStyle.success, row=3)
    async def start_update_button(self, interaction: Interaction, button: Button):
        # Default to all servers if none explicitly selected (matches PS bot)
        if not self.selected_servers:
            self.selected_servers = [
                (s.get("name") or s.get("display_name") or str(s.get("id", "")))
                for s in self.servers if isinstance(s, dict)
            ]

        await interaction.response.defer()

        agent_id = await _find_agent_for_guild(self.bot, self.guild_id)
        if not agent_id:
            await interaction.followup.send(
                "\u274c No remote agent connected. Updates require a remote agent.", ephemeral=True
            )
            return

        # Resolve selected server dicts
        target_servers = []
        for name in sorted(self.selected_servers):
            srv = await _get_server_by_identifier(self.guild_id, name, self.servers)
            if srv:
                target_servers.append(srv)

        if not target_servers:
            await interaction.followup.send("\u274c Could not resolve selected servers.", ephemeral=True)
            return

        # Validate that all servers have steamcmd_path and server_path
        missing = []
        for srv in target_servers:
            if not srv.get("steamcmd_path") or not srv.get("server_path"):
                missing.append(_server_label(srv))
        if missing:
            await interaction.followup.send(
                f"\u274c Missing `steamcmd_path` or `server_path` in DB for: {', '.join(missing)}\n"
                "Use `/setup` to configure server directories first.",
                ephemeral=True,
            )
            return

        # Send initial confirmation
        server_names = ", ".join(_server_label(s) for s in target_servers)
        await interaction.followup.send(
            f"\U0001f680 Starting update for **{server_names}**\n"
            f"Countdown: {self.countdown_seconds}s | Validation: {self.validation_mode}",
            ephemeral=True,
        )

        # Log to server log channel
        await _send_to_log_channel(self.bot, self.guild_id, Embed(
            title="\U0001f4e5 Server Update Started",
            description=f"**Servers:** {server_names}\n**Countdown:** {self.countdown_seconds}s\n**Validation:** {self.validation_mode}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        ))

        # Run update as background task
        asyncio.create_task(
            self._run_update_sequence(interaction, agent_id, target_servers)
        )

    async def _run_update_sequence(self, interaction: Interaction, agent_id: str, target_servers: List[Dict]):
        """Full update sequence matching PowerShell bot's Invoke-ServerMaintenance."""
        results = []

        validate_str = (
            "without validate" if self.validation_mode == "none"
            else f"with {self.validation_mode} validate"
        )

        for srv in target_servers:
            display = _server_label(srv)
            server_name = srv.get("name", "")
            steamcmd_path = srv.get("steamcmd_path", "")
            server_path = srv.get("server_path", "")

            # Create maintenance job record
            job = _create_job(
                service_name=server_name,
                mode="update",
                validate=self.validation_mode,
                countdown=self.countdown_seconds,
                initiator=str(interaction.user),
            )
            job_id = job["id"]
            logger.info("Maintenance job #%s started for %s", job_id, server_name)

            try:
                # --- Step 1: RCON countdown warnings ---
                if self.countdown_seconds > 0:
                    await self._rcon_countdown(srv, self.countdown_seconds)

                # --- Step 2: Save world via RCON ---
                await _log_text(self.bot, self.guild_id,
                    f"Saving world on {server_name} before shutdown...")
                try:
                    async with SimpleRCONClient(
                        host=srv["host"], port=srv["rcon_port"],
                        password=srv["rcon_password"], timeout=10.0,
                    ) as rcon:
                        await rcon.execute("saveworld")
                    logger.info("Saveworld sent to %s", display)
                    await _log_text(self.bot, self.guild_id,
                        f"World saved on {server_name}")
                except Exception as e:
                    logger.warning("Saveworld failed for %s: %s", display, e)
                    await _log_text(self.bot, self.guild_id,
                        f"World save failed for {server_name}: {e} — continuing with shutdown")

                # --- Step 3: Graceful exit via RCON (doexit) ---
                try:
                    async with SimpleRCONClient(
                        host=srv["host"], port=srv["rcon_port"],
                        password=srv["rcon_password"], timeout=5.0,
                    ) as rcon:
                        await rcon.execute("doexit")
                    logger.info("DoExit sent to %s", display)
                except Exception:
                    pass  # Server may already be shutting down
                await _log_text(self.bot, self.guild_id,
                    f"Sent doexit to {server_name} for maintenance")

                # Brief pause — let the game process begin graceful shutdown
                # before the agent's sc stop hits it.
                await asyncio.sleep(5)

                # --- Steps 4-6: stop → update → start (atomic on agent) ---
                # The agent runs the full sequence and writes a persistent job log,
                # so it continues autonomously even if the bot disconnects mid-update.
                await _log_text(self.bot, self.guild_id,
                    f"Handing {server_name} to agent: stop \u2192 update \u2192 start "
                    f"({validate_str})")

                maintain_result = await self.bot.agent_manager.send_command(
                    agent_id, "maintain_server", server_name,
                    params={
                        "steamcmd_path": steamcmd_path,
                        "server_path": server_path,
                        "ark_appid": ASA_APP_ID,
                        "validate": self.validation_mode != "none",
                        "use_custom_script": True,
                    },
                    timeout=3600,  # 1 hour — agent handles stop + SteamCMD + start
                )

                # Handle response
                if isinstance(maintain_result, dict):
                    if maintain_result.get("type") == "error":
                        error_msg = maintain_result.get("error", "Unknown error")
                        await _log_text(self.bot, self.guild_id,
                            f"Maintenance for {server_name} FAILED: {error_msg}")
                        _complete_job(job, success=False, message=error_msg)
                        results.append(f"\u274c **{display}**: {error_msg}")
                        continue
                    data = maintain_result.get("data", {})
                    agent_job_id = data.get("job_id", "") if isinstance(data, dict) else ""
                    msg = data.get("message", "Completed") if isinstance(data, dict) else str(data)
                    log_line = f"Maintenance complete for {server_name}: {msg}"
                    if agent_job_id:
                        log_line += f" (agent job: {agent_job_id})"
                    await _log_text(self.bot, self.guild_id, log_line)
                else:
                    await _log_text(self.bot, self.guild_id,
                        f"Maintenance complete for {server_name}")

                _complete_job(job, success=True, message="Updated & restarted successfully")
                logger.info("Maintenance job #%s completed: %s - success", job_id, server_name)
                results.append(f"\u2705 **{display}**: Updated & restarted successfully")

            except Exception as e:
                logger.error("Update failed for %s: %s", display, e)
                _complete_job(job, success=False, message=str(e))
                await _log_text(self.bot, self.guild_id,
                    f"Maintenance Job #{job_id} FAILED: {server_name} - {e}")
                results.append(f"\u274c **{display}**: {e}")

        # --- Final Discord followup ---
        all_success = all("\u2705" in r for r in results)
        embed = Embed(
            title="\U0001f4e5 Update Results",
            description="\n".join(results) if results else "No results.",
            color=discord.Color.green() if all_success else discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )

        # Always post to log channel — interaction tokens expire after 15 min so
        # the followup below silently fails for long cluster updates.
        summary_lines = ["**📥 Update Results**"] + results
        await _log_text(self.bot, self.guild_id, "\n".join(summary_lines))

        # Best-effort ephemeral reply (works only if interaction token still valid)
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            pass  # Token expired — results already sent to log channel above

    async def _rcon_countdown(self, server: Dict, total_seconds: int):
        """Send RCON countdown warnings and log channel messages matching PS bot pattern."""
        server_name = server.get("name") or _server_label(server)

        await _log_text(self.bot, self.guild_id,
            f"Starting maintenance countdown for {server_name} (mode=update)")

        # Milestone warnings sent to RCON only (5 min, 3 min, 1 min, 30 sec)
        warnings = [
            (300, "\U0001f504 Server rebooting for updates in 5 MINUTES"),
            (180, "\U0001f504 Server rebooting for updates in 3 MINUTES"),
            (60, "\U0001f504 Server rebooting for updates in 1 MINUTE"),
            (30, "\U0001f504 Server rebooting for updates in 30 SECONDS"),
            (10, None),  # Triggers 10-second final countdown
        ]

        elapsed = 0
        for warn_at, message in warnings:
            if warn_at > total_seconds:
                continue

            wait_until = total_seconds - warn_at
            if wait_until > elapsed:
                await asyncio.sleep(wait_until - elapsed)
                elapsed = wait_until

            if message:
                try:
                    async with SimpleRCONClient(
                        host=server["host"], port=server["rcon_port"],
                        password=server["rcon_password"], timeout=3.0,
                    ) as rcon:
                        await rcon.execute(f"ServerChat {message}")
                    await _log_text(self.bot, self.guild_id, message)
                except Exception:
                    pass

            # 10-second final countdown — sent to both RCON and log channel
            if warn_at == 10:
                first_msg = "Server shutting down in 10 seconds!"
                try:
                    async with SimpleRCONClient(
                        host=server["host"], port=server["rcon_port"],
                        password=server["rcon_password"], timeout=2.0,
                    ) as rcon:
                        await rcon.execute(f"ServerChat {first_msg}")
                except Exception:
                    pass
                await _log_text(self.bot, self.guild_id, first_msg)

                for i in range(9, 0, -1):
                    countdown_msg = f"[Maintenance] Server shutting down for maintenance in {i} seconds!"
                    try:
                        async with SimpleRCONClient(
                            host=server["host"], port=server["rcon_port"],
                            password=server["rcon_password"], timeout=2.0,
                        ) as rcon:
                            await rcon.execute(f"ServerChat {countdown_msg}")
                    except Exception:
                        pass
                    await _log_text(self.bot, self.guild_id, countdown_msg)
                    await asyncio.sleep(1)

                elapsed = total_seconds
                return

        # Wait any remaining time after last milestone
        remaining = total_seconds - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

    @discord.ui.button(label="\u00ab Back", style=discord.ButtonStyle.primary, row=4)
    async def back_button(self, interaction: Interaction, button: Button):
        servers = await get_ark_servers(self.guild_id)
        view = ServerManagementView(self.guild_id, self.bot, servers)
        await interaction.response.edit_message(embed=_main_panel_embed(len(servers)), view=view)


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------

class BroadcastModal(Modal, title="Broadcast Message"):
    message_input = TextInput(
        label="Broadcast Message",
        placeholder="Enter your message to broadcast to all players...",
        style=discord.TextStyle.paragraph, required=True, max_length=1000,
    )

    def __init__(self, server: Dict):
        super().__init__()
        self.server = server

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        display = _server_label(self.server)
        try:
            async with SimpleRCONClient(
                host=self.server["host"], port=self.server["rcon_port"],
                password=self.server["rcon_password"], timeout=5.0,
            ) as rcon:
                await rcon.execute(f"ServerChat {self.message_input.value}")
            await interaction.followup.send(f'\U0001f4e2 Broadcast sent to **{display}**: "{self.message_input.value}"', ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"\u274c Failed: {e}", ephemeral=True)


class MOTDModal(Modal, title="Set Message of the Day"):
    motd_input = TextInput(
        label="Message of the Day",
        placeholder="Enter the MOTD (leave empty to clear)...",
        style=discord.TextStyle.paragraph, required=False, max_length=500, default="",
    )

    def __init__(self, server: Dict):
        super().__init__()
        self.server = server

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        display = _server_label(self.server)
        motd = self.motd_input.value.strip()
        try:
            if motd:
                async with SimpleRCONClient(
                    host=self.server["host"], port=self.server["rcon_port"],
                    password=self.server["rcon_password"], timeout=5.0,
                ) as rcon:
                    await rcon.execute(f"ServerChat [MOTD] {motd}")
                await interaction.followup.send(f'\U0001f4dd MOTD set for **{display}**: "{motd}"', ephemeral=True)
            else:
                await interaction.followup.send(f"\U0001f4dd MOTD cleared for **{display}**", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"\u274c Failed: {e}", ephemeral=True)


class CustomRCONModal(Modal, title="Custom RCON Command"):
    command_input = TextInput(
        label="RCON Command",
        placeholder="Enter a custom RCON command (e.g., ListPlayers)...",
        style=discord.TextStyle.short, required=True, max_length=200,
    )

    def __init__(self, server: Dict):
        super().__init__()
        self.server = server

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        command = self.command_input.value.strip()
        display = _server_label(self.server)
        try:
            async with SimpleRCONClient(
                host=self.server["host"], port=self.server["rcon_port"],
                password=self.server["rcon_password"], timeout=10.0,
            ) as rcon:
                result = await rcon.execute(command)
            if result and result.strip():
                text = result.strip()
                if len(text) > 1900:
                    text = text[:1900] + "..."
                embed = Embed(
                    title=f"\u2328\ufe0f RCON Result - {display}",
                    description=f"**Command:** `{command}`\n\n```\n{text}\n```",
                    color=discord.Color.purple(),
                )
                embed.timestamp = discord.utils.utcnow()
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(
                    f"\u2328\ufe0f `{command}` executed on **{display}** (no output)", ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(f"\u274c Failed on **{display}**: {e}", ephemeral=True)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class ServerManagementCog(commands.Cog):
    """Server Management Console cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="servermgmt", description="Server Management Console")
    @app_commands.checks.has_permissions(administrator=True)
    async def servermgmt(self, interaction: Interaction):
        """Open the server management console."""
        if not await check_feature(interaction, "server_management"):
            return
        guild_id = interaction.guild.id
        servers = await get_ark_servers(guild_id)
        view = ServerManagementView(guild_id, self.bot, servers)
        await interaction.response.send_message(
            embed=_main_panel_embed(len(servers)), view=view, ephemeral=True
        )
        # Store message reference for auto-refresh
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    """Setup function for the cog."""
    await bot.add_cog(ServerManagementCog(bot))
    logger.info("Server Management cog loaded")
