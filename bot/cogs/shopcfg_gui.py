"""
Shop Configuration GUI Cog.
Provides a GUI for shop administration - items management and settings.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.database import shop_db, server_config_db
from bot.utils.subscription_checker import check_feature

logger = logging.getLogger("ShopCfgGUI")


async def _log_to_admin_channel(bot, guild_id: int, message: str):
    """Send a message to the guild's configured admin log channel."""
    try:
        config = await server_config_db.get_server_config(guild_id)
        if not config:
            logger.warning(f"No config found for guild {guild_id}")
            return
        channel_id = config.get("admin_log_channel_id")
        if not channel_id:
            logger.warning(f"admin_log_channel_id not configured for guild {guild_id}")
            return
        channel = bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Admin log channel {channel_id} not found for guild {guild_id}")
            return
        await channel.send(message)
    except Exception as e:
        logger.error(f"Failed to send to admin log channel: {e}")


class ShopCfgCog(commands.Cog):
    """Shop configuration GUI."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permission."""
        if not interaction.guild:
            return False
        config = await server_config_db.get_server_config(interaction.guild.id)
        admin_role_id = config.get("admin_role_id") if config else None
        if admin_role_id:
            member = interaction.guild.get_member(interaction.user.id)
            if member and admin_role_id in [r.id for r in member.roles]:
                return True
        return interaction.user.guild_permissions.administrator

    # ---------------------------------------------------------------------------
    # Main Shop Config View
    # ---------------------------------------------------------------------------

    @app_commands.command(name="shopcfg", description="🛒 Configure shop (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def shopcfg_command(self, interaction: discord.Interaction):
        """Main shop configuration command with GUI."""
        await interaction.response.defer(ephemeral=True)
        if not await check_feature(interaction, "shop"):
            return
        if not await self.is_admin(interaction):
            await interaction.followup.send(
                "❌ You need Administrator permission to use this command.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            embed=self._build_main_embed(),
            view=ShopCfgMainView(self),
            ephemeral=True,
        )

    @shopcfg_command.error
    async def shopcfg_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)

    def _build_main_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🛒 Shop Configuration",
            description="Manage your server's shop system",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="📦 Shop Items",
            value="Add, edit, or remove shop items",
            inline=False,
        )
        embed.add_field(
            name="⚙️ Shop Settings",
            value="Configure shop enable/disable, channels, and options",
            inline=False,
        )
        return embed


class ShopCfgMainView(discord.ui.View):
    """Main shop configuration view with category buttons."""

    def __init__(self, cog: ShopCfgCog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="📦 Shop Items", style=discord.ButtonStyle.primary)
    async def shop_items_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            embed=ShopItemsView.build_embed(),
            view=ShopItemsView(self.cog),
        )

    @discord.ui.button(label="⚙️ Shop Settings", style=discord.ButtonStyle.primary)
    async def shop_settings_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission.", ephemeral=True
            )
            return
        shop_view = ShopSettingsView(self.cog, interaction.guild_id)
        await interaction.response.edit_message(
            embed=await shop_view.create_embed(),
            view=shop_view,
        )


class ShopItemsView(discord.ui.View):
    """Shop items management view."""

    def __init__(self, cog: ShopCfgCog):
        super().__init__(timeout=None)
        self.cog = cog
        self.items_per_page = 25

    @staticmethod
    def build_embed() -> discord.Embed:
        embed = discord.Embed(
            title="📦 Shop Items Management",
            description="Manage shop inventory items",
            color=discord.Color.blue(),
        )
        embed.add_field(name="➕ Add Item", value="Add a new item to the shop", inline=True)
        embed.add_field(name="✏️ Edit Item", value="Edit an existing item", inline=True)
        embed.add_field(name="🗑️ Remove Item", value="Remove an item from the shop", inline=True)
        embed.add_field(name="📋 List Items", value="View all shop items (paginated)", inline=True)
        return embed

    @discord.ui.button(label="➕ Add Item", style=discord.ButtonStyle.success, row=1)
    async def add_item_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission.", ephemeral=True
            )
            return
        await interaction.response.send_modal(AddShopItemModal(self.cog))

    @discord.ui.button(label="✏️ Edit Item", style=discord.ButtonStyle.primary, row=1)
    async def edit_item_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission.", ephemeral=True
            )
            return
        items = await shop_db.get_store_items(interaction.guild_id, enabled_only=False)
        if not items:
            await interaction.response.edit_message(
                content="No items in the shop to edit.", embed=None, view=None
            )
            return
        view = EditItemSelectView(self.cog, items)
        await interaction.response.edit_message(
            content=None, embed=view._build_embed(), view=view
        )

    @discord.ui.button(label="🗑️ Remove Item", style=discord.ButtonStyle.danger, row=1)
    async def remove_item_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission.", ephemeral=True
            )
            return
        items = await shop_db.get_store_items(interaction.guild_id, enabled_only=False)
        if not items:
            await interaction.response.edit_message(
                content="No items in the shop to remove.", embed=None, view=None
            )
            return
        view = RemoveItemSelectView(self.cog, items)
        await interaction.response.edit_message(
            content=None, embed=view._build_embed(), view=view
        )

    @discord.ui.button(label="📋 List Items", style=discord.ButtonStyle.secondary, row=2)
    async def list_items_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission.", ephemeral=True
            )
            return
        items = await shop_db.get_store_items(interaction.guild_id, enabled_only=False)
        if not items:
            await interaction.response.edit_message(
                content="No items in the shop.", embed=None, view=None
            )
            return
        view = ShopItemsPaginationView(self.cog, items, 0)
        await interaction.response.edit_message(
            content=None, embed=view._build_embed(0), view=view
        )

    def _build_list_embed(self, items: list, page: int) -> discord.Embed:
        start = page * self.items_per_page
        end = start + self.items_per_page
        page_items = items[start:end]

        embed = discord.Embed(title="📋 Shop Items", color=discord.Color.blue())
        embed.set_footer(text="✨ = quality selection | 🔵 = blueprint select")
        lines = []
        for item in page_items:
            status = "✅" if item.get("enabled") else "❌"
            q_tag = " ✨" if item.get("supports_quality") else ""
            b_tag = " 🔵" if item.get("allow_blueprint_select") else ""
            lines.append(
                f"{status} **{item['name']}**{q_tag}{b_tag} — "
                f"{item['cost']:,} coins ({item['category']})"
            )
        embed.description = "\n".join(lines)
        total_pages = (len(items) + self.items_per_page - 1) // self.items_per_page
        embed.add_field(
            name="Page", value=f"{page + 1}/{total_pages} • {len(items)} items", inline=False
        )
        return embed

    @discord.ui.button(label="« Back", style=discord.ButtonStyle.secondary, row=3)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None, embed=self.cog._build_main_embed(), view=ShopCfgMainView(self.cog)
        )


class ShopItemsPaginationView(discord.ui.View):
    """Pagination view for shop items list."""

    def __init__(self, cog: ShopCfgCog, items: list, page: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.items = items
        self.page = page
        self.items_per_page = 25
        self.total_pages = (len(items) + self.items_per_page - 1) // self.items_per_page

    def _build_embed(self, page: int) -> discord.Embed:
        start = page * self.items_per_page
        end = start + self.items_per_page
        page_items = self.items[start:end]

        embed = discord.Embed(title="📋 Shop Items", color=discord.Color.blue())
        embed.set_footer(text="✨ = quality selection | 🔵 = blueprint select")
        lines = []
        for item in page_items:
            status = "✅" if item.get("enabled") else "❌"
            q_tag = " ✨" if item.get("supports_quality") else ""
            b_tag = " 🔵" if item.get("allow_blueprint_select") else ""
            lines.append(
                f"{status} **{item['name']}**{q_tag}{b_tag} — "
                f"{item['cost']:,} coins ({item['category']})"
            )
        embed.description = "\n".join(lines)
        embed.add_field(
            name="Page",
            value=f"{page + 1}/{self.total_pages} • {len(self.items)} items",
            inline=False,
        )
        return embed

    @discord.ui.button(label="⏮️ First", style=discord.ButtonStyle.secondary, disabled=True)
    async def first_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.page = 0
        self.first_button.disabled = True
        self.prev_button.disabled = True
        self.next_button.disabled = self.total_pages <= 1
        self.last_button.disabled = self.total_pages <= 1
        await interaction.response.edit_message(embed=self._build_embed(0), view=self)

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary, disabled=True)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        new_page = max(0, self.page - 1)
        self.page = new_page
        self.first_button.disabled = new_page == 0
        self.prev_button.disabled = new_page == 0
        self.next_button.disabled = False
        self.last_button.disabled = False
        await interaction.response.edit_message(embed=self._build_embed(new_page), view=self)

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        new_page = self.page + 1
        if new_page < self.total_pages:
            self.page = new_page
            self.first_button.disabled = False
            self.prev_button.disabled = False
            self.next_button.disabled = new_page >= self.total_pages - 1
            self.last_button.disabled = new_page >= self.total_pages - 1
            await interaction.response.edit_message(embed=self._build_embed(new_page), view=self)

    @discord.ui.button(label="⏭️ Last", style=discord.ButtonStyle.secondary)
    async def last_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        new_page = self.total_pages - 1
        self.page = new_page
        self.first_button.disabled = False
        self.prev_button.disabled = False
        self.next_button.disabled = True
        self.last_button.disabled = True
        await interaction.response.edit_message(embed=self._build_embed(new_page), view=self)

    @discord.ui.button(label="« Back", style=discord.ButtonStyle.secondary)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None, embed=ShopItemsView.build_embed(), view=ShopItemsView(self.cog)
        )


# ---------------------------------------------------------------------------
# Add Item Modal and Confirmation View
# ---------------------------------------------------------------------------

class AddShopItemModal(discord.ui.Modal, title="Add Shop Item"):
    def __init__(self, cog: ShopCfgCog):
        super().__init__()
        self.cog = cog
        self.name = discord.ui.TextInput(
            label="Item Name", placeholder="e.g., Golden King"
        )
        self.description = discord.ui.TextInput(
            label="Description",
            placeholder="Item description shown in shop",
            style=discord.TextStyle.paragraph,
            required=False,
        )
        self.cost = discord.ui.TextInput(label="Cost (coins)", placeholder="100")
        self.ark_command = discord.ui.TextInput(
            label="Blueprint Path",
            placeholder="e.g., Blueprint'/Game/PrimalItem/Test_Item.Test_Item'",
            style=discord.TextStyle.paragraph,
        )
        self.category = discord.ui.TextInput(label="Category", placeholder="general")
        # 5 fields — Discord modal limit
        for field in [self.name, self.description, self.cost, self.ark_command, self.category]:
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cost = int(self.cost.value)
        except ValueError:
            await interaction.response.send_message("❌ Cost must be a number.", ephemeral=True)
            return

        view = AddShopItemConfirmView(
            cog=self.cog,
            name=self.name.value,
            description=self.description.value,
            cost=cost,
            ark_command=self.ark_command.value,
            category=self.category.value,
            guild_id=interaction.guild_id,
            bot=interaction.client,
        )
        await interaction.response.edit_message(content=None, embed=view._build_embed(), view=view)


class AddShopItemConfirmView(discord.ui.View):
    """Confirmation view before adding a shop item, with quality/blueprint toggle buttons."""

    def __init__(
        self,
        cog: ShopCfgCog,
        name: str,
        description: str,
        cost: int,
        ark_command: str,
        category: str,
        guild_id: int,
        bot=None,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.name = name
        self.description = description
        self.cost = cost
        self.ark_command = ark_command
        self.category = category
        self.guild_id = guild_id
        self.bot = bot
        self.supports_quality = False
        self.allow_blueprint_select = False

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Confirm Add Shop Item",
            description=f"Add **{self.name}** to the shop?",
            color=discord.Color.yellow(),
        )
        embed.add_field(name="Cost", value=f"{self.cost:,} coins", inline=True)
        embed.add_field(name="Category", value=self.category or "general", inline=True)
        embed.add_field(
            name="Supports Quality",
            value="✅ Yes" if self.supports_quality else "❌ No",
            inline=True,
        )
        embed.add_field(
            name="Blueprint Select",
            value="✅ Yes" if self.allow_blueprint_select else "❌ No",
            inline=True,
        )
        if self.description:
            embed.add_field(name="Description", value=self.description[:200], inline=False)
        if self.ark_command:
            embed.add_field(name="Blueprint Path", value=f"`{self.ark_command[:100]}`", inline=False)
        return embed

    @discord.ui.button(label="🎯 Quality: Off", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_quality_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.supports_quality = not self.supports_quality
        button.label = f"🎯 Quality: {'On ✅' if self.supports_quality else 'Off ❌'}"
        button.style = (
            discord.ButtonStyle.success if self.supports_quality else discord.ButtonStyle.secondary
        )
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="🔵 Blueprint Select: Off", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_blueprint_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.allow_blueprint_select = not self.allow_blueprint_select
        button.label = f"🔵 Blueprint Select: {'On ✅' if self.allow_blueprint_select else 'Off ❌'}"
        button.style = (
            discord.ButtonStyle.success
            if self.allow_blueprint_select
            else discord.ButtonStyle.secondary
        )
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="✅ Confirm Add", style=discord.ButtonStyle.success, row=2)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            item_id = await shop_db.add_store_item(
                guild_id=self.guild_id,
                name=self.name,
                description=self.description or "",
                cost=self.cost,
                ark_command=self.ark_command,
                category=self.category or "general",
                supports_quality=self.supports_quality,
                allow_blueprint_select=self.allow_blueprint_select,
            )
            embed = discord.Embed(
                title="✅ Item Added",
                description=f"Added **{self.name}** to shop",
                color=discord.Color.green(),
            )
            embed.add_field(name="Cost", value=f"{self.cost:,} coins", inline=True)
            embed.add_field(name="Category", value=self.category or "general", inline=True)
            embed.add_field(
                name="Supports Quality", value="✅" if self.supports_quality else "❌", inline=True
            )
            embed.add_field(
                name="Blueprint Select",
                value="✅" if self.allow_blueprint_select else "❌",
                inline=True,
            )
            await interaction.response.edit_message(
                embed=embed, view=BackToShopItemsView(self.cog)
            )
            if self.bot:
                await _log_to_admin_channel(
                    self.bot,
                    self.guild_id,
                    f"[Shop] Added shop item: **{self.name}** (ID: #{item_id}) - "
                    f"{self.cost:,} coins ({self.category or 'general'})",
                )
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None, embed=ShopItemsView.build_embed(), view=ShopItemsView(self.cog)
        )


class BackToShopItemsView(discord.ui.View):
    """Simple single-button view for returning to ShopItemsView."""

    def __init__(self, cog: ShopCfgCog):
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="↩️ Back to Items", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None, embed=ShopItemsView.build_embed(), view=ShopItemsView(self.cog)
        )


# ---------------------------------------------------------------------------
# Edit Item — paginated list with dropdown
# ---------------------------------------------------------------------------

class EditItemSelectView(discord.ui.View):
    """Paginated view for editing shop items."""

    def __init__(self, cog: ShopCfgCog, items: list, page: int = 0):
        super().__init__(timeout=None)
        self.cog = cog
        self.items = items
        self.page = page
        self.items_per_page = 25
        self.total_pages = (len(items) + self.items_per_page - 1) // self.items_per_page

        self._build_select()

    def _get_page_items(self):
        start = self.page * self.items_per_page
        end = min(start + self.items_per_page, len(self.items))
        return self.items[start:end]

    def _build_embed(self):
        page_items = self._get_page_items()[:20]  # Limit to 20 for embed to stay under 1024 chars
        embed = discord.Embed(
            title="✏️ Edit Shop Item",
            description="Select an item to edit from the dropdown below",
            color=discord.Color.blue(),
        )
        lines = []
        for item in page_items:
            status = "✅" if item.get("enabled") else "❌"
            lines.append(f"{status} **{item['name']}** — {item['cost']:,} coins")
        embed.add_field(
            name=f"Items (Page {self.page + 1}/{self.total_pages})",
            value="\n".join(lines) or "No items",
            inline=False,
        )
        return embed

    def _build_select(self):
        # Remove old select if exists
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)

        page_items = self._get_page_items()
        options = [
            discord.SelectOption(
                label=f"{item['name'][:90]}",
                value=str(item["item_id"]),
            )
            for item in page_items
        ]
        if options:
            select = discord.ui.Select(
                placeholder=f"Select item to edit (Page {self.page + 1}/{self.total_pages})",
                min_values=1,
                max_values=1,
                options=options,
            )
            select.callback = self._on_select
            self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        item_id = int(interaction.data["values"][0])
        item = await shop_db.get_store_item(item_id)
        if not item or item["guild_id"] != interaction.guild_id:
            await interaction.response.send_message("❌ Item not found.", ephemeral=True)
            return
        await interaction.response.send_modal(EditShopItemModal(item, self.cog))

    @discord.ui.button(label="⏮️ First", style=discord.ButtonStyle.secondary)
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self._build_select()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self._build_select()
            await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            self.page += 1
            self._build_select()
            await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="⏭️ Last", style=discord.ButtonStyle.secondary)
    async def last_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.total_pages - 1
        self._build_select()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="« Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None, embed=ShopItemsView.build_embed(), view=ShopItemsView(self.cog)
        )


class EditShopItemModal(discord.ui.Modal):
    def __init__(self, item: dict, cog: ShopCfgCog):
        item_name = item.get("name", "Item")
        super().__init__(title=f"Edit: {item_name}")
        self.item = item  # preserved — loop variable renamed to 'field' below
        self.cog = cog

        self.enabled = discord.ui.TextInput(
            label="Enabled (yes/no)",
            default="yes" if item.get("enabled") else "no",
            placeholder="yes or no",
        )
        self.description = discord.ui.TextInput(
            label="Description",
            default=item.get("description", ""),
            style=discord.TextStyle.paragraph,
            required=False,
        )
        self.cost = discord.ui.TextInput(
            label="Cost (coins)",
            default=str(item.get("cost", 0)),
        )
        self.ark_command = discord.ui.TextInput(
            label="ARK Command / Blueprint",
            default=item.get("ark_command", ""),
            style=discord.TextStyle.paragraph,
        )
        self.category = discord.ui.TextInput(
            label="Category",
            default=item.get("category", "general"),
        )
        for field in [self.enabled, self.description, self.cost, self.ark_command, self.category]:
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cost = int(self.cost.value)
        except ValueError:
            await interaction.response.send_message("❌ Cost must be a number.", ephemeral=True)
            return

        enabled = 1 if self.enabled.value.lower() in ("yes", "y", "true", "1") else 0

        await shop_db.update_store_item(
            self.item["item_id"],
            description=self.description.value or "",
            cost=cost,
            ark_command=self.ark_command.value,
            category=self.category.value or "general",
            enabled=enabled,
        )

        item_name = self.item.get("name", "Item")

        # Load current quality/blueprint state for the result view
        updated_item = await shop_db.get_store_item(self.item["item_id"])
        supports_quality = bool(updated_item.get("supports_quality", False)) if updated_item else False
        allow_blueprint_select = (
            bool(updated_item.get("allow_blueprint_select", False)) if updated_item else False
        )

        view = EditShopItemResultView(
            cog=self.cog,
            item_id=self.item["item_id"],
            item_name=item_name,
            supports_quality=supports_quality,
            allow_blueprint_select=allow_blueprint_select,
        )
        await interaction.response.edit_message(content=None, embed=view._build_embed(), view=view)


class EditShopItemResultView(discord.ui.View):
    """Post-edit result view with quality/blueprint toggle buttons."""

    def __init__(
        self,
        cog: ShopCfgCog,
        item_id: int,
        item_name: str,
        supports_quality: bool,
        allow_blueprint_select: bool,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.item_id = item_id
        self.item_name = item_name
        self.supports_quality = supports_quality
        self.allow_blueprint_select = allow_blueprint_select

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"✅ Updated: {self.item_name}",
            description="Toggle quality/blueprint options below, then go back to items.",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Supports Quality",
            value="✅ Yes" if self.supports_quality else "❌ No",
            inline=True,
        )
        embed.add_field(
            name="Blueprint Select",
            value="✅ Yes" if self.allow_blueprint_select else "❌ No",
            inline=True,
        )
        return embed

    @discord.ui.button(label="🎯 Toggle Quality", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_quality_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.supports_quality = not self.supports_quality
        await shop_db.update_store_item(
            self.item_id, supports_quality=1 if self.supports_quality else 0
        )
        button.style = (
            discord.ButtonStyle.success if self.supports_quality else discord.ButtonStyle.secondary
        )
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(
        label="🔵 Toggle Blueprint Select", style=discord.ButtonStyle.secondary, row=1
    )
    async def toggle_blueprint_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.allow_blueprint_select = not self.allow_blueprint_select
        await shop_db.update_store_item(
            self.item_id,
            allow_blueprint_select=1 if self.allow_blueprint_select else 0,
        )
        button.style = (
            discord.ButtonStyle.success
            if self.allow_blueprint_select
            else discord.ButtonStyle.secondary
        )
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="↩️ Back to Items", style=discord.ButtonStyle.secondary, row=2)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None, embed=ShopItemsView.build_embed(), view=ShopItemsView(self.cog)
        )


# ---------------------------------------------------------------------------
# Remove Item — dynamic select with items list
# ---------------------------------------------------------------------------

class RemoveItemSelectView(discord.ui.View):
    """Paginated view for removing shop items."""

    def __init__(self, cog: ShopCfgCog, items: list, page: int = 0):
        super().__init__(timeout=None)
        self.cog = cog
        self.items = items
        self.page = page
        self.items_per_page = 25
        self.total_pages = (len(items) + self.items_per_page - 1) // self.items_per_page

        self._build_select()

    def _get_page_items(self):
        start = self.page * self.items_per_page
        end = min(start + self.items_per_page, len(self.items))
        return self.items[start:end]

    def _build_embed(self):
        page_items = self._get_page_items()[:20]
        embed = discord.Embed(
            title="🗑️ Remove Shop Item",
            description="Select an item to remove from the shop",
            color=discord.Color.blue(),
        )
        lines = []
        for item in page_items:
            status = "✅" if item.get("enabled") else "❌"
            lines.append(f"{status} **{item['name']}** — {item['cost']:,} coins")
        embed.add_field(
            name=f"Items (Page {self.page + 1}/{self.total_pages})",
            value="\n".join(lines) or "No items",
            inline=False,
        )
        return embed

    def _build_select(self):
        # Remove old select if exists
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)

        page_items = self._get_page_items()
        options = [
            discord.SelectOption(
                label=f"{item['name'][:90]}",
                value=str(item["item_id"]),
            )
            for item in page_items
        ]
        if options:
            select = discord.ui.Select(
                placeholder=f"Select item to remove (Page {self.page + 1}/{self.total_pages})",
                min_values=1,
                max_values=1,
                options=options,
            )
            select.callback = self._on_select
            self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        item_id = int(interaction.data["values"][0])
        item = await shop_db.get_store_item(item_id)
        if not item or item["guild_id"] != interaction.guild_id:
            await interaction.response.send_message("❌ Item not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Confirm Remove Shop Item",
            description=f"Remove **{item['name']}** from the shop?",
            color=discord.Color.red(),
        )
        embed.add_field(name="Cost", value=f"{item.get('cost', 0):,} coins", inline=True)
        embed.add_field(name="Category", value=item.get("category", "general"), inline=True)

        view = RemoveShopItemConfirmView(
            item_id, item["name"], interaction.guild_id, interaction.client, self.cog
        )
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @discord.ui.button(label="⏮️ First", style=discord.ButtonStyle.secondary)
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        self._build_select()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self._build_select()
            await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages - 1:
            self.page += 1
            self._build_select()
            await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="⏭️ Last", style=discord.ButtonStyle.secondary)
    async def last_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.total_pages - 1
        self._build_select()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="« Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None, embed=ShopItemsView.build_embed(), view=ShopItemsView(self.cog)
        )


class RemoveShopItemConfirmView(discord.ui.View):
    """Confirmation view before removing a shop item."""

    def __init__(
        self, item_id: int, item_name: str, guild_id: int, bot=None, cog: ShopCfgCog = None
    ):
        super().__init__(timeout=120)
        self.item_id = item_id
        self.item_name = item_name
        self.guild_id = guild_id
        self.bot = bot
        self.cog = cog

    @discord.ui.button(label="✅ Confirm Remove", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await shop_db.delete_store_item(self.item_id)
            embed = discord.Embed(
                title="✅ Item Removed",
                description=f"Removed **{self.item_name}** from shop",
                color=discord.Color.red(),
            )
            await interaction.response.edit_message(
                embed=embed, view=BackToShopItemsView(self.cog)
            )
            if self.bot:
                await _log_to_admin_channel(
                    self.bot,
                    self.guild_id,
                    f"[Shop] Removed shop item: **{self.item_name}** (ID: #{self.item_id})",
                )
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=None, embed=ShopItemsView.build_embed(), view=ShopItemsView(self.cog)
        )


# ---------------------------------------------------------------------------
# Shop Settings View
# ---------------------------------------------------------------------------

class ShopSettingsView(discord.ui.View):
    """Shop settings view."""

    def __init__(self, cog: ShopCfgCog, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id

    async def create_embed(self) -> discord.Embed:
        """Create shop settings embed."""
        from bot.database import shop_db

        config = await shop_db.get_shop_config(self.guild_id)
        enabled = config.get("shop_enabled", True)
        items_per_page = config.get("items_per_page", 4)

        embed = discord.Embed(
            title="⚙️ Shop Settings",
            description="Configure shop behavior and requirements.",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Shop Enabled", value="✅ Yes" if enabled else "❌ No", inline=True)
        embed.add_field(name="Items Per Page", value=str(items_per_page), inline=True)
        embed.add_field(
            name="📝 Bulk Shop Management",
            value=(
                "**Quick Setup:**\n"
                "1. `/downloadsample` - Download shop template CSV\n"
                "2. Edit the CSV with your items and prices\n"
                "3. `/uploadshop` - Upload your configured shop\n\n"
                "This is the fastest way to add many items at once!"
            ),
            inline=False,
        )
        return embed

    @discord.ui.button(label="✏️ Edit Settings", style=discord.ButtonStyle.primary)
    async def edit_settings_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission.", ephemeral=True
            )
            return

        from bot.database import shop_db
        config = await shop_db.get_shop_config(self.guild_id)
        await interaction.response.send_modal(ShopSettingsModal(self.guild_id, config))

    @discord.ui.button(label="« Back", style=discord.ButtonStyle.secondary)
    async def back_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.edit_message(
            content=None, embed=self.cog._build_main_embed(), view=ShopCfgMainView(self.cog)
        )


class ShopSettingsModal(discord.ui.Modal, title="Shop Settings"):
    def __init__(self, guild_id: int, config: dict = None):
        super().__init__()
        self.guild_id = guild_id

        # Pre-fill with current values
        current_enabled = "yes" if config and config.get("shop_enabled", True) else "no"
        current_items = str(config.get("items_per_page", 4)) if config else "4"

        self.enabled = discord.ui.TextInput(
            label="Shop Enabled (yes/no)",
            placeholder="yes",
            default=current_enabled,
            required=False,
        )
        self.items_per_page = discord.ui.TextInput(
            label="Items Per Page (1-25)",
            placeholder="4 (max 25)",
            default=current_items,
            required=False,
        )
        for field in [self.enabled, self.items_per_page]:
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        updates = {}

        if self.enabled.value:
            val = self.enabled.value.lower()
            if val in ("yes", "y", "true", "1"):
                updates["shop_enabled"] = 1
            elif val in ("no", "n", "false", "0"):
                updates["shop_enabled"] = 0

        if self.items_per_page.value:
            try:
                val = int(self.items_per_page.value)
                updates["items_per_page"] = min(25, max(1, val))
            except ValueError:
                pass

        if updates:
            await shop_db.update_shop_config(self.guild_id, **updates)

        await interaction.response.send_message("✅ Settings updated!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCfgCog(bot))
