import discord
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button, Select
from discord import app_commands, SelectOption
import asyncio
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from bot.cogs.remote_agent import RemoteAgentManager
from bot.database import remote_agent_db
from bot.database import server_config_db
from bot.utils.subscription_checker import check_feature

logger = logging.getLogger(__name__)


class AgentRegistrationModal(Modal):
    """Modal for registering a new remote agent."""

    def __init__(self, parent_message=None):
        super().__init__(title="🔗 Register Remote Agent")
        self.parent_message = parent_message

        self.add_item(
            TextInput(
                label="Agent IP Address",
                placeholder="192.168.1.50",
                required=True,
                style=discord.TextStyle.short,
                custom_id="agent_ip",
            )
        )

        self.add_item(
            TextInput(
                label="Agent Port",
                placeholder="8080",
                required=True,
                style=discord.TextStyle.short,
                custom_id="agent_port",
                default="8080",
            )
        )

        self.add_item(
            TextInput(
                label="Authentication Key",
                placeholder="agent_1234567890",
                required=True,
                style=discord.TextStyle.short,
                custom_id="auth_key",
            )
        )

        self.add_item(
            TextInput(
                label="Display Name (optional)",
                placeholder="e.g., Game Server PC, Living Room Rig",
                required=False,
                style=discord.TextStyle.short,
                custom_id="display_name",
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        """Handle agent registration submission."""
        agent_ip = self.children[0].value.strip()
        agent_port = self.children[1].value.strip()
        auth_key = self.children[2].value.strip()
        display_name = self.children[3].value.strip() if self.children[3].value else None

        await interaction.response.defer(ephemeral=True)

        # Validate inputs
        try:
            agent_port = int(agent_port)
            if agent_port < 1 or agent_port > 65535:
                raise ValueError("Port must be between 1 and 65535")
        except ValueError:
            embed = discord.Embed(
                title="❌ Invalid Port",
                description="Port must be a valid number between 1 and 65535.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Get the agent manager from the bot
        agent_manager = interaction.client.agent_manager

        # Register the agent
        success, message = await agent_manager.register_agent(interaction.guild_id, agent_ip, agent_port, auth_key)

        if success:
            agent_id = f"{agent_ip}:{agent_port}"
            agent_info = await agent_manager.get_agent_status(agent_id)
            servers = agent_info.get("servers", [])

            embed = discord.Embed(
                title="✅ Agent Registration Successful",
                description=f"Successfully connected to remote agent at **{agent_ip}:{agent_port}**",
                color=discord.Color.green(),
            )

            embed.add_field(name="🔗 Agent Address", value=f"{agent_ip}:{agent_port}", inline=True)
            embed.add_field(name="�️ Discovered Servers", value=str(len(servers)), inline=True)
            embed.add_field(name="� Status", value="🟢 Connected", inline=True)

            if servers:
                server_list = "\n".join([f"• {server.get('name', 'Unknown')}" for server in servers[:5]])
                if len(servers) > 5:
                    server_list += f"\n... and {len(servers) - 5} more"
                embed.add_field(name="🎮 ARK Servers Found", value=server_list, inline=False)

            embed.set_footer(text="You can now manage these servers remotely!")
            
            # Auto-refresh the parent agent control panel
            if self.parent_message:
                try:
                    from bot.database import remote_agent_db
                    guild_agents = await remote_agent_db.get_remote_agents(interaction.guild_id)
                    agents_count = len(guild_agents)
                    connected_count = sum(1 for agent in guild_agents if agent["agent_id"] in agent_manager.connections)
                    
                    refresh_embed = discord.Embed(
                        title="🌐 Agent Control",
                        description="Manage your remote ARK server agents",
                        color=discord.Color.blue(),
                    )
                    refresh_embed.add_field(name="🤖 Registered Agents", value=str(agents_count), inline=True)
                    refresh_embed.add_field(
                        name="📡 Connection Status",
                        value=f"🟢 {connected_count} Connected" if connected_count > 0 else "🔴 Offline",
                        inline=True,
                    )
                    refresh_embed.set_footer(text="Use the buttons below to manage your remote agents")
                    await self.parent_message.edit(embed=refresh_embed)
                except Exception as e:
                    logger.error(f"Failed to refresh agent control panel: {e}")

        else:
            embed = discord.Embed(
                title="❌ Agent Registration Failed",
                description=f"Failed to connect to agent at {agent_ip}:{agent_port}",
                color=discord.Color.red(),
            )
            embed.add_field(name="🔧 Error Details", value=message, inline=False)
            embed.add_field(
                name="💡 Troubleshooting Steps",
                value=(
                    "1. **Verify Agent Status**: Ensure the ARK Agent is running on the target server\n"
                    "2. **Check Network Connectivity**: Ping the agent IP from this machine\n"
                    "3. **Validate Port**: Confirm the agent is listening on the specified port\n"
                    "4. **Authentication Key**: Double-check the auth key matches the agent's config\n"
                    "5. **Firewall Settings**: Ensure the firewall allows connections on port " + str(agent_port)
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)


class AgentControlView(View):
    """Agent Control panel — register, view status, and remove remote agents.
    ARK server start/stop/restart is handled by /servermgmt, not here.
    """

    def __init__(self, guild_id: int, user: discord.User, agent_manager: RemoteAgentManager):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user = user
        self.agent_manager = agent_manager

        register_btn = Button(label="🔗 Register Agent", style=discord.ButtonStyle.primary, custom_id="register_agent")
        register_btn.callback = self.handle_register_agent
        self.add_item(register_btn)

        status_btn = Button(label="🤖 Agent Status", style=discord.ButtonStyle.secondary, custom_id="agent_status")
        status_btn.callback = self.handle_agent_status
        self.add_item(status_btn)

        remove_btn = Button(label="🗑️ Remove Agent", style=discord.ButtonStyle.danger, custom_id="remove_agent")
        remove_btn.callback = self.handle_remove_agent
        self.add_item(remove_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

    async def handle_register_agent(self, interaction: discord.Interaction):
        """Open the agent registration modal."""
        # Pass the parent message for auto-refresh
        parent_message = interaction.message
        await interaction.response.send_modal(AgentRegistrationModal(parent_message=parent_message))

    async def handle_agent_status(self, interaction: discord.Interaction):
        """Show all registered agents with live connection status."""
        await interaction.response.defer(ephemeral=True)

        agents = await remote_agent_db.get_remote_agents(interaction.guild_id)

        if not agents:
            embed = discord.Embed(
                title="🤖 No Agents Registered",
                description="No remote agents are registered.\nClick **Register Agent** to add one.",
                color=discord.Color.orange(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🤖 Agent Status",
            description=f"{len(agents)} registered agent(s)",
            color=discord.Color.blue(),
        )

        for agent in agents:
            agent_id = agent["agent_id"]
            ip = agent["ip"]
            port = agent["port"]
            connected = agent_id in self.agent_manager.connections
            status_icon = "🟢 Connected" if connected else "🔴 Disconnected"

            # Last connected timestamp
            connected_at = agent.get("last_connected") or agent.get("created_at")
            last_seen = "Never"
            if connected_at:
                try:
                    dt_str = connected_at if isinstance(connected_at, str) else str(connected_at)
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    delta = datetime.now() - dt
                    h, rem = divmod(int(delta.total_seconds()), 3600)
                    m = rem // 60
                    last_seen = f"{h}h {m}m ago" if h else f"{m}m ago"
                except Exception:
                    last_seen = "Unknown"

            embed.add_field(
                name=f"🤖 {agent_id}",
                value=(
                    f"📡 **Status:** {status_icon}\n"
                    f"🖥️ **Address:** `{ip}:{port}`\n"
                    f"🔑 **Auth Key:** `[configured]`\n"
                    f"🕐 **Last Seen:** {last_seen}"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def handle_remove_agent(self, interaction: discord.Interaction):
        """Show a select menu to pick an agent to remove."""
        await interaction.response.defer(ephemeral=True)

        agents = await remote_agent_db.get_remote_agents(interaction.guild_id)

        if not agents:
            embed = discord.Embed(
                title="🤖 No Agents Registered",
                description="There are no agents to remove.",
                color=discord.Color.orange(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        options = [
            SelectOption(
                label=a["agent_id"],
                value=a["agent_id"],
                description=f"{a['ip']}:{a['port']}",
            )
            for a in agents
        ]

        view = RemoveAgentView(self.guild_id, self.user, self.agent_manager, options)
        embed = discord.Embed(
            title="🗑️ Remove Agent",
            description="Select the agent to unregister:",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


# Keep old name as alias so any existing references don't break
RemoteServerManagementView = AgentControlView


class RemoveAgentView(View):
    """Confirmation view for removing a registered agent."""

    def __init__(self, guild_id: int, user: discord.User, agent_manager: RemoteAgentManager, options: list):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user = user
        self.agent_manager = agent_manager

        select = Select(placeholder="Select agent to remove…", options=options)
        select.callback = self.on_select
        self.add_item(select)
        self.selected_agent_id = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

    async def on_select(self, interaction: discord.Interaction):
        self.selected_agent_id = interaction.data["values"][0]

        confirm_btn = Button(label="✅ Confirm Remove", style=discord.ButtonStyle.danger, custom_id="confirm_remove")
        confirm_btn.callback = self.on_confirm
        cancel_btn = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_remove")
        cancel_btn.callback = self.on_cancel

        # Swap to confirm/cancel buttons
        self.clear_items()
        self.add_item(confirm_btn)
        self.add_item(cancel_btn)

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🗑️ Confirm Remove",
                description=f"Remove agent **{self.selected_agent_id}**?\nThis will disconnect and unregister it.",
                color=discord.Color.red(),
            ),
            view=self,
        )

    async def on_confirm(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        success = await remote_agent_db.delete_remote_agent(self.guild_id, self.selected_agent_id)
        # Properly close WebSocket and cancel background tasks before removing
        agent_id = self.selected_agent_id
        # Cancel reconnect task first so it doesn't respawn the connection
        reconnect_task = self.agent_manager._reconnect_tasks.pop(agent_id, None)
        if reconnect_task and not reconnect_task.done():
            reconnect_task.cancel()
        # Cancel listener task
        listener_task = self.agent_manager._listeners.pop(agent_id, None)
        if listener_task and not listener_task.done():
            listener_task.cancel()
        # Close the WebSocket connection
        ws = self.agent_manager.connections.pop(agent_id, None)
        if ws:
            try:
                await ws.close()
            except Exception as e:
                logger.warning(f"Error closing WebSocket for {agent_id}: {e}")
        # Remove from agents dict (must be last — reconnect loop checks this)
        self.agent_manager.agents.pop(agent_id, None)

        if success:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="✅ Agent Removed",
                    description=f"Agent **{self.selected_agent_id}** has been unregistered.",
                    color=discord.Color.green(),
                ),
                view=None,
            )
        else:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="❌ Failed",
                    description="Could not remove the agent. Check logs for details.",
                    color=discord.Color.red(),
                ),
                view=None,
            )

    async def on_cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Removal cancelled.", embed=None, view=None)

class ServerControlView(View):
    """View for controlling a specific remote server."""

    def __init__(
        self, guild_id: int, user: discord.User, agent_manager: RemoteAgentManager, server_options: List[SelectOption]
    ):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user = user
        self.agent_manager = agent_manager
        self.selected_server = None

        # Add server selector
        self.add_item(ServerSelect(server_options))

        # Add control buttons (initially disabled)
        self.start_button = Button(
            label="▶️ Start Server", style=discord.ButtonStyle.success, custom_id="start_server", disabled=True
        )
        self.stop_button = Button(
            label="⏹️ Stop Server", style=discord.ButtonStyle.danger, custom_id="stop_server", disabled=True
        )
        self.restart_button = Button(
            label="🔄 Restart Server", style=discord.ButtonStyle.secondary, custom_id="restart_server", disabled=True
        )
        self.status_button = Button(
            label="📊 Get Status", style=discord.ButtonStyle.primary, custom_id="get_status", disabled=True
        )
        self.update_button = Button(
            label="🔄 Update Server", style=discord.ButtonStyle.secondary, custom_id="update_server", disabled=True
        )
        self.backup_button = Button(
            label="💾 Backup Server", style=discord.ButtonStyle.secondary, custom_id="backup_server", disabled=True
        )
        self.mod_button = Button(
            label="📦 Manage Mods", style=discord.ButtonStyle.secondary, custom_id="manage_mods", disabled=True
        )

        self.add_item(self.start_button)
        self.add_item(self.stop_button)
        self.add_item(self.restart_button)
        self.add_item(self.status_button)
        self.add_item(self.update_button)
        self.add_item(self.backup_button)
        self.add_item(self.mod_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the user who initiated can interact."""
        return interaction.user.id == self.user.id

    def enable_controls(self):
        """Enable server control buttons."""
        self.start_button.disabled = False
        self.stop_button.disabled = False
        self.restart_button.disabled = False
        self.status_button.disabled = False
        self.update_button.disabled = False
        self.backup_button.disabled = False
        self.mod_button.disabled = False

    async def handle_start_server(self, interaction: discord.Interaction):
        """Handle start server command."""
        if not self.selected_server:
            await interaction.response.send_message("❌ Please select a server first.", ephemeral=True)
            return

        agent_id, server_name = self.selected_server.split(":", 1)

        await interaction.response.defer(ephemeral=True)

        try:
            result = await self.agent_manager.send_command(agent_id, "start_server", server_name, timeout=30)
            status = result.get("status", "unknown")
            result_embed = discord.Embed(
                title="✅ Server Start Command Sent",
                description=f"Start command sent to {server_name}\nStatus: {status}",
                color=discord.Color.green(),
            )
        except Exception as e:
            result_embed = discord.Embed(
                title="❌ Failed to Start Server",
                description=f"Failed to start {server_name}: {e}",
                color=discord.Color.red(),
            )

        await interaction.followup.send(embed=result_embed, ephemeral=True)

    async def handle_stop_server(self, interaction: discord.Interaction):
        """Handle stop server command."""
        if not self.selected_server:
            await interaction.response.send_message("❌ Please select a server first.", ephemeral=True)
            return

        agent_id, server_name = self.selected_server.split(":", 1)

        await interaction.response.defer(ephemeral=True)

        try:
            result = await self.agent_manager.send_command(agent_id, "stop_server", server_name, timeout=30)
            status = result.get("status", "unknown")
            result_embed = discord.Embed(
                title="✅ Server Stop Command Sent",
                description=f"Stop command sent to {server_name}\nStatus: {status}",
                color=discord.Color.green(),
            )
        except Exception as e:
            result_embed = discord.Embed(
                title="❌ Failed to Stop Server",
                description=f"Failed to stop {server_name}: {e}",
                color=discord.Color.red(),
            )

        await interaction.followup.send(embed=result_embed, ephemeral=True)

    async def handle_restart_server(self, interaction: discord.Interaction):
        """Handle restart server command."""
        if not self.selected_server:
            await interaction.response.send_message("❌ Please select a server first.", ephemeral=True)
            return

        agent_id, server_name = self.selected_server.split(":", 1)

        await interaction.response.defer(ephemeral=True)

        try:
            result = await self.agent_manager.send_command(agent_id, "restart_server", server_name, timeout=60)
            status = result.get("status", "unknown")
            result_embed = discord.Embed(
                title="✅ Server Restart Command Sent",
                description=f"Restart command sent to {server_name}\nStatus: {status}",
                color=discord.Color.green(),
            )
        except Exception as e:
            result_embed = discord.Embed(
                title="❌ Failed to Restart Server",
                description=f"Failed to restart {server_name}: {e}",
                color=discord.Color.red(),
            )

        await interaction.followup.send(embed=result_embed, ephemeral=True)

    async def handle_get_status(self, interaction: discord.Interaction):
        """Handle get status command."""
        if not self.selected_server:
            await interaction.response.send_message("❌ Please select a server first.", ephemeral=True)
            return

        agent_id, server_name = self.selected_server.split(":", 1)

        await interaction.response.defer(ephemeral=True)

        try:
            result = await self.agent_manager.send_command(agent_id, "get_status", server_name, timeout=15)
            data = result.get("data", {})
            status = result.get("status", "unknown")

            result_embed = discord.Embed(
                title=f"📊 {server_name} Status",
                color=discord.Color.green(),
            )
            if isinstance(data, dict):
                state = data.get("service_state", data.get("state", status))
                result_embed.add_field(name="State", value=state, inline=True)
                if "players" in data:
                    result_embed.add_field(name="Players", value=str(data["players"]), inline=True)
                if "cpu_percent" in data:
                    result_embed.add_field(name="CPU", value=f"{data['cpu_percent']}%", inline=True)
                if "memory_mb" in data:
                    result_embed.add_field(name="Memory", value=f"{data['memory_mb']} MB", inline=True)
            else:
                result_embed.description = f"Status: {status}"
        except Exception as e:
            result_embed = discord.Embed(
                title="❌ Failed to Get Status",
                description=f"Failed to get status for {server_name}: {e}",
                color=discord.Color.red(),
            )

        await interaction.followup.send(embed=result_embed, ephemeral=True)

    async def handle_update_server(self, interaction: discord.Interaction):
        """Handle update server command."""
        if not self.selected_server:
            await interaction.response.send_message("❌ Please select a server first.", ephemeral=True)
            return

        agent_id, server_name = self.selected_server.split(":", 1)
        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.followup.send(f"🔄 Starting update for {server_name}...", ephemeral=True)
            result = await self.agent_manager.send_command(agent_id, "update_server", server_name, timeout=300)

            embed = discord.Embed(
                title="✅ Server Update Complete",
                description=f"Server '{server_name}' updated successfully",
                color=discord.Color.green(),
            )

            if result.get("data"):
                data = result["data"]
                if "backup_path" in data:
                    embed.add_field(name="📁 Backup Created", value=f"`{data['backup_path']}`", inline=False)

            await interaction.edit_original_response(embed=embed)

        except TimeoutError:
            await interaction.edit_original_response(content="⏰ Update timed out after 5 minutes.")
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Update failed: {e}")

    async def handle_backup_server(self, interaction: discord.Interaction):
        """Handle backup server command."""
        if not self.selected_server:
            await interaction.response.send_message("❌ Please select a server first.", ephemeral=True)
            return

        agent_id, server_name = self.selected_server.split(":", 1)
        await interaction.response.defer(ephemeral=True)

        try:
            result = await self.agent_manager.send_command(agent_id, "backup_server", server_name, timeout=60)

            embed = discord.Embed(
                title="✅ Server Backup Complete",
                description=f"Server '{server_name}' backed up successfully",
                color=discord.Color.green(),
            )

            if result.get("data"):
                data = result["data"]
                if "backup_path" in data:
                    embed.add_field(name="📁 Backup Location", value=f"`{data['backup_path']}`", inline=False)
                if "size_mb" in data:
                    embed.add_field(name="💾 Size", value=f"{data['size_mb']} MB", inline=True)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(content=f"❌ Backup failed: {e}", ephemeral=True)

    async def handle_manage_mods(self, interaction: discord.Interaction):
        """Handle mod management - opens mod installation modal."""
        if not self.selected_server:
            await interaction.response.send_message("❌ Please select a server first.", ephemeral=True)
            return

        # Open mod installation modal
        modal = ModInstallationModal(self.selected_server, self.agent_manager)
        await interaction.response.send_modal(modal)

    async def callback(self, interaction: discord.Interaction):
        """Handle button interactions."""
        custom_id = interaction.data["custom_id"]

        if custom_id == "start_server":
            await self.handle_start_server(interaction)
        elif custom_id == "stop_server":
            await self.handle_stop_server(interaction)
        elif custom_id == "restart_server":
            await self.handle_restart_server(interaction)
        elif custom_id == "get_status":
            await self.handle_get_status(interaction)
        elif custom_id == "update_server":
            await self.handle_update_server(interaction)
        elif custom_id == "backup_server":
            await self.handle_backup_server(interaction)
        elif custom_id == "manage_mods":
            await self.handle_manage_mods(interaction)


class ModInstallationModal(Modal):
    """Modal for installing mods via CurseForge ID."""

    def __init__(self, selected_server: str, agent_manager: RemoteAgentManager):
        super().__init__(title="📦 Install Mod")
        self.selected_server = selected_server
        self.agent_manager = agent_manager

        self.add_item(
            TextInput(
                label="CurseForge Mod ID",
                placeholder="e.g., 894766 for S+",
                required=True,
                style=discord.TextStyle.short,
                custom_id="curseforge_id",
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        """Handle mod installation submission."""
        curseforge_id_str = self.children[0].value

        try:
            curseforge_id = int(curseforge_id_str)
        except ValueError:
            await interaction.response.send_message("❌ Invalid CurseForge ID. Must be a number.", ephemeral=True)
            return

        agent_id, server_name = self.selected_server.split(":", 1)
        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.followup.send(f"📦 Installing mod {curseforge_id} to {server_name}...", ephemeral=True)

            params = {"curseforge_id": curseforge_id}
            result = await self.agent_manager.send_command(agent_id, "install_mod", server_name, params, timeout=180)

            embed = discord.Embed(
                title="✅ Mod Installation Complete",
                description=f"Mod {curseforge_id} installed to '{server_name}'",
                color=discord.Color.green(),
            )

            if result.get("data"):
                data = result["data"]
                if "mod_name" in data:
                    embed.title = f"Mod Installed: {data['mod_name']}"
                if "install_path" in data:
                    embed.add_field(name="📁 Install Location", value=f"`{data['install_path']}`", inline=False)
                if "download_size" in data:
                    embed.add_field(name="💾 Download Size", value=data["download_size"], inline=True)

            await interaction.edit_original_response(embed=embed)

        except TimeoutError:
            await interaction.edit_original_response(content="⏰ Mod installation timed out after 3 minutes.")
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Mod installation failed: {e}")


class ServerSelect(Select):
    """Select dropdown for choosing a remote server."""

    def __init__(self, options: List[SelectOption]):
        super().__init__(
            placeholder="🎮 Select a server to control...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="server_select",
        )

    async def callback(self, interaction: discord.Interaction):
        """Handle server selection."""
        selected_value = self.values[0]
        self.view.selected_server = selected_value
        self.view.enable_controls()

        agent_id, server_name = selected_value.split(":", 1)

        embed = discord.Embed(
            title="✅ Server Selected", description=f"Selected {server_name} on {agent_id}", color=discord.Color.green()
        )
        embed.add_field(name="🎮 Server", value=server_name, inline=True)
        embed.add_field(name="🤖 Agent", value=agent_id, inline=True)

        await interaction.response.edit_message(embed=embed, view=self.view)


class RemoteAgentGUI(commands.Cog):
    """Discord commands for remote agent GUI management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions."""
        if not interaction.guild:
            return False

        member = interaction.guild.get_member(interaction.user.id)
        return member.guild_permissions.administrator

    @app_commands.command(name="remote_management", description="🎮 Open remote server management GUI")
    async def remote_management(self, interaction: discord.Interaction):
        """Open the remote server management GUI."""
        if not await check_feature(interaction, "remote_agent"):
            return
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        # Get the agent manager from the bot
        agent_manager = interaction.client.agent_manager

        view = RemoteServerManagementView(interaction.guild_id, interaction.user, agent_manager)

        embed = discord.Embed(
            title="🎮 Remote Server Management",
            description="Manage your remote ARK servers through agents",
            color=discord.Color.blue(),
        )

        # Get registered agents from database (not in-memory connections)
        registered_agents = await remote_agent_db.get_remote_agents(interaction.guild_id)
        agents_count = len(registered_agents)
        
        # Count connected agents from in-memory connections
        connected_count = sum(1 for agent in registered_agents if agent["agent_id"] in agent_manager.connections)
        
        ark_servers = await server_config_db.get_ark_servers(interaction.guild_id)
        servers_count = len(ark_servers)

        embed.add_field(name="🤖 Registered Agents", value=str(agents_count), inline=True)
        embed.add_field(name="🎮 Managed Servers", value=str(servers_count), inline=True)
        embed.add_field(name="📡 Status", value=f"🟢 {connected_count} Connected" if connected_count > 0 else "🔴 No Agents", inline=True)

        embed.set_footer(text="Use the buttons below to manage your remote servers")

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup the remote agent GUI cog."""
    await bot.add_cog(RemoteAgentGUI(bot))
