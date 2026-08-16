"""
Player/Economy Management GUI - Interactive interface for managing users and economy.
Provides visual tools for granting coins, managing player links, and viewing user info.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button, Modal, TextInput
from typing import Optional, List
import logging

from bot.database import user_db, players_db, server_config_db
from bot.utils.config import Config
from bot.utils.arkids_api import get_arkids_client
from bot.database.store_db import get_all_items
from bot.rcon.client import RCONManager

logger = logging.getLogger("PlayerGUI")


class PlayerManagementView(View):
    """Main player/economy management interface."""

    def __init__(self, guild_id: int, user: discord.User, guild: discord.Guild, timeout: int = 300):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.guild = guild

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This management panel is not for you!", ephemeral=True
            )
            return False
        return True

    def create_main_embed(self) -> discord.Embed:
        """Create the main player management embed."""
        embed = discord.Embed(
            title="👥 Player & Economy Management",
            description=(
                "Manage player accounts, Phoenix Coins, and player linking.\n\n"
                "**Available Actions:**\n"
                "• Grant coins to users\n"
                "• View user information and stats\n"
                "• Link/unlink player accounts\n"
                "• Search for players"
            ),
            color=discord.Color.blue(),
        )

        embed.add_field(
            name=f"{Config.CURRENCY_EMOJI} Economy System",
            value=(
                f"Currency: **{Config.CURRENCY_NAME}**\n"
                f"Starting Balance: **{Config.SHOP_STARTING_BALANCE}**"
            ),
            inline=True,
        )

        embed.set_footer(text="💡 Select an action below")
        return embed


class PlayerMainView(PlayerManagementView):
    """Main player management view with action buttons."""

    def __init__(
        self,
        guild_id: int,
        user: discord.User,
        guild: discord.Guild,
        bot: commands.Bot = None,
        timeout: int = 300,
    ):
        super().__init__(guild_id, user, guild, timeout)
        self.bot = bot

        self.add_item(PlayerActionButton("Grant Coins", "💰", "grant"))
        self.add_item(PlayerActionButton("User Info", "👤", "userinfo"))
        self.add_item(PlayerActionButton("Give Item", "📦", "give_item"))
        # Give Creature disabled - not possible via RCON in ASA
        # self.add_item(PlayerActionButton("Give Creature", "🦖", "give_creature"))
        self.add_item(PlayerActionButton("Link Player", "🔗", "link"))
        self.add_item(PlayerActionButton("Unlink Player", "🔓", "unlink"))
        self.add_item(PlayerActionButton("Search Player", "🔍", "search"))


class PlayerActionButton(Button):
    """Button for player management actions."""

    def __init__(self, label: str, emoji: str, action: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=label,
            emoji=emoji,
            custom_id=f"player_{action}",
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        view: PlayerMainView = self.view

        if self.action == "grant":
            # Show user select for granting coins
            grant_view = GrantCoinsView(view.guild_id, view.user, view.guild)
            embed = grant_view.create_embed()
            await interaction.response.send_message(embed=embed, view=grant_view, ephemeral=True)

        elif self.action == "userinfo":
            # Show user select for viewing info
            info_view = UserInfoSelectView(view.guild_id, view.user, view.guild)
            embed = info_view.create_embed()
            await interaction.response.send_message(embed=embed, view=info_view, ephemeral=True)

        elif self.action == "give_item":
            # Show new view-based give item panel (dropdown players + inline search)
            import logging

            logging.getLogger("ArkBot").info("Give Item button clicked - opening panel view")
            try:
                from bot.cogs.enhanced_give_item import GiveItemPanelView

                player_gui_cog = interaction.client.get_cog("PlayerGUI")
                if not player_gui_cog:
                    await interaction.response.send_message(
                        "❌ PlayerGUI cog not found.", ephemeral=True
                    )
                    return
                panel = GiveItemPanelView(player_gui_cog.bot, interaction.user)
                # Defer first to allow us to pre-load players without requiring user clicks
                await interaction.response.defer(ephemeral=True)
                try:
                    await panel.load_linked_players()
                except Exception as e:
                    logger.error(
                        f"Error loading linked players for Give Item panel: {e}", exc_info=True
                    )
                embed = discord.Embed(
                    title="📦 Give Item to Player",
                    description=(
                        "Select a player and item to give.\n\n"
                        "**Features:**\n"
                        "✅ Auto-detects which server player is on\n"
                        "✅ Search items from database\n"
                        "✅ No server selection needed"
                    ),
                    color=discord.Color.orange(),
                )
                await interaction.followup.send(embed=embed, view=panel, ephemeral=True)
            except Exception as e:
                logging.getLogger("ArkBot").error(f"Give Item panel error: {e}", exc_info=True)
                await interaction.response.send_message(
                    f"❌ Error opening give item UI: {e}", ephemeral=True
                )

        elif self.action == "give_creature":
            # Show give dino panel
            logger.info("Give Creature button clicked - opening dino panel view")
            try:
                from bot.cogs.enhanced_give_item import GiveDinoPanelView

                player_gui_cog = interaction.client.get_cog("PlayerGUI")
                if not player_gui_cog:
                    await interaction.response.send_message(
                        "❌ PlayerGUI cog not found.", ephemeral=True
                    )
                    return
                panel = GiveDinoPanelView(player_gui_cog.bot, interaction.user)
                await interaction.response.defer(ephemeral=True)
                try:
                    await panel.load_linked_players()
                except Exception as e:
                    logger.error(
                        f"Error loading linked players for Give Dino panel: {e}", exc_info=True
                    )
                await interaction.followup.send(
                    embed=panel.create_embed(), view=panel, ephemeral=True
                )
            except Exception as e:
                logger.error(f"Give Dino panel error: {e}", exc_info=True)
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"❌ Error opening give dino UI: {e}", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ Error opening give dino UI: {e}", ephemeral=True
                    )

        elif self.action == "link":
            # Show link player modal
            modal = LinkPlayerModal()
            await interaction.response.send_modal(modal)

        elif self.action == "unlink":
            # Show user select for unlinking
            unlink_view = UnlinkPlayerView(view.guild_id, view.user, view.guild)
            embed = unlink_view.create_embed()
            await interaction.response.send_message(embed=embed, view=unlink_view, ephemeral=True)

        elif self.action == "search":
            # Show search modal
            modal = SearchPlayerModal(view.guild)
            await interaction.response.send_modal(modal)


class GrantCoinsView(View):
    """View for granting coins to a user."""

    def __init__(self, guild_id: int, user: discord.User, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.guild = guild
        self.selected_user = None

        # Add user select
        select = discord.ui.UserSelect(
            placeholder="Select a user to grant coins...", custom_id="grant_user_select"
        )
        select.callback = self.user_selected
        self.add_item(select)

    async def user_selected(self, interaction: discord.Interaction):
        """Handle user selection."""
        user_id = int(interaction.data["values"][0])
        self.selected_user = self.guild.get_member(user_id)

        if self.selected_user:
            modal = GrantCoinsModal(self.selected_user)
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message("❌ User not found!", ephemeral=True)

    def create_embed(self) -> discord.Embed:
        """Create grant coins embed."""
        embed = discord.Embed(
            title="💰 Grant Phoenix Coins",
            description=(
                "Select a user from the dropdown below to grant them Phoenix Coins.\n\n"
                f"**Currency:** {Config.CURRENCY_NAME} {Config.CURRENCY_EMOJI}"
            ),
            color=discord.Color.gold(),
        )
        return embed


class GrantCoinsModal(Modal):
    """Modal for entering coin amount to grant."""

    def __init__(self, target_user: discord.Member):
        super().__init__(title=f"💰 Grant Coins to {target_user.display_name[:30]}")
        self.target_user = target_user

        self.amount = TextInput(
            label="Amount of Phoenix Coins", placeholder="e.g., 1000", required=True, max_length=10
        )
        self.add_item(self.amount)

        self.reason = TextInput(
            label="Reason (optional)",
            placeholder="e.g., Event winner, Bug compensation",
            required=False,
            max_length=200,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
            if amount <= 0:
                raise ValueError("Amount must be positive")

            # Ensure user exists in database
            await user_db.create_or_update_user(self.target_user.id, str(self.target_user))

            # Grant coins
            reason = self.reason.value or f"Admin grant by {interaction.user}"
            new_balance = await user_db.add_coins(
                self.target_user.id, amount, reason, interaction.user.id
            )

            embed = discord.Embed(
                title="✅ Coins Granted",
                description=f"Granted **{amount}** {Config.CURRENCY_EMOJI} to {self.target_user.mention}",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="New Balance", value=f"{new_balance} {Config.CURRENCY_EMOJI}", inline=True
            )
            if self.reason.value:
                embed.add_field(name="Reason", value=self.reason.value, inline=False)
            embed.set_footer(text=f"Granted by {interaction.user}")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid amount! Please enter a positive number.", ephemeral=True
            )


class UserInfoSelectView(View):
    """View for selecting a user to view info."""

    def __init__(self, guild_id: int, user: discord.User, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.guild = guild

        select = discord.ui.UserSelect(
            placeholder="Select a user to view info...", custom_id="info_user_select"
        )
        select.callback = self.user_selected
        self.add_item(select)

    async def user_selected(self, interaction: discord.Interaction):
        """Handle user selection for info view."""
        user_id = int(interaction.data["values"][0])
        member = self.guild.get_member(user_id)

        if member:
            # Get user info from database
            db_user = await user_db.get_user(user_id)
            player_link = await players_db.get_player_by_discord_id(user_id)

            embed = discord.Embed(
                title=f"👤 User Info: {member.display_name}", color=discord.Color.blue()
            )

            embed.set_thumbnail(url=member.display_avatar.url)

            # Discord info
            embed.add_field(
                name="📱 Discord",
                value=(
                    f"**Username:** {member.name}\n"
                    f"**ID:** {member.id}\n"
                    f"**Joined Server:** {member.joined_at.strftime('%Y-%m-%d') if member.joined_at else 'Unknown'}"
                ),
                inline=True,
            )

            # Economy info
            if db_user:
                balance = db_user.get("phoenix_coins", 0)
                embed.add_field(
                    name=f"{Config.CURRENCY_EMOJI} Economy",
                    value=(
                        f"**Balance:** {balance} coins\n"
                        f"**Last Seen:** {(db_user.get('last_seen') or 'Never')[:10]}"
                    ),
                    inline=True,
                )
            else:
                embed.add_field(
                    name=f"{Config.CURRENCY_EMOJI} Economy", value="Not registered", inline=True
                )

            # ARK link info
            if player_link:
                embed.add_field(
                    name="🎮 ARK Link",
                    value=(
                        f"**EOS ID:** `{player_link['eos_id']}`\n"
                        f"**Last Server:** {player_link.get('last_seen_server', 'Unknown')}\n"
                        f"**Linked:** {(player_link.get('created_at') or 'Unknown')[:10]}"
                    ),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="🎮 ARK Link",
                    value="❌ Not linked - Use `/linkplayer` to link",
                    inline=False,
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("❌ User not found!", ephemeral=True)

    def create_embed(self) -> discord.Embed:
        """Create user info selection embed."""
        embed = discord.Embed(
            title="👤 View User Info",
            description="Select a user from the dropdown to view their account information.",
            color=discord.Color.blue(),
        )
        return embed


class LinkPlayerModal(Modal):
    """Modal for linking a player's Discord to their EOS ID."""

    def __init__(self):
        super().__init__(title="🔗 Link Player Account")

        self.discord_id = TextInput(
            label="Discord User ID",
            placeholder="e.g., 123456789012345678",
            required=True,
            max_length=20,
        )
        self.add_item(self.discord_id)

        self.eos_id = TextInput(
            label="EOS ID (from ARK)",
            placeholder="e.g., 00010203040506070809...",
            required=True,
            max_length=50,
        )
        self.add_item(self.eos_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            discord_id = int(self.discord_id.value)
            eos_id = self.eos_id.value.strip()

            # Link the player
            success = await players_db.link_player(self.guild_id, discord_id, eos_id)

            if success:
                embed = discord.Embed(
                    title="✅ Player Linked",
                    description=f"Discord <@{discord_id}> linked to EOS ID.",
                    color=discord.Color.green(),
                )
                embed.add_field(name="EOS ID", value=f"`{eos_id}`", inline=False)
            else:
                embed = discord.Embed(
                    title="❌ Link Failed",
                    description="Failed to link player account.",
                    color=discord.Color.red(),
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid Discord ID! Please enter a valid numeric ID.", ephemeral=True
            )


class UnlinkPlayerView(View):
    """View for unlinking a player's account."""

    def __init__(self, guild_id: int, user: discord.User, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.guild = guild

        select = discord.ui.UserSelect(
            placeholder="Select a user to unlink...", custom_id="unlink_user_select"
        )
        select.callback = self.user_selected
        self.add_item(select)

    async def user_selected(self, interaction: discord.Interaction):
        """Handle user selection for unlinking."""
        user_id = int(interaction.data["values"][0])

        # Check if user is linked
        player_link = await players_db.get_player_by_discord_id(interaction.guild_id, user_id)

        if player_link:
            confirm_view = ConfirmUnlinkView(interaction.guild_id, user_id, player_link["eos_id"])
            embed = discord.Embed(
                title="⚠️ Confirm Unlink",
                description=f"Are you sure you want to unlink <@{user_id}>?",
                color=discord.Color.orange(),
            )
            embed.add_field(name="Current EOS ID", value=f"`{player_link['eos_id']}`", inline=False)
            embed.add_field(
                name="⚠️ Warning",
                value="This will prevent them from receiving in-game deliveries until re-linked!",
                inline=False,
            )
            await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
        else:
            await interaction.response.send_message(
                "❌ This user is not linked to any ARK account.", ephemeral=True
            )

    def create_embed(self) -> discord.Embed:
        """Create unlink selection embed."""
        embed = discord.Embed(
            title="🔓 Unlink Player Account",
            description="Select a user to unlink their Discord from their ARK EOS ID.",
            color=discord.Color.orange(),
        )
        return embed


class ConfirmUnlinkView(View):
    """Confirmation view for unlinking."""

    def __init__(self, guild_id: int, discord_id: int, eos_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.discord_id = discord_id
        self.eos_id = eos_id

    @discord.ui.button(label="Yes, Unlink", style=discord.ButtonStyle.danger, emoji="🔓")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        # Unlink the player
        success = await players_db.unlink_player_by_discord_id(self.guild_id, self.discord_id)

        if success:
            embed = discord.Embed(
                title="✅ Player Unlinked",
                description=f"<@{self.discord_id}> has been unlinked from their ARK account.",
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title="❌ Error", description="Failed to unlink player.", color=discord.Color.red()
            )

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            content="❌ Unlink cancelled.", embed=None, view=None
        )


class SearchPlayerModal(Modal):
    """Modal for searching players."""

    def __init__(self, guild: discord.Guild):
        super().__init__(title="🔍 Search Player")
        self.guild = guild

        self.query = TextInput(
            label="Search Query",
            placeholder="Enter Discord ID, username, or EOS ID",
            required=True,
            max_length=50,
        )
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        query = self.query.value.strip()
        results = []

        # Try to find by Discord ID
        try:
            discord_id = int(query)
            player = await players_db.get_player_by_discord_id(discord_id)
            if player:
                results.append(("Discord ID Match", discord_id, player))
        except ValueError:
            pass

        # Try to find by EOS ID
        player = await players_db.get_player_by_eos_id(query)
        if player:
            results.append(("EOS ID Match", player["discord_user_id"], player))

        # Try to find by username in guild
        for member in self.guild.members:
            if query.lower() in member.name.lower() or query.lower() in member.display_name.lower():
                player = await players_db.get_player_by_discord_id(member.id)
                results.append(("Username Match", member.id, player))
                if len(results) >= 5:
                    break

        if results:
            embed = discord.Embed(
                title="🔍 Search Results",
                description=f"Found {len(results)} result(s) for '{query}'",
                color=discord.Color.blue(),
            )

            for match_type, discord_id, player in results[:5]:
                linked = f"✅ Linked: `{player['eos_id'][:20]}...`" if player else "❌ Not linked"
                embed.add_field(name=f"{match_type}: <@{discord_id}>", value=linked, inline=False)
        else:
            embed = discord.Embed(
                title="🔍 No Results",
                description=f"No players found matching '{query}'",
                color=discord.Color.orange(),
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class PlayerGUI(commands.Cog):
    """Interactive player and economy management GUI."""

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

    @app_commands.command(
        name="playermgmt", description="👥 Interactive player & economy management (admin only)"
    )
    async def player_mgmt(self, interaction: discord.Interaction):
        """Open the interactive player management GUI."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        view = PlayerMainView(interaction.guild_id, interaction.user, interaction.guild, self.bot)
        embed = view.create_main_embed()

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class GiveItemView(View):
    """Interactive view for giving items to players with auto-server detection."""

    def __init__(self, guild_id: int, user: discord.User, guild: discord.Guild, timeout: int = 180):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.guild = guild
        self.selected_player = None
        self.selected_item = None

        # Add player selector (will be loaded async)
        self.player_select = ItemPlayerSelectDropdown()
        self.add_item(self.player_select)

        # Add item search button
        self.add_item(ItemSearchButton())

        # Add quantity/quality button
        self.add_item(ConfirmItemButton())

    async def load_players(self):
        """Load players into dropdown before showing view."""
        await self.player_select._load_players()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ This panel is not for you!", ephemeral=True)
            return False
        return True


class ItemPlayerSelectDropdown(Select):
    """Dropdown to select a player from Discord members."""

    def __init__(self):
        # Initialize with a loading placeholder
        options = [
            discord.SelectOption(
                label="Loading players...", description="Please wait", value="loading", emoji="⏳"
            )
        ]
        super().__init__(
            placeholder="Select a player...",
            custom_id="item_player_select",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.loaded = False

    async def _load_players(self):
        """Load linked players into the dropdown with a robust fallback."""
        try:
            # Prefer only Discord-linked players from DB
            cached_players = await players_db.get_linked_players()

            # Fallback: if empty, scan guild members and include those linked in DB
            if not cached_players:
                try:
                    guild = getattr(self.view, "guild", None)
                    if guild and guild.members:
                        linked = []
                        for member in guild.members:
                            rec = await players_db.get_player_by_discord_id(member.id)
                            if rec and rec.get("eos_id"):
                                rec["discord_display_name"] = member.display_name
                                rec["discord_username"] = str(member)
                                linked.append(rec)
                        cached_players = linked
                except Exception as e2:
                    logger.debug(f"Fallback guild member scan failed: {e2}")

            options = []
            for player in cached_players[:24]:  # Leave room for manual option
                eos_id = player.get("eos_id", "Unknown")
                display_name = player.get("discord_display_name") or player.get("discord_username")
                last_server = player.get("last_seen_server") or "Unknown"
                discord_id = player.get("discord_user_id")

                # Build display label
                label = display_name or f"User {str(discord_id)[:8]}"

                # Build description with server and EOS
                description_parts = []
                if last_server and last_server != "Unknown":
                    description_parts.append(f"Server: {last_server[:20]}")
                if eos_id and eos_id != "Unknown":
                    description_parts.append(f"EOS: {eos_id[:20]}")

                description = (
                    " | ".join(description_parts) if description_parts else "Linked Discord user"
                )

                # Value is EOS ID (primary key)
                value = eos_id

                options.append(
                    discord.SelectOption(
                        label=str(label)[:100],
                        description=str(description)[:100],
                        value=value,
                        emoji="👤",
                    )
                )

            # Add option for manual entry
            options.append(
                discord.SelectOption(
                    label="Manual Entry (Steam ID/Name)",
                    description="For players not in cache",
                    value="manual",
                    emoji="✏️",
                )
            )

            # If no cached players, show message
            if len(options) == 1:  # Only manual entry
                options.insert(
                    0,
                    discord.SelectOption(
                        label="No linked players found",
                        description="Use manual entry or link EOS in Discord",
                        value="none",
                        emoji="ℹ️",
                    ),
                )

            self.options = options[:25]  # Discord limit
            self.loaded = True
        except Exception as e:
            logger.error(f"Error loading players: {e}")
            self.options = [
                discord.SelectOption(
                    label="Error loading players", description=str(e)[:100], value="error"
                )
            ]
            self.loaded = True

    async def callback(self, interaction: discord.Interaction):
        view: GiveItemView = self.view

        # Load players if not already loaded
        if not self.loaded:
            await interaction.response.defer(ephemeral=True)
            await self._load_players()

            # Edit the message to refresh the view with updated dropdown
            try:
                await interaction.edit_original_response(view=view)
                await interaction.followup.send(
                    "✅ Players loaded! Please select a player from the dropdown.", ephemeral=True
                )
            except Exception as e:
                logger.error(f"Error refreshing dropdown: {e}")
                await interaction.followup.send(
                    "✅ Players loaded! Please click the button again to see the updated list.",
                    ephemeral=True,
                )
            return

        if self.values[0] == "manual":
            # Show manual entry modal
            await interaction.response.send_modal(ManualItemPlayerEntryModal(view))
        elif self.values[0] == "none":
            await interaction.response.send_message(
                "ℹ️ No cached players found. Please use manual entry or wait for the player cache to populate.",
                ephemeral=True,
            )
        elif self.values[0] == "error":
            await interaction.response.send_message(
                "❌ Error loading players. Please try again.", ephemeral=True
            )
        else:
            # Value is EOS ID - lookup player by EOS ID
            eos_id = self.values[0]
            player_data = await players_db.get_player_by_eos_id(eos_id)
            view.selected_player = player_data

            # Build confirmation message
            char_name = player_data.get("character_name") or player_data.get(
                "player_name", "Unknown"
            )
            level = player_data.get("level", 0)
            discord_id = player_data.get("discord_user_id")

            msg = f"✅ Selected player: **{char_name}**"
            if level > 0:
                msg += f" (Lvl {level})"
            if discord_id:
                msg += f" - <@{discord_id}>"
            msg += f"\nEOS: `{eos_id}`"

            await interaction.response.send_message(msg, ephemeral=True)


class ManualItemPlayerEntryModal(Modal, title="Manual Player Entry"):
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
            custom_id="item_search_btn",
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
        super().__init__(timeout=None)
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

        super().__init__(
            placeholder="Select an item...", options=options, custom_id="item_results_dropdown"
        )
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
            custom_id="confirm_item_btn",
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
            servers = await server_config_db.get_ark_servers(guild_id)
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
    """Interactive view for giving creatures to players with auto-server detection."""

    def __init__(self, guild_id: int, user: discord.User, guild: discord.Guild, timeout: int = 180):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.guild = guild
        self.selected_player = None
        self.selected_creature = None

        # Add player selector (will be loaded async)
        self.player_select = CreaturePlayerSelectDropdown()
        self.add_item(self.player_select)

        # Add creature search button
        self.add_item(CreatureSearchButton())

        # Add confirm button
        self.add_item(ConfirmCreatureButton())

    async def load_players(self):
        """Load players into dropdown before showing view."""
        await self.player_select._load_players()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ This panel is not for you!", ephemeral=True)
            return False
        return True


class CreaturePlayerSelectDropdown(Select):
    """Dropdown to select a player for creature spawning."""

    def __init__(self):
        # Initialize with a loading placeholder
        options = [
            discord.SelectOption(
                label="Loading players...", description="Please wait", value="loading", emoji="⏳"
            )
        ]
        super().__init__(
            placeholder="Select a player...",
            custom_id="creature_player_select",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.loaded = False

    async def _load_players(self):
        """Load cached players (active within 90 days)."""
        try:
            from datetime import datetime, timedelta

            # Get all cached players from last 90 days
            cached_players = await players_db.get_cached_players(days_since_seen=90)

            options = []
            for player in cached_players[:24]:  # Leave room for manual option
                eos_id = player.get("eos_id", "Unknown")
                character_name = player.get("character_name") or player.get("player_name")
                level = player.get("level", 0)
                last_server = player.get("last_server", "Unknown")
                discord_id = player.get("discord_user_id")

                # Build display label
                if character_name:
                    label = f"{character_name}"
                    if level > 0:
                        label += f" (Lvl {level})"
                else:
                    label = f"Player {eos_id[:8]}"

                # Build description with server and link status
                description_parts = []
                if last_server and last_server != "Unknown":
                    description_parts.append(f"Server: {last_server[:20]}")
                if discord_id:
                    description_parts.append("🔗 Linked")
                else:
                    description_parts.append(f"EOS: {eos_id[:20]}")

                description = " | ".join(description_parts)

                # Value is EOS ID (primary key)
                value = eos_id

                options.append(
                    discord.SelectOption(
                        label=label[:100],
                        description=description[:100],
                        value=value,
                        emoji="🦖" if level >= 100 else "👤",
                    )
                )

            options.append(
                discord.SelectOption(
                    label="Manual Entry (Steam ID/Name)",
                    description="For players not in cache",
                    value="manual",
                    emoji="✏️",
                )
            )

            # If no cached players, show message
            if len(options) == 1:  # Only manual entry
                options.insert(
                    0,
                    discord.SelectOption(
                        label="No players in cache",
                        description="Use manual entry or wait for cache to populate",
                        value="none",
                        emoji="ℹ️",
                    ),
                )

            self.options = options[:25]
            self.loaded = True
        except Exception as e:
            logger.error(f"Error loading players: {e}")
            self.options = [
                discord.SelectOption(
                    label="Error loading players", description=str(e)[:100], value="error"
                )
            ]
            self.loaded = True

    async def callback(self, interaction: discord.Interaction):
        view: GiveCreatureView = self.view

        # Load players if not already loaded
        if not self.loaded:
            await interaction.response.defer(ephemeral=True)
            await self._load_players()

            # Edit the message to refresh the view with updated dropdown
            try:
                await interaction.edit_original_response(view=view)
                await interaction.followup.send(
                    "✅ Players loaded! Please select a player from the dropdown.", ephemeral=True
                )
            except Exception as e:
                logger.error(f"Error refreshing dropdown: {e}")
                await interaction.followup.send(
                    "✅ Players loaded! Please click the button again to see the updated list.",
                    ephemeral=True,
                )
            return

        if self.values[0] == "manual":
            await interaction.response.send_modal(ManualCreaturePlayerEntryModal(view))
        elif self.values[0] == "none":
            await interaction.response.send_message(
                "ℹ️ No cached players found. Please use manual entry or wait for the player cache to populate.",
                ephemeral=True,
            )
        elif self.values[0] == "error":
            await interaction.response.send_message(
                "❌ Error loading players. Please try again.", ephemeral=True
            )
        else:
            # Value is EOS ID - lookup player by EOS ID
            eos_id = self.values[0]
            player_data = await players_db.get_player_by_eos_id(eos_id)
            view.selected_player = player_data

            # Build confirmation message
            char_name = player_data.get("character_name") or player_data.get(
                "player_name", "Unknown"
            )
            level = player_data.get("level", 0)
            discord_id = player_data.get("discord_user_id")

            msg = f"✅ Selected player: **{char_name}**"
            if level > 0:
                msg += f" (Lvl {level})"
            if discord_id:
                msg += f" - <@{discord_id}>"
            msg += f"\nEOS: `{eos_id}`"

            await interaction.response.send_message(msg, ephemeral=True)


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
            custom_id="creature_search_btn",
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
        super().__init__(timeout=None)
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
            placeholder="Select a creature...",
            options=options,
            custom_id="creature_results_dropdown",
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
            custom_id="confirm_creature_btn",
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
            servers = await server_config_db.get_ark_servers(guild_id)
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


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(PlayerGUI(bot))
