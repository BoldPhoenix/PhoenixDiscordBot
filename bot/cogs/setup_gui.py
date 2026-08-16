"""
Setup GUI - Interactive configuration wizard for bot setup.
Provides a visual interface for all initial configuration options.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button, Modal, TextInput
from typing import Optional
import logging
import asyncio

from bot.database import server_config_db
from bot.rcon.simple_client import SimpleRCONClient
from bot.utils.log_parser import detect_cluster_ids_from_filesystem

logger = logging.getLogger("SetupGUI")


async def _sync_agent_config(bot, guild_id: int) -> None:
    """Push the guild's current server list to its connected remote agent(s).

    Called after every ark-server add/edit/remove: without this, an already-
    connected agent keeps its stale in-memory server list and maintain_server
    fails with "Server 'X' not found in config" (field bug 2026-07-03, new
    Genesis map server). Never raises - config sync must not break the GUI.
    """
    try:
        manager = getattr(bot, "agent_manager", None)
        if manager is None:
            return
        await manager.push_server_config(guild_id)
    except Exception as e:
        logger.warning(f"Agent config sync failed for guild {guild_id}: {e}")


async def _sync_agent_config_for(interaction) -> None:
    """Interaction-shaped wrapper: ALL attribute access inside the guard, so a
    test double (or odd interaction) can never break the write path."""
    try:
        await _sync_agent_config_for(interaction)
    except Exception as e:
        logger.warning(f"Agent config sync skipped: {e}")


class SetupView(View):
    """Main setup configuration interface."""

    def __init__(self, guild_id: int, user: discord.User):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user = user
        self.config = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This setup panel is not for you!", ephemeral=True
            )
            return False
        return True

    async def load_config(self):
        """Load current configuration."""
        self.config = await server_config_db.get_server_config(self.guild_id)

    async def create_main_embed(self) -> discord.Embed:
        """Create the main setup embed."""
        embed = discord.Embed(
            title="🛠️ Bot Setup & Configuration",
            description=(
                "Welcome to the interactive setup wizard!\n"
                "Configure your bot settings using the buttons below.\n\n"
                "**Current Status:** " + ("✅ Configured" if self.config else "⚠️ Not Configured")
            ),
            color=discord.Color.blue(),
        )

        # Show simplified configuration if exists
        if self.config:
            # Hosting Type
            hosting_type = self.config.get("hosting_type", "self_hosted")
            hosting_display = "🏠 Self-Hosted" if hosting_type == "self_hosted" else "☁️ Nitrado"
            embed.add_field(name="🖥️ Hosting Type", value=hosting_display, inline=True)

            # Admin Role
            if self.config.get("admin_role_id"):
                embed.add_field(
                    name="👑 Admin Role", value=f"<@&{self.config['admin_role_id']}>", inline=True
                )
            else:
                embed.add_field(name="👑 Admin Role", value="Not Set", inline=True)

            # User Role
            if self.config.get("user_role_id"):
                embed.add_field(
                    name="👤 User Role", value=f"<@&{self.config['user_role_id']}>", inline=True
                )
            else:
                embed.add_field(name="👤 User Role", value="Not Set (all users)", inline=True)

            # Agent Status (if bot is available) - only show for premium/lifetime
            if hasattr(self, 'bot') and self.bot:
                from bot.database import subscription_db, remote_agent_db
                try:
                    sub = await subscription_db.get_or_create_subscription(self.guild_id)
                    tier = subscription_db.get_effective_tier(sub)
                    
                    if tier in ("premium", "lifetime"):
                        # Get registered agents from database for this guild
                        registered_agents = await remote_agent_db.get_remote_agents(self.guild_id)
                        agent_count = len(registered_agents)
                        
                        # Count connected agents via shared bot.agent_manager
                        # (cog class is RemoteAgentCommands; bot.agent_manager is the shared instance)
                        connected_count = 0
                        agent_manager = getattr(self.bot, 'agent_manager', None)
                        if agent_manager:
                            connected_count = sum(1 for agent in registered_agents if agent["agent_id"] in agent_manager.connections)
                        
                        if agent_count == 0:
                            agent_status = "🔴 No Agents"
                        elif connected_count > 0:
                            agent_status = f"🟢 {connected_count}/{agent_count} Connected"
                        else:
                            agent_status = f"🔴 0/{agent_count} Connected"
                        embed.add_field(name="🌐 Remote Agent", value=agent_status, inline=True)
                except Exception:
                    pass  # Silently skip if there's an issue
        else:
            embed.add_field(
                name="📋 Getting Started",
                value=(
                    "1️⃣ Set your **Hosting Type** (Self-Hosted or Nitrado)\n"
                    "2️⃣ Configure your **Discord Channels**\n"
                    "3️⃣ Set an **Admin Role** for bot management\n"
                    "4️⃣ Configure **Shop Settings** (optional)\n"
                    "5️⃣ Add your **ARK Servers**"
                ),
                inline=False,
            )

        embed.set_footer(text="💡 Click a button below to configure each section")
        return embed


class SetupMainView(SetupView):
    """Main setup view with category buttons."""

    def __init__(
        self, guild_id: int, user: discord.User, guild: discord.Guild, bot: commands.Bot = None
    ):
        super().__init__(guild_id, user)
        self.guild = guild
        self.bot = bot

        # Add category buttons
        self.add_item(SetupCategoryButton("Hosting Type", "🖥️", "hosting"))
        self.add_item(SetupCategoryButton("Channels", "📺", "channels"))
        self.add_item(SetupCategoryButton("Admin Role", "👑", "admin"))
        self.add_item(SetupCategoryButton("User Role", "👤", "userrole"))
        self.add_item(SetupCategoryButton("Shop", "🛒", "shop"))
        self.add_item(SetupCategoryButton("Economy", "💰", "economy"))
        self.add_item(SetupCategoryButton("Cluster Settings", "🔗", "cluster"))
        self.add_item(SetupCategoryButton("Manage Servers", "⚙️", "manageservers"))
        self.add_item(SetupCategoryButton("Agent Control", "🌐", "botcontrol"))


class SetupCategoryButton(Button):
    """Button for setup categories."""

    def __init__(self, label: str, emoji: str, category: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=label,
            emoji=emoji,
            custom_id=f"setup_{category}",
        )
        self.category = category

    async def callback(self, interaction: discord.Interaction):
        view: SetupMainView = self.view
        logger.info(f"SetupCategoryButton callback triggered: category={self.category}")

        if self.category == "hosting":
            # Show hosting type selection
            hosting_view = HostingTypeView(view.guild_id, view.user)
            await hosting_view.load_config()
            embed = hosting_view.create_embed()
            await interaction.response.send_message(embed=embed, view=hosting_view, ephemeral=True)

        elif self.category == "channels":
            # Show channel configuration
            channel_view = ChannelConfigView(view.guild_id, view.user, view.guild)
            await channel_view.load_config()
            embed = channel_view.create_embed()
            await interaction.response.send_message(embed=embed, view=channel_view, ephemeral=True)

        elif self.category == "admin":
            # Show admin role selection
            admin_view = AdminRoleView(view.guild_id, view.user, view.guild)
            await admin_view.load_config()
            embed = admin_view.create_embed()
            await interaction.response.send_message(embed=embed, view=admin_view, ephemeral=True)

        elif self.category == "userrole":
            # Show user role selection
            user_view = UserRoleView(view.guild_id, view.user, view.guild)
            await user_view.load_config()
            embed = user_view.create_embed()
            await interaction.response.send_message(embed=embed, view=user_view, ephemeral=True)

        elif self.category == "shop":
            # Open shopcfg GUI directly
            from bot.cogs.shopcfg_gui import ShopCfgCog, ShopCfgMainView
            
            # Get or create the ShopCfgCog instance
            shopcfg_cog = interaction.client.get_cog("ShopCfgCog")
            if not shopcfg_cog:
                await interaction.response.send_message(
                    "❌ Shop configuration system not loaded. Please contact the bot owner.",
                    ephemeral=True
                )
                return
            
            # Check admin permission
            if not await shopcfg_cog.is_admin(interaction):
                await interaction.response.send_message(
                    "❌ You need Administrator permission to configure the shop.",
                    ephemeral=True
                )
                return
            
            # Open the shopcfg main view
            await interaction.response.send_message(
                embed=shopcfg_cog._build_main_embed(),
                view=ShopCfgMainView(shopcfg_cog),
                ephemeral=True
            )

        elif self.category == "cluster":
            # Show cluster settings view
            cluster_view = ClusterSettingsView(view.guild_id, view.user, view.bot)
            await cluster_view.load_config()
            embed = await cluster_view.create_embed()
            await interaction.response.send_message(embed=embed, view=cluster_view, ephemeral=True)

        elif self.category == "manageservers":
            # Show server management view
            server_view = ManageServersView(view.guild_id, view.user, view.guild)
            await server_view.load_servers()
            embed = server_view.create_embed()
            await interaction.response.send_message(embed=embed, view=server_view, ephemeral=True)
            # Capture the message for refresh capability
            server_view.message = await interaction.original_response()

        elif self.category == "botcontrol":
            # Show remote agent management panel
            from bot.cogs.remote_agent_gui import AgentControlView
            from bot.database import remote_agent_db

            agent_manager = view.bot.agent_manager
            agent_view = AgentControlView(view.guild_id, view.user, agent_manager)

            # Get agents for THIS guild only from database
            guild_agents = await remote_agent_db.get_remote_agents(view.guild_id)
            agents_count = len(guild_agents)
            
            # Count how many are currently connected
            connected_count = sum(1 for agent in guild_agents if agent["agent_id"] in agent_manager.connections)
            
            ark_servers = await server_config_db.get_ark_servers(interaction.guild_id)
            servers_count = len(ark_servers)

            embed = discord.Embed(
                title="🌐 Agent Control",
                description="Manage your remote ARK server agents",
                color=discord.Color.blue(),
            )
            embed.add_field(name="🤖 Registered Agents", value=str(agents_count), inline=True)
            embed.add_field(
                name="📡 Connection Status",
                value=f"🟢 {connected_count} Connected" if connected_count > 0 else "🔴 Offline",
                inline=True,
            )
            embed.set_footer(text="Use the buttons below to manage your remote agents")
            await interaction.response.send_message(embed=embed, view=agent_view, ephemeral=True)

        elif self.category == "economy":
            # Open economy config GUI
            from bot.cogs.economy import EconomyAdminPanel, economy_db
            
            settings = await economy_db.get_economy_settings(view.guild_id)
            roles = await economy_db.get_economy_roles(view.guild_id)
            
            panel = EconomyAdminPanel(view.guild_id, settings, roles)
            embed = panel.build_embed()
            await interaction.response.send_message(embed=embed, view=panel, ephemeral=True)

        elif self.category == "servicemgmt":
            # Show service management view (Phase 16)
            logger.info("servicemgmt: Starting...")
            await interaction.response.defer(ephemeral=True)
            logger.info("servicemgmt: Deferred, creating view...")
            try:
                service_view = ServiceManagementView(view.guild_id, view.user, view.bot)
                logger.info("servicemgmt: View created, sending initial message...")
                
                # Send message immediately with "Loading..." state
                embed = await service_view.create_embed()
                msg = await interaction.followup.send(embed=embed, view=service_view, ephemeral=True)
                service_view.message = msg
                logger.info("servicemgmt: Initial message sent, loading services in background...")
                
                # Load services in background and refresh
                await service_view.load_services()
                logger.info("servicemgmt: Services loaded, refreshing message...")
                await service_view.refresh()
                logger.info("servicemgmt: Done!")
            except Exception as e:
                logger.error(f"Error loading service management view: {e}", exc_info=True)
                await interaction.followup.send(f"❌ Error loading service management: {e}", ephemeral=True)


class HostingTypeView(SetupView):
    """View for selecting hosting type."""

    def __init__(self, guild_id: int, user: discord.User):
        super().__init__(guild_id, user)

        self.add_item(HostingTypeButton("Self-Hosted", "🏠", "self_hosted"))
        self.add_item(HostingTypeButton("Nitrado", "☁️", "nitrado"))

    def create_embed(self) -> discord.Embed:
        """Create hosting type selection embed."""
        current = "Not Set"
        if self.config:
            hosting = self.config.get("hosting_type", "self_hosted")
            current = "🏠 Self-Hosted" if hosting == "self_hosted" else "☁️ Nitrado"

        embed = discord.Embed(
            title="🖥️ Hosting Type Configuration",
            description=f"**Current Setting:** {current}\n\nSelect your server hosting type:",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="🏠 Self-Hosted",
            value=(
                "For servers running on your own machine\n"
                "• Phoenix service control (start/stop/restart)\n"
                "• Local log file viewing\n"
                "• Crash monitoring & diagnostics\n"
                "• Full server management"
            ),
            inline=True,
        )

        embed.add_field(
            name="☁️ Nitrado",
            value=(
                "For servers hosted by Nitrado\n"
                "• Live server monitoring (RCON)\n"
                "• RCON commands & player management\n"
                "• Voice channel status updates\n"
                "• Chat relay\n"
                "• Shop & economy system"
            ),
            inline=True,
        )

        return embed


class HostingTypeButton(Button):
    """Button for hosting type selection."""

    def __init__(self, label: str, emoji: str, hosting_type: str):
        super().__init__(
            style=(
                discord.ButtonStyle.success
                if hosting_type == "self_hosted"
                else discord.ButtonStyle.primary
            ),
            label=label,
            emoji=emoji,
        )
        self.hosting_type = hosting_type

    async def callback(self, interaction: discord.Interaction):
        view: HostingTypeView = self.view

        # Ensure config exists
        await server_config_db.create_or_update_server_config(view.guild_id, interaction.guild.name)

        # Set hosting type
        await server_config_db.set_hosting_type(view.guild_id, self.hosting_type)

        display = "🏠 Self-Hosted" if self.hosting_type == "self_hosted" else "☁️ Nitrado"

        embed = discord.Embed(
            title="✅ Hosting Type Updated",
            description=f"Server hosting type set to: **{display}**",
            color=discord.Color.green(),
        )

        await interaction.response.edit_message(embed=embed, view=None)


class ChannelConfigView(SetupView):
    """View for configuring Discord channels."""

    def __init__(self, guild_id: int, user: discord.User, guild: discord.Guild):
        super().__init__(guild_id, user)
        self.guild = guild

        self.add_item(ChannelSelectButton("Chat Channel", "💬", "chat"))
        self.add_item(ChannelSelectButton("Status Channel", "📊", "status"))
        self.add_item(ChannelSelectButton("Shop Channel", "🛒", "shop"))
        self.add_item(ChannelSelectButton("Admin Log Channel", "📝", "admin_log"))
        self.add_item(ChannelSelectButton("Server Log Channel", "🖥️", "server_log"))
        self.add_item(ChannelSelectButton("Server Status Category", "🔊", "voice_category"))
        self.add_item(ChannelSelectButton("Mod Channel", "📦", "mod"))
        self.add_item(ChannelSelectButton("Economy Channel", "💰", "economy"))
        self.add_item(ChannelSelectButton("Events Channel", "🎉", "events"))

    def create_embed(self) -> discord.Embed:
        """Create channel configuration embed."""
        embed = discord.Embed(
            title="📺 Channel Configuration",
            description="Configure the Discord channels for bot features.\nClick a button to select a channel.",
            color=discord.Color.blue(),
        )

        if self.config:
            chat_ch = (
                f"<#{self.config['chat_channel_id']}>"
                if self.config.get("chat_channel_id")
                else "❌ Not Set"
            )
            status_ch = (
                f"<#{self.config['status_channel_id']}>"
                if self.config.get("status_channel_id")
                else "❌ Not Set"
            )
            shop_ch = (
                f"<#{self.config['shop_channel_id']}>"
                if self.config.get("shop_channel_id")
                else "❌ Not Set"
            )
            admin_log_ch = (
                f"<#{self.config['admin_log_channel_id']}>"
                if self.config.get("admin_log_channel_id")
                else "❌ Not Set"
            )
            server_log_ch = (
                f"<#{self.config['server_log_channel_id']}>"
                if self.config.get("server_log_channel_id")
                else "❌ Not Set"
            )
            voice_cat = (
                f"<#{self.config['voice_category_id']}>"
                if self.config.get("voice_category_id")
                else "❌ Not Set"
            )
            mod_ch = (
                f"<#{self.config['mod_channel_id']}>"
                if self.config.get("mod_channel_id")
                else "❌ Not Set"
            )
            economy_ch = (
                f"<#{self.config['economy_channel_id']}>"
                if self.config.get("economy_channel_id")
                else "❌ Not Set"
            )
            events_ch = (
                f"<#{self.config['events_channel_id']}>"
                if self.config.get("events_channel_id")
                else "❌ Not Set"
            )
        else:
            chat_ch = status_ch = shop_ch = "❌ Not Set"
            admin_log_ch = server_log_ch = voice_cat = "❌ Not Set"
            mod_ch = economy_ch = events_ch = "❌ Not Set"

        embed.add_field(
            name="💬 Chat Channel", value=f"Cross-server chat relay\n{chat_ch}", inline=True
        )
        embed.add_field(
            name="📊 Status Channel", value=f"Health status embeds\n{status_ch}", inline=True
        )
        embed.add_field(name="🛒 Shop Channel", value=f"Purchase logs\n{shop_ch}", inline=True)
        embed.add_field(name="📝 Admin Log Channel", value=f"Admin RCON commands\n{admin_log_ch}", inline=True)
        embed.add_field(
            name="🖥️ Server Log Channel", value=f"Server updates/reboots\n{server_log_ch}", inline=True
        )
        embed.add_field(
            name="🔊 Server Status Category", value=f"Server status voice channels\n{voice_cat}", inline=True
        )
        embed.add_field(
            name="📦 Mod Channel", value=f"Installed mods list\n{mod_ch}", inline=True
        )
        embed.add_field(
            name="💰 Economy Channel", value=f"Payday logs\n{economy_ch}", inline=True
        )
        embed.add_field(
            name="🎉 Events Channel", value=f"Event info/transactions\n{events_ch}", inline=True
        )

        return embed


class ChannelSelectButton(Button):
    """Button to open channel selection."""

    def __init__(self, label: str, emoji: str, channel_type: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=label, emoji=emoji)
        self.channel_type = channel_type

    async def callback(self, interaction: discord.Interaction):
        view: ChannelConfigView = self.view

        # Create channel select view
        select_view = ChannelSelectView(
            view.guild_id, view.user, view.guild, self.channel_type, self.label
        )

        embed = discord.Embed(
            title=f"Select {self.label}",
            description="Choose a channel from the dropdown below:",
            color=discord.Color.blue(),
        )

        await interaction.response.edit_message(embed=embed, view=select_view)


class ChannelSelectView(View):
    """View with channel selector dropdown."""

    def __init__(
        self,
        guild_id: int,
        user: discord.User,
        guild: discord.Guild,
        channel_type: str,
        channel_label: str,
    ):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user = user
        self.channel_type = channel_type
        self.channel_label = channel_label

        # Add channel select - voice_category needs category type, others need text
        if channel_type == "voice_category":
            select = discord.ui.ChannelSelect(
                placeholder=f"Select {channel_label}...",
                channel_types=[discord.ChannelType.category],
                custom_id="channel_select",
            )
        else:
            select = discord.ui.ChannelSelect(
                placeholder=f"Select {channel_label}...",
                channel_types=[discord.ChannelType.text],
                custom_id="channel_select",
            )
        select.callback = self.channel_callback
        self.add_item(select)

    async def channel_callback(self, interaction: discord.Interaction):
        """Handle channel selection."""
        channel = interaction.data["values"][0]
        channel_id = int(channel)

        # Map channel type to database field
        field_map = {
            "chat": "chat_channel_id",
            "status": "status_channel_id",
            "shop": "shop_channel_id",
            "admin_log": "admin_log_channel_id",
            "server_log": "server_log_channel_id",
            "voice_category": "voice_category_id",
            "mod": "mod_channel_id",
            "economy": "economy_channel_id",
            "events": "events_channel_id",
        }

        field = field_map.get(self.channel_type)
        if field:
            await server_config_db.create_or_update_server_config(
                self.guild_id, interaction.guild.name, **{field: channel_id}
            )

        config = await server_config_db.get_server_config(self.guild_id)
        view = ChannelConfigView(self.guild_id, self.user, interaction.guild)
        view.config = config
        await interaction.response.edit_message(embed=view.create_embed(), view=view)


class AdminRoleView(SetupView):
    """View for selecting admin role."""

    def __init__(self, guild_id: int, user: discord.User, guild: discord.Guild):
        super().__init__(guild_id, user)
        self.guild = guild

        # Add role select
        select = discord.ui.RoleSelect(
            placeholder="Select Admin Role...", custom_id="admin_role_select"
        )
        select.callback = self.role_callback
        self.add_item(select)

    async def role_callback(self, interaction: discord.Interaction):
        """Handle role selection."""
        role_id = int(interaction.data["values"][0])

        await server_config_db.create_or_update_server_config(
            self.guild_id, interaction.guild.name, admin_role_id=role_id
        )

        embed = discord.Embed(
            title="✅ Admin Role Updated",
            description=f"Admin role set to <@&{role_id}>\n\nUsers with this role can manage the bot.",
            color=discord.Color.green(),
        )

        await interaction.response.edit_message(embed=embed, view=None)

    def create_embed(self) -> discord.Embed:
        """Create admin role selection embed."""
        current = "Not Set"
        if self.config and self.config.get("admin_role_id"):
            current = f"<@&{self.config['admin_role_id']}>"

        embed = discord.Embed(
            title="👑 Admin Role Configuration",
            description=(
                f"**Current Admin Role:** {current}\n\n"
                "Select the role that can manage bot settings.\n"
                "Users with this role will be able to:\n"
                "• Add/remove ARK servers\n"
                "• Grant Phoenix Coins\n"
                "• Manage shop items\n"
                "• Execute RCON commands\n"
                "• Access server controls"
            ),
            color=discord.Color.gold(),
        )

        return embed


class UserRoleView(SetupView):
    """View for selecting user role."""

    def __init__(self, guild_id: int, user: discord.User, guild: discord.Guild):
        super().__init__(guild_id, user)
        self.guild = guild

        # Add role select
        select = discord.ui.RoleSelect(
            placeholder="Select User Role...", custom_id="user_role_select"
        )
        select.callback = self.role_callback
        self.add_item(select)

    async def role_callback(self, interaction: discord.Interaction):
        """Handle role selection."""
        role_id = int(interaction.data["values"][0])

        await server_config_db.create_or_update_server_config(
            self.guild_id, interaction.guild.name, user_role_id=role_id
        )

        embed = discord.Embed(
            title="✅ User Role Updated",
            description=f"User role set to <@&{role_id}>\n\nUsers with this role can use bot features like:\n• Shop purchases\n• Kit claims\n• Link their accounts",
            color=discord.Color.green(),
        )

        await interaction.response.edit_message(embed=embed, view=None)

    def create_embed(self) -> discord.Embed:
        """Create user role selection embed."""
        current = "Not Set (all users can access)"
        if self.config and self.config.get("user_role_id"):
            current = f"<@&{self.config['user_role_id']}>"

        embed = discord.Embed(
            title="👤 User Role Configuration",
            description=(
                f"**Current User Role:** {current}\n\n"
                "Select the role required to use bot features.\n"
                "Users with this role will be able to:\n"
                "• Use the shop and purchase items\n"
                "• Claim starter kits\n"
                "• Link their Discord to in-game characters\n"
                "• View server status\n\n"
                "**Note:** Leave unset to allow all users.\n"
                "Admin role members bypass this check."
            ),
            color=discord.Color.blue(),
        )

        return embed


# ShopSettingsModal removed - all shop configuration now handled by /shopcfg command


class ClusterSettingsView(SetupView):
    """View for cluster configuration."""

    def __init__(self, guild_id: int, user: discord.User, bot: commands.Bot = None):
        super().__init__(guild_id, user)
        self.bot = bot

        self.add_item(ConfigureClusterButton())
        self.add_item(RefreshClusterButton())

    async def create_embed(self) -> discord.Embed:
        """Create cluster settings embed."""
        embed = discord.Embed(
            title="🔗 Cluster Settings",
            description="Configure your ARK cluster settings for cross-server functionality.",
            color=discord.Color.blue(),
        )

        # Show current settings
        if self.config:
            cluster_root = self.config.get("cluster_root_path") or "Not Set"
            
            embed.add_field(
                name="📁 Cluster Root Path", value=f"`{cluster_root}`", inline=False
            )

            # Detect cluster IDs via remote agent if cluster root is set
            detected_clusters = []
            if cluster_root and cluster_root != "Not Set" and self.bot:
                try:
                    agent_manager = self.bot.agent_manager
                    if agent_manager and len(agent_manager.agents) > 0:
                        # Get first available agent
                        agent_id = list(agent_manager.agents.keys())[0]
                        
                        # Send detect_cluster_ids command to agent
                        result = await agent_manager.send_command(
                            agent_id,
                            "detect_cluster_ids",
                            params={"cluster_root_path": cluster_root}
                        )
                        
                        # Agent returns data in result["data"]["cluster_ids"]
                        if result and result.get("data") and "cluster_ids" in result["data"]:
                            detected_clusters = result["data"]["cluster_ids"]
                except Exception as e:
                    logger.error(f"Failed to detect cluster IDs via remote agent: {e}")
            
            if detected_clusters:
                cluster_list = "\n".join([f"• `{cid}`" for cid in detected_clusters])
                embed.add_field(
                    name=f"🆔 Detected Cluster IDs ({len(detected_clusters)})",
                    value=cluster_list,
                    inline=False
                )
            else:
                embed.add_field(
                    name="🆔 Detected Cluster IDs",
                    value="No clusters detected yet (requires remote agent)",
                    inline=False
                )

            embed.add_field(
                name="ℹ️ How It Works",
                value=(
                    "• **Cluster Root Path**: Set to your cluster storage location\n"
                    "• **Cluster IDs**: Auto-detected via remote agent scanning `<root>/clusters/`\n"
                    "• Each folder in `clusters/` represents a cluster ID\n"
                    "• Click **Refresh** to re-scan for cluster IDs"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="Getting Started",
                value=(
                    "Click **Configure Cluster** to set your cluster root path.\n\n"
                    "Example: `R:\\PhoenixArk\\PhoenixArkCluster`\n\n"
                    "Cluster IDs will be auto-detected from the `clusters/` subdirectory."
                ),
                inline=False,
            )

        return embed


class RefreshClusterButton(Button):
    """Button to refresh cluster settings view."""

    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Refresh", emoji="🔄")

    async def callback(self, interaction: discord.Interaction):
        view: ClusterSettingsView = self.view
        await view.load_config()
        embed = await view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class ConfigureClusterButton(Button):
    """Button to open cluster configuration modal."""

    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Configure Cluster", emoji="⚙️")

    async def callback(self, interaction: discord.Interaction):
        view: ClusterSettingsView = self.view
        modal = ClusterSettingsModal(view.guild_id, view.config, parent_view=view)
        await interaction.response.send_modal(modal)


class ClusterSettingsModal(Modal):
    """Modal for configuring cluster settings."""

    def __init__(self, guild_id: int, config: dict = None, parent_view=None):
        super().__init__(title="🔗 Cluster Configuration")
        self.guild_id = guild_id
        self.parent_view = parent_view

        # Pre-fill with current value
        cluster_root = config.get("cluster_root_path", "") if config else ""

        self.cluster_root_path = TextInput(
            label="Cluster Root Path",
            placeholder="e.g., D:\\ARK\\Cluster or /ark/cluster",
            default=cluster_root,
            required=False,
            max_length=255,
            style=discord.TextStyle.short,
        )
        self.add_item(self.cluster_root_path)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cluster_root = self.cluster_root_path.value.strip() or None

            await server_config_db.create_or_update_server_config(
                self.guild_id, interaction.guild.name, cluster_root_path=cluster_root
            )

            embed = discord.Embed(
                title="✅ Cluster Settings Updated",
                description="Your cluster configuration has been saved.\n\n**Click the 🔄 Refresh button** to see the updated values.",
                color=discord.Color.green(),
            )

            if cluster_root:
                embed.add_field(
                    name="📁 Cluster Root Path", value=f"`{cluster_root}`", inline=False
                )
                embed.add_field(
                    name="ℹ️ Next Steps",
                    value=(
                        "Cluster ID and Folder Path will be auto-detected from your server logs.\n"
                        "Make sure your servers are configured to use this cluster path."
                    ),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="📁 Cluster Root Path", value="Cleared (not set)", inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to update cluster settings: {str(e)}", ephemeral=True
            )


class AddServerModal(Modal):
    """Modal for adding an ARK server - Page 1: Basic Connection Info."""

    def __init__(self, guild_id: int, parent_view: "ManageServersView" = None):
        super().__init__(title="➕ Add Server (1/2): Connection")
        self.guild_id = guild_id
        self.parent_view = parent_view

        self.server_name = TextInput(
            label="Server Name",
            placeholder="e.g., Island, Ragnarok, Center",
            required=True,
            max_length=50,
        )
        self.add_item(self.server_name)

        self.host = TextInput(
            label="Server IP Address (⚠️ NOT 127.0.0.1)",
            placeholder="e.g., 192.168.1.100 or game.example.com",
            required=True,
            max_length=100,
        )
        self.add_item(self.host)

        self.rcon_port = TextInput(
            label="RCON Port", placeholder="e.g., 27020", required=True, max_length=6
        )
        self.add_item(self.rcon_port)

        self.rcon_password = TextInput(
            label="RCON Password",
            placeholder="Your server's RCON password",
            required=True,
            max_length=100,
        )
        self.add_item(self.rcon_password)

        self.game_port = TextInput(
            label="Game Port (optional)",
            placeholder="e.g., 7777",
            required=False,
            max_length=6,
        )
        self.add_item(self.game_port)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rcon_port = int(self.rcon_port.value)
            game_port = int(self.game_port.value) if self.game_port.value else None

            # Test RCON connectivity first
            await interaction.response.defer(ephemeral=True)
            
            # Show progress message during RCON test
            progress_msg = await interaction.followup.send(
                embed=discord.Embed(
                    title="🔄 Testing RCON Connection...",
                    description=f"Connecting to **{self.host.value}:{self.rcon_port.value}**\n\nThis may take up to 10 seconds...",
                    color=discord.Color.blue(),
                ),
                ephemeral=True,
                wait=True
            )

            test_result = await self._test_rcon_connection()
            rcon_failed = not test_result["success"]

            # Store data and show intermediate view with "Continue Setup" button
            server_data = {
                "name": self.server_name.value,
                "host": self.host.value,
                "rcon_port": rcon_port,
                "rcon_password": self.rcon_password.value,
                "game_port": game_port,
                "rcon_test_result": test_result,
                "rcon_failed": rcon_failed,
            }
            
            embed = discord.Embed(
                title="✅ Step 1 Complete: Connection Info Saved",
                description=f"**{self.server_name.value}** connection details validated.",
                color=discord.Color.green() if not rcon_failed else discord.Color.orange(),
            )
            
            if rcon_failed:
                embed.add_field(
                    name="⚠️ RCON Connection Warning",
                    value=f"Could not connect: {test_result['error']}\n\nYou can still continue setup and fix connectivity later.",
                    inline=False,
                )
            else:
                embed.add_field(
                    name="✅ RCON Connection Verified",
                    value="Successfully connected to server via RCON.",
                    inline=False,
                )
            
            embed.add_field(
                name="📋 Next Step",
                value="Click **Continue Setup** to configure advanced settings (paths, service name, max players).",
                inline=False,
            )
            
            # Replace the progress message with the result
            view = AddServerContinueView(self.guild_id, server_data, self.parent_view, progress_msg)
            await progress_msg.edit(embed=embed, view=view)


        except ValueError:
            await interaction.followup.send(
                "❌ Invalid port number! Ports must be numbers.", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in EditServerModal: {e}")
            await interaction.followup.send(f"❌ Error editing server: {e}", ephemeral=True)

    async def _test_rcon_connection(self) -> dict:
        """Test RCON connectivity with provided credentials."""
        try:
            rcon_port = int(self.rcon_port.value)

            client = SimpleRCONClient(
                host=self.host.value,
                port=rcon_port,
                password=self.rcon_password.value,
                timeout=10.0,
            )

            # Try to connect and authenticate
            connected = await asyncio.wait_for(client.connect(), timeout=10.0)

            if connected:
                # Try a simple command to verify execution
                try:
                    result = await asyncio.wait_for(client.execute("GetChat"), timeout=5.0)
                    await client.disconnect()
                    return {"success": True}
                except Exception as cmd_error:
                    await client.disconnect()
                    # Connection worked but command failed - still consider success
                    # since the auth was successful
                    logger.debug(f"Command test failed but auth succeeded: {cmd_error}")
                    return {"success": True}
            else:
                return {"success": False, "error": "Authentication failed - check password"}

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Connection timeout - server may be offline or unreachable",
            }
        except ConnectionRefusedError:
            return {"success": False, "error": "Connection refused - check IP address and port"}
        except OSError as e:
            return {"success": False, "error": f"Network error: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Unexpected error: {str(e)}"}


class AddServerContinueView(discord.ui.View):
    """Intermediate view after page 1 - shows Continue Setup button."""
    
    def __init__(self, guild_id: int, server_data: dict, parent_view: "ManageServersView" = None, message=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.server_data = server_data
        self.parent_view = parent_view
        self.message = message
    
    @discord.ui.button(label="Continue Setup →", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def continue_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the advanced settings modal."""
        modal = AddServerAdvancedModal(self.guild_id, self.server_data, self.parent_view, interaction.message)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the setup process."""
        embed = discord.Embed(
            title="❌ Server Setup Cancelled",
            description="Server was not added. You can start over anytime.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class AddServerAdvancedModal(Modal):
    """Modal for adding an ARK server - Page 2: Advanced Settings."""
    
    def __init__(self, guild_id: int, server_data: dict, parent_view: "ManageServersView" = None, message=None):
        super().__init__(title="➕ Add Server (2/2): Advanced")
        self.guild_id = guild_id
        self.server_data = server_data
        self.parent_view = parent_view
        self.message = message
        
        self.server_path = TextInput(
            label="Server Path (for log monitoring)",
            placeholder="e.g., D:\\ARK\\Island or /ark/island",
            required=False,
            max_length=255,
        )
        self.add_item(self.server_path)
        
        self.service_name = TextInput(
            label="Service Name (e.g. PhoenixArk_Aberration)",
            placeholder="e.g., ArkAberration",
            required=False,
            max_length=100,
        )
        self.add_item(self.service_name)
        
        self.max_players = TextInput(
            label="Max Players (default: 70)",
            placeholder="70",
            required=False,
            max_length=3,
        )
        self.add_item(self.max_players)
        
        self.steamcmd_path = TextInput(
            label="SteamCMD Directory (for updates)",
            placeholder="e.g., D:\\SteamCMD",
            required=False,
            max_length=255,
        )
        self.add_item(self.steamcmd_path)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Parse inputs
            server_path = self.server_path.value.strip() if self.server_path.value else None
            service_name = self.service_name.value.strip() if self.service_name.value else None
            steamcmd_path = self.steamcmd_path.value.strip() if self.steamcmd_path.value else None
            max_players = int(self.max_players.value) if self.max_players.value else 70
            
            # Check if cluster root path exists
            guild_config = await server_config_db.get_server_config(self.guild_id)
            cluster_root = guild_config.get("cluster_root_path") if guild_config else None
            
            # Validate: Must have either server_path OR cluster_root_path
            if not server_path and not cluster_root:
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="⚠️ Server Path Recommended",
                        description=(
                            "No server path provided. The bot will have limited functionality:\n"
                            "• No log-based player counting\n"
                            "• No auto-detection of settings\n"
                            "• RCON-only player tracking\n\n"
                            "You can add the server path later via `/editserver`."
                        ),
                        color=discord.Color.orange(),
                    ),
                    ephemeral=True
                )
            
            # Ensure config exists
            await server_config_db.create_or_update_server_config(
                self.guild_id, interaction.guild.name
            )
            
            # Add server with all fields
            server_id = await server_config_db.add_ark_server(
                guild_id=self.guild_id,
                name=self.server_data["name"],
                host=self.server_data["host"],
                rcon_port=self.server_data["rcon_port"],
                rcon_password=self.server_data["rcon_password"],
                game_port=self.server_data.get("game_port"),
                server_path=server_path,
                service_name=service_name,
                steamcmd_path=steamcmd_path,
                max_players=max_players,
            )
            await _sync_agent_config_for(interaction)
            
            # Create success embed
            rcon_failed = self.server_data.get("rcon_failed", False)
            
            if rcon_failed:
                embed = discord.Embed(
                    title="⚠️ Server Added (RCON Connection Failed)",
                    description=f"**{self.server_data['name']}** has been saved, but RCON connection could not be verified.",
                    color=discord.Color.orange(),
                )
                embed.add_field(
                    name="⚠️ Connection Issue",
                    value=f"**Error:** {self.server_data['rcon_test_result']['error']}\n\n**Next Steps:**\n• Verify firewall/port forwarding\n• Check IP address and RCON port\n• Edit server to update credentials\n• Server will appear offline until RCON connects",
                    inline=False,
                )
            else:
                embed = discord.Embed(
                    title="✅ Server Added Successfully",
                    description=f"**{self.server_data['name']}** has been added and verified!",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Status", value="✅ RCON Connection Verified", inline=False)
            
            embed.add_field(name="Host", value=self.server_data["host"], inline=True)
            embed.add_field(name="RCON Port", value=str(self.server_data["rcon_port"]), inline=True)
            embed.add_field(name="Max Players", value=str(max_players), inline=True)
            
            if server_path:
                embed.add_field(name="Server Path", value=server_path, inline=False)
            if service_name:
                embed.add_field(name="Service Name", value=service_name, inline=True)
            if steamcmd_path:
                embed.add_field(name="SteamCMD Path", value=steamcmd_path, inline=True)
            
            if server_path:
                embed.add_field(
                    name="✅ Features Enabled",
                    value="• Log-based player counting\n• Auto-detect MaxPlayers\n• Auto-detect Cluster ID/Folder",
                    inline=False,
                )
            
            # Add guidance about remote agent (only for free tier)
            from bot.database import subscription_db
            sub = await subscription_db.get_or_create_subscription(self.guild_id)
            tier = subscription_db.get_effective_tier(sub)
            
            if tier == "free":
                embed.add_field(
                    name="📝 Remote Updates (Premium/Lifetime Only)",
                    value=(
                        "⚠️ **SteamCMD Path is only active with Premium/Lifetime subscription**\n\n"
                        "To enable automated server updates:\n"
                        "1. Upgrade to Premium or Lifetime tier\n"
                        "2. Register and configure a Remote Agent\n\n"
                        "*Without Premium/Lifetime, SteamCMD path has no effect on bot operation.*"
                    ),
                    inline=False,
                )
            
            embed.set_footer(text=f"Server ID: {server_id} | You can edit this server anytime")
            
            # Create voice channel for the server immediately (before editing message)
            try:
                logger.info(f"Attempting to create voice channel for server: {self.server_data['name']} (ID: {server_id})")
                server_monitor_cog = interaction.client.get_cog("ServerMonitor")
                if server_monitor_cog:
                    logger.info(f"ServerMonitor cog found, fetching server config for ID: {server_id}")
                    server_config = await server_config_db.get_ark_server_by_id(server_id)
                    if server_config:
                        logger.info(f"Server config retrieved: {server_config.get('name')} - calling create_voice_channel_for_server")
                        result = await server_monitor_cog.create_voice_channel_for_server(self.guild_id, server_config)
                        if result:
                            logger.info(f"✅ Successfully created voice channel for: {self.server_data['name']}")
                        else:
                            logger.warning(f"⚠️ create_voice_channel_for_server returned False for: {self.server_data['name']}")
                    else:
                        logger.error(f"❌ Server config not found in database for ID: {server_id}")
                else:
                    logger.error(f"❌ ServerMonitor cog not found - cannot create voice channel")
            except Exception as e:
                logger.error(f"❌ Exception creating voice channel for new server: {e}", exc_info=True)
            
            # Send the success message
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Refresh parent view if available
            if self.parent_view:
                await self.parent_view.refresh()
        
        except ValueError as e:
            await interaction.followup.send(
                f"❌ Invalid input: {str(e)}", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in AddServerAdvancedModal: {e}")
            await interaction.followup.send(
                f"❌ Error adding server: {str(e)}", ephemeral=True
            )


# ---------------------------------------------------------------------------
# Unified 4-page server configuration wizard — shared helpers
# ---------------------------------------------------------------------------


async def _wizard_update(
    interaction: discord.Interaction,
    wizard_data: dict,
    embed: discord.Embed,
    view=None,
) -> None:
    """Send the next wizard step as a new ephemeral message.

    Uses interaction.response.send_message (most reliable for modal submits).
    Best-effort cleanup of the previous step's message via stored webhook.
    """
    # Best-effort delete of the previous step's message
    prev_webhook = wizard_data.get("_wizard_webhook")
    prev_msg_id = wizard_data.get("_wizard_msg_id")
    if prev_webhook and prev_msg_id:
        try:
            await prev_webhook.delete_message(prev_msg_id)
        except Exception:
            pass

    # Send new step — simple and reliable for modal submit interactions
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # Track this message for cleanup by the next step
    try:
        msg = await interaction.original_response()
        wizard_data["_wizard_webhook"] = interaction.followup
        wizard_data["_wizard_msg_id"] = msg.id
    except Exception:
        # Tracking failed — wizard still works, just no cleanup of this message
        wizard_data.pop("_wizard_webhook", None)
        wizard_data.pop("_wizard_msg_id", None)


async def _test_rcon_connection(host: str, port: int, password: str) -> dict:
    """Best-effort RCON connectivity test (informational only, short timeout)."""
    try:
        client = SimpleRCONClient(host=host, port=port, password=password, timeout=4.0)
        connected = await asyncio.wait_for(client.connect(), timeout=4.0)
        if connected:
            try:
                await asyncio.wait_for(client.execute("GetChat"), timeout=3.0)
            except Exception:
                pass
            await client.disconnect()
            return {"success": True}
        return {"success": False, "error": "Authentication failed — check RCON password"}
    except asyncio.TimeoutError:
        return {"success": False, "error": "Timeout — server may still be starting"}
    except ConnectionRefusedError:
        return {"success": False, "error": "Connection refused — check IP and RCON port"}
    except OSError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Unified 4-page server configuration wizard
# ---------------------------------------------------------------------------

class ConfigureServerModal1(Modal):
    """Unified wizard page 1/4 — Identity: Display Name, Map, Host, Service Name, Max Players."""

    def __init__(self, guild_id: int, parent_view=None, wizard_data: dict = None):
        super().__init__(title="Configure Server (1/4): Identity")
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.wizard_data = wizard_data.copy() if wizard_data else {}

        existing = self.wizard_data

        self.display_name = TextInput(
            label="Display Name",
            placeholder="e.g., The Island, Aberration PvP",
            default=existing.get("name", ""),
            required=True,
            max_length=100,
        )
        self.add_item(self.display_name)

        self.map_name = TextInput(
            label="Map Name",
            placeholder="e.g., TheIsland, Aberration_WP",
            default=existing.get("map_name", ""),
            required=True,
            max_length=50,
        )
        self.add_item(self.map_name)

        self.host = TextInput(
            label="Host / IP Address",
            placeholder="e.g., 192.168.1.100 or game.example.com",
            default=existing.get("host", ""),
            required=True,
            max_length=100,
        )
        self.add_item(self.host)

        self.service_name = TextInput(
            label="Service Name (Windows Service)",
            placeholder="e.g., PhoenixARK_Island",
            default=existing.get("service_name", ""),
            required=True,
            max_length=100,
        )
        self.add_item(self.service_name)

        self.max_players = TextInput(
            label="Max Players",
            placeholder="70",
            default=str(existing.get("max_players", 70)),
            required=False,
            max_length=3,
        )
        self.add_item(self.max_players)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            max_players = int(self.max_players.value) if self.max_players.value else 70
        except ValueError:
            max_players = 70

        self.wizard_data["name"] = self.display_name.value
        self.wizard_data["map_name"] = self.map_name.value
        self.wizard_data["host"] = self.host.value
        self.wizard_data["service_name"] = self.service_name.value
        self.wizard_data["max_players"] = max_players

        embed = discord.Embed(
            title="✅ (1/4): Identity Saved",
            description=f"**{self.wizard_data['name']}** — Map: `{self.wizard_data['map_name']}`",
            color=discord.Color.green(),
        )
        embed.add_field(name="Host", value=self.wizard_data["host"], inline=True)
        embed.add_field(name="Service", value=self.wizard_data["service_name"], inline=True)
        embed.add_field(
            name="📋 Next", value="Click **Continue** to configure ports and credentials.", inline=False
        )

        view = ConfigureContinueView1(self.guild_id, self.wizard_data, self.parent_view)
        await _wizard_update(interaction, self.wizard_data, embed, view)


class ConfigureContinueView1(discord.ui.View):
    """Intermediate view between wizard pages 1 and 2."""

    def __init__(self, guild_id: int, wizard_data: dict, parent_view=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.wizard_data = wizard_data
        self.parent_view = parent_view

    @discord.ui.button(label="Continue →", style=discord.ButtonStyle.primary, emoji="🔌")
    async def continue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ConfigureServerModal2(self.guild_id, self.wizard_data, self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(title="❌ Cancelled", color=discord.Color.red()), view=None
        )
        self.stop()


class ConfigureServerModal2(Modal):
    """Unified wizard page 2/4 — Ports & Auth: Game, Query, RCON ports + RCON password + Admin pw."""

    def __init__(self, guild_id: int, wizard_data: dict, parent_view=None):
        super().__init__(title="Configure Server (2/4): Ports & Auth")
        self.guild_id = guild_id
        self.wizard_data = wizard_data
        self.parent_view = parent_view

        self.game_port = TextInput(
            label="Game Port",
            placeholder="7777",
            default=str(wizard_data.get("game_port", "7777")),
            required=True,
            max_length=5,
        )
        self.add_item(self.game_port)

        self.query_port = TextInput(
            label="Query Port",
            placeholder="7778",
            default=str(wizard_data.get("query_port", "7778")),
            required=True,
            max_length=5,
        )
        self.add_item(self.query_port)

        self.rcon_port = TextInput(
            label="RCON Port",
            placeholder="27020",
            default=str(wizard_data.get("rcon_port", "27020")),
            required=True,
            max_length=6,
        )
        self.add_item(self.rcon_port)

        self.rcon_password = TextInput(
            label="RCON Password",
            placeholder="Your server's RCON password",
            default=wizard_data.get("rcon_password", ""),
            required=True,
            max_length=100,
        )
        self.add_item(self.rcon_password)

        self.admin_password = TextInput(
            label="Admin Password",
            placeholder="ARK server admin password",
            default=wizard_data.get("admin_password", ""),
            required=True,
            max_length=100,
        )
        self.add_item(self.admin_password)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.wizard_data["game_port"] = int(self.game_port.value)
            self.wizard_data["query_port"] = int(self.query_port.value)
            self.wizard_data["rcon_port"] = int(self.rcon_port.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Ports must be valid numbers.", ephemeral=True
            )
            return

        self.wizard_data["rcon_password"] = self.rcon_password.value
        self.wizard_data["admin_password"] = self.admin_password.value

        embed = discord.Embed(
            title="✅ (2/4): Ports & Auth Saved",
            description=f"Ports configured for **{self.wizard_data.get('name', '?')}**",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Ports",
            value=(
                f"Game: {self.wizard_data['game_port']} | "
                f"Query: {self.wizard_data['query_port']} | "
                f"RCON: {self.wizard_data['rcon_port']}"
            ),
            inline=False,
        )
        embed.add_field(
            name="📋 Next", value="Click **Continue** to configure file paths.", inline=False
        )

        view = ConfigureContinueView2(self.guild_id, self.wizard_data, self.parent_view)
        await _wizard_update(interaction, self.wizard_data, embed, view)


class ConfigureContinueView2(discord.ui.View):
    """Intermediate view between wizard pages 2 and 3."""

    def __init__(self, guild_id: int, wizard_data: dict, parent_view=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.wizard_data = wizard_data
        self.parent_view = parent_view

    @discord.ui.button(label="Continue →", style=discord.ButtonStyle.primary, emoji="📁")
    async def continue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ConfigureServerModal3(self.guild_id, self.wizard_data, self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(title="❌ Cancelled", color=discord.Color.red()), view=None
        )
        self.stop()


class ConfigureServerModal3(Modal):
    """Unified wizard page 3/4 — Paths: Server Path, SteamCMD, Server Password, Mods."""

    def __init__(self, guild_id: int, wizard_data: dict, parent_view=None):
        super().__init__(title="Configure Server (3/4): Paths")
        self.guild_id = guild_id
        self.wizard_data = wizard_data
        self.parent_view = parent_view

        self.server_path = TextInput(
            label="Server Path",
            placeholder="e.g., D:\\ARK\\Servers\\Island",
            default=wizard_data.get("server_path", ""),
            required=True,
            max_length=255,
        )
        self.add_item(self.server_path)

        self.steamcmd_path = TextInput(
            label="SteamCMD Path",
            placeholder="e.g., D:\\SteamCMD",
            default=wizard_data.get("steamcmd_path", ""),
            required=True,
            max_length=255,
        )
        self.add_item(self.steamcmd_path)

        self.server_password = TextInput(
            label="Server Password (optional)",
            placeholder="Leave blank for no password",
            default="",
            required=False,
            max_length=50,
        )
        self.add_item(self.server_password)

        self.mods = TextInput(
            label="Mods (comma-separated IDs, optional)",
            placeholder="e.g., 123456,789012",
            default=wizard_data.get("mods", ""),
            required=False,
            max_length=500,
        )
        self.add_item(self.mods)

    async def on_submit(self, interaction: discord.Interaction):
        self.wizard_data["server_path"] = self.server_path.value
        self.wizard_data["steamcmd_path"] = self.steamcmd_path.value
        self.wizard_data["server_password"] = self.server_password.value
        self.wizard_data["mods"] = self.mods.value or None

        embed = discord.Embed(
            title="✅ (3/4): Paths Saved",
            description=f"Paths configured for **{self.wizard_data.get('name', '?')}**",
            color=discord.Color.green(),
        )
        embed.add_field(name="Server Path", value=self.wizard_data["server_path"] or "—", inline=False)
        embed.add_field(name="SteamCMD", value=self.wizard_data["steamcmd_path"] or "—", inline=True)
        embed.add_field(
            name="📋 Next", value="Click **Continue** to configure advanced settings.", inline=False
        )

        view = ConfigureContinueView3(self.guild_id, self.wizard_data, self.parent_view)
        await _wizard_update(interaction, self.wizard_data, embed, view)


class ConfigureContinueView3(discord.ui.View):
    """Intermediate view between wizard pages 3 and 4."""

    def __init__(self, guild_id: int, wizard_data: dict, parent_view=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.wizard_data = wizard_data
        self.parent_view = parent_view

    @discord.ui.button(label="Continue →", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def continue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ConfigureServerModal4(self.guild_id, self.wizard_data, self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(title="❌ Cancelled", color=discord.Color.red()), view=None
        )
        self.stop()


class ConfigureServerModal4(Modal):
    """Unified wizard page 4/4 — Advanced: Cluster ID, Cluster Path, BattlEye."""

    def __init__(self, guild_id: int, wizard_data: dict, parent_view=None):
        super().__init__(title="Configure Server (4/4): Advanced")
        self.guild_id = guild_id
        self.wizard_data = wizard_data
        self.parent_view = parent_view

        self.cluster_id = TextInput(
            label="Cluster ID (optional)",
            placeholder="Leave blank for single server",
            default=wizard_data.get("cluster_id", ""),
            required=False,
            max_length=100,
        )
        self.add_item(self.cluster_id)

        self.cluster_path = TextInput(
            label="Cluster Path (optional)",
            placeholder="e.g., D:\\ARK\\Cluster",
            default=wizard_data.get("cluster_path", ""),
            required=False,
            max_length=255,
        )
        self.add_item(self.cluster_path)

        self.battleye_enabled = TextInput(
            label="BattlEye Enabled (true/false)",
            placeholder="false",
            default="false",
            required=False,
            max_length=5,
        )
        self.add_item(self.battleye_enabled)

        self.active_event = TextInput(
            label="Active Event (optional)",
            placeholder="e.g., WinterWonderland, Easter, Summer",
            default=wizard_data.get("active_event", ""),
            required=False,
            max_length=64,
        )
        self.add_item(self.active_event)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        self.wizard_data["cluster_id"] = self.cluster_id.value or None
        self.wizard_data["cluster_path"] = self.cluster_path.value or None
        self.wizard_data["active_event"] = self.active_event.value.strip() or None
        battleye = self.battleye_enabled.value.strip().lower() not in ("false", "no", "0", "")
        self.wizard_data["battleye_enabled"] = battleye

        try:
            server_id = self.wizard_data.get("server_id")
            # Fields to persist in DB (exclude ephemeral/agent-only and wizard-internal fields)
            _skip = {
                "server_id", "admin_password", "server_password", "rcon_test_result",
                "_wizard_webhook", "_wizard_msg_id",
            }
            db_fields = {k: v for k, v in self.wizard_data.items() if k not in _skip and v is not None}

            if server_id:
                await server_config_db.update_ark_server(server_id, **db_fields)
                action = "updated"
                # Sync registry on agent for the linked Windows service
                service_name_for_update = self.wizard_data.get("service_name")
                if service_name_for_update:
                    _agent_manager = getattr(interaction.client, "agent_manager", None)
                    if _agent_manager:
                        _agent_id = await _agent_manager.get_connected_agent_for_guild(interaction.guild_id)
                        if _agent_id:
                            try:
                                await _agent_manager.update_server_config(
                                    agent_id=_agent_id,
                                    server_name=service_name_for_update,
                                    display_name=service_name_for_update,
                                    map_name=self.wizard_data.get("map_name", ""),
                                    game_port=self.wizard_data.get("game_port", 7777),
                                    query_port=self.wizard_data.get("query_port", 7778),
                                    rcon_port=self.wizard_data.get("rcon_port", 27020),
                                    rcon_password=self.wizard_data.get("rcon_password", ""),
                                    server_password=self.wizard_data.get("server_password", "") or "",
                                    admin_password=self.wizard_data.get("admin_password", "") or "",
                                    max_players=self.wizard_data.get("max_players", 70),
                                    server_path=self.wizard_data.get("server_path", "") or "",
                                    steamcmd_path=self.wizard_data.get("steamcmd_path", "") or "",
                                    mods=self.wizard_data.get("mods", "") or "",
                                    cluster_id=self.wizard_data.get("cluster_id", "") or "",
                                    cluster_path=self.wizard_data.get("cluster_path", "") or "",
                                    battleye_enabled=battleye,
                                    active_event=self.wizard_data.get("active_event", "") or "",
                                )
                            except Exception as reg_err:
                                logger.warning(f"Registry update skipped: {reg_err}")
            else:
                server_id = await server_config_db.add_ark_server(
                    guild_id=interaction.guild_id, **db_fields
                )
                action = "added"

            await _sync_agent_config_for(interaction)

            # --- Service handling ---
            service_name = self.wizard_data.get("service_name")
            service_status_name = None
            service_status_value = None

            if service_name:
                agent_manager = getattr(interaction.client, "agent_manager", None)
                if not agent_manager:
                    service_status_name = "⚠️ Service"
                    service_status_value = "No agent manager — install service manually via `/servermgmt`"
                else:
                    try:
                        agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
                        if not agent_id:
                            service_status_name = "⚠️ Service"
                            service_status_value = (
                                "No agent connected for this guild — "
                                "connect an agent then use `/servermgmt` to install the service"
                            )
                        else:
                            list_result = await agent_manager.list_server_services(agent_id)
                            existing_services = (
                                list_result.get("data") or []
                            ) if not list_result.get("error") else []
                            service_exists = any(
                                s.get("service_name") == service_name
                                and s.get("status") != "NOT_FOUND"
                                for s in existing_services
                            )
                            if service_exists:
                                service_status_name = "ℹ️ Service"
                                service_status_value = f"`{service_name}` already exists on agent"
                            else:
                                result = await agent_manager.create_server_service(
                                    agent_id=agent_id,
                                    server_name=service_name,
                                    display_name=service_name,
                                    map_name=self.wizard_data.get("map_name", ""),
                                    game_port=self.wizard_data.get("game_port", 7777),
                                    query_port=self.wizard_data.get("query_port", 7778),
                                    rcon_port=self.wizard_data.get("rcon_port", 27020),
                                    rcon_password=self.wizard_data.get("rcon_password", ""),
                                    server_password=self.wizard_data.get("server_password", ""),
                                    admin_password=self.wizard_data.get("admin_password", ""),
                                    max_players=self.wizard_data.get("max_players", 70),
                                    server_path=self.wizard_data.get("server_path", ""),
                                    steamcmd_path=self.wizard_data.get("steamcmd_path", ""),
                                    mods=self.wizard_data.get("mods", "") or "",
                                    cluster_id=self.wizard_data.get("cluster_id", "") or "",
                                    cluster_path=self.wizard_data.get("cluster_path", "") or "",
                                    battleye_enabled=battleye,
                                    active_event=self.wizard_data.get("active_event", "") or "",
                                )
                                if result.get("error"):
                                    service_status_name = "⚠️ Service"
                                    service_status_value = f"Creation failed: {result['error']}"
                                else:
                                    # Auto-start the service after creation
                                    try:
                                        start_result = await agent_manager.start_ark_service(
                                            agent_id, service_name
                                        )
                                        if start_result.get("error") or start_result.get("type") == "error":
                                            service_status_name = "⚠️ Service"
                                            service_status_value = (
                                                f"Created `{service_name}` — start failed: "
                                                f"{start_result.get('error', 'unknown')}"
                                                f"\nStart manually via `/servermgmt`"
                                            )
                                        else:
                                            service_status_name = "✅ Service"
                                            service_status_value = f"Created and starting: `{service_name}`"
                                    except Exception as start_err:
                                        service_status_name = "⚠️ Service"
                                        service_status_value = (
                                            f"Created `{service_name}` — auto-start error: {start_err}"
                                            f"\nStart manually via `/servermgmt`"
                                        )
                    except Exception as svc_err:
                        logger.warning(f"Service creation error: {svc_err}")
                        service_status_name = "⚠️ Service"
                        service_status_value = f"Error: {svc_err}"

            # --- RCON test (best-effort, informational) ---
            rcon_test = await _test_rcon_connection(
                host=self.wizard_data.get("host", ""),
                port=self.wizard_data.get("rcon_port", 27020),
                password=self.wizard_data.get("rcon_password", ""),
            )

            # --- Build final embed ---
            embed = discord.Embed(
                title=f"✅ Server {action.title()} Successfully!",
                description=f"**{self.wizard_data.get('name')}** has been {action}.",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Connection",
                value=f"`{self.wizard_data.get('host')}:{self.wizard_data.get('rcon_port')}`",
                inline=True,
            )
            embed.add_field(name="Map", value=self.wizard_data.get("map_name", "—"), inline=True)

            if rcon_test.get("success"):
                embed.add_field(name="✅ RCON", value="Connected", inline=True)
            else:
                embed.add_field(
                    name="⚠️ RCON",
                    value=rcon_test.get("error", "Failed"),
                    inline=False,
                )

            if service_status_name:
                embed.add_field(name=service_status_name, value=service_status_value, inline=False)

            if action == "updated":
                embed.set_footer(
                    text=(
                        "⚠️ If you changed the RCON port, any existing voice channel linked to the old port "
                        "will not auto-update. Remove the old voice channel manually and re-run server monitor "
                        "setup to create a new one."
                    )
                )

            # Delete the previous step's message, then send final result
            prev_webhook = self.wizard_data.get("_wizard_webhook")
            prev_msg_id = self.wizard_data.get("_wizard_msg_id")
            if prev_webhook and prev_msg_id:
                try:
                    await prev_webhook.delete_message(prev_msg_id)
                except Exception:
                    pass
            await interaction.followup.send(embed=embed, ephemeral=True)

            if self.parent_view and hasattr(self.parent_view, "refresh"):
                await self.parent_view.refresh()

        except Exception as e:
            logger.error(f"Error in ConfigureServerModal4.on_submit: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ Error saving server: {e}", ephemeral=True)
            except Exception:
                pass


class ConfigureServerButton(Button):
    """Unified 'Configure Server' button — opens ServerSelectorView for the 4-page wizard.

    Replaces both AddServerFromManageButton (Manage Servers) and
    CreateServiceButton (Service Mgmt).
    """

    def __init__(self, guild_id: int, parent_view):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Configure Server",
            emoji="⚙️",
            custom_id="configure_server",
            row=1,
        )
        self.guild_id = guild_id
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        from bot.database import subscription_db

        sub = await subscription_db.get_or_create_subscription(interaction.guild_id)
        tier = subscription_db.get_effective_tier(sub)
        servers = await server_config_db.get_ark_servers(interaction.guild_id)

        selector = ServerSelectorView(interaction.guild_id, servers, self.parent_view, tier)
        embed = selector.create_embed()
        msg = await interaction.followup.send(embed=embed, view=selector, ephemeral=True, wait=True)
        # Store webhook + message ID so wizard pages can edit this single message in place
        selector._wizard_webhook = interaction.followup
        selector._wizard_msg_id = msg.id


class ServerSelectorView(discord.ui.View):
    """Entry view for the configure wizard: pick an existing server or add a new one."""

    def __init__(self, guild_id: int, servers: list, parent_view, tier: str):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.servers = servers
        self.parent_view = parent_view
        self.tier = tier

        if servers:
            options = [
                discord.SelectOption(
                    label=s["name"],
                    value=str(s["id"]),
                    description=f"{s['host']}:{s.get('rcon_port', '?')}",
                )
                for s in servers[:25]  # Discord select max 25 options
            ]
            select = discord.ui.Select(
                placeholder="Select server to edit…",
                options=options,
                custom_id="configure_server_select",
                row=0,
            )
            select.callback = self.server_select_callback
            self.add_item(select)

        add_btn = Button(
            style=discord.ButtonStyle.success,
            label="Add New Server",
            emoji="➕",
            row=1,
        )
        add_btn.callback = self.add_new_callback
        self.add_item(add_btn)

    async def server_select_callback(self, interaction: discord.Interaction):
        server_id = int(interaction.data["values"][0])
        server = next((s for s in self.servers if s["id"] == server_id), None)
        if not server:
            await interaction.response.send_message("❌ Server not found.", ephemeral=True)
            return

        wizard_data = {
            "server_id": server_id,
            "name": server.get("name", ""),
            "map_name": server.get("map_name", ""),
            "host": server.get("host", ""),
            "service_name": server.get("service_name", ""),
            "max_players": server.get("max_players", 70),
            "game_port": server.get("game_port", 7777),
            "query_port": server.get("query_port", 7778),
            "rcon_port": server.get("rcon_port", 27020),
            "rcon_password": server.get("rcon_password", ""),
            "admin_password": "",
            "server_path": server.get("server_path", ""),
            "steamcmd_path": server.get("steamcmd_path", ""),
            "server_password": "",
            "mods": server.get("mods", ""),
            "cluster_id": server.get("cluster_id", ""),
            "cluster_path": server.get("cluster_path", ""),
            "active_event": server.get("active_event", ""),
            "_wizard_webhook": getattr(self, "_wizard_webhook", None),
            "_wizard_msg_id": getattr(self, "_wizard_msg_id", None),
        }
        modal = ConfigureServerModal1(self.guild_id, self.parent_view, wizard_data)
        await interaction.response.send_modal(modal)

    async def add_new_callback(self, interaction: discord.Interaction):
        if self.tier == "free" and len(self.servers) >= 2:
            await interaction.response.send_message(
                "❌ **Free tier limit reached!**\n\n"
                "You can only configure **2 ARK servers** on the free tier.\n\n"
                "💎 **Upgrade to Premium** for unlimited servers.\n"
                "Use `/subscribe` to upgrade!",
                ephemeral=True,
            )
            return
        wizard_data = {
            "_wizard_webhook": getattr(self, "_wizard_webhook", None),
            "_wizard_msg_id": getattr(self, "_wizard_msg_id", None),
        }
        modal = ConfigureServerModal1(self.guild_id, self.parent_view, wizard_data)
        await interaction.response.send_modal(modal)

    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="⚙️ Configure Server",
            description="Select an existing server to edit, or click **Add New Server**.",
            color=discord.Color.blue(),
        )
        if self.servers:
            embed.add_field(
                name=f"📊 Existing Servers ({len(self.servers)})",
                value="\n".join(
                    f"• **{s['name']}** — `{s['host']}:{s.get('rcon_port', '?')}`"
                    for s in self.servers
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="📋 No Servers Yet",
                value="Click **Add New Server** to get started.",
                inline=False,
            )
        return embed


class ManageServersView(discord.ui.View):
    """View for managing ARK servers."""

    def __init__(
        self,
        guild_id: int,
        user: discord.User,
        guild: discord.Guild,
        message: discord.Message = None,
    ):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user = user
        self.guild = guild
        self.message = message
        self.servers = []
        self.selected_server = None

    async def load_servers(self):
        """Load all servers for this guild, including disabled ones."""
        # Show ALL servers including disabled — admins need visibility to re-enable after upgrading.
        # Hard-deleted servers are gone; disabled servers remain visible with a warning indicator.
        self.servers = await server_config_db.get_ark_servers(self.guild_id, include_disabled=True)

        # Add server selector dropdown (row 0) - disabled servers shown with ⚠️ indicator
        if self.servers:
            options = []
            for server in self.servers:
                label = server["name"]
                description = f"{server['host']}:{server['rcon_port']}"
                if not server.get("enabled", True):
                    label = f"⚠️ {label} (Disabled)"
                    reason = server.get("disabled_reason") or "Disabled"
                    description = f"{description} — {reason}"
                options.append(discord.SelectOption(label=label, value=str(server["id"]), description=description))
            
            select = discord.ui.Select(
                placeholder="Select a server to manage...",
                options=options,
                custom_id="server_selector",
                row=0,
            )
            select.callback = self.server_select_callback
            self.add_item(select)

        # Add action buttons (row 1) — unified wizard replaces old AddServerFromManageButton
        self.add_item(ConfigureServerButton(self.guild_id, self))

    async def server_select_callback(self, interaction: discord.Interaction):
        """Handle server selection from dropdown."""
        server_id = int(interaction.data["values"][0])
        self.selected_server = next((s for s in self.servers if s["id"] == server_id), None)

        if self.selected_server:
            # Try to detect and cache ARK version if not already cached
            if not self.selected_server.get("ark_version") and self.selected_server.get("server_path"):
                try:
                    from bot.utils.ark_version import detect_and_cache_server_version
                    version = await detect_and_cache_server_version(
                        self.selected_server["id"],
                        self.selected_server.get("server_path")
                    )
                    if version:
                        self.selected_server["ark_version"] = version
                except Exception as e:
                    # Silently fail - version detection is not critical
                    logger.warning(f"Failed to detect ARK version: {e}")

            # Populate live RCON status from server monitor cache
            server_monitor = interaction.client.get_cog("ServerMonitor")
            if server_monitor:
                cache = server_monitor.guild_server_caches.get(self.guild_id, {}).get(
                    self.selected_server["name"], {}
                )
                is_online = cache.get("online")
                if is_online is True:
                    self.selected_server["rcon_status"] = "online"
                elif is_online is False:
                    self.selected_server["rcon_status"] = "offline"

            # Show edit/remove options for selected server
            manage_view = ServerActionsView(
                self.selected_server, self.guild_id, interaction.user, self
            )
            embed = manage_view.create_embed()
            await interaction.response.send_message(embed=embed, view=manage_view, ephemeral=True)

    def create_embed(self) -> discord.Embed:
        """Create server management embed."""
        embed = discord.Embed(
            title="⚙️ Manage ARK Servers",
            description="Select a server from the dropdown to edit or remove it.",
            color=discord.Color.blue(),
        )

        if self.servers:
            # Show summary of all servers
            server_list = "\n".join(
                [
                    f"• **{server['name']}** - `{server['host']}:{server['rcon_port']}`"
                    for server in self.servers
                ]
            )
            embed.add_field(
                name=f"📊 Configured Servers ({len(self.servers)})", value=server_list, inline=False
            )
        else:
            embed.add_field(
                name="📋 No Servers",
                value="No ARK servers configured yet. Click **Configure Server** to add one.",
                inline=False,
            )

        embed.set_footer(
            text="💡 Use the dropdown to manage existing servers, or click 'Configure Server' to add a new one"
        )
        return embed

    async def refresh(self):
        """Reload servers and update the message."""
        if not self.message:
            return

        # Clear current items
        self.clear_items()

        # Reload servers and rebuild view
        await self.load_servers()

        # Update the message
        embed = self.create_embed()
        try:
            await self.message.edit(embed=embed, view=self)
        except Exception as e:
            logger.error(f"Failed to refresh manage servers view: {e}")


class AddServerFromManageButton(Button):
    """Button to add a new server from manage view."""

    def __init__(self, guild_id: int, parent_view: "ManageServersView" = None):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Add Server",
            emoji="➕",
            custom_id="add_server_from_manage",
            row=1,
        )
        self.guild_id = guild_id
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # Check subscription tier and enforce server limits before opening modal
        from bot.database import subscription_db, server_config_db
        
        sub = await subscription_db.get_or_create_subscription(interaction.guild_id)
        tier = subscription_db.get_effective_tier(sub)
        
        # Free tier: limit to 2 servers total
        if tier == "free":
            existing_servers = await server_config_db.get_ark_servers(interaction.guild_id)
            if len(existing_servers) >= 2:
                await interaction.response.send_message(
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
        
        modal = AddServerModal(self.guild_id, self.parent_view)
        await interaction.response.send_modal(modal)



class ServerActionsView(discord.ui.View):
    """View with edit/remove/toggle actions for a server."""

    def __init__(
        self,
        server: dict,
        guild_id: int,
        user: discord.User,
        parent_view: "ManageServersView" = None,
    ):
        super().__init__(timeout=300)
        self.server = server
        self.guild_id = guild_id
        self.user = user
        self.parent_view = parent_view

        self.add_item(EditServerButton(server, parent_view))
        self.add_item(ToggleServerButton(server, parent_view))
        self.add_item(RemoveServerButton(server, guild_id, parent_view))

    def create_embed(self) -> discord.Embed:
        """Create server details embed."""
        embed = discord.Embed(
            title=f"⚙️ Manage: {self.server['name']}",
            description="Choose an action:",
            color=discord.Color.blue(),
        )

        embed.add_field(name="Host", value=self.server["host"], inline=True)
        embed.add_field(name="RCON Port", value=str(self.server["rcon_port"]), inline=True)
        if self.server.get("server_path"):
            embed.add_field(name="Server Path", value=self.server["server_path"], inline=True)
        if self.server.get("steamcmd_path"):
            embed.add_field(name="SteamCMD Path", value=self.server["steamcmd_path"], inline=True)
        if self.server.get("ark_version"):
            # Show version with update status indicator
            version_text = self.server["ark_version"]
            if self.server.get("update_needed"):
                # Also show latest version if available
                latest = self.server.get("latest_build_id")
                version_text += " ⚠️ UPDATE AVAILABLE"
                if latest:
                    version_text += f"\nLatest: {latest}"
            else:
                version_text += " ✅"
            embed.add_field(name="🎮 ARK Version", value=version_text, inline=False)
        if self.server.get("game_port"):
            embed.add_field(name="Game Port", value=str(self.server["game_port"]), inline=True)

        status = "✅ Enabled" if self.server.get("enabled", True) else "❌ Disabled"
        embed.add_field(name="Status", value=status, inline=True)
        
        # Add RCON connectivity status
        rcon_status = self.server.get("rcon_status", "unknown")
        if rcon_status == "online":
            rcon_indicator = "🟢 RCON Connected"
        elif rcon_status == "offline":
            rcon_indicator = "🔴 RCON Unreachable"
        else:
            rcon_indicator = "⚪ RCON Status Unknown"
        embed.add_field(name="Connection", value=rcon_indicator, inline=True)

        return embed


class EditServerButton(Button):
    """Button to edit a server."""

    def __init__(self, server: dict, parent_view: "ManageServersView" = None):
        super().__init__(style=discord.ButtonStyle.primary, label="Edit Server", emoji="✏️")
        self.server = server
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        server = self.server
        wizard_data = {
            "server_id": server["id"],
            "name": server.get("name", ""),
            "map_name": server.get("map_name", ""),
            "host": server.get("host", ""),
            "service_name": server.get("service_name", ""),
            "max_players": server.get("max_players", 70),
            "game_port": server.get("game_port", 7777),
            "query_port": server.get("query_port", 7778),
            "rcon_port": server.get("rcon_port", 27020),
            "rcon_password": server.get("rcon_password", ""),
            "admin_password": "",
            "server_path": server.get("server_path", ""),
            "steamcmd_path": server.get("steamcmd_path", ""),
            "server_password": "",
            "mods": server.get("mods", ""),
            "cluster_id": server.get("cluster_id", ""),
            "cluster_path": server.get("cluster_path", ""),
            "active_event": server.get("active_event", ""),
        }
        modal = ConfigureServerModal1(interaction.guild_id, self.parent_view, wizard_data)
        await interaction.response.send_modal(modal)
        # Clean up the ServerActionsView embed that spawned this edit
        try:
            if interaction.message:
                await interaction.followup.delete_message(interaction.message.id)
        except Exception:
            pass


class ToggleServerButton(Button):
    """Button to toggle server enabled/disabled status."""

    def __init__(self, server: dict, parent_view: "ManageServersView" = None):
        current_status = server.get("enabled", True)
        style = discord.ButtonStyle.danger if current_status else discord.ButtonStyle.success
        label = "Disable Server" if current_status else "Enable Server"
        emoji = "🔴" if current_status else "🟢"

        super().__init__(style=style, label=label, emoji=emoji)
        self.server = server
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        from bot.database import subscription_db

        current_status = self.server.get("enabled", True)
        new_status = not current_status

        # Tier enforcement: block re-enabling a server that was disabled due to tier limits
        if new_status and self.server.get("disabled_reason") == "tier_limit":
            sub = await subscription_db.get_or_create_subscription(interaction.guild_id)
            tier = subscription_db.get_effective_tier(sub)
            if tier == "free":
                await interaction.response.send_message(
                    "❌ **Premium Required**\n\n"
                    "This server was disabled because your subscription was downgraded to **Free** tier.\n\n"
                    "💎 **Upgrade to Premium** for:\n"
                    "• Unlimited servers\n"
                    "• Economy, shop, kits, and games\n\n"
                    "Use `/subscribe` to upgrade!",
                    ephemeral=True,
                )
                return

        # Update server status in database
        success = await server_config_db.update_ark_server(self.server["id"], enabled=new_status)

        if success:
            await _sync_agent_config_for(interaction)
            status_text = "enabled" if new_status else "disabled"
            embed = discord.Embed(
                title="✅ Server Status Updated",
                description=f"**{self.server['name']}** has been {status_text}.",
                color=discord.Color.green(),
            )
            await interaction.response.edit_message(embed=embed, view=None)

            # Refresh parent view
            if self.parent_view:
                await self.parent_view.refresh()
        else:
            await interaction.response.send_message(
                "❌ Failed to update server status.", ephemeral=True
            )


class RemoveServerButton(Button):
    """Button to remove a server."""

    def __init__(self, server: dict, guild_id: int, parent_view: "ManageServersView" = None):
        super().__init__(style=discord.ButtonStyle.danger, label="Remove Server", emoji="🗑️")
        self.server = server
        self.guild_id = guild_id
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        service_name = self.server.get("service_name")

        if not service_name:
            # Case A: no linked service — simple remove confirmation
            confirm_view = ConfirmRemoveView(
                self.server, self.guild_id, interaction.user, self.parent_view
            )
            embed = discord.Embed(
                title="⚠️ Confirm Removal",
                description=f"Are you sure you want to remove **{self.server['name']}**?\n\nThis action cannot be undone!",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
            return

        # service_name is set — check if agent has a live service
        await interaction.response.defer(ephemeral=True)
        agent_manager = getattr(interaction.client, "agent_manager", None)
        service_found = False
        agent_id = None

        if agent_manager:
            try:
                agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
                if agent_id:
                    result = await agent_manager.list_server_services(agent_id)
                    services = result.get("data", []) if not result.get("error") else []
                    service_found = any(s.get("service_name") == service_name for s in services)
            except Exception as e:
                logger.warning(f"Could not query agent for service check: {e}")

        if service_found:
            # Case B: service found — offer linked removal options
            view = LinkedRemoveServerView(
                self.server, self.guild_id, interaction.user, self.parent_view, agent_id
            )
            embed = discord.Embed(
                title="⚠️ Linked Server & Service",
                description=(
                    f"**{self.server['name']}** is linked to Windows service "
                    f"**`{service_name}`**.\n\nWhat would you like to do?"
                ),
                color=discord.Color.orange(),
            )
            embed.add_field(
                name="🗑️ Remove from bot only",
                value="Deletes the bot's DB record. Windows service keeps running.",
                inline=False,
            )
            embed.add_field(
                name="💥 Remove both",
                value="Stops + deletes the Windows service AND removes the bot record.",
                inline=False,
            )
        else:
            # Case C: service_name in DB but not found on agent (orphaned record)
            view = ConfirmRemoveView(self.server, self.guild_id, interaction.user, self.parent_view)
            embed = discord.Embed(
                title="⚠️ Confirm Removal",
                description=(
                    f"Are you sure you want to remove **{self.server['name']}**?\n\n"
                    f"⚠️ Associated Windows service `{service_name}` was not found on the agent."
                ),
                color=discord.Color.red(),
            )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class ConfirmRemoveView(discord.ui.View):
    """Confirmation view for server removal."""

    def __init__(
        self,
        server: dict,
        guild_id: int,
        user: discord.User,
        parent_view: "ManageServersView" = None,
    ):
        super().__init__(timeout=300)
        self.server = server
        self.guild_id = guild_id
        self.user = user
        self.parent_view = parent_view

    @discord.ui.button(label="Yes, Remove", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            success = await server_config_db.remove_ark_server(self.server["id"])
            if success:
                await _sync_agent_config_for(interaction)
                # Defer the interaction and then edit to close the dialog
                await interaction.response.defer()
                
                # Edit the original confirmation message to remove buttons
                try:
                    await interaction.edit_original_response(
                        content=f"✅ Server **{self.server['name']}** has been removed.",
                        embed=None,
                        view=None,
                    )
                except:
                    # If edit fails, try to send a followup message
                    await interaction.followup.send(
                        f"✅ Server **{self.server['name']}** has been removed.",
                        ephemeral=True
                    )
                
                # Refresh parent view
                if self.parent_view:
                    await self.parent_view.refresh()
            else:
                await interaction.response.edit_message(
                    content=f"❌ Failed to remove server.",
                    embed=None,
                    view=None,
                )
        except Exception as e:
            await interaction.response.edit_message(
                content=f"❌ Error removing server: {e}",
                embed=None,
                view=None,
            )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Defer the interaction and then edit to close the dialog
        await interaction.response.defer()
        
        try:
            await interaction.edit_original_response(
                content="✅ Removal cancelled.",
                embed=None,
                view=None,
            )
        except:
            # If edit fails, try to send a followup message
            await interaction.followup.send(
                "✅ Removal cancelled.",
                ephemeral=True
            )


class LinkedRemoveServerView(discord.ui.View):
    """Confirmation view when server has a linked Windows service.

    Offers three options:
    - Remove from bot only (keep service running)
    - Remove both (stop + delete service AND remove DB record)
    - Cancel
    """

    def __init__(
        self,
        server: dict,
        guild_id: int,
        user: discord.User,
        parent_view: "ManageServersView",
        agent_id: Optional[str],
    ):
        super().__init__(timeout=120)
        self.server = server
        self.guild_id = guild_id
        self.user = user
        self.parent_view = parent_view
        self.agent_id = agent_id

    @discord.ui.button(label="Remove from bot only", style=discord.ButtonStyle.primary, emoji="🗑️")
    async def bot_only_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Delete DB record only — leave Windows service running."""
        try:
            success = await server_config_db.remove_ark_server(self.server["id"])
            if success:
                await _sync_agent_config_for(interaction)
                await interaction.response.edit_message(
                    content=f"✅ **{self.server['name']}** removed from bot. Windows service left running.",
                    embed=None,
                    view=None,
                )
                if self.parent_view:
                    await self.parent_view.refresh()
            else:
                await interaction.response.edit_message(
                    content="❌ Failed to remove server from database.", embed=None, view=None
                )
        except Exception as e:
            await interaction.response.edit_message(
                content=f"❌ Error: {e}", embed=None, view=None
            )

    @discord.ui.button(label="Remove both", style=discord.ButtonStyle.danger, emoji="💥")
    async def remove_both_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Stop + delete Windows service AND remove DB record."""
        await interaction.response.defer(ephemeral=True)
        service_name = self.server.get("service_name")
        errors = []

        agent_manager = getattr(interaction.client, "agent_manager", None)
        if agent_manager and self.agent_id and service_name:
            try:
                # Stop service first
                await agent_manager.stop_ark_service(self.agent_id, service_name)
            except Exception as e:
                logger.warning(f"Stop service failed (continuing): {e}")

            try:
                result = await agent_manager.delete_server_service(
                    self.agent_id, service_name, service_name
                )
                if result.get("error"):
                    errors.append(f"Service deletion: {result['error']}")
            except Exception as e:
                errors.append(f"Service deletion: {e}")

        try:
            success = await server_config_db.remove_ark_server(self.server["id"])
            if not success:
                errors.append("DB record deletion failed")
        except Exception as e:
            errors.append(f"DB: {e}")

        await _sync_agent_config_for(interaction)

        if errors:
            msg = f"⚠️ Partial removal of **{self.server['name']}**:\n" + "\n".join(f"• {e}" for e in errors)
        else:
            msg = f"✅ **{self.server['name']}** and its Windows service have been removed."

        try:
            await interaction.edit_original_response(content=msg, embed=None, view=None)
        except Exception:
            await interaction.followup.send(msg, ephemeral=True)

        if self.parent_view:
            await self.parent_view.refresh()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Removal cancelled.", embed=None, view=None)


class EditServerModal(Modal):
    """Modal for editing an ARK server - Page 1: Basic Connection Info."""

    def __init__(self, server_config: dict, parent_view: "ManageServersView" = None):
        super().__init__(title=f"✏️ Edit (1/2): {server_config['name']}")
        self.server_config = server_config
        self.server_id = server_config["id"]
        self.guild_id = server_config["guild_id"]
        self.parent_view = parent_view

        self.server_name = TextInput(
            label="Server Name",
            placeholder="e.g., Island, Ragnarok, Center",
            default=server_config.get("name") or "",
            required=True,
            max_length=50,
        )
        self.add_item(self.server_name)

        # Handle both 'host' and 'rcon_host' column names for backward compatibility
        host_value = server_config.get("host") or server_config.get("rcon_host") or ""
        self.host = TextInput(
            label="Server IP Address (⚠️ NOT 127.0.0.1)",
            placeholder="e.g., 192.168.1.100 or game.example.com",
            default=host_value,
            required=True,
            max_length=100,
        )
        self.add_item(self.host)

        self.rcon_port = TextInput(
            label="RCON Port",
            placeholder="e.g., 27020",
            default=str(server_config.get("rcon_port") or ""),
            required=True,
            max_length=6,
        )
        self.add_item(self.rcon_port)

        self.rcon_password = TextInput(
            label="RCON Password",
            placeholder="Your server's RCON password",
            default=server_config.get("rcon_password") or "",
            required=True,
            max_length=100,
        )
        self.add_item(self.rcon_password)

        self.game_port = TextInput(
            label="Game Port (optional)",
            placeholder="e.g., 7777",
            default=str(server_config.get("game_port")) if server_config.get("game_port") else "",
            required=False,
            max_length=6,
        )
        self.add_item(self.game_port)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rcon_port = int(self.rcon_port.value)
            game_port = int(self.game_port.value) if self.game_port.value else None

            await interaction.response.defer(ephemeral=True)

            # Store data and show intermediate view with "Continue Setup" button
            server_data = {
                "server_id": self.server_id,
                "name": self.server_name.value,
                "host": self.host.value,
                "rcon_port": rcon_port,
                "rcon_password": self.rcon_password.value,
                "game_port": game_port,
            }
            
            embed = discord.Embed(
                title="✅ Step 1 Complete: Connection Info Updated",
                description=f"**{self.server_name.value}** basic settings saved.",
                color=discord.Color.blue(),
            )
            
            embed.add_field(
                name="📋 Next Step",
                value="Click **Continue Setup** to configure advanced settings (paths, service name, max players).",
                inline=False,
            )
            
            # Send message and get reference for tracking
            msg = await interaction.followup.send(embed=embed, ephemeral=True, wait=True)
            view = EditServerContinueView(self.guild_id, server_data, self.server_config, self.parent_view, msg)
            await msg.edit(embed=embed, view=view)

        except ValueError:
            await interaction.followup.send(
                "❌ Invalid port number! Ports must be numbers.", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in EditServerModal: {e}")
            await interaction.followup.send(f"❌ Error editing server: {e}", ephemeral=True)


class EditServerContinueView(discord.ui.View):
    """Intermediate view after edit page 1 - shows Continue Setup button."""
    
    def __init__(self, guild_id: int, server_data: dict, existing_config: dict, parent_view: "ManageServersView" = None, message=None):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.server_data = server_data
        self.existing_config = existing_config
        self.parent_view = parent_view
        self.message = message
    
    @discord.ui.button(label="Continue Setup →", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def continue_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the advanced settings modal."""
        modal = EditServerAdvancedModal(self.guild_id, self.server_data, self.existing_config, self.parent_view, interaction.message)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the edit process."""
        embed = discord.Embed(
            title="❌ Edit Cancelled",
            description="Server was not updated. Changes discarded.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class EditServerAdvancedModal(Modal):
    """Modal for editing an ARK server - Page 2: Advanced Settings."""
    
    def __init__(self, guild_id: int, server_data: dict, existing_config: dict, parent_view: "ManageServersView" = None, message=None):
        super().__init__(title=f"✏️ Edit (2/2): {server_data['name']}")
        self.guild_id = guild_id
        self.server_data = server_data
        self.existing_config = existing_config
        self.parent_view = parent_view
        self.message = message
        
        self.server_path = TextInput(
            label="Server Path (for log monitoring)",
            placeholder="e.g., D:\\ARK\\Island or /ark/island",
            default=existing_config.get("server_path") or "",
            required=False,
            max_length=255,
        )
        self.add_item(self.server_path)
        
        self.service_name = TextInput(
            label="Service Name (e.g. PhoenixArk_Aberration)",
            placeholder="e.g., ArkAberration",
            default=existing_config.get("service_name") or "",
            required=False,
            max_length=100,
        )
        self.add_item(self.service_name)
        
        self.max_players = TextInput(
            label="Max Players (default: 70)",
            placeholder="70",
            default=str(existing_config.get("max_players")) if existing_config.get("max_players") else "70",
            required=False,
            max_length=3,
        )
        self.add_item(self.max_players)
        
        self.steamcmd_path = TextInput(
            label="SteamCMD Directory (for updates)",
            placeholder="e.g., D:\\SteamCMD",
            default=existing_config.get("steamcmd_path") or "",
            required=False,
            max_length=255,
        )
        self.add_item(self.steamcmd_path)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            # Parse inputs
            server_path = self.server_path.value.strip() if self.server_path.value else None
            service_name = self.service_name.value.strip() if self.service_name.value else None
            steamcmd_path = self.steamcmd_path.value.strip() if self.steamcmd_path.value else None
            max_players = int(self.max_players.value) if self.max_players.value else 70
            
            # Update server with all fields from both pages
            success = await server_config_db.update_ark_server(
                self.server_data["server_id"],
                name=self.server_data["name"],
                host=self.server_data["host"],
                rcon_port=self.server_data["rcon_port"],
                rcon_password=self.server_data["rcon_password"],
                game_port=self.server_data.get("game_port"),
                server_path=server_path,
                service_name=service_name,
                steamcmd_path=steamcmd_path,
                max_players=max_players,
            )
            
            if success:
                await _sync_agent_config_for(interaction)
                embed = discord.Embed(
                    title="✅ Server Updated Successfully",
                    description=f"**{self.server_data['name']}** has been updated!",
                    color=discord.Color.green(),
                )
                
                embed.add_field(name="Host", value=self.server_data["host"], inline=True)
                embed.add_field(name="RCON Port", value=str(self.server_data["rcon_port"]), inline=True)
                embed.add_field(name="Max Players", value=str(max_players), inline=True)
                
                if server_path:
                    embed.add_field(name="Server Path", value=server_path, inline=False)
                if service_name:
                    embed.add_field(name="Service Name", value=service_name, inline=True)
                if steamcmd_path:
                    embed.add_field(name="SteamCMD Path", value=steamcmd_path, inline=True)
                
                embed.set_footer(text=f"Server ID: {self.server_data['server_id']}")
                
                # Send the success message
                await interaction.followup.send(embed=embed, ephemeral=True)
                
                # Refresh parent view if available
                if self.parent_view:
                    await self.parent_view.refresh()
            else:
                await interaction.followup.send("❌ Failed to update server.", ephemeral=True)
        
        except ValueError as e:
            await interaction.followup.send(
                f"❌ Invalid input: {str(e)}", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in EditServerAdvancedModal: {e}")
            await interaction.followup.send(
                f"❌ Error updating server: {str(e)}", ephemeral=True
            )



class ServerDirectoriesModal(Modal):
    """Modal for editing server directory paths (server_path, steamcmd_path, log_path, service_name)."""

    def __init__(self, server: dict, parent_view=None):
        super().__init__(title=f"📁 Directories: {server.get('name', 'Server')}")
        self.server = server
        self.parent_view = parent_view

        self.server_path = TextInput(
            label="Server Path",
            placeholder="e.g., D:\\ARK\\Island",
            default=server.get("server_path") or "",
            required=False,
            max_length=255,
        )
        self.add_item(self.server_path)

        self.steamcmd_path = TextInput(
            label="SteamCMD Path",
            placeholder="e.g., C:\\SteamCMD\\steamcmd.exe",
            default=server.get("steamcmd_path") or "",
            required=False,
            max_length=255,
        )
        self.add_item(self.steamcmd_path)

        self.log_path = TextInput(
            label="Log Path",
            placeholder="e.g., D:\\ARK\\Island\\ShooterGame\\Saved\\Logs",
            default=server.get("log_path") or "",
            required=False,
            max_length=255,
        )
        self.add_item(self.log_path)

        self.service_name = TextInput(
            label="Service Name",
            placeholder="e.g., ARKIsland",
            default=server.get("service_name") or "",
            required=False,
            max_length=100,
        )
        self.add_item(self.service_name)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from bot.database import server_config_db
            updates = {
                "server_path": self.server_path.value.strip() or None,
                "steamcmd_path": self.steamcmd_path.value.strip() or None,
                "log_path": self.log_path.value.strip() or None,
                "service_name": self.service_name.value.strip() or None,
            }
            await server_config_db.update_ark_server(self.server["id"], **updates)
            await _sync_agent_config_for(interaction)
            await interaction.response.send_message(
                "✅ Server directories updated.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error updating directories: {e}", ephemeral=True
            )


# ============================================================================
# Phase 16: Service Management View
# ============================================================================

class ServiceManagementView(discord.ui.View):
    """View for managing PhoenixARK Windows services."""

    def __init__(
        self,
        guild_id: int,
        user: discord.User,
        bot: commands.Bot,
        message: discord.Message = None,
    ):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user = user
        self.bot = bot
        self.message = message
        self.services = None  # None = not loaded yet, [] = loaded but empty
        self.selected_service = None

    async def load_services(self):
        """Load all PhoenixARK services from the remote agent."""
        logger.info("load_services: Starting...")
        
        # Always add action buttons first — unified wizard replaces old CreateServiceButton
        self.add_item(ConfigureServerButton(self.guild_id, self))
        logger.info("load_services: Added ConfigureServerButton")

        agent_manager = getattr(self.bot, "agent_manager", None)
        if not agent_manager:
            logger.warning("load_services: No agent_manager found on bot")
            self.services = []  # Set to empty list so embed shows "No Services"
            return

        logger.info(f"load_services: Found agent_manager, getting agent for guild {self.guild_id}")
        
        try:
            agent_id = await asyncio.wait_for(
                agent_manager.get_connected_agent_for_guild(self.guild_id),
                timeout=5.0
            )
            logger.info(f"load_services: Got agent_id: {agent_id}")
        except asyncio.TimeoutError:
            logger.error("load_services: Timeout waiting for get_connected_agent_for_guild")
            self.services = []  # Set to empty list so embed shows "No Services"
            return
        except Exception as e:
            logger.error(f"load_services: Error getting agent_id: {e}", exc_info=True)
            self.services = []  # Set to empty list so embed shows "No Services"
            return

        if not agent_id:
            logger.warning(f"load_services: No agent connected for guild {self.guild_id}")
            self.services = []  # Set to empty list so embed shows "No Services"
            return

        try:
            logger.info(f"load_services: Calling list_server_services for agent {agent_id}")
            result = await asyncio.wait_for(
                agent_manager.list_server_services(agent_id),
                timeout=10.0
            )
            logger.info(f"load_services: Got result from agent: {result}")
            if result.get("error"):
                logger.error(f"load_services: Agent returned error: {result['error']}")
                self.services = []  # Set to empty list so embed shows "No Services"
                return

            self.services = result.get("data", [])
            logger.info(f"load_services: Loaded {len(self.services)} services")

            # Add service selector dropdown (insert at beginning, before buttons)
            if self.services:
                options = []
                for svc in self.services:
                    name = svc.get("server_name", "Unknown")
                    status = svc.get("status", "Unknown")
                    status_emoji = "🟢" if status.upper() == "RUNNING" else "🔴"
                    options.append(
                        discord.SelectOption(
                            label=f"{status_emoji} {name}",
                            value=svc.get("service_name", name),
                            description=f"Status: {status}",
                        )
                    )

                select = discord.ui.Select(
                    placeholder="Select a service to manage...",
                    options=options,
                    custom_id="service_selector",
                    row=0,
                )
                select.callback = self.service_select_callback
                self.add_item(select)

        except Exception as e:
            logger.error(f"Failed to load services: {e}")
            self.services = []  # Set to empty list so embed shows "No Services"

    async def service_select_callback(self, interaction: discord.Interaction):
        """Handle service selection from dropdown."""
        service_name = interaction.data["values"][0]
        self.selected_service = next(
            (s for s in self.services if s.get("service_name") == service_name), None
        )

        if self.selected_service:
            # Show service actions view
            actions_view = ServiceActionsView(
                self.selected_service, self.guild_id, interaction.user, self
            )
            embed = actions_view.create_embed()
            await interaction.response.send_message(embed=embed, view=actions_view, ephemeral=True)

    async def create_embed(self) -> discord.Embed:
        """Create service management embed."""
        embed = discord.Embed(
            title="🔧 Service Management",
            description="Manage PhoenixARK Windows services for your ARK servers.",
            color=discord.Color.blue(),
        )

        agent_manager = getattr(self.bot, "agent_manager", None)
        if not agent_manager:
            embed.add_field(
                name="❌ No Agent Manager",
                value="Remote agent system not loaded. Please contact the bot owner.",
                inline=False,
            )
            return embed

        agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            embed.add_field(
                name="❌ No Agent Connected",
                value="No remote agent is currently connected. Use **Agent Control** to register and connect an agent first.",
                inline=False,
            )
            return embed

        # Show loading state if services haven't been loaded yet
        if self.services is None:
            embed.add_field(
                name="⏳ Loading Services...",
                value="Querying remote agent for PhoenixARK services...",
                inline=False,
            )
            return embed

        if self.services:
            service_list = []
            for svc in self.services:
                name = svc.get("server_name", "Unknown")
                status = svc.get("status", "Unknown")
                status_emoji = "🟢" if status.upper() == "RUNNING" else "🔴"
                service_list.append(f"{status_emoji} **{name}** — {status}")

            embed.add_field(
                name=f"📊 Services ({len(self.services)})",
                value="\n".join(service_list),
                inline=False,
            )
        else:
            embed.add_field(
                name="📋 No Services",
                value="No PhoenixARK services found. Click **Configure Server** to create one.",
                inline=False,
            )

        embed.set_footer(
            text="💡 Select a service from the dropdown to manage it, or click 'Configure Server' to add a new one"
        )
        return embed

    async def refresh(self):
        """Reload services and update the message."""
        if not self.message:
            return

        self.clear_items()
        await self.load_services()

        embed = await self.create_embed()
        try:
            await self.message.edit(embed=embed, view=self)
        except Exception as e:
            logger.error(f"Failed to refresh service view: {e}")


class CreateServiceButton(Button):
    """Button to create a new PhoenixARK service."""

    def __init__(self, guild_id: int, parent_view: "ServiceManagementView"):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Create Service",
            emoji="➕",
            custom_id="create_service",
            row=1,
        )
        self.guild_id = guild_id
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        modal = CreateServiceModal(self.guild_id, self.parent_view)
        await interaction.response.send_modal(modal)



class ServiceActionsView(discord.ui.View):
    """View with actions for a selected service."""

    def __init__(
        self,
        service: dict,
        guild_id: int,
        user: discord.User,
        parent_view: "ServiceManagementView",
    ):
        super().__init__(timeout=300)
        self.service = service
        self.guild_id = guild_id
        self.user = user
        self.parent_view = parent_view

        self.add_item(StartServiceButton(service, parent_view))
        self.add_item(StopServiceButton(service, parent_view))
        self.add_item(RestartServiceButton(service, parent_view))
        self.add_item(ViewServiceConfigButton(service, guild_id, parent_view))
        self.add_item(UpdateServiceConfigButton(service, guild_id, parent_view))
        self.add_item(DeleteServiceButton(service, guild_id, parent_view))

    def create_embed(self) -> discord.Embed:
        """Create embed showing service details."""
        name = self.service.get("server_name", "Unknown")
        service_name = self.service.get("service_name", "Unknown")
        status = self.service.get("status", "Unknown")
        status_emoji = "🟢" if status.upper() == "RUNNING" else "🔴"

        embed = discord.Embed(
            title=f"🔧 Service: {name}",
            description=f"**Service Name:** `{service_name}`\n**Status:** {status_emoji} {status}",
            color=discord.Color.blue() if status.upper() == "RUNNING" else discord.Color.orange(),
        )

        embed.set_footer(text="Use the buttons below to manage this service")
        return embed


class StartServiceButton(Button):
    """Button to start a service."""

    def __init__(self, service: dict, parent_view: "ServiceManagementView"):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Start",
            emoji="▶️",
            custom_id="start_service",
            row=0,
        )
        self.service = service
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        agent_manager = getattr(interaction.client, "agent_manager", None)
        if not agent_manager:
            await interaction.followup.send("❌ Agent manager not available.", ephemeral=True)
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send("❌ No agent connected.", ephemeral=True)
            return

        service_name = self.service.get("service_name")
        result = await agent_manager.start_ark_service(agent_id, service_name)

        if result.get("error"):
            await interaction.followup.send(f"❌ Failed to start: {result['error']}", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Service **{service_name}** started.", ephemeral=True)
            await self.parent_view.refresh()


class StopServiceButton(Button):
    """Button to stop a service."""

    def __init__(self, service: dict, parent_view: "ServiceManagementView"):
        super().__init__(
            style=discord.ButtonStyle.danger,
            label="Stop",
            emoji="⏹️",
            custom_id="stop_service",
            row=0,
        )
        self.service = service
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        agent_manager = getattr(interaction.client, "agent_manager", None)
        if not agent_manager:
            await interaction.followup.send("❌ Agent manager not available.", ephemeral=True)
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send("❌ No agent connected.", ephemeral=True)
            return

        service_name = self.service.get("service_name")
        result = await agent_manager.stop_ark_service(agent_id, service_name)

        if result.get("error"):
            await interaction.followup.send(f"❌ Failed to stop: {result['error']}", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Service **{service_name}** stopped.", ephemeral=True)
            await self.parent_view.refresh()


class RestartServiceButton(Button):
    """Button to restart a service."""

    def __init__(self, service: dict, parent_view: "ServiceManagementView"):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Restart",
            emoji="🔄",
            custom_id="restart_service",
            row=0,
        )
        self.service = service
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        agent_manager = getattr(interaction.client, "agent_manager", None)
        if not agent_manager:
            await interaction.followup.send("❌ Agent manager not available.", ephemeral=True)
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send("❌ No agent connected.", ephemeral=True)
            return

        service_name = self.service.get("service_name")
        result = await agent_manager.restart_ark_service(agent_id, service_name)

        if result.get("error"):
            await interaction.followup.send(f"❌ Failed to restart: {result['error']}", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Service **{service_name}** restarted.", ephemeral=True)
            await self.parent_view.refresh()


class ViewServiceConfigButton(Button):
    """Button to view service configuration."""

    def __init__(self, service: dict, guild_id: int, parent_view: "ServiceManagementView"):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="View Config",
            emoji="📋",
            custom_id="view_service_config",
            row=1,
        )
        self.service = service
        self.guild_id = guild_id
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        agent_manager = getattr(interaction.client, "agent_manager", None)
        if not agent_manager:
            await interaction.followup.send("❌ Agent manager not available.", ephemeral=True)
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send("❌ No agent connected.", ephemeral=True)
            return

        server_name = self.service.get("server_name")
        result = await agent_manager.read_server_config(agent_id, server_name)

        if result.get("error"):
            await interaction.followup.send(f"❌ Failed to read config: {result['error']}", ephemeral=True)
            return

        config = result.get("data", {})

        embed = discord.Embed(
            title=f"📋 Service Config: {server_name}",
            color=discord.Color.blue(),
        )

        embed.add_field(name="Display Name", value=config.get("display_name", "N/A"), inline=True)
        embed.add_field(name="Map", value=config.get("map_name", "N/A"), inline=True)
        embed.add_field(name="Max Players", value=config.get("max_players", "N/A"), inline=True)

        embed.add_field(name="Game Port", value=config.get("game_port", "N/A"), inline=True)
        embed.add_field(name="Query Port", value=config.get("query_port", "N/A"), inline=True)
        embed.add_field(name="RCON Port", value=config.get("rcon_port", "N/A"), inline=True)

        embed.add_field(name="Server Path", value=config.get("server_path", "N/A"), inline=False)
        embed.add_field(name="SteamCMD Path", value=config.get("steamcmd_path", "N/A"), inline=False)

        mods = config.get("mods", "")
        embed.add_field(name="Mods", value=mods if mods else "None", inline=False)

        cluster_id = config.get("cluster_id", "")
        if cluster_id:
            embed.add_field(name="Cluster ID", value=cluster_id, inline=True)
            embed.add_field(name="Cluster Path", value=config.get("cluster_path", "N/A"), inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)


class UpdateServiceConfigButton(Button):
    """Button to update service configuration."""

    def __init__(self, service: dict, guild_id: int, parent_view: "ServiceManagementView"):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Edit Config",
            emoji="✏️",
            custom_id="update_service_config",
            row=1,
        )
        self.service = service
        self.guild_id = guild_id
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # Don't defer - modals must be sent as first response
        server_name = self.service.get("server_name")
        
        # Try database first (fast, no agent call needed)
        db_server = await server_config_db.get_ark_server_by_name(interaction.guild_id, server_name)
        
        if db_server:
            # Use database as source of truth
            current_config = {
                "display_name": db_server.get("display_name", ""),
                "max_players": str(db_server.get("max_players", "")),
                "mods": db_server.get("mods", ""),
                "cluster_id": db_server.get("cluster_id", ""),
                "cluster_path": db_server.get("cluster_path", ""),
            }
        else:
            # Fallback to registry if not in database
            agent_manager = getattr(interaction.client, "agent_manager", None)
            if not agent_manager:
                await interaction.response.send_message("❌ Agent manager not available.", ephemeral=True)
                return

            agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
            if not agent_id:
                await interaction.response.send_message("❌ No agent connected.", ephemeral=True)
                return
            
            result = await agent_manager.read_server_config(agent_id, server_name)
            
            if result.get("error"):
                await interaction.response.send_message(
                    f"❌ Server not found in database or registry: {server_name}",
                    ephemeral=True
                )
                return

            config = result.get("data", {})
            current_config = {
                "display_name": config.get("display_name", ""),
                "max_players": str(config.get("max_players", "")),
                "mods": config.get("mods", ""),
                "cluster_id": config.get("cluster_id", ""),
                "cluster_path": config.get("cluster_path", ""),
            }
        
        modal = UpdateServiceConfigModal(self.guild_id, server_name, current_config, self.parent_view)
        await interaction.response.send_modal(modal)


class DeleteServiceButton(Button):
    """Button to delete a service."""

    def __init__(self, service: dict, guild_id: int, parent_view: "ServiceManagementView"):
        super().__init__(
            style=discord.ButtonStyle.danger,
            label="Delete",
            emoji="🗑️",
            custom_id="delete_service",
            row=2,
        )
        self.service = service
        self.guild_id = guild_id
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        # Check DB for a linked bot server record
        await interaction.response.defer(ephemeral=True)

        service_name = self.service.get("service_name")
        server_name = self.service.get("server_name")
        linked_server = None

        try:
            all_servers = await server_config_db.get_ark_servers(self.guild_id, include_disabled=True)
            linked_server = next(
                (s for s in all_servers if s.get("service_name") == service_name), None
            )
        except Exception as e:
            logger.warning(f"Could not check DB for linked server: {e}")

        if linked_server:
            # Case B: matching DB record found — offer linked removal options
            view = LinkedRemoveServiceView(self.service, self.guild_id, linked_server, self.parent_view)
            embed = discord.Embed(
                title="⚠️ Linked Service & Bot Record",
                description=(
                    f"Windows service **`{service_name}`** is registered in the bot as "
                    f"**{linked_server['name']}**.\n\nWhat would you like to do?"
                ),
                color=discord.Color.orange(),
            )
            embed.add_field(
                name="🔧 Delete service only",
                value="Removes the Windows service and registry. Bot record stays.",
                inline=False,
            )
            embed.add_field(
                name="💥 Delete both",
                value="Removes the Windows service AND the bot's server record.",
                inline=False,
            )
        else:
            # Case A: no matching DB record — simple deletion
            view = DeleteServiceConfirmView(self.service, self.guild_id, self.parent_view)
            embed = discord.Embed(
                title="⚠️ Confirm Deletion",
                description=(
                    f"Are you sure you want to delete:\n\n"
                    f"**Server:** {server_name}\n**Service:** {service_name}\n\n"
                    f"This will remove the Windows service and registry configuration. "
                    f"Server files will NOT be deleted."
                ),
                color=discord.Color.orange(),
            )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class LinkedRemoveServiceView(discord.ui.View):
    """Confirmation view when a Windows service has a linked bot server record.

    Offers three options:
    - Delete service only (leave DB record)
    - Delete both (service + DB record)
    - Cancel
    """

    def __init__(
        self,
        service: dict,
        guild_id: int,
        linked_server: dict,
        parent_view: "ServiceManagementView",
    ):
        super().__init__(timeout=120)
        self.service = service
        self.guild_id = guild_id
        self.linked_server = linked_server
        self.parent_view = parent_view

    @discord.ui.button(label="Delete service only", style=discord.ButtonStyle.primary, emoji="🔧")
    async def service_only_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove Windows service; leave bot DB record intact."""
        await interaction.response.defer(ephemeral=True)

        agent_manager = getattr(interaction.client, "agent_manager", None)
        if not agent_manager:
            await interaction.followup.send("❌ Agent manager not available.", ephemeral=True)
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send("❌ No agent connected.", ephemeral=True)
            return

        server_name = self.service.get("server_name")
        service_name = self.service.get("service_name")
        result = await agent_manager.delete_server_service(agent_id, server_name, service_name)

        if result.get("error"):
            await interaction.followup.send(f"❌ Failed to delete service: {result['error']}", ephemeral=True)
        else:
            await interaction.followup.send(
                f"✅ Service **`{service_name}`** deleted. Bot record for **{self.linked_server['name']}** kept.",
                ephemeral=True,
            )
            if self.parent_view:
                await self.parent_view.refresh()

    @discord.ui.button(label="Delete both", style=discord.ButtonStyle.danger, emoji="💥")
    async def delete_both_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove Windows service AND the bot's DB record."""
        await interaction.response.defer(ephemeral=True)

        agent_manager = getattr(interaction.client, "agent_manager", None)
        errors = []

        if agent_manager:
            agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
            if agent_id:
                server_name = self.service.get("server_name")
                service_name = self.service.get("service_name")
                try:
                    result = await agent_manager.delete_server_service(agent_id, server_name, service_name)
                    if result.get("error"):
                        errors.append(f"Service deletion: {result['error']}")
                except Exception as e:
                    errors.append(f"Service deletion: {e}")

        try:
            success = await server_config_db.remove_ark_server(self.linked_server["id"])
            if not success:
                errors.append("DB record deletion failed")
        except Exception as e:
            errors.append(f"DB: {e}")

        await _sync_agent_config_for(interaction)

        service_name = self.service.get("service_name")
        if errors:
            msg = f"⚠️ Partial deletion:\n" + "\n".join(f"• {e}" for e in errors)
        else:
            msg = (
                f"✅ Service **`{service_name}`** and bot record for "
                f"**{self.linked_server['name']}** have both been removed."
            )

        await interaction.followup.send(msg, ephemeral=True)
        if self.parent_view:
            await self.parent_view.refresh()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Deletion cancelled.", embed=None, view=None)


class DeleteServiceConfirmView(discord.ui.View):
    """Confirmation view for service deletion."""

    def __init__(self, service: dict, guild_id: int, parent_view: "ServiceManagementView"):
        super().__init__(timeout=60)
        self.service = service
        self.guild_id = guild_id
        self.parent_view = parent_view

    @discord.ui.button(label="Delete Service", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        agent_manager = getattr(interaction.client, "agent_manager", None)
        if not agent_manager:
            await interaction.followup.send("❌ Agent manager not available.", ephemeral=True)
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send("❌ No agent connected.", ephemeral=True)
            return

        server_name = self.service.get("server_name")
        service_name = self.service.get("service_name")

        result = await agent_manager.delete_server_service(agent_id, server_name, service_name)

        if result.get("error"):
            await interaction.followup.send(f"❌ Failed to delete: {result['error']}", ephemeral=True)
        else:
            await interaction.followup.send(f"✅ Service **{service_name}** deleted.", ephemeral=True)
            await self.parent_view.refresh()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Deletion cancelled.", view=None)


class CreateServiceModal(Modal):
    """Modal for creating a new PhoenixARK service - Page 1: Basic Configuration (5 fields)."""

    def __init__(self, guild_id: int, parent_view: "ServiceManagementView"):
        super().__init__(title="➕ Create Service (1/3): Basic")
        self.guild_id = guild_id
        self.parent_view = parent_view

        self.service_name = TextInput(
            label="Service Name (Windows Service)",
            placeholder="e.g., PhoenixARK_Aberration",
            required=True,
            max_length=50,
        )
        self.add_item(self.service_name)

        self.map_name = TextInput(
            label="Map Name",
            placeholder="e.g., TheIsland, Aberration_WP",
            required=True,
            max_length=50,
        )
        self.add_item(self.map_name)

        self.game_port = TextInput(
            label="Game Port",
            placeholder="7777",
            default="7777",
            required=True,
            max_length=5,
        )
        self.add_item(self.game_port)

        self.query_port = TextInput(
            label="Query Port",
            placeholder="7778",
            default="7778",
            required=True,
            max_length=5,
        )
        self.add_item(self.query_port)

        self.rcon_port = TextInput(
            label="RCON Port",
            placeholder="27020",
            default="27020",
            required=True,
            max_length=6,
        )
        self.add_item(self.rcon_port)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            game_port = int(self.game_port.value)
            query_port = int(self.query_port.value)
            rcon_port = int(self.rcon_port.value)

            service_data = {
                "service_name": self.service_name.value,
                "map_name": self.map_name.value,
                "game_port": game_port,
                "query_port": query_port,
                "rcon_port": rcon_port,
            }

            # Pre-populate from linked DB server record so later pages can pre-fill
            linked_server = await server_config_db.get_ark_server_by_service_name(
                self.guild_id, self.service_name.value
            )
            if linked_server:
                service_data["existing_server"] = linked_server
                # Also seed top-level fields so pages 1/2 benefit too
                service_data.setdefault("map_name", linked_server.get("map_name", self.map_name.value))
                service_data.setdefault("game_port", linked_server.get("game_port", game_port))
                service_data.setdefault("query_port", linked_server.get("query_port", query_port))
                service_data.setdefault("rcon_port", linked_server.get("rcon_port", rcon_port))

            embed = discord.Embed(
                title="✅ Step 1/3: Basic Configuration",
                description=f"**{self.service_name.value}** - Map: {self.map_name.value}",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Ports",
                value=f"Game: {game_port} | Query: {query_port} | RCON: {rcon_port}",
                inline=True,
            )
            embed.add_field(
                name="📋 Next",
                value="Click **Continue** to configure server paths and passwords.",
                inline=False,
            )

            view = CreateServiceContinueView1(self.guild_id, service_data, self.parent_view)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid number! Ports must be numbers.", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in CreateServiceModal: {e}")
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


class CreateServiceContinueView1(discord.ui.View):
    """Continue button after page 1 - reuses message."""

    def __init__(self, guild_id: int, service_data: dict, parent_view: "ServiceManagementView"):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.service_data = service_data
        self.parent_view = parent_view

    @discord.ui.button(label="Continue →", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def continue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CreateServiceSettingsModal(self.guild_id, self.service_data, self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ Cancelled",
            description="Service creation cancelled.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class CreateServiceSettingsModal(Modal):
    """Modal for creating a new PhoenixARK service - Page 2: Server Settings (5 fields)."""

    def __init__(self, guild_id: int, service_data: dict, parent_view: "ServiceManagementView"):
        super().__init__(title="➕ Create Service (2/3): Settings")
        self.guild_id = guild_id
        self.service_data = service_data
        self.parent_view = parent_view

        self.battleye = TextInput(
            label="BattlEye Enabled (true/false)",
            placeholder="false",
            default="false",
            required=True,
            max_length=5,
        )
        self.add_item(self.battleye)

        self.logging = TextInput(
            label="Logging Enabled (true/false)",
            placeholder="true",
            default="true",
            required=True,
            max_length=5,
        )
        self.add_item(self.logging)

        self.mods = TextInput(
            label="Mods (comma-separated IDs)",
            placeholder="e.g., 123456,789012",
            default="",
            required=False,
            max_length=500,
        )
        self.add_item(self.mods)

        self.cluster_id = TextInput(
            label="Cluster ID (optional)",
            placeholder="Leave blank for single server",
            default="",
            required=False,
            max_length=100,
        )
        self.add_item(self.cluster_id)

        self.cluster_dir = TextInput(
            label="Cluster Directory Override (optional)",
            placeholder="e.g., D:\\ARK\\Cluster",
            default="",
            required=False,
            max_length=255,
        )
        self.add_item(self.cluster_dir)

    async def on_submit(self, interaction: discord.Interaction):
        self.service_data["battleye_enabled"] = self.battleye.value.lower() == "true"
        self.service_data["logging_enabled"] = self.logging.value.lower() == "true"
        self.service_data["mods"] = self.mods.value
        self.service_data["cluster_id"] = self.cluster_id.value
        self.service_data["cluster_dir_override"] = self.cluster_dir.value

        embed = discord.Embed(
            title="✅ Step 2/3: Server Settings",
            description=f"**{self.service_data['service_name']}** settings saved.",
            color=discord.Color.green(),
        )
        settings = [
            f"BattlEye: {self.service_data['battleye_enabled']}",
            f"Logging: {self.service_data['logging_enabled']}",
        ]
        if self.mods.value:
            settings.append(f"Mods: {self.mods.value[:50]}...")
        if self.cluster_id.value:
            settings.append(f"Cluster: {self.cluster_id.value}")
        embed.add_field(name="Settings", value="\n".join(settings), inline=False)
        embed.add_field(name="📋 Next", value="Click **Continue** to configure paths.", inline=False)

        view = CreateServiceContinueView2(self.guild_id, self.service_data, self.parent_view)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class CreateServiceContinueView2(discord.ui.View):
    """Continue button after page 2 - reuses message."""

    def __init__(self, guild_id: int, service_data: dict, parent_view: "ServiceManagementView"):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.service_data = service_data
        self.parent_view = parent_view

    @discord.ui.button(label="Continue →", style=discord.ButtonStyle.primary, emoji="📁")
    async def continue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = CreateServicePathsModal(self.guild_id, self.service_data, self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="❌ Cancelled",
            description="Service creation cancelled.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class CreateServicePathsModal(Modal):
    """Modal for creating a new PhoenixARK service - Page 3: Paths (2 fields)."""

    def __init__(self, guild_id: int, service_data: dict, parent_view: "ServiceManagementView"):
        super().__init__(title="➕ Create Service (3/3): Paths")
        self.guild_id = guild_id
        self.service_data = service_data
        self.parent_view = parent_view

        self.server_path = TextInput(
            label="Server Path",
            placeholder="e.g., D:\\ARK\\Servers\\Aberration",
            required=True,
            max_length=255,
        )
        self.add_item(self.server_path)

        self.steamcmd_path = TextInput(
            label="SteamCMD Path",
            placeholder="e.g., D:\\SteamCMD",
            required=True,
            max_length=255,
        )
        self.add_item(self.steamcmd_path)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        self.service_data["server_path"] = self.server_path.value
        self.service_data["steamcmd_path"] = self.steamcmd_path.value

        agent_manager = getattr(interaction.client, "agent_manager", None)
        if not agent_manager:
            await interaction.followup.send("❌ Agent manager not available.", ephemeral=True)
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send("❌ No agent connected.", ephemeral=True)
            return

        progress_embed = discord.Embed(
            title="🔄 Creating Service...",
            description=f"Creating **{self.service_data['service_name']}**...",
            color=discord.Color.blue(),
        )
        await interaction.followup.send(embed=progress_embed, ephemeral=True)

        result = await agent_manager.create_server_service(
            agent_id=agent_id,
            server_name=self.service_data["service_name"],
            display_name=self.service_data["service_name"],
            map_name=self.service_data["map_name"],
            game_port=self.service_data["game_port"],
            query_port=self.service_data["query_port"],
            rcon_port=27020,
            rcon_password="",
            server_password="",
            admin_password="",
            max_players=self.service_data["max_players"],
            server_path=self.service_data["server_path"],
            steamcmd_path=self.service_data["steamcmd_path"],
            mods=self.service_data.get("mods", ""),
            cluster_id=self.service_data.get("cluster_id", ""),
            cluster_path=self.service_data.get("cluster_dir_override", ""),
            battleye_enabled=self.service_data.get("battleye_enabled", False),
        )

        if result.get("error"):
            error_embed = discord.Embed(
                title="❌ Service Creation Failed",
                description=f"Error: {result['error']}",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)
        else:
            service_name = result.get("data", {}).get("service_name", "Unknown")

            try:
                await server_config_db.add_ark_server(
                    guild_id=interaction.guild_id,
                    name=self.service_data["service_name"],
                    host="localhost",
                    game_port=self.service_data["game_port"],
                    query_port=self.service_data["query_port"],
                    rcon_port=27020,
                    rcon_password="",
                    max_players=self.service_data["max_players"],
                    display_name=self.service_data["service_name"],
                    map_name=self.service_data["map_name"],
                    service_name=service_name,
                    server_path=self.service_data["server_path"],
                    steamcmd_path=self.service_data["steamcmd_path"],
                    cluster_id=self.service_data.get("cluster_id") or None,
                    cluster_path=self.service_data.get("cluster_dir_override") or None,
                    mods=self.service_data.get("mods") or None,
                )
                await _sync_agent_config_for(interaction)
            except Exception as db_error:
                logger.error(f"Failed to add server to database: {db_error}", exc_info=True)

            start_result = await agent_manager.start_ark_service(agent_id, service_name)

            success_embed = discord.Embed(
                title="✅ Service Created Successfully!",
                color=discord.Color.green(),
            )
            success_embed.add_field(name="Service", value=service_name, inline=True)
            success_embed.add_field(name="Map", value=self.service_data["map_name"], inline=True)

            if start_result.get("error"):
                success_embed.add_field(
                    name="⚠️ Not Started",
                    value=f"Start error: {start_result['error']}",
                    inline=False,
                )
            else:
                success_embed.add_field(name="🟢 Status", value="Service started", inline=False)

            await interaction.followup.send(embed=success_embed, ephemeral=True)

            if self.parent_view:
                await self.parent_view.refresh()


class CreateServiceContinueView(discord.ui.View):
    """Intermediate view after page 1 - shows Continue Setup button."""

    def __init__(self, guild_id: int, service_data: dict, parent_view: "ServiceManagementView"):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.service_data = service_data
        self.parent_view = parent_view

    @discord.ui.button(label="Continue Setup →", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def continue_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the paths & passwords modal."""
        modal = CreateServicePathsModal(self.guild_id, self.service_data, self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the setup process."""
        embed = discord.Embed(
            title="❌ Service Setup Cancelled",
            description="Service was not created. You can start over anytime.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class CreateServicePathsModal(Modal):
    """Modal for creating a new PhoenixARK service - Page 2: Paths & Passwords."""

    def __init__(self, guild_id: int, service_data: dict, parent_view: "ServiceManagementView"):
        super().__init__(title="➕ Create Service (2/3): Paths & Passwords")
        self.guild_id = guild_id
        self.service_data = service_data
        self.parent_view = parent_view

        # Get existing server data for pre-fill
        existing = service_data.get("existing_server") or {}

        self.rcon_password = TextInput(
            label="RCON Password",
            placeholder="Enter RCON password",
            default=existing.get("rcon_password", ""),
            required=True,
            max_length=50,
        )
        self.add_item(self.rcon_password)

        self.server_password = TextInput(
            label="Server Password (optional)",
            placeholder="Leave blank for no password",
            default="",  # Not stored in database
            required=False,
            max_length=50,
        )
        self.add_item(self.server_password)

        self.admin_password = TextInput(
            label="Admin Password (optional)",
            placeholder="Leave blank for no admin password",
            default="",  # Not stored in database
            required=False,
            max_length=50,
        )
        self.add_item(self.admin_password)

        self.server_path = TextInput(
            label="Server Path",
            placeholder="e.g., D:\\ARK\\Servers\\Island",
            default=existing.get("server_path", ""),
            required=True,
            max_length=255,
        )
        self.add_item(self.server_path)

        self.steamcmd_path = TextInput(
            label="SteamCMD Path",
            placeholder="e.g., D:\\SteamCMD",
            default=existing.get("steamcmd_path", ""),
            required=True,
            max_length=255,
        )
        self.add_item(self.steamcmd_path)

    async def on_submit(self, interaction: discord.Interaction):
        # Store data for page 3
        self.service_data["rcon_password"] = self.rcon_password.value
        self.service_data["server_password"] = self.server_password.value
        self.service_data["admin_password"] = self.admin_password.value
        self.service_data["server_path"] = self.server_path.value
        self.service_data["steamcmd_path"] = self.steamcmd_path.value

        embed = discord.Embed(
            title="✅ Step 2 Complete: Paths & Passwords Saved",
            description=f"**{self.service_data['service_name']}** paths and passwords saved.",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="📋 Next Step",
            value="Click **Continue Setup** to configure advanced settings (cluster, BattlEye, etc.).",
            inline=False,
        )

        view = CreateServiceAdvancedContinueView(self.guild_id, self.service_data, self.parent_view)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class CreateServiceAdvancedContinueView(discord.ui.View):
    """Intermediate view after page 2 - shows Continue Setup button."""

    def __init__(self, guild_id: int, service_data: dict, parent_view: "ServiceManagementView"):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.service_data = service_data
        self.parent_view = parent_view

    @discord.ui.button(label="Continue Setup →", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def continue_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open the advanced settings modal."""
        modal = CreateServiceAdvancedModal(self.guild_id, self.service_data, self.parent_view)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the setup process."""
        embed = discord.Embed(
            title="❌ Service Setup Cancelled",
            description="Service was not created. You can start over anytime.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class CreateServiceAdvancedModal(Modal):
    """Modal for creating a new PhoenixARK service - Page 3: Advanced Settings."""

    def __init__(self, guild_id: int, service_data: dict, parent_view: "ServiceManagementView"):
        super().__init__(title="➕ Create Service (3/3): Advanced")
        self.guild_id = guild_id
        self.service_data = service_data
        self.parent_view = parent_view

        # Get existing server data for pre-fill
        existing = service_data.get("existing_server") or {}

        self.max_players = TextInput(
            label="Max Players (default: 70)",
            placeholder="70",
            default=str(existing.get("max_players", 70)),
            required=False,
            max_length=3,
        )
        self.add_item(self.max_players)

        self.cluster_id = TextInput(
            label="Cluster ID (optional)",
            placeholder="Leave blank for single server",
            default=existing.get("cluster_id", ""),
            required=False,
            max_length=100,
        )
        self.add_item(self.cluster_id)

        self.cluster_path = TextInput(
            label="Cluster Path (optional)",
            placeholder="e.g., D:\\ARK\\Cluster",
            default=existing.get("cluster_path", ""),
            required=False,
            max_length=255,
        )
        self.add_item(self.cluster_path)

        self.mods = TextInput(
            label="Mods (comma-separated IDs, optional)",
            placeholder="e.g., 123456,789012",
            default=existing.get("mods", ""),
            required=False,
            max_length=500,
        )
        self.add_item(self.mods)

        self.battleye_enabled = TextInput(
            label="BattlEye Enabled (true/false, default: false)",
            placeholder="false",
            default="false",
            required=False,
            max_length=5,
        )
        self.add_item(self.battleye_enabled)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            max_players = int(self.max_players.value) if self.max_players.value else 70
            battleye_enabled = self.battleye_enabled.value.lower() != "false"

            agent_manager = getattr(interaction.client, "agent_manager", None)
            if not agent_manager:
                await interaction.followup.send("❌ Agent manager not available.", ephemeral=True)
                return

            agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
            if not agent_id:
                await interaction.followup.send("❌ No agent connected.", ephemeral=True)
                return

            # Show progress
            progress_msg = await interaction.followup.send(
                embed=discord.Embed(
                    title="🔄 Creating Service...",
                    description=f"Creating **{self.service_data['service_name']}** service...\n\nThis may take a few seconds.",
                    color=discord.Color.blue(),
                ),
                ephemeral=True,
                wait=True,
            )

            result = await agent_manager.create_server_service(
                agent_id=agent_id,
                server_name=self.service_data["service_name"],
                display_name=self.service_data["service_name"],
                map_name=self.service_data["map_name"],
                game_port=self.service_data["game_port"],
                query_port=self.service_data["query_port"],
                rcon_port=self.service_data["rcon_port"],
                rcon_password=self.service_data["rcon_password"],
                server_password=self.service_data.get("server_password", ""),
                admin_password=self.service_data.get("admin_password", ""),
                server_path=self.service_data["server_path"],
                steamcmd_path=self.service_data["steamcmd_path"],
                max_players=max_players,
                mods=self.mods.value,
                cluster_id=self.cluster_id.value,
                cluster_path=self.cluster_path.value,
                battleye_enabled=battleye_enabled,
            )

            if result.get("error"):
                await progress_msg.edit(
                    embed=discord.Embed(
                        title="❌ Service Creation Failed",
                        description=f"Error: {result['error']}",
                        color=discord.Color.red(),
                    )
                )
            else:
                service_name = result.get("data", {}).get("service_name", "Unknown")

                # Add server to database
                try:
                    server_id = await server_config_db.add_ark_server(
                        guild_id=interaction.guild_id,
                        name=self.service_data["service_name"],
                        host="localhost",  # Agent is local to the game server
                        game_port=self.service_data["game_port"],
                        query_port=self.service_data["query_port"],
                        rcon_port=self.service_data["rcon_port"],
                        rcon_password=self.service_data["rcon_password"],
                        max_players=max_players,
                        display_name=self.service_data["service_name"],
                        map_name=self.service_data["map_name"],
                        service_name=service_name,
                        server_path=self.service_data["server_path"],
                        steamcmd_path=self.service_data["steamcmd_path"],
                        cluster_id=self.cluster_id.value if self.cluster_id.value else None,
                        cluster_path=self.cluster_path.value if self.cluster_path.value else None,
                        mods=self.mods.value if self.mods.value else None,
                    )
                    logger.info(f"Added server to database: {self.service_data['service_name']} (ID: {server_id})")
                    await _sync_agent_config_for(interaction)
                except Exception as db_error:
                    logger.error(f"Failed to add server to database: {db_error}", exc_info=True)
                    # Continue even if database write fails - service is already created

                # Try to start the service
                start_result = await agent_manager.start_ark_service(agent_id, service_name)

                embed = discord.Embed(
                    title="✅ Service Created Successfully!",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Display Name", value=self.service_data["service_name"], inline=True)
                embed.add_field(name="Service Name", value=service_name, inline=True)
                embed.add_field(name="Map", value=self.service_data["map_name"], inline=True)

                if start_result.get("error"):
                    embed.add_field(
                        name="⚠️ Service Created but Not Started",
                        value=f"Start error: {start_result['error']}\n\nYou can start it manually with `/startservice {service_name}`",
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name="🟢 Service Started",
                        value="The ARK server service is now running.",
                        inline=False,
                    )

                await progress_msg.edit(embed=embed)

                # Refresh the parent view
                if self.parent_view:
                    await self.parent_view.refresh()

        except ValueError as e:
            await interaction.followup.send(f"❌ Invalid input: {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating service: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)



class UpdateServiceConfigModal(Modal, title="Update Service Configuration"):
    """Modal for updating service configuration."""

    display_name = TextInput(
        label="Display Name",
        placeholder="Server display name",
        required=False,
        max_length=100,
    )
    max_players = TextInput(
        label="Max Players",
        placeholder="e.g., 70",
        required=False,
        max_length=4,
    )
    mods = TextInput(
        label="Mods (comma-separated IDs)",
        placeholder="e.g., 123456,789012",
        required=False,
        max_length=500,
    )
    cluster_id = TextInput(
        label="Cluster ID",
        placeholder="Cluster identifier",
        required=False,
        max_length=100,
    )
    cluster_path = TextInput(
        label="Cluster Path",
        placeholder="e.g., D:\\ARK\\Cluster",
        required=False,
        max_length=255,
    )

    def __init__(self, guild_id: int, server_name: str, current_config: dict, parent_view: "ServiceManagementView"):
        super().__init__()
        self.guild_id = guild_id
        self.server_name = server_name
        self.current_config = current_config
        self.parent_view = parent_view

        # Pre-fill with current values
        self.display_name.default = current_config.get("display_name", "")
        self.max_players.default = str(current_config.get("max_players", ""))
        self.mods.default = current_config.get("mods", "")
        self.cluster_id.default = current_config.get("cluster_id", "")
        self.cluster_path.default = current_config.get("cluster_path", "")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        updates = {}
        
        # Only include fields that have changed
        if str(self.display_name) and str(self.display_name) != self.current_config.get("display_name", ""):
            updates["display_name"] = str(self.display_name)
        
        if str(self.max_players) and str(self.max_players) != str(self.current_config.get("max_players", "")):
            try:
                updates["max_players"] = int(str(self.max_players))
            except ValueError:
                await interaction.followup.send("❌ Max Players must be a number", ephemeral=True)
                return
        
        if str(self.mods) and str(self.mods) != self.current_config.get("mods", ""):
            updates["mods"] = str(self.mods)
        
        if str(self.cluster_id) and str(self.cluster_id) != self.current_config.get("cluster_id", ""):
            updates["cluster_id"] = str(self.cluster_id)
        
        if str(self.cluster_path) and str(self.cluster_path) != self.current_config.get("cluster_path", ""):
            updates["cluster_path"] = str(self.cluster_path)

        if not updates:
            await interaction.followup.send("ℹ️ No changes detected.", ephemeral=True)
            return

        # Update BOTH database and registry to keep them in sync
        try:
            # 1. Update database first
            from bot.database import server_config_db as server_config_db_module
            
            # Get server ID from database
            db_server = await server_config_db.get_ark_server_by_name(interaction.guild_id, self.server_name)
            
            if db_server and db_server.get("id"):
                # Update database
                await server_config_db.update_ark_server(
                    server_id=db_server["id"],
                    **updates
                )
                logger.info(f"Updated database for {self.server_name}: {updates}")
            
            # 2. Update registry via agent
            agent_manager = getattr(interaction.client, "agent_manager", None)
            if agent_manager:
                agent_id = await agent_manager.get_connected_agent_for_guild(interaction.guild_id)
                if agent_id:
                    result = await agent_manager.update_server_config(
                        agent_id=agent_id,
                        server_name=self.server_name,
                        **updates,
                    )
                    
                    if result.get("error"):
                        logger.warning(f"Registry update failed for {self.server_name}: {result['error']}")
            
            await interaction.followup.send(
                f"✅ Configuration updated for **{self.server_name}**",
                ephemeral=True,
            )
            await self.parent_view.refresh()
            
        except Exception as e:
            logger.error(f"Failed to update config: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to update: {e}", ephemeral=True)



class SetupGUI(commands.Cog):
    """Interactive setup GUI for bot configuration."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

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


    @app_commands.command(name="setup", description="🛠️ Interactive setup wizard (admin only)")
    async def setup_wizard(self, interaction: discord.Interaction):
        """Open the interactive setup GUI wizard."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        view = SetupMainView(interaction.guild_id, interaction.user, interaction.guild, self.bot)
        await view.load_config()
        embed = await view.create_main_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="servercfg",
        description="⚙️ Manage ARK servers - add, edit, remove, and configure servers",
    )
    async def server_cfg(self, interaction: discord.Interaction):
        """Open the server management GUI."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        server_view = ManageServersView(interaction.guild_id, interaction.user, interaction.guild)
        await server_view.load_servers()
        embed = server_view.create_embed()

        await interaction.response.send_message(embed=embed, view=server_view, ephemeral=True)
        # Capture the message for refresh capability
        server_view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(SetupGUI(bot))
