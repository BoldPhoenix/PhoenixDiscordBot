"""
Kits Management GUI - Interactive interface for managing starter kits.
Provides visual tools for creating, editing, and deleting kits.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button, Modal, TextInput
from typing import Optional, List
import logging
import aiosqlite
import json
from pathlib import Path

from bot.database import server_config_db
from bot.utils.config import Config
from bot.utils.subscription_checker import check_feature

logger = logging.getLogger("KitsGUI")


async def get_all_kits() -> List[dict]:
    """Get all kits from database."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM kits ORDER BY name") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_kit(kit_id: int) -> Optional[dict]:
    """Get a specific kit."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM kits WHERE kit_id = ?", (kit_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_kit(
    name: str, description: str, items: str, cooldown: int, max_claims: int
) -> int:
    """Create a new kit."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "INSERT INTO kits (name, description, items, cooldown_hours, max_claims) VALUES (?, ?, ?, ?, ?)",
            (name, description, items, cooldown, max_claims),
        )
        await db.commit()
        return cursor.lastrowid


async def update_kit(kit_id: int, **kwargs) -> bool:
    """Update a kit."""
    db_path = Path(Config.DATABASE_PATH)
    if not kwargs:
        return False

    set_clauses = [f"{k} = ?" for k in kwargs.keys()]
    values = list(kwargs.values()) + [kit_id]

    async with aiosqlite.connect(db_path) as db:
        await db.execute(f"UPDATE kits SET {', '.join(set_clauses)} WHERE kit_id = ?", values)
        await db.commit()
        return True


async def delete_kit(kit_id: int) -> bool:
    """Delete a kit."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("DELETE FROM kits WHERE kit_id = ?", (kit_id,))
        await db.commit()
        return cursor.rowcount > 0


async def toggle_kit(kit_id: int) -> bool:
    """Toggle kit enabled status."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE kits SET enabled = NOT enabled WHERE kit_id = ?", (kit_id,))
        await db.commit()
        return True


class KitsManagementView(View):
    """Main kits management interface."""

    def __init__(self, guild_id: int, user: discord.User, timeout: int = 300):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.kits = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This management panel is not for you!", ephemeral=True
            )
            return False
        return True

    async def load_data(self):
        """Load kits from database."""
        self.kits = await get_all_kits()

    def create_main_embed(self) -> discord.Embed:
        """Create the main kits management embed."""
        embed = discord.Embed(
            title="📦 Kits Management Panel",
            description=(
                "Create and manage starter kits for players.\n" f"**Total Kits:** {len(self.kits)}"
            ),
            color=discord.Color.blue(),
        )

        if self.kits:
            for kit in self.kits[:5]:
                status = "✅" if kit.get("enabled", True) else "❌"
                items_count = len(json.loads(kit.get("items", "[]")))

                cooldown = (
                    f"⏱️ {kit['cooldown_hours']}h" if kit.get("cooldown_hours") else "No cooldown"
                )
                max_claims = (
                    f"🎯 Max: {kit['max_claims']}" if kit.get("max_claims") else "Unlimited"
                )

                embed.add_field(
                    name=f"{status} {kit['name']} (ID: {kit['kit_id']})",
                    value=f"📦 {items_count} items | {cooldown} | {max_claims}",
                    inline=False,
                )

            if len(self.kits) > 5:
                embed.add_field(
                    name="", value=f"*...and {len(self.kits) - 5} more kits*", inline=False
                )
        else:
            embed.add_field(
                name="No Kits",
                value="No kits have been created yet. Click 'Create Kit' to add one!",
                inline=False,
            )

        embed.set_footer(text="💡 Use the buttons below to manage kits")
        return embed


class KitsMainView(KitsManagementView):
    """Main kits view with action buttons."""

    def __init__(self, guild_id: int, user: discord.User):
        super().__init__(guild_id, user)

        self.add_item(KitsActionButton("Create Kit", "➕", "create"))
        self.add_item(KitsActionButton("View Kits", "📋", "view"))
        self.add_item(KitsActionButton("Edit Kit", "✏️", "edit"))
        self.add_item(KitsActionButton("Delete Kit", "🗑️", "delete"))
        self.add_item(KitsActionButton("Toggle Kit", "🔄", "toggle"))


class KitsActionButton(Button):
    """Button for kits actions."""

    def __init__(self, label: str, emoji: str, action: str):
        super().__init__(
            style=discord.ButtonStyle.primary, label=label, emoji=emoji, custom_id=f"kits_{action}"
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        view: KitsMainView = self.view

        if self.action == "create":
            modal = CreateKitModal()
            await interaction.response.send_modal(modal)

        elif self.action == "view":
            kits_view = KitsListView(view.guild_id, view.user)
            await kits_view.load_data()
            embed = kits_view.create_list_embed()
            await interaction.response.send_message(embed=embed, view=kits_view, ephemeral=True)

        elif self.action == "edit":
            edit_view = EditKitSelectView(view.guild_id, view.user)
            await edit_view.load_data()
            embed = edit_view.create_select_embed()
            await interaction.response.send_message(embed=embed, view=edit_view, ephemeral=True)

        elif self.action == "delete":
            delete_view = DeleteKitSelectView(view.guild_id, view.user)
            await delete_view.load_data()
            embed = delete_view.create_select_embed()
            await interaction.response.send_message(embed=embed, view=delete_view, ephemeral=True)

        elif self.action == "toggle":
            toggle_view = ToggleKitSelectView(view.guild_id, view.user)
            await toggle_view.load_data()
            embed = toggle_view.create_select_embed()
            await interaction.response.send_message(embed=embed, view=toggle_view, ephemeral=True)


class CreateKitModal(Modal):
    """Modal for creating a new kit."""

    def __init__(self):
        super().__init__(title="➕ Create Starter Kit")

        self.kit_name = TextInput(
            label="Kit Name", placeholder="e.g., Starter Kit, VIP Kit", required=True, max_length=50
        )
        self.add_item(self.kit_name)

        self.description = TextInput(
            label="Description",
            placeholder="A basic starter kit for new players",
            required=True,
            max_length=200,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.description)

        self.items = TextInput(
            label="Items (JSON array)",
            placeholder='[{"blueprint": "/Game/...", "quantity": 1}]',
            required=True,
            max_length=2000,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.items)

        self.cooldown = TextInput(
            label="Cooldown (hours, 0 = none)",
            placeholder="24",
            required=True,
            max_length=5,
            default="0",
        )
        self.add_item(self.cooldown)

        self.max_claims = TextInput(
            label="Max Claims (0 = unlimited)",
            placeholder="1",
            required=True,
            max_length=5,
            default="0",
        )
        self.add_item(self.max_claims)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate JSON
            items_list = json.loads(self.items.value)
            if not isinstance(items_list, list):
                raise ValueError("Items must be a JSON array")

            cooldown = int(self.cooldown.value)
            max_claims = int(self.max_claims.value)

            if cooldown < 0 or max_claims < 0:
                raise ValueError("Values must be non-negative")

            kit_id = await create_kit(
                name=self.kit_name.value,
                description=self.description.value,
                items=self.items.value,
                cooldown=cooldown,
                max_claims=max_claims,
            )

            embed = discord.Embed(
                title="✅ Kit Created",
                description=f"**{self.kit_name.value}** has been created!",
                color=discord.Color.green(),
            )
            embed.add_field(name="Items", value=f"{len(items_list)} items", inline=True)
            embed.add_field(name="Cooldown", value=f"{cooldown} hours", inline=True)
            embed.add_field(
                name="Max Claims",
                value=str(max_claims) if max_claims > 0 else "Unlimited",
                inline=True,
            )
            embed.set_footer(text=f"Kit ID: {kit_id}")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except json.JSONDecodeError:
            await interaction.response.send_message(
                "❌ Invalid JSON format for items!\n\n"
                "**Example format:**\n"
                '```json\n[{"blueprint": "/Game/PrimalEarth/...", "quantity": 1, "quality": 0}]\n```',
                ephemeral=True,
            )
        except ValueError as e:
            await interaction.response.send_message(f"❌ Invalid values: {e}", ephemeral=True)


class KitsListView(KitsManagementView):
    """View for listing all kits with details."""

    def __init__(self, guild_id: int, user: discord.User):
        super().__init__(guild_id, user)
        self.current_page = 0
        self.items_per_page = 5

        self.add_item(PaginationButton("◀️ Previous", "prev"))
        self.add_item(PaginationButton("Next ▶️", "next"))

    def create_list_embed(self) -> discord.Embed:
        """Create kit list embed."""
        total_pages = max(1, (len(self.kits) + self.items_per_page - 1) // self.items_per_page)
        self.current_page = min(self.current_page, total_pages - 1)

        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_kits = self.kits[start:end]

        embed = discord.Embed(
            title="📋 All Kits",
            description=f"Showing {len(page_kits)} of {len(self.kits)} kits",
            color=discord.Color.blue(),
        )

        for kit in page_kits:
            status = "✅ Enabled" if kit.get("enabled", True) else "❌ Disabled"
            items_count = len(json.loads(kit.get("items", "[]")))

            value = f"**Status:** {status}\n"
            value += f"**Items:** {items_count}\n"
            value += f"**Cooldown:** {kit.get('cooldown_hours', 0)} hours\n"
            value += f"**Max Claims:** {kit.get('max_claims') if kit.get('max_claims') else 'Unlimited'}\n"
            value += f"*{(kit.get('description') or 'No description')[:50]}*"

            embed.add_field(
                name=f"📦 {kit['name']} (ID: {kit['kit_id']})", value=value, inline=False
            )

        if not page_kits:
            embed.add_field(name="No Kits", value="No kits found", inline=False)

        embed.set_footer(text=f"Page {self.current_page + 1}/{total_pages}")
        return embed


class PaginationButton(Button):
    """Button for pagination."""

    def __init__(self, label: str, direction: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=label)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: KitsListView = self.view

        if self.direction == "prev" and view.current_page > 0:
            view.current_page -= 1
        elif self.direction == "next":
            total_pages = max(1, (len(view.kits) + view.items_per_page - 1) // view.items_per_page)
            if view.current_page < total_pages - 1:
                view.current_page += 1

        embed = view.create_list_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class EditKitSelectView(KitsManagementView):
    """View for selecting a kit to edit."""

    def __init__(self, guild_id: int, user: discord.User):
        super().__init__(guild_id, user)

    async def load_data(self):
        """Load kits and add select menu."""
        await super().load_data()

        if self.kits:
            options = []
            for kit in self.kits[:25]:
                options.append(
                    discord.SelectOption(
                        label=kit["name"][:50],
                        description=f"ID: {kit['kit_id']} | {len(json.loads(kit.get('items', '[]')))} items",
                        value=str(kit["kit_id"]),
                    )
                )

            select = Select(
                placeholder="Select a kit to edit...", options=options, custom_id="edit_kit_select"
            )
            select.callback = self.kit_selected
            self.add_item(select)

    async def kit_selected(self, interaction: discord.Interaction):
        """Handle kit selection for editing."""
        kit_id = int(interaction.data["values"][0])
        kit = await get_kit(kit_id)

        if kit:
            modal = EditKitModal(kit)
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message("❌ Kit not found!", ephemeral=True)

    def create_select_embed(self) -> discord.Embed:
        """Create kit selection embed."""
        embed = discord.Embed(
            title="✏️ Edit Kit",
            description="Select a kit from the dropdown to edit it.",
            color=discord.Color.blue(),
        )
        return embed


class EditKitModal(Modal):
    """Modal for editing an existing kit."""

    def __init__(self, kit: dict):
        super().__init__(title=f"✏️ Edit: {kit['name'][:30]}")
        self.kit_id = kit["kit_id"]

        self.kit_name = TextInput(
            label="Kit Name", default=kit["name"], required=True, max_length=50
        )
        self.add_item(self.kit_name)

        self.description = TextInput(
            label="Description",
            default=kit.get("description", ""),
            required=True,
            max_length=200,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.description)

        self.cooldown = TextInput(
            label="Cooldown (hours)",
            default=str(kit.get("cooldown_hours", 0)),
            required=True,
            max_length=5,
        )
        self.add_item(self.cooldown)

        self.max_claims = TextInput(
            label="Max Claims (0 = unlimited)",
            default=str(kit.get("max_claims", 0)),
            required=True,
            max_length=5,
        )
        self.add_item(self.max_claims)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cooldown = int(self.cooldown.value)
            max_claims = int(self.max_claims.value)

            if cooldown < 0 or max_claims < 0:
                raise ValueError("Values must be non-negative")

            await update_kit(
                self.kit_id,
                name=self.kit_name.value,
                description=self.description.value,
                cooldown_hours=cooldown,
                max_claims=max_claims,
            )

            embed = discord.Embed(
                title="✅ Kit Updated",
                description=f"**{self.kit_name.value}** has been updated!",
                color=discord.Color.green(),
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid values! Please enter valid numbers.", ephemeral=True
            )


class DeleteKitSelectView(KitsManagementView):
    """View for selecting a kit to delete."""

    def __init__(self, guild_id: int, user: discord.User):
        super().__init__(guild_id, user)

    async def load_data(self):
        """Load kits and add select menu."""
        await super().load_data()

        if self.kits:
            options = []
            for kit in self.kits[:25]:
                options.append(
                    discord.SelectOption(
                        label=kit["name"][:50],
                        description=f"ID: {kit['kit_id']}",
                        value=str(kit["kit_id"]),
                    )
                )

            select = Select(
                placeholder="Select a kit to delete...",
                options=options,
                custom_id="delete_kit_select",
            )
            select.callback = self.kit_selected
            self.add_item(select)

    async def kit_selected(self, interaction: discord.Interaction):
        """Handle kit selection for deletion."""
        kit_id = int(interaction.data["values"][0])
        kit = await get_kit(kit_id)

        if kit:
            confirm_view = ConfirmDeleteView(kit)
            embed = discord.Embed(
                title="⚠️ Confirm Deletion",
                description=f"Are you sure you want to delete **{kit['name']}**?",
                color=discord.Color.red(),
            )
            embed.add_field(name="⚠️ Warning", value="This cannot be undone!", inline=False)
            await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Kit not found!", ephemeral=True)

    def create_select_embed(self) -> discord.Embed:
        """Create kit deletion selection embed."""
        embed = discord.Embed(
            title="🗑️ Delete Kit",
            description="Select a kit from the dropdown to delete it.",
            color=discord.Color.red(),
        )
        return embed


class ConfirmDeleteView(View):
    """Confirmation view for kit deletion."""

    def __init__(self, kit: dict):
        super().__init__(timeout=None)
        self.kit = kit

    @discord.ui.button(label="Yes, Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        success = await delete_kit(self.kit["kit_id"])

        if success:
            embed = discord.Embed(
                title="✅ Kit Deleted",
                description=f"**{self.kit['name']}** has been deleted.",
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title="❌ Error", description="Failed to delete kit.", color=discord.Color.red()
            )

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            content="❌ Deletion cancelled.", embed=None, view=None
        )


class ToggleKitSelectView(KitsManagementView):
    """View for toggling kit enabled status."""

    def __init__(self, guild_id: int, user: discord.User):
        super().__init__(guild_id, user)

    async def load_data(self):
        """Load kits and add select menu."""
        await super().load_data()

        if self.kits:
            options = []
            for kit in self.kits[:25]:
                status = "✅" if kit.get("enabled", True) else "❌"
                options.append(
                    discord.SelectOption(
                        label=f"{status} {kit['name'][:45]}",
                        description=f"Click to toggle",
                        value=str(kit["kit_id"]),
                    )
                )

            select = Select(
                placeholder="Select a kit to toggle...",
                options=options,
                custom_id="toggle_kit_select",
            )
            select.callback = self.kit_selected
            self.add_item(select)

    async def kit_selected(self, interaction: discord.Interaction):
        """Handle kit selection for toggling."""
        kit_id = int(interaction.data["values"][0])
        kit = await get_kit(kit_id)

        if kit:
            await toggle_kit(kit_id)
            new_status = not kit.get("enabled", True)

            embed = discord.Embed(
                title="✅ Kit Toggled",
                description=f"**{kit['name']}** is now {'✅ Enabled' if new_status else '❌ Disabled'}",
                color=discord.Color.green(),
            )
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.send_message("❌ Kit not found!", ephemeral=True)

    def create_select_embed(self) -> discord.Embed:
        """Create toggle selection embed."""
        embed = discord.Embed(
            title="🔄 Toggle Kit",
            description="Select a kit to enable/disable it.",
            color=discord.Color.blue(),
        )
        return embed


class KitsGUI(commands.Cog):
    """Interactive kits management GUI."""

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
        name="kitsmgmt", description="📦 Interactive kits management panel (admin only)"
    )
    async def kits_mgmt(self, interaction: discord.Interaction):
        """Open the interactive kits management GUI."""
        if not await check_feature(interaction, "kits"):
            return
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        view = KitsMainView(interaction.guild_id, interaction.user)
        await view.load_data()
        embed = view.create_main_embed()

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(KitsGUI(bot))
