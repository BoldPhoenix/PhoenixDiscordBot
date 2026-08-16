"""
Tests for bot/cogs/server_service.py — ServerServiceCog and modal/view classes.

Tests cover:
- Module-level imports — all public classes importable
- MAP_CHOICES: correct length and expected maps present
- CreateServerServiceModal: field count ≤ 5, labels, __init__ stores attributes
- CreateServerServiceModal.on_submit: success path, agent error path, ValueError path
- UpdateServerConfigModal: field count ≤ 5, labels, on_submit success/no-changes/error
- DeleteServerConfirmView: buttons present, confirm success/error, cancel path
- ServerServiceCog: instantiation, commands present, get_agent_for_guild with/without manager
- All commands are coroutine functions
- setup() function exists

Uses real discord.py objects where possible — no mocks.
All async tests use @pytest.mark.asyncio.
"""

import pytest
import asyncio
import inspect
from types import SimpleNamespace

import discord
from discord.ext import commands


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bot():
    """Minimal bot-like object with agent_manager=None."""
    bot = SimpleNamespace()
    bot.agent_manager = None
    bot.guilds = []
    return bot


def _make_agent_manager(**results):
    """
    Fake agent manager that returns canned results for service operations.
    results: mapping of method_name -> return_value (passed to awaitable).
    """
    mgr = SimpleNamespace()

    async def _make_async(value):
        return value

    for method, retval in results.items():
        setattr(mgr, method, lambda v=retval, **_kw: _make_async(v))

    # Default: methods return success
    default_success = {"error": None, "data": {"service_name": "PhoenixARK_TheIsland"}}
    for method in [
        "create_server_service",
        "update_server_config",
        "delete_server_service",
        "read_server_config",
        "list_server_services",
        "start_ark_service",
        "stop_ark_service",
        "restart_ark_service",
    ]:
        if not hasattr(mgr, method):
            setattr(mgr, method, lambda v=default_success, **_kw: _make_async(v))

    async def get_connected_agent_for_guild(guild_id):
        return "192.168.1.1:8080"

    mgr.get_connected_agent_for_guild = get_connected_agent_for_guild
    return mgr


def _make_interaction(response_sent=None):
    """Fake discord.Interaction that captures calls without network I/O."""
    interaction = SimpleNamespace()

    sent_messages = response_sent if response_sent is not None else []
    deferred = []
    modals_sent = []
    followup_messages = []

    class FakeResponse:
        async def defer(self, ephemeral=False):
            deferred.append(ephemeral)

        async def send_message(self, content=None, **kwargs):
            sent_messages.append(content)

        async def send_modal(self, modal):
            modals_sent.append(modal)

        async def edit_message(self, content=None, **kwargs):
            sent_messages.append(content)

    class FakeFollowup:
        async def send(self, content=None, **kwargs):
            followup_messages.append(content)

    interaction.response = FakeResponse()
    interaction.followup = FakeFollowup()
    interaction.guild_id = 123456789
    interaction.user = SimpleNamespace(id=987654321)
    interaction._deferred = deferred
    interaction._sent = sent_messages
    interaction._modals = modals_sent
    interaction._followup = followup_messages
    return interaction


# ---------------------------------------------------------------------------
# 1. Module imports
# ---------------------------------------------------------------------------

class TestImports:
    def test_import_server_service_cog(self):
        from bot.cogs.server_service import ServerServiceCog
        assert ServerServiceCog is not None

    def test_import_create_server_service_modal(self):
        from bot.cogs.server_service import CreateServerServiceModal
        assert CreateServerServiceModal is not None

    def test_import_update_server_config_modal(self):
        from bot.cogs.server_service import UpdateServerConfigModal
        assert UpdateServerConfigModal is not None

    def test_import_delete_server_confirm_view(self):
        from bot.cogs.server_service import DeleteServerConfirmView
        assert DeleteServerConfirmView is not None

    def test_import_map_choices(self):
        from bot.cogs.server_service import MAP_CHOICES
        assert MAP_CHOICES is not None

    def test_setup_function_exists(self):
        import bot.cogs.server_service as mod
        assert hasattr(mod, "setup")
        assert asyncio.iscoroutinefunction(mod.setup)


# ---------------------------------------------------------------------------
# 2. MAP_CHOICES
# ---------------------------------------------------------------------------

class TestMapChoices:
    def test_map_choices_count(self):
        from bot.cogs.server_service import MAP_CHOICES
        assert len(MAP_CHOICES) == 11

    def test_map_choices_includes_the_island(self):
        from bot.cogs.server_service import MAP_CHOICES
        values = [c.value for c in MAP_CHOICES]
        assert "TheIsland" in values

    def test_map_choices_includes_aberration(self):
        from bot.cogs.server_service import MAP_CHOICES
        values = [c.value for c in MAP_CHOICES]
        assert "Aberration_P" in values

    def test_map_choices_includes_fjordur(self):
        from bot.cogs.server_service import MAP_CHOICES
        values = [c.value for c in MAP_CHOICES]
        assert "Fjordur" in values

    def test_map_choices_are_app_commands_choice(self):
        from bot.cogs.server_service import MAP_CHOICES
        from discord import app_commands
        for choice in MAP_CHOICES:
            assert isinstance(choice, app_commands.Choice)


# ---------------------------------------------------------------------------
# 3. CreateServerServiceModal
# ---------------------------------------------------------------------------

class TestCreateServerServiceModal:
    def _make_modal(self, **kwargs):
        from bot.cogs.server_service import CreateServerServiceModal
        defaults = dict(
            cog=SimpleNamespace(agent_manager=None),
            agent_id="192.168.1.1:8080",
            map_name="TheIsland",
            server_path="D:\\ARK\\Servers\\Island",
            steamcmd_path="D:\\SteamCMD",
            max_players=70,
            rcon_password="secret",
        )
        defaults.update(kwargs)
        return CreateServerServiceModal(**defaults)

    def test_modal_has_five_or_fewer_text_inputs(self):
        """Discord modals only support 5 TextInput fields maximum."""
        from bot.cogs.server_service import CreateServerServiceModal
        text_inputs = [
            v for v in vars(CreateServerServiceModal).values()
            if isinstance(v, discord.ui.TextInput)
        ]
        assert len(text_inputs) <= 5, (
            f"Discord only allows 5 TextInput fields, found {len(text_inputs)}"
        )

    def test_modal_has_server_name_field(self):
        from bot.cogs.server_service import CreateServerServiceModal
        assert hasattr(CreateServerServiceModal, "server_name")
        assert isinstance(CreateServerServiceModal.server_name, discord.ui.TextInput)

    def test_modal_has_display_name_field(self):
        from bot.cogs.server_service import CreateServerServiceModal
        assert hasattr(CreateServerServiceModal, "display_name")
        assert isinstance(CreateServerServiceModal.display_name, discord.ui.TextInput)

    def test_modal_has_game_port_field(self):
        from bot.cogs.server_service import CreateServerServiceModal
        assert hasattr(CreateServerServiceModal, "game_port")

    def test_modal_has_rcon_port_field(self):
        from bot.cogs.server_service import CreateServerServiceModal
        assert hasattr(CreateServerServiceModal, "rcon_port")

    def test_modal_rcon_password_not_a_text_input_field(self):
        """rcon_password moved to slash command param — must NOT be a TextInput on the modal."""
        from bot.cogs.server_service import CreateServerServiceModal
        # It should NOT exist as a class-level TextInput
        val = vars(CreateServerServiceModal).get("rcon_password")
        assert not isinstance(val, discord.ui.TextInput), (
            "rcon_password should not be a TextInput field (exceeds 5-field limit)"
        )

    def test_init_stores_agent_id(self):
        modal = self._make_modal()
        assert modal.agent_id == "192.168.1.1:8080"

    def test_init_stores_map_name(self):
        modal = self._make_modal(map_name="Fjordur")
        assert modal.map_name == "Fjordur"

    def test_init_stores_rcon_password(self):
        modal = self._make_modal(rcon_password="mypassword")
        assert modal.rcon_password == "mypassword"

    def test_init_stores_max_players(self):
        modal = self._make_modal(max_players=100)
        assert modal.max_players == 100

    def test_on_submit_is_coroutine(self):
        from bot.cogs.server_service import CreateServerServiceModal
        assert asyncio.iscoroutinefunction(CreateServerServiceModal.on_submit)

    @pytest.mark.asyncio
    async def test_on_submit_success(self):
        """on_submit sends success message when agent returns no error."""
        from bot.cogs.server_service import CreateServerServiceModal

        mgr = _make_agent_manager()
        cog = SimpleNamespace(agent_manager=mgr)

        modal = self._make_modal(cog=cog)
        # Set _value on the discord.ui.TextInput instances (str(textinput) returns _value)
        modal.server_name._value = "TheIsland"
        modal.display_name._value = "The Island"
        modal.game_port._value = "7777"
        modal.query_port._value = "27015"
        modal.rcon_port._value = "27020"

        interaction = _make_interaction()
        await modal.on_submit(interaction)
        assert len(interaction._followup) == 1
        assert "✅" in interaction._followup[0]

    @pytest.mark.asyncio
    async def test_on_submit_agent_error(self):
        """on_submit sends error message when agent returns an error."""
        from bot.cogs.server_service import CreateServerServiceModal

        async def fail_create(**_kw):
            return {"error": "Service already exists"}

        mgr = _make_agent_manager()
        mgr.create_server_service = fail_create
        cog = SimpleNamespace(agent_manager=mgr)

        modal = self._make_modal(cog=cog)
        modal.server_name._value = "TheIsland"
        modal.display_name._value = "The Island"
        modal.game_port._value = "7777"
        modal.query_port._value = "27015"
        modal.rcon_port._value = "27020"

        interaction = _make_interaction()
        await modal.on_submit(interaction)
        assert len(interaction._followup) == 1
        assert "❌" in interaction._followup[0]


# ---------------------------------------------------------------------------
# 4. UpdateServerConfigModal
# ---------------------------------------------------------------------------

class TestUpdateServerConfigModal:
    def _make_modal(self, **kwargs):
        from bot.cogs.server_service import UpdateServerConfigModal
        defaults = dict(
            cog=SimpleNamespace(agent_manager=None),
            agent_id="192.168.1.1:8080",
            server_name="TheIsland",
            current_config={},
        )
        defaults.update(kwargs)
        return UpdateServerConfigModal(**defaults)

    def test_modal_has_five_or_fewer_text_inputs(self):
        from bot.cogs.server_service import UpdateServerConfigModal
        text_inputs = [
            v for v in vars(UpdateServerConfigModal).values()
            if isinstance(v, discord.ui.TextInput)
        ]
        assert len(text_inputs) <= 5

    def test_modal_has_display_name_field(self):
        from bot.cogs.server_service import UpdateServerConfigModal
        assert hasattr(UpdateServerConfigModal, "display_name")

    def test_modal_has_max_players_field(self):
        from bot.cogs.server_service import UpdateServerConfigModal
        assert hasattr(UpdateServerConfigModal, "max_players")

    def test_modal_has_mods_field(self):
        from bot.cogs.server_service import UpdateServerConfigModal
        assert hasattr(UpdateServerConfigModal, "mods")

    def test_modal_has_cluster_id_field(self):
        from bot.cogs.server_service import UpdateServerConfigModal
        assert hasattr(UpdateServerConfigModal, "cluster_id")

    def test_init_stores_server_name(self):
        modal = self._make_modal(server_name="Fjordur")
        assert modal.server_name == "Fjordur"

    def test_init_stores_agent_id(self):
        modal = self._make_modal(agent_id="10.0.0.1:8080")
        assert modal.agent_id == "10.0.0.1:8080"

    def test_init_prefills_display_name_from_config(self):
        from bot.cogs.server_service import UpdateServerConfigModal
        modal = self._make_modal(current_config={"display_name": "My Island"})
        assert modal.display_name.default == "My Island"

    def test_init_prefills_max_players_from_config(self):
        from bot.cogs.server_service import UpdateServerConfigModal
        modal = self._make_modal(current_config={"max_players": 100})
        assert modal.max_players.default == "100"

    def test_on_submit_is_coroutine(self):
        from bot.cogs.server_service import UpdateServerConfigModal
        assert asyncio.iscoroutinefunction(UpdateServerConfigModal.on_submit)

    @pytest.mark.asyncio
    async def test_on_submit_no_changes(self):
        """on_submit sends 'No changes' when all fields are blank."""
        from bot.cogs.server_service import UpdateServerConfigModal
        cog = SimpleNamespace(agent_manager=_make_agent_manager())
        modal = self._make_modal(cog=cog)

        # All optional fields left blank (default _value is None → str() returns "")
        modal.display_name._value = None
        modal.max_players._value = None
        modal.mods._value = None
        modal.cluster_id._value = None

        interaction = _make_interaction()
        await modal.on_submit(interaction)
        assert len(interaction._followup) == 1
        assert "No changes" in interaction._followup[0]

    @pytest.mark.asyncio
    async def test_on_submit_invalid_max_players(self):
        """on_submit sends error when max_players is non-numeric."""
        from bot.cogs.server_service import UpdateServerConfigModal
        cog = SimpleNamespace(agent_manager=_make_agent_manager())
        modal = self._make_modal(cog=cog)

        modal.display_name._value = None
        modal.max_players._value = "notanumber"
        modal.mods._value = None
        modal.cluster_id._value = None

        interaction = _make_interaction()
        await modal.on_submit(interaction)
        assert len(interaction._followup) == 1
        assert "❌" in interaction._followup[0]

    @pytest.mark.asyncio
    async def test_on_submit_success(self):
        """on_submit sends success message when agent confirms update."""
        from bot.cogs.server_service import UpdateServerConfigModal
        cog = SimpleNamespace(agent_manager=_make_agent_manager())
        modal = self._make_modal(cog=cog)

        modal.display_name._value = "New Name"
        modal.max_players._value = None
        modal.mods._value = None
        modal.cluster_id._value = None

        interaction = _make_interaction()
        await modal.on_submit(interaction)
        assert len(interaction._followup) == 1
        assert "✅" in interaction._followup[0]

    @pytest.mark.asyncio
    async def test_on_submit_agent_error(self):
        """on_submit sends error when agent returns an error."""
        from bot.cogs.server_service import UpdateServerConfigModal

        async def fail_update(agent_id, server_name, **_kw):
            return {"error": "Server not found"}

        mgr = _make_agent_manager()
        mgr.update_server_config = fail_update
        cog = SimpleNamespace(agent_manager=mgr)
        modal = self._make_modal(cog=cog)

        modal.display_name._value = "Changed"
        modal.max_players._value = None
        modal.mods._value = None
        modal.cluster_id._value = None

        interaction = _make_interaction()
        await modal.on_submit(interaction)
        assert "❌" in interaction._followup[0]


# ---------------------------------------------------------------------------
# 5. DeleteServerConfirmView
# ---------------------------------------------------------------------------

class TestDeleteServerConfirmView:
    def _make_view(self, **kwargs):
        from bot.cogs.server_service import DeleteServerConfirmView
        defaults = dict(
            cog=SimpleNamespace(agent_manager=_make_agent_manager()),
            agent_id="192.168.1.1:8080",
            server_name="TheIsland",
            service_name="PhoenixARK_TheIsland",
        )
        defaults.update(kwargs)
        return DeleteServerConfirmView(**defaults)

    def test_view_has_confirm_delete_button(self):
        view = self._make_view()
        button_labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert "Delete Service" in button_labels

    def test_view_has_cancel_button(self):
        view = self._make_view()
        button_labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert "Cancel" in button_labels

    def test_view_confirm_button_is_danger_style(self):
        view = self._make_view()
        for c in view.children:
            if isinstance(c, discord.ui.Button) and c.label == "Delete Service":
                assert c.style == discord.ButtonStyle.danger

    def test_view_inherits_discord_view(self):
        from bot.cogs.server_service import DeleteServerConfirmView
        assert issubclass(DeleteServerConfirmView, discord.ui.View)

    @pytest.mark.asyncio
    async def test_confirm_delete_success(self):
        """confirm_delete callback sends success message when agent returns no error."""
        view = self._make_view()
        interaction = _make_interaction()
        # Button.callback is a bound _ItemCallback(interaction) → call with just interaction
        await view.confirm_delete.callback(interaction)
        assert len(interaction._followup) == 1
        assert "✅" in interaction._followup[0]

    @pytest.mark.asyncio
    async def test_confirm_delete_agent_error(self):
        """confirm_delete sends error when agent returns an error."""
        async def fail_delete(agent_id, server_name, service_name):
            return {"error": "Service not found"}

        mgr = _make_agent_manager()
        mgr.delete_server_service = fail_delete
        view = self._make_view(cog=SimpleNamespace(agent_manager=mgr))

        interaction = _make_interaction()
        await view.confirm_delete.callback(interaction)
        assert "❌" in interaction._followup[0]

    @pytest.mark.asyncio
    async def test_cancel_button_edits_message(self):
        """cancel button edits the message to show cancellation."""
        view = self._make_view()
        interaction = _make_interaction()
        await view.cancel.callback(interaction)
        assert len(interaction._sent) == 1
        assert "cancel" in interaction._sent[0].lower()


# ---------------------------------------------------------------------------
# 6. ServerServiceCog
# ---------------------------------------------------------------------------

class TestServerServiceCogInit:
    def test_cog_instantiation(self):
        from bot.cogs.server_service import ServerServiceCog
        bot = _make_bot()
        cog = ServerServiceCog(bot)
        assert cog is not None

    def test_cog_stores_bot(self):
        from bot.cogs.server_service import ServerServiceCog
        bot = _make_bot()
        cog = ServerServiceCog(bot)
        assert cog.bot is bot

    def test_cog_inherits_commands_cog(self):
        from bot.cogs.server_service import ServerServiceCog
        assert issubclass(ServerServiceCog, commands.Cog)

    def test_agent_manager_none_when_bot_has_none(self):
        from bot.cogs.server_service import ServerServiceCog
        bot = _make_bot()
        cog = ServerServiceCog(bot)
        assert cog.agent_manager is None

    def test_agent_manager_property_reads_from_bot(self):
        from bot.cogs.server_service import ServerServiceCog
        bot = _make_bot()
        mgr = _make_agent_manager()
        bot.agent_manager = mgr
        cog = ServerServiceCog(bot)
        assert cog.agent_manager is mgr


class TestServerServiceCogCommands:
    def _make_cog(self):
        from bot.cogs.server_service import ServerServiceCog
        bot = _make_bot()
        bot.agent_manager = _make_agent_manager()
        return ServerServiceCog(bot)

    def test_create_service_command_exists(self):
        cog = self._make_cog()
        assert hasattr(cog, "create_service")

    def test_update_service_command_exists(self):
        cog = self._make_cog()
        assert hasattr(cog, "update_service")

    def test_delete_service_command_exists(self):
        cog = self._make_cog()
        assert hasattr(cog, "delete_service")

    def test_view_service_config_command_exists(self):
        cog = self._make_cog()
        assert hasattr(cog, "view_service_config")

    def test_list_services_command_exists(self):
        cog = self._make_cog()
        assert hasattr(cog, "list_services")

    def test_start_service_command_exists(self):
        cog = self._make_cog()
        assert hasattr(cog, "start_service")

    def test_stop_service_command_exists(self):
        cog = self._make_cog()
        assert hasattr(cog, "stop_service")

    def test_restart_service_command_exists(self):
        cog = self._make_cog()
        assert hasattr(cog, "restart_service")

    def test_create_service_is_coroutine(self):
        from bot.cogs.server_service import ServerServiceCog
        cb = ServerServiceCog.create_service.callback
        assert asyncio.iscoroutinefunction(cb)

    def test_update_service_is_coroutine(self):
        from bot.cogs.server_service import ServerServiceCog
        cb = ServerServiceCog.update_service.callback
        assert asyncio.iscoroutinefunction(cb)

    def test_delete_service_is_coroutine(self):
        from bot.cogs.server_service import ServerServiceCog
        cb = ServerServiceCog.delete_service.callback
        assert asyncio.iscoroutinefunction(cb)

    def test_list_services_is_coroutine(self):
        from bot.cogs.server_service import ServerServiceCog
        cb = ServerServiceCog.list_services.callback
        assert asyncio.iscoroutinefunction(cb)


class TestGetAgentForGuild:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_agent_manager(self):
        from bot.cogs.server_service import ServerServiceCog
        bot = _make_bot()
        cog = ServerServiceCog(bot)
        result = await cog.get_agent_for_guild(123456789)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_agent_id_when_connected(self):
        from bot.cogs.server_service import ServerServiceCog
        bot = _make_bot()
        bot.agent_manager = _make_agent_manager()
        cog = ServerServiceCog(bot)
        result = await cog.get_agent_for_guild(123456789)
        assert result == "192.168.1.1:8080"


class TestCreateServiceCommandFlow:
    @pytest.mark.asyncio
    async def test_no_agent_sends_error_not_modal(self):
        """When no agent is connected, command sends error message (not a modal)."""
        from bot.cogs.server_service import ServerServiceCog
        bot = _make_bot()
        # agent_manager exists but returns None for get_connected_agent_for_guild
        mgr = SimpleNamespace()
        async def no_agent(guild_id):
            return None
        mgr.get_connected_agent_for_guild = no_agent
        bot.agent_manager = mgr
        cog = ServerServiceCog(bot)

        interaction = _make_interaction()
        await cog.create_service.callback(
            cog, interaction,
            map_name="TheIsland",
            server_path="D:\\ARK",
            steamcmd_path="D:\\SteamCMD",
            rcon_password="secret",
            max_players=70,
        )
        assert len(interaction._sent) == 1
        assert "❌" in interaction._sent[0]
        assert len(interaction._modals) == 0

    @pytest.mark.asyncio
    async def test_with_agent_sends_modal(self):
        """When agent is connected, command sends modal (not a plain message)."""
        from bot.cogs.server_service import ServerServiceCog
        bot = _make_bot()
        bot.agent_manager = _make_agent_manager()
        cog = ServerServiceCog(bot)

        interaction = _make_interaction()
        await cog.create_service.callback(
            cog, interaction,
            map_name="TheIsland",
            server_path="D:\\ARK",
            steamcmd_path="D:\\SteamCMD",
            rcon_password="secret",
            max_players=70,
        )
        assert len(interaction._modals) == 1
        assert len(interaction._sent) == 0

    @pytest.mark.asyncio
    async def test_update_service_no_agent_sends_error(self):
        """update_service with no agent sends error, not modal."""
        from bot.cogs.server_service import ServerServiceCog
        bot = _make_bot()
        mgr = SimpleNamespace()
        async def no_agent(guild_id):
            return None
        mgr.get_connected_agent_for_guild = no_agent
        bot.agent_manager = mgr
        cog = ServerServiceCog(bot)

        interaction = _make_interaction()
        await cog.update_service.callback(cog, interaction, server_name="TheIsland")
        assert len(interaction._sent) == 1
        assert "❌" in interaction._sent[0]
        assert len(interaction._modals) == 0

    @pytest.mark.asyncio
    async def test_update_service_with_agent_sends_modal(self):
        """update_service with agent connected sends modal directly."""
        from bot.cogs.server_service import ServerServiceCog
        bot = _make_bot()
        bot.agent_manager = _make_agent_manager()
        cog = ServerServiceCog(bot)

        interaction = _make_interaction()
        await cog.update_service.callback(cog, interaction, server_name="TheIsland")
        assert len(interaction._modals) == 1
        assert len(interaction._sent) == 0
