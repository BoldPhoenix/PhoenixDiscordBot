"""
Enhanced Give Item Modal with player autocomplete, item search, and quality dropdown.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button, Select
import logging
from typing import Optional, List, Dict, Any

from bot.database import players_db, store_db
from bot.utils.arkids_api import get_arkids_client
from bot.utils.validation import validate_rcon_input

logger = logging.getLogger("EnhancedGiveItem")


# Quality mappings
QUALITY_TIERS = {
    "0": "Primitive",
    "1": "Ramshackle",
    "2": "Apprentice",
    "3": "Journeyman",
    "4": "Mastercraft",
    "5": "Ascendant",
}


class ItemSearchView(View):
    """View for item search results with pagination."""

    def __init__(self, items: List[Any], parent_interaction: discord.Interaction, callback):
        super().__init__(timeout=None)
        self.items = items  # List of ArkItem objects
        self.parent_interaction = parent_interaction
        self.selected_item: Optional[Any] = None
        self.callback = callback
        self.page = 0
        self.items_per_page = 10

        self._update_buttons()

    def _update_buttons(self):
        """Update button states based on current page."""
        self.clear_items()

        # Add item selection dropdown
        start_idx = self.page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.items))
        page_items = self.items[start_idx:end_idx]

        options = []
        for idx, item in enumerate(page_items):
            label = item.name[:100]
            # Truncate label if too long
            if len(label) > 97:
                label = label[:97] + "..."
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(start_idx + idx),
                    description=item.blueprint[:100] if item.blueprint else None,
                )
            )

        if options:
            select = Select(
                placeholder=f"Choose an item (Page {self.page + 1})",
                options=options,
                custom_id="item_select",
            )
            select.callback = self._item_selected
            self.add_item(select)

        # Pagination buttons
        if self.page > 0:
            prev_btn = Button(
                label="◀ Previous", style=discord.ButtonStyle.secondary, custom_id="prev"
            )
            prev_btn.callback = self._prev_page
            self.add_item(prev_btn)

        if end_idx < len(self.items):
            next_btn = Button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="next")
            next_btn.callback = self._next_page
            self.add_item(next_btn)

        # Cancel button
        cancel_btn = Button(label="❌ Cancel", style=discord.ButtonStyle.danger, custom_id="cancel")
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    async def _item_selected(self, interaction: discord.Interaction):
        """Handle item selection."""
        selected_idx = int(interaction.data["values"][0])
        self.selected_item = self.items[selected_idx]

        await interaction.response.edit_message(
            content=f"✅ Selected: **{self.selected_item.name}**\n\nYou can now submit the form!",
            view=None,
        )
        self.stop()

        # Call the callback to update the parent modal
        if self.callback:
            await self.callback(self.selected_item)

    async def _prev_page(self, interaction: discord.Interaction):
        """Go to previous page."""
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(view=self)

    async def _next_page(self, interaction: discord.Interaction):
        """Go to next page."""
        max_pages = (len(self.items) + self.items_per_page - 1) // self.items_per_page
        self.page = min(max_pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(view=self)

    async def _cancel(self, interaction: discord.Interaction):
        """Cancel item selection."""
        await interaction.response.edit_message(content="❌ Item search cancelled.", view=None)
        self.stop()


class ItemSearchModal(Modal, title="🔍 Search for Item"):
    """Modal for searching items."""

    search_query = TextInput(
        label="Item Name",
        placeholder="metal ingot, rifle, saddle, etc.",
        required=True,
        max_length=100,
    )

    def __init__(self, parent_modal):
        super().__init__()
        self.parent_modal = parent_modal
        self.selected_item: Optional[Any] = None

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            query = self.search_query.value.strip()

            # Search arkids API
            arkids_client = get_arkids_client()
            api_results = await arkids_client.search_items(query)

            if not api_results:
                await interaction.followup.send(
                    f"❌ No items found matching '{query}'. Try a different search term.",
                    ephemeral=True,
                )
                return

            # Show selection view
            embed = discord.Embed(
                title=f"🔍 Search Results: {query}",
                description=f"Found {len(api_results)} item(s). Select one:",
                color=discord.Color.blue(),
            )

            async def update_parent(selected_item):
                """Update parent modal with selected item."""
                self.parent_modal.selected_item_name = selected_item.name
                self.parent_modal.selected_item_blueprint = selected_item.blueprint

            view = ItemSearchView(api_results, interaction, update_parent)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

            # Wait for selection
            await view.wait()
            self.selected_item = view.selected_item

        except Exception as e:
            logger.error(f"Error searching items: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error searching items: {str(e)}", ephemeral=True)


class ItemCatalogView(View):
    """Category-driven item catalog with pagination. Writes selection back to a parent GiveItemPanelView."""

    def __init__(self, parent_view: "GiveItemPanelView"):
        super().__init__(timeout=None)
        self.parent_view = parent_view
        self.mode = "categories"  # or "items"
        self.categories: list[str] = []
        self.category_page = 0
        self.items: list[dict[str, Any]] = []
        self.items_page = 0
        self.items_per_page = 10

    async def _load_categories(self):
        try:
            cats = await store_db.get_categories()
            self.categories = cats or []
        except Exception as e:
            logger.error(f"Catalog: failed to load categories: {e}", exc_info=True)
            self.categories = []

    def _render_categories_embed(self) -> discord.Embed:
        start = self.category_page * 4
        page_cats = self.categories[start : start + 4]
        e = discord.Embed(title="RCON Shop", color=discord.Color.teal())
        desc = "Categories\n\n"
        for idx, cat in enumerate(page_cats, start=1):
            # Count items per category if known
            desc += f"{idx} {cat}\n"
        if not page_cats:
            desc += "No categories configured."
        e.description = desc
        e.set_footer(text=f"Page: {self.category_page + 1}/{max(1, (len(self.categories)+3)//4)}")
        return e

    def _render_items_embed(self) -> discord.Embed:
        start = self.items_page * self.items_per_page
        page_items = self.items[start : start + self.items_per_page]
        e = discord.Embed(title="RCON Shop", color=discord.Color.teal())
        e.description = "Items\n\n" + (
            "\n".join([f"{i+1}. {it.get('name','?')}" for i, it in enumerate(page_items)])
            or "No items"
        )
        e.set_footer(
            text=f"Page: {self.items_page + 1}/{max(1, (len(self.items)+self.items_per_page-1)//self.items_per_page)}"
        )
        return e

    def _rebuild_controls(self):
        self.clear_items()
        if self.mode == "categories":
            # Nav buttons
            if self.category_page > 0:
                prev = Button(label="◀", style=discord.ButtonStyle.primary)
                prev.callback = self._prev_categories
                self.add_item(prev)
            if (self.category_page + 1) * 4 < len(self.categories):
                nxt = Button(label="▶", style=discord.ButtonStyle.primary)
                nxt.callback = self._next_categories
                self.add_item(nxt)
            # Numbered category selects (up to 4)
            for i in range(1, 5):
                btn = Button(label=str(i), style=discord.ButtonStyle.success)

                async def make_cb(interaction: discord.Interaction, index=i):
                    await self._select_category(interaction, index)

                btn.callback = make_cb
                self.add_item(btn)
            # Close
            close = Button(label="✖", style=discord.ButtonStyle.secondary)
            close.callback = self._close
            self.add_item(close)
        else:
            # Items view controls
            if self.items_page > 0:
                prev = Button(label="◀", style=discord.ButtonStyle.primary)
                prev.callback = self._prev_items
                self.add_item(prev)
            if (self.items_page + 1) * self.items_per_page < len(self.items):
                nxt = Button(label="▶", style=discord.ButtonStyle.primary)
                nxt.callback = self._next_items
                self.add_item(nxt)
            # Dropdown for items on page
            start = self.items_page * self.items_per_page
            page_items = self.items[start : start + self.items_per_page]
            options = [
                discord.SelectOption(
                    label=(it.get("name") or "Unnamed")[:100], value=str(start + idx)
                )
                for idx, it in enumerate(page_items)
            ]
            if options:
                select = Select(placeholder="Select an item", options=options)
                select.callback = self._item_selected
                self.add_item(select)
            back = Button(label="⬅ Categories", style=discord.ButtonStyle.secondary)
            back.callback = self._back_to_categories
            self.add_item(back)
            close = Button(label="✖", style=discord.ButtonStyle.secondary)
            close.callback = self._close
            self.add_item(close)

    async def _prev_categories(self, interaction: discord.Interaction):
        self.category_page = max(0, self.category_page - 1)
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_categories_embed(), view=self)

    async def _next_categories(self, interaction: discord.Interaction):
        max_pages = (len(self.categories) + 3) // 4
        self.category_page = min(max_pages - 1, self.category_page + 1)
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_categories_embed(), view=self)

    async def _select_category(self, interaction: discord.Interaction, index: int):
        start = self.category_page * 4
        cat_idx = start + (index - 1)
        if cat_idx < 0 or cat_idx >= len(self.categories):
            return
        category = self.categories[cat_idx]
        try:
            self.items = await store_db.get_all_items(category=category, enabled_only=True)
        except Exception as e:
            logger.error(f"Catalog: load items failed: {e}")
            self.items = []
        self.items_page = 0
        self.mode = "items"
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_items_embed(), view=self)

    async def _prev_items(self, interaction: discord.Interaction):
        self.items_page = max(0, self.items_page - 1)
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_items_embed(), view=self)

    async def _next_items(self, interaction: discord.Interaction):
        max_pages = (len(self.items) + self.items_per_page - 1) // self.items_per_page
        self.items_page = min(max_pages - 1, self.items_page + 1)
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_items_embed(), view=self)

    async def _item_selected(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        sel = self.items[idx]
        # Attempt to resolve blueprint via arkids search on item name
        name = sel.get("name") or ""
        blueprint = None
        try:
            if name:
                arkids_client = get_arkids_client()
                results = await arkids_client.search_items(name)
                if results:
                    blueprint = results[0].blueprint
        except Exception as e:
            logger.debug(f"Catalog: arkids search failed: {e}")
        if blueprint:
            self.parent_view.selected_item_name = name
            self.parent_view.selected_item_blueprint = blueprint
            self.parent_view.item_text = name
            await interaction.response.edit_message(content=f"✅ Selected: **{name}**", view=None)
            await self.parent_view.refresh_message(interaction, notify_changed=True)
        else:
            await interaction.response.edit_message(
                content=f"❌ Could not resolve blueprint for '{name}'. Try Search.", view=None
            )

    async def _back_to_categories(self, interaction: discord.Interaction):
        self.mode = "categories"
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_categories_embed(), view=self)

    async def _close(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=None)

    async def start(self, interaction: discord.Interaction):
        await self._load_categories()
        self.mode = "categories"
        self.category_page = 0
        self._rebuild_controls()
        await interaction.response.send_message(
            embed=self._render_categories_embed(), view=self, ephemeral=True
        )


class EnhancedGiveItemView(View):
    """View with item search button that appears in the modal message."""

    def __init__(self, parent_modal, bot: commands.Bot):
        super().__init__(timeout=None)
        self.parent_modal = parent_modal
        self.bot = bot

    @discord.ui.button(label="🔍 Search Items", style=discord.ButtonStyle.primary)
    async def search_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open item search modal."""
        modal = ItemSearchModal(self.parent_modal)
        await interaction.response.send_modal(modal)


class EnhancedGiveItemModal(Modal, title="📦 Give Item to Player"):
    """Enhanced modal with player selection and item search."""

    item_name = TextInput(
        label="Item Name (use Search button below)",
        placeholder="Click 🔍 Search Items button after submitting",
        required=True,
        max_length=100,
    )

    quantity = TextInput(
        label="Quantity", placeholder="Default: 1", required=False, default="1", max_length=10
    )

    quality = TextInput(
        label="Quality (0-5: Primitive to Ascendant)",
        placeholder="0=Primitive, 1=Ramshackle, 2=Apprentice, 3=Journeyman, 4=Mastercraft, 5=Ascendant",
        required=False,
        default="0",
        max_length=1,
    )

    def __init__(self, bot: commands.Bot, player: discord.Member = None, player_data: dict = None):
        super().__init__()
        self.bot = bot
        self.player = player
        self.player_data = player_data
        self.selected_item_name: Optional[str] = None
        self.selected_item_blueprint: Optional[str] = None

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Parse quantity and quality
            qty = int(self.quantity.value or "1")
            qual = int(self.quality.value or "0")

            # Validate quality
            if qual < 0 or qual > 5:
                await interaction.followup.send(
                    f"❌ Invalid quality tier: {qual}. Must be 0-5 (0=Primitive, 5=Ascendant).",
                    ephemeral=True,
                )
                return

            quality_name = QUALITY_TIERS.get(str(qual), "Unknown")

            # Use pre-filled player data
            if not self.player_data:
                await interaction.followup.send(
                    "❌ Player data not available. Please try again.", ephemeral=True
                )
                return

            eos_id = self.player_data["eos_id"]
            specimen_id = self.player_data.get("specimen_id")
            discord_id = self.player.id
            player_display = self.player.display_name

            # Get item blueprint - use selected item if available, otherwise search
            if self.selected_item_blueprint:
                item_display_name = self.selected_item_name
                item_blueprint = self.selected_item_blueprint
            else:
                # Search for item
                arkids_client = get_arkids_client()
                item_results = await arkids_client.search_items(self.item_name.value)
                if not item_results:
                    await interaction.followup.send(
                        f"❌ No items found matching '{self.item_name.value}'. Use the 🔍 Search Items button.",
                        ephemeral=True,
                    )
                    return
                item = item_results[0]
                item_display_name = item.name
                item_blueprint = item.blueprint

            if not item_blueprint:
                await interaction.followup.send(
                    f"❌ No blueprint found for '{item_display_name}'. Cannot give item.",
                    ephemeral=True,
                )
                return

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
                        p_eos = p.get("steam_id", "").strip()
                        p_specimen = p.get("specimen_id", "").strip()

                        # Check by specimen ID first (most reliable), then EOS ID
                        if specimen_id and p_specimen == str(specimen_id).strip():
                            found_server = server_name
                            break
                        elif p_eos == str(eos_id).strip():
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

            # Validate player identifier before building RCON command
            player_identifier = specimen_id or eos_id
            if player_identifier and not validate_rcon_input(str(player_identifier)):
                await interaction.followup.send(
                    "❌ Invalid player identifier format.", ephemeral=True,
                )
                return

            # Execute give command - use specimen ID if available, otherwise EOS ID
            client = server_monitor.rcon_manager.clients[found_server]
            if specimen_id:
                # Use numeric specimen ID (preferred method)
                command = f'GiveItemToPlayer {specimen_id} "{item_blueprint}" {qty} {qual} 0'
            else:
                # Fallback to EOS ID (may not work on all servers)
                command = f'GiveItemToPlayer "{eos_id}" "{item_blueprint}" {qty} {qual} 0'
            response = await client.execute_command(command)

            # Build success embed
            embed = discord.Embed(title="✅ Item Given Successfully", color=discord.Color.green())
            embed.add_field(name="Server", value=found_server, inline=False)
            embed.add_field(name="Player", value=f"{player_display}", inline=True)
            embed.add_field(name="Item", value=item_display_name, inline=True)
            embed.add_field(name="Quantity", value=str(qty), inline=True)
            embed.add_field(name="Quality", value=f"{qual} ({quality_name})", inline=True)
            if not specimen_id:
                embed.add_field(
                    name="⚠️ Warning",
                    value="Player has no specimen ID linked. Item delivery may fail. Ask player to check their implant and use `/register_specimen`.",
                    inline=False,
                )
            if response:
                embed.add_field(name="RCON Response", value=f"```{response[:200]}```", inline=False)
            embed.set_footer(text=f"Executed by {interaction.user.display_name}")

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(
                f"{interaction.user} gave {qty}x {item_display_name} (q{qual}/{quality_name}) to {player_display} on {found_server}"
            )

        except ValueError:
            await interaction.followup.send(
                "❌ Invalid quantity or quality. Please enter numbers only.", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in EnhancedGiveItemModal: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error giving item: {str(e)}", ephemeral=True)


# -------- New: View-based Give Item panel (dropdown players + inline search) --------


class LinkedPlayersSelect(Select):
    """Dropdown of players linked to EOS (from DB)."""

    def __init__(self, options: list[discord.SelectOption]):
        super().__init__(
            placeholder="Select a linked player...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="linked_players_select",
        )


class QualitySelect(Select):
    def __init__(self, default_value: str = "0"):
        options = [
            discord.SelectOption(
                label=f"{tier} - {name}", value=tier, default=(tier == default_value)
            )
            for tier, name in QUALITY_TIERS.items()
        ]
        super().__init__(
            placeholder="Select quality (0-5)",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="quality_select",
        )


class QuantitySelect(Select):
    def __init__(self, default_value: str = "1"):
        qty_options = ["1", "5", "10", "25", "50", "100", "Custom..."]
        options = [
            discord.SelectOption(label=q, value=q, default=(q == default_value))
            for q in qty_options
        ]
        super().__init__(
            placeholder="Select quantity",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="quantity_select",
        )


class EditItemTextModal(Modal, title="✏ Edit Item Text"):
    item_text = TextInput(
        label="Item name to search",
        placeholder="rifle, metal ingot, saddle...",
        required=True,
        max_length=100,
    )

    def __init__(self, parent_view: "GiveItemPanelView"):
        super().__init__()
        self.parent_view = parent_view
        if parent_view.item_text:
            self.item_text.default = parent_view.item_text

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.item_text = self.item_text.value.strip()
        await self.parent_view.refresh_message(interaction, notify_changed=True)


class ItemSearchModalForPanel(ItemSearchModal):
    """Reuse item search but write back into panel instead of modal."""

    def __init__(self, parent_view: "GiveItemPanelView"):
        # Initialize with a faux parent modal interface used by ItemSearchModal
        # We'll provide attributes that ItemSearchModal expects to set.
        class ParentShim:
            selected_item_name: Optional[str] = None
            selected_item_blueprint: Optional[str] = None

        self._shim = ParentShim()
        super().__init__(parent_modal=self._shim)
        self.parent_view = parent_view
        if parent_view.item_text:
            self.search_query.default = parent_view.item_text

    async def on_submit(self, interaction: discord.Interaction):
        await super().on_submit(interaction)
        # After selection, propagate values into the panel view
        if getattr(self._shim, "selected_item_blueprint", None):
            self.parent_view.selected_item_name = self._shim.selected_item_name
            self.parent_view.selected_item_blueprint = self._shim.selected_item_blueprint
            # Also update item_text to the chosen item name
            self.parent_view.item_text = self._shim.selected_item_name
            await self.parent_view.refresh_message(interaction, notify_changed=True)


class GiveItemPanelView(View):
    """Non-modal Give Item panel with linked players dropdown and item search button."""

    def __init__(self, bot: commands.Bot, author: discord.User):
        super().__init__(timeout=None)
        self.bot = bot
        self.author = author
        # State
        self.selected_discord_user_id: Optional[int] = None
        self.selected_item_name: Optional[str] = None
        self.selected_item_blueprint: Optional[str] = None
        self.item_text: str = ""
        self.quantity: int = 1
        self.quality: int = 0
        # Dynamic components
        self.players_select: Optional[LinkedPlayersSelect] = None
        self.quality_select: Optional[QualitySelect] = None
        self.quantity_select: Optional[QuantitySelect] = None

    async def load_linked_players(self):
        players = []
        try:
            players = await players_db.get_linked_players()
            logger.info(f"GiveItemPanel: loaded {len(players)} linked players")
        except Exception as e:
            logger.error(f"GiveItemPanel: error loading linked players: {e}", exc_info=True)

        # Build list with names, fetching missing ones
        player_options = []
        for p in players:
            # If names are missing, try to fetch from Discord
            display_name = p.get("discord_display_name")
            username = p.get("discord_username")
            discord_id = p.get("discord_user_id")

            if (not display_name or not username) and discord_id:
                try:
                    logger.info(f"Attempting to fetch Discord user {discord_id}")
                    user = await self.bot.fetch_user(discord_id)
                    if user:
                        display_name = user.display_name or user.name
                        username = user.name
                        # Update database with fetched names
                        await players_db.update_player_names(discord_id, username, display_name)
                        logger.info(f"Fetched and updated names for user {discord_id}: {username}")
                    else:
                        logger.warning(f"fetch_user returned None for {discord_id}")
                except Exception as e:
                    logger.error(f"Could not fetch user {discord_id}: {e}", exc_info=True)

            label = (display_name or username or str(discord_id))[:100]
            description = f"EOS {str(p.get('eos_id'))[:24]}..." if p.get("eos_id") else None
            value_str = str(discord_id) if discord_id is not None else None
            if not value_str:
                continue

            player_options.append(
                {
                    "label": label,
                    "value": value_str,
                    "description": description,
                    "sort_key": (display_name or username or str(discord_id)).lower(),
                }
            )

        # Sort alphabetically by display name/username
        player_options.sort(key=lambda x: x["sort_key"])

        # Limit to 25 options per Discord constraints
        options: list[discord.SelectOption] = []
        for p in player_options[:25]:
            options.append(
                discord.SelectOption(
                    label=p["label"], value=p["value"], description=p["description"]
                )
            )

        if options:
            self.players_select = LinkedPlayersSelect(options)
            self.players_select.callback = self._on_player_selected
            self.add_item(self.players_select)
        else:
            # Fallback: Discord built-in user selector
            fallback = discord.ui.UserSelect(
                placeholder="Select a player (fallback)", custom_id="fallback_user_select"
            )

            async def _fallback_cb(interaction: discord.Interaction):
                try:
                    uid = int(interaction.data["values"][0])
                    self.selected_discord_user_id = uid
                except Exception:
                    self.selected_discord_user_id = None
                await self.refresh_message(interaction)

            fallback.callback = _fallback_cb
            self.add_item(fallback)

        # Quantity and quality controls
        self.quality_select = QualitySelect(default_value=str(self.quality))
        self.quality_select.callback = self._on_quality_selected
        self.add_item(self.quality_select)

        self.quantity_select = QuantitySelect(default_value=str(self.quantity))
        self.quantity_select.callback = self._on_quantity_selected
        self.add_item(self.quantity_select)

        # Row of buttons: Edit Item, Search, Submit
        edit_btn = Button(label="✏ Edit Item", style=discord.ButtonStyle.secondary)
        edit_btn.callback = self._open_edit_item
        self.add_item(edit_btn)

        search_btn = Button(label="🔍 Search Items", style=discord.ButtonStyle.primary)
        search_btn.callback = self._open_search
        self.add_item(search_btn)

        catalog_btn = Button(label="🛒 Catalog", style=discord.ButtonStyle.primary)
        catalog_btn.callback = self._open_catalog
        self.add_item(catalog_btn)

        submit_btn = Button(label="Submit", style=discord.ButtonStyle.success)
        submit_btn.callback = self._submit
        self.add_item(submit_btn)

    def create_embed(self) -> discord.Embed:
        e = discord.Embed(title="📦 Give Item", color=discord.Color.blurple())
        e.add_field(
            name="Player",
            value=(f"<@{self.selected_discord_user_id}>" if self.selected_discord_user_id else "—"),
            inline=False,
        )
        e.add_field(
            name="Item", value=(self.selected_item_name or (self.item_text or "—")), inline=False
        )
        e.add_field(name="Quantity", value=str(self.quantity), inline=True)
        qual_name = QUALITY_TIERS.get(str(self.quality), "?")
        e.add_field(name="Quality", value=f"{self.quality} ({qual_name})", inline=True)
        e.set_footer(text=f"Requested by {self.author.display_name}")
        return e

    async def refresh_message(self, interaction: discord.Interaction, notify_changed: bool = False):
        # Re-render the view to reflect any default changes
        # Need to rebuild selects to reflect default values
        self.clear_items()
        if self.players_select:
            # rebuild linked players select preserving options
            opts = self.players_select.options
            self.players_select = LinkedPlayersSelect(opts)
            self.players_select.callback = self._on_player_selected
            self.add_item(self.players_select)
        self.quality_select = QualitySelect(default_value=str(self.quality))
        self.quality_select.callback = self._on_quality_selected
        self.add_item(self.quality_select)
        self.quantity_select = QuantitySelect(default_value=str(self.quantity))
        self.quantity_select.callback = self._on_quantity_selected
        self.add_item(self.quantity_select)

        edit_btn = Button(label="✏ Edit Item", style=discord.ButtonStyle.secondary)
        edit_btn.callback = self._open_edit_item
        self.add_item(edit_btn)
        search_btn = Button(label="🔍 Search Items", style=discord.ButtonStyle.primary)
        search_btn.callback = self._open_search
        self.add_item(search_btn)
        catalog_btn = Button(label="🛒 Catalog", style=discord.ButtonStyle.primary)
        catalog_btn.callback = self._open_catalog
        self.add_item(catalog_btn)
        submit_btn = Button(label="Submit", style=discord.ButtonStyle.success)
        submit_btn.callback = self._submit
        self.add_item(submit_btn)

        content = "✅ Updated selection." if notify_changed else None
        try:
            # Prefer editing the component message directly
            if not interaction.response.is_done():
                await interaction.response.edit_message(
                    content=content, embed=self.create_embed(), view=self
                )
            elif interaction.message:
                await interaction.message.edit(
                    content=content, embed=self.create_embed(), view=self
                )
            else:
                await interaction.edit_original_response(
                    content=content, embed=self.create_embed(), view=self
                )
        except Exception as e:
            logger.debug(f"refresh_message fallback due to {e}")
            # Final fallback: try original response without content change
            try:
                await interaction.edit_original_response(embed=self.create_embed(), view=self)
            except Exception as e2:
                logger.error(f"Failed to refresh GiveItemPanel message: {e2}")

    async def _on_player_selected(self, interaction: discord.Interaction):
        try:
            self.selected_discord_user_id = int(interaction.data["values"][0])
        except Exception:
            self.selected_discord_user_id = None
        await self.refresh_message(interaction)

    async def _on_quality_selected(self, interaction: discord.Interaction):
        self.quality = int(interaction.data["values"][0] if interaction.data.get("values") else 0)
        await self.refresh_message(interaction)

    async def _on_quantity_selected(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        if val == "Custom...":
            # Open modal to capture custom quantity
            class QtyModal(Modal, title="Set Quantity"):
                q = TextInput(label="Quantity", placeholder="e.g., 37", required=True, max_length=6)

                def __init__(self, view_ref: "GiveItemPanelView"):
                    super().__init__()
                    self.view_ref = view_ref

                async def on_submit(self, inter: discord.Interaction):
                    try:
                        self.view_ref.quantity = max(1, int(self.q.value))
                    except Exception:
                        self.view_ref.quantity = 1
                    await self.view_ref.refresh_message(inter, notify_changed=True)

            await interaction.response.send_modal(QtyModal(self))
            return
        else:
            try:
                self.quantity = max(1, int(val))
            except Exception:
                self.quantity = 1
        await self.refresh_message(interaction)

    async def _open_edit_item(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(EditItemTextModal(self))
        except Exception as e:
            logger.error("Edit Item modal failed: %s", e, exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Could not open edit modal. Please try again.", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ Could not open edit modal. Please try again.", ephemeral=True
                    )
            except Exception:
                pass

    async def _open_search(self, interaction: discord.Interaction):
        # Use current item_text as seed; results will write back
        modal = ItemSearchModalForPanel(self)
        try:
            await interaction.response.send_modal(modal)
        except Exception as e:
            logger.error(f"Search Items modal failed: {e}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Could not open search modal. Please try again.", ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ Could not open search modal. Please try again.", ephemeral=True
                    )
            except Exception:
                pass

    async def _open_catalog(self, interaction: discord.Interaction):
        view = ItemCatalogView(self)
        await view.start(interaction)

    async def _submit(self, interaction: discord.Interaction):
        # Defer immediately to prevent timeout during RCON queries
        await interaction.response.defer(ephemeral=True)

        # Validate selections
        if not self.selected_discord_user_id:
            await interaction.followup.send("❌ Please select a player.", ephemeral=True)
            return
        if not self.selected_item_blueprint:
            # If no blueprint yet but we have text, try an automatic search pick first
            if self.item_text:
                try:
                    arkids_client = get_arkids_client()
                    item_results = await arkids_client.search_items(self.item_text)
                    if item_results:
                        item = item_results[0]
                        self.selected_item_name = item.name
                        self.selected_item_blueprint = item.blueprint
                except Exception as e:
                    logger.error(f"Auto-search on submit failed: {e}")
        if not self.selected_item_blueprint:
            await interaction.followup.send(
                "❌ Please choose an item (use Search).", ephemeral=True
            )
            return

        # Retrieve EOS for selected Discord user
        player = await players_db.get_player_by_discord_id(self.selected_discord_user_id)
        if not player or not player.get("eos_id"):
            await interaction.followup.send(
                "❌ Selected user is not linked to an EOS ID.", ephemeral=True
            )
            return

        eos_id = player["eos_id"]
        item_blueprint = self.selected_item_blueprint

        # Auto-detect server (reuse logic)
        from bot.cogs.server_monitor import ServerMonitor

        server_monitor = self.bot.get_cog("ServerMonitor")
        if not server_monitor or not server_monitor.rcon_manager:
            await interaction.followup.send("❌ Server monitor not available.", ephemeral=True)
            return

        found_server = None
        for server_name, client in server_monitor.rcon_manager.clients.items():
            try:
                players_online = await client.get_player_list()
                # Diagnostics: log sample of identifiers returned
                sample = [
                    {
                        "name": p.get("name"),
                        "steam_id": p.get("steam_id"),
                        "eos_id": p.get("eos_id"),
                        "id": p.get("id"),
                    }
                    for p in players_online[:5]
                ]
                logger.info(f"GiveItemPanel: {server_name} online sample: {sample}")
                # Normalize EOS: strip leading zeros for comparison (DB may store with extra leading 0)
                target = str(eos_id).strip().lstrip("0")
                for p in players_online:
                    ids_to_check = [
                        str(p.get("steam_id", "")).strip().lstrip("0"),
                        str(p.get("eos_id", "")).strip().lstrip("0"),
                        str(p.get("id", "")).strip().lstrip("0"),
                    ]
                    if target and target in ids_to_check:
                        found_server = server_name
                        logger.info(
                            f"GiveItemPanel: Matched player on {server_name} - DB EOS: {eos_id}, RCON returned: {p.get('steam_id')}"
                        )
                        break
                if found_server:
                    break
            except Exception as e:
                logger.debug(f"Could not check {server_name}: {e}")

        if not found_server:
            # Fallback: allow manual server selection and proceed
            class ServerSelectView(View):
                def __init__(self, outer: "GiveItemPanelView", servers: list[str], eos: str):
                    super().__init__(timeout=None)
                    self.outer = outer
                    self.eos = eos
                    options = [discord.SelectOption(label=s, value=s) for s in servers]
                    select = Select(placeholder="Select server", options=options)

                    async def _on_select(inter: discord.Interaction):
                        server_name = inter.data["values"][0]
                        try:
                            client = self.outer.bot.get_cog("ServerMonitor").rcon_manager.clients[
                                server_name
                            ]
                            cmd = f'GiveItemToPlayer "{self.eos}" "{self.outer.selected_item_blueprint}" {self.outer.quantity} {self.outer.quality} 0'
                            resp = await client.execute_command(cmd)
                            emb = discord.Embed(
                                title="✅ Item Given Successfully", color=discord.Color.green()
                            )
                            emb.add_field(name="Server", value=server_name, inline=False)
                            emb.add_field(
                                name="Player",
                                value=f"<@{self.outer.selected_discord_user_id}>",
                                inline=True,
                            )
                            emb.add_field(
                                name="Item",
                                value=self.outer.selected_item_name or self.outer.item_text,
                                inline=True,
                            )
                            emb.add_field(
                                name="Quantity", value=str(self.outer.quantity), inline=True
                            )
                            qn = QUALITY_TIERS.get(str(self.outer.quality), "?")
                            emb.add_field(
                                name="Quality", value=f"{self.outer.quality} ({qn})", inline=True
                            )
                            if resp:
                                emb.add_field(
                                    name="RCON Response",
                                    value=f"```{(resp or '')[:200]}```",
                                    inline=False,
                                )
                            emb.set_footer(text=f"Executed by {inter.user.display_name}")
                            await inter.response.edit_message(embed=emb, view=None)
                            logger.info(
                                f"Manual server give: {inter.user} → {self.outer.selected_discord_user_id} on {server_name}"
                            )
                        except Exception as e:
                            await inter.response.edit_message(
                                content=f"❌ Failed on {server_name}: {e}", view=None
                            )

                    select.callback = _on_select
                    self.add_item(select)

                    cancel = Button(label="✖ Cancel", style=discord.ButtonStyle.danger)

                    async def _cancel(inter: discord.Interaction):
                        await inter.response.edit_message(content="Cancelled.", view=None)

                    cancel.callback = _cancel
                    self.add_item(cancel)

            servers = list(server_monitor.rcon_manager.clients.keys())
            fallback_view = ServerSelectView(self, servers, eos_id)
            await interaction.followup.send(
                "Player not detected online. Choose a server to proceed:",
                view=fallback_view,
                ephemeral=True,
            )
            return

        # Execute give command
        client = server_monitor.rcon_manager.clients[found_server]
        command = f'GiveItemToPlayer "{eos_id}" "{item_blueprint}" {self.quantity} {self.quality} 0'
        response = await client.execute_command(command)

        embed = discord.Embed(title="✅ Item Given Successfully", color=discord.Color.green())
        embed.add_field(name="Server", value=found_server, inline=False)
        embed.add_field(name="Player", value=f"<@{self.selected_discord_user_id}>", inline=True)
        embed.add_field(name="Item", value=self.selected_item_name or self.item_text, inline=True)
        embed.add_field(name="Quantity", value=str(self.quantity), inline=True)
        qual_name = QUALITY_TIERS.get(str(self.quality), "?")
        embed.add_field(name="Quality", value=f"{self.quality} ({qual_name})", inline=True)
        if response:
            embed.add_field(
                name="RCON Response", value=f"```{(response or '')[:200]}```", inline=False
            )
        embed.set_footer(text=f"Executed by {interaction.user.display_name}")

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(
            f"{interaction.user} gave {self.quantity}x {self.selected_item_name or self.item_text} (q{self.quality}) to <@{self.selected_discord_user_id}> on {found_server}"
        )


# -------- Give Dino Panel (uses SpawnExactDino command) --------

DINO_CATEGORIES = {
    "Carnivores": [
        ("Rex", "Rex_Character_BP_C"),
        ("Spino", "Spino_Character_BP_C"),
        ("Giga", "Gigant_Character_BP_C"),
        ("Allo", "Allo_Character_BP_C"),
        ("Carno", "Carno_Character_BP_C"),
        ("Raptor", "Raptor_Character_BP_C"),
        ("Baryonyx", "Baryonyx_Character_BP_C"),
        ("Theri", "Therizino_Character_BP_C"),
    ],
    "Herbivores": [
        ("Bronto", "Sauropod_Character_BP_C"),
        ("Paraceratherium", "Paracer_Character_BP_C"),
        ("Stego", "Stego_Character_BP_C"),
        ("Trike", "Trike_Character_BP_C"),
        ("Ankylo", "Ankylo_Character_BP_C"),
        ("Doedicurus", "Doed_Character_BP_C"),
        ("Mammoth", "Mammoth_Character_BP_C"),
    ],
    "Flyers": [
        ("Argentavis", "Argent_Character_BP_C"),
        ("Pteranodon", "Ptero_Character_BP_C"),
        ("Quetzal", "Quetz_Character_BP_C"),
        ("Griffin", "Griffin_Character_BP_C"),
        ("Tapejara", "Tapejara_Character_BP_C"),
        ("Wyvern (Fire)", "Wyvern_Character_BP_Fire_C"),
        ("Wyvern (Lightning)", "Wyvern_Character_BP_Lightning_C"),
        ("Wyvern (Poison)", "Wyvern_Character_BP_Poison_C"),
    ],
    "Aquatic": [
        ("Mosasaur", "Mosa_Character_BP_C"),
        ("Megalodon", "Megalodon_Character_BP_C"),
        ("Basilosaurus", "Basilosaurus_Character_BP_C"),
        ("Tusoteuthis", "Tusoteuthis_Character_BP_C"),
        ("Plesiosaur", "Plesiosaur_Character_BP_C"),
    ],
    "Utility": [
        ("Ankylo", "Ankylo_Character_BP_C"),
        ("Doedicurus", "Doed_Character_BP_C"),
        ("Castoroides", "Beaver_Character_BP_C"),
        ("Mantis", "Mantis_Character_BP_C"),
        ("Phoenix", "Phoenix_Character_BP_C"),
    ],
}

SADDLE_BLUEPRINTS = {
    # Carnivores
    "Rex_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_RexSaddle.PrimalItemArmor_RexSaddle'",
    "Spino_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_SpinoSaddle.PrimalItemArmor_SpinoSaddle'",
    "Gigant_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_GigantSaddle.PrimalItemArmor_GigantSaddle'",
    "Allo_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_AlloSaddle.PrimalItemArmor_AlloSaddle'",
    "Carno_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_CarnoSaddle.PrimalItemArmor_CarnoSaddle'",
    "Raptor_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_RaptorSaddle.PrimalItemArmor_RaptorSaddle'",
    "Baryonyx_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_BaryonyxSaddle.PrimalItemArmor_BaryonyxSaddle'",
    "Therizino_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_TherizinosaurusSaddle.PrimalItemArmor_TherizinosaurusSaddle'",
    # Herbivores
    "Sauropod_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_SauroSaddle.PrimalItemArmor_SauroSaddle'",
    "Paracer_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_ParacerSaddle.PrimalItemArmor_ParacerSaddle'",
    "Stego_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_StegoSaddle.PrimalItemArmor_StegoSaddle'",
    "Trike_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_TrikeSaddle.PrimalItemArmor_TrikeSaddle'",
    "Ankylo_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_AnkyloSaddle.PrimalItemArmor_AnkyloSaddle'",
    "Doed_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_DoedSaddle.PrimalItemArmor_DoedSaddle'",
    "Mammoth_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_MammothSaddle.PrimalItemArmor_MammothSaddle'",
    # Flyers
    "Argent_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_ArgentSaddle.PrimalItemArmor_ArgentSaddle'",
    "Ptero_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_PteroSaddle.PrimalItemArmor_PteroSaddle'",
    "Quetz_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_QuetzSaddle.PrimalItemArmor_QuetzSaddle'",
    "Griffin_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_GriffinSaddle.PrimalItemArmor_GriffinSaddle'",
    "Tapejara_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_TapejaraSaddle.PrimalItemArmor_TapejaraSaddle'",
    "Wyvern_Character_BP_Fire_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_WyvernSaddle.PrimalItemArmor_WyvernSaddle'",
    "Wyvern_Character_BP_Lightning_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_WyvernSaddle.PrimalItemArmor_WyvernSaddle'",
    "Wyvern_Character_BP_Poison_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_WyvernSaddle.PrimalItemArmor_WyvernSaddle'",
    # Aquatic
    "Mosa_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_MosaSaddle.PrimalItemArmor_MosaSaddle'",
    "Megalodon_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_MegalodonSaddle.PrimalItemArmor_MegalodonSaddle'",
    "Basilosaurus_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_BasiloSaddle.PrimalItemArmor_BasiloSaddle'",
    "Tusoteuthis_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_TusoSaddle.PrimalItemArmor_TusoSaddle'",
    "Plesiosaur_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_PlesiaSaddle.PrimalItemArmor_PlesiaSaddle'",
    # Utility
    "Beaver_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_BeaverSaddle.PrimalItemArmor_BeaverSaddle'",
    "Mantis_Character_BP_C": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Saddles/PrimalItemArmor_MantisSaddle.PrimalItemArmor_MantisSaddle'",
    # Phoenix has no saddle
}


class GiveDinoPanelView(View):
    """Panel for giving dinos with SpawnExactDino command."""

    def __init__(self, bot: commands.Bot, author: discord.User):
        super().__init__(timeout=None)
        self.bot = bot
        self.author = author
        # State
        self.selected_discord_user_id: Optional[int] = None
        self.selected_dino_class: Optional[str] = None
        self.selected_dino_name: Optional[str] = None
        self.level: int = 150
        self.gender: str = "Random"  # Random, Male, Female
        self.include_saddle: bool = True
        # Dynamic components
        self.players_select: Optional[Select] = None

    async def load_linked_players(self):
        players = []
        try:
            players = await players_db.get_linked_players()
            logger.info(f"GiveDinoPanel: loaded {len(players)} linked players")
        except Exception as ex:
            logger.error(f"GiveDinoPanel: error loading linked players: {ex}", exc_info=True)

        options: list[discord.SelectOption] = []
        count = 0
        for p in players:
            if count >= 25:
                break
            label = (
                p.get("discord_display_name")
                or p.get("discord_username")
                or str(p.get("discord_user_id"))
            )[:100]
            description = f"EOS {str(p.get('eos_id'))[:24]}..." if p.get("eos_id") else None
            value_str = (
                str(p.get("discord_user_id")) if p.get("discord_user_id") is not None else None
            )
            if not value_str:
                continue
            options.append(
                discord.SelectOption(label=label, value=value_str, description=description)
            )
            count += 1

        if options:
            self.players_select = Select(
                placeholder="Select a linked player...",
                options=options,
                custom_id="dino_player_select",
            )
            self.players_select.callback = self._on_player_selected
            self.add_item(self.players_select)
        else:
            fallback = discord.ui.UserSelect(
                placeholder="Select a player (fallback)", custom_id="dino_fallback_user"
            )

            async def _fallback_cb(interaction: discord.Interaction):
                try:
                    uid = int(interaction.data["values"][0])
                    self.selected_discord_user_id = uid
                except Exception:
                    self.selected_discord_user_id = None
                await self.refresh_message(interaction)

            fallback.callback = _fallback_cb
            self.add_item(fallback)

        # Gender selector
        gender_select = Select(
            placeholder="Gender",
            options=[
                discord.SelectOption(label="Random", value="Random", default=True),
                discord.SelectOption(label="Male", value="Male"),
                discord.SelectOption(label="Female", value="Female"),
            ],
            custom_id="gender_select",
        )
        gender_select.callback = self._on_gender_selected
        self.add_item(gender_select)

        # Level selector
        level_select = Select(
            placeholder="Level",
            options=[
                discord.SelectOption(label="150", value="150", default=True),
                discord.SelectOption(label="200", value="200"),
                discord.SelectOption(label="300", value="300"),
                discord.SelectOption(label="450", value="450"),
                discord.SelectOption(label="Custom...", value="Custom"),
            ],
            custom_id="level_select",
        )
        level_select.callback = self._on_level_selected
        self.add_item(level_select)

        # Saddle toggle button
        saddle_btn = Button(
            label="✅ Include Saddle (Ascendant)",
            style=discord.ButtonStyle.success,
            custom_id="saddle_toggle",
        )
        saddle_btn.callback = self._toggle_saddle
        self.add_item(saddle_btn)

        # Dino catalog button
        catalog_btn = Button(
            label="🦖 Choose Dino", style=discord.ButtonStyle.primary, custom_id="dino_catalog"
        )
        catalog_btn.callback = self._open_dino_catalog
        self.add_item(catalog_btn)

        # Submit
        submit_btn = Button(
            label="Submit", style=discord.ButtonStyle.success, custom_id="dino_submit"
        )
        submit_btn.callback = self._submit
        self.add_item(submit_btn)

    def create_embed(self) -> discord.Embed:
        e = discord.Embed(title="🦖 Give Dino", color=discord.Color.green())
        e.add_field(
            name="Player",
            value=(f"<@{self.selected_discord_user_id}>" if self.selected_discord_user_id else "—"),
            inline=False,
        )
        e.add_field(name="Dino", value=(self.selected_dino_name or "—"), inline=False)
        e.add_field(name="Level", value=str(self.level), inline=True)
        e.add_field(name="Gender", value=self.gender, inline=True)
        e.add_field(
            name="Saddle", value=("Yes (Ascendant)" if self.include_saddle else "No"), inline=True
        )
        e.set_footer(text=f"Requested by {self.author.display_name}")
        return e

    async def refresh_message(self, interaction: discord.Interaction, notify_changed: bool = False):
        self.clear_items()
        # Rebuild player selector
        if self.players_select:
            opts = self.players_select.options
            self.players_select = Select(
                placeholder="Select a linked player...",
                options=opts,
                custom_id="dino_player_select",
            )
            self.players_select.callback = self._on_player_selected
            self.add_item(self.players_select)

        # Rebuild gender
        gender_select = Select(
            placeholder="Gender",
            options=[
                discord.SelectOption(
                    label="Random", value="Random", default=(self.gender == "Random")
                ),
                discord.SelectOption(label="Male", value="Male", default=(self.gender == "Male")),
                discord.SelectOption(
                    label="Female", value="Female", default=(self.gender == "Female")
                ),
            ],
            custom_id="gender_select",
        )
        gender_select.callback = self._on_gender_selected
        self.add_item(gender_select)

        # Rebuild level
        level_options = [
            discord.SelectOption(label="150", value="150", default=(self.level == 150)),
            discord.SelectOption(label="200", value="200", default=(self.level == 200)),
            discord.SelectOption(label="300", value="300", default=(self.level == 300)),
            discord.SelectOption(label="450", value="450", default=(self.level == 450)),
            discord.SelectOption(label="Custom...", value="Custom"),
        ]
        level_select = Select(placeholder="Level", options=level_options, custom_id="level_select")
        level_select.callback = self._on_level_selected
        self.add_item(level_select)

        # Saddle button
        saddle_btn = Button(
            label=("✅ Include Saddle (Ascendant)" if self.include_saddle else "❌ No Saddle"),
            style=(
                discord.ButtonStyle.success
                if self.include_saddle
                else discord.ButtonStyle.secondary
            ),
            custom_id="saddle_toggle",
        )
        saddle_btn.callback = self._toggle_saddle
        self.add_item(saddle_btn)

        catalog_btn = Button(
            label="🦖 Choose Dino", style=discord.ButtonStyle.primary, custom_id="dino_catalog"
        )
        catalog_btn.callback = self._open_dino_catalog
        self.add_item(catalog_btn)

        submit_btn = Button(
            label="Submit", style=discord.ButtonStyle.success, custom_id="dino_submit"
        )
        submit_btn.callback = self._submit
        self.add_item(submit_btn)

        content = "✅ Updated." if notify_changed else None
        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(
                    content=content, embed=self.create_embed(), view=self
                )
            elif interaction.message:
                await interaction.message.edit(
                    content=content, embed=self.create_embed(), view=self
                )
            else:
                await interaction.edit_original_response(
                    content=content, embed=self.create_embed(), view=self
                )
        except Exception as e:
            logger.debug(f"refresh_message fallback due to {e}")
            try:
                await interaction.edit_original_response(embed=self.create_embed(), view=self)
            except Exception as e2:
                logger.error("Failed to refresh GiveDinoPanel message: %s", e2)

    async def _on_player_selected(self, interaction: discord.Interaction):
        try:
            self.selected_discord_user_id = int(interaction.data["values"][0])
        except Exception:
            self.selected_discord_user_id = None
        await self.refresh_message(interaction)

    async def _on_gender_selected(self, interaction: discord.Interaction):
        self.gender = interaction.data["values"][0]
        await self.refresh_message(interaction)

    async def _on_level_selected(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        if val == "Custom":

            class LevelModal(Modal, title="Set Level"):
                lv = TextInput(label="Level", placeholder="e.g., 500", required=True, max_length=6)

                def __init__(self, view_ref: "GiveDinoPanelView"):
                    super().__init__()
                    self.view_ref = view_ref

                async def on_submit(self, inter: discord.Interaction):
                    try:
                        self.view_ref.level = max(1, int(self.lv.value))
                    except Exception:
                        self.view_ref.level = 150
                    await self.view_ref.refresh_message(inter, notify_changed=True)

            await interaction.response.send_modal(LevelModal(self))
            return
        else:
            try:
                self.level = int(val)
            except Exception:
                self.level = 150
        await self.refresh_message(interaction)

    async def _toggle_saddle(self, interaction: discord.Interaction):
        self.include_saddle = not self.include_saddle
        await self.refresh_message(interaction)

    async def _open_dino_catalog(self, interaction: discord.Interaction):
        view = DinoCatalogView(self)
        await view.start(interaction)

    async def _submit(self, interaction: discord.Interaction):
        if not self.selected_discord_user_id:
            await interaction.response.send_message("❌ Please select a player.", ephemeral=True)
            return
        if not self.selected_dino_class:
            await interaction.response.send_message("❌ Please choose a dino.", ephemeral=True)
            return

        # Retrieve EOS
        player = await players_db.get_player_by_discord_id(self.selected_discord_user_id)
        if not player or not player.get("eos_id"):
            await interaction.response.send_message(
                "❌ Selected user is not linked to an EOS ID.", ephemeral=True
            )
            return

        eos_id = player["eos_id"]

        # Auto-detect server
        from bot.cogs.server_monitor import ServerMonitor

        server_monitor = self.bot.get_cog("ServerMonitor")
        if not server_monitor or not server_monitor.rcon_manager:
            await interaction.response.send_message(
                "❌ Server monitor not available.", ephemeral=True
            )
            return

        found_server = None
        for server_name, client in server_monitor.rcon_manager.clients.items():
            try:
                players_online = await client.get_player_list()
                target = str(eos_id).strip().lstrip("0")
                for p in players_online:
                    ids_to_check = [
                        str(p.get("steam_id", "")).strip().lstrip("0"),
                        str(p.get("eos_id", "")).strip().lstrip("0"),
                        str(p.get("id", "")).strip().lstrip("0"),
                    ]
                    if target and target in ids_to_check:
                        found_server = server_name
                        break
                if found_server:
                    break
            except Exception as ex:
                logger.debug(f"Could not check {server_name}: {ex}")

        if not found_server:
            # Fallback server selector
            class ServerSelectView(View):
                def __init__(self, outer: "GiveDinoPanelView", servers: list[str], eos: str):
                    super().__init__(timeout=None)
                    self.outer = outer
                    self.eos = eos
                    options = [discord.SelectOption(label=s, value=s) for s in servers]
                    select = Select(placeholder="Select server", options=options)

                    async def _on_select(inter: discord.Interaction):
                        server_name = inter.data["values"][0]
                        await self.outer._execute_spawn(inter, server_name, self.eos)

                    select.callback = _on_select
                    self.add_item(select)
                    cancel = Button(label="✖ Cancel", style=discord.ButtonStyle.danger)

                    async def _cancel(inter: discord.Interaction):
                        await inter.response.edit_message(content="Cancelled.", view=None)

                    cancel.callback = _cancel
                    self.add_item(cancel)

            servers = list(server_monitor.rcon_manager.clients.keys())
            fallback_view = ServerSelectView(self, servers, eos_id)
            await interaction.response.send_message(
                "Player not detected online. Choose a server to proceed:",
                view=fallback_view,
                ephemeral=True,
            )
            return

        # Execute spawn
        await self._execute_spawn(interaction, found_server, eos_id)

    async def _execute_spawn(self, interaction: discord.Interaction, server_name: str, eos_id: str):
        from bot.cogs.server_monitor import ServerMonitor

        server_monitor = self.bot.get_cog("ServerMonitor")
        client = server_monitor.rcon_manager.clients[server_name]

        # Get player info for imprinting
        player = await players_db.get_player_by_discord_id(self.selected_discord_user_id)
        player_name = (
            player.get("discord_display_name") or player.get("discord_username") or "Player"
        )

        # Construct full blueprint path
        dino_base = self.selected_dino_class.replace("_Character_BP_C", "")
        blueprint = f"Blueprint'/Game/PrimalEarth/Dinos/{dino_base}/{self.selected_dino_class}.{self.selected_dino_class}'"

        # Saddle blueprint and quality
        saddle_bp = SADDLE_BLUEPRINTS.get(self.selected_dino_class, "")
        saddle_quality = 10 if self.include_saddle and saddle_bp else 1  # 10 = Ascendant

        # Calculate base and extra levels (split evenly)
        base_level = self.level // 2
        extra_levels = self.level - base_level

        # Base stats: "Health,Stamina,Oxygen,Food,Weight,MeleeDmg,MoveSpeed,CraftingSkill"
        # Distribute base levels evenly across health, stamina, melee
        base_stats = f"{base_level//3},{base_level//3},0,0,0,{base_level//3},0,0"

        # Added stats: distribute extra levels similarly
        added_stats = f"{extra_levels//3},{extra_levels//3},0,0,0,{extra_levels//3},0,0"

        # Name
        dino_display_name = self.selected_dino_name or "Dino"

        # Cloned and Neutered
        cloned = 0
        neutered = (
            1 if self.gender == "Random" else 0
        )  # Neuter if random gender to prevent breeding

        # Tamed date and upload (leave blank)
        tamed_date = ""
        uploaded_from = ""

        # Imprinter name and ID
        imprinter_name = player_name
        imprinter_id = str(self.selected_discord_user_id)

        # Imprint quality (1.0 = 100%)
        imprint_quality = 1

        # Required 0 parameter
        zero_param = 0

        # Region colors (empty = random natural colors)
        region_colors = ""

        # Creature ID (0 = auto-generate)
        creature_id = 0

        # Experience (set to match level)
        experience = self.level * 1000

        # Spawn distance/offset (100 units in front, 0 Y, 200 Z above)
        spawn_distance = 100
        spawn_y = 0
        spawn_z = 200

        # Build command (SpawnExactDino with all 23 parameters)
        command = (
            f'cheat SpawnExactDino "{blueprint}" "{saddle_bp}" {saddle_quality} '
            f'{base_level} {extra_levels} "{base_stats}" "{added_stats}" '
            f'"{dino_display_name}" {cloned} {neutered} "{tamed_date}" "{uploaded_from}" '
            f'"{imprinter_name}" {imprinter_id} {imprint_quality} {zero_param} '
            f'"{region_colors}" {creature_id} {experience} {spawn_distance} {spawn_y} {spawn_z}'
        )

        try:
            response = await client.execute_command(command)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Spawn failed: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Spawn failed: {e}", ephemeral=True)
            logger.error("SpawnExactDino failed: %s", e, exc_info=True)
            return

        embed = discord.Embed(title="✅ Dino Spawned Successfully", color=discord.Color.green())
        embed.add_field(name="Server", value=server_name, inline=False)
        embed.add_field(name="Player", value=f"<@{self.selected_discord_user_id}>", inline=True)
        embed.add_field(name="Dino", value=dino_display_name, inline=True)
        embed.add_field(
            name="Level",
            value=f"{self.level} (Base: {base_level}, Extra: {extra_levels})",
            inline=True,
        )
        embed.add_field(name="Gender", value=self.gender, inline=True)
        if self.include_saddle and saddle_bp:
            embed.add_field(name="Saddle", value="✅ Ascendant (Quality 10)", inline=True)
        else:
            embed.add_field(name="Saddle", value="❌ None", inline=True)
        embed.add_field(name="Imprinted To", value=imprinter_name, inline=True)
        embed.add_field(name="Imprint Quality", value="100%", inline=True)
        if response:
            embed.add_field(
                name="RCON Response", value=f"```{(response or '')[:200]}```", inline=False
            )
        embed.set_footer(text=f"Executed by {self.author.display_name}")

        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(
            "%s spawned %s (level %d, %s) for <@%s> on %s",
            self.author,
            dino_display_name,
            self.level,
            self.gender,
            self.selected_discord_user_id,
            server_name,
        )


class DinoCatalogView(View):
    """Category-driven dino catalog for GiveDinoPanel."""

    def __init__(self, parent_view: GiveDinoPanelView):
        super().__init__(timeout=None)
        self.parent_view = parent_view
        self.mode = "categories"  # or "dinos"
        self.categories = list(DINO_CATEGORIES.keys())
        self.category_page = 0
        self.dinos: list[tuple[str, str]] = []
        self.dinos_page = 0
        self.dinos_per_page = 10

    def _render_categories_embed(self) -> discord.Embed:
        start = self.category_page * 4
        page_cats = self.categories[start : start + 4]
        e = discord.Embed(title="🦖 Dino Catalog", color=discord.Color.green())
        desc = "Categories\n\n"
        for idx, cat in enumerate(page_cats, start=1):
            desc += f"{idx}. {cat}\n"
        if not page_cats:
            desc += "No categories."
        e.description = desc
        e.set_footer(text=f"Page: {self.category_page + 1}/{max(1, (len(self.categories)+3)//4)}")
        return e

    def _render_dinos_embed(self) -> discord.Embed:
        start = self.dinos_page * self.dinos_per_page
        page_dinos = self.dinos[start : start + self.dinos_per_page]
        e = discord.Embed(title="🦖 Dino Catalog", color=discord.Color.green())
        e.description = "Dinos\n\n" + (
            "\n".join([f"{i+1}. {name}" for i, (name, _) in enumerate(page_dinos)]) or "No dinos"
        )
        e.set_footer(
            text=f"Page: {self.dinos_page + 1}/{max(1, (len(self.dinos)+self.dinos_per_page-1)//self.dinos_per_page)}"
        )
        return e

    def _rebuild_controls(self):
        self.clear_items()
        if self.mode == "categories":
            if self.category_page > 0:
                prev = Button(label="◀", style=discord.ButtonStyle.primary)
                prev.callback = self._prev_categories
                self.add_item(prev)
            if (self.category_page + 1) * 4 < len(self.categories):
                nxt = Button(label="▶", style=discord.ButtonStyle.primary)
                nxt.callback = self._next_categories
                self.add_item(nxt)
            for i in range(1, 5):
                btn = Button(label=str(i), style=discord.ButtonStyle.success)

                def make_callback(index):
                    async def callback(interaction: discord.Interaction):
                        await self._select_category(interaction, index)

                    return callback

                btn.callback = make_callback(i)
                self.add_item(btn)
            close = Button(label="✖", style=discord.ButtonStyle.secondary)
            close.callback = self._close
            self.add_item(close)
        else:
            if self.dinos_page > 0:
                prev = Button(label="◀", style=discord.ButtonStyle.primary)
                prev.callback = self._prev_dinos
                self.add_item(prev)
            if (self.dinos_page + 1) * self.dinos_per_page < len(self.dinos):
                nxt = Button(label="▶", style=discord.ButtonStyle.primary)
                nxt.callback = self._next_dinos
                self.add_item(nxt)
            start = self.dinos_page * self.dinos_per_page
            page_dinos = self.dinos[start : start + self.dinos_per_page]
            options = [
                discord.SelectOption(label=name[:100], value=str(start + idx))
                for idx, (name, _) in enumerate(page_dinos)
            ]
            if options:
                select = Select(placeholder="Select a dino", options=options)
                select.callback = self._dino_selected
                self.add_item(select)
            back = Button(label="⬅ Categories", style=discord.ButtonStyle.secondary)
            back.callback = self._back_to_categories
            self.add_item(back)
            close = Button(label="✖", style=discord.ButtonStyle.secondary)
            close.callback = self._close
            self.add_item(close)

    async def _prev_categories(self, interaction: discord.Interaction):
        self.category_page = max(0, self.category_page - 1)
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_categories_embed(), view=self)

    async def _next_categories(self, interaction: discord.Interaction):
        max_pages = (len(self.categories) + 3) // 4
        self.category_page = min(max_pages - 1, self.category_page + 1)
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_categories_embed(), view=self)

    async def _select_category(self, interaction: discord.Interaction, index: int):
        start = self.category_page * 4
        cat_idx = start + (index - 1)
        if cat_idx < 0 or cat_idx >= len(self.categories):
            return
        category = self.categories[cat_idx]
        self.dinos = DINO_CATEGORIES[category]
        self.dinos_page = 0
        self.mode = "dinos"
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_dinos_embed(), view=self)

    async def _prev_dinos(self, interaction: discord.Interaction):
        self.dinos_page = max(0, self.dinos_page - 1)
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_dinos_embed(), view=self)

    async def _next_dinos(self, interaction: discord.Interaction):
        max_pages = (len(self.dinos) + self.dinos_per_page - 1) // self.dinos_per_page
        self.dinos_page = min(max_pages - 1, self.dinos_page + 1)
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_dinos_embed(), view=self)

    async def _dino_selected(self, interaction: discord.Interaction):
        idx = int(interaction.data["values"][0])
        sel = self.dinos[idx]
        self.parent_view.selected_dino_name = sel[0]
        self.parent_view.selected_dino_class = sel[1]
        await interaction.response.edit_message(content=f"✅ Selected: **{sel[0]}**", view=None)
        await self.parent_view.refresh_message(interaction, notify_changed=True)

    async def _back_to_categories(self, interaction: discord.Interaction):
        self.mode = "categories"
        self._rebuild_controls()
        await interaction.response.edit_message(embed=self._render_categories_embed(), view=self)

    async def _close(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=None)

    async def start(self, interaction: discord.Interaction):
        self.mode = "categories"
        self.category_page = 0
        self._rebuild_controls()
        await interaction.response.send_message(
            embed=self._render_categories_embed(), view=self, ephemeral=True
        )


class EnhancedGiveItemCog(commands.Cog):
    """Enhanced give item command with player autocomplete and item search."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="giveitem_gui", description="🎁 Give an item to a player (enhanced UI)"
    )
    @app_commands.describe(player="Select a linked player")
    @app_commands.checks.has_permissions(administrator=True)
    async def giveitem_enhanced(self, interaction: discord.Interaction, player: discord.Member):
        """Enhanced give item with autocomplete and search."""
        # Check if player has linked account
        from bot.database import players_db

        player_data = await players_db.get_player_by_discord_id(player.id)

        if not player_data or not player_data.get("eos_id"):
            await interaction.response.send_message(
                f"❌ {player.mention} has not linked their EOS ID yet. Ask them to use `/players` → Link Account.",
                ephemeral=True,
            )
            return

        # Create modal with pre-filled player data
        modal = EnhancedGiveItemModal(self.bot, player=player, player_data=player_data)
        await interaction.response.send_modal(modal)

        # Send a follow-up message with the search button
        view = EnhancedGiveItemView(modal, self.bot)
        await interaction.followup.send(
            "💡 **Tip**: Click the 🔍 Search Items button below to find items easily!",
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(EnhancedGiveItemCog(bot))
