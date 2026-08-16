"""
Loot Crates Cog - GUI for managing ARK loot crate configurations.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
import logging
from typing import Optional, List, Dict, Any
import aiosqlite

from bot.database import server_config_db
from bot.database.loot_crate_db import (
    get_crate_configs,
    get_crate_with_sets,
    create_crate_config,
    update_crate_config,
    delete_crate_config,
    create_item_set,
    delete_item_set,
    create_set_item,
    delete_set_item,
    export_crate_to_ini,
    import_crate_from_ini,
    init_loot_crate_tables,
)
from bot.utils.loot_crate_parser import parse_all_crates
from bot.utils.config import Config

logger = logging.getLogger("LootCrates")


class LootCrateCog(commands.Cog):
    """Loot crate configuration management."""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def cog_load(self):
        db_path = Config.DATABASE_PATH
        await init_loot_crate_tables(db_path)
        logger.info("Loot Crates cog loaded")
    
    @app_commands.command(name="lootcrates", description="Manage loot crate configurations")
    async def lootcrates(self, interaction: discord.Interaction):
        servers = await server_config_db.get_ark_servers(interaction.guild_id)
        
        if not servers:
            await interaction.response.send_message(
                "No servers configured. Use `/setup` first.",
                ephemeral=True
            )
            return
        
        view = LootServerSelectView(interaction.guild_id, servers, interaction.user.id)
        embed = discord.Embed(
            title="📦 Loot Crate Editor",
            description="Select a server to manage loot crate configurations.",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class LootServerSelectView(View):
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
        view = LootCategoryView(self.guild_id, server_name, self.user_id)
        embed = discord.Embed(
            title=f"📦 Loot Crates - {server_name}",
            description="Select a category to view or configure loot crates.",
            color=discord.Color.gold()
        )
        await interaction.response.edit_message(embed=embed, view=view)


class LootCategoryView(View):
    """Category selection for loot crates."""
    
    def __init__(self, guild_id: int, server_name: str, user_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.server_name = server_name
        self.user_id = user_id
        
        categories = [
            ("🏛️ Artifacts", "artifact"),
            ("🌍 Surface Drops", "surface"),
            ("🕳️ Cave Drops", "cave"),
            ("📦 Supply Crates", "crate"),
            ("✅ Configured", "configured"),
        ]
        
        for i, (label, value) in enumerate(categories):
            btn = Button(
                style=discord.ButtonStyle.primary,
                label=label,
                row=i // 3
            )
            btn.callback = lambda interaction, v=value: self._on_category(interaction, v)
            self.add_item(btn)
        
        import_btn = Button(
            style=discord.ButtonStyle.success,
            label="📥 Import from INI",
            row=1
        )
        import_btn.callback = self._on_import
        self.add_item(import_btn)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id
    
    async def _on_category(self, interaction: discord.Interaction, category: str):
        view = LootCrateListView(self.guild_id, self.server_name, category, self.user_id)
        embed = await view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def _on_import(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ImportIniModal(self.guild_id, self.server_name))


class ImportIniModal(Modal):
    """Modal for pasting INI content to import."""
    
    def __init__(self, guild_id: int, server_name: str):
        super().__init__(title="Import Loot Crates from INI", timeout=None)
        self.guild_id = guild_id
        self.server_name = server_name
        
        self.ini_content = TextInput(
            label="Paste Game.ini Content",
            placeholder="Paste the contents of your Game.ini file here...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000
        )
        self.add_item(self.ini_content)
    
    async def on_submit(self, interaction: discord.Interaction):
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


class LootCrateListView(View):
    """List of loot crates in a category with select menu."""
    
    def __init__(self, guild_id: int, server_name: str, category: str, user_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.server_name = server_name
        self.category = category
        self.user_id = user_id
        self.crates = []
        self.configured_crates = []
        self._initialized = False
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id
    
    async def build_ui_async(self):
        if self._initialized:
            return
        
        self._initialized = True
        db_path = Config.DATABASE_PATH
        
        self.configured_crates = await get_crate_configs(self.guild_id, self.server_name, db_path)
        configured_classes = {c['class_string'] for c in self.configured_crates}
        
        if self.category == "configured":
            self.crates = self.configured_crates
        else:
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                tag_filter = f'%{self.category}%'
                cursor = await db.execute(
                    "SELECT object_id, label, class_string FROM ark_ref_loot_sources WHERE tags LIKE ? LIMIT 25",
                    (tag_filter,)
                )
                self.crates = [dict(row) for row in await cursor.fetchall()]
        
        if self.crates:
            options = []
            for crate in self.crates[:25]:
                label = crate.get('label') or crate.get('class_string', 'Unknown')
                if len(label) > 50:
                    label = label[:47] + "..."
                class_str = crate.get('class_string', '')
                is_configured = class_str in configured_classes
                prefix = "✅ " if is_configured else "⬜ "
                options.append(discord.SelectOption(
                    label=f"{prefix}{label[:47]}",
                    value=class_str,
                    description=class_str[:50] if class_str else None
                ))
            
            select = Select(
                placeholder="Select a crate to edit...",
                options=options,
                row=0
            )
            select.callback = self._on_crate_select
            self.add_item(select)
        
        back_btn = Button(
            style=discord.ButtonStyle.secondary,
            label="◀ Back",
            row=1
        )
        back_btn.callback = self._on_back
        self.add_item(back_btn)
    
    async def _on_crate_select(self, interaction: discord.Interaction):
        for item in self.children:
            if isinstance(item, Select) and item.values:
                class_string = item.values[0]
                break
        else:
            return
        
        crate_id = None
        for c in self.configured_crates:
            if c['class_string'] == class_string:
                crate_id = c['id']
                break
        
        if not crate_id:
            db_path = Config.DATABASE_PATH
            label = None
            for crate in self.crates:
                if crate.get('class_string') == class_string:
                    label = crate.get('label')
                    break
            
            crate_id = await create_crate_config(
                guild_id=self.guild_id,
                server_name=self.server_name,
                class_string=class_string,
                label=label,
                db_path=db_path
            )
        
        if crate_id:
            view = CrateEditorView(self.guild_id, self.server_name, crate_id, self.user_id)
            embed = await view.create_embed()
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("Failed to open crate editor.", ephemeral=True)
    
    async def _on_back(self, interaction: discord.Interaction):
        view = LootCategoryView(self.guild_id, self.server_name, self.user_id)
        embed = discord.Embed(
            title=f"📦 Loot Crates - {self.server_name}",
            description="Select a category to view or configure loot crates.",
            color=discord.Color.gold()
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def create_embed(self) -> discord.Embed:
        await self.build_ui_async()
        
        embed = discord.Embed(
            title=f"📦 {self.category.title()} Crates",
            color=discord.Color.gold()
        )
        
        description = f"**{self.server_name}**"
        
        if self.crates:
            configured_classes = {c['class_string'] for c in self.configured_crates}
            configured_count = len([c for c in self.crates if c.get('class_string') in configured_classes])
            description += f"\n\nFound {len(self.crates)} crates ({configured_count} configured)"
            embed.set_footer(text="✅ = Configured | ⬜ = Not configured")
        else:
            description += "\n\nNo crates found in this category."
        
        embed.description = description
        return embed


class CrateSettingsModal(Modal):
    """Modal for editing crate settings."""
    
    def __init__(self, crate_id: int):
        super().__init__(title="Crate Settings", timeout=None)
        self.crate_id = crate_id
        
        self.label_input = TextInput(
            label="Display Name",
            placeholder="Level 15 Supply Crate",
            required=False,
            max_length=50
        )
        self.add_item(self.label_input)
        
        self.min_sets = TextInput(
            label="Min Item Sets",
            placeholder="1",
            required=False,
            max_length=3
        )
        self.add_item(self.min_sets)
        
        self.max_sets = TextInput(
            label="Max Item Sets",
            placeholder="1",
            required=False,
            max_length=3
        )
        self.add_item(self.max_sets)
    
    async def on_submit(self, interaction: discord.Interaction):
        db_path = Config.DATABASE_PATH
        updates = {}
        
        if self.label_input.value.strip():
            updates['label'] = self.label_input.value.strip()
        
        try:
            if self.min_sets.value.strip():
                updates['min_item_sets'] = int(self.min_sets.value.strip())
        except ValueError:
            pass
        
        try:
            if self.max_sets.value.strip():
                updates['max_item_sets'] = int(self.max_sets.value.strip())
        except ValueError:
            pass
        
        if updates:
            await update_crate_config(self.crate_id, db_path, **updates)
        
        await interaction.response.send_message("✅ Settings updated.", ephemeral=True)


class CrateEditorView(View):
    """Editor for a single loot crate."""
    
    def __init__(self, guild_id: int, server_name: str, crate_id: int, user_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.server_name = server_name
        self.crate_id = crate_id
        self.user_id = user_id
        self.crate_data = None
        
        self._build_ui()
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id
    
    def _build_ui(self):
        edit_btn = Button(
            style=discord.ButtonStyle.primary,
            label="⚙️ Settings",
            row=0
        )
        edit_btn.callback = self._on_settings
        self.add_item(edit_btn)
        
        add_set_btn = Button(
            style=discord.ButtonStyle.success,
            label="➕ Add Item Set",
            row=0
        )
        add_set_btn.callback = self._on_add_set
        self.add_item(add_set_btn)
        
        export_btn = Button(
            style=discord.ButtonStyle.primary,
            label="📄 Export INI",
            row=1
        )
        export_btn.callback = self._on_export
        self.add_item(export_btn)
        
        delete_btn = Button(
            style=discord.ButtonStyle.danger,
            label="🗑️ Delete",
            row=1
        )
        delete_btn.callback = self._on_delete
        self.add_item(delete_btn)
        
        back_btn = Button(
            style=discord.ButtonStyle.secondary,
            label="◀ Back",
            row=2
        )
        back_btn.callback = self._on_back
        self.add_item(back_btn)
    
    async def create_embed(self) -> discord.Embed:
        db_path = Config.DATABASE_PATH
        self.crate_data = await get_crate_with_sets(self.crate_id, db_path)
        
        if not self.crate_data:
            return discord.Embed(
                title="❌ Error",
                description="Crate not found.",
                color=discord.Color.red()
            )
        
        label = self.crate_data.get('label') or self.crate_data.get('class_string', 'Unknown')
        embed = discord.Embed(
            title=f"📦 {label}",
            description=f"**{self.server_name}**\n"
                       f"Class: `{self.crate_data.get('class_string', 'N/A')}`",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="Settings",
            value=f"Min Sets: {self.crate_data.get('min_item_sets', 1)}\n"
                  f"Max Sets: {self.crate_data.get('max_item_sets', 1)}\n"
                  f"Prevent Duplicates: {'Yes' if self.crate_data.get('prevent_duplicates') else 'No'}",
            inline=True
        )
        
        item_sets = self.crate_data.get('item_sets', [])
        if item_sets:
            sets_text = []
            for i, item_set in enumerate(item_sets, 1):
                items_count = len(item_set.get('items') or [])
                sets_text.append(f"**Set {i}** (Weight: {item_set.get('weight', 1.0)}) - {items_count} items")
            embed.add_field(
                name=f"Item Sets ({len(item_sets)})",
                value="\n".join(sets_text) or "None",
                inline=False
            )
        else:
            embed.add_field(
                name="Item Sets",
                value="No item sets configured. Click 'Add Item Set' to begin.",
                inline=False
            )
        
        return embed
    
    async def _on_settings(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CrateSettingsModal(self.crate_id))
    
    async def _on_add_set(self, interaction: discord.Interaction):
        db_path = Config.DATABASE_PATH
        set_id = await create_item_set(
            crate_config_id=self.crate_id,
            set_name="New Item Set",
            db_path=db_path
        )
        
        if set_id:
            embed = await self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Failed to add item set.", ephemeral=True)
    
    async def _on_export(self, interaction: discord.Interaction):
        db_path = Config.DATABASE_PATH
        ini_output = await export_crate_to_ini(self.crate_id, db_path)
        
        if ini_output:
            if len(ini_output) > 1900:
                ini_output = ini_output[:1900] + "\n..."
            await interaction.response.send_message(f"```ini\n{ini_output}\n```", ephemeral=True)
        else:
            await interaction.response.send_message("Failed to export crate.", ephemeral=True)
    
    async def _on_delete(self, interaction: discord.Interaction):
        db_path = Config.DATABASE_PATH
        success = await delete_crate_config(self.crate_id, db_path)
        
        if success:
            view = LootCategoryView(self.guild_id, self.server_name, self.user_id)
            embed = discord.Embed(
                title=f"📦 Loot Crates - {self.server_name}",
                description="Crate deleted. Select a category to continue.",
                color=discord.Color.gold()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("Failed to delete crate.", ephemeral=True)
    
    async def _on_back(self, interaction: discord.Interaction):
        view = LootCategoryView(self.guild_id, self.server_name, self.user_id)
        embed = discord.Embed(
            title=f"📦 Loot Crates - {self.server_name}",
            description="Select a category to view or configure loot crates.",
            color=discord.Color.gold()
        )
        await interaction.response.edit_message(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(LootCrateCog(bot))
