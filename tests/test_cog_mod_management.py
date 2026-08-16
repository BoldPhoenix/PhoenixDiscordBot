"""
Tests for batch mod management classes in mod_management.py.

Covers:
  - BatchServerSelectView  (mode routing)
  - BatchModAddModal       (validation, name lookup)
  - BatchModAddConfirmView (already-present skip, per-server errors, results embed)
  - BatchModRemoveView     (empty intersection, non-empty dropdown)
  - BatchModRemoveConfirmView (not-found skip, per-server errors, results embed)
  - ModMainView            (batch buttons absent <2 servers, present >=2 servers)
"""

import asyncio
import inspect
import pytest
import discord

from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from bot.cogs.mod_management import (
    BatchAddButton,
    BatchRemoveButton,
    BatchServerSelectView,
    BatchModAddModal,
    BatchModAddConfirmView,
    BatchModRemoveView,
    BatchModRemoveConfirmView,
    ModMainView,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_server(name: str) -> dict:
    return {"name": name, "host": "127.0.0.1", "rcon_port": 27020}


def make_interaction(guild_id: int = 1, user_id: int = 99, client=None) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = guild_id
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.edit_original_response = AsyncMock()
    interaction.client = client or MagicMock()
    interaction.message = MagicMock()
    return interaction


def make_agent_manager(mod_ids=None, set_ok=True):
    """Return a mock RemoteAgentManager that returns given mod_ids on get_mods."""
    am = AsyncMock()
    am.get_connected_agent_for_guild = AsyncMock(return_value="agent-1")
    am.get_mods = AsyncMock(
        return_value={"type": "complete", "data": {"mod_ids": mod_ids or []}}
    )
    set_result = {"type": "complete"} if set_ok else {"type": "error", "error": "set failed"}
    am.set_mods = AsyncMock(return_value=set_result)
    return am


def make_bot(agent_manager=None, guild_id=1):
    bot = MagicMock()
    bot.agent_manager = agent_manager or make_agent_manager()
    bot.guilds = []
    bot.get_cog = MagicMock(return_value=None)
    return bot


# ---------------------------------------------------------------------------
# TestModMainViewBatchButtons
# ---------------------------------------------------------------------------

class TestModMainViewBatchButtons:
    """Batch buttons absent with 1 server, present with 2+."""

    def _view_with_servers(self, n: int) -> ModMainView:
        user = MagicMock()
        user.id = 42
        bot = make_bot()
        view = ModMainView(guild_id=1, user=user, bot=bot)
        # Inject servers directly (simulates post-load_data state)
        view.servers = [make_server(f"Server{i}") for i in range(n)]
        return view

    @pytest.mark.asyncio
    async def test_one_server_no_batch_buttons(self):
        user = MagicMock()
        user.id = 42
        bot = make_bot()
        view = ModMainView(guild_id=1, user=user, bot=bot)
        # load_data fetches servers; mock it
        with patch(
            "bot.database.server_config_db.get_ark_servers",
            AsyncMock(return_value=[make_server("OnlyServer")]),
        ):
            await view.load_data()

        labels = [item.label for item in view.children if hasattr(item, "label")]
        assert "🌐 Batch Add" not in labels
        assert "🗑️ Batch Remove" not in labels

    @pytest.mark.asyncio
    async def test_two_servers_batch_buttons_present(self):
        user = MagicMock()
        user.id = 42
        bot = make_bot()
        view = ModMainView(guild_id=1, user=user, bot=bot)
        with patch(
            "bot.database.server_config_db.get_ark_servers",
            AsyncMock(return_value=[make_server("S1"), make_server("S2")]),
        ):
            await view.load_data()

        labels = [item.label for item in view.children if hasattr(item, "label")]
        assert "🌐 Batch Add" in labels
        assert "🗑️ Batch Remove" in labels

    @pytest.mark.asyncio
    async def test_three_servers_batch_buttons_present(self):
        user = MagicMock()
        user.id = 42
        bot = make_bot()
        view = ModMainView(guild_id=1, user=user, bot=bot)
        with patch(
            "bot.database.server_config_db.get_ark_servers",
            AsyncMock(return_value=[make_server(f"S{i}") for i in range(3)]),
        ):
            await view.load_data()

        labels = [item.label for item in view.children if hasattr(item, "label")]
        assert "🌐 Batch Add" in labels
        assert "🗑️ Batch Remove" in labels

    def test_batch_add_button_row(self):
        servers = [make_server("S1"), make_server("S2")]
        btn = BatchAddButton(servers, guild_id=1, bot=MagicMock())
        assert btn.row == 1
        assert btn.style == discord.ButtonStyle.success

    def test_batch_remove_button_row(self):
        servers = [make_server("S1"), make_server("S2")]
        btn = BatchRemoveButton(servers, guild_id=1, bot=MagicMock())
        assert btn.row == 1
        assert btn.style == discord.ButtonStyle.danger


# ---------------------------------------------------------------------------
# TestBatchServerSelectView
# ---------------------------------------------------------------------------

class TestBatchServerSelectView:
    """Routing: add → modal; remove → fetch intersection + view."""

    SERVERS = [make_server("Alpha"), make_server("Beta")]

    def _view(self, mode: str) -> BatchServerSelectView:
        bot = make_bot()
        return BatchServerSelectView(
            servers=self.SERVERS,
            guild_id=1,
            user_id=99,
            mode=mode,
            bot=bot,
        )

    def test_initial_continue_disabled(self):
        view = self._view("add")
        assert view.continue_btn.disabled is True

    def test_dropdown_min_max_values(self):
        view = self._view("add")
        assert view.server_select.min_values == 1
        assert view.server_select.max_values == len(self.SERVERS)

    @pytest.mark.asyncio
    async def test_interaction_check_correct_user(self):
        view = self._view("add")
        interaction = make_interaction(user_id=99)
        result = await view.interaction_check(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_interaction_check_wrong_user(self):
        view = self._view("add")
        interaction = make_interaction(user_id=555)
        result = await view.interaction_check(interaction)
        assert result is False

    @pytest.mark.asyncio
    async def test_on_select_enables_continue(self):
        view = self._view("add")
        interaction = make_interaction(user_id=99)
        # Simulate dropdown values being set
        view.server_select = MagicMock()
        view.server_select.values = ["Alpha"]
        await view._on_select(interaction)
        assert view.selected == ["Alpha"]
        assert view.continue_btn.disabled is False

    @pytest.mark.asyncio
    async def test_on_all_selects_all_servers(self):
        view = self._view("add")
        interaction = make_interaction(user_id=99)
        await view._on_all(interaction)
        assert set(view.selected) == {"Alpha", "Beta"}
        assert view.continue_btn.disabled is False

    @pytest.mark.asyncio
    async def test_cancel_clears_view(self):
        view = self._view("add")
        interaction = make_interaction(user_id=99)
        await view._on_cancel(interaction)
        interaction.response.edit_message.assert_called_once()
        call_kwargs = interaction.response.edit_message.call_args[1]
        assert call_kwargs.get("view") is None

    @pytest.mark.asyncio
    async def test_continue_add_mode_opens_modal(self):
        view = self._view("add")
        view.selected = ["Alpha"]
        view.continue_btn.disabled = False
        interaction = make_interaction(user_id=99)
        await view._on_continue(interaction)
        interaction.response.send_modal.assert_called_once()
        modal = interaction.response.send_modal.call_args[0][0]
        assert isinstance(modal, BatchModAddModal)
        assert modal.server_names == ["Alpha"]

    @pytest.mark.asyncio
    async def test_continue_remove_mode_empty_selection_sends_error(self):
        view = self._view("remove")
        view.selected = []
        interaction = make_interaction(user_id=99)
        await view._on_continue(interaction)
        interaction.response.send_message.assert_called_once()
        assert "No servers" in interaction.response.send_message.call_args[0][0]

    @pytest.mark.asyncio
    async def test_continue_remove_no_agent_manager(self):
        bot = MagicMock()
        bot.agent_manager = None
        view = BatchServerSelectView(self.SERVERS, 1, 99, "remove", bot)
        view.selected = ["Alpha"]
        interaction = make_interaction(user_id=99)
        await view._on_continue(interaction)
        interaction.response.defer.assert_called_once()
        interaction.edit_original_response.assert_called_once()
        assert "Agent manager" in interaction.edit_original_response.call_args[1]["content"]

    @pytest.mark.asyncio
    async def test_continue_remove_no_agent_connected(self):
        am = make_agent_manager()
        am.get_connected_agent_for_guild = AsyncMock(return_value=None)
        bot = make_bot(agent_manager=am)
        view = BatchServerSelectView(self.SERVERS, 1, 99, "remove", bot)
        view.selected = ["Alpha"]
        interaction = make_interaction(user_id=99)
        await view._on_continue(interaction)
        assert "No remote agent" in interaction.edit_original_response.call_args[1]["content"]

    @pytest.mark.asyncio
    async def test_continue_remove_no_intersection(self):
        # Alpha has mod 111, Beta has mod 222 — intersection is empty
        am = AsyncMock()
        am.get_connected_agent_for_guild = AsyncMock(return_value="agent-1")

        async def side_effect(agent_id, server_name):
            if server_name == "Alpha":
                return {"type": "complete", "data": {"mod_ids": ["111"]}}
            return {"type": "complete", "data": {"mod_ids": ["222"]}}

        am.get_mods = side_effect
        bot = make_bot(agent_manager=am)
        view = BatchServerSelectView(self.SERVERS, 1, 99, "remove", bot)
        view.selected = ["Alpha", "Beta"]
        interaction = make_interaction(user_id=99)
        await view._on_continue(interaction)
        content = interaction.edit_original_response.call_args[1]["content"]
        assert "No mods are common" in content

    @pytest.mark.asyncio
    async def test_continue_remove_with_intersection_opens_remove_view(self):
        # Both servers share mod 999
        am = AsyncMock()
        am.get_connected_agent_for_guild = AsyncMock(return_value="agent-1")
        am.get_mods = AsyncMock(
            return_value={"type": "complete", "data": {"mod_ids": ["999"]}}
        )
        bot = make_bot(agent_manager=am)
        view = BatchServerSelectView(self.SERVERS, 1, 99, "remove", bot)
        view.selected = ["Alpha", "Beta"]
        interaction = make_interaction(user_id=99)

        with patch("bot.cogs.mod_management.ModRemoveView._get_mod_names", AsyncMock(return_value={"999": {"name": "TestMod", "url": ""}})):
            await view._on_continue(interaction)

        interaction.edit_original_response.assert_called_once()
        call_kwargs = interaction.edit_original_response.call_args[1]
        assert isinstance(call_kwargs.get("view"), BatchModRemoveView)


# ---------------------------------------------------------------------------
# TestBatchModAddModal
# ---------------------------------------------------------------------------

class TestBatchModAddModal:

    def _modal(self, server_names=None) -> BatchModAddModal:
        return BatchModAddModal(
            server_names=server_names or ["Alpha", "Beta"],
            guild_id=1,
            bot=MagicMock(),
        )

    def test_has_one_text_input(self):
        modal = self._modal()
        assert len(modal.children) == 1

    @pytest.mark.asyncio
    async def test_non_numeric_mod_id_rejected(self):
        modal = self._modal()
        modal.mod_id_input = MagicMock()
        modal.mod_id_input.value = "not-a-number"
        interaction = make_interaction()
        await modal.on_submit(interaction)
        interaction.response.send_message.assert_called_once()
        assert "Invalid mod ID" in interaction.response.send_message.call_args[0][0]

    @pytest.mark.asyncio
    async def test_valid_mod_id_shows_confirm_view(self):
        modal = self._modal(["Alpha", "Beta"])
        modal.mod_id_input = MagicMock()
        modal.mod_id_input.value = "123456"
        interaction = make_interaction()

        with patch(
            "bot.cogs.mod_management.curseforge_db.get_mod_by_id",
            AsyncMock(return_value={"name": "Cool Mod"}),
        ):
            await modal.on_submit(interaction)

        interaction.response.send_message.assert_called_once()
        kwargs = interaction.response.send_message.call_args[1]
        assert isinstance(kwargs.get("view"), BatchModAddConfirmView)
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_unknown_mod_uses_fallback_name(self):
        modal = self._modal(["Alpha"])
        modal.mod_id_input = MagicMock()
        modal.mod_id_input.value = "999"
        interaction = make_interaction()

        with patch(
            "bot.cogs.mod_management.curseforge_db.get_mod_by_id",
            AsyncMock(return_value=None),
        ):
            await modal.on_submit(interaction)

        kwargs = interaction.response.send_message.call_args[1]
        assert "Mod 999" in kwargs["embed"].description


# ---------------------------------------------------------------------------
# TestBatchModAddConfirmView
# ---------------------------------------------------------------------------

class TestBatchModAddConfirmView:

    def _view(self, server_names=None, bot=None) -> BatchModAddConfirmView:
        return BatchModAddConfirmView(
            mod_id="111",
            mod_name="TestMod",
            server_names=server_names or ["Alpha", "Beta"],
            guild_id=1,
            bot=bot or make_bot(),
        )

    @pytest.mark.asyncio
    async def test_no_agent_manager_returns_error(self):
        bot = make_bot()
        bot.agent_manager = None
        view = self._view(bot=bot)
        interaction = make_interaction(client=bot)
        await view.confirm.callback(interaction)
        content = interaction.edit_original_response.call_args[1]["content"]
        assert "Agent manager" in content

    @pytest.mark.asyncio
    async def test_no_agent_connected_returns_error(self):
        am = make_agent_manager()
        am.get_connected_agent_for_guild = AsyncMock(return_value=None)
        bot = make_bot(agent_manager=am)
        view = self._view(bot=bot)
        interaction = make_interaction(client=bot)
        await view.confirm.callback(interaction)
        content = interaction.edit_original_response.call_args[1]["content"]
        assert "No remote agent" in content

    @pytest.mark.asyncio
    async def test_already_present_shows_warning(self):
        am = make_agent_manager(mod_ids=["111"])
        bot = make_bot(agent_manager=am)
        view = self._view(server_names=["Alpha"], bot=bot)
        interaction = make_interaction(client=bot)
        await view.confirm.callback(interaction)
        embed = interaction.edit_original_response.call_args[1]["embed"]
        assert "Already present" in embed.description

    @pytest.mark.asyncio
    async def test_successful_add_shows_check(self):
        am = make_agent_manager(mod_ids=[], set_ok=True)
        bot = make_bot(agent_manager=am)
        view = self._view(server_names=["Alpha"], bot=bot)
        interaction = make_interaction(client=bot)
        with patch("bot.cogs.mod_management._log_to_channel", AsyncMock()):
            await view.confirm.callback(interaction)
        embed = interaction.edit_original_response.call_args[1]["embed"]
        assert "✅" in embed.description

    @pytest.mark.asyncio
    async def test_set_mods_failure_shows_error(self):
        am = make_agent_manager(mod_ids=[], set_ok=False)
        bot = make_bot(agent_manager=am)
        view = self._view(server_names=["Alpha"], bot=bot)
        interaction = make_interaction(client=bot)
        await view.confirm.callback(interaction)
        embed = interaction.edit_original_response.call_args[1]["embed"]
        assert "❌" in embed.description

    @pytest.mark.asyncio
    async def test_per_server_results_all_shown(self):
        # Alpha has the mod (already present); Beta does not (will be added)
        am = AsyncMock()
        am.get_connected_agent_for_guild = AsyncMock(return_value="agent-1")

        async def get_mods(agent_id, server_name):
            if server_name == "Alpha":
                return {"type": "complete", "data": {"mod_ids": ["111"]}}
            return {"type": "complete", "data": {"mod_ids": []}}

        am.get_mods = get_mods
        am.set_mods = AsyncMock(return_value={"type": "complete"})
        bot = make_bot(agent_manager=am)
        view = self._view(server_names=["Alpha", "Beta"], bot=bot)
        interaction = make_interaction(client=bot)
        with patch("bot.cogs.mod_management._log_to_channel", AsyncMock()):
            await view.confirm.callback(interaction)
        embed = interaction.edit_original_response.call_args[1]["embed"]
        assert "Alpha" in embed.description
        assert "Beta" in embed.description

    @pytest.mark.asyncio
    async def test_cancel_sends_cancelled_message(self):
        view = self._view()
        interaction = make_interaction()
        await view.cancel.callback(interaction)
        interaction.response.edit_message.assert_called_once()
        assert "Cancelled" in interaction.response.edit_message.call_args[1].get("content", "")


# ---------------------------------------------------------------------------
# TestBatchModRemoveView
# ---------------------------------------------------------------------------

class TestBatchModRemoveView:

    def _view(self, mod_ids=None, server_names=None) -> BatchModRemoveView:
        ids = mod_ids or ["111", "222"]
        info = {mid: {"name": f"Mod {mid}", "url": ""} for mid in ids}
        return BatchModRemoveView(
            mod_ids=ids,
            mod_info=info,
            server_names=server_names or ["Alpha", "Beta"],
            guild_id=1,
            user_id=99,
            bot=make_bot(),
        )

    def test_pagination_calculated_correctly(self):
        view = self._view(mod_ids=[str(i) for i in range(12)])
        assert view.total_pages == 3  # 12 / 5 = 2.4 → 3 pages

    def test_remove_select_created_on_init(self):
        view = self._view()
        assert hasattr(view, "remove_select")
        assert view.remove_select in view.children

    @pytest.mark.asyncio
    async def test_interaction_check_correct_user(self):
        view = self._view()
        interaction = make_interaction(user_id=99)
        result = await view.interaction_check(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_interaction_check_wrong_user(self):
        view = self._view()
        interaction = make_interaction(user_id=555)
        result = await view.interaction_check(interaction)
        assert result is False

    @pytest.mark.asyncio
    async def test_embed_shows_server_list(self):
        view = self._view(server_names=["Alpha", "Beta"])
        embed = await view.create_embed()
        assert "Alpha" in embed.description
        assert "Beta" in embed.description

    @pytest.mark.asyncio
    async def test_embed_shows_mod_count(self):
        view = self._view(mod_ids=["111", "222"])
        embed = await view.create_embed()
        assert "2" in embed.description

    @pytest.mark.asyncio
    async def test_remove_callback_sends_confirm_view(self):
        view = self._view(mod_ids=["111"])
        view.remove_select = MagicMock()
        view.remove_select.values = ["111"]
        interaction = make_interaction(user_id=99)
        await view._remove_mod_callback(interaction)
        interaction.response.send_message.assert_called_once()
        kwargs = interaction.response.send_message.call_args[1]
        assert isinstance(kwargs.get("view"), BatchModRemoveConfirmView)
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_navigation_updates_page(self):
        view = self._view(mod_ids=[str(i) for i in range(10)])
        interaction = make_interaction(user_id=99)
        await view.next_page(interaction)
        assert view.current_page == 1
        interaction.response.edit_message.assert_called_once()


# ---------------------------------------------------------------------------
# TestBatchModRemoveConfirmView
# ---------------------------------------------------------------------------

class TestBatchModRemoveConfirmView:

    def _view(self, server_names=None, bot=None) -> BatchModRemoveConfirmView:
        return BatchModRemoveConfirmView(
            mod_id="111",
            mod_name="TestMod",
            server_names=server_names or ["Alpha", "Beta"],
            guild_id=1,
            bot=bot or make_bot(),
        )

    @pytest.mark.asyncio
    async def test_no_agent_manager_returns_error(self):
        bot = make_bot()
        bot.agent_manager = None
        view = self._view(bot=bot)
        interaction = make_interaction(client=bot)
        await view.confirm.callback(interaction)
        content = interaction.edit_original_response.call_args[1]["content"]
        assert "Agent manager" in content

    @pytest.mark.asyncio
    async def test_no_agent_connected_returns_error(self):
        am = make_agent_manager()
        am.get_connected_agent_for_guild = AsyncMock(return_value=None)
        bot = make_bot(agent_manager=am)
        view = self._view(bot=bot)
        interaction = make_interaction(client=bot)
        await view.confirm.callback(interaction)
        content = interaction.edit_original_response.call_args[1]["content"]
        assert "No remote agent" in content

    @pytest.mark.asyncio
    async def test_mod_not_found_shows_warning(self):
        am = make_agent_manager(mod_ids=["999"])  # mod 111 not present
        bot = make_bot(agent_manager=am)
        view = self._view(server_names=["Alpha"], bot=bot)
        interaction = make_interaction(client=bot)
        await view.confirm.callback(interaction)
        embed = interaction.edit_original_response.call_args[1]["embed"]
        assert "Not found (skipped)" in embed.description

    @pytest.mark.asyncio
    async def test_successful_remove_shows_check(self):
        am = make_agent_manager(mod_ids=["111"], set_ok=True)
        bot = make_bot(agent_manager=am)
        view = self._view(server_names=["Alpha"], bot=bot)
        interaction = make_interaction(client=bot)
        with patch("bot.cogs.mod_management._log_to_channel", AsyncMock()):
            await view.confirm.callback(interaction)
        embed = interaction.edit_original_response.call_args[1]["embed"]
        assert "✅" in embed.description

    @pytest.mark.asyncio
    async def test_set_mods_failure_shows_error(self):
        am = make_agent_manager(mod_ids=["111"], set_ok=False)
        bot = make_bot(agent_manager=am)
        view = self._view(server_names=["Alpha"], bot=bot)
        interaction = make_interaction(client=bot)
        await view.confirm.callback(interaction)
        embed = interaction.edit_original_response.call_args[1]["embed"]
        assert "❌" in embed.description

    @pytest.mark.asyncio
    async def test_per_server_results_all_shown(self):
        # Alpha has mod 111 (removes ok); Beta does not have it (skips)
        am = AsyncMock()
        am.get_connected_agent_for_guild = AsyncMock(return_value="agent-1")

        async def get_mods(agent_id, server_name):
            if server_name == "Alpha":
                return {"type": "complete", "data": {"mod_ids": ["111"]}}
            return {"type": "complete", "data": {"mod_ids": ["999"]}}

        am.get_mods = get_mods
        am.set_mods = AsyncMock(return_value={"type": "complete"})
        bot = make_bot(agent_manager=am)
        view = self._view(server_names=["Alpha", "Beta"], bot=bot)
        interaction = make_interaction(client=bot)
        with patch("bot.cogs.mod_management._log_to_channel", AsyncMock()):
            await view.confirm.callback(interaction)
        embed = interaction.edit_original_response.call_args[1]["embed"]
        assert "Alpha" in embed.description
        assert "Beta" in embed.description

    @pytest.mark.asyncio
    async def test_cancel_sends_cancelled_message(self):
        view = self._view()
        interaction = make_interaction()
        await view.cancel.callback(interaction)
        interaction.response.edit_message.assert_called_once()
        assert "Cancelled" in interaction.response.edit_message.call_args[1].get("content", "")

    @pytest.mark.asyncio
    async def test_refresh_triggered_on_success(self):
        am = make_agent_manager(mod_ids=["111"], set_ok=True)
        mod_cog = MagicMock()
        mod_cog._refresh_and_send_mod_embeds = AsyncMock()
        bot = make_bot(agent_manager=am)
        bot.get_cog = MagicMock(return_value=mod_cog)
        view = self._view(server_names=["Alpha"], bot=bot)
        interaction = make_interaction(client=bot)
        with patch("bot.cogs.mod_management._log_to_channel", AsyncMock()):
            with patch("asyncio.create_task") as mock_create_task:
                await view.confirm.callback(interaction)
                mock_create_task.assert_called_once()
