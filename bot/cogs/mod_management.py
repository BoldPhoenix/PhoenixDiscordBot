"""
Mod Management GUI - Interactive interface for managing ARK server mods.
Provides visual tools for viewing, adding, and removing mods from servers.
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Select, View, Button, Modal, TextInput
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging
import asyncio
import aiohttp
import os

from bot.database import curseforge_db, server_config_db
from bot.utils.config import Config
from bot.utils.subscription_checker import check_feature

logger = logging.getLogger("ModManagement")


async def _log_to_channel(bot, guild_id: int, message: str):
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


class ModInfoView(View):
    """View for mod info with Add to Server button."""

    def __init__(self, mod_id: int, mod_name: str, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        self.mod_id = mod_id
        self.mod_name = mod_name
        self.guild_id = guild_id
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Add to Server", style=discord.ButtonStyle.success, row=0)
    async def add_to_server(self, interaction: discord.Interaction, button: Button):
        """Handle Add to Server button click."""
        servers = await server_config_db.get_ark_servers(self.guild_id)

        if not servers:
            await interaction.response.send_message(
                "No servers configured. Use `/setup` to add servers first.",
                ephemeral=True,
            )
            return

        if len(servers) == 1:
            await self._add_mod_to_server(interaction, servers[0].get("name"))
        else:
            view = AddModServerSelectView(self.mod_id, servers, self.user_id)
            await interaction.response.send_message(
                f"Select server to add **{self.mod_name}** (`{self.mod_id}`):",
                view=view,
                ephemeral=True,
            )

    async def _add_mod_to_server(self, interaction: discord.Interaction, server_name: str):
        """Add mod to a specific server."""
        from bot.cogs.remote_agent import RemoteAgentManager

        agent_manager: RemoteAgentManager = getattr(
            interaction.client, "agent_manager", None
        )
        if not agent_manager:
            await interaction.response.send_message(
                "Agent manager not available.",
                ephemeral=True,
            )
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            await interaction.response.send_message(
                "No remote agent connected.",
                ephemeral=True,
            )
            return

        try:
            result = await agent_manager.get_mods(agent_id, server_name)
            if result.get("type") != "complete":
                await interaction.response.send_message(
                    f"Failed to get current mods: {result.get('error')}",
                    ephemeral=True,
                )
                return

            current_mods = result.get("data", {}).get("mod_ids", [])
            mod_id_str = str(self.mod_id)

            if mod_id_str in [str(m) for m in current_mods]:
                await interaction.response.send_message(
                    f"**{self.mod_name}** (`{self.mod_id}`) is already installed on **{server_name}**.",
                    ephemeral=True,
                )
                return

            new_mods = current_mods + [mod_id_str]
            set_result = await agent_manager.set_mods(agent_id, server_name, new_mods)

            if set_result.get("type") == "complete":
                await _log_to_channel(
                    interaction.client, self.guild_id,
                    f"[Mod Management] Added **{self.mod_name}** (`{self.mod_id}`) to **{server_name}**"
                )
                await interaction.response.send_message(
                    f"✅ Added **{self.mod_name}** (`{self.mod_id}`) to **{server_name}**.\n"
                    "Restart the server for changes to take effect.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"Failed to add mod: {set_result.get('error')}",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Error adding mod: {e}")
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True,
            )


class AddModConfirmView(View):
    """Confirmation view before adding a mod."""

    def __init__(self, mod_id: str, mod_name: str, server_name: str, guild_id: int, bot=None, parent_view=None, parent_message=None):
        super().__init__(timeout=120)
        self.mod_id = mod_id
        self.mod_name = mod_name
        self.server_name = server_name
        self.guild_id = guild_id
        self.bot = bot
        self.parent_view = parent_view
        self.parent_message = parent_message

    @discord.ui.button(label="✅ Confirm Add", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        from bot.cogs.remote_agent import RemoteAgentManager

        agent_manager: RemoteAgentManager = getattr(
            interaction.client, "agent_manager", None
        )
        if not agent_manager:
            await interaction.response.send_message(
                "Agent manager not available.", ephemeral=True
            )
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            await interaction.response.send_message(
                "No remote agent connected.", ephemeral=True
            )
            return

        try:
            result = await agent_manager.get_mods(agent_id, self.server_name)
            current_mods = result.get("data", {}).get("mod_ids", [])

            if self.mod_id in [str(m) for m in current_mods]:
                await interaction.response.send_message(
                    f"Mod `{self.mod_id}` is already installed on **{self.server_name}**.",
                    ephemeral=True
                )
                return

            new_mods = current_mods + [self.mod_id]
            set_result = await agent_manager.set_mods(agent_id, self.server_name, new_mods)

            if set_result.get("type") == "complete":
                await _log_to_channel(
                    interaction.client, self.guild_id,
                    f"[Mod Management] Added **{self.mod_name}** (`{self.mod_id}`) to **{self.server_name}**"
                )

                embed = discord.Embed(
                    title="Mod Added",
                    description=f"Added **{self.mod_name}** (`{self.mod_id}`) to **{self.server_name}**",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Total Mods", value=str(len(new_mods)), inline=True)
                embed.add_field(name="Restart Required", value="Restart server to apply.", inline=False)

                await interaction.response.edit_message(embed=embed, view=None)

                # Refresh mod embed channel in background — don't block after responding
                if self.bot:
                    mod_cog = self.bot.get_cog("ModManagement")
                    if mod_cog:
                        asyncio.create_task(mod_cog._refresh_and_send_mod_embeds())

                # Refresh parent mod list view if available
                if self.parent_view and self.parent_message:
                    try:
                        from bot.cogs.remote_agent import RemoteAgentManager
                        agent_manager = getattr(interaction.client, "agent_manager", None)
                        if agent_manager:
                            agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)
                            if agent_id:
                                result = await agent_manager.get_mods(agent_id, self.server_name)
                                if result.get("type") == "complete":
                                    self.parent_view.all_mod_ids = result.get("data", {}).get("mod_ids", [])
                                    self.parent_view.total_pages = max(1, (len(self.parent_view.all_mod_ids) + self.parent_view.mods_per_page - 1) // self.parent_view.mods_per_page)
                                    self.parent_view.current_page = min(self.parent_view.current_page, self.parent_view.total_pages - 1)
                                    self.parent_view.update_buttons()
                                    self.parent_view._create_remove_select()
                                    embed_refresh = await self.parent_view.create_embed()
                                    await self.parent_message.edit(embed=embed_refresh, view=self.parent_view)
                    except Exception as e:
                        logger.error(f"Failed to refresh parent mod list view after add: {e}")
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="❌ Cancelled. No changes made.",
            embed=None,
            view=None
        )


class RemoveModConfirmView(View):
    """Confirmation view before removing a mod."""

    def __init__(self, mod_id: str, mod_name: str, server_name: str, guild_id: int, bot=None, parent_view=None, parent_message=None):
        super().__init__(timeout=120)
        self.mod_id = mod_id
        self.mod_name = mod_name
        self.server_name = server_name
        self.guild_id = guild_id
        self.bot = bot
        self.parent_view = parent_view
        self.parent_message = parent_message

    @discord.ui.button(label="✅ Confirm Remove", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Acknowledge immediately — prevents "This interaction failed" if later steps are slow
        await interaction.response.defer()

        from bot.cogs.remote_agent import RemoteAgentManager

        agent_manager: RemoteAgentManager = getattr(
            interaction.client, "agent_manager", None
        )
        if not agent_manager:
            await interaction.edit_original_response(
                content="Agent manager not available.", embed=None, view=None
            )
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            await interaction.edit_original_response(
                content="No remote agent connected.", embed=None, view=None
            )
            return

        try:
            result = await agent_manager.get_mods(agent_id, self.server_name)
            current_mods = result.get("data", {}).get("mod_ids", [])
            new_mods = [m for m in current_mods if str(m) != self.mod_id]

            set_result = await agent_manager.set_mods(agent_id, self.server_name, new_mods)

            if set_result.get("type") == "complete":
                await _log_to_channel(
                    interaction.client, self.guild_id,
                    f"[Mod Management] Removed **{self.mod_name}** (`{self.mod_id}`) from **{self.server_name}**"
                )

                # Replace confirmation with refreshed mod list view
                try:
                    refreshed = await agent_manager.get_mods(agent_id, self.server_name)
                    if refreshed.get("type") == "complete":
                        new_mod_ids = refreshed.get("data", {}).get("mod_ids", [])
                        from bot.cogs.mod_management import ModRemoveView
                        new_view = await ModRemoveView.create(
                            new_mod_ids,
                            self.server_name,
                            self.guild_id,
                            interaction.user.id,
                            bot=self.bot
                        )
                        new_embed = await new_view.create_embed()
                        new_embed.description = f"✅ Removed **{self.mod_name}**\n\n" + (new_embed.description or "")
                        await interaction.edit_original_response(embed=new_embed, view=new_view)
                    else:
                        embed = discord.Embed(
                            title="✅ Mod Removed",
                            description=f"Removed **{self.mod_name}** (`{self.mod_id}`) from **{self.server_name}**",
                            color=discord.Color.green(),
                        )
                        embed.add_field(name="Restart Required", value="Restart server to apply.", inline=False)
                        await interaction.edit_original_response(embed=embed, view=None)
                except Exception as e:
                    logger.error(f"Failed to refresh mod list after remove: {e}")
                    embed = discord.Embed(
                        title="✅ Mod Removed",
                        description=f"Removed **{self.mod_name}** (`{self.mod_id}`) from **{self.server_name}**",
                        color=discord.Color.green(),
                    )
                    embed.add_field(name="Restart Required", value="Restart server to apply.", inline=False)
                    await interaction.edit_original_response(embed=embed, view=None)

                # Refresh the mod embed channel in the background — don't block the interaction
                if self.bot:
                    mod_cog = self.bot.get_cog("ModManagement")
                    if mod_cog:
                        asyncio.create_task(mod_cog._refresh_and_send_mod_embeds())
            else:
                error_msg = set_result.get("error", "Unknown error from agent")
                await interaction.edit_original_response(
                    content=f"❌ Failed to remove mod: {error_msg}", embed=None, view=None
                )
        except Exception as e:
            logger.error(f"ModRemoveConfirmView.confirm error: {e}", exc_info=True)
            await interaction.edit_original_response(
                content=f"❌ Error: {e}", embed=None, view=None
            )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="❌ Cancelled. No changes made.",
            embed=None,
            view=None
        )


class AddModServerSelectView(View):
    """Server selector for adding a mod from search results."""

    def __init__(self, mod_id: int, servers: list, user_id: int):
        super().__init__(timeout=None)
        self.mod_id = mod_id
        self.servers = servers
        self.user_id = user_id

        options = [
            discord.SelectOption(
                label=srv.get("name", "Unknown"),
                value=srv.get("name"),
            )
            for srv in servers[:25]
        ]

        self.server_select = Select(
            placeholder="Select server...",
            options=options,
            row=0,
        )
        self.server_select.callback = self._server_selected
        self.add_item(self.server_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def _server_selected(self, interaction: discord.Interaction):
        """Handle server selection."""
        server_name = self.server_select.values[0]
        guild_id = interaction.guild_id

        from bot.cogs.remote_agent import RemoteAgentManager

        agent_manager: RemoteAgentManager = getattr(
            interaction.client, "agent_manager", None
        )
        if not agent_manager:
            await interaction.response.edit_message(
                content="Agent manager not available.",
                view=None,
            )
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(guild_id)
        if not agent_id:
            await interaction.response.edit_message(
                content="No remote agent connected.",
                view=None,
            )
            return

        try:
            result = await agent_manager.get_mods(agent_id, server_name)
            if result.get("type") != "complete":
                await interaction.response.edit_message(
                    content=f"Failed to get mods: {result.get('error')}",
                    view=None,
                )
                return

            current_mods = result.get("data", {}).get("mod_ids", [])
            mod_id_str = str(self.mod_id)

            if mod_id_str in [str(m) for m in current_mods]:
                await interaction.response.edit_message(
                    content=f"Mod `{self.mod_id}` is already installed on **{server_name}**.",
                    view=None,
                )
                return

            new_mods = current_mods + [mod_id_str]
            set_result = await agent_manager.set_mods(agent_id, server_name, new_mods)

            if set_result.get("type") == "complete":
                mod_name = self.mod_info.get(mod_id_str, f"Mod {mod_id_str}")
                await _log_to_channel(
                    interaction.client, guild_id,
                    f"[Mod Management] Added **{mod_name}** (`{mod_id_str}`) to **{server_name}**"
                )
                await interaction.response.edit_message(
                    content=f"✅ Added mod `{mod_id_str}` to **{server_name}**.\n"
                    "Restart the server for changes to take effect.",
                    view=None,
                )
            else:
                await interaction.response.edit_message(
                    content=f"Failed to add mod: {set_result.get('error')}",
                    view=None,
                )
        except Exception as e:
            logger.error(f"Error adding mod to server: {e}")
            await interaction.response.edit_message(
                content=f"Error: {str(e)}",
                view=None,
            )


class ModListView(View):
    """Paginated view for viewing installed mods."""

    def __init__(self, mod_ids: list, mod_info: dict, server_name: str, user_id: int, mods_per_page: int = 10, guild_id: int = None, bot=None):
        super().__init__(timeout=None)
        self.all_mod_ids = mod_ids
        self.mod_info = mod_info
        self.server_name = server_name
        self.user_id = user_id
        self.mods_per_page = mods_per_page
        self.current_page = 0
        self.total_pages = max(1, (len(self.all_mod_ids) + mods_per_page - 1) // mods_per_page)
        self.guild_id = guild_id
        self.bot = bot

        self.first_button = Button(style=discord.ButtonStyle.secondary, label="⏮ First", row=0)
        self.prev_button = Button(style=discord.ButtonStyle.secondary, label="◀ Prev", row=0)
        self.page_label = Button(style=discord.ButtonStyle.secondary, label="1/1", row=0, disabled=True)
        self.next_button = Button(style=discord.ButtonStyle.secondary, label="Next ▶", row=0)
        self.last_button = Button(style=discord.ButtonStyle.secondary, label="Last ⏭", row=0)

        self.first_button.callback = self.first_page
        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page
        self.last_button.callback = self.last_page

        self.add_item(self.first_button)
        self.add_item(self.prev_button)
        self.add_item(self.page_label)
        self.add_item(self.next_button)
        self.add_item(self.last_button)

        if guild_id is not None and bot is not None:
            self.back_button = Button(style=discord.ButtonStyle.secondary, label="← Back", row=1)
            self.back_button.callback = self.go_back
            self.add_item(self.back_button)

        self.update_buttons()

    async def go_back(self, interaction: discord.Interaction):
        """Return to the main Mod Management view."""
        view = ModMainView(guild_id=self.guild_id, user=interaction.user, bot=self.bot)
        await view.load_data()
        embed = view.create_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @classmethod
    async def create(cls, mod_ids: list, server_name: str, user_id: int, mods_per_page: int = 10, guild_id: int = None, bot=None):
        """Factory method to create ModListView with mod info fetched."""
        mod_info = await cls._get_mod_names(mod_ids)
        return cls(mod_ids, mod_info, server_name, user_id, mods_per_page, guild_id=guild_id, bot=bot)

    @staticmethod
    async def _get_mod_names(mod_ids: list) -> dict:
        """Fetch mod names and URLs from cache. Returns {mod_id: {"name": ..., "url": ...}}."""
        from bot.database import curseforge_db

        result = {}
        for mod_id_str in mod_ids:
            try:
                mod_id = int(mod_id_str)
                mod = await curseforge_db.get_mod_by_id(mod_id)
                if mod:
                    result[mod_id_str] = {
                        "name": mod.get("name", "Unknown"),
                        "url": mod.get("website_url") or f"https://www.curseforge.com/ark-survival-ascended/mods/{mod_id}",
                    }
                else:
                    result[mod_id_str] = {
                        "name": f"Mod {mod_id}",
                        "url": f"https://www.curseforge.com/ark-survival-ascended/mods/{mod_id}",
                    }
            except ValueError:
                result[mod_id_str] = {
                    "name": mod_id_str,
                    "url": f"https://www.curseforge.com/ark-survival-ascended/mods/{mod_id_str}",
                }
        return result

    def update_buttons(self):
        self.first_button.disabled = self.current_page <= 0
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        self.last_button.disabled = self.current_page >= self.total_pages - 1
        self.page_label.label = f"{self.current_page + 1}/{self.total_pages}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def first_page(self, interaction: discord.Interaction):
        self.current_page = 0
        self.update_buttons()
        await self.update_message(interaction)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await self.update_message(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self.update_buttons()
        await self.update_message(interaction)

    async def last_page(self, interaction: discord.Interaction):
        self.current_page = self.total_pages - 1
        self.update_buttons()
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def create_embed(self) -> discord.Embed:
        start = self.current_page * self.mods_per_page
        end = min(start + self.mods_per_page, len(self.all_mod_ids))
        page_mod_ids = self.all_mod_ids[start:end]

        lines = []
        for idx, mid in enumerate(page_mod_ids, start + 1):
            info = self.mod_info.get(mid, {})
            if isinstance(info, dict):
                name = info.get("name", f"Mod #{mid}")
                url = info.get("url") or f"https://www.curseforge.com/ark-survival-ascended/mods/{mid}"
            else:
                # Legacy string format
                name = str(info)
                url = f"https://www.curseforge.com/ark-survival-ascended/mods/{mid}"
            lines.append(f"**{idx}.** [{name}]({url}) (`{mid}`)")

        # Use description instead of add_field — description allows 4096 chars
        # vs field value's 1024-char limit, which overflows with 10 long mod names.
        description = "\n".join(lines) if lines else "*No mods installed*"

        embed = discord.Embed(
            title=f"Mods for {self.server_name} — {len(self.all_mod_ids)} installed",
            description=description,
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"Showing {start + 1}-{end} of {len(self.all_mod_ids)} mods")
        return embed


class ModRemoveView(View):
    """Paginated view for removing installed mods."""

    def __init__(self, mod_ids: list, mod_info: dict, server_name: str, guild_id: int, user_id: int, mods_per_page: int = 5, bot=None):
        super().__init__(timeout=None)
        self.all_mod_ids = mod_ids
        self.mod_info = mod_info
        self.server_name = server_name
        self.guild_id = guild_id
        self.user_id = user_id
        self.mods_per_page = mods_per_page
        self.current_page = 0
        self.total_pages = max(1, (len(self.all_mod_ids) + mods_per_page - 1) // mods_per_page)
        self.bot = bot

        # Navigation buttons (row 0)
        self.first_button = Button(style=discord.ButtonStyle.secondary, label="⏮ First", row=0)
        self.prev_button = Button(style=discord.ButtonStyle.secondary, label="◀ Prev", row=0)
        self.page_label = Button(style=discord.ButtonStyle.secondary, label="1/1", row=0, disabled=True)
        self.next_button = Button(style=discord.ButtonStyle.secondary, label="Next ▶", row=0)
        self.last_button = Button(style=discord.ButtonStyle.secondary, label="Last ⏭", row=0)

        self.first_button.callback = self.first_page
        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page
        self.last_button.callback = self.last_page

        self.add_item(self.first_button)
        self.add_item(self.prev_button)
        self.add_item(self.page_label)
        self.add_item(self.next_button)
        self.add_item(self.last_button)

        self._create_remove_select()
        self.update_buttons()

    @classmethod
    async def create(cls, mod_ids: list, server_name: str, guild_id: int, user_id: int, mods_per_page: int = 5, bot=None):
        """Factory method to create ModRemoveView with mod info fetched."""
        mod_info = await cls._get_mod_names(mod_ids)
        return cls(mod_ids, mod_info, server_name, guild_id, user_id, mods_per_page, bot)

    def update_buttons(self):
        self.first_button.disabled = self.current_page <= 0
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        self.last_button.disabled = self.current_page >= self.total_pages - 1
        self.page_label.label = f"{self.current_page + 1}/{self.total_pages}"

    def _create_remove_select(self):
        """Create the Remove select menu for current page mods."""
        if hasattr(self, 'remove_select') and self.remove_select in self.children:
            self.remove_item(self.remove_select)

        start = self.current_page * self.mods_per_page
        end = min(start + self.mods_per_page, len(self.all_mod_ids))
        page_mod_ids = self.all_mod_ids[start:end]

        if not page_mod_ids:
            return

        options = []
        for mid in page_mod_ids:
            info = self.mod_info.get(mid, {})
            name = info.get("name", f"Mod #{mid}") if isinstance(info, dict) else str(info)
            label = f"Remove: {name}"[:100]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(mid),
                    description=f"Mod ID: {mid}",
                )
            )

        if options:
            self.remove_select = Select(
                placeholder="Select mod to remove...",
                options=options,
                row=1,
            )
            self.remove_select.callback = self._remove_mod_callback
            self.add_item(self.remove_select)

    @staticmethod
    async def _get_mod_names(mod_ids: list) -> dict:
        """Fetch mod names and URLs from cache. Returns {mod_id: {"name": ..., "url": ...}}."""
        from bot.database import curseforge_db

        result = {}
        for mod_id_str in mod_ids:
            try:
                mod_id = int(mod_id_str)
                mod = await curseforge_db.get_mod_by_id(mod_id)
                if mod:
                    result[mod_id_str] = {
                        "name": mod.get("name", "Unknown"),
                        "url": mod.get("website_url") or f"https://www.curseforge.com/ark-survival-ascended/mods/{mod_id}",
                    }
                else:
                    result[mod_id_str] = {
                        "name": f"Mod {mod_id}",
                        "url": f"https://www.curseforge.com/ark-survival-ascended/mods/{mod_id}",
                    }
            except ValueError:
                result[mod_id_str] = {
                    "name": mod_id_str,
                    "url": f"https://www.curseforge.com/ark-survival-ascended/mods/{mod_id_str}",
                }
        return result

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def first_page(self, interaction: discord.Interaction):
        self.current_page = 0
        self.update_buttons()
        self._create_remove_select()
        await self.update_message(interaction)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        self._create_remove_select()
        await self.update_message(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self.update_buttons()
        self._create_remove_select()
        await self.update_message(interaction)

    async def last_page(self, interaction: discord.Interaction):
        self.current_page = self.total_pages - 1
        self.update_buttons()
        self._create_remove_select()
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = await self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def create_embed(self) -> discord.Embed:
        start = self.current_page * self.mods_per_page
        end = min(start + self.mods_per_page, len(self.all_mod_ids))
        page_mod_ids = self.all_mod_ids[start:end]

        embed = discord.Embed(
            title=f"Remove Mods - {self.server_name}",
            description=f"**{len(self.all_mod_ids)}** mods installed",
            color=discord.Color.red(),
        )

        if page_mod_ids:
            lines = []
            for idx, mid in enumerate(page_mod_ids, start + 1):
                info = self.mod_info.get(mid, {})
                if isinstance(info, dict):
                    name = info.get("name", f"Mod #{mid}")
                    url = info.get("url") or f"https://www.curseforge.com/ark-survival-ascended/mods/{mid}"
                else:
                    name = str(info)
                    url = f"https://www.curseforge.com/ark-survival-ascended/mods/{mid}"
                line = f"**{idx}.** [{name}]({url}) (`{mid}`)"
                lines.append(line)

            mod_list = "\n".join(lines)
            embed.add_field(name="Installed Mods", value=mod_list, inline=False)

        embed.set_footer(text=f"Showing {start + 1}-{end} of {len(self.all_mod_ids)} mods")
        return embed

    async def _remove_mod_callback(self, interaction: discord.Interaction):
        """Show confirmation before removing a mod."""
        mod_id_str = self.remove_select.values[0]
        
        _info = self.mod_info.get(mod_id_str, {})
        mod_name = _info.get("name", f"Mod {mod_id_str}") if isinstance(_info, dict) else str(_info)

        embed = discord.Embed(
            title="Confirm Remove Mod",
            description=f"Remove **{mod_name}** (`{mod_id_str}`) from **{self.server_name}**?",
            color=discord.Color.red(),
        )
        embed.add_field(
            name="Warning",
            value="A server restart is required after removing mods.",
            inline=False,
        )

        # Pass parent view and message for refresh
        parent_message = interaction.message
        view = RemoveModConfirmView(mod_id_str, mod_name, self.server_name, self.guild_id, self.bot, parent_view=self, parent_message=parent_message)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ModSearchResultsView(View):
    """Paginated view for mod search results with sorting and Add to Server."""

    SORT_OPTIONS = {
        "name_asc": ("Name (A-Z)", "name", False),
        "name_desc": ("Name (Z-A)", "name", True),
        "downloads_desc": ("Downloads (High-Low)", "download_count", True),
        "downloads_asc": ("Downloads (Low-High)", "download_count", False),
        "date_desc": ("Updated (Newest)", "date_modified", True),
        "date_asc": ("Updated (Oldest)", "date_modified", False),
        "author_asc": ("Author (A-Z)", "author", False),
        "author_desc": ("Author (Z-A)", "author", True),
        "id_asc": ("Mod ID (Low-High)", "mod_id", False),
        "id_desc": ("Mod ID (High-Low)", "mod_id", True),
    }

    def __init__(self, results: list, query: str, user_id: int, guild_id: int = None, selected_server: str = None, mods_per_page: int = 5):
        super().__init__(timeout=None)
        self.all_results = results
        self.query = query
        self.user_id = user_id
        self.guild_id = guild_id
        self.selected_server = selected_server
        self.mods_per_page = mods_per_page
        self.current_page = 0
        self.current_sort = "name_asc"
        self.results = self._sort_results(results, self.current_sort)
        self.total_pages = max(1, (len(self.results) + mods_per_page - 1) // mods_per_page)

        # Navigation buttons (row 0)
        self.first_button = Button(style=discord.ButtonStyle.secondary, label="⏮ First", row=0)
        self.prev_button = Button(style=discord.ButtonStyle.secondary, label="◀ Prev", row=0)
        self.page_label = Button(style=discord.ButtonStyle.secondary, label="1/1", row=0, disabled=True)
        self.next_button = Button(style=discord.ButtonStyle.secondary, label="Next ▶", row=0)
        self.last_button = Button(style=discord.ButtonStyle.secondary, label="Last ⏭", row=0)

        self.first_button.callback = self.first_page
        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page
        self.last_button.callback = self.last_page

        self.add_item(self.first_button)
        self.add_item(self.prev_button)
        self.add_item(self.page_label)
        self.add_item(self.next_button)
        self.add_item(self.last_button)

        # Sort dropdown (row 1)
        self.sort_select = Select(
            placeholder="Sort by...",
            options=[
                discord.SelectOption(label=label, value=key, default=key == self.current_sort)
                for key, (label, _, _) in self.SORT_OPTIONS.items()
            ],
            row=1,
        )
        self.sort_select.callback = self.change_sort
        self.add_item(self.sort_select)

        # Add to Server select (row 2)
        self._create_add_select()

        self.update_buttons()

    def _sort_results(self, results: list, sort_key: str) -> list:
        """Sort results by the specified key."""
        if sort_key not in self.SORT_OPTIONS:
            return results

        _, field, reverse = self.SORT_OPTIONS[sort_key]
        
        def sort_key_func(item):
            val = item.get(field, "")
            if field == "download_count":
                return val or 0
            elif field == "mod_id":
                return val or 0
            elif field == "date_modified":
                return val or ""
            else:
                return (val or "").lower()

        return sorted(results, key=sort_key_func, reverse=reverse)

    def update_buttons(self):
        self.first_button.disabled = self.current_page <= 0
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        self.last_button.disabled = self.current_page >= self.total_pages - 1
        self.page_label.label = f"{self.current_page + 1}/{self.total_pages}"

    def _create_add_select(self):
        """Create the Add to Server select menu for current page mods."""
        # Remove old add select if it exists
        if hasattr(self, 'add_select') and self.add_select in self.children:
            self.remove_item(self.add_select)

        start = self.current_page * self.mods_per_page
        end = min(start + self.mods_per_page, len(self.results))
        page_results = self.results[start:end]

        if not page_results:
            return

        options = []
        for mod in page_results[:25]:
            name = (mod.get("name") or "Unknown")[:50]
            mod_id = mod.get("mod_id", 0)
            options.append(
                discord.SelectOption(
                    label=f"Add: {name}",
                    value=str(mod_id),
                    description=f"Mod ID: {mod_id}",
                )
            )

        if options:
            self.add_select = Select(
                placeholder="Add a mod to server...",
                options=options,
                row=2,
            )
            self.add_select.callback = self._add_mod_callback
            self.add_item(self.add_select)

    async def _add_mod_callback(self, interaction: discord.Interaction):
        """Handle adding a mod from search results."""
        mod_id_str = self.add_select.values[0]
        mod_id = int(mod_id_str)

        if not self.guild_id:
            await interaction.response.send_message(
                "Server context not available. Use /modmgmt to manage mods.",
                ephemeral=True,
            )
            return

        from bot.database import server_config_db
        from bot.cogs.remote_agent import RemoteAgentManager

        servers = await server_config_db.get_ark_servers(self.guild_id)
        if not servers:
            await interaction.response.send_message(
                "No servers configured for this guild.",
                ephemeral=True,
            )
            return

        if self.selected_server:
            await self._add_mod_to_server(interaction, mod_id, self.selected_server)
        elif len(servers) == 1:
            await self._add_mod_to_server(interaction, mod_id, servers[0].get("name"))
        else:
            await self._show_server_selector(interaction, mod_id, servers)

    async def _show_server_selector(self, interaction: discord.Interaction, mod_id: int, servers: list):
        """Show server selector for adding mod."""
        view = AddModServerSelectView(mod_id, servers, self.user_id)
        await interaction.response.send_message(
            f"Select server to add mod `{mod_id}`:",
            view=view,
            ephemeral=True,
        )

    async def _add_mod_to_server(self, interaction: discord.Interaction, mod_id: int, server_name: str):
        """Add mod to a specific server."""
        from bot.cogs.remote_agent import RemoteAgentManager

        agent_manager: RemoteAgentManager = getattr(
            interaction.client, "agent_manager", None
        )
        if not agent_manager:
            await interaction.response.send_message(
                "Agent manager not available.",
                ephemeral=True,
            )
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            await interaction.response.send_message(
                "No remote agent connected.",
                ephemeral=True,
            )
            return

        try:
            result = await agent_manager.get_mods(agent_id, server_name)
            if result.get("type") != "complete":
                await interaction.response.send_message(
                    f"Failed to get current mods: {result.get('error')}",
                    ephemeral=True,
                )
                return

            current_mods = result.get("data", {}).get("mod_ids", [])

            mod_id_str = str(mod_id)
            if mod_id_str in [str(m) for m in current_mods]:
                await interaction.response.send_message(
                    f"Mod `{mod_id}` is already installed on **{server_name}**.",
                    ephemeral=True,
                )
                return

            new_mods = current_mods + [mod_id_str]
            set_result = await agent_manager.set_mods(agent_id, server_name, new_mods)

            if set_result.get("type") == "complete":
                await _log_to_channel(
                    interaction.client, self.guild_id,
                    f"[Mod Management] Added mod `{mod_id}` to **{server_name}**"
                )
                await interaction.response.send_message(
                    f"✅ Added mod `{mod_id}` to **{server_name}**.\n"
                    "Restart the server for changes to take effect.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"Failed to add mod: {set_result.get('error')}",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Error adding mod: {e}")
            await interaction.response.send_message(
                f"Error: {str(e)}",
                ephemeral=True,
            )
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This search is not for you!", ephemeral=True)
            return False
        return True

    async def first_page(self, interaction: discord.Interaction):
        self.current_page = 0
        self.update_buttons()
        self._create_add_select()
        await self.update_message(interaction)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        self._create_add_select()
        await self.update_message(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self.update_buttons()
        self._create_add_select()
        await self.update_message(interaction)

    async def last_page(self, interaction: discord.Interaction):
        self.current_page = self.total_pages - 1
        self.update_buttons()
        self._create_add_select()
        await self.update_message(interaction)

    async def change_sort(self, interaction: discord.Interaction):
        self.current_sort = self.sort_select.values[0]
        self.results = self._sort_results(self.all_results, self.current_sort)
        self.current_page = 0
        self.total_pages = max(1, (len(self.results) + self.mods_per_page - 1) // self.mods_per_page)
        
        # Rebuild sort dropdown with new default
        self.remove_item(self.sort_select)
        self.sort_select = Select(
            placeholder="Sort by...",
            options=[
                discord.SelectOption(label=label, value=key, default=key == self.current_sort)
                for key, (label, _, _) in self.SORT_OPTIONS.items()
            ],
            row=1,
        )
        self.sort_select.callback = self.change_sort
        self.add_item(self.sort_select)
        
        self.update_buttons()
        self._create_add_select()
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def create_embed(self) -> discord.Embed:
        start = self.current_page * self.mods_per_page
        end = min(start + self.mods_per_page, len(self.results))
        page_results = self.results[start:end]

        sort_label = self.SORT_OPTIONS.get(self.current_sort, ("Unknown", "", False))[0]

        embed = discord.Embed(
            title=f"Mod Search: {self.query}",
            description=f"Found {len(self.results)} mods • Sorted by: {sort_label}",
            color=discord.Color.blue(),
        )

        for mod in page_results:
            name = mod.get("name", "Unknown")
            mod_id = mod.get("mod_id", 0)
            author = mod.get("author", "Unknown")
            downloads = mod.get("download_count", 0)
            website_url = mod.get("website_url")
            summary = mod.get("summary", "")
            date_modified = mod.get("date_modified", "")

            if website_url:
                link = f"[View on CurseForge]({website_url})"
            else:
                link = f"[View on CurseForge](https://www.curseforge.com/ark-survival-ascended/mods/{mod_id})"

            if summary and len(summary) > 250:
                summary = summary[:247] + "..."

            updated_str = ""
            if date_modified:
                try:
                    updated_str = date_modified[:10]
                except:
                    pass

            value = f"ID: `{mod_id}` | {link}\n"
            if summary:
                value += f"*{summary}*\n"
            value += f"Author: {author} | Downloads: {downloads:,}"
            if updated_str:
                value += f" | Updated: {updated_str}"

            embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text=f"Showing {start + 1}-{end} of {len(self.results)} mods")
        return embed


class ModManagementView(View):
    """Base mod management view."""

    def __init__(self, guild_id: int, user: discord.User, timeout: int = 300):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.servers = []
        self.selected_server = None
        self.current_mods = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "This mod management panel is not for you!", ephemeral=True
            )
            return False
        return True

    async def load_servers(self):
        self.servers = await server_config_db.get_ark_servers(self.guild_id)

    async def load_mods(self, server_name: str):
        from bot.cogs.remote_agent import RemoteAgentManager

        if not hasattr(self, "bot"):
            return

        agent_manager: RemoteAgentManager = getattr(self.bot, "agent_manager", None)
        if not agent_manager:
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            return

        try:
            result = await agent_manager.get_mods(agent_id, server_name)
            if result.get("type") == "complete":
                self.current_mods = result.get("data", {}).get("mod_ids", [])
        except Exception as e:
            logger.error(f"Failed to load mods: {e}")
            self.current_mods = []


class ModMainView(ModManagementView):
    """Main mod management view with action buttons."""

    def __init__(self, guild_id: int, user: discord.User, bot: commands.Bot):
        super().__init__(guild_id, user)
        self.bot = bot

        self.add_item(ModActionButton("View Mods", "view"))
        self.add_item(ModActionButton("Add Mod", "add"))
        self.add_item(ModActionButton("Remove Mod", "remove"))

    async def load_data(self):
        await self.load_servers()
        if len(self.servers) >= 2:
            self.add_item(BatchAddButton(self.servers, self.guild_id, self.bot))
            self.add_item(BatchRemoveButton(self.servers, self.guild_id, self.bot))

    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Mod Management",
            description=(
                "Manage ARK: Survival Ascended mods for your servers.\n\n"
                f"**Servers:** {len(self.servers)}\n"
                f"**Mod Cache:** Check `/modmgmt stats` for cache info"
            ),
            color=discord.Color.green(),
        )

        if self.selected_server:
            embed.add_field(
                name="Selected Server",
                value=f"**{self.selected_server}**\nMods: {len(self.current_mods)}",
                inline=False,
            )

        embed.set_footer(text="Use buttons to manage mods")
        return embed


class ModSearchInputModal(Modal):
    """Modal for entering search query from mod browser."""

    def __init__(self, server_name: str, guild_id: int, user_id: int, servers: list):
        super().__init__(title="Search Mods")
        self.server_name = server_name
        self.guild_id = guild_id
        self.user_id = user_id
        self.servers = servers

        self.query_input = TextInput(
            label="Search query",
            placeholder="Enter mod name, author, or keyword...",
            required=True,
            max_length=100,
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction):
        query = self.query_input.value.strip()
        
        from bot.database import curseforge_db

        cache_count = await curseforge_db.get_mod_count()

        if cache_count == 0:
            embed = discord.Embed(
                title="Mod Cache Empty",
                description="The mod cache has not been populated yet.",
                color=discord.Color.orange(),
            )
            embed.add_field(
                name="How to find mod IDs",
                value=(
                    "1. Visit [CurseForge](https://www.curseforge.com/ark-survival-ascended/mods)\n"
                    "2. Find the mod you want\n"
                    "3. Copy the mod ID from the URL\n"
                    "4. Use `/modmgmt` to add the mod by ID"
                ),
                inline=False,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        results = await curseforge_db.search_mods(query, limit=100)

        if not results:
            embed = discord.Embed(
                title="No Results",
                description=f"No mods found matching '{query}'.",
                color=discord.Color.orange(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        view = ModSearchResultsView(
            results, query, self.user_id, self.guild_id, self.server_name
        )
        embed = view.create_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ModActionButton(Button):
    """Button for mod actions."""

    def __init__(self, label: str, action: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=label,
            custom_id=f"mod_{action}",
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        view: ModMainView = self.view

        if self.action == "view":
            await self._show_mods(interaction, view)
        elif self.action == "add":
            await self._show_add_modal(interaction, view)
        elif self.action == "remove":
            await self._show_remove_menu(interaction, view)

    async def _show_mods(self, interaction: discord.Interaction, view: ModMainView):
        if not view.servers:
            await interaction.response.send_message(
                "No servers configured. Use `/setup` to add servers first.",
                ephemeral=True,
            )
            return

        server_select = ServerSelectMenu(view.servers, "view_mods")
        select_view = View(timeout=120)
        select_view.add_item(server_select)
        await interaction.response.send_message(
            "Select a server to view mods:", view=select_view, ephemeral=True
        )

    async def _show_add_modal(self, interaction: discord.Interaction, view: ModMainView):
        """Open Add Mod modal for direct mod ID entry."""
        if not view.servers:
            await interaction.response.send_message(
                "No servers configured. Use `/setup` to add servers first.",
                ephemeral=True,
            )
            return

        if len(view.servers) == 1:
            # Single server - open AddModModal directly for mod ID entry
            server_name = view.servers[0].get("name")
            modal = AddModModal(server_name)
            await interaction.response.send_modal(modal)
        else:
            # Multiple servers - show server selector first, then AddModModal
            server_select = ServerSelectMenu(view.servers, "add_mod")
            select_view = View(timeout=120)
            select_view.add_item(server_select)
            await interaction.response.send_message(
                "Select a server to add mods to:", view=select_view, ephemeral=True
            )

    async def _open_search_with_server(self, interaction: discord.Interaction, view: ModMainView, server_name: str):
        """Open search interface with server pre-selected."""
        from bot.database import curseforge_db

        # Pre-fetch servers for the search view
        servers = await server_config_db.get_ark_servers(view.guild_id)

        # Create search input modal
        modal = ModSearchInputModal(server_name, view.guild_id, view.user.id, servers)
        await interaction.response.send_modal(modal)

    async def _show_remove_menu(self, interaction: discord.Interaction, view: ModMainView):
        if not view.servers:
            await interaction.response.send_message(
                "No servers configured. Use `/setup` to add servers first.",
                ephemeral=True,
            )
            return

        server_select = ServerSelectMenu(view.servers, "remove_mod")
        select_view = View(timeout=120)
        select_view.add_item(server_select)
        await interaction.response.send_message(
            "Select a server to remove mods:", view=select_view, ephemeral=True
        )


class ServerSelectMenu(Select):
    """Dropdown for selecting a server."""

    def __init__(self, servers: List[dict], action: str):
        options = [
            discord.SelectOption(
                label=srv.get("name", "Unknown"),
                value=srv.get("name"),
                description=f"Server at {srv.get('host', 'unknown')}",
            )
            for srv in servers[:25]
        ]

        super().__init__(
            placeholder="Select a server...",
            options=options,
            custom_id=f"server_select_{action}",
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        server_name = self.values[0]

        if self.action == "view_mods":
            await self._view_mods(interaction, server_name)
        elif self.action == "add_mod":
            await self._show_add_modal(interaction, server_name)
        elif self.action == "remove_mod":
            await self._show_remove_menu(interaction, server_name)

    async def _view_mods(self, interaction: discord.Interaction, server_name: str):
        from bot.cogs.remote_agent import RemoteAgentManager

        bot = interaction.client
        agent_manager: RemoteAgentManager = getattr(bot, "agent_manager", None)

        if not agent_manager:
            await interaction.response.edit_message(
                content="Agent manager not available.", view=None
            )
            return

        guild_id = interaction.guild_id
        agent_id = await agent_manager.get_connected_agent_for_guild(guild_id)

        if not agent_id:
            await interaction.response.edit_message(
                content="No remote agent connected for this guild.", view=None
            )
            return

        await interaction.response.edit_message(
            content=f"Fetching mods for **{server_name}**...", view=None
        )

        try:
            result = await agent_manager.get_mods(agent_id, server_name)

            if result.get("type") == "complete":
                data = result.get("data", {})
                mod_ids = data.get("mod_ids", [])

                if not mod_ids:
                    embed = discord.Embed(
                        title=f"Mods for {server_name}",
                        description="No mods installed",
                        color=discord.Color.blue(),
                    )
                    await interaction.edit_original_response(content=None, embed=embed)
                    return

                view = await ModListView.create(
                    mod_ids=mod_ids,
                    server_name=server_name,
                    user_id=interaction.user.id,
                    guild_id=guild_id,
                    bot=bot,
                )
                embed = view.create_embed()
                await interaction.edit_original_response(content=None, embed=embed, view=view)
            else:
                await interaction.edit_original_response(
                    content=f"Failed to get mods: {result.get('error', 'Unknown error')}"
                )

        except Exception as e:
            logger.error(f"Error viewing mods: {e}")
            await interaction.edit_original_response(content=f"Error: {str(e)}")

    async def _get_mod_names(self, mod_ids: List[str]) -> dict:
        result = {}
        for mod_id_str in mod_ids:
            try:
                mod_id = int(mod_id_str)
                mod = await curseforge_db.get_mod_by_id(mod_id)
                if mod:
                    result[mod_id_str] = mod.get("name", "Unknown")
                else:
                    result[mod_id_str] = f"Mod {mod_id}"
            except ValueError:
                result[mod_id_str] = mod_id_str
        return result

    async def _show_add_modal(self, interaction: discord.Interaction, server_name: str):
        modal = AddModModal(server_name)
        await interaction.response.send_modal(modal)

    async def _show_remove_menu(self, interaction: discord.Interaction, server_name: str):
        from bot.cogs.remote_agent import RemoteAgentManager

        bot = interaction.client
        agent_manager: RemoteAgentManager = getattr(bot, "agent_manager", None)

        if not agent_manager:
            await interaction.response.edit_message(
                content="Agent manager not available.", view=None
            )
            return

        guild_id = interaction.guild_id
        agent_id = await agent_manager.get_connected_agent_for_guild(guild_id)

        if not agent_id:
            await interaction.response.edit_message(
                content="No remote agent connected.", view=None
            )
            return

        try:
            result = await agent_manager.get_mods(agent_id, server_name)
            mod_ids = result.get("data", {}).get("mod_ids", [])

            if not mod_ids:
                await interaction.response.edit_message(
                    content=f"No mods installed on **{server_name}**.", view=None
                )
                return

            view = await ModRemoveView.create(
                mod_ids=mod_ids,
                server_name=server_name,
                guild_id=guild_id,
                user_id=interaction.user.id,
                bot=interaction.client,
            )
            embed = await view.create_embed()
            await interaction.response.edit_message(
                content=None, embed=embed, view=view
            )

        except Exception as e:
            logger.error(f"Error loading mods for removal: {e}")
            await interaction.response.edit_message(content=f"Error: {str(e)}", view=None)

class AddModModal(Modal):
    """Modal for adding a mod to a server."""

    def __init__(self, server_name: str):
        super().__init__(title=f"Add Mod to {server_name}")
        self.server_name = server_name

        self.mod_id_input = TextInput(
            label="Mod ID",
            placeholder="Enter CurseForge mod ID (e.g., 123456)",
            required=True,
            max_length=20,
        )
        self.add_item(self.mod_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        mod_id = self.mod_id_input.value.strip()

        if not mod_id.isdigit():
            await interaction.response.send_message(
                "Invalid mod ID. Must be a number.", ephemeral=True
            )
            return

        from bot.cogs.remote_agent import RemoteAgentManager
        from bot.database import curseforge_db

        bot = interaction.client
        agent_manager: RemoteAgentManager = getattr(bot, "agent_manager", None)

        if not agent_manager:
            await interaction.response.send_message(
                "Agent manager not available.", ephemeral=True
            )
            return

        guild_id = interaction.guild_id
        agent_id = await agent_manager.get_connected_agent_for_guild(guild_id)

        if not agent_id:
            await interaction.response.send_message(
                "No remote agent connected.", ephemeral=True
            )
            return

        # Get mod name for confirmation
        mod_info = await curseforge_db.get_mod_by_id(int(mod_id))
        mod_name = mod_info.get("name", f"Mod {mod_id}") if mod_info else f"Mod {mod_id}"

        # Show confirmation embed
        embed = discord.Embed(
            title="Confirm Add Mod",
            description=f"Add **{mod_name}** (`{mod_id}`) to **{self.server_name}**?",
            color=discord.Color.yellow(),
        )
        embed.add_field(
            name="Note",
            value="A server restart is required after adding mods.",
            inline=False,
        )

        view = AddModConfirmView(mod_id, mod_name, self.server_name, guild_id, interaction.client)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class BatchAddButton(Button):
    """Button to start batch-add flow (shown when 2+ servers configured)."""

    def __init__(self, servers: list, guild_id: int, bot):
        super().__init__(style=discord.ButtonStyle.success, label="🌐 Batch Add", row=1)
        self.servers = servers
        self.guild_id = guild_id
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        view = BatchServerSelectView(
            self.servers, self.guild_id, interaction.user.id, mode="add", bot=self.bot
        )
        embed = discord.Embed(
            title="Batch Add Mod — Select Servers",
            description="Choose servers to add a mod to, then click **Continue →**.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class BatchRemoveButton(Button):
    """Button to start batch-remove flow (shown when 2+ servers configured)."""

    def __init__(self, servers: list, guild_id: int, bot):
        super().__init__(style=discord.ButtonStyle.danger, label="🗑️ Batch Remove", row=1)
        self.servers = servers
        self.guild_id = guild_id
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        view = BatchServerSelectView(
            self.servers, self.guild_id, interaction.user.id, mode="remove", bot=self.bot
        )
        embed = discord.Embed(
            title="Batch Remove Mod — Select Servers",
            description=(
                "Choose servers to remove a mod from, then click **Continue →**.\n"
                "Only mods shared by **all selected servers** will be shown."
            ),
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class BatchServerSelectView(View):
    """Multi-select server picker reused by both batch add and batch remove flows."""

    def __init__(self, servers: list, guild_id: int, user_id: int, mode: str, bot):
        super().__init__(timeout=180)
        self.servers = servers
        self.guild_id = guild_id
        self.user_id = user_id
        self.mode = mode  # "add" or "remove"
        self.bot = bot
        self.selected: List[str] = []

        options = [
            discord.SelectOption(label=srv.get("name", "Unknown"), value=srv.get("name"))
            for srv in servers[:25]
        ]
        self.server_select = Select(
            placeholder="Select servers...",
            options=options,
            min_values=1,
            max_values=min(25, len(servers)),
            row=0,
        )
        self.server_select.callback = self._on_select
        self.add_item(self.server_select)

        self.all_btn = Button(label="✅ All Servers", style=discord.ButtonStyle.success, row=1)
        self.all_btn.callback = self._on_all
        self.add_item(self.all_btn)

        self.continue_btn = Button(
            label="Continue →", style=discord.ButtonStyle.primary, row=1, disabled=True
        )
        self.continue_btn.callback = self._on_continue
        self.add_item(self.continue_btn)

        self.cancel_btn = Button(label="❌ Cancel", style=discord.ButtonStyle.secondary, row=1)
        self.cancel_btn.callback = self._on_cancel
        self.add_item(self.cancel_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def _on_select(self, interaction: discord.Interaction):
        self.selected = list(self.server_select.values)
        self.continue_btn.disabled = False
        await interaction.response.edit_message(view=self)

    async def _on_all(self, interaction: discord.Interaction):
        self.selected = [srv.get("name") for srv in self.servers]
        self.continue_btn.disabled = False
        await interaction.response.edit_message(
            content=f"✅ All **{len(self.selected)}** servers selected.", view=self
        )

    async def _on_cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Cancelled.", embed=None, view=None)

    async def _on_continue(self, interaction: discord.Interaction):
        if not self.selected:
            await interaction.response.send_message("No servers selected.", ephemeral=True)
            return

        if self.mode == "add":
            modal = BatchModAddModal(self.selected, self.guild_id, self.bot)
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.defer()
            from bot.cogs.remote_agent import RemoteAgentManager

            agent_manager: RemoteAgentManager = getattr(self.bot, "agent_manager", None)
            if not agent_manager:
                await interaction.edit_original_response(
                    content="Agent manager not available.", embed=None, view=None
                )
                return

            agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)
            if not agent_id:
                await interaction.edit_original_response(
                    content="No remote agent connected.", embed=None, view=None
                )
                return

            server_mod_sets: Dict[str, set] = {}
            for server_name in self.selected:
                try:
                    result = await agent_manager.get_mods(agent_id, server_name)
                    if result.get("type") == "complete":
                        server_mod_sets[server_name] = set(
                            str(m) for m in result["data"].get("mod_ids", [])
                        )
                except Exception as e:
                    logger.warning(f"Failed to get mods for {server_name}: {e}")

            if not server_mod_sets:
                await interaction.edit_original_response(
                    content="Could not retrieve mods from any selected server.",
                    embed=None,
                    view=None,
                )
                return

            intersection = set.intersection(*server_mod_sets.values())
            if not intersection:
                await interaction.edit_original_response(
                    content=f"⚠️ No mods are common to all **{len(self.selected)}** selected servers.",
                    embed=None,
                    view=None,
                )
                return

            mod_ids = sorted(intersection)
            mod_info = await ModRemoveView._get_mod_names(mod_ids)
            view = BatchModRemoveView(
                mod_ids, mod_info, self.selected, self.guild_id, interaction.user.id, bot=self.bot
            )
            embed = await view.create_embed()
            await interaction.edit_original_response(content=None, embed=embed, view=view)


class BatchModAddModal(Modal):
    """Modal for entering a mod ID to add to multiple servers."""

    def __init__(self, server_names: List[str], guild_id: int, bot):
        super().__init__(title="Batch Add Mod")
        self.server_names = server_names
        self.guild_id = guild_id
        self.bot = bot

        self.mod_id_input = TextInput(
            label="Mod ID",
            placeholder="Enter CurseForge mod ID (e.g., 123456)",
            required=True,
            max_length=20,
        )
        self.add_item(self.mod_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        mod_id = self.mod_id_input.value.strip()
        if not mod_id.isdigit():
            await interaction.response.send_message(
                "Invalid mod ID. Must be a number.", ephemeral=True
            )
            return

        mod_info = await curseforge_db.get_mod_by_id(int(mod_id))
        mod_name = mod_info.get("name", f"Mod {mod_id}") if mod_info else f"Mod {mod_id}"

        server_list = ", ".join(self.server_names)
        if len(server_list) > 900:
            server_list = server_list[:897] + "..."

        embed = discord.Embed(
            title="Confirm Batch Add Mod",
            description=(
                f"Add **{mod_name}** (`{mod_id}`) to **{len(self.server_names)}** servers?\n\n"
                f"**Servers:** {server_list}"
            ),
            color=discord.Color.yellow(),
        )
        embed.add_field(
            name="Note", value="A server restart is required after adding mods.", inline=False
        )
        view = BatchModAddConfirmView(mod_id, mod_name, self.server_names, self.guild_id, self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class BatchModAddConfirmView(View):
    """Confirmation view for batch-adding a mod to multiple servers."""

    def __init__(
        self, mod_id: str, mod_name: str, server_names: List[str], guild_id: int, bot
    ):
        super().__init__(timeout=120)
        self.mod_id = mod_id
        self.mod_name = mod_name
        self.server_names = server_names
        self.guild_id = guild_id
        self.bot = bot

    @discord.ui.button(label="✅ Confirm Add", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        from bot.cogs.remote_agent import RemoteAgentManager

        agent_manager: RemoteAgentManager = getattr(self.bot, "agent_manager", None)
        if not agent_manager:
            await interaction.edit_original_response(
                content="Agent manager not available.", embed=None, view=None
            )
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            await interaction.edit_original_response(
                content="No remote agent connected.", embed=None, view=None
            )
            return

        results: List[str] = []
        added_count = 0
        for server_name in self.server_names:
            try:
                result = await agent_manager.get_mods(agent_id, server_name)
                if result.get("type") != "complete":
                    results.append(f"❌ **{server_name}**: Failed to get mods")
                    continue
                current_mods = result.get("data", {}).get("mod_ids", [])
                if self.mod_id in [str(m) for m in current_mods]:
                    results.append(f"⚠️ **{server_name}**: Already present")
                    continue
                new_mods = current_mods + [self.mod_id]
                set_result = await agent_manager.set_mods(agent_id, server_name, new_mods)
                if set_result.get("type") == "complete":
                    results.append(f"✅ **{server_name}**: Added")
                    added_count += 1
                else:
                    results.append(f"❌ **{server_name}**: {set_result.get('error', 'Error')}")
            except Exception as e:
                results.append(f"❌ **{server_name}**: {str(e)}")

        if added_count > 0:
            await _log_to_channel(
                interaction.client,
                self.guild_id,
                f"[Batch Mod] Added **{self.mod_name}** (`{self.mod_id}`) to "
                f"{added_count} server(s): " + ", ".join(self.server_names),
            )

        embed = discord.Embed(
            title=f"Batch Add: {self.mod_name}",
            description="\n".join(results),
            color=discord.Color.green() if added_count > 0 else discord.Color.orange(),
        )
        embed.add_field(
            name="Restart Required",
            value="Restart affected servers for changes to take effect.",
            inline=False,
        )
        await interaction.edit_original_response(embed=embed, view=None)

        if added_count > 0 and self.bot:
            mod_cog = self.bot.get_cog("ModManagement")
            if mod_cog:
                asyncio.create_task(mod_cog._refresh_and_send_mod_embeds())

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="❌ Cancelled. No changes made.", embed=None, view=None
        )


class BatchModRemoveView(View):
    """Paginated view of intersection mods for batch removal."""

    def __init__(
        self,
        mod_ids: List[str],
        mod_info: dict,
        server_names: List[str],
        guild_id: int,
        user_id: int,
        mods_per_page: int = 5,
        bot=None,
    ):
        super().__init__(timeout=180)
        self.all_mod_ids = mod_ids
        self.mod_info = mod_info
        self.server_names = server_names
        self.guild_id = guild_id
        self.user_id = user_id
        self.mods_per_page = mods_per_page
        self.bot = bot
        self.current_page = 0
        self.total_pages = max(1, (len(self.all_mod_ids) + mods_per_page - 1) // mods_per_page)

        self.first_button = Button(style=discord.ButtonStyle.secondary, label="⏮ First", row=0)
        self.prev_button = Button(style=discord.ButtonStyle.secondary, label="◀ Prev", row=0)
        self.page_label = Button(
            style=discord.ButtonStyle.secondary, label="1/1", row=0, disabled=True
        )
        self.next_button = Button(style=discord.ButtonStyle.secondary, label="Next ▶", row=0)
        self.last_button = Button(style=discord.ButtonStyle.secondary, label="Last ⏭", row=0)

        self.first_button.callback = self.first_page
        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page
        self.last_button.callback = self.last_page

        self.add_item(self.first_button)
        self.add_item(self.prev_button)
        self.add_item(self.page_label)
        self.add_item(self.next_button)
        self.add_item(self.last_button)

        self._create_remove_select()
        self.update_buttons()

    def update_buttons(self):
        self.first_button.disabled = self.current_page <= 0
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1
        self.last_button.disabled = self.current_page >= self.total_pages - 1
        self.page_label.label = f"{self.current_page + 1}/{self.total_pages}"

    def _create_remove_select(self):
        if hasattr(self, "remove_select") and self.remove_select in self.children:
            self.remove_item(self.remove_select)

        start = self.current_page * self.mods_per_page
        end = min(start + self.mods_per_page, len(self.all_mod_ids))
        page_mod_ids = self.all_mod_ids[start:end]
        if not page_mod_ids:
            return

        options = []
        for mid in page_mod_ids:
            info = self.mod_info.get(mid, {})
            name = info.get("name", f"Mod #{mid}") if isinstance(info, dict) else str(info)
            options.append(
                discord.SelectOption(
                    label=f"Remove: {name}"[:100],
                    value=str(mid),
                    description=f"Mod ID: {mid}",
                )
            )

        if options:
            self.remove_select = Select(
                placeholder="Select mod to remove from all selected servers...",
                options=options,
                row=1,
            )
            self.remove_select.callback = self._remove_mod_callback
            self.add_item(self.remove_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def first_page(self, interaction: discord.Interaction):
        self.current_page = 0
        self.update_buttons()
        self._create_remove_select()
        await self.update_message(interaction)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        self._create_remove_select()
        await self.update_message(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self.update_buttons()
        self._create_remove_select()
        await self.update_message(interaction)

    async def last_page(self, interaction: discord.Interaction):
        self.current_page = self.total_pages - 1
        self.update_buttons()
        self._create_remove_select()
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        embed = await self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def create_embed(self) -> discord.Embed:
        start = self.current_page * self.mods_per_page
        end = min(start + self.mods_per_page, len(self.all_mod_ids))
        page_mod_ids = self.all_mod_ids[start:end]

        server_list = ", ".join(self.server_names)
        if len(server_list) > 200:
            server_list = server_list[:197] + "..."

        embed = discord.Embed(
            title="Batch Remove Mod",
            description=(
                f"**{len(self.all_mod_ids)}** mods shared by all selected servers\n"
                f"**Servers:** {server_list}"
            ),
            color=discord.Color.red(),
        )
        if page_mod_ids:
            lines = []
            for idx, mid in enumerate(page_mod_ids, start + 1):
                info = self.mod_info.get(mid, {})
                if isinstance(info, dict):
                    name = info.get("name", f"Mod #{mid}")
                    url = (
                        info.get("url")
                        or f"https://www.curseforge.com/ark-survival-ascended/mods/{mid}"
                    )
                else:
                    name = str(info)
                    url = f"https://www.curseforge.com/ark-survival-ascended/mods/{mid}"
                lines.append(f"**{idx}.** [{name}]({url}) (`{mid}`)")
            embed.add_field(name="Shared Mods", value="\n".join(lines), inline=False)
        embed.set_footer(
            text=f"Showing {start + 1}-{end} of {len(self.all_mod_ids)} shared mods"
        )
        return embed

    async def _remove_mod_callback(self, interaction: discord.Interaction):
        mod_id_str = self.remove_select.values[0]
        info = self.mod_info.get(mod_id_str, {})
        mod_name = (
            info.get("name", f"Mod {mod_id_str}") if isinstance(info, dict) else str(info)
        )

        server_list = ", ".join(self.server_names)
        if len(server_list) > 900:
            server_list = server_list[:897] + "..."

        embed = discord.Embed(
            title="Confirm Batch Remove Mod",
            description=(
                f"Remove **{mod_name}** (`{mod_id_str}`) from **{len(self.server_names)}** servers?\n\n"
                f"**Servers:** {server_list}"
            ),
            color=discord.Color.red(),
        )
        embed.add_field(
            name="Warning",
            value="A server restart is required after removing mods.",
            inline=False,
        )
        view = BatchModRemoveConfirmView(
            mod_id_str, mod_name, self.server_names, self.guild_id, self.bot
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class BatchModRemoveConfirmView(View):
    """Confirmation view for batch-removing a mod from multiple servers."""

    def __init__(
        self, mod_id: str, mod_name: str, server_names: List[str], guild_id: int, bot
    ):
        super().__init__(timeout=120)
        self.mod_id = mod_id
        self.mod_name = mod_name
        self.server_names = server_names
        self.guild_id = guild_id
        self.bot = bot

    @discord.ui.button(label="✅ Confirm Remove", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        from bot.cogs.remote_agent import RemoteAgentManager

        agent_manager: RemoteAgentManager = getattr(self.bot, "agent_manager", None)
        if not agent_manager:
            await interaction.edit_original_response(
                content="Agent manager not available.", embed=None, view=None
            )
            return

        agent_id = await agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            await interaction.edit_original_response(
                content="No remote agent connected.", embed=None, view=None
            )
            return

        results: List[str] = []
        removed_count = 0
        for server_name in self.server_names:
            try:
                result = await agent_manager.get_mods(agent_id, server_name)
                if result.get("type") != "complete":
                    results.append(f"❌ **{server_name}**: Failed to get mods")
                    continue
                current_mods = result.get("data", {}).get("mod_ids", [])
                if self.mod_id not in [str(m) for m in current_mods]:
                    results.append(f"⚠️ **{server_name}**: Not found (skipped)")
                    continue
                new_mods = [m for m in current_mods if str(m) != self.mod_id]
                set_result = await agent_manager.set_mods(agent_id, server_name, new_mods)
                if set_result.get("type") == "complete":
                    results.append(f"✅ **{server_name}**: Removed")
                    removed_count += 1
                else:
                    results.append(f"❌ **{server_name}**: {set_result.get('error', 'Error')}")
            except Exception as e:
                results.append(f"❌ **{server_name}**: {str(e)}")

        if removed_count > 0:
            await _log_to_channel(
                interaction.client,
                self.guild_id,
                f"[Batch Mod] Removed **{self.mod_name}** (`{self.mod_id}`) from "
                f"{removed_count} server(s): " + ", ".join(self.server_names),
            )

        embed = discord.Embed(
            title=f"Batch Remove: {self.mod_name}",
            description="\n".join(results),
            color=discord.Color.green() if removed_count > 0 else discord.Color.orange(),
        )
        embed.add_field(
            name="Restart Required",
            value="Restart affected servers for changes to take effect.",
            inline=False,
        )
        await interaction.edit_original_response(embed=embed, view=None)

        if removed_count > 0 and self.bot:
            mod_cog = self.bot.get_cog("ModManagement")
            if mod_cog:
                asyncio.create_task(mod_cog._refresh_and_send_mod_embeds())

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="❌ Cancelled. No changes made.", embed=None, view=None
        )


class ModManagement(commands.Cog):
    """Discord commands for mod management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._startup_done = False
        logger.info("ModManagement cog initialized")

    async def cog_load(self):
        """Called when cog is loaded. Start periodic mod refresh."""
        self.refresh_mods_loop.start()

    async def cog_unload(self):
        """Called when cog is unloaded. Stop periodic task."""
        self.refresh_mods_loop.cancel()

    @tasks.loop(minutes=5)
    async def refresh_mods_loop(self):
        """Periodically refresh mod embeds."""
        try:
            await self._refresh_and_send_mod_embeds()
        except Exception as e:
            logger.error(f"Failed to refresh mods in periodic loop: {e}")

    @refresh_mods_loop.before_loop
    async def before_refresh_mods_loop(self):
        """Wait for bot to be ready before starting loop."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(10)  # Wait for agent connections

    async def _delayed_startup(self):
        """Wait for bot to be ready, then refresh mods and send embed."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)  # Wait for agent connections

        if self._startup_done:
            return
        self._startup_done = True

        try:
            await self._refresh_and_send_mod_embeds()
        except Exception as e:
            logger.error(f"Failed to refresh mods on startup: {e}")

    async def _refresh_and_send_mod_embeds(self):
        """Refresh mods from all servers and send embed to configured channels."""
        from bot.database import server_config_db
        from bot.cogs.remote_agent import RemoteAgentManager

        agent_manager: RemoteAgentManager = getattr(self.bot, "agent_manager", None)
        if not agent_manager:
            logger.warning("No agent manager available for mod refresh")
            return

        for guild in self.bot.guilds:
            guild_id = guild.id

            # Get ARK servers for this guild
            servers = await server_config_db.get_ark_servers(guild_id)
            if not servers:
                continue

            agent_id = await agent_manager.get_connected_agent_for_guild(guild_id)
            if not agent_id:
                continue

            all_mods = {}
            for server in servers:
                server_name = server.get("name")
                try:
                    result = await agent_manager.get_mods(agent_id, server_name)
                    if result.get("type") == "complete":
                        mod_ids = result.get("data", {}).get("mod_ids", [])
                        for mod_id in mod_ids:
                            if mod_id not in all_mods:
                                all_mods[mod_id] = {"servers": [], "name": None, "url": None}
                            all_mods[mod_id]["servers"].append(server_name)

                            # Try to get mod info from cache or API
                            mod_info = await curseforge_db.get_mod_by_id(int(mod_id))
                            if not mod_info:
                                mod_info = await fetch_mod_from_curseforge(int(mod_id))
                            if mod_info:
                                all_mods[mod_id]["name"] = mod_info.get("name")
                                all_mods[mod_id]["url"] = mod_info.get("website_url")
                except Exception as e:
                    logger.error(f"Failed to get mods for {server_name}: {e}")

            if not all_mods:
                continue

            # Send embed to configured channel
            channel_id = await server_config_db.get_mod_embed_channel_id(guild_id)
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await self._send_mod_embed(channel, all_mods, guild_id)
                    logger.info(f"Sent mod embed to channel {channel_id} for guild {guild_id}")

    def _get_mod_embed_msg_file(self, guild_id: int) -> Path:
        """Get path to file storing the mod embed message ID."""
        from bot.utils.config import Config
        data_dir = Path(Config.DATABASE_PATH).parent
        return data_dir / f"mod_embed_message_id_{guild_id}.txt"

    async def _send_mod_embed(self, channel, mods: dict, guild_id: int):
        """Send or update mod list embed in a channel."""
        total_mods = len(mods)
        mods_per_embed = 10

        sorted_mods = sorted(
            mods.items(),
            key=lambda x: x[1].get("name") or f"Mod {x[0]}"
        )

        embeds = []
        for i in range(0, len(sorted_mods), mods_per_embed):
            chunk = sorted_mods[i:i + mods_per_embed]
            lines = []
            for idx, (mod_id, info) in enumerate(chunk, i + 1):
                name = info.get("name") or f"Mod #{mod_id}"
                url = info.get("url") or f"https://www.curseforge.com/ark-survival-ascended/mods/{mod_id}"
                line = f"**{idx}.** [{name}]({url})"
                if len(info.get("servers") or []) > 1:
                    line += f" ({len(info['servers'])} servers)"
                lines.append(line)

            is_first = i == 0
            embed = discord.Embed(
                title="Server Mods" if is_first else "Server Mods (continued)",
                description=f"**{total_mods}** mods installed\n\n" + "\n".join(lines) if is_first else "\n".join(lines),
                color=discord.Color.blue(),
            )
            embeds.append(embed)

        # Try to update existing message
        msg_file = self._get_mod_embed_msg_file(guild_id)
        message_updated = False

        if msg_file.exists():
            try:
                old_id = int(msg_file.read_text().strip())
                old_msg = await channel.fetch_message(old_id)
                if old_msg:
                    await old_msg.edit(content="", embeds=embeds)
                    message_updated = True
                    logger.debug(f"Updated existing mod embed message {old_id}")
            except discord.NotFound:
                msg_file.unlink(missing_ok=True)
                logger.debug("Previous mod embed message not found, will create new")
            except Exception as e:
                logger.warning(f"Failed to update existing mod embed: {e}")

        # Send new message if we couldn't update
        if not message_updated:
            new_msg = await channel.send(embeds=embeds)
            msg_file.write_text(str(new_msg.id))
            logger.debug(f"Created new mod embed message {new_msg.id}")

    @app_commands.command(name="modmgmt", description="Open mod management panel")
    @app_commands.checks.has_permissions(administrator=True)
    async def modmgmt(self, interaction: discord.Interaction):
        """Open the mod management interface."""
        if not await check_feature(interaction, "mod_management"):
            return
        view = ModMainView(interaction.guild_id, interaction.user, self.bot)
        await view.load_data()

        embed = view.create_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="setmodchannel", description="Set channel for mod list embeds")
    @app_commands.describe(channel="Channel to send mod list embeds to")
    @app_commands.checks.has_permissions(administrator=True)
    async def setmodchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the channel for mod list embeds."""
        if not await check_feature(interaction, "mod_management"):
            return
        from bot.database import server_config_db

        await server_config_db.set_mod_embed_channel_id(interaction.guild_id, channel.id)

        embed = discord.Embed(
            title="Mod Channel Set",
            description=f"Mod list embeds will be sent to {channel.mention}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="refreshmods", description="Refresh mod list and send to channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def refreshmods(self, interaction: discord.Interaction):
        """Manually refresh mods and send embed."""
        if not await check_feature(interaction, "mod_management"):
            return
        await interaction.response.defer(ephemeral=True)

        try:
            await self._refresh_and_send_mod_embeds()
            await interaction.followup.send("Mod list refreshed and sent to configured channel.", ephemeral=True)
        except Exception as e:
            logger.error(f"Failed to refresh mods: {e}")
            await interaction.followup.send(f"Failed to refresh mods: {str(e)}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModManagement(bot))
