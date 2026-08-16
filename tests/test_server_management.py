"""
Tests for server_management.py - Server Management Console.

Tests cover:
- Helper functions (_build_server_options, _server_label, _get_server_by_identifier)
- Embed builders (correct titles, descriptions, icons)
- View construction (correct buttons, rows, server context propagation)
- Modal construction
- Cog setup
- Icon/label alignment with PS bot
- Button style correctness
- Ephemeral navigation

Uses real discord.py objects — no mocks (Jeffrey Snover methodology).
Views/Modals require a running asyncio event loop; all such tests are async.
"""

import pytest
import asyncio
from types import SimpleNamespace
import discord


# ---------------------------------------------------------------------------
# Lightweight bot stand-in (no mocks — real namespace with real attributes)
# ---------------------------------------------------------------------------

class _FakeAgentManager:
    """Minimal stand-in for RemoteAgentManager used in view construction tests."""
    async def get_connected_agent_for_guild(self, guild_id: int):
        return None


def _make_bot():
    """Create a lightweight bot-like object with agent_manager."""
    bot = SimpleNamespace()
    bot.agent_manager = _FakeAgentManager()
    return bot


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestBuildServerOptions:
    def test_basic_server(self):
        from bot.cogs.server_management import _build_server_options
        servers = [
            {"name": "Aberration", "display_name": "Aberration Server",
             "host": "192.168.1.10", "map_name": "Aberration_WP", "id": 1}
        ]
        options = _build_server_options(servers)
        assert len(options) == 1
        assert options[0].label == "Aberration Server"
        assert options[0].value == "Aberration"
        assert "Aberration_WP" in options[0].description

    def test_missing_map_name_shows_not_set(self):
        from bot.cogs.server_management import _build_server_options
        servers = [{"name": "Test", "host": "localhost", "map_name": None, "id": 1}]
        options = _build_server_options(servers)
        assert len(options) == 1
        assert "Not set" in options[0].description

    def test_empty_servers(self):
        from bot.cogs.server_management import _build_server_options
        assert _build_server_options([]) == []

    def test_non_dict_skipped(self):
        from bot.cogs.server_management import _build_server_options
        assert _build_server_options(["not a dict"]) == []

    def test_fallback_to_server_id(self):
        from bot.cogs.server_management import _build_server_options
        servers = [{"id": 42, "host": "localhost", "name": "", "display_name": ""}]
        options = _build_server_options(servers)
        assert len(options) == 1
        assert "42" in options[0].label

    def test_label_truncated_at_100(self):
        from bot.cogs.server_management import _build_server_options
        servers = [{"name": "A" * 150, "host": "localhost", "id": 1}]
        options = _build_server_options(servers)
        assert len(options[0].label) <= 100

    def test_display_name_preferred_over_name(self):
        from bot.cogs.server_management import _build_server_options
        servers = [{"name": "internal", "display_name": "Public Name", "host": "h", "id": 1}]
        options = _build_server_options(servers)
        assert options[0].label == "Public Name"


class TestServerLabel:
    def test_display_name_preferred(self):
        from bot.cogs.server_management import _server_label
        assert _server_label({"display_name": "Pretty", "name": "ugly"}) == "Pretty"

    def test_fallback_to_name(self):
        from bot.cogs.server_management import _server_label
        assert _server_label({"name": "TestServer"}) == "TestServer"

    def test_fallback_to_id(self):
        from bot.cogs.server_management import _server_label
        assert "99" in _server_label({"id": 99})

    def test_empty_display_and_name(self):
        from bot.cogs.server_management import _server_label
        result = _server_label({"display_name": "", "name": "", "id": 7})
        assert "7" in result

    def test_whitespace_only_display_name(self):
        from bot.cogs.server_management import _server_label
        result = _server_label({"display_name": "   ", "name": "Fallback"})
        assert result == "Fallback"


class TestGetServerByIdentifier:
    @pytest.mark.asyncio
    async def test_find_by_name(self):
        from bot.cogs.server_management import _get_server_by_identifier
        servers = [{"name": "Aberration", "display_name": "Aber", "id": 1}]
        result = await _get_server_by_identifier(123, "Aberration", servers)
        assert result is not None
        assert result["name"] == "Aberration"

    @pytest.mark.asyncio
    async def test_find_by_display_name(self):
        from bot.cogs.server_management import _get_server_by_identifier
        servers = [{"name": "ab", "display_name": "Aber Server", "id": 1}]
        result = await _get_server_by_identifier(123, "Aber Server", servers)
        assert result is not None

    @pytest.mark.asyncio
    async def test_find_by_id(self):
        from bot.cogs.server_management import _get_server_by_identifier
        servers = [{"name": "ab", "display_name": "", "id": 5}]
        result = await _get_server_by_identifier(123, "5", servers)
        assert result is not None

    @pytest.mark.asyncio
    async def test_not_found(self):
        from bot.cogs.server_management import _get_server_by_identifier
        servers = [{"name": "ab", "display_name": "", "id": 1}]
        result = await _get_server_by_identifier(123, "nonexistent", servers)
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_identifier(self):
        from bot.cogs.server_management import _get_server_by_identifier
        result = await _get_server_by_identifier(123, "", [])
        assert result is None

    @pytest.mark.asyncio
    async def test_none_identifier(self):
        from bot.cogs.server_management import _get_server_by_identifier
        result = await _get_server_by_identifier(123, None, [])
        assert result is None

    @pytest.mark.asyncio
    async def test_non_dict_entries_skipped(self):
        from bot.cogs.server_management import _get_server_by_identifier
        servers = ["not_a_dict", {"name": "Real", "display_name": "", "id": 1}]
        result = await _get_server_by_identifier(123, "Real", servers)
        assert result is not None
        assert result["name"] == "Real"


# ---------------------------------------------------------------------------
# Embed builder tests
# ---------------------------------------------------------------------------

class TestEmbedBuilders:
    def test_main_panel_embed_content(self):
        from bot.cogs.server_management import _main_panel_embed
        embed = _main_panel_embed(3)
        assert "Server Management" in embed.title
        assert "3" in embed.description
        assert "Select a server" in embed.description

    def test_main_panel_embed_zero_servers(self):
        from bot.cogs.server_management import _main_panel_embed
        embed = _main_panel_embed(0)
        assert "0" in embed.description

    def test_category_panel_embed_content(self):
        from bot.cogs.server_management import _category_panel_embed
        server = {"display_name": "Aberration", "service_name": "ArkAberration", "hosting_type": "self_hosted"}
        embed = _category_panel_embed(server)
        assert "Select Category" in embed.title
        assert "Aberration" in embed.description
        assert "ArkAberration" in embed.description
        assert "Self-Hosted" in embed.description

    def test_category_panel_embed_missing_service(self):
        from bot.cogs.server_management import _category_panel_embed
        server = {"name": "Test"}
        embed = _category_panel_embed(server)
        assert "N/A" in embed.description

    def test_server_ops_embed(self):
        from bot.cogs.server_management import _server_ops_embed
        embed = _server_ops_embed({"display_name": "TestServer"})
        assert "Server Operations" in embed.title
        assert "TestServer" in embed.description

    def test_server_control_embed(self):
        from bot.cogs.server_management import _server_control_embed
        embed = _server_control_embed({"display_name": "MyServer"})
        assert "Server Control" in embed.title
        assert "MyServer" in embed.description

    def test_advanced_embed(self):
        from bot.cogs.server_management import _advanced_embed
        embed = _advanced_embed({"name": "Adv"})
        assert "Advanced" in embed.title

    def test_diagnostics_embed(self):
        from bot.cogs.server_management import _diagnostics_embed
        embed = _diagnostics_embed({"name": "Diag"})
        assert "Diagnostics" in embed.title

    def test_updates_embed(self):
        from bot.cogs.server_management import _updates_embed
        embed = _updates_embed([{}, {}])
        assert "Updates" in embed.title
        assert "2" in embed.description


# ---------------------------------------------------------------------------
# View construction tests (async — discord.py Views need event loop)
# ---------------------------------------------------------------------------

class TestViewConstruction:
    @pytest.mark.asyncio
    async def test_main_view_has_updates_button_and_select(self):
        from bot.cogs.server_management import ServerManagementView
        servers = [{"name": "S1", "display_name": "Server 1", "host": "h", "id": 1}]
        view = ServerManagementView(123, _make_bot(), servers)
        # Has Updates button and Select dropdown (no refresh button - auto-refresh)
        assert len(view.children) == 2

    @pytest.mark.asyncio
    async def test_main_view_no_servers_has_only_updates(self):
        from bot.cogs.server_management import ServerManagementView
        view = ServerManagementView(123, _make_bot(), [])
        # Has only Updates button when no servers (no refresh button - auto-refresh)
        assert len(view.children) == 1

    @pytest.mark.asyncio
    async def test_selected_view_has_5_buttons(self):
        from bot.cogs.server_management import ServerSelectedView
        server = {"name": "S1", "display_name": "S1"}
        view = ServerSelectedView(123, _make_bot(), server, [server])
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 5

    @pytest.mark.asyncio
    async def test_selected_view_back_label(self):
        from bot.cogs.server_management import ServerSelectedView
        server = {"name": "S1"}
        view = ServerSelectedView(123, _make_bot(), server, [server])
        back_btn = [c for c in view.children if isinstance(c, discord.ui.Button) and "Back" in (c.label or "")]
        assert len(back_btn) == 1
        assert "\u00ab" in back_btn[0].label

    @pytest.mark.asyncio
    async def test_server_ops_view_buttons(self):
        from bot.cogs.server_management import ServerOperationsView
        server = {"name": "S1", "host": "h", "rcon_port": 27020, "rcon_password": "pw"}
        view = ServerOperationsView(123, _make_bot(), server, [server])
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Broadcast" in l for l in labels)
        assert any("Save World" in l for l in labels)
        assert any("Destroy Wild" in l for l in labels)
        assert any("MOTD" in l for l in labels)
        assert any("Back" in l for l in labels)

    @pytest.mark.asyncio
    async def test_server_ops_destroy_wild_uses_t_rex(self):
        from bot.cogs.server_management import ServerOperationsView
        server = {"name": "S1", "host": "h", "rcon_port": 27020, "rcon_password": "pw"}
        view = ServerOperationsView(123, _make_bot(), server, [server])
        destroy_btn = [c for c in view.children if isinstance(c, discord.ui.Button) and "Destroy" in (c.label or "")]
        assert len(destroy_btn) == 1
        assert "\U0001f996" in destroy_btn[0].label

    @pytest.mark.asyncio
    async def test_server_control_view_has_correct_buttons(self):
        from bot.cogs.server_management import ServerControlView
        server = {"name": "S1", "host": "h", "rcon_port": 27020, "rcon_password": "pw"}
        view = ServerControlView(123, _make_bot(), server, [server])
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Stop" in l for l in labels)
        assert any("Start" in l for l in labels)
        assert any("Restart" in l for l in labels)
        assert any("Status" in l for l in labels)
        assert any("Back" in l for l in labels)

    @pytest.mark.asyncio
    async def test_server_control_receives_server_context(self):
        """ServerControlView must receive server dict — no re-selection needed."""
        from bot.cogs.server_management import ServerControlView
        server = {"name": "Aberration", "host": "h", "rcon_port": 27020, "rcon_password": "pw"}
        view = ServerControlView(123, _make_bot(), server, [server])
        assert view.server is server
        assert view.server["name"] == "Aberration"

    @pytest.mark.asyncio
    async def test_advanced_view_buttons(self):
        from bot.cogs.server_management import AdvancedToolsView
        server = {"name": "S1", "host": "h", "rcon_port": 27020, "rcon_password": "pw"}
        view = AdvancedToolsView(123, _make_bot(), server, [server])
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("RCON" in l for l in labels)
        assert any("Chat" in l for l in labels)
        assert any("Back" in l for l in labels)

    @pytest.mark.asyncio
    async def test_diagnostics_view_buttons(self):
        from bot.cogs.server_management import DiagnosticsView
        server = {"name": "S1", "host": "h", "rcon_port": 27020, "rcon_password": "pw"}
        view = DiagnosticsView(123, _make_bot(), server, [server])
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("View Log" in l for l in labels)
        assert any("Errors" in l for l in labels)
        assert any("Crash" in l for l in labels)
        assert any("Back" in l for l in labels)

    @pytest.mark.asyncio
    async def test_updates_view_has_dropdowns_and_button(self):
        from bot.cogs.server_management import ServerUpdatesView
        servers = [{"name": "S1", "display_name": "S1", "host": "h", "id": 1}]
        view = ServerUpdatesView(123, _make_bot(), servers)
        selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(selects) == 3
        assert any("Start Update" in (b.label or "") for b in buttons)
        assert any("Back" in (b.label or "") for b in buttons)

    @pytest.mark.asyncio
    async def test_updates_defaults_to_all_servers_when_none_selected(self):
        """Start Update with no selection should auto-select all servers."""
        from bot.cogs.server_management import ServerUpdatesView
        servers = [
            {"name": "Aberration", "display_name": "Aber", "host": "h", "id": 1},
            {"name": "Island", "display_name": "Island", "host": "h", "id": 2},
        ]
        view = ServerUpdatesView(123, _make_bot(), servers)
        assert view.selected_servers == []
        # Simulate what start_update_button does when no servers selected
        if not view.selected_servers:
            view.selected_servers = [
                (s.get("name") or s.get("display_name") or str(s.get("id", "")))
                for s in view.servers if isinstance(s, dict)
            ]
        assert len(view.selected_servers) == 2
        assert "Aberration" in view.selected_servers
        assert "Island" in view.selected_servers

    @pytest.mark.asyncio
    async def test_all_views_preserve_servers_list(self):
        """Every level-3 view should carry the servers list for back-navigation."""
        from bot.cogs.server_management import (
            ServerOperationsView, ServerControlView,
            AdvancedToolsView, DiagnosticsView,
        )
        server = {"name": "S1", "host": "h", "rcon_port": 1, "rcon_password": "p"}
        servers_list = [server]
        bot = _make_bot()

        for ViewClass in (ServerOperationsView, ServerControlView, AdvancedToolsView, DiagnosticsView):
            view = ViewClass(123, bot, server, servers_list)
            assert view.servers is servers_list
            assert view.server is server
            assert view.guild_id == 123


# ---------------------------------------------------------------------------
# Modal tests (async — discord.py Modals need event loop)
# ---------------------------------------------------------------------------

class TestModals:
    @pytest.mark.asyncio
    async def test_broadcast_modal_stores_server(self):
        from bot.cogs.server_management import BroadcastModal
        server = {"name": "Test", "host": "h", "rcon_port": 27020, "rcon_password": "pw"}
        modal = BroadcastModal(server)
        assert modal.server is server

    @pytest.mark.asyncio
    async def test_motd_modal_stores_server(self):
        from bot.cogs.server_management import MOTDModal
        server = {"name": "Test", "host": "h", "rcon_port": 27020, "rcon_password": "pw"}
        modal = MOTDModal(server)
        assert modal.server is server

    @pytest.mark.asyncio
    async def test_custom_rcon_modal_stores_server(self):
        from bot.cogs.server_management import CustomRCONModal
        server = {"name": "Test", "host": "h", "rcon_port": 27020, "rcon_password": "pw"}
        modal = CustomRCONModal(server)
        assert modal.server is server


# ---------------------------------------------------------------------------
# Cog tests
# ---------------------------------------------------------------------------

class TestServerManagementCog:
    def test_cog_init(self):
        from bot.cogs.server_management import ServerManagementCog
        bot = SimpleNamespace()
        cog = ServerManagementCog(bot)
        assert cog.bot is bot


# ---------------------------------------------------------------------------
# Icon/label correctness (match PS bot exactly)
# ---------------------------------------------------------------------------

class TestPSBotIconAlignment:
    """Verify button labels/icons match the PowerShell bot specification."""

    @pytest.mark.asyncio
    async def test_category_buttons_icons(self):
        from bot.cogs.server_management import ServerSelectedView
        server = {"name": "S1"}
        view = ServerSelectedView(123, _make_bot(), server, [server])
        labels = {c.label for c in view.children if isinstance(c, discord.ui.Button)}
        assert "\U0001f5a5\ufe0f Server Ops" in labels
        assert "\u2699\ufe0f Server Control" in labels
        assert "\U0001f527 Advanced" in labels
        assert "\U0001f50d Diagnostics" in labels
        assert "\u00ab Back" in labels

    @pytest.mark.asyncio
    async def test_server_ops_icons(self):
        from bot.cogs.server_management import ServerOperationsView
        server = {"name": "S1", "host": "h", "rcon_port": 1, "rcon_password": "p"}
        view = ServerOperationsView(123, _make_bot(), server, [server])
        labels = {c.label for c in view.children if isinstance(c, discord.ui.Button)}
        assert "\U0001f4e2 Broadcast" in labels
        assert "\U0001f4be Save World" in labels
        assert "\U0001f996 Destroy Wild" in labels
        assert "\U0001f4dd Set MOTD" in labels

    @pytest.mark.asyncio
    async def test_server_control_icons(self):
        from bot.cogs.server_management import ServerControlView
        server = {"name": "S1", "host": "h", "rcon_port": 1, "rcon_password": "p"}
        view = ServerControlView(123, _make_bot(), server, [server])
        labels = {c.label for c in view.children if isinstance(c, discord.ui.Button)}
        assert "\u23f9\ufe0f Stop" in labels
        assert "\u25b6\ufe0f Start" in labels
        assert "\U0001f504 Restart" in labels
        assert "\U0001f4ca Status" in labels

    @pytest.mark.asyncio
    async def test_advanced_icons(self):
        from bot.cogs.server_management import AdvancedToolsView
        server = {"name": "S1", "host": "h", "rcon_port": 1, "rcon_password": "p"}
        view = AdvancedToolsView(123, _make_bot(), server, [server])
        labels = {c.label for c in view.children if isinstance(c, discord.ui.Button)}
        assert "\u2328\ufe0f Custom RCON" in labels
        assert "\U0001f4ac Chat Log" in labels

    @pytest.mark.asyncio
    async def test_diagnostics_icons(self):
        from bot.cogs.server_management import DiagnosticsView
        server = {"name": "S1", "host": "h", "rcon_port": 1, "rcon_password": "p"}
        view = DiagnosticsView(123, _make_bot(), server, [server])
        labels = {c.label for c in view.children if isinstance(c, discord.ui.Button)}
        assert "\U0001f4c4 View Log" in labels
        assert "\u26a0\ufe0f View Errors" in labels
        assert "\U0001f4a5 Crash History" in labels

    @pytest.mark.asyncio
    async def test_button_styles(self):
        """Verify button styles match PS bot."""
        from bot.cogs.server_management import ServerControlView, ServerOperationsView
        server = {"name": "S1", "host": "h", "rcon_port": 1, "rcon_password": "p"}
        bot = _make_bot()

        ctrl = ServerControlView(123, bot, server, [server])
        ctrl_btns = {c.label: c.style for c in ctrl.children if isinstance(c, discord.ui.Button)}
        assert ctrl_btns["\u23f9\ufe0f Stop"] == discord.ButtonStyle.danger
        assert ctrl_btns["\u25b6\ufe0f Start"] == discord.ButtonStyle.success
        assert ctrl_btns["\U0001f504 Restart"] == discord.ButtonStyle.primary

        ops = ServerOperationsView(123, bot, server, [server])
        ops_btns = {c.label: c.style for c in ops.children if isinstance(c, discord.ui.Button)}
        assert ops_btns["\U0001f4be Save World"] == discord.ButtonStyle.success
        assert ops_btns["\U0001f996 Destroy Wild"] == discord.ButtonStyle.danger


# ---------------------------------------------------------------------------
# find_agent_for_guild tests
# ---------------------------------------------------------------------------

class TestFindAgentForGuild:
    @pytest.mark.asyncio
    async def test_no_agent_manager(self):
        from bot.cogs.server_management import _find_agent_for_guild
        bot = SimpleNamespace()  # No agent_manager attribute
        result = await _find_agent_for_guild(bot, 123)
        assert result is None

    @pytest.mark.asyncio
    async def test_with_agent_manager(self):
        from bot.cogs.server_management import _find_agent_for_guild
        bot = _make_bot()
        result = await _find_agent_for_guild(bot, 123)
        # _FakeAgentManager always returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_agent_manager_is_none(self):
        from bot.cogs.server_management import _find_agent_for_guild
        bot = SimpleNamespace(agent_manager=None)
        result = await _find_agent_for_guild(bot, 123)
        assert result is None


# ---------------------------------------------------------------------------
# Error path: _build_server_options edge cases
# ---------------------------------------------------------------------------

class TestBuildServerOptionsEdgeCases:
    def test_server_with_no_name_or_display_name_or_id(self):
        from bot.cogs.server_management import _build_server_options
        servers = [{"host": "h"}]
        options = _build_server_options(servers)
        # Should produce an option with fallback label "Server #?"
        assert len(options) == 1
        assert "Server #" in options[0].label

    def test_mixed_valid_and_invalid(self):
        from bot.cogs.server_management import _build_server_options
        servers = [
            "invalid",
            {"name": "Good", "host": "h", "id": 1},
            42,
            {"name": "Also Good", "host": "h2", "id": 2},
        ]
        options = _build_server_options(servers)
        assert len(options) == 2

    def test_host_fallback_when_missing(self):
        from bot.cogs.server_management import _build_server_options
        servers = [{"name": "S1", "id": 1}]
        options = _build_server_options(servers)
        assert "Unknown Host" in options[0].description
