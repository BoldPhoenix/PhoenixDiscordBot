"""
Player Management GUI - Add to existing player_management.py
"""

# Add this to the end of player_management.py

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from bot.utils.subscription_checker import check_feature
from bot.utils.validation import validate_rcon_input


# ==================== PLAYER MANAGEMENT GUI ====================

class PlayerMgmtView(discord.ui.View):
    """Main player management view with buttons."""

    def __init__(self, bot, guild_id: int, user: discord.User):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.user = user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

    @discord.ui.button(label="Link/Edit Player", style=discord.ButtonStyle.success, emoji="🔗")
    async def link_edit_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AdminLinkEditPlayerModal(self.guild_id, self.bot)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Unlink Player", style=discord.ButtonStyle.danger, emoji="🔓")
    async def unlink_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = AdminUnlinkPlayerModal(self.guild_id)
        await interaction.response.send_modal(modal)

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

    @discord.ui.button(label="Send Item", style=discord.ButtonStyle.primary, emoji="📦")
    async def send_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SendItemModal(self.guild_id)
        await interaction.response.send_modal(modal)

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


class AdminLinkEditPlayerModal(discord.ui.Modal):
    """Modal for admin to link/edit player."""

    def __init__(self, guild_id: int, bot):
        super().__init__(title="🔗 Link/Edit Player Account")
        self.guild_id = guild_id
        self.bot = bot
        self.discord_user = discord.ui.TextInput(label="Discord User", placeholder="@mention, username, or user ID", required=True, max_length=50)
        self.add_item(self.discord_user)
        self.eos_id = discord.ui.TextInput(label="EOS ID", placeholder="32-char hex", required=True, max_length=32)
        self.add_item(self.eos_id)
        self.specimen_id = discord.ui.TextInput(label="Specimen ID", placeholder="Character specimen ID", required=True, max_length=50)
        self.add_item(self.specimen_id)
        self.character_name = discord.ui.TextInput(label="Character Name", placeholder="Optional", required=False, max_length=64)
        self.add_item(self.character_name)

    async def on_submit(self, interaction: discord.Interaction):
        discord_id_str = self.discord_user.value.strip()
        discord_id = None
        if discord_id_str.startswith("<@") and discord_id_str.endswith(">"):
            discord_id = int(discord_id_str.strip("<@!>"))
        elif discord_id_str.isdigit():
            discord_id = int(discord_id_str)
        if not discord_id:
            await interaction.response.send_message("Invalid Discord user.", ephemeral=True)
            return
        from bot.database import players_db
        success = await players_db.link_player(self.guild_id, discord_id, self.eos_id.value.strip(), str(interaction.user), interaction.user.display_name, self.specimen_id.value.strip() or None)
        if success:
            embed = discord.Embed(title="Player Linked", description=f"Linked {self.character_name.value.strip() or 'Unknown'}", color=discord.Color.green())
        else:
            embed = discord.Embed(title="Link Failed", description="Failed to link.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AdminUnlinkPlayerModal(discord.ui.Modal):
    """Modal for admin to unlink a player."""

    def __init__(self, guild_id: int):
        super().__init__(title="🔓 Unlink Player Account")
        self.guild_id = guild_id
        self.discord_user = discord.ui.TextInput(label="Discord User", placeholder="@mention, username, or user ID", required=True, max_length=50)
        self.add_item(self.discord_user)

    async def on_submit(self, interaction: discord.Interaction):
        discord_id_str = self.discord_user.value.strip()
        discord_id = None
        if discord_id_str.startswith("<@") and discord_id_str.endswith(">"):
            discord_id = int(discord_id_str.strip("<@!>"))
        elif discord_id_str.isdigit():
            discord_id = int(discord_id_str)
        if not discord_id:
            await interaction.response.send_message("Invalid Discord user.", ephemeral=True)
            return
        from bot.database import players_db, server_config_db
        success = await players_db.unlink_player_by_discord_id(self.guild_id, discord_id)
        if success:
            embed = discord.Embed(title="Player Unlinked", description=f"Unlinked <@{discord_id}> successfully.", color=discord.Color.green())
            embed.set_footer(text=f"By {interaction.user.display_name}")
        else:
            embed = discord.Embed(title="Unlink Failed", description="Could not find player.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        if success:
            config = await server_config_db.get_server_config(interaction.guild_id)
            if config and config.get("admin_log_channel_id"):
                log_channel = interaction.client.get_channel(config["admin_log_channel_id"])
                if log_channel:
                    await log_channel.send(embed=embed)


# ==================== ADD COINS ====================

class AddCoinsUserSelectView(discord.ui.View):
    """User select for adding coins."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select a user...")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if not select.values:
            await interaction.response.send_message("Please select a user.", ephemeral=True)
            return
        user = select.values[0]
        modal = AddCoinsModal(self.guild_id, user.id, user.display_name)
        await interaction.response.send_modal(modal)
        self.stop()


class AddCoinsModal(discord.ui.Modal):
    """Modal for amount and reason after user selection."""

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
        from bot.database import players_db, server_config_db
        reason = self.reason.value.strip() or "Admin grant"
        player = await players_db.get_player_by_discord_id(self.guild_id, self.discord_id)
        if not player:
            await interaction.response.send_message("Player not found. They must be linked to an ARK account.", ephemeral=True)
            return
        new_balance = await players_db.add_coins(
            self.guild_id, player["eos_id"], amount,
            reason=reason, admin_id=interaction.user.id, discord_id=self.discord_id,
        )
        embed = discord.Embed(title="✅ Coins Added", description=f"Added **{amount}** coins to **{self.discord_username}**", color=discord.Color.green())
        embed.add_field(name="New Balance", value=f"**{new_balance}** coins")
        embed.set_footer(text=f"By {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_log_channel_id"):
            log_channel = interaction.client.get_channel(config["admin_log_channel_id"])
            if log_channel:
                await log_channel.send(embed=embed)


# ==================== REMOVE COINS ====================

class RemoveCoinsUserSelectView(discord.ui.View):
    """User select for removing coins."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select a user...")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if not select.values:
            await interaction.response.send_message("Please select a user.", ephemeral=True)
            return
        user = select.values[0]
        modal = RemoveCoinsModal(self.guild_id, user.id, user.display_name)
        await interaction.response.send_modal(modal)
        self.stop()


class RemoveCoinsModal(discord.ui.Modal):
    """Modal for amount and reason after user selection."""

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
        from bot.database import players_db, server_config_db
        reason = self.reason.value.strip() or "Admin deduction"
        player = await players_db.get_player_by_discord_id(self.guild_id, self.discord_id)
        if not player:
            await interaction.response.send_message("Player not found. They must be linked to an ARK account.", ephemeral=True)
            return
        success = await players_db.deduct_coins(
            self.guild_id, player["eos_id"], amount,
            reason=reason, admin_id=interaction.user.id, discord_id=self.discord_id,
        )
        if success:
            new_balance = await players_db.get_balance(self.guild_id, player["eos_id"])
            embed = discord.Embed(title="✅ Coins Removed", description=f"Removed **{amount}** coins from **{self.discord_username}**", color=discord.Color.green())
            embed.add_field(name="New Balance", value=f"**{new_balance}** coins")
            embed.set_footer(text=f"By {interaction.user.display_name}")
        else:
            embed = discord.Embed(title="❌ Failed", description="Could not remove coins. Insufficient balance?", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        if success:
            config = await server_config_db.get_server_config(interaction.guild_id)
            if config and config.get("admin_log_channel_id"):
                log_channel = interaction.client.get_channel(config["admin_log_channel_id"])
                if log_channel:
                    await log_channel.send(embed=embed)


# ==================== SEND ITEM ====================

class SendItemModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="📦 Send Item")
        self.guild_id = guild_id
        self.player = discord.ui.TextInput(label="Player ID", placeholder="EOS ID or Specimen ID", required=True, max_length=50)
        self.add_item(self.player)
        self.item = discord.ui.TextInput(label="Item ID", placeholder="e.g., PrimalItem...", required=True, max_length=100)
        self.add_item(self.item)
        self.amount = discord.ui.TextInput(label="Amount", placeholder="1", required=False, max_length=5, default="1")
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        player_id = self.player.value.strip()
        if not validate_rcon_input(player_id):
            await interaction.response.send_message(
                "❌ Invalid player ID. Only alphanumeric characters, underscores, hyphens, and dots are allowed.",
                ephemeral=True,
            )
            return
        from bot.database import server_config_db
        servers = await server_config_db.get_ark_servers(self.guild_id)
        if not servers:
            await interaction.response.send_message("No servers configured.", ephemeral=True)
            return
        from bot.rcon.client import RCONManager
        rcon_manager = RCONManager(servers)
        command = f"giveitem {player_id} {self.item.value.strip()} {self.amount.value.strip() or '1'}"
        response = await rcon_manager.execute_command(servers[0].get('name'), command)
        if response and 'error' not in response.lower():
            embed = discord.Embed(title="Item Sent", description=f"Sent {self.item.value.strip()}", color=discord.Color.green())
        else:
            embed = discord.Embed(title="Failed", description=str(response), color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ==================== KICK/BAN/KILL ====================

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
            await interaction.response.send_message(
                "❌ Invalid player ID. Only alphanumeric characters, underscores, hyphens, and dots are allowed.",
                ephemeral=True,
            )
            return
        from bot.database import server_config_db
        servers = await server_config_db.get_ark_servers(self.guild_id)
        if not servers:
            await interaction.response.send_message("No servers configured.", ephemeral=True)
            return
        from bot.rcon.client import RCONManager
        rcon_manager = RCONManager(servers)
        command = f'kickplayer {player_id} {self.reason.value.strip() or "No reason"}'
        await rcon_manager.execute_command(servers[0].get('name'), command)
        embed = discord.Embed(title="Player Kicked", description=f"**Player:** {self.player.value.strip()}\n**Reason:** {self.reason.value.strip() or 'No reason'}", color=discord.Color.green())
        embed.set_footer(text=f"By {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_log_channel_id"):
            log_channel = interaction.client.get_channel(config["admin_log_channel_id"])
            if log_channel:
                await log_channel.send(embed=embed)


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
            await interaction.response.send_message(
                "❌ Invalid player ID. Only alphanumeric characters, underscores, hyphens, and dots are allowed.",
                ephemeral=True,
            )
            return
        from bot.database import server_config_db
        servers = await server_config_db.get_ark_servers(self.guild_id)
        if not servers:
            await interaction.response.send_message("No servers configured.", ephemeral=True)
            return
        from bot.rcon.client import RCONManager
        rcon_manager = RCONManager(servers)
        command = f'banplayer {player_id} {self.reason.value.strip()}'
        await rcon_manager.execute_command(servers[0].get('name'), command)
        embed = discord.Embed(title="Player Banned", description=f"**Player:** {self.player.value.strip()}\n**Reason:** {self.reason.value.strip()}", color=discord.Color.dark_red())
        embed.set_footer(text=f"By {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_log_channel_id"):
            log_channel = interaction.client.get_channel(config["admin_log_channel_id"])
            if log_channel:
                await log_channel.send(embed=embed)


class UnbanPlayerModal(discord.ui.Modal):
    def __init__(self, guild_id: int):
        super().__init__(title="✅ Unban Player")
        self.guild_id = guild_id
        self.player = discord.ui.TextInput(label="Player ID", placeholder="EOS ID or Player Name", required=True, max_length=50)
        self.add_item(self.player)

    async def on_submit(self, interaction: discord.Interaction):
        player_id = self.player.value.strip()
        if not validate_rcon_input(player_id):
            await interaction.response.send_message(
                "❌ Invalid player ID. Only alphanumeric characters, underscores, hyphens, and dots are allowed.",
                ephemeral=True,
            )
            return
        from bot.database import server_config_db
        servers = await server_config_db.get_ark_servers(self.guild_id)
        if not servers:
            await interaction.response.send_message("No servers configured.", ephemeral=True)
            return
        from bot.rcon.client import RCONManager
        rcon_manager = RCONManager(servers)
        command = f'unbanplayer {player_id}'
        await rcon_manager.execute_command(servers[0].get('name'), command)
        embed = discord.Embed(title="Player Unbanned", description=f"Unbanned: {self.player.value.strip()}", color=discord.Color.green())
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
            await interaction.response.send_message(
                "❌ Invalid player ID. Only alphanumeric characters, underscores, hyphens, and dots are allowed.",
                ephemeral=True,
            )
            return
        from bot.database import server_config_db
        servers = await server_config_db.get_ark_servers(self.guild_id)
        if not servers:
            await interaction.response.send_message("No servers configured.", ephemeral=True)
            return
        from bot.rcon.client import RCONManager
        rcon_manager = RCONManager(servers)
        command = f'killplayer {player_id}'
        await rcon_manager.execute_command(servers[0].get('name'), command)
        embed = discord.Embed(title="Player Killed", description=f"**Player:** {self.player.value.strip()}", color=discord.Color.orange())
        embed.set_footer(text=f"By {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_log_channel_id"):
            log_channel = interaction.client.get_channel(config["admin_log_channel_id"])
            if log_channel:
                await log_channel.send(embed=embed)


# ==================== MAIN COG ====================

class PlayerManagementGUI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="playergui", description="[ADMIN] Open player management GUI panel")
    async def playergui(self, interaction: discord.Interaction):
        if not await check_feature(interaction, "player_management"):
            return
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="Player Management", description="Select an action below:", color=discord.Color.blue())
        view = PlayerMgmtView(self.bot, interaction.guild_id, interaction.user)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(PlayerManagementGUI(bot))
