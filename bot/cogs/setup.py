"""
Setup commands for bot configuration.
Allows server admins to configure the bot entirely through Discord.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import logging

from bot.database import server_config_db

logger = logging.getLogger("Setup")


class Setup(commands.Cog):
    """Server setup and configuration commands."""

    def __init__(self, bot):
        self.bot = bot

    async def is_admin(self, interaction: "discord.Interaction") -> bool:
        """Check if user is admin (has Administrator permission or configured admin role)."""
        # Check Discord administrator permission
        if interaction.user.guild_permissions.administrator:
            return True

        # Check configured admin role
        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_role_id"):
            admin_role = interaction.guild.get_role(config["admin_role_id"])
            if admin_role and admin_role in interaction.user.roles:
                return True

        return False

    @app_commands.command(name="setup", description="🛠️ Interactive setup wizard (admin only)")
    async def setup_wizard(self, interaction: discord.Interaction):
        """Open the interactive setup GUI wizard."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        from bot.cogs.setup_gui import SetupMainView

        view = SetupMainView(interaction.guild_id, interaction.user, interaction.guild, self.bot)
        await view.load_config()
        embed = await view.create_main_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="setchannels", description="⚙️ Configure Discord channels (admin only)"
    )
    @app_commands.describe(
        chat_channel="Channel for ARK in-game chat relay",
        status_channel="Channel for server status (voice channels created here)",
        shop_channel="Channel for shop commands",
        log_channel="Channel for admin action logs",
        announcement_channel="Channel for public shop purchase announcements",
    )
    async def set_channels(
        self,
        interaction: discord.Interaction,
        chat_channel: Optional[discord.TextChannel] = None,
        status_channel: Optional[discord.CategoryChannel] = None,
        shop_channel: Optional[discord.TextChannel] = None,
        log_channel: Optional[discord.TextChannel] = None,
        announcement_channel: Optional[discord.TextChannel] = None,
    ):
        """Configure channel settings."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        updates = {}
        if chat_channel:
            updates["chat_channel_id"] = chat_channel.id
        if status_channel:
            updates["status_channel_id"] = status_channel.id
        if shop_channel:
            updates["shop_channel_id"] = shop_channel.id
        if log_channel:
            updates["admin_log_channel_id"] = log_channel.id
        if announcement_channel:
            updates["shop_announcement_channel_id"] = announcement_channel.id

        if not updates:
            await interaction.followup.send("❌ No channels specified!", ephemeral=True)
            return

        await server_config_db.create_or_update_server_config(
            interaction.guild_id, interaction.guild.name, **updates
        )

        embed = discord.Embed(title="✅ Channels Configured", color=discord.Color.green())

        if chat_channel:
            embed.add_field(name="💬 Chat Channel", value=chat_channel.mention, inline=False)
        if status_channel:
            embed.add_field(name="📊 Status Channel", value=status_channel.mention, inline=False)
        if shop_channel:
            embed.add_field(name="🛒 Shop Channel", value=shop_channel.mention, inline=False)
        if log_channel:
            embed.add_field(name="📝 Log Channel", value=log_channel.mention, inline=False)
        if announcement_channel:
            embed.add_field(
                name="📢 Announcement Channel", value=announcement_channel.mention, inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Log to log channel if configured
        if log_channel:
            log_embed = discord.Embed(
                title="⚙️ Channels Updated",
                description=f"Configuration updated by {interaction.user.mention}",
                color=discord.Color.blue(),
            )
            for field in embed.fields:
                log_embed.add_field(name=field.name, value=field.value, inline=False)
            await log_channel.send(embed=log_embed)

    @app_commands.command(name="setadminrole", description="👑 Set bot admin role (admin only)")
    @app_commands.describe(role="Role that can manage bot configuration")
    async def set_admin_role(self, interaction: discord.Interaction, role: discord.Role):
        """Set the admin role for bot management."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        await server_config_db.create_or_update_server_config(
            interaction.guild_id, interaction.guild.name, admin_role_id=role.id
        )

        await interaction.response.send_message(
            f"✅ Admin role set to {role.mention}. Users with this role can manage the bot.",
            ephemeral=True,
        )

    @app_commands.command(
        name="sethostingtype", description="🏠 Set server hosting type (admin only)"
    )
    @app_commands.describe(
        hosting_type="Choose 'Self-Hosted' for local servers with NSSM, or 'Nitrado' for hosted servers"
    )
    @app_commands.choices(
        hosting_type=[
            app_commands.Choice(name="Self-Hosted (Local servers with NSSM)", value="self_hosted"),
            app_commands.Choice(name="Nitrado (Hosted server provider)", value="nitrado"),
        ]
    )
    async def set_hosting_type(
        self, interaction: discord.Interaction, hosting_type: app_commands.Choice[str]
    ):
        """Set the hosting type for your ARK servers."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Ensure server config exists
        await server_config_db.create_or_update_server_config(
            interaction.guild_id, interaction.guild.name
        )

        # Set the hosting type
        await server_config_db.set_hosting_type(interaction.guild_id, hosting_type.value)

        embed = discord.Embed(title="✅ Hosting Type Configured", color=discord.Color.green())

        if hosting_type.value == "self_hosted":
            embed.description = "🏠 **Self-Hosted** mode enabled"
            embed.add_field(
                name="Available Features",
                value=(
                    "• NSSM service control (start/stop/restart)\n"
                    "• Server log viewing\n"
                    "• Crash monitoring & diagnostics\n"
                    "• Server path configuration\n"
                    "• Local backup management"
                ),
                inline=False,
            )
            embed.add_field(
                name="Next Steps",
                value=(
                    "Use `/addserver` with `service_name` and `server_path` parameters\n"
                    "to enable full server management capabilities."
                ),
                inline=False,
            )
        else:
            embed.description = "☁️ **Nitrado** mode enabled"
            embed.add_field(
                name="Available Features",
                value=(
                    "• Live server monitoring (RCON)\n"
                    "• RCON commands & chat relay\n"
                    "• Server status & player tracking\n"
                    "• Voice channel status updates\n"
                    "• Shop & economy system\n"
                    "• RCON-based restart (DoExit)"
                ),
                inline=False,
            )
            embed.add_field(
                name="Note",
                value=(
                    "Local server management features (logs, NSSM, crash monitor)\n"
                    "are hidden in Nitrado mode as they require local access."
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="addserver", description="➕ Add ARK server (admin only)")
    @app_commands.describe(
        name="Server display name",
        host="Server IP address",
        game_port="Game port number (what players connect to)",
        query_port="Query port number (for status monitoring)",
        rcon_port="RCON port number",
        rcon_password="RCON password",
        service_name="[Self-Hosted] NSSM service name for server control",
        server_path="[Self-Hosted] Server installation path (e.g., R:\\PhoenixArk\\asaserver_island)",
        max_players="Maximum players (default: 70)",
        chat_enabled="Enable chat relay (default: true)",
    )
    async def add_server(
        self,
        interaction: discord.Interaction,
        name: str,
        host: str,
        rcon_port: int,
        rcon_password: str,
        game_port: Optional[int] = None,
        query_port: Optional[int] = None,
        service_name: Optional[str] = None,
        server_path: Optional[str] = None,
        max_players: int = 70,
        chat_enabled: bool = True,
    ):
        """Add an ARK server to monitor."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Check subscription tier and enforce server limits
        from bot.database import subscription_db
        
        sub = await subscription_db.get_or_create_subscription(interaction.guild_id)
        tier = subscription_db.get_effective_tier(sub)
        
        # Free tier: limit to 2 servers total
        if tier == "free":
            existing_servers = await server_config_db.get_ark_servers(interaction.guild_id)
            if len(existing_servers) >= 2:
                await interaction.followup.send(
                    "❌ **Free tier limit reached!**\n\n"
                    "You can only configure **2 ARK servers** on the free tier.\n\n"
                    "💎 **Upgrade to Premium** for:\n"
                    "• Unlimited servers\n"
                    "• Unlimited remote agents\n"
                    "• Economy, shop, kits, and games\n"
                    "• Priority support\n\n"
                    "Use `/subscribe` to upgrade!",
                    ephemeral=True
                )
                return

        # Ensure server config exists
        await server_config_db.create_or_update_server_config(
            interaction.guild_id, interaction.guild.name
        )

        # Add server
        server_id = await server_config_db.add_ark_server(
            interaction.guild_id,
            name=name,
            host=host,
            game_port=game_port,
            query_port=query_port,
            rcon_port=rcon_port,
            rcon_password=rcon_password,
            service_name=service_name,
            server_path=server_path,
            max_players=max_players,
            chat_enabled=chat_enabled,
        )

        embed = discord.Embed(
            title="✅ Server Added",
            description=f"ARK server **{name}** has been added!",
            color=discord.Color.green(),
        )
        embed.add_field(name="Host", value=host, inline=True)
        if game_port:
            embed.add_field(name="Game Port", value=game_port, inline=True)
        if query_port:
            embed.add_field(name="Query Port", value=query_port, inline=True)
        embed.add_field(name="RCON Port", value=rcon_port, inline=True)
        embed.add_field(name="Max Players", value=max_players, inline=True)
        embed.add_field(name="Chat Enabled", value="✅" if chat_enabled else "❌", inline=True)
        if service_name:
            embed.add_field(name="Service Name", value=service_name, inline=True)
        if server_path:
            embed.add_field(name="Server Path", value=f"`{server_path}`", inline=False)

        # Add connection string if game port is provided
        if game_port:
            embed.add_field(name="Connect String", value=f"`{host}:{game_port}`", inline=False)

        embed.set_footer(text=f"Server ID: {server_id}")

        await interaction.followup.send(embed=embed, ephemeral=True)

        # Reload monitoring if server_monitor cog is loaded
        if "ServerMonitor" in self.bot.cogs:
            await self.bot.cogs["ServerMonitor"]._reload_servers_internal()

    @app_commands.command(
        name="listservers", description="📋 List configured ARK servers with connection details"
    )
    async def list_servers(self, interaction: discord.Interaction):
        """List all configured ARK servers with IP addresses and ports."""
        # Defer immediately to avoid timeout
        await interaction.response.defer(ephemeral=True)

        try:
            servers = await server_config_db.get_ark_servers(interaction.guild_id)

            if not servers:
                await interaction.followup.send(
                    "❌ No servers configured. Use `/addserver` to add one!", ephemeral=True
                )
                return

            embed = discord.Embed(
                title="📋 Configured ARK Servers",
                description="Server connection details and ports",
                color=discord.Color.blue(),
            )

            for server in servers:
                # Get ports from database
                game_port = server.get("game_port")
                query_port = server.get("query_port")
                rcon_port = server["rcon_port"]

                value = f"**IP Address:** `{server['host']}`\n"
                value += f"**Game Port:** `{game_port if game_port else 'Not configured'}`\n"
                value += f"**Query Port:** `{query_port if query_port else 'Not configured'}`\n"
                value += f"**RCON Port:** `{rcon_port}`\n"
                value += f"**Max Players:** {server.get('max_players', 70)}\n"
                value += f"**Chat Relay:** {'✅ Enabled' if server.get('chat_enabled', True) else '❌ Disabled'}\n"
                value += f"**Server ID:** `{server['id']}`"

                # Add connection string for players
                if game_port:
                    value += f"\n**Connect:** `{server['host']}:{game_port}`"

                embed.add_field(name=f"🖥️ {server['name']}", value=value, inline=False)

            embed.set_footer(text=f"Total Servers: {len(servers)} | Use /testconnection to verify")

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in listservers command: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
            except:
                pass  # Already responded or timed out

    @app_commands.command(
        name="serverinfo", description="📊 Detailed information panel for a specific server"
    )
    @app_commands.describe(server_name="Name of the server to view")
    async def server_info(self, interaction: discord.Interaction, server_name: str):
        """Show detailed connection information for a specific server."""
        await interaction.response.defer(ephemeral=True)

        try:
            servers = await server_config_db.get_ark_servers(interaction.guild_id)
            server = next((s for s in servers if s["name"].lower() == server_name.lower()), None)

            if not server:
                await interaction.followup.send(
                    f"❌ Server '{server_name}' not found. Use `/listservers` to see available servers.",
                    ephemeral=True,
                )
                return

            # Get ports from database
            game_port = server.get("game_port")
            query_port = server.get("query_port")
            rcon_port = server["rcon_port"]

            embed = discord.Embed(
                title=f"🖥️ {server['name']} - Server Information",
                description="Complete connection and configuration details",
                color=discord.Color.green(),
            )

            # Connection Details
            connection_info = f"**IP Address:** `{server['host']}`\n"
            if game_port:
                connection_info += f"**Game Port:** `{game_port}`\n"
                connection_info += f"**Direct Connect:** `{server['host']}:{game_port}`\n"
            else:
                connection_info += f"**Game Port:** Not configured\n"
            connection_info += (
                f"**Query Port:** `{query_port if query_port else 'Not configured'}`\n"
            )
            connection_info += f"**RCON Port:** `{rcon_port}`"

            embed.add_field(name="🌐 Connection Details", value=connection_info, inline=False)

            # Server Configuration
            config_info = f"**Max Players:** {server.get('max_players', 70)}\n"
            config_info += f"**Chat Relay:** {'✅ Enabled' if server.get('chat_enabled', True) else '❌ Disabled'}\n"
            config_info += f"**Service Name:** {server.get('service_name', 'Not configured')}\n"
            config_info += f"**Server Status:** {'✅ Enabled' if server.get('enabled', True) else '❌ Disabled'}"

            embed.add_field(name="⚙️ Configuration", value=config_info, inline=False)

            # Technical Details
            tech_info = f"**Server ID:** `{server['id']}`\n"
            tech_info += f"**Log Path:** `{server.get('log_path', 'Default')}`\n"
            tech_info += f"**RCON Password:** `{'●' * 12}` (hidden)"

            embed.add_field(name="🔧 Technical Details", value=tech_info, inline=False)

            # Player Connection Instructions
            if game_port:
                instructions = (
                    f"1. Open ARK: Survival Ascended\n"
                    f"2. Go to 'Join ARK'\n"
                    f"3. Click 'Favorites' tab\n"
                    f"4. Click 'Add Server'\n"
                    f"5. Enter: `{server['host']}:{game_port}`\n"
                    f"6. Click 'Add' and then 'Join'"
                )
                embed.add_field(name="🎮 How to Connect", value=instructions, inline=False)

            embed.set_footer(
                text=f"Use /testconnection {server_name} to verify server connectivity"
            )

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in serverinfo command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)

    @server_info.autocomplete("server_name")
    async def server_info_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for serverinfo command."""
        return await self.server_name_autocomplete(interaction, current)

    @app_commands.command(name="removeserver", description="➖ Remove ARK server (admin only)")
    @app_commands.describe(server_id="Server ID (use /listservers to find)")
    async def remove_server(self, interaction: discord.Interaction, server_id: int):
        """Remove an ARK server."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await server_config_db.remove_ark_server(server_id)

            await interaction.followup.send(
                f"✅ Server ID {server_id} has been removed.", ephemeral=True
            )

            # Reload monitoring
            if "ServerMonitor" in self.bot.cogs:
                await self.bot.cogs["ServerMonitor"]._reload_servers_internal()
        except Exception as e:
            logger.error(f"Error removing server: {e}")
            await interaction.followup.send(f"❌ Failed to remove server: {e}", ephemeral=True)

    async def server_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete callback for server name selection."""
        try:
            servers = await server_config_db.get_ark_servers(interaction.guild_id)
            # Filter servers by current input and return up to 25 choices
            choices = [
                app_commands.Choice(name=server["name"], value=server["name"])
                for server in servers
                if current.lower() in server["name"].lower()
            ]
            return choices[:25]  # Discord limit is 25 choices
        except Exception as e:
            logger.error(f"Error in server autocomplete: {e}")
            return []

    @app_commands.command(
        name="editserver", description="✏️ Edit ARK server configuration (admin only)"
    )
    @app_commands.describe(
        server_name="Select the server to edit",
        name="New server name (optional)",
        host="New server IP address (optional)",
        rcon_port="New RCON port (optional)",
        rcon_password="New RCON password (optional)",
        query_port="New query port (optional)",
        service_name="[Self-Hosted] New NSSM service name (optional)",
        server_path="[Self-Hosted] Server installation path (optional)",
        max_players="New max players (optional)",
        chat_enabled="Enable/disable chat relay (optional)",
    )
    async def edit_server(
        self,
        interaction: discord.Interaction,
        server_name: str,
        name: Optional[str] = None,
        host: Optional[str] = None,
        rcon_port: Optional[int] = None,
        rcon_password: Optional[str] = None,
        query_port: Optional[int] = None,
        service_name: Optional[str] = None,
        server_path: Optional[str] = None,
        max_players: Optional[int] = None,
        chat_enabled: Optional[bool] = None,
    ):
        """Edit an existing ARK server configuration."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Get all servers and find the matching one
            servers = await server_config_db.get_ark_servers(interaction.guild_id)
            server = next((s for s in servers if s["name"] == server_name), None)

            if not server:
                await interaction.followup.send(
                    f"❌ Server '{server_name}' not found. Use `/listservers` to see available servers.",
                    ephemeral=True,
                )
                return

            server_id = server["id"]

            # Build update dict with only provided values
            updates = {}
            if name is not None:
                updates["name"] = name
            if host is not None:
                updates["host"] = host
            if rcon_port is not None:
                updates["rcon_port"] = rcon_port
            if rcon_password is not None:
                updates["rcon_password"] = rcon_password
            if query_port is not None:
                updates["query_port"] = query_port
            if service_name is not None:
                updates["service_name"] = service_name
            if server_path is not None:
                updates["server_path"] = server_path
            if max_players is not None:
                updates["max_players"] = max_players
            if chat_enabled is not None:
                updates["chat_enabled"] = chat_enabled

            if not updates:
                await interaction.followup.send(
                    "❌ No changes specified. Please provide at least one field to update.",
                    ephemeral=True,
                )
                return

            # Update the server
            await server_config_db.update_ark_server(server_id, **updates)

            # Build response showing what changed
            embed = discord.Embed(
                title="✅ Server Updated",
                description=f"Successfully updated **{server['name']}** (ID: {server_id})",
                color=discord.Color.green(),
            )

            changes = []
            if name:
                changes.append(f"Name: `{server['name']}` → `{name}`")
            if host:
                changes.append(f"Host: `{server['host']}` → `{host}`")
            if rcon_port:
                changes.append(f"RCON Port: `{server['rcon_port']}` → `{rcon_port}`")
            if rcon_password:
                changes.append(f"RCON Password: `***` → `***` (updated)")
            if query_port:
                changes.append(f"Query Port: `{server.get('query_port', 'None')}` → `{query_port}`")
            if service_name:
                changes.append(
                    f"Service Name: `{server.get('service_name', 'None')}` → `{service_name}`"
                )
            if server_path:
                changes.append(
                    f"Server Path: `{server.get('server_path', 'None')}` → `{server_path}`"
                )
            if max_players:
                changes.append(f"Max Players: `{server.get('max_players', 70)}` → `{max_players}`")
            if chat_enabled is not None:
                old_chat = "✅" if server.get("chat_enabled", True) else "❌"
                new_chat = "✅" if chat_enabled else "❌"
                changes.append(f"Chat Enabled: {old_chat} → {new_chat}")

            embed.add_field(name="Changes Applied", value="\n".join(changes), inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

            # Reload monitoring if server_monitor cog is loaded
            if "ServerMonitor" in self.bot.cogs:
                await self.bot.cogs["ServerMonitor"]._reload_servers_internal()

        except Exception as e:
            logger.error(f"Error editing server: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to update server: {e}", ephemeral=True)

    @edit_server.autocomplete("server_name")
    async def server_name_autocomplete_wrapper(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete wrapper for server name."""
        return await self.server_name_autocomplete(interaction, current)

    @app_commands.command(
        name="updatestatus", 
        description="📊 Check ARK server update status for all servers (admin only)"
    )
    async def check_update_status(self, interaction: discord.Interaction):
        """Check update status for all servers."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            from bot.utils.ark_version import check_server_update_status
            
            servers = await server_config_db.get_ark_servers(interaction.guild_id)
            
            if not servers:
                await interaction.followup.send(
                    "❌ No servers configured. Use `/addserver` to add a server.", ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="📊 ARK Server Update Status",
                description="Checking for available updates...",
                color=discord.Color.blue(),
            )
            
            # Check each server
            for server in servers:
                if not server.get("enabled", True):
                    continue
                
                status_check = await check_server_update_status(
                    server["id"],
                    server.get("server_path"),
                    server.get("steamcmd_path")
                )
                
                # Build status line
                if status_check["error"]:
                    status_line = f"❌ Error: {status_check['error']}"
                elif status_check["update_needed"]:
                    status_line = f"⚠️ **UPDATE AVAILABLE**\nCurrent: {status_check['current_version']}\nLatest: {status_check['latest_version']}"
                else:
                    status_line = f"✅ Up to date\nVersion: {status_check['current_version']}"
                
                embed.add_field(
                    name=f"🖥️ {server['name']}",
                    value=status_line,
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in updatestatus command: {e}")
            await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)

    @app_commands.command(
        name="config", description="📋 View current bot configuration (admin only)"
    )
    async def view_config(self, interaction: discord.Interaction):
        """View current bot configuration."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            config = await server_config_db.get_server_config(interaction.guild_id)

            if not config:
                await interaction.followup.send(
                    "❌ Bot not configured yet. Use `/setup` to get started!", ephemeral=True
                )
                return

            embed = discord.Embed(title="⚙️ Bot Configuration", color=discord.Color.blue())

            # Hosting Type
            hosting_type = await server_config_db.get_hosting_type(interaction.guild_id)
            hosting_display = "🏠 Self-Hosted" if hosting_type == "self_hosted" else "☁️ Nitrado"
            embed.add_field(name="🖥️ Hosting Type", value=hosting_display, inline=False)

            # Channels
            channels_value = ""
            if config.get("chat_channel_id"):
                channels_value += f"💬 Chat: <#{config['chat_channel_id']}>\n"
            if config.get("status_channel_id"):
                channels_value += f"📊 Status: <#{config['status_channel_id']}>\n"
            if config.get("shop_channel_id"):
                channels_value += f"🛒 Shop: <#{config['shop_channel_id']}>\n"
            if config.get("admin_log_channel_id"):
                channels_value += f"📝 Admin Log: <#{config['admin_log_channel_id']}>\n"
            if config.get("server_log_channel_id"):
                channels_value += f"🖥️ Server Log: <#{config['server_log_channel_id']}>\n"
            if channels_value:
                embed.add_field(name="📺 Channels", value=channels_value, inline=False)

            # Admin Role
            if config.get("admin_role_id"):
                embed.add_field(
                    name="👑 Admin Role", value=f"<@&{config['admin_role_id']}>", inline=False
                )

            # Shop Settings
            shop_value = f"**Enabled:** {'✅' if config.get('shop_enabled') else '❌'}\n"
            shop_value += f"**Items/Page:** {config.get('shop_items_per_page', 10)}\n"
            shop_value += f"**Starting Balance:** {config.get('shop_starting_balance', 1000)}\n"
            shop_value += f"**Daily Bonus:** {config.get('shop_daily_login_bonus', 100)}\n"
            shop_value += f"**Refunds:** {'✅' if config.get('shop_allow_refunds') else '❌'}"
            embed.add_field(name="🛒 Shop Settings", value=shop_value, inline=False)

            # Server Count
            servers = await server_config_db.get_ark_servers(interaction.guild_id)
            embed.add_field(name="🖥️ ARK Servers", value=f"{len(servers)} configured", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in config command: {e}")
            await interaction.followup.send(f"❌ An error occurred: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Setup(bot))
