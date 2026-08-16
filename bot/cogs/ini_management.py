"""
INI Management Cog - Section-based INI settings editor.

Design:
- Server → File → Section-based categories
- Mod sections auto-detected and grouped
- 🟠 Dynamic / 🔴 Restart Required indicators
- Edit modals for values
- Search functionality for large lists
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
import logging
from typing import Optional, List, Dict, Any
from collections import OrderedDict
import re

from bot.database import ini_settings_db, server_config_db
from bot.utils.ini_parser import is_complex_key
from bot.utils.ini_classification import is_dynamic_setting, is_server_specific
from bot.utils.subscription_checker import check_feature

logger = logging.getLogger("IniManagement")

MOD_SECTION_PATTERNS = [
    r"CybersStructures",
    r"Shiny",
    r"ARKomatic",
    r"SuperSpyglassPlus",
    r"InventorySaver",
    r"Scribbles",
    r"StarterKit",
    r"Startup",
    r"AdminsArsenal",
    r"OmegaTeleporters",
    r"ATJCreatures",
    r"Trojan",
    r"ZytharianCritters",
]

SECTION_ORDER = [
    "ServerSettings",
    "SessionSettings",
    "/Script/ShooterGame.ShooterGameUserSettings",
    "/Script/Engine.GameUserSettings",
    "ScalabilityGroups",
    "/Script/ShooterGame.ShooterGameMode",
    "/Game/PrimalEarth/CoreBlueprints/TestGameMode.TestGameMode_C",
    "MessageOfTheDay",
    "/Script/Engine.GameSession",
]

SECTION_ICONS = {
    "ServerSettings": "🖥️",
    "SessionSettings": "🔧",
    "/Script/ShooterGame.ShooterGameUserSettings": "⚙️",
    "/Script/ShooterGame.ShooterGameMode": "🎮",
    "/Game/PrimalEarth/CoreBlueprints/TestGameMode.TestGameMode_C": "🎮",
    "ScalabilityGroups": "📊",
    "MessageOfTheDay": "📢",
    "/Script/Engine.GameSession": "🔧",
    "/Script/Engine.GameUserSettings": "⚙️",
}


def is_mod_section(section_name: str) -> bool:
    """Check if a section is a mod-specific section."""
    for pattern in MOD_SECTION_PATTERNS:
        if re.search(pattern, section_name, re.IGNORECASE):
            return True
    return False


def get_section_display_name(section_name: str) -> str:
    """Get display name for a section (actual name with optional icon)."""
    if section_name in SECTION_ICONS:
        return f"{SECTION_ICONS[section_name]} [{section_name}]"
    
    if is_mod_section(section_name):
        return f"🧩 [{section_name}]"
    
    return f"📁 [{section_name}]"


def format_value_for_display(value: str) -> str:
    """Format a value for display."""
    if not value:
        return "`(empty)`"
    
    lower = str(value).lower().strip()
    if lower in ("true", "1", "on", "yes"):
        return "`True`"
    elif lower in ("false", "0", "off", "no"):
        return "`False`"
    elif len(value) > 25:
        return f"`{value[:25]}...`"
    return f"`{value}`"


async def _log_to_channel(bot, guild_id: int, message: str):
    """Send a message to the guild's configured server log channel."""
    try:
        from bot.database import server_config_db
        config = await server_config_db.get_server_config(guild_id)
        if not config:
            logger.warning(f"No config found for guild {guild_id}")
            return
        channel_id = config.get("server_log_channel_id")
        if not channel_id:
            logger.warning(f"server_log_channel_id not configured for guild {guild_id}")
            return
        channel = bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Server log channel {channel_id} not found for guild {guild_id}")
            return
        await channel.send(message)
    except Exception as e:
        logger.error(f"Failed to send to server log channel: {e}")


class IniEditModal(Modal):
    """Modal for editing a single setting."""

    def __init__(self, setting: Dict, guild_id: int, server_name: str, file_name: str, user_id: int, parent_view=None):
        key_name = setting.get("key_name", "Setting")
        super().__init__(title=f"Edit: {key_name[:40]}", timeout=None)
        self.setting = setting
        self.guild_id = guild_id
        self.server_name = server_name
        self.file_name = file_name
        self.user_id = user_id
        self.parent_view = parent_view
        
        current_value = setting.get("key_value", "")
        is_dynamic = is_dynamic_setting(key_name, file_name)
        
        hint = "🟢 Dynamic - applies immediately" if is_dynamic else "🔴 Restart required - queued"
        
        self.value_input = TextInput(
            label=f"Value ({hint})",
            default=current_value,
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=2000,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        key = self.setting.get("key_name", "")
        value = self.value_input.value.strip()
        section = self.setting.get("section_name", "ServerSettings")
        old_value = self.setting.get("key_value", "")
        
        def normalize_for_compare(v):
            if not v:
                return ""
            return str(v).strip().lower()
        
        if normalize_for_compare(value) == normalize_for_compare(old_value):
            await interaction.response.send_message(
                f"ℹ️ **{key}** unchanged - value is already `{value}`",
                ephemeral=True,
            )
            return
        
        is_dynamic = is_dynamic_setting(key, self.file_name)
        
        if is_dynamic:
            success = await ini_settings_db.update_ini_setting(
                self.guild_id, self.server_name, self.file_name,
                section, key, value
            )
            if success:
                await _log_to_channel(
                    interaction.client, self.guild_id,
                    f"[INI Edit] **{self.server_name}** • {self.file_name}\n"
                    f"🟢 **{key}**: `{old_value}` → `{value}` (dynamic, applied immediately)"
                )
                agent_manager = getattr(interaction.client, 'agent_manager', None)
                
                if agent_manager:
                    agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)
                    if agent_id:
                        result = await agent_manager.update_ini_setting(
                            agent_id, self.server_name, self.file_name, section, key, value
                        )
                        
                        if result.get("type") == "complete":
                            # Reload settings and replace message with refreshed view
                            try:
                                updated_settings = await ini_settings_db.get_ini_settings(
                                    self.guild_id, self.server_name, self.file_name
                                )
                                new_view = IniSettingsView(
                                    self.guild_id,
                                    self.server_name,
                                    self.file_name,
                                    updated_settings,
                                    self.user_id,
                                    section=self.parent_view.current_section if hasattr(self, 'parent_view') else None,
                                    page=self.parent_view.page if hasattr(self, 'parent_view') else 0,
                                    search_term=self.parent_view.search_term if hasattr(self, 'parent_view') else "",
                                )
                                new_embed = new_view.create_embed()
                                new_embed.description = f"✅ **{key}** updated to `{value}`\n\n" + (new_embed.description or "")
                                await interaction.response.edit_message(embed=new_embed, view=new_view)
                            except Exception as e:
                                logger.error(f"Failed to refresh INI view: {e}")
                                await interaction.response.send_message(
                                    f"✅ **{key}** updated to `{value}`\n🟢 Written to INI file.",
                                    ephemeral=True,
                                )
                            return
                        else:
                            err = result.get("error", "Unknown error")
                            await interaction.response.send_message(
                                f"⚠️ DB updated but failed to write INI: {err}",
                                ephemeral=True,
                            )
                            return
                
                await interaction.response.send_message(
                    f"✅ **{key}** updated in database (agent not connected for file write).",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Failed to update setting.",
                    ephemeral=True,
                )
        else:
            success = await ini_settings_db.queue_ini_change(
                self.guild_id, self.server_name, self.file_name,
                section, key, value, old_value, self.user_id
            )
            if success:
                await _log_to_channel(
                    interaction.client, self.guild_id,
                    f"[INI Edit] **{self.server_name}** • {self.file_name}\n"
                    f"🔴 **{key}**: `{old_value}` → `{value}` (restart required, queued)"
                )
                
                # Reload settings and replace message with refreshed view
                try:
                    updated_settings = await ini_settings_db.get_ini_settings(
                        self.guild_id, self.server_name, self.file_name
                    )
                    new_view = IniSettingsView(
                        self.guild_id,
                        self.server_name,
                        self.file_name,
                        updated_settings,
                        self.user_id,
                        section=self.parent_view.current_section if self.parent_view else None,
                        page=self.parent_view.page if self.parent_view else 0,
                        search_term=self.parent_view.search_term if self.parent_view else "",
                    )
                    new_embed = new_view.create_embed()
                    new_embed.description = f"📋 **{key}** queued: `{old_value}` → `{value}`\n🔴 Restart required\n\n" + (new_embed.description or "")
                    await interaction.response.edit_message(embed=new_embed, view=new_view)
                except Exception as e:
                    logger.error(f"Failed to refresh INI view after queue: {e}")
                    await interaction.response.send_message(
                        f"📋 **{key}** queued: `{old_value}` → `{value}`\n🔴 Requires server restart - will apply on next stop.",
                        ephemeral=True,
                    )
            else:
                await interaction.response.send_message(
                    "Failed to queue change.",
                    ephemeral=True,
                )


class IniSearchModal(Modal):
    """Modal for searching settings."""

    def __init__(self, view: "IniSettingsView"):
        super().__init__(title="Search Settings", timeout=None)
        self.parent_view = view
        
        self.search_input = TextInput(
            label="Search term",
            placeholder="Enter setting name or value to search...",
            required=True,
            max_length=100,
        )
        self.add_item(self.search_input)

    async def on_submit(self, interaction: discord.Interaction):
        search_term = self.search_input.value.strip().lower()
        self.parent_view.search_term = search_term
        self.parent_view.page = 0
        self.parent_view._build_ui()
        embed = self.parent_view.create_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class IniSettingsView(View):
    """Section-based settings view with search and edit buttons."""

    def __init__(
        self,
        guild_id: int,
        server_name: str,
        file_name: str,
        settings: List[Dict],
        user_id: int,
        section: Optional[str] = None,
        page: int = 0,
        search_term: str = "",
    ):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.server_name = server_name
        self.file_name = file_name
        self.all_settings = settings
        self.user_id = user_id
        self.current_section = section
        self.page = page
        self.per_page = 8
        self.search_term = search_term
        
        self._group_by_section()
        self._build_ui()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    def _group_by_section(self):
        self.sections: Dict[str, List[Dict]] = OrderedDict()
        
        for setting in self.all_settings:
            key = setting.get("key_name", "")
            if is_complex_key(key):
                continue
            section = setting.get("section_name", "Other")
            if section not in self.sections:
                self.sections[section] = []
            self.sections[section].append(setting)

    def _get_settings_to_show(self) -> List[Dict]:
        if self.search_term:
            results = []
            for s in self.all_settings:
                key = s.get("key_name", "").lower()
                value = str(s.get("key_value", "")).lower()
                if self.search_term in key or self.search_term in value:
                    results.append(s)
            return results
        
        if self.current_section and self.current_section in self.sections:
            return self.sections[self.current_section]
        
        def section_sort_key(section_name):
            if section_name in SECTION_ORDER:
                return (0, SECTION_ORDER.index(section_name))
            elif is_mod_section(section_name):
                return (2, section_name.lower())
            else:
                return (1, section_name.lower())
        
        sorted_sections = sorted(self.sections.keys(), key=section_sort_key)
        
        settings = []
        for section in sorted_sections:
            settings.extend(self.sections[section])
        
        return settings
        
        if self.current_section and self.current_section in self.sections:
            return self.sections[self.current_section]
        
        for section_settings in self.sections.values():
            settings.extend(section_settings)
        
        return settings

    def _build_ui(self):
        self.clear_items()
        
        def section_sort_key(section_name):
            if section_name in SECTION_ORDER:
                return (0, SECTION_ORDER.index(section_name))
            elif is_mod_section(section_name):
                return (2, section_name.lower())
            else:
                return (1, section_name.lower())
        
        sorted_sections = sorted(self.sections.keys(), key=section_sort_key)
        
        section_options = [discord.SelectOption(label="📋 All Sections", value="all")]
        for section_name in sorted_sections:
            section_settings = self.sections[section_name]
            display_name = get_section_display_name(section_name)
            count = len(section_settings)
            section_options.append(discord.SelectOption(
                label=f"{display_name} ({count})",
                value=section_name,
                description=f"{count} settings"
            ))
        
        select = Select(
            placeholder="Filter by section...",
            options=section_options[:25],
            row=0,
        )
        select.callback = self._on_section_select
        self.add_item(select)
        
        settings_to_show = self._get_settings_to_show()
        total_pages = max(1, (len(settings_to_show) + self.per_page - 1) // self.per_page)
        
        nav_row = 1
        prev_btn = Button(
            style=discord.ButtonStyle.secondary,
            label="◀ Prev",
            row=nav_row,
            disabled=self.page == 0,
        )
        prev_btn.callback = self._prev_page
        self.add_item(prev_btn)
        
        page_btn = Button(
            style=discord.ButtonStyle.secondary,
            label=f"Page {self.page + 1}/{total_pages}",
            row=nav_row,
            disabled=True,
        )
        self.add_item(page_btn)
        
        next_btn = Button(
            style=discord.ButtonStyle.secondary,
            label="Next ▶",
            row=nav_row,
            disabled=self.page >= total_pages - 1,
        )
        next_btn.callback = self._next_page
        self.add_item(next_btn)
        
        self._build_edit_buttons()
        
        search_btn = Button(
            style=discord.ButtonStyle.secondary,
            label="🔍 Search",
            row=4,
        )
        search_btn.callback = self._open_search
        self.add_item(search_btn)
        
        if self.search_term:
            clear_btn = Button(
                style=discord.ButtonStyle.secondary,
                label=f"✕ Clear",
                row=4,
            )
            clear_btn.callback = self._clear_search
            self.add_item(clear_btn)
        
        back_btn = Button(
            style=discord.ButtonStyle.secondary,
            label="◀ Back",
            row=4,
        )
        back_btn.callback = self._go_back
        self.add_item(back_btn)

    def create_embed(self) -> discord.Embed:
        if self.search_term:
            title = f"🔍 Search: '{self.search_term}'"
        elif self.current_section:
            title = f"{get_section_display_name(self.current_section)}"
        else:
            title = "📋 All Settings"
        
        embed = discord.Embed(
            title=title,
            description=f"**{self.server_name}** • {self.file_name}\n"
                        f"🟢 = Dynamic (immediate) • 🔴 = Restart Required",
            color=discord.Color.blue(),
        )
        
        settings_to_show = self._get_settings_to_show()
        start = self.page * self.per_page
        end = min(start + self.per_page, len(settings_to_show))
        page_settings = settings_to_show[start:end]
        
        if page_settings:
            show_sections = self.search_term or not self.current_section
            
            if show_sections:
                current_section = None
                lines = []
                
                for idx, s in enumerate(page_settings, start + 1):
                    section = s.get("section_name", "Unknown")
                    key = s.get("key_name", "?")
                    value = s.get("key_value", "")
                    is_dyn = is_dynamic_setting(key, self.file_name)
                    icon = "🟢" if is_dyn else "🔴"
                    display = format_value_for_display(str(value))
                    
                    if section != current_section:
                        current_section = section
                        section_display = get_section_display_name(section)
                        lines.append(f"━━━ **{section_display}** ━━━")
                    
                    lines.append(f"**{idx}.** {icon} {key} = {display}")
                
                value_text = "\n".join(lines)
                if len(value_text) > 1024:
                    value_text = value_text[:1020] + "..."
                
                embed.add_field(
                    name="\u200b",
                    value=value_text,
                    inline=False,
                )
            else:
                lines = []
                for idx, s in enumerate(page_settings, start + 1):
                    key = s.get("key_name", "?")
                    value = s.get("key_value", "")
                    is_dyn = is_dynamic_setting(key, self.file_name)
                    icon = "🟢" if is_dyn else "🔴"
                    display = format_value_for_display(str(value))
                    lines.append(f"**{idx}.** {icon} {key} = {display}")
                
                embed.add_field(
                    name="\u200b",
                    value="\n".join(lines),
                    inline=False,
                )
        
        total = len(settings_to_show)
        if total == 0:
            embed.add_field(
                name="No settings found",
                value="Try a different search term or section.",
                inline=False,
            )
            total = 1
        
        embed.set_footer(text=f"Showing {start + 1}-{end} of {total} • Use Edit buttons below")
        
        return embed

    def _build_edit_buttons(self):
        settings_to_show = self._get_settings_to_show()
        start = self.page * self.per_page
        end = min(start + self.per_page, len(settings_to_show))
        page_settings = settings_to_show[start:end]
        
        for idx, s in enumerate(page_settings):
            if idx >= 8:
                break
            btn = Button(
                style=discord.ButtonStyle.primary,
                label=f"Edit {start + idx + 1}",
                row=2 + (idx // 4),
            )
            btn.callback = lambda interaction, setting=s: self._edit_setting(interaction, setting)
            self.add_item(btn)

    async def _edit_setting(self, interaction: discord.Interaction, setting: Dict):
        modal = IniEditModal(
            setting, self.guild_id, self.server_name, self.file_name, self.user_id, parent_view=self
        )
        await interaction.response.send_modal(modal)

    async def _open_search(self, interaction: discord.Interaction):
        modal = IniSearchModal(self)
        await interaction.response.send_modal(modal)

    async def _clear_search(self, interaction: discord.Interaction):
        self.search_term = ""
        self.page = 0
        self._build_ui()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_section_select(self, interaction: discord.Interaction):
        for item in self.children:
            if isinstance(item, Select) and item.values:
                selected = item.values[0]
                self.current_section = selected if selected != "all" else None
                break
        self.page = 0
        self.search_term = ""
        self._build_ui()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _prev_page(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self._build_ui()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _next_page(self, interaction: discord.Interaction):
        settings_to_show = self._get_settings_to_show()
        total_pages = max(1, (len(settings_to_show) + self.per_page - 1) // self.per_page)
        self.page = min(total_pages - 1, self.page + 1)
        self._build_ui()
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _go_back(self, interaction: discord.Interaction):
        servers = await server_config_db.get_ark_servers(self.guild_id)
        view = IniServerSelectView(self.guild_id, servers, self.user_id)
        embed = discord.Embed(
            title="📝 INI Management",
            description="Select a server and INI file to edit settings.\n\n"
                        "🟢 = Dynamic (applies immediately)\n"
                        "🔴 = Restart Required (queued)",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(embed=embed, view=view)


class IniServerSelectView(View):
    """Server and file selection with proper workflow."""

    def __init__(self, guild_id: int, servers: List[Dict], user_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.servers = servers
        self.user_id = user_id
        self.selected_server: Optional[str] = None
        self.selected_file: Optional[str] = None
        
        self._build_ui()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    def _build_ui(self):
        server_options = []
        for server in self.servers[:25]:
            name = server.get("name", "Unknown")
            server_options.append(discord.SelectOption(label=name, value=name))
        
        server_select = Select(
            placeholder="🖥️ Select server...",
            options=server_options,
            row=0,
        )
        server_select.callback = self._on_server_select
        self.add_item(server_select)
        
        file_options = [
            discord.SelectOption(
                label="GameUserSettings.ini",
                value="GameUserSettings.ini",
                description="Server settings, multipliers, mods"
            ),
            discord.SelectOption(
                label="Game.ini",
                value="Game.ini",
                description="Gameplay overrides, engrams, spawns"
            ),
        ]
        file_select = Select(
            placeholder="📄 Select INI file...",
            options=file_options,
            row=1,
        )
        file_select.callback = self._on_file_select
        self.add_item(file_select)
        
        go_btn = Button(
            style=discord.ButtonStyle.success,
            label="✅ Open Settings",
            row=2,
            disabled=True,
        )
        go_btn.callback = self._open_settings
        self.go_button = go_btn
        self.add_item(go_btn)
        
        # Loot Crates button - DISABLED until spreadsheet approach implemented
        # loot_btn = Button(
        #     style=discord.ButtonStyle.primary,
        #     label="📦 Loot Crates",
        #     row=3,
        #     disabled=True,
        # )
        # loot_btn.callback = self._open_loot_crates
        # self.loot_button = loot_btn
        # self.add_item(loot_btn)
        self.loot_button = None  # Placeholder

        if len(self.servers) >= 2:
            self.add_item(BatchEditButton(self.servers, self.guild_id, self.user_id))

    async def _on_server_select(self, interaction: discord.Interaction):
        for item in self.children:
            if isinstance(item, Select) and item.values and item.row == 0:
                self.selected_server = item.values[0]
                break
        self._update_go_button()
        embed = self._create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_file_select(self, interaction: discord.Interaction):
        for item in self.children:
            if isinstance(item, Select) and item.values and item.row == 1:
                self.selected_file = item.values[0]
                break
        self._update_go_button()
        embed = self._create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def _update_go_button(self):
        if self.selected_server and self.selected_file:
            self.go_button.disabled = False
            self.go_button.label = f"✅ Open {self.selected_file[:15]}"
        else:
            self.go_button.disabled = True
            self.go_button.label = "✅ Open Settings"
        
        # Enable loot crates button when server is selected
        # self.loot_button.disabled = not self.selected_server  # DISABLED with loot crates
        pass

    def _create_embed(self) -> discord.Embed:
        server_status = f"✅ **{self.selected_server}**" if self.selected_server else "⬜ Select a server"
        file_status = f"✅ **{self.selected_file}**" if self.selected_file else "⬜ Select an INI file"
        
        return discord.Embed(
            title="📝 INI Management",
            description=f"Select a server and INI file to edit settings.\n\n"
                        f"**Server:** {server_status}\n"
                        f"**File:** {file_status}\n\n"
                        f"🟢 = Dynamic (applies immediately)\n"
                        f"🔴 = Restart Required (queued)",
            color=discord.Color.blue(),
        )

    async def _open_settings(self, interaction: discord.Interaction):
        if not self.selected_server or not self.selected_file:
            await interaction.response.send_message(
                "Please select both a server and an INI file.",
                ephemeral=True,
            )
            return
        
        settings = await ini_settings_db.get_ini_settings(
            self.guild_id, self.selected_server, self.selected_file
        )
        
        if not settings:
            await interaction.response.send_message(
                f"No settings found for **{self.selected_file}**.\n"
                "Settings are auto-imported when the remote agent connects. "
                "Make sure your agent is connected.",
                ephemeral=True,
            )
            return
        
        view = IniSettingsView(
            self.guild_id, self.selected_server, self.selected_file,
            settings, self.user_id
        )
        embed = view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    # DISABLED: Loot crates deferred until spreadsheet approach implemented
    # async def _open_loot_crates(self, interaction: discord.Interaction):
    #     """Open the loot crate editor for the selected server."""
    #     if not self.selected_server:
    #         await interaction.response.send_message(
    #             "Please select a server first.",
    #             ephemeral=True,
    #         )
    #         return
    #     
    #     from bot.cogs.loot_crate_editor import LootCrateEntryView
    #     
    #     view = LootCrateEntryView(self.guild_id, self.selected_server, self.user_id)
    #     await view.build_ui()
    #     embed = await view.create_embed()
    #     await interaction.response.edit_message(embed=embed, view=view)


class BatchEditButton(Button):
    """Button to launch the batch INI edit flow. Added to IniServerSelectView when 2+ servers."""

    def __init__(self, servers: List[Dict], guild_id: int, user_id: int):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="🌐 Batch Edit",
            row=3,
        )
        self.servers = servers
        self.guild_id = guild_id
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        view = BatchIniServerSelectView(
            servers=self.servers,
            guild_id=self.guild_id,
            user_id=self.user_id,
        )
        embed = discord.Embed(
            title="🌐 Batch INI Edit — Select Servers",
            description="Select which servers to apply the INI change to.",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class BatchIniServerSelectView(View):
    """Multi-server picker for batch INI editing."""

    def __init__(self, servers: List[Dict], guild_id: int, user_id: int):
        super().__init__(timeout=180)
        self.servers = servers
        self.guild_id = guild_id
        self.user_id = user_id
        self.selected_servers: List[str] = []
        self._build_ui()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    def _build_ui(self):
        self.clear_items()

        options = [
            discord.SelectOption(label=s.get("name", "Unknown"), value=s.get("name", "Unknown"))
            for s in self.servers[:25]
        ]
        select = Select(
            placeholder="Select servers to edit...",
            options=options,
            min_values=1,
            max_values=min(25, len(self.servers)),
            row=0,
        )
        select.callback = self._on_select
        self.add_item(select)

        all_btn = Button(style=discord.ButtonStyle.success, label="✅ All Servers", row=1)
        all_btn.callback = self._select_all
        self.add_item(all_btn)

        self.continue_btn = Button(
            style=discord.ButtonStyle.primary,
            label="Continue →",
            row=1,
            disabled=len(self.selected_servers) == 0,
        )
        self.continue_btn.callback = self._continue
        self.add_item(self.continue_btn)

        cancel_btn = Button(style=discord.ButtonStyle.secondary, label="❌ Cancel", row=1)
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    async def _on_select(self, interaction: discord.Interaction):
        for item in self.children:
            if isinstance(item, Select) and item.values:
                self.selected_servers = list(item.values)
                break
        self._build_ui()
        await interaction.response.edit_message(view=self)

    async def _select_all(self, interaction: discord.Interaction):
        self.selected_servers = [s.get("name", "Unknown") for s in self.servers]
        self._build_ui()
        await interaction.response.edit_message(view=self)

    async def _continue(self, interaction: discord.Interaction):
        if not self.selected_servers:
            await interaction.response.send_message(
                "Please select at least one server.", ephemeral=True
            )
            return
        view = BatchIniFileSelectView(
            server_names=self.selected_servers,
            guild_id=self.guild_id,
            user_id=self.user_id,
        )
        embed = discord.Embed(
            title="🌐 Batch INI Edit — Select File",
            description=f"**Servers:** {', '.join(self.selected_servers)}\n\nSelect which INI file to edit.",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def _cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Cancelled.", embed=None, view=None)


class BatchIniFileSelectView(View):
    """Pick which INI file to batch-edit."""

    def __init__(self, server_names: List[str], guild_id: int, user_id: int):
        super().__init__(timeout=180)
        self.server_names = server_names
        self.guild_id = guild_id
        self.user_id = user_id
        self._build_ui()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    def _build_ui(self):
        self.clear_items()

        gus_btn = Button(
            style=discord.ButtonStyle.primary,
            label="📄 GameUserSettings.ini",
            row=0,
        )
        gus_btn.callback = lambda i: self._open_settings(i, "GameUserSettings.ini")
        self.add_item(gus_btn)

        game_btn = Button(
            style=discord.ButtonStyle.primary,
            label="📄 Game.ini",
            row=0,
        )
        game_btn.callback = lambda i: self._open_settings(i, "Game.ini")
        self.add_item(game_btn)

        cancel_btn = Button(style=discord.ButtonStyle.secondary, label="❌ Cancel", row=0)
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    async def _open_settings(self, interaction: discord.Interaction, file_name: str):
        reference = self.server_names[0]
        settings = await ini_settings_db.get_ini_settings(self.guild_id, reference, file_name)

        if not settings:
            await interaction.response.edit_message(
                content=(
                    f"No settings found for **{file_name}** on **{reference}**.\n"
                    "Settings are auto-imported when the remote agent connects."
                ),
                embed=None,
                view=None,
            )
            return

        view = BatchIniSettingsView(
            server_names=self.server_names,
            guild_id=self.guild_id,
            file_name=file_name,
            settings=settings,
            user_id=self.user_id,
        )
        embed = view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    async def _cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Cancelled.", embed=None, view=None)


class BatchIniSettingsView(IniSettingsView):
    """
    Variant of IniSettingsView for batch editing.
    Shows 'Select N' buttons instead of 'Edit N'; selecting a setting opens
    BatchIniValueModal which applies to all server_names.
    """

    def __init__(
        self,
        server_names: List[str],
        guild_id: int,
        file_name: str,
        settings: List[Dict],
        user_id: int,
        section: Optional[str] = None,
        page: int = 0,
        search_term: str = "",
    ):
        # Must be set BEFORE super().__init__ which calls _build_ui → _build_edit_buttons
        self.server_names = server_names
        reference = server_names[0] if server_names else "Unknown"
        super().__init__(guild_id, reference, file_name, settings, user_id, section, page, search_term)

    def _get_settings_to_show(self) -> List[Dict]:
        """Override: exclude server-specific keys and sections from batch editing."""
        settings = super()._get_settings_to_show()
        return [
            s for s in settings
            if not is_server_specific(s.get("key_name", ""), s.get("section_name", ""))
        ]

    def _build_edit_buttons(self):
        """Override: 'Select N' buttons instead of 'Edit N'."""
        settings_to_show = self._get_settings_to_show()
        start = self.page * self.per_page
        end = min(start + self.per_page, len(settings_to_show))
        page_settings = settings_to_show[start:end]

        for idx, s in enumerate(page_settings):
            if idx >= 8:
                break
            btn = Button(
                style=discord.ButtonStyle.success,
                label=f"Select {start + idx + 1}",
                row=2 + (idx // 4),
            )
            btn.callback = lambda interaction, setting=s: self._select_setting(interaction, setting)
            self.add_item(btn)

    async def _select_setting(self, interaction: discord.Interaction, setting: Dict):
        modal = BatchIniValueModal(
            server_names=self.server_names,
            file_name=self.file_name,
            setting=setting,
            guild_id=self.guild_id,
            user_id=self.user_id,
        )
        await interaction.response.send_modal(modal)

    def create_embed(self) -> discord.Embed:
        """Override: show batch server context in description."""
        embed = super().create_embed()
        count = len(self.server_names)
        if count <= 3:
            servers_display = ", ".join(self.server_names)
        else:
            servers_display = f"{', '.join(self.server_names[:3])} +{count - 3} more"
        embed.description = (
            f"**🌐 Batch Edit — {count} server{'s' if count != 1 else ''}**: {servers_display}\n"
            f"**File:** {self.file_name} (settings from **{self.server_names[0]}**)\n"
            f"🟢 = Dynamic (immediate) • 🔴 = Restart Required\n"
            f"🔒 Server-specific settings (ports, name, map, passwords, paths) are excluded.\n"
            f"Click **Select N** to apply that setting to all selected servers."
        )
        return embed

    async def _go_back(self, interaction: discord.Interaction):
        """Override: go back to file select (not server select)."""
        view = BatchIniFileSelectView(
            server_names=self.server_names,
            guild_id=self.guild_id,
            user_id=self.user_id,
        )
        embed = discord.Embed(
            title="🌐 Batch INI Edit — Select File",
            description=f"**Servers:** {', '.join(self.server_names)}\n\nSelect which INI file to edit.",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(embed=embed, view=view)


class BatchIniValueModal(Modal):
    """Single-field value modal for batch INI editing. Pre-filled with the current value."""

    def __init__(self, server_names: List[str], file_name: str, setting: Dict, guild_id: int, user_id: int):
        key_name = setting.get("key_name", "Setting")
        super().__init__(title=f"Batch Edit: {key_name[:40]}", timeout=None)
        self.server_names = server_names
        self.file_name = file_name
        self.setting = setting
        self.guild_id = guild_id
        self.user_id = user_id

        current_value = setting.get("key_value", "") or ""
        is_dynamic = is_dynamic_setting(key_name, file_name)
        hint = "🟢 Dynamic — applies immediately" if is_dynamic else "🔴 Restart Required — queued"

        self.value_input = TextInput(
            label=f"New Value ({hint})",
            default=current_value,
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=2000,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        key = self.setting.get("key_name", "")
        value = self.value_input.value.strip()
        section = self.setting.get("section_name", "")
        current_value = self.setting.get("key_value", "")

        is_dynamic = is_dynamic_setting(key, self.file_name)
        dynamic_text = "🟢 Dynamic (applies immediately)" if is_dynamic else "🔴 Restart Required"

        server_list = "\n".join(f"• {s}" for s in self.server_names)

        embed = discord.Embed(title="Confirm Batch INI Edit", color=discord.Color.orange())
        embed.add_field(name="File", value=self.file_name, inline=True)
        embed.add_field(name="Section", value=f"`{section}`", inline=True)
        embed.add_field(name="Key", value=f"`{key}`", inline=True)
        embed.add_field(name="Current Value", value=format_value_for_display(current_value), inline=True)
        embed.add_field(name="New Value", value=f"`{value}`" if value else "`(empty)`", inline=True)
        embed.add_field(name="Apply Mode", value=dynamic_text, inline=True)
        embed.add_field(name=f"Servers ({len(self.server_names)})", value=server_list[:1024], inline=False)

        view = BatchIniEditConfirmView(
            server_names=self.server_names,
            file_name=self.file_name,
            key=key,
            value=value,
            is_dynamic=is_dynamic,
            guild_id=self.guild_id,
            user_id=self.user_id,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class BatchIniEditConfirmView(View):
    """Confirm/cancel view that applies the batch INI change across all selected servers."""

    def __init__(
        self,
        server_names: List[str],
        file_name: str,
        key: str,
        value: str,
        is_dynamic: bool,
        guild_id: int,
        user_id: int,
    ):
        super().__init__(timeout=180)
        self.server_names = server_names
        self.file_name = file_name
        self.key = key
        self.value = value
        self.is_dynamic = is_dynamic
        self.guild_id = guild_id
        self.user_id = user_id

        confirm_btn = Button(style=discord.ButtonStyle.success, label="✅ Confirm", row=0)
        confirm_btn.callback = self._confirm
        self.add_item(confirm_btn)

        cancel_btn = Button(style=discord.ButtonStyle.secondary, label="❌ Cancel", row=0)
        cancel_btn.callback = self._cancel
        self.add_item(cancel_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def _confirm(self, interaction: discord.Interaction):
        await interaction.response.defer()

        bot = interaction.client
        agent_manager = getattr(bot, "agent_manager", None)

        if not agent_manager:
            await interaction.edit_original_response(
                content="❌ No agent manager available.", embed=None, view=None
            )
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)

        results = []
        for server_name in self.server_names:
            try:
                # Resolve section from DB for this server
                existing = await ini_settings_db.find_ini_setting_by_key(
                    self.guild_id, server_name, self.file_name, self.key
                )
                if not existing:
                    results.append(f"❌ **{server_name}**: Key `{self.key}` not found in {self.file_name}")
                    continue

                section = existing["section_name"]
                old_value = existing.get("key_value")

                if self.is_dynamic:
                    db_ok = await ini_settings_db.update_ini_setting(
                        self.guild_id, server_name, self.file_name,
                        section, self.key, self.value,
                    )
                    if not db_ok:
                        results.append(f"❌ **{server_name}**: DB write failed")
                        continue

                    if agent_id:
                        result = await agent_manager.update_ini_setting(
                            agent_id, server_name, self.file_name,
                            section, self.key, self.value,
                        )
                        if result.get("type") == "complete":
                            results.append(f"✅ **{server_name}**: Applied")
                        else:
                            err = result.get("error", "Unknown error")
                            results.append(f"❌ **{server_name}**: Agent error — {err}")
                    else:
                        results.append(f"⚠️ **{server_name}**: DB updated (agent offline)")
                else:
                    ok = await ini_settings_db.queue_ini_change(
                        self.guild_id, server_name, self.file_name,
                        section, self.key, self.value, old_value, self.user_id,
                    )
                    if ok:
                        results.append(f"⏳ **{server_name}**: Queued (restart required)")
                    else:
                        results.append(f"❌ **{server_name}**: Queue failed")
            except Exception as e:
                results.append(f"❌ **{server_name}**: Error — {e}")

        mode_str = "🟢 Dynamic" if self.is_dynamic else "🔴 Restart Required"
        await _log_to_channel(
            bot, self.guild_id,
            f"[Batch INI Edit] **{self.file_name}** • **{self.key}** = `{self.value}`\n"
            f"{mode_str} • Servers: {', '.join(self.server_names)}",
        )

        results_embed = discord.Embed(
            title="🌐 Batch INI Edit — Results",
            description="\n".join(results),
            color=discord.Color.green(),
        )
        results_embed.set_footer(
            text=f"{self.file_name} • {self.key} = {self.value}"
        )

        await interaction.edit_original_response(embed=results_embed, view=None)

    async def _cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Cancelled.", embed=None, view=None)


class IniManagement(commands.Cog):
    """INI file management for ARK servers."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="inimgmt", description="Manage INI settings for servers")
    @app_commands.checks.has_permissions(administrator=True)
    async def inimgmt(self, interaction: discord.Interaction):
        """Open the INI management panel."""
        if not await check_feature(interaction, "ini_management"):
            return
        servers = await server_config_db.get_ark_servers(interaction.guild_id)
        
        if not servers:
            await interaction.response.send_message(
                "No servers configured. Use `/setup` to add servers first.",
                ephemeral=True,
            )
            return
        
        view = IniServerSelectView(interaction.guild_id, servers, interaction.user.id)
        
        embed = discord.Embed(
            title="📝 INI Management",
            description="Select a server and INI file to edit settings.\n\n"
                        "🟢 = Dynamic (applies immediately)\n"
                        "🔴 = Restart Required (queued)",
            color=discord.Color.blue(),
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(IniManagement(bot))
