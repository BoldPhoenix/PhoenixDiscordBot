"""
Kit Management GUI Cog.
Provides admin interface for creating and managing starter kits.
"""

import logging
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

from bot.database import kit_db, server_config_db
from bot.utils.subscription_checker import check_feature
from bot.utils.arkids_api import get_arkids_client

logger = logging.getLogger("KitManagementCog")

QUALITY_CHOICES = [
    app_commands.Choice(name="Primitive (1)", value=1),
    app_commands.Choice(name="Ramshackle (2)", value=2),
    app_commands.Choice(name="Apprentice (4)", value=4),
    app_commands.Choice(name="Journeyman (6)", value=6),
    app_commands.Choice(name="Mastercraft (8)", value=8),
    app_commands.Choice(name="Ascendant (10)", value=10),
]

QUALITY_NAMES = {
    1: "Primitive",
    2: "Ramshackle",
    4: "Apprentice",
    6: "Journeyman",
    8: "Mastercraft",
    10: "Ascendant",
}


async def _log_to_admin_channel(bot, guild_id: int, message: str):
    """Send a message to the guild's configured admin log channel."""
    try:
        config = await server_config_db.get_server_config(guild_id)
        if not config:
            logger.warning("No config found for guild %s", guild_id)
            return
        channel_id = config.get("admin_log_channel_id")
        if not channel_id:
            logger.warning("admin_log_channel_id not configured for guild %s", guild_id)
            return
        channel = bot.get_channel(int(channel_id))
        if not channel:
            logger.warning("Admin log channel %s not found for guild %s", channel_id, guild_id)
            return
        await channel.send(message)
    except Exception as e:
        logger.error("Failed to send to admin log channel: %s", e)


class KitManagementCog(commands.Cog):
    """Kit management GUI."""

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
    # Main Kit Config Command
    # ---------------------------------------------------------------------------

    @app_commands.command(name="kitcfg", description="🎁 Configure starter kits (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def kitcfg_command(self, interaction: discord.Interaction):
        """Main kit configuration command with GUI."""
        if not await check_feature(interaction, "kits"):
            return
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.",
                ephemeral=True,
            )
            return
        
        kits = await kit_db.get_all_kits(interaction.guild.id)
        await interaction.response.send_message(
            embed=await self._build_main_embed(interaction.guild.id, kits),
            view=KitCfgMainView(self, kits),
            ephemeral=True,
        )

    @kitcfg_command.error
    async def kitcfg_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ {error}", ephemeral=True)

    async def _build_main_embed(self, guild_id: int, kits: List[dict]) -> discord.Embed:
        """Build the main kit configuration embed."""
        from bot.database import subscription_db
        
        sub = await subscription_db.get_or_create_subscription(guild_id)
        tier = subscription_db.get_effective_tier(sub)
        
        # Tier limits
        limits = {"free": 2, "premium": 10, "lifetime": 10}
        max_kits = limits.get(tier, 2)
        
        embed = discord.Embed(
            title="🎁 Kit Configuration",
            description=f"Manage starter kits for your server\n**Tier**: {tier.title()} ({len(kits)}/{max_kits} kits)",
            color=discord.Color.blue(),
        )
        
        if kits:
            kit_list = []
            for kit in kits[:10]:  # Show first 10
                status = "✅" if kit["enabled"] else "❌"
                cooldown = f"{kit['cooldown_hours']}h" if kit['cooldown_hours'] > 0 else "One-time"
                kit_list.append(f"{status} **{kit['kit_name']}** - {cooldown}")
            embed.add_field(
                name=f"📦 Kits ({len(kits)})",
                value="\n".join(kit_list) if kit_list else "No kits configured",
                inline=False,
            )
        else:
            embed.add_field(
                name="📦 Kits",
                value="No kits configured. Click **Create Kit** to get started!",
                inline=False,
            )
        
        embed.set_footer(text="Use the buttons below to manage kits")
        return embed


# ---------------------------------------------------------------------------
# Main View
# ---------------------------------------------------------------------------

class KitCfgMainView(discord.ui.View):
    """Main kit configuration view."""

    def __init__(self, cog: KitManagementCog, kits: List[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.kits = kits

    @discord.ui.button(label="Create Kit", style=discord.ButtonStyle.green, emoji="➕")
    async def create_kit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Create a new kit."""
        # Check tier limits
        from bot.database import subscription_db
        
        sub = await subscription_db.get_or_create_subscription(interaction.guild.id)
        tier = subscription_db.get_effective_tier(sub)
        limits = {"free": 2, "premium": 10, "lifetime": 10}
        max_kits = limits.get(tier, 2)
        
        current_count = await kit_db.count_kits(interaction.guild.id)
        if current_count >= max_kits:
            await interaction.response.send_message(
                f"❌ You've reached your kit limit ({max_kits} kits for {tier} tier).\n"
                f"Upgrade to Premium for more kits: `/subscribe`",
                ephemeral=True,
            )
            return
        
        await interaction.response.send_modal(CreateKitModal(self.cog))

    @discord.ui.button(label="Edit Kit", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_kit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Edit an existing kit."""
        if not self.kits:
            await interaction.response.send_message("❌ No kits to edit.", ephemeral=True)
            return
        
        await interaction.response.edit_message(
            content="Select a kit to edit:",
            embed=None,
            view=KitSelectView(self.cog, self.kits, action="edit"),
        )

    @discord.ui.button(label="Delete Kit", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_kit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Delete a kit."""
        if not self.kits:
            await interaction.response.send_message("❌ No kits to delete.", ephemeral=True)
            return
        
        await interaction.response.edit_message(
            content="Select a kit to delete:",
            embed=None,
            view=KitSelectView(self.cog, self.kits, action="delete"),
        )


# ---------------------------------------------------------------------------
# Edit Kit Menu View
# ---------------------------------------------------------------------------

class EditKitMenuView(discord.ui.View):
    """Menu for choosing what to edit about a kit."""

    def __init__(self, cog: KitManagementCog, kit: dict):
        super().__init__(timeout=300)
        self.cog = cog
        self.kit = kit

    @discord.ui.button(label="Edit Properties", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_properties_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Edit kit properties (name, description, requirements, cooldown)."""
        await interaction.response.send_modal(EditKitModal(self.cog, self.kit))

    @discord.ui.button(label="Manage Items", style=discord.ButtonStyle.primary, emoji="📦")
    async def manage_items_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Manage items in this kit."""
        items = await kit_db.get_kit_items(self.kit['kit_id'])
        await interaction.response.edit_message(
            embed=await self._build_items_embed(self.kit, items),
            view=KitItemsView(self.cog, self.kit, items),
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go back to main menu."""
        kits = await kit_db.get_all_kits(interaction.guild.id)
        await interaction.response.edit_message(
            embed=await self.cog._build_main_embed(interaction.guild.id, kits),
            view=KitCfgMainView(self.cog, kits),
        )

    async def _build_items_embed(self, kit: dict, items: List[dict]) -> discord.Embed:
        """Build embed showing kit items."""
        embed = discord.Embed(
            title=f"📦 {kit['kit_name']} - Items",
            description=kit['description'] or "No description",
            color=discord.Color.blue(),
        )
        
        if items:
            item_list = []
            for item in items:
                quality_name = QUALITY_NAMES.get(item["quality"], "Unknown")
                # Shorten blueprint path for display
                bp = item["item_blueprint"]
                if "/" in bp:
                    bp = bp.split("/")[-1].replace("'", "")
                item_list.append(f"• **{bp}** x{item['quantity']} ({quality_name})")
            
            embed.add_field(
                name=f"Items ({len(items)})",
                value="\n".join(item_list[:20]),  # Show first 20
                inline=False,
            )
        else:
            embed.add_field(
                name="Items",
                value="No items in this kit. Click **Add Item** to get started!",
                inline=False,
            )
        
        return embed


# ---------------------------------------------------------------------------
# Kit Selection View
# ---------------------------------------------------------------------------

class KitSelectView(discord.ui.View):
    """View for selecting a kit from a dropdown."""

    def __init__(self, cog: KitManagementCog, kits: List[dict], action: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.action = action
        
        # Add kit selection dropdown
        options = []
        for kit in kits[:25]:  # Discord limit
            status = "✅" if kit["enabled"] else "❌"
            options.append(
                discord.SelectOption(
                    label=kit["kit_name"],
                    description=f"{status} {kit['description'][:50] if kit['description'] else 'No description'}",
                    value=str(kit["kit_id"]),
                )
            )
        
        select = discord.ui.Select(
            placeholder="Choose a kit...",
            options=options,
            custom_id="kit_select",
        )
        select.callback = self.kit_selected
        self.add_item(select)

    async def kit_selected(self, interaction: discord.Interaction):
        """Handle kit selection."""
        kit_id = int(interaction.data["values"][0])
        kit = await kit_db.get_kit_by_id(kit_id)
        
        if not kit:
            await interaction.response.send_message("❌ Kit not found.", ephemeral=True)
            return
        
        if self.action == "edit":
            # Show edit menu with options for properties or items
            await interaction.response.edit_message(
                content=f"**{kit['kit_name']}** - What would you like to edit?",
                embed=None,
                view=EditKitMenuView(self.cog, kit),
            )
        elif self.action == "delete":
            await interaction.response.edit_message(
                content=f"⚠️ Are you sure you want to delete **{kit['kit_name']}**?\n"
                f"This will also delete all items and claim history.",
                embed=None,
                view=ConfirmDeleteView(self.cog, kit),
            )
        elif self.action == "items":
            items = await kit_db.get_kit_items(kit_id)
            await interaction.response.edit_message(
                content=None,
                embed=await self._build_items_embed(kit, items),
                view=KitItemsView(self.cog, kit, items),
            )


# ---------------------------------------------------------------------------
# Create Kit Modal
# ---------------------------------------------------------------------------

class CreateKitModal(discord.ui.Modal, title="Create New Kit"):
    """Modal for creating a new kit."""

    kit_name = discord.ui.TextInput(
        label="Kit Name",
        placeholder="e.g., Starter Kit",
        required=True,
        max_length=50,
    )
    
    description = discord.ui.TextInput(
        label="Description",
        placeholder="e.g., Welcome kit for new players",
        required=False,
        max_length=200,
        style=discord.TextStyle.paragraph,
    )
    
    cooldown_hours = discord.ui.TextInput(
        label="Cooldown (hours, 0 = one-time only)",
        placeholder="24",
        required=True,
        max_length=5,
    )
    
    min_level = discord.ui.TextInput(
        label="Minimum Level (0 = no requirement)",
        placeholder="0",
        required=False,
        max_length=3,
    )
    
    min_playtime = discord.ui.TextInput(
        label="Minimum Playtime (hours, 0 = no requirement)",
        placeholder="0",
        required=False,
        max_length=5,
    )

    def __init__(self, cog: KitManagementCog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        """Handle kit creation."""
        try:
            cooldown = int(self.cooldown_hours.value)
            min_level = int(self.min_level.value) if self.min_level.value else 0
            min_playtime = int(self.min_playtime.value) if self.min_playtime.value else 0
            
            if cooldown < 0 or min_level < 0 or min_playtime < 0:
                await interaction.response.send_message(
                    "❌ Values cannot be negative.",
                    ephemeral=True,
                )
                return
            
            kit_id = await kit_db.create_kit(
                guild_id=interaction.guild.id,
                kit_name=self.kit_name.value,
                description=self.description.value,
                cooldown_hours=cooldown,
                min_level=min_level,
                min_playtime_hours=min_playtime,
            )
            
            await _log_to_admin_channel(
                self.cog.bot,
                interaction.guild.id,
                f"🎁 **Kit Created**: {self.kit_name.value} (ID: {kit_id}) by {interaction.user.mention}",
            )
            
            # Refresh main view
            kits = await kit_db.get_all_kits(interaction.guild.id)
            await interaction.response.send_message(
                embed=await self.cog._build_main_embed(interaction.guild.id, kits),
                view=KitCfgMainView(self.cog, kits),
                ephemeral=True,
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid number format. Please enter valid numbers.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error("Error creating kit: %s", e)
            await interaction.response.send_message(
                f"❌ Error creating kit: {e}",
                ephemeral=True,
            )


# ---------------------------------------------------------------------------
# Edit Kit Modal
# ---------------------------------------------------------------------------

class EditKitModal(discord.ui.Modal, title="Edit Kit"):
    """Modal for editing an existing kit."""

    kit_name = discord.ui.TextInput(
        label="Kit Name",
        required=True,
        max_length=50,
    )
    
    description = discord.ui.TextInput(
        label="Description",
        required=False,
        max_length=200,
        style=discord.TextStyle.paragraph,
    )
    
    cooldown_hours = discord.ui.TextInput(
        label="Cooldown (hours, 0 = one-time only)",
        required=True,
        max_length=5,
    )
    
    min_level = discord.ui.TextInput(
        label="Minimum Level (0 = no requirement)",
        required=False,
        max_length=3,
    )
    
    min_playtime = discord.ui.TextInput(
        label="Minimum Playtime (hours, 0 = no requirement)",
        required=False,
        max_length=5,
    )

    def __init__(self, cog: KitManagementCog, kit: dict):
        super().__init__()
        self.cog = cog
        self.kit = kit
        
        # Pre-fill with current values
        self.kit_name.default = kit["kit_name"]
        self.description.default = kit["description"] or ""
        self.cooldown_hours.default = str(kit["cooldown_hours"])
        self.min_level.default = str(kit["min_level"])
        self.min_playtime.default = str(kit["min_playtime_hours"])

    async def on_submit(self, interaction: discord.Interaction):
        """Handle kit update."""
        try:
            cooldown = int(self.cooldown_hours.value)
            min_level = int(self.min_level.value) if self.min_level.value else 0
            min_playtime = int(self.min_playtime.value) if self.min_playtime.value else 0
            
            if cooldown < 0 or min_level < 0 or min_playtime < 0:
                await interaction.response.send_message(
                    "❌ Values cannot be negative.",
                    ephemeral=True,
                )
                return
            
            await kit_db.update_kit(
                kit_id=self.kit["kit_id"],
                kit_name=self.kit_name.value,
                description=self.description.value,
                cooldown_hours=cooldown,
                min_level=min_level,
                min_playtime_hours=min_playtime,
            )
            
            await _log_to_admin_channel(
                self.cog.bot,
                interaction.guild.id,
                f"🎁 **Kit Updated**: {self.kit_name.value} by {interaction.user.mention}",
            )
            
            # Refresh main view
            kits = await kit_db.get_all_kits(interaction.guild.id)
            await interaction.response.send_message(
                embed=await self.cog._build_main_embed(interaction.guild.id, kits),
                view=KitCfgMainView(self.cog, kits),
                ephemeral=True,
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid number format. Please enter valid numbers.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error("Error updating kit: %s", e)
            await interaction.response.send_message(
                f"❌ Error updating kit: {e}",
                ephemeral=True,
            )


# ---------------------------------------------------------------------------
# Confirm Delete View
# ---------------------------------------------------------------------------

class ConfirmDeleteView(discord.ui.View):
    """Confirmation view for deleting a kit."""

    def __init__(self, cog: KitManagementCog, kit: dict):
        super().__init__(timeout=60)
        self.cog = cog
        self.kit = kit

    @discord.ui.button(label="Yes, Delete", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Confirm deletion."""
        await kit_db.delete_kit(self.kit["kit_id"])
        
        await _log_to_admin_channel(
            self.cog.bot,
            interaction.guild.id,
            f"🗑️ **Kit Deleted**: {self.kit['kit_name']} by {interaction.user.mention}",
        )
        
        # Refresh main view
        kits = await kit_db.get_all_kits(interaction.guild.id)
        await interaction.response.edit_message(
            content=None,
            embed=await self.cog._build_main_embed(interaction.guild.id, kits),
            view=KitCfgMainView(self.cog, kits),
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel deletion."""
        await interaction.response.edit_message(
            content="❌ Deletion cancelled.",
            view=None,
        )


# ---------------------------------------------------------------------------
# Kit Items View
# ---------------------------------------------------------------------------

class KitItemsView(discord.ui.View):
    """View for managing items in a kit."""

    def __init__(self, cog: KitManagementCog, kit: dict, items: List[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.kit = kit
        self.items = items

    @discord.ui.button(label="Add Item", style=discord.ButtonStyle.green, emoji="➕")
    async def add_item_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add an item to the kit."""
        await interaction.response.send_modal(AddItemModal(self.cog, self.kit))

    @discord.ui.button(label="Remove Item", style=discord.ButtonStyle.danger, emoji="➖")
    async def remove_item_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Remove an item from the kit."""
        if not self.items:
            await interaction.response.send_message("❌ No items to remove.", ephemeral=True)
            return
        
        await interaction.response.edit_message(
            content="Select an item to remove:",
            embed=None,
            view=ItemSelectView(self.cog, self.kit, self.items, action="remove"),
        )

    @discord.ui.button(label="Edit Item", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_item_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Edit an item in the kit."""
        if not self.items:
            await interaction.response.send_message("❌ No items to edit.", ephemeral=True)
            return
        
        await interaction.response.edit_message(
            content="Select an item to edit:",
            embed=None,
            view=ItemSelectView(self.cog, self.kit, self.items, action="edit"),
        )

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go back to main menu."""
        kits = await kit_db.get_all_kits(interaction.guild.id)
        await interaction.response.edit_message(
            embed=await self.cog._build_main_embed(interaction.guild.id, kits),
            view=KitCfgMainView(self.cog, kits),
        )


# ---------------------------------------------------------------------------
# Add Item Modal
# ---------------------------------------------------------------------------

class AddItemModal(discord.ui.Modal, title="Add Item to Kit"):
    """Modal for adding an item to a kit."""

    item_blueprint = discord.ui.TextInput(
        label="Item Blueprint Path",
        placeholder="Blueprint'/Game/PrimalEarth/CoreBlueprints/...'",
        required=True,
        max_length=500,
        style=discord.TextStyle.paragraph,
    )
    
    quantity = discord.ui.TextInput(
        label="Quantity",
        placeholder="1",
        required=True,
        max_length=5,
    )
    
    quality = discord.ui.TextInput(
        label="Quality (1-10)",
        placeholder="1=Prim, 2=Ram, 4=App, 6=Jour, 8=Mast, 10=Asc",
        required=True,
        max_length=2,
    )

    def __init__(self, cog: KitManagementCog, kit: dict):
        super().__init__()
        self.cog = cog
        self.kit = kit

    async def _build_items_embed(self, kit: dict, items: List[dict]) -> discord.Embed:
        """Build embed showing kit items."""
        embed = discord.Embed(
            title=f"📦 {kit['kit_name']} - Items",
            description=kit['description'] or "No description",
            color=discord.Color.blue(),
        )
        
        if items:
            item_list = []
            for item in items:
                quality_name = QUALITY_NAMES.get(item["quality"], "Unknown")
                bp = item["item_blueprint"]
                if "/" in bp:
                    bp = bp.split("/")[-1].replace("'", "")
                item_list.append(f"• **{bp}** x{item['quantity']} ({quality_name})")
            
            embed.add_field(
                name=f"Items ({len(items)})",
                value="\n".join(item_list[:20]),
                inline=False,
            )
        else:
            embed.add_field(
                name="Items",
                value="No items in this kit. Click **Add Item** to get started!",
                inline=False,
            )
        
        return embed

    async def on_submit(self, interaction: discord.Interaction):
        """Handle item addition."""
        try:
            quantity = int(self.quantity.value)
            quality = int(self.quality.value)
            
            if quantity <= 0:
                await interaction.response.send_message(
                    "❌ Quantity must be greater than 0.",
                    ephemeral=True,
                )
                return
            
            if quality not in [1, 2, 4, 6, 8, 10]:
                await interaction.response.send_message(
                    "❌ Invalid quality. Must be 1, 2, 4, 6, 8, or 10.",
                    ephemeral=True,
                )
                return
            
            await kit_db.add_kit_item(
                kit_id=self.kit["kit_id"],
                item_blueprint=self.item_blueprint.value,
                quantity=quantity,
                quality=quality,
            )
            
            # Refresh items view
            items = await kit_db.get_kit_items(self.kit["kit_id"])
            await interaction.response.edit_message(
                content=None,
                embed=await self._build_items_embed(self.kit, items),
                view=KitItemsView(self.cog, self.kit, items),
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid number format. Please enter valid numbers.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error("Error adding item: %s", e)
            await interaction.response.send_message(
                f"❌ Error adding item: {e}",
                ephemeral=True,
            )


# ---------------------------------------------------------------------------
# Item Select View
# ---------------------------------------------------------------------------

class ItemSelectView(discord.ui.View):
    """View for selecting an item from a dropdown."""

    def __init__(self, cog: KitManagementCog, kit: dict, items: List[dict], action: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.kit = kit
        self.items = items
        self.action = action
        
        # Add item selection dropdown
        options = []
        for item in items[:25]:  # Discord limit
            bp = item["item_blueprint"]
            if "/" in bp:
                bp = bp.split("/")[-1].replace("'", "")
            quality_name = QUALITY_NAMES.get(item["quality"], "Unknown")
            options.append(
                discord.SelectOption(
                    label=f"{bp} x{item['quantity']}",
                    description=f"Quality: {quality_name}",
                    value=str(item["kit_item_id"]),
                )
            )
        
        select = discord.ui.Select(
            placeholder="Choose an item...",
            options=options,
            custom_id="item_select",
        )
        select.callback = self.item_selected
        self.add_item(select)

    async def item_selected(self, interaction: discord.Interaction):
        """Handle item selection."""
        item_id = int(interaction.data["values"][0])
        
        if self.action == "remove":
            await kit_db.delete_kit_item(item_id)
            
            # Refresh items view
            items = await kit_db.get_kit_items(self.kit["kit_id"])
            await interaction.response.edit_message(
                content=None,
                embed=await self._build_items_embed(self.kit, items),
                view=KitItemsView(self.cog, self.kit, items),
            )
        elif self.action == "edit":
            # Find the item
            item = next((i for i in self.items if i["kit_item_id"] == item_id), None)
            if item:
                await interaction.response.send_modal(EditItemModal(self.cog, self.kit, item))
            else:
                await interaction.response.send_message("❌ Item not found.", ephemeral=True)

    async def _build_items_embed(self, kit: dict, items: List[dict]) -> discord.Embed:
        """Build embed showing kit items."""
        embed = discord.Embed(
            title=f"📦 {kit['kit_name']} - Items",
            description=kit['description'] or "No description",
            color=discord.Color.blue(),
        )
        
        if items:
            item_list = []
            for item in items:
                quality_name = QUALITY_NAMES.get(item["quality"], "Unknown")
                bp = item["item_blueprint"]
                if "/" in bp:
                    bp = bp.split("/")[-1].replace("'", "")
                item_list.append(f"• **{bp}** x{item['quantity']} ({quality_name})")
            
            embed.add_field(
                name=f"Items ({len(items)})",
                value="\n".join(item_list[:20]),
                inline=False,
            )
        else:
            embed.add_field(
                name="Items",
                value="No items in this kit. Click **Add Item** to get started!",
                inline=False,
            )
        
        return embed


# ---------------------------------------------------------------------------
# Edit Item Modal
# ---------------------------------------------------------------------------

class EditItemModal(discord.ui.Modal, title="Edit Item"):
    """Modal for editing an item."""

    quantity = discord.ui.TextInput(
        label="Quantity",
        required=True,
        max_length=5,
    )
    
    quality = discord.ui.TextInput(
        label="Quality (1-10)",
        placeholder="1=Prim, 2=Ram, 4=App, 6=Jour, 8=Mast, 10=Asc",
        required=True,
        max_length=2,
    )

    def __init__(self, cog: KitManagementCog, kit: dict, item: dict):
        super().__init__()
        self.cog = cog
        self.kit = kit
        self.item = item
        
        # Pre-fill with current values
        self.quantity.default = str(item["quantity"])
        self.quality.default = str(item["quality"])

    async def _build_items_embed(self, kit: dict, items: List[dict]) -> discord.Embed:
        """Build embed showing kit items."""
        embed = discord.Embed(
            title=f"📦 {kit['kit_name']} - Items",
            description=kit['description'] or "No description",
            color=discord.Color.blue(),
        )
        
        if items:
            item_list = []
            for item in items:
                quality_name = QUALITY_NAMES.get(item["quality"], "Unknown")
                bp = item["item_blueprint"]
                if "/" in bp:
                    bp = bp.split("/")[-1].replace("'", "")
                item_list.append(f"• **{bp}** x{item['quantity']} ({quality_name})")
            
            embed.add_field(
                name=f"Items ({len(items)})",
                value="\n".join(item_list[:20]),
                inline=False,
            )
        else:
            embed.add_field(
                name="Items",
                value="No items in this kit. Click **Add Item** to get started!",
                inline=False,
            )
        
        return embed

    async def on_submit(self, interaction: discord.Interaction):
        """Handle item update."""
        try:
            quantity = int(self.quantity.value)
            quality = int(self.quality.value)
            
            if quantity <= 0:
                await interaction.response.send_message(
                    "❌ Quantity must be greater than 0.",
                    ephemeral=True,
                )
                return
            
            if quality not in [1, 2, 4, 6, 8, 10]:
                await interaction.response.send_message(
                    "❌ Invalid quality. Must be 1, 2, 4, 6, 8, or 10.",
                    ephemeral=True,
                )
                return
            
            await kit_db.update_kit_item(
                kit_item_id=self.item["kit_item_id"],
                quantity=quantity,
                quality=quality,
            )
            
            # Refresh items view
            items = await kit_db.get_kit_items(self.kit["kit_id"])
            await interaction.response.edit_message(
                content=None,
                embed=await self._build_items_embed(self.kit, items),
                view=KitItemsView(self.cog, self.kit, items),
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid number format. Please enter valid numbers.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error("Error updating item: %s", e)
            await interaction.response.send_message(
                f"❌ Error updating item: {e}",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    """Load the cog."""
    await bot.add_cog(KitManagementCog(bot))
