"""
Simple Give Item Modal - one dialog to give items without multiple confirmations.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput
import logging

from bot.database import players_db
from bot.utils import arkids_api

logger = logging.getLogger("SimpleGiveItem")


class SimpleGiveItemModal(Modal, title="📦 Give Item to Player"):
    """Single modal for giving items - player, item, quantity, quality all in one."""

    player_name = TextInput(
        label="Player Name or Discord @mention",
        placeholder="Type player name or @mention them",
        required=True,
        max_length=100,
    )

    item_name = TextInput(
        label="Item Name", placeholder="metal ingot, rifle, etc.", required=True, max_length=100
    )

    quantity = TextInput(
        label="Quantity", placeholder="Default: 1", required=False, default="1", max_length=10
    )

    quality = TextInput(
        label="Quality (0=Primitive, 1=Ramshackle, etc.)",
        placeholder="Default: 0",
        required=False,
        default="0",
        max_length=3,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Parse quantity and quality
            qty = int(self.quantity.value or "1")
            qual = int(self.quality.value or "0")

            # Resolve player: check if mention, then try DB lookup, then manual
            player_input = self.player_name.value.strip()
            eos_id = None
            discord_id = None
            player_display = player_input

            # Check if it's a mention like <@123456>
            if player_input.startswith("<@") and player_input.endswith(">"):
                discord_id = int(player_input.strip("<@!>"))
                player_data = await players_db.get_player_by_discord_id(discord_id)
                if player_data and player_data.get("eos_id"):
                    eos_id = player_data["eos_id"]
                    player_display = (
                        player_data.get("discord_display_name")
                        or player_data.get("discord_username")
                        or f"User {discord_id}"
                    )
                else:
                    await interaction.followup.send(
                        f"❌ <@{discord_id}> has not linked their EOS ID yet. Ask them to use `/players` → Link Account.",
                        ephemeral=True,
                    )
                    return
            else:
                # Try fuzzy match on linked players by display name or username
                linked_players = await players_db.get_linked_players()
                from difflib import SequenceMatcher

                best_match = None
                best_ratio = 0.0
                for p in linked_players:
                    for candidate in [p.get("discord_display_name"), p.get("discord_username")]:
                        if candidate:
                            ratio = SequenceMatcher(
                                None, player_input.lower(), candidate.lower()
                            ).ratio()
                            if ratio > best_ratio:
                                best_ratio = ratio
                                best_match = p

                if best_match and best_ratio >= 0.7:
                    eos_id = best_match["eos_id"]
                    discord_id = best_match["discord_user_id"]
                    player_display = best_match.get("discord_display_name") or best_match.get(
                        "discord_username"
                    )
                else:
                    # Fall back to manual entry (assume it's an EOS ID or Steam ID)
                    eos_id = player_input
                    player_display = f"Manual: {player_input[:20]}"

            # Search for item
            item_results = await arkids_api.search_items(self.item_name.value)
            if not item_results:
                await interaction.followup.send(
                    f"❌ No items found matching '{self.item_name.value}'. Try a different search term.",
                    ephemeral=True,
                )
                return

            # Take the first match
            item = item_results[0]
            item_display_name = item.get("name", "Unknown")
            item_blueprint = item.get("blueprint", item.get("path", ""))

            # Auto-detect server by checking RCON player lists
            from bot.cogs.server_monitor import ServerMonitor

            server_monitor = self.bot.get_cog("ServerMonitor")
            if not server_monitor or not server_monitor.rcon_manager:
                await interaction.followup.send(
                    "❌ Server monitor not available. Cannot detect player server.", ephemeral=True
                )
                return

            found_server = None
            for server_name, client in server_monitor.rcon_manager.clients.items():
                try:
                    players_online = await client.get_player_list()
                    for p in players_online:
                        p_eos = p.get("eos_id") or p.get("EOSID") or p.get("id")
                        if p_eos and str(p_eos).strip() == str(eos_id).strip():
                            found_server = server_name
                            break
                    if found_server:
                        break
                except Exception as e:
                    logger.debug(f"Could not check {server_name}: {e}")

            if not found_server:
                await interaction.followup.send(
                    f"❌ Player `{player_display}` (EOS: `{eos_id[:20]}...`) not found online on any server.",
                    ephemeral=True,
                )
                return

            # Execute give command
            client = server_monitor.rcon_manager.clients[found_server]
            command = f'GiveItemToPlayer "{eos_id}" "{item_blueprint}" {qty} {qual} 0'
            response = await client.send_command(command)

            # Build success embed
            embed = discord.Embed(title="✅ Item Given Successfully", color=discord.Color.green())
            embed.add_field(name="Server", value=found_server, inline=False)
            embed.add_field(name="Player", value=player_display, inline=True)
            embed.add_field(name="Item", value=item_display_name, inline=True)
            embed.add_field(name="Quantity", value=str(qty), inline=True)
            embed.add_field(name="Quality", value=str(qual), inline=True)
            if response:
                embed.add_field(name="RCON Response", value=f"```{response[:200]}```", inline=False)
            embed.set_footer(text=f"Executed by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(
                f"{interaction.user} gave {qty}x {item_display_name} (q{qual}) to {player_display} on {found_server}"
            )

        except ValueError:
            await interaction.followup.send(
                "❌ Invalid quantity or quality. Please enter numbers only.", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in SimpleGiveItemModal: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error giving item: {str(e)}", ephemeral=True)


class SimpleGiveItemCog(commands.Cog):
    """Cog to provide a streamlined /giveitem command using a single modal."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="giveitem_simple", description="Give an item to a player (one-step modal)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def giveitem_simple(self, interaction: discord.Interaction):
        """Open a single modal to give items without multi-step confirmations."""
        modal = SimpleGiveItemModal(self.bot)
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot):
    await bot.add_cog(SimpleGiveItemCog(bot))
