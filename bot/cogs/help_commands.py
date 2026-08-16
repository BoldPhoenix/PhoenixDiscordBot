"""
Interactive Help System with GUI menus for easy command navigation.
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button

from bot.utils.config import Config


class HelpCategory:
    """Represents a command category."""

    def __init__(
        self, name: str, emoji: str, description: str, commands: dict, gui_command: str = None
    ):
        self.name = name
        self.emoji = emoji
        self.description = description
        self.commands = commands  # {command_name: description}
        self.gui_command = gui_command  # The GUI command for this category


class HelpView(View):
    """Interactive help menu with select dropdown."""

    def __init__(self, categories: dict, command_mentions: dict = None, timeout: int = 180):
        super().__init__(timeout=None)
        self.categories = categories
        self.command_mentions = command_mentions or {}  # {command_name: clickable_mention}
        self.current_category = None

        # Add category selector
        self.category_select = Select(
            placeholder="Select a category...",
            options=[
                discord.SelectOption(
                    label=cat.name, description=cat.description, emoji=cat.emoji, value=key
                )
                for key, cat in categories.items()
            ],
        )
        self.category_select.callback = self.category_callback
        self.add_item(self.category_select)

        # Add navigation buttons
        self.add_item(BackButton())
        self.add_item(AllCommandsButton())

    async def category_callback(self, interaction: discord.Interaction):
        """Handle category selection."""
        category_key = self.category_select.values[0]
        category = self.categories[category_key]
        self.current_category = category_key

        embed = self.create_category_embed(category)
        await interaction.response.edit_message(embed=embed, view=self)

    def create_category_embed(self, category: HelpCategory) -> discord.Embed:
        """Create an embed for a specific category."""
        # Build description with GUI command link at top
        desc_parts = []
        if category.gui_command:
            desc_parts.append(f"**`{category.gui_command}`** ← Click to open GUI")
        desc_parts.append(category.description)

        embed = discord.Embed(
            title=f"{category.emoji} {category.name}",
            description="\n".join(desc_parts),
            color=discord.Color.blue(),
        )

        # Add commands (skip the GUI command since it's shown above)
        for cmd_name, cmd_desc in category.commands.items():
            # Skip GUI commands - they're shown in description
            if "🎨" in cmd_desc or cmd_name == category.gui_command:
                continue
            embed.add_field(name=f"`{cmd_name}`", value=cmd_desc, inline=False)

        embed.set_footer(text="Select a category above or click ⬅️ to go back | Click ❌ to close")
        return embed

    def create_main_menu_embed(self) -> discord.Embed:
        """Create the main help menu embed."""
        embed = discord.Embed(
            title="🤖 Phoenix ARK Bot Help Menu",
            description="A feature packed server manager for Ark: Survival Ascended with tools for Discord!",
            color=discord.Color.blue(),
        )

        # Add all categories with GUI command link at top
        for category in self.categories.values():
            # Build field value with GUI link first, then description
            field_parts = []
            if category.gui_command:
                # Use clickable mention if available, otherwise fallback
                cmd_name = category.gui_command.lstrip("/")
                mention = self.command_mentions.get(cmd_name, f"`{category.gui_command}`")
                field_parts.append(f"**{mention}**")
            field_parts.append(category.description)

            # Add command preview (simplified to avoid timeout)
            cmd_list = list(category.commands.keys())
            commands_preview = ", ".join([f"`{cmd.split()[0]}`" for cmd in cmd_list[:3]])
            if len(category.commands) > 3:
                commands_preview += f" ... (+{len(category.commands) - 3} more)"
            field_parts.append(commands_preview)

            embed.add_field(
                name=f"{category.emoji} **{category.name}**",
                value="\n".join(field_parts),
                inline=True,
            )

        embed.add_field(name="", value="", inline=True)  # Spacer for layout

        embed.set_footer(
            text="Use the dropdown menu below to select a category | Click 📋 for all commands | Click ❌ to close"
        )
        return embed

    def create_all_commands_embed(self) -> discord.Embed:
        """Create an embed showing all commands organized by category."""
        embed = discord.Embed(
            title="📋 All Commands Reference",
            description="Complete list of all available bot commands, organized by category.",
            color=discord.Color.green(),
        )

        # Add each category with all its commands
        for key, category in self.categories.items():
            # Build command list for this category
            cmd_list = []
            for cmd_name, cmd_desc in category.commands.items():
                # Skip GUI command indicators
                if "🎨" in cmd_desc:
                    continue
                cmd_list.append(f"**{cmd_name}** - {cmd_desc}")

            if cmd_list:
                # Join commands with newlines, truncate to stay under Discord's 1024-char field limit
                commands_text = "\n".join(cmd_list)
                if len(commands_text) > 900:
                    commands_text = "\n".join(cmd_list[:12])
                    if len(cmd_list) > 12:
                        commands_text += f"\n... (+{len(cmd_list) - 12} more commands)"
                # Final guard to ensure <=1024
                if len(commands_text) > 1024:
                    commands_text = commands_text[:1000] + "\n... (truncated)"

                embed.add_field(
                    name=f"{category.emoji} {category.name}", value=commands_text, inline=False
                )

        embed.set_footer(text="Click ⬅️ to return to main menu | Click ❌ to close")
        return embed


class BackButton(Button):
    """Button to go back to main menu."""

    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.secondary, emoji="◀️", label="Back", custom_id="help_back"
        )

    async def callback(self, interaction: discord.Interaction):
        view: HelpView = self.view
        embed = view.create_main_menu_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class AllCommandsButton(Button):
    """Button to show all commands."""

    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.primary,
            emoji="📋",
            label="All Commands",
            custom_id="help_all_commands",
        )

    async def callback(self, interaction: discord.Interaction):
        view: HelpView = self.view
        embed = view.create_all_commands_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class HelpCommands(commands.Cog):
    """Interactive help system with GUI navigation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.categories = self._build_categories()
        self.command_mentions = {}  # Cache for command mentions {name: mention_string}
        self._cache_ready = False

    async def cog_load(self):
        """Called when the cog is loaded. Fetch command IDs at startup."""
        # Schedule the command mention fetch after bot is ready
        self.bot.loop.create_task(self._delayed_fetch_commands())

    async def _delayed_fetch_commands(self):
        """Fetch command mentions after bot is fully ready."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(1)  # Wait for commands to sync
        await self._fetch_all_command_mentions()

    async def _fetch_all_command_mentions(self):
        """Fetch all command mentions and populate the cache."""
        if self._cache_ready:
            return  # Already fetched

        try:
            if not self.bot.guilds:
                return

            guild = self.bot.guilds[0]
            synced_commands = await self.bot.tree.fetch_commands(guild=guild)

            for cmd in synced_commands:
                mention = f"</{cmd.name}:{cmd.id}>"
                self.command_mentions[cmd.name] = mention

            self._cache_ready = True
            print(f"Cached {len(self.command_mentions)} command mentions")
        except Exception:
            pass  # Silently fail, will use backtick format

    async def _get_command_mention(self, command_name: str) -> str:
        """Get a clickable command mention string for a slash command.

        Returns </command:id> format for clickable commands, or fallback to `command` if not found.
        """
        # Remove leading slash if present
        cmd_name = command_name.lstrip("/")

        # Check cache first
        if cmd_name in self.command_mentions:
            return self.command_mentions[cmd_name]

        # Try to find the command ID from the bot's command tree
        try:
            # Fetch synced commands from Discord to get actual IDs
            if self.bot.guilds:
                guild = self.bot.guilds[0]  # Use first guild
                synced_commands = await self.bot.tree.fetch_commands(guild=guild)

                for cmd in synced_commands:
                    if cmd.name == cmd_name:
                        mention = f"</{cmd.name}:{cmd.id}>"
                        self.command_mentions[cmd_name] = mention
                        return mention

                # Also check global commands
                global_commands = await self.bot.tree.fetch_commands()
                for cmd in global_commands:
                    if cmd.name == cmd_name:
                        mention = f"</{cmd.name}:{cmd.id}>"
                        self.command_mentions[cmd_name] = mention
                        return mention
        except Exception:
            pass  # Fall through to fallback

        # Fallback: return non-clickable format
        return f"`/{cmd_name}`"

    def create_all_commands_embed(self) -> discord.Embed:
        """Create an embed showing all commands organized by category."""
        embed = discord.Embed(
            title="📋 All Commands Reference",
            description="Complete list of all available bot commands, organized by category.",
            color=discord.Color.green(),
        )

        for key, category in self.categories.items():
            cmd_list = []
            for cmd_name, cmd_desc in category.commands.items():
                if "🎨" in cmd_desc:
                    continue
                cmd_list.append(f"**{cmd_name}** - {cmd_desc}")

            if cmd_list:
                commands_text = "\n".join(cmd_list)
                if len(commands_text) > 900:
                    commands_text = "\n".join(cmd_list[:12])
                    if len(cmd_list) > 12:
                        commands_text += f"\n... (+{len(cmd_list) - 12} more commands)"
                if len(commands_text) > 1024:
                    commands_text = commands_text[:1000] + "\n... (truncated)"
                embed.add_field(
                    name=f"{category.emoji} {category.name}", value=commands_text, inline=False
                )

        embed.set_footer(text="Click ⬅️ to return to main menu | Click ❌ to close")
        return embed

    def _build_categories(self) -> dict:
        """Build the command categories."""
        categories = {
            "setup": HelpCategory(
                name="Setup & Configuration",
                emoji="🛠️",
                description="Bot setup, server management, and admin tools",
                gui_command="/setup",
                commands={
                    "/setup": "Open the setup wizard (servers, channels, roles, hosting type)",
                    "/servermgmt": "[ADMIN] Server control panel (start/stop/restart/update/backup)",
                    "/maintenance": "[ADMIN] Configure backups, updates, and schedules",
                    "/remote_management": "[ADMIN] Open remote agent management panel",
                    "/reloadservers": "[ADMIN] Reload server list from database",
                    "/subscription": "[ADMIN] View your subscription tier and status",
                    "/subscribe": "[ADMIN] Upgrade to Premium or Lifetime",
                    "/ping": "Check bot latency",
                },
            ),
            "monitoring": HelpCategory(
                name="Monitoring & RCON",
                emoji="🖥️",
                description="Live server monitoring and RCON commands",
                gui_command=None,
                commands={
                    "/listplayers": "Show all online players across all servers",
                    "/findplayer <name>": "Find which server a specific player is on",
                    "/saveworld [server]": "[ADMIN] Force save the world (one or all servers)",
                    "/destroywilddinos [server]": "[ADMIN] Wipe all wild dinos (one or all servers)",
                    "/whitelistplayer <steam_id> <server>": "[ADMIN] Add a player to the server whitelist",
                    "/giveexptoplayer <player> <xp> <server>": "[ADMIN] Give XP to a player",
                    "/getchat <server>": "[ADMIN] View recent in-game chat",
                },
            ),
            "mods": HelpCategory(
                name="Mods, INI & Logs",
                emoji="🔧",
                description="Mod management, INI editing, and server log viewing",
                gui_command="/modmgmt",
                commands={
                    "/modmgmt": "[ADMIN] Open mod management panel (install/remove/update mods)",
                    "/setmodchannel": "[ADMIN] Set channel for mod list embeds",
                    "/refreshmods": "[ADMIN] Refresh and re-post the mod list",
                    "/inimgmt": "[ADMIN] Open INI settings editor",
                    "/serverlogs <server>": "[ADMIN] View server logs with pagination (Premium)",
                    "/searchlogs <server> <pattern>": "[ADMIN] Search logs for a pattern (Premium)",
                    "/logstats <server>": "[ADMIN] View log statistics summary (Premium)",
                },
            ),
            "players": HelpCategory(
                name="Players & Economy",
                emoji="👥",
                description="Player linking, management, and Phoenix Coins economy (Premium)",
                gui_command="/playermgmt",
                commands={
                    "/player": "View and manage your player account / link your ARK EOS ID",
                    "/listlinkedplayers": "[ADMIN] List all players with linked ARK accounts",
                    "/playermgmt": "[ADMIN] Open player management interface",
                    "/economycfg": "[ADMIN] Open economy configuration panel",
                    "/leaderboard": "View top players ranked by game wins per game type",
                },
            ),
            "shop": HelpCategory(
                name="Shop & Games",
                emoji="🛒",
                description="In-game item shop, arcade games, and starter kits (Premium)",
                gui_command="/shop",
                commands={
                    "/shop": "Browse the Phoenix ARK item shop",
                    "/buy <item>": "Quickly find and purchase a shop item by name",
                    "/shopcfg": "[ADMIN] Configure shop settings and items",
                    "/uploadshop <file>": "[ADMIN] Bulk import shop items from Excel or CSV",
                    "/downloadshop": "[ADMIN] Export all shop items to Excel",
                    "/downloadsample": "[ADMIN] Download blank shop import template",
                    "/games": "Open the Phoenix Game System (Blackjack, Dice, and more)",
                    "/kit": "View and claim your starter kits",
                    "/kitcfg": "[ADMIN] Create and manage starter kits",
                },
            ),
            "analytics": HelpCategory(
                name="Analytics & AI",
                emoji="📊",
                description="Server analytics, reports, leaderboards, and AI assistant (Premium)",
                gui_command="/analytics",
                commands={
                    "/analytics": "Open interactive ARK analytics dashboard (includes ARK cluster leaderboards)",
                    "/recordsnapshot": "[ADMIN] Record current server data snapshot",
                    "/exportdata <type>": "[ADMIN] Export analytics data to CSV",
                    "/report players": "Generate a player activity chart report",
                    "/report economy": "Generate a coin economy chart report",
                    "/askphoenix <question>": "Ask the Phoenix AI assistant anything about your servers",
                },
            ),
        }
        return categories

    @app_commands.command(name="help", description="Interactive help menu with command categories")
    async def help_command(self, interaction: discord.Interaction):
        """Display the interactive help menu."""
        # Create and send the response immediately without defer
        view = HelpView(self.categories, self.command_mentions)
        embed = view.create_main_menu_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="commands", description="Quick list of all available commands")
    async def commands_list(self, interaction: discord.Interaction):
        """Display a simple list of all commands."""
        embed = discord.Embed(
            title="📋 All Commands",
            description="Complete list of bot commands",
            color=discord.Color.blue(),
        )

        for key, category in self.categories.items():
            commands_text = "\n".join([f"`{cmd}`" for cmd in category.commands.keys()])
            embed.add_field(
                name=f"{category.emoji} {category.name}", value=commands_text, inline=False
            )

        embed.set_footer(text="Use /help for an interactive menu")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="about", description="About this bot")
    async def about_command(self, interaction: discord.Interaction):
        """Display bot information."""
        from bot.database import server_config_db, players_db, subscription_db
        
        embed = discord.Embed(
            title="🤖 Phoenix ARK Bot",
            description="The ultimate Discord bot for ARK: Survival Ascended server management",
            color=discord.Color.gold(),
        )

        # === GLOBAL STATS ===
        total_guilds = len(self.bot.guilds)
        total_users = sum(guild.member_count or 0 for guild in self.bot.guilds)
        
        # Count total ARK servers across all guilds
        total_ark_servers = 0
        for guild in self.bot.guilds:
            try:
                servers = await server_config_db.get_ark_servers(guild.id)
                total_ark_servers += len(servers)
            except:
                pass

        embed.add_field(
            name="📊 Global Stats",
            value=f"{total_guilds} Discord Servers | {total_users:,} Users | {total_ark_servers} ARK Servers",
            inline=False,
        )

        # === LOCAL STATS (this guild) ===
        if interaction.guild_id:
            guild_servers = await server_config_db.get_ark_servers(interaction.guild_id)
            linked_players = await players_db.get_linked_player_count(interaction.guild_id)
            sub = await subscription_db.get_subscription(interaction.guild_id)
            tier = subscription_db.get_effective_tier(sub) if sub else "free"
            tier_label = tier.capitalize()

            embed.add_field(
                name="🖥️ This Server",
                value=f"{len(guild_servers)} ARK Servers | {linked_players} Linked Players | {tier_label} Tier",
                inline=False,
            )

        # === FEATURES BY TIER ===
        free_features = (
            "• Server management (start/stop/restart)\n"
            "• Mod installation & management\n"
            "• INI file editing\n"
            "• Backups & updates\n"
            "• Chat relay & voice status\n"
            "• Basic RCON commands"
        )
        premium_features = (
            "• Phoenix Coins economy\n"
            "• In-game item shop\n"
            "• Arcade games\n"
            "• Starter kits\n"
            "• Player linking & management\n"
            "• Analytics dashboard\n"
            "• AI assistant"
        )

        embed.add_field(name="🆓 Free Tier (2 servers)", value=free_features, inline=True)
        embed.add_field(name="⭐ Premium Tier", value=premium_features, inline=True)

        embed.set_footer(text="Use /subscribe to upgrade | /help for commands")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # REMOVED: /info command - duplicate of /about (keeping /about as it's more comprehensive)


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(HelpCommands(bot))
