"""
Admin cog for managing the store and granting Phoenix Coins.
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
import json
import os
from typing import Optional

from dotenv import load_dotenv

from bot.database import user_db, store_db, players_db
from bot.utils.config import Config
from bot.utils.player_linking import create_eos_id_help_embed
from bot.utils.validation import validate_rcon_input


logger = logging.getLogger("AdminCog")


def is_admin():
    """Check if user has admin role."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if not Config.ADMIN_ROLE_ID:
            return interaction.user.guild_permissions.administrator
        return any(role.id == Config.ADMIN_ROLE_ID for role in interaction.user.roles)

    return app_commands.check(predicate)


class Admin(commands.Cog):
    """Admin commands for managing the store and currency."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="grantcoins", description="[ADMIN] Grant Phoenix Coins to a user")
    @app_commands.describe(
        user="The user to grant coins to", amount="Amount of Phoenix Coins to grant"
    )
    @is_admin()
    async def grant_coins(
        self, interaction: discord.Interaction, user: discord.Member, amount: int
    ):
        """Grant Phoenix Coins to a user."""
        await interaction.response.defer()

        if amount <= 0:
            await interaction.followup.send("❌ Amount must be positive.")
            return

        # Ensure user exists
        await user_db.create_or_update_user(user.id, str(user))

        # Grant coins
        new_balance = await user_db.add_coins(
            user.id, amount, f"Admin grant by {interaction.user}", interaction.user.id
        )

        embed = discord.Embed(
            title="✅ Coins Granted",
            description=f"Granted **{amount}** {Config.CURRENCY_EMOJI} to {user.mention}",
            color=discord.Color.green(),
        )
        embed.add_field(name="New Balance", value=f"{new_balance} {Config.CURRENCY_EMOJI}")
        embed.set_footer(text=f"Granted by {interaction.user}")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="giveitem", description="[ADMIN] Give an item to a player")
    @app_commands.describe(
        player="The Discord user or character name",
        item_name="Item name to search for (e.g., 'Metal Ingot', 'Gun', 'Stone')",
        quantity="Number of items to give (default: 1)",
        quality="Item quality/durability (default: 1)",
        server="Specific server name (optional - will auto-detect if not provided)",
    )
    @is_admin()
    async def give_item(
        self,
        interaction: discord.Interaction,
        player: str,
        item_name: str,
        quantity: int = 1,
        quality: int = 1,
        server: Optional[str] = None,
    ):
        """Give an item to a player - streamlined single command."""
        await interaction.response.defer()

        # Import here to avoid circular dependency
        from bot.utils.arkids_api import get_arkids_client
        from bot.rcon.client import RCONManager
        from bot.database import server_config_db

        try:
            # Step 1: Find the player (try Discord user first, then EOS ID, then character name)
            player_eos_id = None
            player_display = player

            # Try parsing as Discord mention/ID
            if player.startswith("<@") and player.endswith(">"):
                discord_id = int(player.strip("<@!>"))
                player_data = await players_db.get_player_by_discord_id(discord_id)
                if player_data:
                    player_eos_id = player_data.get("eos_id")
                    player_display = (
                        player_data.get("character_name")
                        or player_data.get("player_name")
                        or player
                    )
            elif player.isdigit():
                # Try as Discord ID
                player_data = await players_db.get_player_by_discord_id(int(player))
                if player_data:
                    player_eos_id = player_data.get("eos_id")
                    player_display = (
                        player_data.get("character_name")
                        or player_data.get("player_name")
                        or player
                    )

            # If not found, search by character name
            if not player_eos_id:
                search_results = await players_db.search_players_by_name(player)
                if search_results:
                    player_data = search_results[0]
                    player_eos_id = player_data.get("eos_id")
                    player_display = (
                        player_data.get("character_name")
                        or player_data.get("player_name")
                        or player
                    )
                else:
                    # Use as-is (might be Steam ID or EOS ID)
                    player_eos_id = player
                    player_display = f"Player {player[:16]}"

            # Step 2: Search for the item
            arkids_client = get_arkids_client()
            items = await arkids_client.search_items(item_name, limit=1)

            if not items:
                await interaction.followup.send(
                    f"❌ No items found matching '{item_name}'. Try a different search term.",
                    ephemeral=True,
                )
                return

            item = items[0]

            # Step 3: Get RCON manager and find player on servers
            rcon_manager: RCONManager = (
                self.bot.get_cog("ServerMonitor").rcon_manager
                if self.bot.get_cog("ServerMonitor")
                else None
            )

            if not rcon_manager:
                await interaction.followup.send(
                    "❌ RCON Manager not initialized. Cannot send items.", ephemeral=True
                )
                return

            # Find player on servers
            target_server = None
            target_client = None

            if server:
                # Use specified server
                target_client = rcon_manager.clients.get(server)
                target_server = server
            else:
                # Auto-detect - search all servers
                for server_name, client in rcon_manager.clients.items():
                    try:
                        players_online = await client.get_player_list()
                        # Check if our player is online (by any identifier)
                        for p in players_online:
                            p_name = p.get("name", "").lower()
                            p_steam = p.get("steam_id", "")
                            if (
                                player.lower() in p_name
                                or player_display.lower() in p_name
                                or player == p_steam
                            ):
                                target_server = server_name
                                target_client = client
                                break
                        if target_server:
                            break
                    except:
                        continue

            if not target_client:
                # Try last known server from cache
                if player_eos_id and player_eos_id != player:
                    player_cache = await players_db.get_player_by_eos_id(player_eos_id)
                    if player_cache:
                        last_server = player_cache.get("last_server")
                        if last_server:
                            target_client = rcon_manager.clients.get(last_server)
                            target_server = last_server if target_client else None

            if not target_client or not target_server:
                await interaction.followup.send(
                    f"❌ Player '{player_display}' not found on any server.\n"
                    f"They may be offline or you can specify a server with the `server:` parameter.",
                    ephemeral=True,
                )
                return

            # Validate RCON input
            if player_eos_id and not validate_rcon_input(player_eos_id):
                await interaction.followup.send(
                    "❌ Invalid player ID format. Only alphanumeric characters, underscores, hyphens, and dots are allowed.",
                    ephemeral=True,
                )
                return

            # Step 4: Execute the give item command
            command = (
                f'GiveItemToPlayer {player_eos_id} "{item.blueprint}" {quantity} {quality} false'
            )

            response = await target_client.execute_command(command)

            # Step 5: Send success message
            embed = discord.Embed(
                title="✅ Item Sent",
                description=f"Successfully sent **{quantity}x {item.name}** to **{player_display}**",
                color=discord.Color.green(),
            )
            embed.add_field(name="Server", value=target_server, inline=True)
            embed.add_field(name="Quality", value=str(quality), inline=True)
            embed.add_field(name="Player ID", value=f"`{player_eos_id[:24]}`", inline=False)

            if response:
                embed.add_field(name="Response", value=f"```{response[:200]}```", inline=False)

            embed.set_footer(text=f"Executed by {interaction.user}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in give_item: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to give item: {str(e)}", ephemeral=True)

    @app_commands.command(
        name="reloadconfig",
        description="[ADMIN] Reload config from .env and refresh runtime settings",
    )
    @is_admin()
    async def reload_config(self, interaction: discord.Interaction):
        """Reload environment-based configuration and try to refresh RCON/server monitors without a full restart."""
        await interaction.response.defer(ephemeral=True)

        # Reload .env into process environment
        env_path = os.path.join(os.getcwd(), ".env")
        if not os.path.exists(env_path):
            await interaction.followup.send(
                "❌ .env file not found in working directory.", ephemeral=True
            )
            return

        try:
            load_dotenv(env_path, override=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to reload .env: {e}", ephemeral=True)
            return

        # Update Config from environment
        def _int_env(name: str) -> Optional[int]:
            val = os.getenv(name)
            try:
                return int(val) if val else None
            except:
                return None

        Config.GUILD_ID = _int_env("DISCORD_GUILD_ID")
        Config.CHAT_CHANNEL_ID = _int_env("CHAT_CHANNEL_ID")
        Config.STATUS_CHANNEL_ID = _int_env("STATUS_CHANNEL_ID")
        Config.ADMIN_ROLE_ID = _int_env("ADMIN_ROLE_ID")

        servers_json = os.getenv("ARK_SERVERS", "[]")
        try:
            Config.ARK_SERVERS = json.loads(servers_json) if servers_json else []
        except Exception:
            # Keep previous servers if JSON invalid
            pass

        # Attempt to notify/refresh other cogs (server monitor, chat relay)
        refreshed = []
        failed = []

        # Server monitor reload
        try:
            monitor = self.bot.get_cog("ServerMonitor")
            if monitor and hasattr(monitor, "reload_servers"):
                await monitor.reload_servers(Config.ARK_SERVERS)
                refreshed.append("ServerMonitor")
        except Exception as e:
            failed.append(f"ServerMonitor: {e}")

        # Chat relay channel update
        try:
            relay = self.bot.get_cog("ChatRelay")
            if relay and hasattr(relay, "update_target_channel"):
                await relay.update_target_channel(Config.CHAT_CHANNEL_ID)
                refreshed.append("ChatRelay")
        except Exception as e:
            failed.append(f"ChatRelay: {e}")

        # Status channel update (if cog supports it)
        try:
            status = self.bot.get_cog("ServerStatus")
            if status and hasattr(status, "update_status_channel"):
                await status.update_status_channel(Config.STATUS_CHANNEL_ID)
                refreshed.append("ServerStatus")
        except Exception as e:
            failed.append(f"ServerStatus: {e}")

        msg = [
            "✅ Configuration reloaded from .env.",
            f"• Guild ID: {Config.GUILD_ID or 'unset'}",
            f"• Chat Channel ID: {Config.CHAT_CHANNEL_ID or 'unset'}",
            f"• Status Channel ID: {Config.STATUS_CHANNEL_ID or 'unset'}",
            f"• Admin Role ID: {Config.ADMIN_ROLE_ID or 'unset'}",
            f"• Servers: {len(Config.ARK_SERVERS)}",
        ]

        if refreshed:
            msg.append(f"• Refreshed cogs: {', '.join(refreshed)}")
        if failed:
            msg.append("• Some refresh actions failed (safe to ignore):\n" + "\n".join(failed))

        msg.append("\n⚠️ If RCON connections were changed, a full bot restart may still be needed.")

        await interaction.followup.send("\n".join(msg), ephemeral=True)

    @app_commands.command(name="additem", description="[ADMIN] Add a new item to the store")
    @app_commands.describe(
        name="Item name",
        cost="Cost in Phoenix Coins",
        ark_command="ARK console command (use {player_id} as placeholder)",
        description="Item description",
        category="Item category",
    )
    @is_admin()
    async def add_item(
        self,
        interaction: discord.Interaction,
        name: str,
        cost: int,
        ark_command: str,
        description: str = "",
        category: str = "general",
    ):
        """Add a new item to the store."""
        await interaction.response.defer()

        if cost < 0:
            await interaction.followup.send("❌ Cost cannot be negative.")
            return

        if "{player_id}" not in ark_command:
            await interaction.followup.send(
                "⚠️ Warning: Command doesn't contain {player_id} placeholder. "
                "This might not work correctly."
            )

        item_id = await store_db.add_item(name, description, cost, ark_command, category)

        embed = discord.Embed(title="✅ Item Added to Store", color=discord.Color.green())
        embed.add_field(name="ID", value=str(item_id), inline=True)
        embed.add_field(name="Name", value=name, inline=True)
        embed.add_field(name="Cost", value=f"{cost} {Config.CURRENCY_EMOJI}", inline=True)
        embed.add_field(name="Category", value=category, inline=True)
        embed.add_field(name="Command", value=f"```{ark_command}```", inline=False)
        if description:
            embed.add_field(name="Description", value=description, inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="removeitem", description="[ADMIN] Remove an item from the store")
    @app_commands.describe(item_id="The ID of the item to remove")
    @is_admin()
    async def remove_item(self, interaction: discord.Interaction, item_id: int):
        """Remove an item from the store."""
        await interaction.response.defer()

        # Get item first to show what was removed
        item = await store_db.get_item(item_id)
        if not item:
            await interaction.followup.send("❌ Item not found.")
            return

        success = await store_db.remove_item(item_id)

        if success:
            await interaction.followup.send(
                f"✅ Removed **{item['name']}** (ID: {item_id}) from the store."
            )
        else:
            await interaction.followup.send("❌ Failed to remove item.")

    @app_commands.command(name="setprice", description="[ADMIN] Change an item's price")
    @app_commands.describe(item_id="The ID of the item", new_price="New price in Phoenix Coins")
    @is_admin()
    async def set_price(self, interaction: discord.Interaction, item_id: int, new_price: int):
        """Change an item's price."""
        await interaction.response.defer()

        if new_price < 0:
            await interaction.followup.send("❌ Price cannot be negative.")
            return

        item = await store_db.get_item(item_id)
        if not item:
            await interaction.followup.send("❌ Item not found.")
            return

        success = await store_db.update_item_price(item_id, new_price)

        if success:
            await interaction.followup.send(
                f"✅ Updated **{item['name']}** price from "
                f"{item['cost']} {Config.CURRENCY_EMOJI} to "
                f"{new_price} {Config.CURRENCY_EMOJI}"
            )
        else:
            await interaction.followup.send("❌ Failed to update price.")

    @app_commands.command(name="userinfo", description="[ADMIN] View user information")
    @app_commands.describe(user="The user to view info for")
    @is_admin()
    async def user_info(self, interaction: discord.Interaction, user: discord.Member):
        """View detailed user information."""
        await interaction.response.defer()

        user_data = await user_db.get_user(user.id)

        if not user_data:
            await interaction.followup.send("❌ User not found in database.")
            return

        # Get purchase history
        purchases = await store_db.get_user_purchases(user.id, limit=5)
        coin_history = await user_db.get_coin_history(user.id, limit=5)

        embed = discord.Embed(
            title=f"👤 User Info: {user.display_name}", color=discord.Color.blue()
        )
        embed.add_field(name="Discord ID", value=str(user_data["discord_id"]), inline=True)
        embed.add_field(
            name="Balance",
            value=f"{user_data['phoenix_coins']} {Config.CURRENCY_EMOJI}",
            inline=True,
        )
        embed.add_field(name="Total Purchases", value=str(len(purchases)), inline=True)

        if user_data.get("steam_id"):
            embed.add_field(name="Steam ID", value=user_data["steam_id"], inline=True)

        # Recent purchases
        if purchases:
            purchase_text = "\n".join(
                [
                    f"• {p['item_name']} ({p['status']}) - {p['purchase_date']}"
                    for p in purchases[:5]
                ]
            )
            embed.add_field(name="Recent Purchases", value=purchase_text, inline=False)

        # Recent coin transactions
        if coin_history:
            coin_text = "\n".join(
                [
                    f"• {'+' if t['amount'] > 0 else ''}{t['amount']} {Config.CURRENCY_EMOJI} - {t['reason']}"
                    for t in coin_history[:5]
                ]
            )
            embed.add_field(name="Recent Coin Activity", value=coin_text, inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="setstatuschannel", description="[ADMIN] Set server status channel")
    @app_commands.describe(channel="The channel for server status updates")
    @is_admin()
    async def set_status_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Set the channel for server status updates."""
        await interaction.response.defer()

        # Update environment variable
        os.environ["STATUS_CHANNEL_ID"] = str(channel.id)
        Config.STATUS_CHANNEL_ID = channel.id

        # Save to .env file
        self._update_env_file("STATUS_CHANNEL_ID", str(channel.id))

        await interaction.followup.send(
            f"✅ Status channel set to {channel.mention}\n"
            f"Server status updates will now be posted there."
        )

    @app_commands.command(name="setchatchannel", description="[ADMIN] Set chat relay channel")
    @app_commands.describe(channel="The channel for in-game chat relay")
    @is_admin()
    async def set_chat_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Set the channel for chat relay."""
        await interaction.response.defer()

        os.environ["CHAT_CHANNEL_ID"] = str(channel.id)
        Config.CHAT_CHANNEL_ID = channel.id

        self._update_env_file("CHAT_CHANNEL_ID", str(channel.id))

        await interaction.followup.send(
            f"✅ Chat relay channel set to {channel.mention}\n"
            f"In-game chat will now be relayed there."
        )

    @app_commands.command(name="setadminlogchannel", description="[ADMIN] Set admin action log channel")
    @app_commands.describe(channel="The channel for admin action logs")
    @is_admin()
    async def set_admin_log_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Set the channel for admin action logging."""
        await interaction.response.defer()
        # Persist to database (authoritative)
        from bot.database import server_config_db

        guild_id = interaction.guild_id
        try:
            await server_config_db.create_or_update_server_config(
                guild_id, interaction.guild.name, admin_log_channel_id=channel.id
            )
        except Exception:
            # Fallback to env if DB write fails
            os.environ["ADMIN_LOG_CHANNEL_ID"] = str(channel.id)
            Config.ADMIN_LOG_CHANNEL_ID = channel.id
            self._update_env_file("ADMIN_LOG_CHANNEL_ID", str(channel.id))
            await interaction.followup.send(
                f"⚠️ Saved admin log channel to .env (DB write failed); channel set to {channel.mention}"
            )
            return

        # Keep Config in-memory in sync
        Config.ADMIN_LOG_CHANNEL_ID = channel.id

        await interaction.followup.send(
            f"✅ Admin log channel set to {channel.mention}\n"
            f"Stored in the database for this guild."
        )


    @app_commands.command(name="updateserver", description="[ADMIN] Update ARK server settings")
    @app_commands.describe(
        name="Server name to update",
        host="New host IP (leave empty to keep current)",
        rcon_port="New RCON port (0 to keep current)",
        rcon_password="New RCON password (leave empty to keep current)",
        chat_enabled="Enable/disable chat relay",
    )
    @is_admin()
    async def update_server(
        self,
        interaction: discord.Interaction,
        name: str,
        host: str = None,
        rcon_port: int = 0,
        rcon_password: str = None,
        chat_enabled: bool = None,
    ):
        """Update an existing ARK server configuration."""
        await interaction.response.defer(ephemeral=True)

        # Get current servers
        servers = Config.ARK_SERVERS.copy()

        # Find server
        server = next((s for s in servers if s["name"] == name), None)
        if not server:
            await interaction.followup.send(f"❌ Server '{name}' not found.", ephemeral=True)
            return

        # Update fields
        changes = []
        if host:
            server["host"] = host
            changes.append(f"Host → {host}")
        if rcon_port > 0:
            server["rcon_port"] = rcon_port
            changes.append(f"RCON Port → {rcon_port}")
        if rcon_password:
            server["rcon_password"] = rcon_password
            changes.append("RCON Password → ********")
        if chat_enabled is not None:
            server["chat_enabled"] = chat_enabled
            changes.append(f"Chat Relay → {'✅' if chat_enabled else '❌'}")

        if not changes:
            await interaction.followup.send("❌ No changes specified.", ephemeral=True)
            return

        # Update config
        servers_json = json.dumps(servers)
        os.environ["ARK_SERVERS"] = servers_json
        Config.ARK_SERVERS = servers

        # Save to .env file
        self._update_env_file("ARK_SERVERS", servers_json)

        await interaction.followup.send(
            f"✅ Server '{name}' updated!\n"
            + "\n".join(f"• {change}" for change in changes)
            + f"\n\n⚠️ **Restart the bot** for changes to take full effect.",
            ephemeral=True,
        )

    @app_commands.command(name="adminconfig", description="[ADMIN] View current bot configuration")
    @is_admin()
    async def view_config(self, interaction: discord.Interaction):
        """View current bot configuration."""
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(title="⚙️ Bot Configuration", color=discord.Color.gold())

        # Guild info
        embed.add_field(name="Guild ID", value=str(Config.GUILD_ID or "Not set"), inline=True)

        # Channels
        chat_channel = (
            self.bot.get_channel(Config.CHAT_CHANNEL_ID) if Config.CHAT_CHANNEL_ID else None
        )
        status_channel = (
            self.bot.get_channel(Config.STATUS_CHANNEL_ID) if Config.STATUS_CHANNEL_ID else None
        )

        embed.add_field(
            name="Chat Channel",
            value=chat_channel.mention if chat_channel else "Not set",
            inline=True,
        )
        embed.add_field(
            name="Status Channel",
            value=status_channel.mention if status_channel else "Not set",
            inline=True,
        )

        # Admin role
        if Config.ADMIN_ROLE_ID:
            admin_role = interaction.guild.get_role(Config.ADMIN_ROLE_ID)
            embed.add_field(
                name="Admin Role",
                value=admin_role.mention if admin_role else f"ID: {Config.ADMIN_ROLE_ID}",
                inline=True,
            )

        # Currency
        embed.add_field(
            name="Currency",
            value=f"{Config.CURRENCY_NAME} {Config.CURRENCY_EMOJI}",
            inline=True,
        )

        # Servers
        embed.add_field(name="ARK Servers", value=str(len(Config.ARK_SERVERS)), inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    _ALLOWED_ENV_KEYS = {
        "STATUS_CHANNEL_ID",
        "CHAT_CHANNEL_ID",
        "ADMIN_LOG_CHANNEL_ID",
        "ARK_SERVERS",
    }

    def _update_env_file(self, key: str, value: str):
        """Update .env file with new value. Only allows known safe keys."""
        if key not in self._ALLOWED_ENV_KEYS:
            logger.warning(f"Rejected .env write for disallowed key: {key}")
            return

        env_path = os.path.join(os.getcwd(), ".env")

        # Read current .env
        lines = []
        key_found = False

        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Update existing key
            for i, line in enumerate(lines):
                if line.startswith(f"{key}="):
                    lines[i] = f"{key}={value}\n"
                    key_found = True
                    break

        # Add new key if not found
        if not key_found:
            lines.append(f"{key}={value}\n")

        # Write back to .env
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        logger.info(f"Updated .env file: {key}")

    @app_commands.command(name="findmyeosid", description="📖 Guide to finding your ARK EOS ID")
    async def find_my_eos_id(self, interaction: discord.Interaction):
        """Show instructions for finding EOS ID."""
        embed = create_eos_id_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="delivercoins", description="[ADMIN] Deliver Phoenix Coins to a player in-game"
    )
    @app_commands.describe(
        user="The Discord user to deliver coins to",
        server="Server name where the player is located",
        quantity="Number of Phoenix Coins to deliver",
    )
    @is_admin()
    async def deliver_coins(
        self, interaction: discord.Interaction, user: discord.Member, server: str, quantity: int
    ):
        """Deliver Phoenix Coins to a player in-game."""
        await interaction.response.defer()

        if quantity <= 0:
            await interaction.followup.send(" Quantity must be positive.")
            return

        # Get player's EOS ID
        player = await players_db.get_player_by_discord_id(user.id)
        if not player:
            await interaction.followup.send(
                f" {user.mention} hasn't linked their account yet.\n"
                f"They need to use /linkplayer first."
            )
            return

        # Get RCON client for the server
        from bot.rcon.client import RCONManager

        rcon_manager = RCONManager(Config.ARK_SERVERS)
        client = rcon_manager.get_client(server)

        if not client:
            await interaction.followup.send(f" Server '{server}' not found in configuration.")
            return

        # Try to resolve player ID
        player_id = await client.resolve_player_id_by_eos(player["eos_id"])

        if player_id:
            # Player is online, deliver immediately
            success = await client.give_phoenix_coin(player_id, quantity)
            if success:
                # Update player tracking
                await players_db.update_player_id(user.id, player_id, server)

                await interaction.followup.send(
                    f" Delivered **{quantity}** Phoenix Coin(s) to {user.mention} on **{server}**!"
                )

                # Notify player in-game
                await client.broadcast_message(
                    f"{user.display_name} received {quantity} Phoenix Coin(s)!"
                )
            else:
                await interaction.followup.send(" Failed to deliver coins via RCON.")
        else:
            # Player is offline, queue delivery
            from bot.rcon.client import PHOENIX_COIN_BP

            await players_db.queue_delivery(user.id, server, PHOENIX_COIN_BP, quantity)
            await interaction.followup.send(
                f" {user.mention} is offline.\n"
                f"Queued **{quantity}** Phoenix Coin(s) for delivery when they join **{server}**."
            )

    @app_commands.command(
        name="setplayerid", description="[ADMIN] Manually set a player's PlayerID"
    )
    @app_commands.describe(
        user="The Discord user", server="Server name", player_id="The in-game PlayerID"
    )
    @is_admin()
    async def set_player_id(
        self, interaction: discord.Interaction, user: discord.Member, server: str, player_id: int
    ):
        """Manually set a player's PlayerID."""
        await players_db.update_player_id(user.id, player_id, server)
        await interaction.response.send_message(
            f" Set PlayerID for {user.mention} to {player_id} on **{server}**", ephemeral=True
        )

async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(Admin(bot))
