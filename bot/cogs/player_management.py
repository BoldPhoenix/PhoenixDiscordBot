"""
Player Management Commands - Phase 3 Implementation

Commands:
- /player - User self-service panel (link/unlink/view info)
- /broadcast - Admin broadcast message to servers
- /listlinkedplayers - Admin paginated list of linked players
- /playermgmt - Admin player management panel with modals
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
import re
from typing import Optional, List
from datetime import datetime

from bot.rcon.client import RCONManager
from bot.database import server_config_db, players_db
from bot.utils.eos import InvalidEosId, normalize_eos_id
from bot.utils.subscription_checker import check_feature

logger = logging.getLogger("PlayerManagement")

from bot.utils.validation import validate_rcon_input  # noqa: F401 - re-exported for backward compat


async def setup(bot):
    """Setup function for Discord.py cog loading."""
    await bot.add_cog(PlayerManagement(bot))


class PlayerManagement(commands.Cog):
    """ARK player management commands."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        """Initialize player management when cog loads."""
        logger.info("Player Management cog loaded")

    async def get_servers_for_guild(self, guild_id: int):
        """Get ARK servers configured for a guild."""
        servers = await server_config_db.get_ark_servers(guild_id)
        return servers if servers else []

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

    # ==================== /player ====================

    @app_commands.command(name="player", description="Manage your player account and ARK linking")
    async def player_command(self, interaction: discord.Interaction):
        """User self-service panel for player linking and info."""
        if not await check_feature(interaction, "player_management"):
            return
        logger.info(f"/player called: user_id={interaction.user.id}, guild_id={interaction.guild_id}")

        # Get linked player info (balance lives on players table now)
        player_info = await players_db.get_player_by_discord_id(
            interaction.guild_id, interaction.user.id
        )
        balance = (player_info.get("balance", 0) or 0) if player_info else 0

        embed = discord.Embed(
            title="🎮 Player Panel",
            description="Manage your ARK account and view stats",
            color=discord.Color.blue(),
        )

        # Balance info
        embed.add_field(
            name="💰 Bank Balance",
            value=f"**{balance}** Phoenix Coins",
            inline=True,
        )

        # Player link status
        if player_info:
            # Same NULL-vs-missing trap as /listlinkedplayers: a player row can exist with a
            # Discord id and no eos_id at all, and `None[:16]` would break /player for them.
            eos_id = player_info.get("eos_id") or ""
            character = player_info.get("character_name") or "Unknown"
            eos_display = f"`{eos_id[:16]}...`" if eos_id else "_no EOS ID linked_"
            embed.add_field(
                name="🔗 Linked Account",
                value=f"**{character}**\n{eos_display}",
                inline=True,
            )
        else:
            embed.add_field(
                name="🔗 Linked Account",
                value="Not linked",
                inline=True,
            )

        # Create view with buttons
        view = PlayerPanelView(self.bot, interaction.guild_id, interaction.user, balance, player_info)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ==================== /listlinkedplayers ====================

    @app_commands.command(name="listlinkedplayers", description="[ADMIN] List all players with linked ARK accounts")
    async def list_linked_players(self, interaction: discord.Interaction):
        """Admin command to list all linked players with pagination."""
        if not await check_feature(interaction, "player_management"):
            return
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need admin permissions to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        players = await players_db.get_linked_players_for_guild(interaction.guild_id)

        if not players:
            await interaction.followup.send(
                "No linked players found.",
                ephemeral=True
            )
            return

        # Pagination: 10 players per page
        items_per_page = 10
        total_pages = (len(players) + items_per_page - 1) // items_per_page
        page = 1

        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_players = players[start_idx:end_idx]

        embed = discord.Embed(
            title="🔗 Linked Players",
            description=f"Total: {len(players)} linked players",
            color=discord.Color.blue(),
        )

        for player in page_players:
            # `.get(key, default)` only falls back when the KEY IS MISSING. Every one of these keys
            # is in the SELECT, so a SQL NULL comes back as None and the default never fires —
            # `None[:20]` then raises TypeError.
            #
            # In the command that raised AFTER interaction.response.defer(), so the interaction sat
            # on "thinking…" forever with no error shown to anyone, and it took /listlinkedplayers
            # down for every admin. Same slice, same failure, in the pagination callback.
            #
            # It is not a rare row: get_linked_players_for_guild filters on
            # `discord_user_id IS NOT NULL` and says nothing about eos_id, and this guild has dozens
            # of members who joined Discord and never linked an ARK account.
            discord_user = player.get("discord_username") or "Unknown"
            eos_id = (player.get("eos_id") or "Not linked")[:20]
            specimen_id = player.get("specimen_id") or "N/A"
            character = player.get("character_name") or "Unknown"

            embed.add_field(
                name=f"🎮 {character}",
                value=f"Discord: {discord_user}\nEOS: `{eos_id}`\nSpecimen: `{specimen_id}`",
                inline=False,
            )

        embed.set_footer(text=f"Page {page}/{total_pages}")

        # Add pagination buttons if needed
        if total_pages > 1:
            view = LinkedPlayersPaginationView(
                self.bot,
                interaction.guild_id,
                interaction.user,
                players,
                page,
                total_pages,
            )
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

    # ==================== /playermgmt ====================

    @app_commands.command(name="playermgmt", description="[ADMIN] Open player management interface")
    async def player_mgmt(self, interaction: discord.Interaction):
        """Admin player management panel."""
        if not await check_feature(interaction, "player_management"):
            return
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need admin permissions to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Get stats
        linked_players = await players_db.get_linked_players_for_guild(interaction.guild_id)
        servers = await self.get_servers_for_guild(interaction.guild_id)

        embed = discord.Embed(
            title="👥 Player Management",
            description="Manage linked players and view statistics",
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="📊 Statistics",
            value=f"**Linked Players:** {len(linked_players)}\n**Servers:** {len(servers)}",
            inline=True,
        )

        embed.add_field(
            name="⚡ Quick Actions",
            value="Use the buttons below to manage players",
            inline=True,
        )

        view = PlayerMgmtView(self.bot, interaction.guild_id, interaction.user)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


# ==================== Views ====================

class PlayerPanelView(discord.ui.View):
    """View for /player command with buttons."""

    def __init__(self, bot, guild_id: int, user, balance: int, player_info: dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.user = user
        self.balance = balance
        self.player_info = player_info

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This panel is not for you!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Bank Balance", style=discord.ButtonStyle.primary, emoji="💰")
    async def view_balance(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show bank balance."""
        # Re-fetch balance from players table
        balance, eos_id = await players_db.get_balance_by_discord_id(self.guild_id, self.user.id)

        if eos_id is None:
            embed = discord.Embed(
                title="Bank Balance",
                description="You don't have a linked ARK account.\nUse **Link/Edit Player** to link your account.",
                color=discord.Color.orange(),
            )
        else:
            embed = discord.Embed(
                title="Bank Balance",
                description=f"Your current balance: **{balance}** Phoenix Coins",
                color=discord.Color.green(),
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="View My Info", style=discord.ButtonStyle.secondary, emoji="👤")
    async def view_my_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View linked player info."""
        # Re-fetch player info from database (in case it was just linked)
        player_info = await players_db.get_player_by_discord_id(
            self.guild_id, self.user.id
        )

        if not player_info:
            embed = discord.Embed(
                title="👤 Your Info",
                description="❌ You don't have a linked ARK account.\n\nUse **Link/Edit Player** to link your account.",
                color=discord.Color.orange(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        eos_id = player_info.get("eos_id", "Not set")
        specimen_id = player_info.get("specimen_id", "Not captured")
        character_name = player_info.get("character_name", "Unknown")
        player_name = player_info.get("player_name", "Unknown")
        last_server = player_info.get("last_server", "Unknown")
        last_seen = player_info.get("last_seen_timestamp")

        if last_seen:
            # Use Discord timestamp format for automatic timezone conversion
            last_seen_str = f"<t:{int(last_seen)}:f>"
        else:
            last_seen_str = "Never"

        embed = discord.Embed(
            title="👤 Your ARK Info",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Character", value=character_name, inline=True)
        embed.add_field(name="Player Name", value=player_name, inline=True)
        embed.add_field(name="EOS ID", value=f"`{eos_id}`", inline=False)
        embed.add_field(name="Specimen ID", value=f"`{specimen_id}`", inline=True)
        embed.add_field(name="Last Server", value=last_server, inline=True)
        embed.add_field(name="Last Seen", value=last_seen_str, inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Link/Edit Player", style=discord.ButtonStyle.success, emoji="🔗")
    async def link_edit_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to link/edit player with dropdown."""
        modal = LinkEditPlayerModal(self.guild_id, self.user.id, self.player_info)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Unlink Player", style=discord.ButtonStyle.danger, emoji="🔓")
    async def unlink_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open unlink confirmation modal."""
        if not self.player_info:
            await interaction.response.send_message(
                "❌ You don't have a linked ARK account to unlink.",
                ephemeral=True
            )
            return
        modal = UnlinkConfirmModal(self.guild_id, self.user.id, self.player_info)
        await interaction.response.send_modal(modal)


class LinkEditPlayerModal(discord.ui.Modal):
    """Modal for linking/editing player with dropdown."""

    def __init__(self, guild_id: int, discord_user_id: int, player_info: dict):
        super().__init__(title="🔗 Link Player Account")
        self.guild_id = guild_id
        self.discord_user_id = discord_user_id
        self.player_info = player_info

        # Current values
        current_eos = player_info.get("eos_id", "") if player_info else ""
        current_specimen = player_info.get("specimen_id", "") if player_info else ""
        current_character = player_info.get("character_name", "") if player_info else ""

        self.character_name = discord.ui.TextInput(
            label="Character Name",
            placeholder="Your in-game character name",
            required=True,
            max_length=64,
            default=current_character,
        )
        self.add_item(self.character_name)

        self.eos_id = discord.ui.TextInput(
            label="EOS ID (32-char hex)",
            placeholder="e.g., 00010203040506070809abcdef...",
            required=True,
            max_length=32,
            default=current_eos,
        )
        self.add_item(self.eos_id)

        self.specimen_id = discord.ui.TextInput(
            label="Specimen ID (Optional)",
            placeholder="Your character specimen implant ID",
            required=False,
            max_length=50,
            default=current_specimen,
        )
        self.add_item(self.specimen_id)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        # Validate BEFORE writing. max_length=32 on the TextInput stops 33 characters and waves 31
        # straight through, which is the wrong half of the problem: Deez_Knutz721 linked a 31-char
        # ID (one `6` dropped mid-string), every EOS-keyed lookup missed, and five store purchases
        # queued and never delivered. See bot/utils/eos.py.
        try:
            eos_id = normalize_eos_id(self.eos_id.value)
        except InvalidEosId as e:
            await interaction.response.send_message(
                f"❌ {e}\n\nNothing was saved — your existing link is untouched.", ephemeral=True
            )
            return
        specimen_id = self.specimen_id.value.strip() if self.specimen_id.value.strip() else None
        character_name = self.character_name.value.strip()

        success = await players_db.link_player(
            self.guild_id,
            self.discord_user_id,
            eos_id,
            str(interaction.user),
            interaction.user.display_name,
            specimen_id,
        )

        # Update character name separately since link_player doesn't support it
        if success:
            from bot.utils.config import Config
            import aiosqlite
            db_path = Config.DATABASE_PATH
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "UPDATE players SET character_name = ?, player_name = ? WHERE guild_id = ? AND discord_user_id = ?",
                    (character_name, character_name, self.guild_id, self.discord_user_id)
                )
                await db.commit()

        if success:
            embed = discord.Embed(
                title="✅ Account Linked",
                description=f"Your Discord has been linked to ARK player **{character_name}**",
                color=discord.Color.green(),
            )
            embed.add_field(name="EOS ID", value=f"`{eos_id}`", inline=True)
            if specimen_id:
                embed.add_field(name="Specimen ID", value=f"`{specimen_id}`", inline=True)
        else:
            embed = discord.Embed(
                title="❌ Link Failed",
                description="Failed to link account. The EOS ID may already be linked to another user.",
                color=discord.Color.red(),
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class UnlinkConfirmModal(discord.ui.Modal):
    """Modal for unlinking player with confirmation."""

    def __init__(self, guild_id: int, discord_user_id: int, player_info: dict):
        super().__init__(title="🔓 Unlink Player Account")
        self.guild_id = guild_id
        self.discord_user_id = discord_user_id
        self.player_info = player_info

        eos_id = player_info.get("eos_id", "N/A") if player_info else "N/A"
        character = player_info.get("character_name", "Unknown") if player_info else "Unknown"

        self.confirm = discord.ui.TextInput(
            label=f'Type "{character}" to confirm',
            placeholder=f"Type the character name exactly",
            required=True,
            max_length=64,
        )
        self.add_item(self.confirm)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle unlink confirmation."""
        expected = self.player_info.get("character_name", "") if self.player_info else ""
        typed = self.confirm.value.strip()

        if typed != expected:
            await interaction.response.send_message(
                "❌ Character name doesn't match. Unlink cancelled.",
                ephemeral=True
            )
            return

        success = await players_db.unlink_player_by_discord_id(
            self.guild_id, self.discord_user_id
        )

        if success:
            embed = discord.Embed(
                title="✅ Unlinked",
                description="Your ARK account has been unlinked from Discord.",
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to unlink account.",
                color=discord.Color.red(),
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class LinkedPlayersPaginationView(discord.ui.View):
    """Pagination view for listlinkedplayers."""

    def __init__(self, bot, guild_id: int, user, players: list, current_page: int, total_pages: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.user = user
        self.players = players
        self.current_page = current_page
        self.total_pages = total_pages

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This panel is not for you!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page."""
        if self.current_page > 1:
            self.current_page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page."""
        if self.current_page < self.total_pages:
            self.current_page += 1
            await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        """Update the embed with new page."""
        items_per_page = 10
        start_idx = (self.current_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_players = self.players[start_idx:end_idx]

        embed = discord.Embed(
            title="🔗 Linked Players",
            description=f"Total: {len(self.players)} linked players",
            color=discord.Color.blue(),
        )

        for player in page_players:
            # `.get(key, default)` only falls back when the KEY IS MISSING. Every one of these keys
            # is in the SELECT, so a SQL NULL comes back as None and the default never fires —
            # `None[:20]` then raises TypeError.
            #
            # In the command that raised AFTER interaction.response.defer(), so the interaction sat
            # on "thinking…" forever with no error shown to anyone, and it took /listlinkedplayers
            # down for every admin. Same slice, same failure, in the pagination callback.
            #
            # It is not a rare row: get_linked_players_for_guild filters on
            # `discord_user_id IS NOT NULL` and says nothing about eos_id, and this guild has dozens
            # of members who joined Discord and never linked an ARK account.
            discord_user = player.get("discord_username") or "Unknown"
            eos_id = (player.get("eos_id") or "Not linked")[:20]
            specimen_id = player.get("specimen_id") or "N/A"
            character = player.get("character_name") or "Unknown"

            embed.add_field(
                name=f"🎮 {character}",
                value=f"Discord: {discord_user}\nEOS: `{eos_id}`\nSpecimen: `{specimen_id}`",
                inline=False,
            )

        embed.set_footer(text=f"Page {self.current_page}/{self.total_pages}")

        await interaction.response.edit_message(embed=embed, view=self)


class PlayerMgmtView(discord.ui.View):
    """View for /playermgmt command — full admin panel."""

    def __init__(self, bot, guild_id: int, user):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.user = user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This panel is not for you!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Link/Edit Player", style=discord.ButtonStyle.success, emoji="🔗")
    async def link_edit_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🔗 Link/Edit Player", description="Select a Discord user to link or edit:", color=discord.Color.blue())
        view = AdminLinkEditUserSelectView(self.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Unlink Player", style=discord.ButtonStyle.danger, emoji="🔓")
    async def unlink_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🔓 Unlink Player", description="Select a Discord user to unlink:", color=discord.Color.orange())
        view = AdminUnlinkUserSelectView(self.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Add Coins", style=discord.ButtonStyle.success, emoji="💰")
    async def add_coins(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="💰 Add Coins", description="Select a user to add coins to:", color=discord.Color.green())
        view = AddCoinsUserSelectView(self.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Remove Coins", style=discord.ButtonStyle.danger, emoji="💸")
    async def remove_coins(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="💸 Remove Coins", description="Select a user to remove coins from:", color=discord.Color.red())
        view = RemoveCoinsUserSelectView(self.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Kick Player", style=discord.ButtonStyle.secondary, emoji="👢")
    async def kick_player_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = KickPlayerModal(self.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Ban Player", style=discord.ButtonStyle.danger, emoji="🚫")
    async def ban_player_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = BanPlayerModal(self.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Unban Player", style=discord.ButtonStyle.success, emoji="✅")
    async def unban_player_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = UnbanPlayerModal(self.guild_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Kill Player", style=discord.ButtonStyle.danger, emoji="💀")
    async def kill_player_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = KillPlayerModal(self.guild_id)
        await interaction.response.send_modal(modal)


# ==================== Admin Link/Unlink Views & Modals ====================

class AdminLinkEditUserSelectView(discord.ui.View):
    """User select dropdown for admin Link/Edit player."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select a user to link/edit...")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if not select.values:
            return
        user = select.values[0]
        # Pre-load existing player info for this user
        player_info = await players_db.get_player_by_discord_id(self.guild_id, user.id)
        modal = AdminLinkEditPlayerModal(self.guild_id, user.id, user.display_name, player_info)
        await interaction.response.send_modal(modal)
        self.stop()


class AdminLinkEditPlayerModal(discord.ui.Modal):
    """Modal for admin to link/edit player (after user select)."""

    def __init__(self, guild_id: int, discord_id: int, discord_username: str, player_info: dict):
        super().__init__(title=f"🔗 Link/Edit: {discord_username[:38]}")
        self.guild_id = guild_id
        self.discord_id = discord_id
        self.discord_username = discord_username

        current_eos = player_info.get("eos_id", "") if player_info else ""
        current_specimen = player_info.get("specimen_id", "") if player_info else ""
        current_character = player_info.get("character_name", "") if player_info else ""

        self.eos_id = discord.ui.TextInput(label="EOS ID (32-char hex)", placeholder="e.g., 00010203040506070809abcdef...", required=True, max_length=32, default=current_eos)
        self.add_item(self.eos_id)
        self.character_name = discord.ui.TextInput(label="Character Name", placeholder="In-game character name", required=False, max_length=64, default=current_character)
        self.add_item(self.character_name)
        self.specimen_id = discord.ui.TextInput(label="Specimen ID (Optional)", placeholder="Character specimen implant ID", required=False, max_length=50, default=current_specimen)
        self.add_item(self.specimen_id)

    async def on_submit(self, interaction: discord.Interaction):
        eos_id = self.eos_id.value.strip()
        specimen_id = self.specimen_id.value.strip() or None
        char_name = self.character_name.value.strip()

        success = await players_db.link_player(
            self.guild_id, self.discord_id, eos_id,
            self.discord_username, self.discord_username,
            specimen_id
        )
        if success and char_name:
            import aiosqlite
            from bot.utils.config import Config
            async with aiosqlite.connect(Config.DATABASE_PATH) as db:
                await db.execute(
                    "UPDATE players SET character_name = ?, player_name = ? WHERE guild_id = ? AND discord_user_id = ?",
                    (char_name, char_name, self.guild_id, self.discord_id)
                )
                await db.commit()

        if success:
            embed = discord.Embed(title="✅ Player Linked", description=f"Linked <@{self.discord_id}> to EOS `{eos_id}`", color=discord.Color.green())
            if char_name:
                embed.add_field(name="Character", value=char_name, inline=True)
        else:
            embed = discord.Embed(title="❌ Link Failed", description="Failed to link player.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AdminUnlinkUserSelectView(discord.ui.View):
    """Discord user select for admin Unlink - validates the user is linked."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select a user to unlink...")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if not select.values:
            return
        user = select.values[0]
        player_info = await players_db.get_player_by_discord_id(self.guild_id, user.id)
        if not player_info:
            await interaction.response.send_message(f"❌ **{user.display_name}** does not have a linked ARK account.", ephemeral=True)
            return

        character = player_info.get("character_name", "Unknown")
        eos_id = player_info.get("eos_id", "N/A")

        embed = discord.Embed(
            title="🔓 Confirm Unlink",
            description=f"Are you sure you want to unlink **{user.display_name}**?",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Character", value=character, inline=True)
        embed.add_field(name="EOS ID", value=f"`{eos_id}`", inline=True)
        view = AdminUnlinkConfirmView(self.guild_id, user.id, user.display_name)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        self.stop()


class AdminUnlinkConfirmView(discord.ui.View):
    """Confirmation buttons for admin unlink."""

    def __init__(self, guild_id: int, discord_id: int, discord_username: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.discord_id = discord_id
        self.discord_username = discord_username

    @discord.ui.button(label="Confirm Unlink", style=discord.ButtonStyle.danger, emoji="🔓")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        success = await players_db.unlink_player_by_discord_id(self.guild_id, self.discord_id)
        if success:
            embed = discord.Embed(title="✅ Player Unlinked", description=f"Unlinked **{self.discord_username}** successfully.", color=discord.Color.green())
        else:
            embed = discord.Embed(title="❌ Unlink Failed", description="Could not find that player.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Cancelled.", ephemeral=True)
        self.stop()


# ==================== Coins Modals ====================

class AddCoinsUserSelectView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select a user...")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if not select.values:
            return
        user = select.values[0]
        modal = AddCoinsModal(self.guild_id, user.id, user.display_name)
        await interaction.response.send_modal(modal)
        self.stop()


class AddCoinsModal(discord.ui.Modal):
    def __init__(self, guild_id: int, discord_id: int, discord_username: str):
        super().__init__(title="💰 Add Coins")
        self.guild_id = guild_id
        self.discord_id = discord_id
        self.discord_username = discord_username
        self.amount = discord.ui.TextInput(label="Amount", placeholder="Number of coins to add", required=True, max_length=10)
        self.add_item(self.amount)
        self.reason = discord.ui.TextInput(label="Reason", placeholder="Reason for adding coins", required=False, max_length=100)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value.strip())
        except ValueError:
            await interaction.response.send_message("Invalid amount.", ephemeral=True)
            return
        reason = self.reason.value.strip() or "Admin grant"

        try:
            player = await players_db.get_player_by_discord_id(self.guild_id, self.discord_id)
            if not player:
                await interaction.response.send_message(
                    f"**{self.discord_username}** doesn't have a linked ARK account.", ephemeral=True
                )
                return

            new_balance = await players_db.add_coins(
                self.guild_id, player["eos_id"], amount, reason, admin_id=interaction.user.id
            )
            embed = discord.Embed(title="Coins Added", description=f"Added **{amount}** coins to **{self.discord_username}**\nNew Balance: **{new_balance}**", color=discord.Color.green())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            import logging
            logger = logging.getLogger("PlayerManagement")
            logger.error(f"Error in AddCoinsModal: {e}")
            await interaction.response.send_message("Something went wrong. Try again.", ephemeral=True)


class RemoveCoinsUserSelectView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select a user...")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if not select.values:
            return
        user = select.values[0]
        modal = RemoveCoinsModal(self.guild_id, user.id, user.display_name)
        await interaction.response.send_modal(modal)
        self.stop()


class RemoveCoinsModal(discord.ui.Modal):
    def __init__(self, guild_id: int, discord_id: int, discord_username: str):
        super().__init__(title="💸 Remove Coins")
        self.guild_id = guild_id
        self.discord_id = discord_id
        self.discord_username = discord_username
        self.amount = discord.ui.TextInput(label="Amount", placeholder="Number of coins to remove", required=True, max_length=10)
        self.add_item(self.amount)
        self.reason = discord.ui.TextInput(label="Reason", placeholder="Reason for removing coins", required=False, max_length=100)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value.strip())
        except ValueError:
            await interaction.response.send_message("Invalid amount.", ephemeral=True)
            return
        reason = self.reason.value.strip() or "Admin deduction"

        try:
            player = await players_db.get_player_by_discord_id(self.guild_id, self.discord_id)
            if not player:
                await interaction.response.send_message(
                    f"**{self.discord_username}** doesn't have a linked ARK account.", ephemeral=True
                )
                return

            success = await players_db.deduct_coins(self.guild_id, player["eos_id"], amount, reason)
            if success:
                new_balance = await players_db.get_balance(self.guild_id, player["eos_id"])
                embed = discord.Embed(title="Coins Removed", description=f"Removed **{amount}** coins from **{self.discord_username}**\nNew Balance: **{new_balance}**", color=discord.Color.green())
            else:
                embed = discord.Embed(title="Failed", description="Insufficient balance or player not found.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            import logging
            logger = logging.getLogger("PlayerManagement")
            logger.error(f"Error in RemoveCoinsModal: {e}")
            await interaction.response.send_message("Something went wrong. Try again.", ephemeral=True)


# ==================== RCON Action Modals ====================

class KickPlayerModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="👢 Kick Player")
        self.guild_id = guild_id
        self.player = discord.ui.TextInput(label="Player ID", placeholder="EOS ID or Player Name", required=True, max_length=50)
        self.add_item(self.player)
        self.reason = discord.ui.TextInput(label="Reason", placeholder="Reason for kick", required=False, max_length=100)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        player_id = self.player.value.strip()
        if not validate_rcon_input(player_id):
            await interaction.response.send_message("❌ Invalid player ID. Only alphanumeric characters, underscores, hyphens, and dots are allowed.", ephemeral=True)
            return
        servers = await server_config_db.get_ark_servers(self.guild_id)
        if not servers:
            await interaction.response.send_message("❌ No servers configured.", ephemeral=True)
            return
        rcon_manager = RCONManager(servers)
        command = f'kickplayer {player_id}'
        await rcon_manager.execute_command(servers[0].get('name'), command)
        embed = discord.Embed(title="👢 Player Kicked", description=f"Kicked `{player_id}`\nReason: {self.reason.value.strip() or 'No reason'}", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=True)


class BanPlayerModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="🚫 Ban Player")
        self.guild_id = guild_id
        self.player = discord.ui.TextInput(label="Player ID", placeholder="EOS ID or Player Name", required=True, max_length=50)
        self.add_item(self.player)
        self.reason = discord.ui.TextInput(label="Reason", placeholder="Reason for ban", required=True, max_length=100)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        player_id = self.player.value.strip()
        if not validate_rcon_input(player_id):
            await interaction.response.send_message("❌ Invalid player ID. Only alphanumeric characters, underscores, hyphens, and dots are allowed.", ephemeral=True)
            return
        servers = await server_config_db.get_ark_servers(self.guild_id)
        if not servers:
            await interaction.response.send_message("❌ No servers configured.", ephemeral=True)
            return
        rcon_manager = RCONManager(servers)
        command = f'banplayer {player_id}'
        await rcon_manager.execute_command(servers[0].get('name'), command)
        embed = discord.Embed(title="🚫 Player Banned", description=f"Banned `{player_id}`\nReason: {self.reason.value.strip()}", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)


class UnbanPlayerModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="✅ Unban Player")
        self.guild_id = guild_id
        self.player = discord.ui.TextInput(label="Player ID", placeholder="EOS ID or Player Name", required=True, max_length=50)
        self.add_item(self.player)

    async def on_submit(self, interaction: discord.Interaction):
        player_id = self.player.value.strip()
        if not validate_rcon_input(player_id):
            await interaction.response.send_message("❌ Invalid player ID. Only alphanumeric characters, underscores, hyphens, and dots are allowed.", ephemeral=True)
            return
        servers = await server_config_db.get_ark_servers(self.guild_id)
        if not servers:
            await interaction.response.send_message("❌ No servers configured.", ephemeral=True)
            return
        rcon_manager = RCONManager(servers)
        command = f'unbanplayer {player_id}'
        await rcon_manager.execute_command(servers[0].get('name'), command)
        embed = discord.Embed(title="✅ Player Unbanned", description=f"Unbanned `{player_id}`", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)


class KillPlayerModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="💀 Kill Player")
        self.guild_id = guild_id
        self.player = discord.ui.TextInput(label="Player ID", placeholder="EOS ID or Player Name", required=True, max_length=50)
        self.add_item(self.player)

    async def on_submit(self, interaction: discord.Interaction):
        player_id = self.player.value.strip()
        if not validate_rcon_input(player_id):
            await interaction.response.send_message("❌ Invalid player ID. Only alphanumeric characters, underscores, hyphens, and dots are allowed.", ephemeral=True)
            return
        servers = await server_config_db.get_ark_servers(self.guild_id)
        if not servers:
            await interaction.response.send_message("❌ No servers configured.", ephemeral=True)
            return
        rcon_manager = RCONManager(servers)
        command = f'killplayer {player_id}'
        await rcon_manager.execute_command(servers[0].get('name'), command)
        embed = discord.Embed(title="💀 Player Killed", description=f"Kill command sent for `{player_id}`", color=discord.Color.dark_red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
