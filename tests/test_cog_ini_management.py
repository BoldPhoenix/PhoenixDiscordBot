"""
Tests for batch INI management classes in ini_management.py.

Covers:
  - BatchEditButton    (only added when 2+ servers; row = 3)
  - BatchIniServerSelectView  (continue disabled initially; All Servers; Cancel; Continue→file)
  - BatchIniFileSelectView    (GUS button opens modal; Game.ini button opens modal; Cancel)
  - BatchIniEditModal         (empty section rejected; empty key rejected; dynamic→🟢; restart→🔴)
  - BatchIniEditConfirmView   (no agent_manager; dynamic+agent; dynamic+offline; restart-required;
                                errors; cancel; log channel)
"""

import asyncio
import pytest
import discord

from unittest.mock import AsyncMock, MagicMock, patch

from bot.cogs.ini_management import (
    BatchEditButton,
    BatchIniServerSelectView,
    BatchIniFileSelectView,
    BatchIniSettingsView,
    BatchIniValueModal,
    BatchIniEditConfirmView,
    IniServerSelectView,
)


# ---------------------------------------------------------------------------
# Helpers
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


def make_agent_manager(agent_id="agent-1", ini_update_ok=True):
    am = AsyncMock()
    am.get_connected_agent_for_guild = AsyncMock(return_value=agent_id)
    result = {"type": "complete"} if ini_update_ok else {"type": "error", "error": "write failed"}
    am.update_ini_setting = AsyncMock(return_value=result)
    return am


def make_bot(agent_manager=None):
    bot = MagicMock()
    bot.agent_manager = agent_manager
    return bot


# ---------------------------------------------------------------------------
# TestBatchEditButton
# ---------------------------------------------------------------------------

class TestBatchEditButton:
    """BatchEditButton added only when 2+ servers, on row 3."""

    def _view_buttons(self, n: int):
        servers = [make_server(f"Server{i}") for i in range(n)]
        view = IniServerSelectView(guild_id=1, servers=servers, user_id=42)
        return [item for item in view.children if isinstance(item, BatchEditButton)], view

    def test_one_server_no_batch_button(self):
        btns, _ = self._view_buttons(1)
        assert len(btns) == 0

    def test_two_servers_has_batch_button(self):
        btns, _ = self._view_buttons(2)
        assert len(btns) == 1

    def test_three_servers_has_batch_button(self):
        btns, _ = self._view_buttons(3)
        assert len(btns) == 1

    def test_batch_button_row_is_3(self):
        btns, _ = self._view_buttons(2)
        assert btns[0].row == 3

    def test_batch_button_label_contains_batch(self):
        btns, _ = self._view_buttons(2)
        label = btns[0].label.lower()
        assert "batch" in label

    @pytest.mark.asyncio
    async def test_batch_button_callback_sends_ephemeral(self):
        servers = [make_server("A"), make_server("B")]
        btn = BatchEditButton(servers=servers, guild_id=1, user_id=99)
        interaction = make_interaction(user_id=99)
        await btn.callback(interaction)
        interaction.response.send_message.assert_called_once()
        kwargs = interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True
        assert isinstance(kwargs.get("view"), BatchIniServerSelectView)


# ---------------------------------------------------------------------------
# TestBatchIniServerSelectView
# ---------------------------------------------------------------------------

class TestBatchIniServerSelectView:
    """Server multi-select: continue initially disabled, All Servers, Cancel, Continue."""

    def _view(self, n=3):
        servers = [make_server(f"Srv{i}") for i in range(n)]
        return BatchIniServerSelectView(servers=servers, guild_id=1, user_id=42), servers

    def _get_continue_btn(self, view):
        return view.continue_btn

    def test_continue_disabled_initially(self):
        view, _ = self._view()
        btn = self._get_continue_btn(view)
        assert btn.disabled is True

    def test_continue_enabled_after_select_all(self):
        view, servers = self._view()
        view.selected_servers = [s["name"] for s in servers]
        view._build_ui()
        btn = self._get_continue_btn(view)
        assert btn.disabled is False

    def test_all_servers_fills_selected(self):
        view, servers = self._view()
        assert view.selected_servers == []
        # simulate _select_all without async
        view.selected_servers = [s.get("name", "Unknown") for s in view.servers]
        assert len(view.selected_servers) == len(servers)

    @pytest.mark.asyncio
    async def test_select_all_updates_view(self):
        view, servers = self._view()
        interaction = make_interaction(user_id=42)
        await view._select_all(interaction)
        assert len(view.selected_servers) == len(servers)
        interaction.response.edit_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_clears_message(self):
        view, _ = self._view()
        interaction = make_interaction(user_id=42)
        await view._cancel(interaction)
        interaction.response.edit_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_continue_with_no_servers_sends_error(self):
        view, _ = self._view()
        view.selected_servers = []
        interaction = make_interaction(user_id=42)
        await view._continue(interaction)
        interaction.response.send_message.assert_called_once()
        msg = interaction.response.send_message.call_args.args[0]
        assert "select" in msg.lower()

    @pytest.mark.asyncio
    async def test_continue_with_servers_opens_file_view(self):
        view, servers = self._view()
        view.selected_servers = [s["name"] for s in servers]
        interaction = make_interaction(user_id=42)
        await view._continue(interaction)
        interaction.response.edit_message.assert_called_once()
        kwargs = interaction.response.edit_message.call_args.kwargs
        assert isinstance(kwargs.get("view"), BatchIniFileSelectView)

    @pytest.mark.asyncio
    async def test_on_select_updates_selected_servers(self):
        view, servers = self._view()
        # Simulate a select item with values (use _values internal attr)
        select_item = next(
            item for item in view.children if isinstance(item, discord.ui.Select)
        )
        select_item._values = ["Srv0", "Srv1"]
        interaction = make_interaction(user_id=42)
        await view._on_select(interaction)
        assert "Srv0" in view.selected_servers
        assert "Srv1" in view.selected_servers

    def test_select_max_values_capped_at_25(self):
        # Build view with 30 servers
        servers = [make_server(f"S{i}") for i in range(30)]
        view = BatchIniServerSelectView(servers=servers, guild_id=1, user_id=42)
        select_item = next(
            item for item in view.children if isinstance(item, discord.ui.Select)
        )
        assert select_item.max_values <= 25

    @pytest.mark.asyncio
    async def test_interaction_check_returns_false_for_other_user(self):
        view, _ = self._view()
        interaction = make_interaction(user_id=999)
        result = await view.interaction_check(interaction)
        assert result is False


# ---------------------------------------------------------------------------
# TestBatchIniFileSelectView
# ---------------------------------------------------------------------------

class TestBatchIniFileSelectView:
    """File picker: buttons load settings and open BatchIniSettingsView."""

    def _view(self):
        return BatchIniFileSelectView(server_names=["Srv0", "Srv1"], guild_id=1, user_id=42)

    def _get_buttons(self, view):
        return [item for item in view.children if isinstance(item, discord.ui.Button)]

    def _fake_settings(self):
        return [{"key_name": "HarvestAmountMultiplier", "key_value": "2.0", "section_name": "ServerSettings"}]

    @pytest.mark.asyncio
    async def test_gus_button_opens_settings_view(self):
        view = self._view()
        interaction = make_interaction(user_id=42)
        btns = self._get_buttons(view)
        gus_btn = next(b for b in btns if "GameUserSettings" in b.label)
        with patch("bot.database.ini_settings_db.get_ini_settings", AsyncMock(return_value=self._fake_settings())):
            await gus_btn.callback(interaction)
        interaction.response.edit_message.assert_called_once()
        kwargs = interaction.response.edit_message.call_args.kwargs
        assert isinstance(kwargs.get("view"), BatchIniSettingsView)

    @pytest.mark.asyncio
    async def test_game_ini_button_opens_settings_view(self):
        view = self._view()
        interaction = make_interaction(user_id=42)
        btns = self._get_buttons(view)
        game_btn = next(b for b in btns if "Game.ini" in b.label and "GameUser" not in b.label)
        with patch("bot.database.ini_settings_db.get_ini_settings", AsyncMock(return_value=self._fake_settings())):
            await game_btn.callback(interaction)
        interaction.response.edit_message.assert_called_once()
        kwargs = interaction.response.edit_message.call_args.kwargs
        assert isinstance(kwargs.get("view"), BatchIniSettingsView)

    @pytest.mark.asyncio
    async def test_settings_view_carries_server_names(self):
        view = self._view()
        interaction = make_interaction(user_id=42)
        btns = self._get_buttons(view)
        gus_btn = next(b for b in btns if "GameUserSettings" in b.label)
        with patch("bot.database.ini_settings_db.get_ini_settings", AsyncMock(return_value=self._fake_settings())):
            await gus_btn.callback(interaction)
        settings_view = interaction.response.edit_message.call_args.kwargs.get("view")
        assert settings_view.server_names == ["Srv0", "Srv1"]

    @pytest.mark.asyncio
    async def test_no_settings_shows_error(self):
        view = self._view()
        interaction = make_interaction(user_id=42)
        btns = self._get_buttons(view)
        gus_btn = next(b for b in btns if "GameUserSettings" in b.label)
        with patch("bot.database.ini_settings_db.get_ini_settings", AsyncMock(return_value=[])):
            await gus_btn.callback(interaction)
        kwargs = interaction.response.edit_message.call_args.kwargs
        assert kwargs.get("view") is None
        assert "No settings found" in kwargs.get("content", "")

    @pytest.mark.asyncio
    async def test_cancel_clears(self):
        view = self._view()
        interaction = make_interaction(user_id=42)
        btns = self._get_buttons(view)
        cancel_btn = next(b for b in btns if "Cancel" in b.label)
        await cancel_btn.callback(interaction)
        interaction.response.edit_message.assert_called_once()


# ---------------------------------------------------------------------------
# TestBatchIniSettingsView
# ---------------------------------------------------------------------------

class TestBatchIniSettingsView:
    """BatchIniSettingsView: Select buttons, server-specific filter, back navigation."""

    def _settings(self):
        return [
            {"key_name": "HarvestAmountMultiplier", "key_value": "2.0", "section_name": "ServerSettings"},
            {"key_name": "MaxPlayers", "key_value": "70", "section_name": "ServerSettings"},
            {"key_name": "ServerName", "key_value": "My ARK", "section_name": "SessionSettings"},
            {"key_name": "Port", "key_value": "7777", "section_name": "SessionSettings"},
            {"key_name": "SpectatorPassword", "key_value": "secret", "section_name": "ServerSettings"},
            {"key_name": "ServerId", "key_value": "abc-123", "section_name": "AsaBotCompanion"},
            {"key_name": "Message", "key_value": "Welcome!", "section_name": "MessageOfTheDay"},
            {"key_name": "Duration", "key_value": "20", "section_name": "MessageOfTheDay"},
        ]

    def _view(self, server_names=None):
        return BatchIniSettingsView(
            server_names=server_names or ["Srv0", "Srv1"],
            guild_id=1,
            file_name="GameUserSettings.ini",
            settings=self._settings(),
            user_id=42,
        )

    def test_server_specific_keys_excluded(self):
        view = self._view()
        shown = view._get_settings_to_show()
        keys = [s["key_name"] for s in shown]
        assert "ServerName" not in keys
        assert "Port" not in keys
        assert "SpectatorPassword" not in keys
        assert "ServerId" not in keys

    def test_motd_section_excluded(self):
        view = self._view()
        shown = view._get_settings_to_show()
        sections = [s["section_name"] for s in shown]
        assert "MessageOfTheDay" not in sections

    def test_non_specific_keys_included(self):
        view = self._view()
        shown = view._get_settings_to_show()
        keys = [s["key_name"] for s in shown]
        assert "HarvestAmountMultiplier" in keys
        assert "MaxPlayers" in keys

    def test_select_buttons_not_edit_buttons(self):
        view = self._view()
        btns = [item for item in view.children if isinstance(item, discord.ui.Button)]
        action_btns = [b for b in btns if b.label.startswith("Select")]
        edit_btns = [b for b in btns if b.label.startswith("Edit")]
        assert len(action_btns) > 0
        assert len(edit_btns) == 0

    def test_embed_description_contains_server_list(self):
        view = self._view(server_names=["Alpha", "Beta"])
        embed = view.create_embed()
        assert "Alpha" in embed.description
        assert "Beta" in embed.description

    def test_embed_description_mentions_lock(self):
        view = self._view()
        embed = view.create_embed()
        assert "🔒" in embed.description or "server-specific" in embed.description.lower()

    def test_server_names_stored(self):
        view = self._view(server_names=["A", "B", "C"])
        assert view.server_names == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_select_button_opens_value_modal(self):
        view = self._view()
        # Find first Select button
        btns = [item for item in view.children if isinstance(item, discord.ui.Button) and item.label.startswith("Select")]
        assert len(btns) > 0
        interaction = make_interaction(user_id=42)
        await btns[0].callback(interaction)
        interaction.response.send_modal.assert_called_once()
        modal = interaction.response.send_modal.call_args.args[0]
        assert isinstance(modal, BatchIniValueModal)

    @pytest.mark.asyncio
    async def test_go_back_returns_to_file_select(self):
        view = self._view()
        interaction = make_interaction(user_id=42)
        await view._go_back(interaction)
        interaction.response.edit_message.assert_called_once()
        kwargs = interaction.response.edit_message.call_args.kwargs
        assert isinstance(kwargs.get("view"), BatchIniFileSelectView)

    def test_many_servers_truncated_in_embed(self):
        view = self._view(server_names=["S1", "S2", "S3", "S4", "S5"])
        embed = view.create_embed()
        assert "+2 more" in embed.description


# ---------------------------------------------------------------------------
# TestBatchIniValueModal
# ---------------------------------------------------------------------------

class TestBatchIniValueModal:
    """BatchIniValueModal: pre-filled value, confirm view creation."""

    def _setting(self, key="MaxPlayers", value="70", section="ServerSettings"):
        return {"key_name": key, "key_value": value, "section_name": section}

    def _modal(self, key="MaxPlayers", value="70", file_name="GameUserSettings.ini"):
        return BatchIniValueModal(
            server_names=["Srv0", "Srv1"],
            file_name=file_name,
            setting=self._setting(key=key, value=value),
            guild_id=1,
            user_id=42,
        )

    def test_modal_has_only_value_field(self):
        modal = self._modal()
        assert hasattr(modal, "value_input")
        assert not hasattr(modal, "key_input")
        assert not hasattr(modal, "section_input")

    def test_value_prefilled_with_current(self):
        modal = self._modal(value="42")
        assert modal.value_input.default == "42"

    def test_title_contains_key_name(self):
        modal = self._modal(key="HarvestAmountMultiplier")
        assert "HarvestAmountMultiplier" in modal.title

    @pytest.mark.asyncio
    async def test_submit_creates_confirm_view(self):
        modal = self._modal()
        modal.value_input._value = "100"
        interaction = make_interaction(user_id=42)
        await modal.on_submit(interaction)
        kwargs = interaction.response.send_message.call_args.kwargs
        assert isinstance(kwargs.get("view"), BatchIniEditConfirmView)

    @pytest.mark.asyncio
    async def test_confirm_view_has_correct_key_and_value(self):
        modal = self._modal(key="MaxPlayers")
        modal.value_input._value = "80"
        interaction = make_interaction(user_id=42)
        await modal.on_submit(interaction)
        view = interaction.response.send_message.call_args.kwargs.get("view")
        assert view.key == "MaxPlayers"
        assert view.value == "80"
        assert view.server_names == ["Srv0", "Srv1"]

    @pytest.mark.asyncio
    async def test_dynamic_shows_green_in_embed(self):
        modal = self._modal(key="HarvestAmountMultiplier")
        modal.value_input._value = "3.0"
        interaction = make_interaction(user_id=42)
        await modal.on_submit(interaction)
        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        embed_text = " ".join(f.value for f in embed.fields)
        assert "🟢" in embed_text

    @pytest.mark.asyncio
    async def test_restart_required_shows_red_in_embed(self):
        modal = self._modal(key="MaxPlayers")
        modal.value_input._value = "80"
        interaction = make_interaction(user_id=42)
        await modal.on_submit(interaction)
        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        embed_text = " ".join(f.value for f in embed.fields)
        assert "🔴" in embed_text

    @pytest.mark.asyncio
    async def test_embed_shows_current_and_new_value(self):
        modal = self._modal(key="MaxPlayers", value="70")
        modal.value_input._value = "80"
        interaction = make_interaction(user_id=42)
        await modal.on_submit(interaction)
        embed = interaction.response.send_message.call_args.kwargs.get("embed")
        field_names = [f.name for f in embed.fields]
        assert "Current Value" in field_names
        assert "New Value" in field_names

    @pytest.mark.asyncio
    async def test_ephemeral(self):
        modal = self._modal()
        modal.value_input._value = "80"
        interaction = make_interaction(user_id=42)
        await modal.on_submit(interaction)
        assert interaction.response.send_message.call_args.kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# TestBatchIniEditConfirmView
# ---------------------------------------------------------------------------

class TestBatchIniEditConfirmView:
    """Confirm view: dynamic/restart/offline/error/cancel/log behaviors."""

    def _view(
        self,
        server_names=None,
        file_name="GameUserSettings.ini",
        key="MaxPlayers",
        value="80",
        is_dynamic=False,
    ):
        return BatchIniEditConfirmView(
            server_names=server_names or ["Srv0", "Srv1"],
            file_name=file_name,
            key=key,
            value=value,
            is_dynamic=is_dynamic,
            guild_id=1,
            user_id=42,
        )

    def _mock_find(self, section="ServerSettings", old_value="50"):
        """Return an AsyncMock for find_ini_setting_by_key that returns a found row."""
        return AsyncMock(return_value={"section_name": section, "key_value": old_value})

    def _get_confirm_btn(self, view):
        return next(b for b in view.children if "Confirm" in b.label)

    def _get_cancel_btn(self, view):
        return next(b for b in view.children if "Cancel" in b.label)

    @pytest.mark.asyncio
    async def test_no_agent_manager_returns_error(self):
        view = self._view(is_dynamic=True)
        bot = make_bot(agent_manager=None)
        interaction = make_interaction(user_id=42, client=bot)
        await view._confirm(interaction)
        interaction.response.defer.assert_called_once()
        interaction.edit_original_response.assert_called_once()
        content = interaction.edit_original_response.call_args.kwargs.get("content", "")
        assert "❌" in content or "No agent" in content

    @pytest.mark.asyncio
    async def test_key_not_found_shows_error_per_server(self):
        view = self._view(key="UnknownKey", is_dynamic=False, server_names=["Srv0"])
        am = make_agent_manager(agent_id="agent-1")
        bot = make_bot(agent_manager=am)
        interaction = make_interaction(user_id=42, client=bot)

        with patch("bot.database.ini_settings_db.find_ini_setting_by_key", AsyncMock(return_value=None)):
            with patch("bot.cogs.ini_management._log_to_channel", AsyncMock()):
                await view._confirm(interaction)

        embed = interaction.edit_original_response.call_args.kwargs.get("embed")
        assert embed is not None
        assert "❌" in embed.description
        assert "not found" in embed.description.lower()

    @pytest.mark.asyncio
    async def test_dynamic_setting_calls_db_and_agent(self):
        view = self._view(
            key="HarvestAmountMultiplier", is_dynamic=True,
            server_names=["Srv0", "Srv1"]
        )
        am = make_agent_manager(agent_id="agent-1", ini_update_ok=True)
        bot = make_bot(agent_manager=am)
        interaction = make_interaction(user_id=42, client=bot)

        with patch("bot.database.ini_settings_db.find_ini_setting_by_key", self._mock_find()):
            with patch("bot.database.ini_settings_db.update_ini_setting", AsyncMock(return_value=True)) as mock_db:
                with patch("bot.cogs.ini_management._log_to_channel", AsyncMock()):
                    await view._confirm(interaction)

        assert mock_db.call_count == 2
        assert am.update_ini_setting.call_count == 2

    @pytest.mark.asyncio
    async def test_dynamic_results_embed_shows_checkmarks(self):
        view = self._view(key="HarvestAmountMultiplier", is_dynamic=True, server_names=["Srv0"])
        am = make_agent_manager(agent_id="agent-1", ini_update_ok=True)
        bot = make_bot(agent_manager=am)
        interaction = make_interaction(user_id=42, client=bot)

        with patch("bot.database.ini_settings_db.find_ini_setting_by_key", self._mock_find()):
            with patch("bot.database.ini_settings_db.update_ini_setting", AsyncMock(return_value=True)):
                with patch("bot.cogs.ini_management._log_to_channel", AsyncMock()):
                    await view._confirm(interaction)

        embed = interaction.edit_original_response.call_args.kwargs.get("embed")
        assert embed is not None
        assert "✅" in embed.description

    @pytest.mark.asyncio
    async def test_dynamic_agent_offline_shows_warning(self):
        view = self._view(key="HarvestAmountMultiplier", is_dynamic=True, server_names=["Srv0"])
        am = make_agent_manager(agent_id=None)
        bot = make_bot(agent_manager=am)
        interaction = make_interaction(user_id=42, client=bot)

        with patch("bot.database.ini_settings_db.find_ini_setting_by_key", self._mock_find()):
            with patch("bot.database.ini_settings_db.update_ini_setting", AsyncMock(return_value=True)):
                with patch("bot.cogs.ini_management._log_to_channel", AsyncMock()):
                    await view._confirm(interaction)

        embed = interaction.edit_original_response.call_args.kwargs.get("embed")
        assert embed is not None
        assert "⚠️" in embed.description

    @pytest.mark.asyncio
    async def test_restart_required_calls_queue_not_agent(self):
        view = self._view(key="MaxPlayers", is_dynamic=False, server_names=["Srv0", "Srv1"])
        am = make_agent_manager(agent_id="agent-1")
        bot = make_bot(agent_manager=am)
        interaction = make_interaction(user_id=42, client=bot)

        with patch("bot.database.ini_settings_db.find_ini_setting_by_key", self._mock_find()):
            with patch("bot.database.ini_settings_db.queue_ini_change", AsyncMock(return_value=True)) as mock_q:
                with patch("bot.cogs.ini_management._log_to_channel", AsyncMock()):
                    await view._confirm(interaction)

        assert mock_q.call_count == 2
        am.update_ini_setting.assert_not_called()

    @pytest.mark.asyncio
    async def test_restart_results_embed_shows_queued(self):
        view = self._view(key="MaxPlayers", is_dynamic=False, server_names=["Srv0"])
        am = make_agent_manager(agent_id="agent-1")
        bot = make_bot(agent_manager=am)
        interaction = make_interaction(user_id=42, client=bot)

        with patch("bot.database.ini_settings_db.find_ini_setting_by_key", self._mock_find()):
            with patch("bot.database.ini_settings_db.queue_ini_change", AsyncMock(return_value=True)):
                with patch("bot.cogs.ini_management._log_to_channel", AsyncMock()):
                    await view._confirm(interaction)

        embed = interaction.edit_original_response.call_args.kwargs.get("embed")
        assert embed is not None
        assert "⏳" in embed.description

    @pytest.mark.asyncio
    async def test_db_failure_shows_error_in_results(self):
        view = self._view(key="HarvestAmountMultiplier", is_dynamic=True, server_names=["Srv0"])
        am = make_agent_manager(agent_id="agent-1")
        bot = make_bot(agent_manager=am)
        interaction = make_interaction(user_id=42, client=bot)

        with patch("bot.database.ini_settings_db.find_ini_setting_by_key", self._mock_find()):
            with patch("bot.database.ini_settings_db.update_ini_setting", AsyncMock(return_value=False)):
                with patch("bot.cogs.ini_management._log_to_channel", AsyncMock()):
                    await view._confirm(interaction)

        embed = interaction.edit_original_response.call_args.kwargs.get("embed")
        assert embed is not None
        assert "❌" in embed.description

    @pytest.mark.asyncio
    async def test_agent_error_shows_error_in_results(self):
        view = self._view(key="HarvestAmountMultiplier", is_dynamic=True, server_names=["Srv0"])
        am = make_agent_manager(agent_id="agent-1", ini_update_ok=False)
        bot = make_bot(agent_manager=am)
        interaction = make_interaction(user_id=42, client=bot)

        with patch("bot.database.ini_settings_db.find_ini_setting_by_key", self._mock_find()):
            with patch("bot.database.ini_settings_db.update_ini_setting", AsyncMock(return_value=True)):
                with patch("bot.cogs.ini_management._log_to_channel", AsyncMock()):
                    await view._confirm(interaction)

        embed = interaction.edit_original_response.call_args.kwargs.get("embed")
        assert embed is not None
        assert "❌" in embed.description

    @pytest.mark.asyncio
    async def test_per_server_results_all_shown(self):
        view = self._view(
            key="HarvestAmountMultiplier", is_dynamic=True,
            server_names=["Alpha", "Beta", "Gamma"]
        )
        am = make_agent_manager(agent_id="agent-1", ini_update_ok=True)
        bot = make_bot(agent_manager=am)
        interaction = make_interaction(user_id=42, client=bot)

        with patch("bot.database.ini_settings_db.find_ini_setting_by_key", self._mock_find()):
            with patch("bot.database.ini_settings_db.update_ini_setting", AsyncMock(return_value=True)):
                with patch("bot.cogs.ini_management._log_to_channel", AsyncMock()):
                    await view._confirm(interaction)

        embed = interaction.edit_original_response.call_args.kwargs.get("embed")
        assert embed is not None
        assert "Alpha" in embed.description
        assert "Beta" in embed.description
        assert "Gamma" in embed.description

    @pytest.mark.asyncio
    async def test_cancel_does_not_call_db(self):
        view = self._view()
        interaction = make_interaction(user_id=42)
        with patch("bot.database.ini_settings_db.update_ini_setting") as mock_db:
            with patch("bot.database.ini_settings_db.queue_ini_change") as mock_q:
                await view._cancel(interaction)
        mock_db.assert_not_called()
        mock_q.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_edits_message(self):
        view = self._view()
        interaction = make_interaction(user_id=42)
        await view._cancel(interaction)
        interaction.response.edit_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_channel_called_on_success(self):
        view = self._view(key="MaxPlayers", is_dynamic=False, server_names=["Srv0"])
        am = make_agent_manager(agent_id="agent-1")
        bot = make_bot(agent_manager=am)
        interaction = make_interaction(user_id=42, client=bot)

        with patch("bot.database.ini_settings_db.find_ini_setting_by_key", self._mock_find()):
            with patch("bot.database.ini_settings_db.queue_ini_change", AsyncMock(return_value=True)):
                with patch("bot.cogs.ini_management._log_to_channel", AsyncMock()) as mock_log:
                    await view._confirm(interaction)

        mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_results_embed_footer_contains_key(self):
        view = self._view(key="MaxPlayers", is_dynamic=False, server_names=["Srv0"])
        am = make_agent_manager(agent_id="agent-1")
        bot = make_bot(agent_manager=am)
        interaction = make_interaction(user_id=42, client=bot)

        with patch("bot.database.ini_settings_db.find_ini_setting_by_key", self._mock_find()):
            with patch("bot.database.ini_settings_db.queue_ini_change", AsyncMock(return_value=True)):
                with patch("bot.cogs.ini_management._log_to_channel", AsyncMock()):
                    await view._confirm(interaction)

        embed = interaction.edit_original_response.call_args.kwargs.get("embed")
        assert embed is not None
        assert embed.footer is not None
        assert "MaxPlayers" in embed.footer.text

    @pytest.mark.asyncio
    async def test_interaction_check_blocks_other_users(self):
        view = self._view()
        interaction = make_interaction(user_id=999)
        result = await view.interaction_check(interaction)
        assert result is False
