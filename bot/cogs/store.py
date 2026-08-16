"""
Store cog for managing the in-game item shop.
Players can browse items, purchase with Phoenix Coins, and receive items in-game.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import logging
from typing import Optional
import aiosqlite

from bot.database import user_db, store_db, players_db, server_config_db
from bot.rcon.client import RCONManager
from bot.utils.config import Config
from bot.utils.eos import InvalidEosId, normalize_eos_id
from bot.utils.subscription_checker import check_feature


logger = logging.getLogger("StoreCog")


class LinkedPlayersView(View):
    """Pagination view for linked players list."""

    def __init__(self, players: list):
        super().__init__(timeout=None)  # 5 minute timeout
        self.players = players
        self.page = 0
        self.page_size = 10
        self.total_pages = (len(players) + self.page_size - 1) // self.page_size

        # Update button states
        self.update_buttons()

    def update_buttons(self):
        """Update button enabled/disabled state based on current page."""
        # Disable previous button on first page
        self.children[0].disabled = self.page == 0
        # Disable next button on last page
        self.children[1].disabled = self.page >= self.total_pages - 1

    def create_embed(self) -> discord.Embed:
        """Create embed for current page."""
        start_idx = self.page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.players))
        page_players = self.players[start_idx:end_idx]

        embed = discord.Embed(
            title="🔗 Linked Player Accounts",
            description=f"Showing {start_idx + 1}-{end_idx} of {len(self.players)} linked players",
            color=discord.Color.blue(),
        )

        for player in page_players:
            display_name = player.get("discord_display_name") or "Unknown"
            # `or`, not `.get(key, default)`: the key is always present from the SELECT, so a SQL
            # NULL returns None and the default never fires — `len(None)` then raises TypeError
            # after this command has already deferred, which is the "stuck on thinking…" failure.
            eos_id = player.get("eos_id") or ""
            specimen_id = player.get("specimen_id")

            # Truncate EOS ID for display
            if not eos_id:
                eos_display = "_not linked_"
            else:
                eos_display = f"`{eos_id[:20]}...`" if len(eos_id) > 20 else f"`{eos_id}`"

            field_value = f"EOS: {eos_display}\n"
            if specimen_id:
                field_value += f"Specimen: `{specimen_id}` ✅\n"
            else:
                field_value += "Specimen: Not set ⚠️\n"

            if player.get("last_seen_server"):
                field_value += f"Last seen: {player['last_seen_server']}"

            embed.add_field(
                name=f"{display_name} (<@{player['discord_user_id']}>)",
                value=field_value,
                inline=False,
            )

        if self.total_pages > 1:
            embed.set_footer(
                text=f"Page {self.page + 1} of {self.total_pages} | Use /viewplayerinfo @user for full details"
            )
        else:
            embed.set_footer(text="Use /viewplayerinfo @user for full details")

        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: Button):
        """Go to previous page."""
        self.page -= 1
        self.update_buttons()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        """Go to next page."""
        self.page += 1
        self.update_buttons()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class Store(commands.Cog):
    """Store commands for purchasing in-game items with Phoenix Coins."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rcon_manager = RCONManager(Config.ARK_SERVERS)

    async def is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions."""
        if interaction.user.guild_permissions.administrator:
            return True
        guild_id = interaction.guild_id
        if guild_id:
            config = await server_config_db.get_server_config(guild_id)
            if config and config.get("admin_role_id"):
                return any(role.id == config["admin_role_id"] for role in interaction.user.roles)
        return False

    @app_commands.command(name="store", description="Browse the Phoenix Store")
    @app_commands.describe(category="Filter by category")
    async def store_list(self, interaction: discord.Interaction, category: Optional[str] = None):
        """Display available items in the store."""
        if not await check_feature(interaction, "shop"):
            return
        await interaction.response.defer()

        # Check if shop is enabled
        if not Config.SHOP_ENABLED:
            await interaction.followup.send("❌ The shop is currently disabled.", ephemeral=True)
            return

        # Ensure user exists in database
        await user_db.create_or_update_user(interaction.user.id, str(interaction.user))

        # Get items
        items = await store_db.get_all_items(category=category)

        if not items:
            await interaction.followup.send("❌ No items available in the store.")
            return

        # Get user's balance
        balance = await user_db.get_balance(interaction.user.id)

        # Group items by category
        categories = {}
        for item in items:
            cat = item["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(item)

        # Create embed
        embed = discord.Embed(
            title=f"{Config.CURRENCY_EMOJI} Phoenix Store",
            description=f"Your Balance: **{balance}** {Config.CURRENCY_NAME}",
            color=discord.Color.gold(),
        )

        for cat, cat_items in categories.items():
            items_text = ""
            for item in cat_items[: Config.SHOP_ITEMS_PER_PAGE]:  # Limit per config
                items_text += (
                    f"**[{item['item_id']}]** {item['name']}\n"
                    f"└ {item['cost']} {Config.CURRENCY_EMOJI} - {item['description']}\n\n"
                )

            if items_text:
                embed.add_field(name=f"📦 {cat.upper()}", value=items_text, inline=False)

        embed.set_footer(text="Use /buy <item_id> to purchase items | /balance to check your coins")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="buy", description="Purchase an item from the store")
    @app_commands.describe(
        item_id="The ID of the item to purchase",
        character_name="Your character name in-game (case-sensitive)",
    )
    async def buy_item(self, interaction: discord.Interaction, item_id: int, character_name: str):
        """Purchase an item and have it delivered in-game."""
        if not await check_feature(interaction, "shop"):
            return
        await interaction.response.defer()

        # Check if shop is enabled
        if not Config.SHOP_ENABLED:
            await interaction.followup.send("❌ The shop is currently disabled.", ephemeral=True)
            return

        # Check if account linking is required
        if Config.SHOP_REQUIRE_LINKED_ACCOUNT:
            # TODO: Check if user has linked EOS account
            pass

        # Ensure user exists
        await user_db.create_or_update_user(interaction.user.id, str(interaction.user))

        # Get item details
        item = await store_db.get_item(item_id)
        if not item:
            await interaction.followup.send("❌ Item not found.")
            return

        if not item["enabled"]:
            await interaction.followup.send("❌ This item is currently unavailable.")
            return

        # Check balance
        balance = await user_db.get_balance(interaction.user.id)
        if balance < item["cost"]:
            await interaction.followup.send(
                f"❌ Insufficient funds. You have {balance} {Config.CURRENCY_EMOJI}, "
                f"but need {item['cost']} {Config.CURRENCY_EMOJI}."
            )
            return

        # Find which server the player is on
        server_name = await self.rcon_manager.find_player_server(character_name)

        if not server_name:
            await interaction.followup.send(
                f"❌ Character '{character_name}' not found on any server. "
                "Make sure:\n"
                "• You are online in-game\n"
                "• Your character name is spelled exactly as it appears in-game\n"
                "• Your character is fully loaded into the world"
            )
            return

        # Deduct coins
        if not await user_db.deduct_coins(
            interaction.user.id, item["cost"], f"Purchase: {item['name']}"
        ):
            await interaction.followup.send("❌ Failed to process payment.")
            return

        # Record transaction
        transaction_id = await store_db.record_purchase(
            interaction.user.id, item_id, item["cost"], server_name, "pending"
        )

        # Deliver item
        client = self.rcon_manager.get_client(server_name)
        if not client:
            await store_db.update_transaction_status(
                transaction_id, "failed", "Server RCON unavailable"
            )
            # Refund coins
            await user_db.add_coins(
                interaction.user.id, item["cost"], f"Refund: {item['name']} (delivery failed)"
            )
            await interaction.followup.send(
                "❌ Failed to connect to server. Your coins have been refunded."
            )
            return

        success, message = await client.give_item_to_player(character_name, item["ark_command"])

        if success:
            await store_db.update_transaction_status(transaction_id, "completed")

            new_balance = await user_db.get_balance(interaction.user.id)

            embed = discord.Embed(
                title="✅ Purchase Successful!",
                description=(
                    f"**{item['name']}** has been delivered to **{character_name}** "
                    f"on **{server_name}**!"
                ),
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Cost", value=f"{item['cost']} {Config.CURRENCY_EMOJI}", inline=True
            )
            embed.add_field(
                name="New Balance", value=f"{new_balance} {Config.CURRENCY_EMOJI}", inline=True
            )
            embed.set_footer(text=f"Transaction ID: {transaction_id}")

            await interaction.followup.send(embed=embed)

            # Notify in-game
            await client.broadcast_message(
                f"{interaction.user.display_name} purchased {item['name']} from the Phoenix Store!"
            )
        else:
            await store_db.update_transaction_status(transaction_id, "failed", message)
            # Refund coins
            await user_db.add_coins(
                interaction.user.id, item["cost"], f"Refund: {item['name']} (delivery failed)"
            )
            await interaction.followup.send(
                f"❌ Failed to deliver item: {message}\nYour coins have been refunded."
            )

    @app_commands.command(name="balance", description="Check your Phoenix Coins balance")
    async def check_balance(self, interaction: discord.Interaction):
        """Check user's Phoenix Coin balance."""
        if not await check_feature(interaction, "shop"):
            return
        await interaction.response.defer()

        await user_db.create_or_update_user(interaction.user.id, str(interaction.user))
        balance = await user_db.get_balance(interaction.user.id)

        embed = discord.Embed(
            title=f"{Config.CURRENCY_EMOJI} Phoenix Coins Balance",
            description=f"You have **{balance}** {Config.CURRENCY_NAME}",
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Use /store to browse items")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="transactions", description="View your purchase history")
    @app_commands.describe(limit="Number of transactions to show (max 25)")
    async def transaction_history(self, interaction: discord.Interaction, limit: int = 10):
        """View purchase transaction history."""
        if not await check_feature(interaction, "shop"):
            return
        await interaction.response.defer()

        limit = min(limit, 25)  # Cap at 25
        transactions = await store_db.get_user_purchases(interaction.user.id, limit)

        if not transactions:
            await interaction.followup.send("You haven't made any purchases yet.")
            return

        embed = discord.Embed(title="📜 Purchase History", color=discord.Color.blue())

        for trans in transactions:
            status_emoji = {"completed": "✅", "pending": "⏳", "failed": "❌"}.get(
                trans["status"], "❓"
            )

            field_value = (
                f"**Server:** {trans['server_name']}\n"
                f"**Cost:** {trans['cost']} {Config.CURRENCY_EMOJI}\n"
                f"**Status:** {status_emoji} {trans['status'].title()}\n"
                f"**Date:** {trans['purchase_date']}"
            )

            if trans.get("error_message"):
                field_value += f"\n**Error:** {trans['error_message']}"

            embed.add_field(
                name=f"{trans['item_name']} (ID: {trans['transaction_id']})",
                value=field_value,
                inline=False,
            )

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="linkplayer",
        description="Link your Discord account to your ARK EOS ID and Specimen ID",
    )
    @app_commands.describe(
        eos_id="Your EOS ID (type 'help' for instructions, or leave blank to auto-detect)",
        specimen_id="Your Specimen Implant ID (numeric, find in your implant inventory - optional)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(send_messages=True)
    async def link_player(
        self, interaction: discord.Interaction, eos_id: str = "", specimen_id: str = ""
    ):
        """Link Discord user to EOS ID and optionally Specimen ID for item/coin delivery."""
        if not await check_feature(interaction, "shop"):
            return
        await interaction.response.defer(ephemeral=True)

        # Check if user needs help finding their EOS ID
        if eos_id.lower() in ["help", "?", "how"]:
            embed = discord.Embed(
                title="🔍 How to Find Your EOS ID",
                description="Follow these steps to find your EOS ID in ARK:",
                color=discord.Color.blue(),
            )
            embed.add_field(
                name="Step 1: Open Console",
                value="Press **TAB** key in-game to open the console",
                inline=False,
            )
            embed.add_field(
                name="Step 2: Run Command",
                value="Type: `ShowMyAdminManager` and press Enter",
                inline=False,
            )
            embed.add_field(
                name="Step 3: Find EOS ID",
                value="Look for the line that says **EOS ID** followed by a long string of numbers and letters",
                inline=False,
            )
            embed.add_field(
                name="Step 4: Link Account",
                value="Use `/linkplayer <your_eos_id>` with the ID you found",
                inline=False,
            )
            embed.add_field(
                name="🆔 Specimen ID (Optional but Recommended)",
                value=(
                    "For item delivery via RCON:\n"
                    "• Open your inventory\n"
                    "• Look at your **Specimen Implant**\n"
                    "• The number shown is your Specimen ID\n"
                    "• Use `/linkplayer <eos_id> <specimen_id>` to link both at once\n"
                    "• Or use `/register_specimen <specimen_id>` later"
                ),
                inline=False,
            )
            embed.set_footer(text="EOS ID: 00012a3b4c5d... | Specimen ID: 3744359")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # If no EOS ID provided, try to auto-detect from save files
        if not eos_id:
            try:
                # Try to find player by character name matching Discord username
                from bot.asa_parser_adapter import get_all_players_from_cluster
                from pathlib import Path

                cluster_path = (
                    Path(Config.CLUSTER_ROOT) if hasattr(Config, "CLUSTER_ROOT") else None
                )
                if not cluster_path or not cluster_path.exists():
                    await interaction.followup.send(
                        "❌ Auto-detection not available. Please provide your EOS ID manually.\n"
                        "Use `/linkplayer help` for instructions on finding your EOS ID.",
                        ephemeral=True,
                    )
                    return

                players = await get_all_players_from_cluster(cluster_path)

                # Try to find player by character name (case insensitive match with Discord name)
                discord_name = interaction.user.display_name.lower()
                matches = [
                    p
                    for p in players
                    if discord_name in p.character_name.lower()
                    or discord_name in p.player_name.lower()
                ]

                if len(matches) == 1:
                    # Single match found - auto-link
                    player = matches[0]
                    success = await players_db.link_player(
                        interaction.guild_id,
                        interaction.user.id,
                        player.eos_id,
                        str(interaction.user),
                        interaction.user.display_name,
                    )
                    if success:
                        await interaction.followup.send(
                            f"✅ **Auto-detected and linked!**\n"
                            f"Character: `{player.character_name or player.player_name}`\n"
                            f"EOS ID: `{player.eos_id}`\n\n"
                            f"You can now receive items and coins in-game!",
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send(
                            "❌ Failed to link account.", ephemeral=True
                        )
                    return
                elif len(matches) > 1:
                    # Multiple matches - ask user to choose
                    embed = discord.Embed(
                        title="🔍 Multiple Characters Found",
                        description="We found multiple characters that might be yours. Please use the command with your EOS ID:",
                        color=discord.Color.orange(),
                    )
                    for p in matches[:5]:  # Show max 5
                        embed.add_field(
                            name=p.character_name or p.player_name or "Unknown",
                            value=f"EOS ID: `{p.eos_id}`\nLevel {p.level}",
                            inline=False,
                        )
                    embed.set_footer(text="Use /linkplayer <eos_id> with the correct ID")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
                else:
                    # No matches found
                    await interaction.followup.send(
                        "❌ No characters found matching your Discord name.\n"
                        "Please provide your EOS ID manually: `/linkplayer <your_eos_id>`\n"
                        "Or use `/linkplayer help` for instructions.",
                        ephemeral=True,
                    )
                    return
            except Exception as e:
                logger.error(f"Auto-detection failed: {e}")
                await interaction.followup.send(
                    "❌ Auto-detection failed. Please provide your EOS ID manually.\n"
                    "Use `/linkplayer help` for instructions.",
                    ephemeral=True,
                )
                return

        # Manual EOS ID provided - link it.
        # Validate the EOS ID FIRST, before anything is written or looked up. A malformed ID is not
        # a cosmetic problem here: every downstream lookup is an exact match on this string, so a
        # single dropped character silently costs the player every purchase they ever make.
        try:
            eos_id = normalize_eos_id(eos_id)
        except InvalidEosId as e:
            await interaction.followup.send(
                f"❌ {e}\n\nNothing was linked. Use `/linkplayer help` to find your EOS ID.",
                ephemeral=True,
            )
            return

        # Validate specimen_id if provided
        if specimen_id and not specimen_id.isdigit():
            await interaction.followup.send(
                "❌ Invalid Specimen ID! It should be a numeric value (e.g., 3744359).\n"
                "Leave it blank if you don't have it yet, or check your Specimen Implant in inventory.",
                ephemeral=True,
            )
            return

        # If specimen_id not provided, try to fetch it automatically via RCON
        if not specimen_id:
            try:
                monitor_cog = self.bot.get_cog("ServerMonitor")
                if monitor_cog and monitor_cog.rcon_manager:
                    # Try to fetch specimen ID from any server
                    for server_name, rcon_client in monitor_cog.rcon_manager.clients.items():
                        try:
                            fetched_id = await players_db.sync_specimen_id_from_rcon(
                                rcon_client, eos_id, None  # Don't update DB yet, just fetch
                            )
                            if fetched_id:
                                specimen_id = fetched_id
                                logger.info(f"Auto-fetched specimen ID {specimen_id} for {eos_id}")
                                break
                        except:
                            continue
            except Exception as e:
                logger.debug(f"Could not auto-fetch specimen ID: {e}")

        success = await players_db.link_player(
            interaction.guild_id,
            interaction.user.id,
            eos_id,
            str(interaction.user),
            interaction.user.display_name,
            specimen_id if specimen_id else None,
        )
        if success:
            msg = f"✅ Successfully linked your account to EOS ID: `{eos_id}`\n"
            if specimen_id:
                msg += f"✅ Specimen ID registered: `{specimen_id}`\n"
            else:
                msg += "⚠️ No Specimen ID found. You can add it later with `/register_specimen <id>` or it will be auto-synced when you're online.\n"
            msg += "\nYou can now receive items and coins directly in-game!"
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ Failed to link account. Please try again.", ephemeral=True
            )

    @app_commands.command(
        name="adminlinkplayer",
        description="[ADMIN] Link another player's Discord account to their EOS ID",
    )
    @app_commands.describe(
        user="The Discord user to link",
        eos_id="Their EOS ID from ARK",
        specimen_id="Their Specimen Implant ID (numeric, optional)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def admin_link_player(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        eos_id: str,
        specimen_id: str = "",
    ):
        """Admin command to link another player's account."""
        if not await check_feature(interaction, "shop"):
            return
        await interaction.response.defer(ephemeral=True)

        # Admins get the same guard as players — this path is how a support fix gets applied, so a
        # typo here re-creates the exact fault it is being used to repair.
        try:
            eos_id = normalize_eos_id(eos_id)
        except InvalidEosId as e:
            await interaction.followup.send(f"❌ {e}\n\nNothing was linked.", ephemeral=True)
            return

        # Validate specimen_id if provided
        if specimen_id and not specimen_id.isdigit():
            await interaction.followup.send(
                "❌ Invalid Specimen ID! It should be a numeric value (e.g., 3744359).",
                ephemeral=True,
            )
            return

        # If specimen_id not provided, try to fetch it automatically via RCON
        if not specimen_id:
            try:
                monitor_cog = self.bot.get_cog("ServerMonitor")
                if monitor_cog and monitor_cog.rcon_manager:
                    # Try to fetch specimen ID from any server
                    for server_name, rcon_client in monitor_cog.rcon_manager.clients.items():
                        try:
                            fetched_id = await players_db.sync_specimen_id_from_rcon(
                                rcon_client, eos_id, None  # Don't update DB yet, just fetch
                            )
                            if fetched_id:
                                specimen_id = fetched_id
                                logger.info(
                                    f"Admin auto-fetched specimen ID {specimen_id} for {eos_id}"
                                )
                                break
                        except:
                            continue
            except Exception as e:
                logger.debug(f"Could not auto-fetch specimen ID: {e}")

        success = await players_db.link_player(
            interaction.guild_id,
            user.id, eos_id, str(user), user.display_name, specimen_id if specimen_id else None
        )

        if success:
            msg = f"✅ Successfully linked {user.mention} to EOS ID: `{eos_id}`\n"
            if specimen_id:
                msg += f"✅ Specimen ID registered: `{specimen_id}`\n"
            else:
                msg += "⚠️ No Specimen ID found. It will be auto-synced when they're online.\n"
            msg += f"\n{user.display_name} can now receive items and coins in-game!"
            await interaction.followup.send(msg, ephemeral=True)
        else:
            # Check if EOS ID is already linked to someone else
            try:
                from pathlib import Path

                db_path = Path(Config.DATABASE_PATH)
                async with aiosqlite.connect(db_path) as db:
                    async with db.execute(
                        "SELECT discord_user_id FROM players WHERE eos_id = ?", (eos_id,)
                    ) as cursor:
                        existing = await cursor.fetchone()
                        if existing and existing[0] != user.id:
                            await interaction.followup.send(
                                f"❌ That EOS ID is already linked to <@{existing[0]}>.\n"
                                f"Each EOS ID can only be linked to one Discord account.",
                                ephemeral=True,
                            )
                            return
            except:
                pass

            await interaction.followup.send(
                f"❌ Failed to link account for {user.mention}. Please try again.", ephemeral=True
            )

    @app_commands.command(
        name="viewplayerinfo", description="[ADMIN] View another player's linked account info"
    )
    @app_commands.describe(user="The Discord user to view info for")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def view_player_info(self, interaction: discord.Interaction, user: discord.Member):
        """Admin command to view another player's linked account information."""
        if not await check_feature(interaction, "player_management"):
            return
        await interaction.response.defer(ephemeral=True)

        player = await players_db.get_player_by_discord_id(user.id)
        if player:
            # If missing specimen ID, try to fetch it immediately via RCON
            if not player.get("specimen_id"):
                try:
                    monitor_cog = self.bot.get_cog("ServerMonitor")
                    if monitor_cog and monitor_cog.rcon_manager:
                        for server_name, rcon_client in monitor_cog.rcon_manager.clients.items():
                            try:
                                fetched_id = await players_db.sync_specimen_id_from_rcon(
                                    rcon_client, player["eos_id"], player["discord_user_id"]
                                )
                                if fetched_id:
                                    player["specimen_id"] = fetched_id
                                    logger.info(
                                        f"Auto-synced specimen ID {fetched_id} via /viewplayerinfo"
                                    )
                                    break
                            except:
                                continue
                except Exception as e:
                    logger.debug(f"Could not auto-sync in /viewplayerinfo: {e}")

            embed = discord.Embed(
                title=f"🔗 Linked Account - {user.display_name}",
                description=f"Account information for {user.mention}",
                color=discord.Color.blue(),
            )
            embed.add_field(name="Discord User", value=f"{user.mention} ({user.id})", inline=False)
            embed.add_field(name="EOS ID", value=f"`{player['eos_id']}`", inline=False)

            # Show specimen ID status
            if player.get("specimen_id"):
                embed.add_field(
                    name="Specimen ID", value=f"`{player['specimen_id']}`", inline=False
                )
                embed.add_field(
                    name="✅ Item Delivery",
                    value="Ready! Can receive items via RCON.",
                    inline=False,
                )
            else:
                embed.add_field(
                    name="⚠️ Specimen ID",
                    value="Not found. Will auto-sync when they're online.",
                    inline=False,
                )

            if player.get("last_seen_server"):
                embed.add_field(
                    name="Last Seen Server", value=player["last_seen_server"], inline=True
                )
                if player.get("last_player_id"):
                    embed.add_field(
                        name="Last Player ID", value=player["last_player_id"], inline=True
                    )
                embed.add_field(
                    name="Last Updated", value=player.get("updated_at", "Unknown"), inline=True
                )
            else:
                embed.add_field(name="Status", value="Not yet seen in-game", inline=False)

            embed.set_footer(text="Use /adminlinkplayer to update their info")
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                f"❌ {user.mention} hasn't linked their account yet.\n"
                f"Use `/adminlinkplayer` and select {user.mention} from the dropdown to link their account.",
                ephemeral=True,
            )

    @app_commands.command(name="unlinkplayer", description="[ADMIN] Unlink a player's account")
    @app_commands.describe(
        user="The Discord user to unlink (optional if using eos_id)",
        eos_id="The EOS ID to unlink (optional if using user)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def unlink_player(
        self, interaction: discord.Interaction, user: discord.Member = None, eos_id: str = None
    ):
        """Admin command to unlink a player's account."""
        if not await check_feature(interaction, "player_management"):
            return
        await interaction.response.defer(ephemeral=True)

        if not user and not eos_id:
            await interaction.followup.send(
                "❌ You must provide either a Discord user or an EOS ID to unlink.", ephemeral=True
            )
            return

        # Unlink by Discord user
        if user:
            player = await players_db.get_player_by_discord_id(interaction.guild_id, user.id)
            if not player:
                await interaction.followup.send(
                    f"❌ {user.mention} doesn't have a linked account.", ephemeral=True
                )
                return

            success = await players_db.unlink_player_by_discord_id(interaction.guild_id, user.id)
            if success:
                await interaction.followup.send(
                    f"✅ Successfully unlinked {user.mention}\n"
                    f"EOS ID `{player['eos_id']}` is now available to link to another account.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"❌ Failed to unlink {user.mention}. Please try again.", ephemeral=True
                )

        # Unlink by EOS ID
        elif eos_id:
            player = await players_db.get_player_by_eos_id(eos_id)
            if not player:
                await interaction.followup.send(
                    f"❌ EOS ID `{eos_id}` is not linked to any account.", ephemeral=True
                )
                return

            discord_id = player.get("discord_user_id")
            success = await players_db.unlink_player_by_eos_id(interaction.guild_id, eos_id)
            if success:
                await interaction.followup.send(
                    f"✅ Successfully unlinked EOS ID `{eos_id}`\n"
                    f"Previously linked to Discord user ID: `{discord_id}`\n"
                    f"This EOS ID can now be linked to a new account.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"❌ Failed to unlink EOS ID `{eos_id}`. Please try again.", ephemeral=True
                )

    @app_commands.command(
        name="listlinkedplayers", description="[ADMIN] View all linked player accounts"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def list_linked_players(self, interaction: discord.Interaction):
        """Admin command to view all linked player accounts."""
        if not await check_feature(interaction, "player_management"):
            return
        await interaction.response.defer(ephemeral=True)

        players = await players_db.get_all_linked_players()

        if not players:
            await interaction.followup.send(
                "No players have linked their accounts yet.", ephemeral=True
            )
            return

        # Create pagination view
        view = LinkedPlayersView(players)
        embed = view.create_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="mylink", description="View your linked EOS ID and Specimen ID")
    async def my_link(self, interaction: discord.Interaction):
        """View your linked EOS ID, Specimen ID, and player information."""
        if not await check_feature(interaction, "player_management"):
            return
        await interaction.response.defer(ephemeral=True)

        player = await players_db.get_player_by_discord_id(interaction.user.id)
        if player:
            # If missing specimen ID, try to fetch it immediately via RCON
            if not player.get("specimen_id"):
                try:
                    monitor_cog = self.bot.get_cog("ServerMonitor")
                    if monitor_cog and monitor_cog.rcon_manager:
                        for server_name, rcon_client in monitor_cog.rcon_manager.clients.items():
                            try:
                                fetched_id = await players_db.sync_specimen_id_from_rcon(
                                    rcon_client, player["eos_id"], player["discord_user_id"]
                                )
                                if fetched_id:
                                    player["specimen_id"] = fetched_id
                                    logger.info(f"Auto-synced specimen ID {fetched_id} via /mylink")
                                    break
                            except:
                                continue
                except Exception as e:
                    logger.debug(f"Could not auto-sync in /mylink: {e}")

            embed = discord.Embed(title="🔗 Your Linked Account", color=discord.Color.blue())
            embed.add_field(name="EOS ID", value=f"`{player['eos_id']}`", inline=False)

            # Show specimen ID status
            if player.get("specimen_id"):
                embed.add_field(
                    name="Specimen ID", value=f"`{player['specimen_id']}`", inline=False
                )
                embed.add_field(
                    name="✅ Item Delivery",
                    value="Ready! You can receive items via RCON.",
                    inline=False,
                )
            else:
                embed.add_field(
                    name="⚠️ Specimen ID",
                    value="Not found. Make sure you're online on a server, or use `/register_specimen <id>` manually.",
                    inline=False,
                )

            if player.get("last_seen_server"):
                # Show server status even if player_id is not tracked
                embed.add_field(
                    name="Last Seen Server", value=player["last_seen_server"], inline=True
                )
                if player.get("last_player_id"):
                    embed.add_field(
                        name="Last Player ID", value=player["last_player_id"], inline=True
                    )
                embed.add_field(
                    name="Last Updated", value=player.get("updated_at", "Unknown"), inline=True
                )
            else:
                embed.add_field(name="Status", value="Not yet seen in-game", inline=False)

            embed.set_footer(
                text="This information is used to deliver items and coins to you in-game"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ You haven't linked your account yet.\n"
                "Use `/linkplayer <eos_id>` to link your account.\n"
                "Optionally include your Specimen ID: `/linkplayer <eos_id> <specimen_id>`",
                ephemeral=True,
            )

    @app_commands.command(name="relink", description="Update your linked EOS ID")
    @app_commands.describe(new_eos_id="Your new EOS ID (type 'help' for instructions)")
    async def relink_player(self, interaction: discord.Interaction, new_eos_id: str):
        """Update your linked EOS ID. Useful if you made a typo or need to change accounts."""
        if not await check_feature(interaction, "player_management"):
            return
        await interaction.response.defer(ephemeral=True)

        # Check if user needs help
        if new_eos_id.lower() in ["help", "?", "how"]:
            embed = discord.Embed(
                title="🔍 How to Find Your EOS ID",
                description="Follow these steps to find your EOS ID in ARK:",
                color=discord.Color.blue(),
            )
            embed.add_field(
                name="Step 1: Open Console",
                value="Press **TAB** key in-game to open the console",
                inline=False,
            )
            embed.add_field(
                name="Step 2: Run Command",
                value="Type: `ShowMyAdminManager` and press Enter",
                inline=False,
            )
            embed.add_field(
                name="Step 3: Find EOS ID",
                value="Look for the line that says **EOS ID** followed by a long string of numbers and letters",
                inline=False,
            )
            embed.add_field(
                name="Step 4: Relink Account",
                value="Use `/relink <your_new_eos_id>` with the correct ID",
                inline=False,
            )
            embed.set_footer(text="Your EOS ID looks like: 00012a3b4c5d6e7f8901234567890abc")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # /relink exists precisely because someone got their EOS ID wrong, so it is the LAST place
        # that should accept a malformed one.
        try:
            new_eos_id = normalize_eos_id(new_eos_id)
        except InvalidEosId as e:
            await interaction.followup.send(
                f"❌ {e}\n\nYour existing link was not changed. `/relink help` shows where to find it.",
                ephemeral=True,
            )
            return

        # Check if user has an existing link
        existing_player = await players_db.get_player_by_discord_id(interaction.user.id)

        if not existing_player:
            await interaction.followup.send(
                "❌ You don't have a linked account yet.\n"
                "Use `/linkplayer <eos_id>` to create your first link.",
                ephemeral=True,
            )
            return

        # Show confirmation with old and new EOS IDs
        old_eos_id = existing_player.get("eos_id") or "Unknown"

        # Update the link
        success = await players_db.link_player(
            interaction.guild_id,
            interaction.user.id, new_eos_id, str(interaction.user), interaction.user.display_name
        )

        if success:
            embed = discord.Embed(
                title="✅ Account Relinked Successfully",
                description="Your EOS ID has been updated.",
                color=discord.Color.green(),
            )
            embed.add_field(name="Previous EOS ID", value=f"`{old_eos_id}`", inline=False)
            embed.add_field(name="New EOS ID", value=f"`{new_eos_id}`", inline=False)
            embed.set_footer(text="Items and coins will now be delivered to your new account")
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ Failed to update your link. Please try again or contact an admin.",
                ephemeral=True,
            )

    @app_commands.command(name="getmyinfo", description="View your complete account information")
    async def get_my_info(self, interaction: discord.Interaction):
        """View your complete account information including balance, link status, and Discord info."""
        if not await check_feature(interaction, "player_management"):
            return
        await interaction.response.defer(ephemeral=True)

        # Get user info from database
        db_user = await user_db.get_user(interaction.user.id)
        player_link = await players_db.get_player_by_discord_id(interaction.user.id)

        embed = discord.Embed(title=f"👤 Your Account Info", color=discord.Color.blue())

        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        # Discord info
        joined_at = (
            interaction.user.joined_at.strftime("%Y-%m-%d")
            if hasattr(interaction.user, "joined_at") and interaction.user.joined_at
            else "Unknown"
        )
        embed.add_field(
            name="📱 Discord",
            value=(
                f"**Username:** {interaction.user.name}\n"
                f"**Display Name:** {interaction.user.display_name}\n"
                f"**ID:** {interaction.user.id}\n"
                f"**Joined Server:** {joined_at}"
            ),
            inline=True,
        )

        # Economy info
        if db_user:
            balance = db_user.get("phoenix_coins", 0)
            last_seen = db_user.get("last_seen", "Never")
            if last_seen and last_seen != "Never":
                last_seen = last_seen[:10]  # Format date
            embed.add_field(
                name=f"{Config.CURRENCY_EMOJI} Economy",
                value=(
                    f"**Balance:** {balance} {Config.CURRENCY_NAME}\n"
                    f"**Status:** {'✅ Registered' if balance >= 0 else 'Not registered'}\n"
                    f"**Last Active:** {last_seen}"
                ),
                inline=True,
            )
        else:
            embed.add_field(
                name=f"{Config.CURRENCY_EMOJI} Economy",
                value=(f"**Status:** Not registered\n" f"Use `/store` to register"),
                inline=True,
            )

        # ARK link info
        if player_link:
            specimen_id = player_link.get('specimen_id')
            specimen_text = f"**Specimen ID:** `{specimen_id}`\n" if specimen_id else ""
            embed.add_field(
                name="🎮 ARK Link",
                value=(
                    f"**Status:** ✅ Linked\n"
                    f"**EOS ID:** `{player_link['eos_id']}`\n"
                    f"{specimen_text}"
                    f"**Last Server:** {player_link.get('last_seen_server', 'Unknown')}\n"
                    f"**Linked Since:** {(player_link.get('created_at') or 'Unknown')[:10]}"
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="🎮 ARK Link",
                value=(
                    "**Status:** ❌ Not linked\n"
                    "Use `/linkplayer` to link your ARK account and receive in-game items!"
                ),
                inline=False,
            )

        embed.set_footer(
            text="💡 Use /store to browse items, /balance to check coins, /linkplayer to link your ARK account"
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="sync_specimen", description="[Admin] Bulk sync specimen IDs for all linked players"
    )
    @app_commands.describe(server_name="Server to query (leave empty for all online players)")
    async def sync_specimen_ids(
        self, interaction: discord.Interaction, server_name: Optional[str] = None
    ):
        """Admin command to bulk update specimen IDs via RCON for all linked players."""
        if not await check_feature(interaction, "shop"):
            return
        await interaction.response.defer(ephemeral=True)

        # Check if user is admin
        admin_role_id = Config.ADMIN_ROLE_ID
        if admin_role_id:
            if not any(role.id == admin_role_id for role in interaction.user.roles):
                await interaction.followup.send(
                    "❌ You don't have permission to use this command.", ephemeral=True
                )
                return

        try:
            # Get ServerMonitor cog for access to RCON clients
            monitor_cog = self.bot.get_cog("ServerMonitor")
            if not monitor_cog or not monitor_cog.rcon_manager:
                await interaction.followup.send("❌ RCON manager not available.", ephemeral=True)
                return

            # Get all linked players
            all_players = await players_db.get_all_linked_players()

            if not all_players:
                await interaction.followup.send("❌ No linked players found.", ephemeral=True)
                return

            synced_count = 0
            failed_count = 0
            skipped_count = 0

            embed = discord.Embed(
                title="🔄 Syncing Specimen IDs",
                description="Querying servers for specimen IDs...",
                color=discord.Color.blue(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

            # If specific server requested, only use that server's RCON
            servers_to_check = []
            if server_name:
                if server_name in monitor_cog.rcon_manager.clients:
                    servers_to_check = [
                        (server_name, monitor_cog.rcon_manager.clients[server_name])
                    ]
                else:
                    await interaction.edit_original_response(
                        embed=discord.Embed(
                            title="❌ Error",
                            description=f"Server '{server_name}' not found or RCON not available.",
                            color=discord.Color.red(),
                        )
                    )
                    return
            else:
                # Check all servers
                servers_to_check = list(monitor_cog.rcon_manager.clients.items())

            # Sync each player
            for player in all_players:
                discord_user_id = player.get("discord_user_id")
                eos_id = player.get("eos_id")
                specimen_id = player.get("specimen_id")

                if not eos_id or not discord_user_id:
                    skipped_count += 1
                    continue

                if specimen_id:
                    # Already has specimen ID
                    skipped_count += 1
                    continue

                # Try each server until we find the player
                synced = False
                for srv_name, rcon_client in servers_to_check:
                    try:
                        fetched_id = await players_db.sync_specimen_id_from_rcon(
                            rcon_client, eos_id, discord_user_id
                        )
                        if fetched_id:
                            synced_count += 1
                            synced = True
                            logger.info(
                                f"Synced specimen ID {fetched_id} for Discord user {discord_user_id}"
                            )
                            break  # Found it, no need to check other servers
                    except Exception as e:
                        logger.debug(f"Could not sync {eos_id} on {srv_name}: {e}")

                if not synced:
                    failed_count += 1

            # Send results
            result_embed = discord.Embed(
                title="✅ Specimen ID Sync Complete",
                description=f"Processed {len(all_players)} linked players",
                color=discord.Color.green(),
            )
            result_embed.add_field(name="✅ Synced", value=str(synced_count), inline=True)
            result_embed.add_field(
                name="⏭️ Skipped", value=f"{skipped_count} (already have ID)", inline=True
            )
            result_embed.add_field(name="❌ Failed", value=f"{failed_count} (offline)", inline=True)
            result_embed.set_footer(text="Players must be online for specimen ID to be retrieved")

            await interaction.edit_original_response(embed=result_embed)

        except Exception as e:
            logger.error(f"Error in sync_specimen command: {e}", exc_info=True)
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="❌ Error",
                    description=f"Failed to sync specimen IDs: {str(e)}",
                    color=discord.Color.red(),
                )
            )

    @app_commands.command(
        name="lookupplayer", description="[ADMIN] Look up a player's EOS ID by character name"
    )
    @app_commands.describe(character_name="Character name to search for (partial match supported)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def lookup_player(self, interaction: discord.Interaction, character_name: str):
        """Look up a player's EOS ID from save files by character name."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
            return
        if not await check_feature(interaction, "shop"):
            return
        await interaction.response.defer(ephemeral=True)

        try:
            # Get all players from cluster save files
            from bot.asa_parser_adapter import get_all_players_from_cluster
            from pathlib import Path

            # Try to get cluster path from config
            cluster_path = None
            guild_id = Config.DISCORD_GUILD_ID or (
                interaction.guild.id if interaction.guild else None
            )

            if guild_id:
                from bot.database import server_config_db

                config = await server_config_db.get_server_config(guild_id)
                if config and config.get("cluster_folder_path"):
                    cluster_path = Path(config["cluster_folder_path"])

            if not cluster_path or not cluster_path.exists():
                # Fallback to Config.CLUSTER_ROOT if available
                if hasattr(Config, "CLUSTER_ROOT"):
                    cluster_path = Path(Config.CLUSTER_ROOT)

            if not cluster_path or not cluster_path.exists():
                await interaction.followup.send(
                    "❌ Cluster path not configured. Contact an admin to set up player lookup.",
                    ephemeral=True,
                )
                return

            # Search for players
            all_players = await get_all_players_from_cluster(cluster_path)

            # Filter by character name (case-insensitive, partial match)
            search_term = character_name.lower()
            matches = [
                p
                for p in all_players
                if search_term in (p.character_name or "").lower()
                or search_term in (p.player_name or "").lower()
            ]

            if not matches:
                await interaction.followup.send(
                    f"❌ No players found matching '{character_name}'.\n"
                    "Try a different name or check spelling.",
                    ephemeral=True,
                )
                return

            # Show results
            if len(matches) == 1:
                player = matches[0]
                embed = discord.Embed(title="✅ Player Found", color=discord.Color.green())
                embed.add_field(
                    name="Character Name", value=player.character_name or "Unknown", inline=True
                )
                embed.add_field(
                    name="Platform Name", value=player.player_name or "Unknown", inline=True
                )
                embed.add_field(name="EOS ID", value=f"`{player.eos_id}`", inline=False)
                embed.add_field(name="Level", value=str(player.level), inline=True)
                if player.tribe_id:
                    embed.add_field(name="Tribe ID", value=str(player.tribe_id), inline=True)
                embed.set_footer(
                    text="Use /linkplayer <eos_id> to link this account to your Discord"
                )
                await interaction.followup.send(embed=embed, ephemeral=True)

            else:
                # Multiple matches
                embed = discord.Embed(
                    title=f"🔍 Found {len(matches)} Players",
                    description=f"Multiple players match '{character_name}':",
                    color=discord.Color.blue(),
                )

                for i, player in enumerate(matches[:10], 1):  # Limit to 10
                    char_name = player.character_name or player.player_name or "Unknown"
                    platform_name = (
                        player.player_name if player.player_name != player.character_name else ""
                    )

                    field_value = f"**EOS ID:** `{player.eos_id}`\n"
                    if platform_name:
                        field_value += f"**Platform:** {platform_name}\n"
                    field_value += f"**Level:** {player.level}"

                    embed.add_field(name=f"{i}. {char_name}", value=field_value, inline=False)

                if len(matches) > 10:
                    embed.set_footer(
                        text=f"Showing 10 of {len(matches)} matches. Be more specific for fewer results."
                    )
                else:
                    embed.set_footer(
                        text="Use /linkplayer <eos_id> to link an account to your Discord"
                    )

                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in lookup_player command: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error looking up player: {str(e)}", ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(Store(bot))
