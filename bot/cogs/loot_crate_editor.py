"""
Loot Crate Editor - Path-based single-view editor for complex INI settings.

Architecture:
- Single LootEditorView that rebuilds itself based on current path
- Path: ["Main"] -> ["Main", "Set", set_id] -> ["Main", "Set", set_id, "Item", item_id]
- Navigation via Select dropdown
- All modals carry context (crate_id, set_id, item_id)
- Export to Discord + Apply to Server via agent
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Button, Modal, TextInput
import logging
from typing import Optional, List, Dict, Any

from bot.utils.config import Config
from bot.utils.subscription_checker import check_feature
from bot.database.loot_crate_db import (
    get_crate_with_sets,
    get_crate_configs,
    create_crate_config,
    update_crate_config,
    delete_crate_config,
    create_item_set,
    update_item_set,
    delete_item_set,
    create_set_item,
    update_set_item,
    delete_set_item,
    export_crate_to_ini,
    import_crate_from_ini,
)
from bot.database import server_config_db
import aiosqlite

logger = logging.getLogger("LootCrateEditor")


class CrateSelectModal(Modal, title="Select Loot Crate"):
    """Modal for entering/selecting a crate class string."""
    
    crate_class = TextInput(
        label="Crate Class String",
        placeholder="SupplyCrate_ClassName_C",
        required=True,
        max_length=200
    )
    
    def __init__(self, guild_id: int, server_name: str, callback_view):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.server_name = server_name
        self.callback_view = callback_view
    
    async def on_submit(self, interaction: discord.Interaction):
        class_string = self.crate_class.value.strip()
        db_path = Config.DATABASE_PATH
        
        # Check if crate already exists for this server
        existing = await get_crate_configs(self.guild_id, self.server_name, db_path)
        crate_id = None
        
        for crate in existing:
            if crate.get('class_string') == class_string:
                crate_id = crate['id']
                break
        
        if not crate_id:
            # Create new crate
            crate_id = await create_crate_config(
                guild_id=self.guild_id,
                server_name=self.server_name,
                class_string=class_string,
                label=class_string.split('.')[-1].replace('_C', ''),
                db_path=db_path
            )
        
        if crate_id:
            view = LootEditorView(
                guild_id=self.guild_id,
                server_name=self.server_name,
                crate_id=crate_id,
                user_id=interaction.user.id
            )
            await view.initialize()
            embed = await view.create_embed()
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("Failed to create crate.", ephemeral=True)


class ItemSetModal(Modal, title="Edit Item Set"):
    """Modal for editing item set properties."""
    
    set_name = TextInput(label="Set Name", default="Item Set", max_length=100)
    weight = TextInput(label="Weight", default="1.0")
    min_items = TextInput(label="Min Items", default="1")
    max_items = TextInput(label="Max Items", default="1")
    
    def __init__(self, crate_id: int, set_id: int, set_data: dict):
        super().__init__(timeout=None)
        self.crate_id = crate_id
        self.set_id = set_id
        
        # Pre-fill with existing data
        if set_data:
            self.set_name.default = set_data.get('set_name', 'Item Set')
            self.weight.default = str(set_data.get('weight', 1.0))
            self.min_items.default = str(set_data.get('min_items', 1))
            self.max_items.default = str(set_data.get('max_items', 1))
    
    async def on_submit(self, interaction: discord.Interaction):
        db_path = Config.DATABASE_PATH
        try:
            await update_item_set(
                self.set_id,
                db_path,
                set_name=self.set_name.value,
                weight=float(self.weight.value),
                min_items=int(self.min_items.value),
                max_items=int(self.max_items.value)
            )
            await interaction.response.send_message("✅ Set updated!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


class ItemModal(Modal, title="Edit Item"):
    """Modal for editing a single item in a set."""
    
    class_string = TextInput(label="Blueprint Path", max_length=500)
    min_qty = TextInput(label="Min Quantity", default="1")
    max_qty = TextInput(label="Max Quantity", default="1")
    quality_min = TextInput(label="Min Quality", default="0")
    quality_max = TextInput(label="Max Quality", default="0")
    bp_chance = TextInput(label="Blueprint Chance %", default="0")
    
    def __init__(self, crate_id: int, set_id: int, item_id: int, item_data: dict):
        super().__init__(timeout=None)
        self.crate_id = crate_id
        self.set_id = set_id
        self.item_id = item_id
        
        # Pre-fill with existing data
        if item_data:
            self.class_string.default = item_data.get('class_string', '')
            self.min_qty.default = str(item_data.get('min_quantity', 1))
            self.max_qty.default = str(item_data.get('max_quantity', 1))
            self.quality_min.default = str(item_data.get('quality_min', 0))
            self.quality_max.default = str(item_data.get('quality_max', 0))
            self.bp_chance.default = str(item_data.get('chance_to_be_blueprint', 0))
    
    async def on_submit(self, interaction: discord.Interaction):
        db_path = Config.DATABASE_PATH
        try:
            await update_set_item(
                self.item_id,
                db_path,
                class_string=self.class_string.value,
                min_quantity=int(self.min_qty.value),
                max_quantity=int(self.max_qty.value),
                quality_min=float(self.quality_min.value),
                quality_max=float(self.quality_max.value),
                chance_to_be_blueprint=float(self.bp_chance.value) / 100.0
            )
            await interaction.response.send_message("✅ Item updated!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


class CrateSettingsModal(Modal, title="Crate Settings"):
    """Modal for editing crate-level settings."""
    
    label = TextInput(label="Display Label", max_length=100)
    min_sets = TextInput(label="Min Item Sets", default="1")
    max_sets = TextInput(label="Max Item Sets", default="1")
    
    def __init__(self, crate_id: int, crate_data: dict):
        super().__init__(timeout=None)
        self.crate_id = crate_id
        
        if crate_data:
            self.label.default = crate_data.get('label', '')
            self.min_sets.default = str(crate_data.get('min_item_sets', 1))
            self.max_sets.default = str(crate_data.get('max_item_sets', 1))
    
    async def on_submit(self, interaction: discord.Interaction):
        db_path = Config.DATABASE_PATH
        try:
            await update_crate_config(
                self.crate_id,
                db_path,
                label=self.label.value,
                min_item_sets=int(self.min_sets.value),
                max_item_sets=int(self.max_sets.value)
            )
            await interaction.response.send_message("✅ Crate settings updated!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)


class LootEditorView(View):
    """
    Single-view loot crate editor with path-based navigation.
    
    Path levels:
    - ["Main"] - Show crate overview + item sets list
    - ["Main", "Set", set_id] - Show single set details + items list
    """
    
    def __init__(self, guild_id: int, server_name: str, crate_id: int, user_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.server_name = server_name
        self.crate_id = crate_id
        self.user_id = user_id
        self.path: List[str] = ["Main"]
        self.crate_data: Dict[str, Any] = {}
        self._initialized = False
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id
    
    async def initialize(self):
        if self._initialized:
            return
        self._initialized = True
        db_path = Config.DATABASE_PATH
        self.crate_data = await get_crate_with_sets(self.crate_id, db_path)
    
    def refresh_components(self):
        self.clear_items()
        nav_options = [discord.SelectOption(label="📦 Crate Overview", value="Main")]
        
        if len(self.path) >= 3 and self.path[1] == "Set":
            try:
                set_id = int(self.path[2])
                set_data = self._get_set_by_id(set_id)
                if set_data:
                    set_name = set_data.get('set_name', f'Set {set_id}')
                    nav_options.append(discord.SelectOption(
                        label=f"📋 {set_name[:20]}",
                        value=f"Set:{set_id}"
                    ))
            except (ValueError, IndexError):
                pass
        
        nav_select = Select(placeholder="Navigate to...", options=nav_options[:25], row=0)
        nav_select.callback = self._on_navigate
        self.add_item(nav_select)
        
        if self.path[-1] == "Main":
            self._add_main_buttons()
        elif len(self.path) >= 3 and self.path[1] == "Set":
            try:
                self._add_set_buttons(int(self.path[2]))
            except ValueError:
                pass
    
    def _get_set_by_id(self, set_id: int) -> Optional[Dict]:
        for item_set in self.crate_data.get('item_sets', []):
            if item_set.get('id') == set_id:
                return item_set
        return None
    
    def _add_main_buttons(self):
        settings_btn = Button(style=discord.ButtonStyle.secondary, label="⚙️ Settings", row=1)
        settings_btn.callback = self._on_settings
        self.add_item(settings_btn)
        
        add_set_btn = Button(style=discord.ButtonStyle.success, label="➕ Add Set", row=1)
        add_set_btn.callback = self._on_add_set
        self.add_item(add_set_btn)
        
        export_btn = Button(style=discord.ButtonStyle.primary, label="📤 Export", row=2)
        export_btn.callback = self._on_export
        self.add_item(export_btn)
        
        delete_btn = Button(style=discord.ButtonStyle.danger, label="🗑️ Delete", row=2)
        delete_btn.callback = self._on_delete_crate
        self.add_item(delete_btn)
        
        # Server integration buttons
        apply_btn = Button(style=discord.ButtonStyle.success, label="☁️ Apply to Server", row=3)
        apply_btn.callback = self._on_apply_to_server
        self.add_item(apply_btn)
        
        read_btn = Button(style=discord.ButtonStyle.primary, label="📖 Read from Server", row=3)
        read_btn.callback = self._on_read_from_server
        self.add_item(read_btn)
    
    def _add_set_buttons(self, set_id: int):
        edit_btn = Button(style=discord.ButtonStyle.secondary, label="✏️ Edit Set", row=1)
        edit_btn.callback = lambda interaction: self._on_edit_set(interaction, set_id)
        self.add_item(edit_btn)
        
        add_item_btn = Button(style=discord.ButtonStyle.success, label="➕ Add Item", row=1)
        add_item_btn.callback = lambda interaction: self._on_add_item(interaction, set_id)
        self.add_item(add_item_btn)
        
        delete_btn = Button(style=discord.ButtonStyle.danger, label="🗑️ Delete Set", row=2)
        delete_btn.callback = lambda interaction: self._on_delete_set(interaction, set_id)
        self.add_item(delete_btn)
    
    async def create_embed(self) -> discord.Embed:
        await self.initialize()
        crate_name = self.crate_data.get('label') or self.crate_data.get('class_string', 'Unknown')
        embed = discord.Embed(title=f"📦 {crate_name}", color=discord.Color.gold())
        embed.set_footer(text=f"Path: {' > '.join(self.path)}")
        
        if self.path[-1] == "Main":
            self._build_main_embed(embed)
        elif len(self.path) >= 3 and self.path[1] == "Set":
            try:
                self._build_set_embed(embed, int(self.path[2]))
            except ValueError:
                embed.description = "Invalid path."
        
        return embed
    
    def _build_main_embed(self, embed: discord.Embed):
        min_sets = self.crate_data.get('min_item_sets', 1)
        max_sets = self.crate_data.get('max_item_sets', 1)
        embed.add_field(name="⚙️ Crate Settings", value=f"Min Sets: {min_sets}\nMax Sets: {max_sets}", inline=True)
        
        item_sets = self.crate_data.get('item_sets', [])
        if item_sets:
            sets_text = ""
            for i, item_set in enumerate(item_sets[:10]):
                name = item_set.get('set_name', f'Set {i+1}')
                weight = item_set.get('weight', 1.0)
                items_count = len(item_set.get('items') or [])
                sets_text += f"**{i+1}.** {name} (W:{weight}, Items:{items_count})\n"
            if len(item_sets) > 10:
                sets_text += f"\n... and {len(item_sets) - 10} more"
            embed.add_field(name=f"📋 Item Sets ({len(item_sets)})", value=sets_text[:1024] or "No sets", inline=False)
        else:
            embed.add_field(name="📋 Item Sets", value="No item sets. Click **➕ Add Set** to create one.", inline=False)
    
    def _build_set_embed(self, embed: discord.Embed, set_id: int):
        set_data = self._get_set_by_id(set_id)
        if not set_data:
            embed.description = "Set not found."
            return
        
        name = set_data.get('set_name', 'Unnamed')
        weight = set_data.get('weight', 1.0)
        min_items = set_data.get('min_items', 1)
        max_items = set_data.get('max_items', 1)
        
        embed.add_field(name=f"📋 {name}", value=f"Weight: {weight}\nMin Items: {min_items}\nMax Items: {max_items}", inline=True)
        
        items = set_data.get('items', [])
        if items:
            items_text = ""
            for i, item in enumerate(items[:10]):
                class_str = item.get('class_string', 'Unknown')
                short_class = class_str.split('.')[-1][:30]
                min_qty = item.get('min_quantity', 1)
                max_qty = item.get('max_quantity', 1)
                items_text += f"**{i+1}.** {short_class} ({min_qty}-{max_qty})\n"
            if len(items) > 10:
                items_text += f"\n... and {len(items) - 10} more"
            embed.add_field(name=f"🎯 Items ({len(items)})", value=items_text[:1024] or "No items", inline=False)
        else:
            embed.add_field(name="🎯 Items", value="No items. Click **➕ Add Item** to add one.", inline=False)
    
    async def _on_navigate(self, interaction: discord.Interaction):
        value = self.children[0].values[0]
        if value == "Main":
            self.path = ["Main"]
        elif value.startswith("Set:"):
            set_id = value.split(":")[1]
            self.path = ["Main", "Set", set_id]
        await self._refresh_view(interaction)
    
    async def _on_settings(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CrateSettingsModal(self.crate_id, self.crate_data))
    
    async def _on_add_set(self, interaction: discord.Interaction):
        db_path = Config.DATABASE_PATH
        set_id = await create_item_set(crate_config_id=self.crate_id, set_name="New Item Set", db_path=db_path)
        if set_id:
            self.crate_data = await get_crate_with_sets(self.crate_id, db_path)
            self.path = ["Main", "Set", str(set_id)]
            await self._refresh_view(interaction)
        else:
            await interaction.response.send_message("Failed to create set.", ephemeral=True)
    
    async def _on_edit_set(self, interaction: discord.Interaction, set_id: int):
        set_data = self._get_set_by_id(set_id)
        await interaction.response.send_modal(ItemSetModal(self.crate_id, set_id, set_data))
    
    async def _on_delete_set(self, interaction: discord.Interaction, set_id: int):
        db_path = Config.DATABASE_PATH
        success = await delete_item_set(set_id, db_path)
        if success:
            self.crate_data = await get_crate_with_sets(self.crate_id, db_path)
            self.path = ["Main"]
            await self._refresh_view(interaction)
        else:
            await interaction.response.send_message("Failed to delete set.", ephemeral=True)
    
    async def _on_add_item(self, interaction: discord.Interaction, set_id: int):
        db_path = Config.DATABASE_PATH
        item_id = await create_set_item(
            item_set_id=set_id,
            class_string="Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/PrimalItem_WeaponStonePick.PrimalItem_WeaponStonePick'",
            db_path=db_path
        )
        if item_id:
            self.crate_data = await get_crate_with_sets(self.crate_id, db_path)
            await self._refresh_view(interaction)
        else:
            await interaction.response.send_message("Failed to create item.", ephemeral=True)
    
    async def _on_export(self, interaction: discord.Interaction):
        db_path = Config.DATABASE_PATH
        ini_content = await export_crate_to_ini(self.crate_id, db_path)
        if ini_content:
            if len(ini_content) > 1900:
                ini_content = ini_content[:1900] + "\n..."
            await interaction.response.send_message(f"```ini\n{ini_content}\n```", ephemeral=True)
        else:
            await interaction.response.send_message("Failed to export.", ephemeral=True)
    
    async def _on_delete_crate(self, interaction: discord.Interaction):
        db_path = Config.DATABASE_PATH
        success = await delete_crate_config(self.crate_id, db_path)
        if success:
            await interaction.response.send_message("✅ Crate deleted.", ephemeral=True)
        else:
            await interaction.response.send_message("Failed to delete crate.", ephemeral=True)
    
    async def _on_apply_to_server(self, interaction: discord.Interaction):
        """Export this crate and write to server's Game.ini via agent."""
        # Get agent manager from bot
        agent_manager = getattr(interaction.client, 'agent_manager', None)
        if not agent_manager:
            await interaction.response.send_message(
                "❌ No agent manager available. Remote agent required.",
                ephemeral=True
            )
            return
        
        # Find connected agent for this guild
        agent_id = None
        for aid, info in agent_manager.agents.items():
            if info.get('guild_id') == self.guild_id:
                agent_id = aid
                break
        
        if not agent_id:
            await interaction.response.send_message(
                "❌ No connected agent for this server. Connect an agent first.",
                ephemeral=True
            )
            return
        
        # Export crate to INI format
        db_path = Config.DATABASE_PATH
        ini_content = await export_crate_to_ini(self.crate_id, db_path)
        
        if not ini_content:
            await interaction.response.send_message(
                "❌ Failed to export crate configuration.",
                ephemeral=True
            )
            return
        
        # Read current Game.ini from server
        try:
            result = await agent_manager.read_ini(agent_id, self.server_name, "Game.ini")
            if not result or result.get('status') != 'success':
                await interaction.response.send_message(
                    "❌ Failed to read Game.ini from server.",
                    ephemeral=True
                )
                return
            
            current_ini = result.get('data', '')
            
            # Append our crate config (in real implementation, would merge properly)
            # For now, just append to the [/Script/ShooterGame.ShooterGameMode] section
            new_ini = current_ini
            
            # Find or create the section
            section_header = "[/Script/ShooterGame.ShooterGameMode]"
            if section_header in new_ini:
                # Insert after the section header
                parts = new_ini.split(section_header, 1)
                new_ini = parts[0] + section_header + "\n" + ini_content + parts[1]
            else:
                # Append section
                new_ini = new_ini.rstrip() + "\n\n" + section_header + "\n" + ini_content
            
            # Write back
            write_result = await agent_manager.write_ini(
                agent_id, self.server_name, "Game.ini", new_ini
            )
            
            if write_result and write_result.get('status') == 'success':
                await interaction.response.send_message(
                    "✅ Crate configuration applied to Game.ini.\n"
                    "⚠️ **Server restart required** for changes to take effect.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ Failed to write Game.ini: {write_result.get('error', 'Unknown error')}",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Apply to server failed: {e}")
            await interaction.response.send_message(
                f"❌ Error applying to server: {e}",
                ephemeral=True
            )
    
    async def _on_read_from_server(self, interaction: discord.Interaction):
        """Read Game.ini from server and import crates."""
        # Get agent manager from bot
        agent_manager = getattr(interaction.client, 'agent_manager', None)
        if not agent_manager:
            await interaction.response.send_message(
                "❌ No agent manager available. Remote agent required.",
                ephemeral=True
            )
            return
        
        # Find connected agent for this guild
        agent_id = None
        for aid, info in agent_manager.agents.items():
            if info.get('guild_id') == self.guild_id:
                agent_id = aid
                break
        
        if not agent_id:
            await interaction.response.send_message(
                "❌ No connected agent for this server. Connect an agent first.",
                ephemeral=True
            )
            return
        
        # Read Game.ini from server
        try:
            result = await agent_manager.read_ini(agent_id, self.server_name, "Game.ini")
            
            if not result or result.get('status') != 'success':
                await interaction.response.send_message(
                    "❌ Failed to read Game.ini from server.",
                    ephemeral=True
                )
                return
            
            ini_content = result.get('data', '')
            
            # Parse crates from the content
            from bot.utils.loot_crate_parser import parse_all_crates
            crates = parse_all_crates(ini_content)
            
            if not crates:
                await interaction.response.send_message(
                    "No loot crate configurations found in Game.ini.",
                    ephemeral=True
                )
                return
            
            # Import found crates
            db_path = Config.DATABASE_PATH
            imported = 0
            for crate_data in crates:
                try:
                    crate_id = await import_crate_from_ini(
                        guild_id=self.guild_id,
                        server_name=self.server_name,
                        class_string=crate_data['class_string'],
                        crate_data=crate_data,
                        db_path=db_path
                    )
                    if crate_id:
                        imported += 1
                except Exception as e:
                    logger.warning(f"Failed to import crate {crate_data.get('class_string')}: {e}")
            
            # Refresh view with new data
            self.crate_data = await get_crate_with_sets(self.crate_id, db_path)
            self.refresh_components()
            embed = await self.create_embed()
            
            await interaction.response.edit_message(
                embed=embed,
                view=self,
                content=f"✅ Imported {imported} crate(s) from server."
            )
            
        except Exception as e:
            logger.error(f"Read from server failed: {e}")
            await interaction.response.send_message(
                f"❌ Error reading from server: {e}",
                ephemeral=True
            )
    
    async def _refresh_view(self, interaction: discord.Interaction):
        db_path = Config.DATABASE_PATH
        self.crate_data = await get_crate_with_sets(self.crate_id, db_path)
        self.refresh_components()
        embed = await self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class LootCrateListSelect(Select):
    """Select dropdown for choosing a crate to edit."""
    
    def __init__(self, guild_id: int, server_name: str, crates: List[Dict]):
        self.guild_id = guild_id
        self.server_name = server_name
        
        options = []
        for crate in crates[:25]:
            label = crate.get('label') or crate.get('class_string', 'Unknown')
            if len(label) > 50:
                label = label[:47] + "..."
            options.append(discord.SelectOption(
                label=label,
                value=str(crate['id']),
                description=(crate.get('class_string') or '')[:50]
            ))
        
        super().__init__(
            placeholder="Select a crate to edit...",
            options=options,
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        crate_id = int(self.values[0])
        view = LootEditorView(
            guild_id=self.guild_id,
            server_name=self.server_name,
            crate_id=crate_id,
            user_id=interaction.user.id
        )
        await view.initialize()
        embed = await view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class LootCrateEntryView(View):
    """Entry point view for selecting a crate to edit."""
    
    def __init__(self, guild_id: int, server_name: str, user_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.server_name = server_name
        self.user_id = user_id
        self.crates = []
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id
    
    async def build_ui(self):
        """Load crates and build select dropdown."""
        self.clear_items()
        db_path = Config.DATABASE_PATH
        self.crates = await get_crate_configs(self.guild_id, self.server_name, db_path)
        
        if self.crates:
            select = LootCrateListSelect(self.guild_id, self.server_name, self.crates)
            self.add_item(select)
        
        # Add "New Crate" button
        new_btn = Button(style=discord.ButtonStyle.success, label="➕ New Crate", row=1)
        new_btn.callback = self._on_new_crate
        self.add_item(new_btn)
        
        # Import button
        import_btn = Button(style=discord.ButtonStyle.primary, label="📥 Import from INI", row=1)
        import_btn.callback = self._on_import
        self.add_item(import_btn)
    
    async def create_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"📦 Loot Crates - {self.server_name}",
            color=discord.Color.gold()
        )
        
        if self.crates:
            embed.description = f"Found {len(self.crates)} configured crate(s). Select one to edit."
        else:
            embed.description = "No crates configured yet. Click **➕ New Crate** to create one, or **📥 Import from INI** to import from your Game.ini."
        
        return embed
    
    async def _on_new_crate(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            CrateSelectModal(self.guild_id, self.server_name, self)
        )
    
    async def _on_import(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            ImportIniModal(self.guild_id, self.server_name, self.user_id)
        )


class ImportIniModal(Modal, title="Import Loot Crates from INI"):
    """Modal for pasting INI content to import."""
    
    ini_content = TextInput(
        label="Paste Game.ini Content",
        placeholder="Paste ConfigOverrideSupplyCrateItems content...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000
    )
    
    def __init__(self, guild_id: int, server_name: str, user_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.server_name = server_name
        self.user_id = user_id
    
    async def on_submit(self, interaction: discord.Interaction):
        from bot.utils.loot_crate_parser import parse_all_crates
        
        content = self.ini_content.value
        db_path = Config.DATABASE_PATH
        
        crates = parse_all_crates(content)
        
        if not crates:
            await interaction.response.send_message(
                "No loot crate configurations found in the provided content.",
                ephemeral=True
            )
            return
        
        imported = 0
        for crate_data in crates:
            try:
                crate_id = await import_crate_from_ini(
                    guild_id=self.guild_id,
                    server_name=self.server_name,
                    class_string=crate_data['class_string'],
                    crate_data=crate_data,
                    db_path=db_path
                )
                if crate_id:
                    imported += 1
            except Exception as e:
                logger.warning(f"Failed to import crate {crate_data.get('class_string')}: {e}")
        
        await interaction.response.send_message(
            f"✅ Imported {imported} loot crate configuration(s).",
            ephemeral=True
        )


class LootCrateCog(commands.Cog):
    """Loot crate configuration management."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="lootcrates", description="Manage loot crate configurations")
    async def lootcrates(self, interaction: discord.Interaction):
        if not await check_feature(interaction, "loot_crates"):
            return
        if not interaction.guild_id:
            await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            return
        
        servers = await server_config_db.get_ark_servers(interaction.guild_id)
        
        if not servers:
            await interaction.response.send_message(
                "No servers configured. Use `/setup` first.",
                ephemeral=True
            )
            return
        
        if len(servers) == 1:
            # Skip server selection if only one server
            server_name = servers[0].get('name')
            view = LootCrateEntryView(interaction.guild_id, server_name, interaction.user.id)
            await view.build_ui()
            embed = await view.create_embed()
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            # Show server selection
            view = ServerSelectView(interaction.guild_id, servers, interaction.user.id)
            embed = discord.Embed(
                title="📦 Loot Crate Editor",
                description="Select a server to manage loot crates.",
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ServerSelectView(View):
    """Server selection for loot crate editing."""
    
    def __init__(self, guild_id: int, servers: List[Dict], user_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.servers = servers
        self.user_id = user_id
        
        options = []
        for server in servers[:25]:
            options.append(discord.SelectOption(
                label=server.get("name", "Unknown"),
                value=server.get("name", "Unknown")
            ))
        
        self.server_select = Select(
            placeholder="Select server...",
            options=options,
            row=0
        )
        self.server_select.callback = self._on_server_select
        self.add_item(self.server_select)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id
    
    async def _on_server_select(self, interaction: discord.Interaction):
        server_name = self.server_select.values[0]
        view = LootCrateEntryView(self.guild_id, server_name, self.user_id)
        await view.build_ui()
        embed = await view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(LootCrateCog(bot))
