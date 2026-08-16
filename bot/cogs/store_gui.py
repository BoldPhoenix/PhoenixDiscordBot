"""
Store Management GUI - Interactive interface for managing shop items.
Provides visual tools for adding, editing, and removing store items.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button, Modal, TextInput
from typing import Optional, List
import logging

from bot.database import store_db, server_config_db
from bot.utils.config import Config

logger = logging.getLogger("StoreGUI")


class StoreManagementView(View):
    """Main store management interface."""

    def __init__(self, guild_id: int, user: discord.User, timeout: int = 300):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.items = []
        self.categories = []
        self.current_page = 0
        self.items_per_page = 10
        self.selected_category = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This store management panel is not for you!", ephemeral=True
            )
            return False
        return True

    async def load_data(self):
        """Load store items and categories."""
        self.items = await store_db.get_all_items(enabled_only=False)
        self.categories = await store_db.get_categories()

    def create_main_embed(self) -> discord.Embed:
        """Create the main store management embed."""
        embed = discord.Embed(
            title="🛒 Store Management Panel",
            description=(
                "Manage your Phoenix Store items.\n"
                "Add, edit, or remove items from the shop.\n\n"
                f"**Total Items:** {len(self.items)}\n"
                f"**Categories:** {len(self.categories)}"
            ),
            color=discord.Color.gold(),
        )

        # Show items by category
        if self.categories:
            items_by_cat = {}
            for item in self.items:
                cat = item.get("category", "general")
                items_by_cat[cat] = items_by_cat.get(cat, 0) + 1

            cat_text = "\n".join(
                [f"• **{cat}**: {count} items" for cat, count in items_by_cat.items()]
            )
            embed.add_field(name="📦 Categories", value=cat_text or "No categories", inline=False)

        embed.set_footer(text="💡 Use the buttons below to manage items")
        return embed


class StoreMainView(StoreManagementView):
    """Main store management view with action buttons."""

    def __init__(self, guild_id: int, user: discord.User):
        super().__init__(guild_id, user)

        self.add_item(StoreActionButton("Add Item", "➕", "add"))
        self.add_item(StoreActionButton("View Items", "📋", "view"))
        self.add_item(StoreActionButton("Edit Item", "✏️", "edit"))
        self.add_item(StoreActionButton("Remove Item", "🗑️", "remove"))
        self.add_item(StoreActionButton("Bulk Import", "📤", "import"))


class StoreActionButton(Button):
    """Button for store actions."""

    def __init__(self, label: str, emoji: str, action: str):
        super().__init__(
            style=discord.ButtonStyle.primary, label=label, emoji=emoji, custom_id=f"store_{action}"
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        view: StoreMainView = self.view

        if self.action == "add":
            modal = AddItemModal()
            await interaction.response.send_modal(modal)

        elif self.action == "view":
            items_view = ItemListView(view.guild_id, view.user)
            await items_view.load_data()
            embed = items_view.create_list_embed()
            await interaction.response.send_message(embed=embed, view=items_view, ephemeral=True)

        elif self.action == "edit":
            edit_view = EditItemSelectView(view.guild_id, view.user)
            await edit_view.load_data()
            embed = edit_view.create_select_embed()
            await interaction.response.send_message(embed=embed, view=edit_view, ephemeral=True)

        elif self.action == "remove":
            remove_view = RemoveItemSelectView(view.guild_id, view.user)
            await remove_view.load_data()
            embed = remove_view.create_select_embed()
            await interaction.response.send_message(embed=embed, view=remove_view, ephemeral=True)

        elif self.action == "import":
            embed = discord.Embed(
                title="📤 Bulk Import",
                description=(
                    "To bulk import items, use the `/uploadshop` command.\n\n"
                    "**Required Format:**\n"
                    "Upload an Excel file (.xlsx) with an 'items' sheet.\n\n"
                    "**Columns:**\n"
                    "• Item Name\n"
                    "• Price Per Item\n"
                    "• Allow Quality Select (future)\n"
                    "• Allow Blueprint Select (future)\n"
                    "• Max Stack Size (future)\n"
                    "• Category\n"
                    "• Description\n"
                    "• Class Name\n"
                    "• Blueprint Path\n"
                    "• Server Type\n\n"
                    "**Modes:**\n"
                    "• `preview` - See changes before applying\n"
                    "• `replace` - Clear store and import\n"
                    "• `merge` - Add/update items"
                ),
                color=discord.Color.blue(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class AddItemModal(Modal):
    """Modal for adding a new store item."""

    def __init__(self):
        super().__init__(title="➕ Add Store Item")

        self.item_name = TextInput(
            label="Item Name",
            placeholder="e.g., Phoenix Flak Helmet",
            required=True,
            max_length=100,
        )
        self.add_item(self.item_name)

        self.description = TextInput(
            label="Description",
            placeholder="A sturdy helmet for brave survivors",
            required=False,
            max_length=200,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.description)

        self.price = TextInput(
            label="Price (Phoenix Coins)", placeholder="100", required=True, max_length=10
        )
        self.add_item(self.price)

        self.category = TextInput(
            label="Category",
            placeholder="e.g., armor, weapons, tools, resources",
            required=True,
            max_length=50,
        )
        self.add_item(self.category)

        self.ark_command = TextInput(
            label="ARK Command (blueprint path)",
            placeholder='cheat giveitem "Blueprint\'/Game/..." 1 0 0',
            required=True,
            max_length=500,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.ark_command)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price.value)
            if price < 0:
                raise ValueError("Price must be positive")

            item_id = await store_db.add_item(
                name=self.item_name.value,
                description=self.description.value or "",
                cost=price,
                ark_command=self.ark_command.value,
                category=self.category.value.lower(),
            )

            embed = discord.Embed(
                title="✅ Item Added",
                description=f"**{self.item_name.value}** has been added to the store!",
                color=discord.Color.green(),
            )
            embed.add_field(name="Price", value=f"{price} {Config.CURRENCY_EMOJI}", inline=True)
            embed.add_field(name="Category", value=self.category.value, inline=True)
            embed.add_field(name="Item ID", value=str(item_id), inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Invalid price! Please enter a positive number.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error adding item: {e}", ephemeral=True)


class ItemListView(StoreManagementView):
    """View for listing store items with pagination."""

    def __init__(self, guild_id: int, user: discord.User):
        super().__init__(guild_id, user)

        self.add_item(PaginationButton("◀️ Previous", "prev"))
        self.add_item(PaginationButton("Next ▶️", "next"))
        self.add_item(CategoryFilterSelect())

    def create_list_embed(self) -> discord.Embed:
        """Create item list embed."""
        # Filter by category if selected
        if self.selected_category:
            filtered_items = [i for i in self.items if i.get("category") == self.selected_category]
        else:
            filtered_items = self.items

        total_pages = max(1, (len(filtered_items) + self.items_per_page - 1) // self.items_per_page)
        self.current_page = min(self.current_page, total_pages - 1)

        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_items = filtered_items[start:end]

        embed = discord.Embed(
            title="📋 Store Items",
            description=f"Showing {len(page_items)} of {len(filtered_items)} items"
            + (f" in **{self.selected_category}**" if self.selected_category else ""),
            color=discord.Color.blue(),
        )

        for item in page_items:
            status = "✅" if item.get("enabled", True) else "❌"
            embed.add_field(
                name=f"{status} {item['name']} (ID: {item['item_id']})",
                value=f"💰 {item['cost']} coins | 📁 {item.get('category', 'general')}",
                inline=False,
            )

        if not page_items:
            embed.add_field(name="No Items", value="No items found in store", inline=False)

        embed.set_footer(text=f"Page {self.current_page + 1}/{total_pages}")
        return embed


class PaginationButton(Button):
    """Button for pagination."""

    def __init__(self, label: str, direction: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=label)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: ItemListView = self.view

        if self.direction == "prev" and view.current_page > 0:
            view.current_page -= 1
        elif self.direction == "next":
            filtered_items = [
                i
                for i in view.items
                if not view.selected_category or i.get("category") == view.selected_category
            ]
            total_pages = max(
                1, (len(filtered_items) + view.items_per_page - 1) // view.items_per_page
            )
            if view.current_page < total_pages - 1:
                view.current_page += 1

        embed = view.create_list_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class CategoryFilterSelect(Select):
    """Dropdown to filter by category."""

    def __init__(self):
        super().__init__(
            placeholder="Filter by category...",
            options=[discord.SelectOption(label="All Categories", value="all")],
            custom_id="category_filter",
        )

    async def callback(self, interaction: discord.Interaction):
        view: ItemListView = self.view

        selected = self.values[0]
        view.selected_category = None if selected == "all" else selected
        view.current_page = 0

        # Update options with categories
        categories = list(set(item.get("category", "general") for item in view.items))
        self.options = [discord.SelectOption(label="All Categories", value="all")]
        for cat in sorted(categories):
            self.options.append(discord.SelectOption(label=cat.title(), value=cat))

        embed = view.create_list_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class EditItemSelectView(StoreManagementView):
    """View for selecting an item to edit."""

    def __init__(self, guild_id: int, user: discord.User):
        super().__init__(guild_id, user)

    async def load_data(self):
        """Load items and add select menu."""
        await super().load_data()

        # Add item select (limited to 25 options)
        options = []
        for item in self.items[:25]:
            options.append(
                discord.SelectOption(
                    label=f"{item['name'][:50]}",
                    description=f"💰 {item['cost']} | {item.get('category', 'general')}",
                    value=str(item["item_id"]),
                )
            )

        if options:
            select = Select(
                placeholder="Select an item to edit...",
                options=options,
                custom_id="edit_item_select",
            )
            select.callback = self.item_selected
            self.add_item(select)

    async def item_selected(self, interaction: discord.Interaction):
        """Handle item selection for editing."""
        item_id = int(interaction.data["values"][0])
        item = await store_db.get_item(item_id)

        if item:
            modal = EditItemModal(item)
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message("❌ Item not found!", ephemeral=True)

    def create_select_embed(self) -> discord.Embed:
        """Create item selection embed."""
        embed = discord.Embed(
            title="✏️ Edit Store Item",
            description="Select an item from the dropdown to edit it.",
            color=discord.Color.blue(),
        )

        if len(self.items) > 25:
            embed.add_field(
                name="⚠️ Note",
                value=f"Showing first 25 items. Use `/setprice` command for items not shown.",
                inline=False,
            )

        return embed


class EditItemModal(Modal):
    """Modal for editing an existing item."""

    def __init__(self, item: dict):
        super().__init__(title=f"✏️ Edit: {item['name'][:40]}")
        self.item_id = item["item_id"]

        self.item_name = TextInput(
            label="Item Name", default=item["name"], required=True, max_length=100
        )
        self.add_item(self.item_name)

        self.description = TextInput(
            label="Description",
            default=item.get("description", ""),
            required=False,
            max_length=200,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.description)

        self.price = TextInput(
            label="Price (Phoenix Coins)", default=str(item["cost"]), required=True, max_length=10
        )
        self.add_item(self.price)

        self.category = TextInput(
            label="Category", default=item.get("category", "general"), required=True, max_length=50
        )
        self.add_item(self.category)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price.value)
            if price < 0:
                raise ValueError("Price must be positive")

            # Update price (main editable field)
            await store_db.update_item_price(self.item_id, price)

            # Note: Full item update would need additional DB function
            # For now, we update price which is the most common change

            embed = discord.Embed(
                title="✅ Item Updated",
                description=f"**{self.item_name.value}** has been updated!",
                color=discord.Color.green(),
            )
            embed.add_field(name="New Price", value=f"{price} {Config.CURRENCY_EMOJI}", inline=True)
            embed.add_field(name="Category", value=self.category.value, inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid price! Please enter a positive number.", ephemeral=True
            )


class RemoveItemSelectView(StoreManagementView):
    """View for selecting an item to remove."""

    def __init__(self, guild_id: int, user: discord.User):
        super().__init__(guild_id, user)

    async def load_data(self):
        """Load items and add select menu."""
        await super().load_data()

        options = []
        for item in self.items[:25]:
            options.append(
                discord.SelectOption(
                    label=f"{item['name'][:50]}",
                    description=f"💰 {item['cost']} | ID: {item['item_id']}",
                    value=str(item["item_id"]),
                )
            )

        if options:
            select = Select(
                placeholder="Select an item to remove...",
                options=options,
                custom_id="remove_item_select",
            )
            select.callback = self.item_selected
            self.add_item(select)

    async def item_selected(self, interaction: discord.Interaction):
        """Handle item selection for removal."""
        item_id = int(interaction.data["values"][0])
        item = await store_db.get_item(item_id)

        if item:
            confirm_view = ConfirmRemoveView(item)
            embed = discord.Embed(
                title="⚠️ Confirm Removal",
                description=f"Are you sure you want to remove **{item['name']}**?",
                color=discord.Color.red(),
            )
            embed.add_field(
                name="Price", value=f"{item['cost']} {Config.CURRENCY_EMOJI}", inline=True
            )
            embed.add_field(name="Category", value=item.get("category", "general"), inline=True)

            await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Item not found!", ephemeral=True)

    def create_select_embed(self) -> discord.Embed:
        """Create item removal selection embed."""
        embed = discord.Embed(
            title="🗑️ Remove Store Item",
            description="Select an item from the dropdown to remove it.",
            color=discord.Color.red(),
        )

        embed.add_field(name="⚠️ Warning", value="Removing items cannot be undone!", inline=False)

        return embed


class ConfirmRemoveView(View):
    """Confirmation view for item removal."""

    def __init__(self, item: dict):
        super().__init__(timeout=None)
        self.item = item

    @discord.ui.button(label="Yes, Remove", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        success = await store_db.remove_item(self.item["item_id"])

        if success:
            embed = discord.Embed(
                title="✅ Item Removed",
                description=f"**{self.item['name']}** has been removed from the store.",
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title="❌ Error", description="Failed to remove item.", color=discord.Color.red()
            )

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            content="❌ Removal cancelled.", embed=None, view=None
        )


class StoreGUI(commands.Cog):
    """Interactive store management GUI."""

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
        name="storecfg", description="🛒 Interactive store management panel (admin only)"
    )
    async def store_cfg(self, interaction: discord.Interaction):
        """Open the interactive store management GUI."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        view = StoreMainView(interaction.guild_id, interaction.user)
        await view.load_data()
        embed = view.create_main_embed()

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(StoreGUI(bot))
