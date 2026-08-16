"""
Tests for bot/cogs/remote_agent_gui.py — GUI classes and RemoteAgentGUI cog.

Tests cover:
- Module-level imports — all public classes importable
- AgentControlView construction: correct buttons present (Register, Status, Remove)
- AgentControlView button styles match design
- AgentControlView.interaction_check enforces original-user-only access
- AgentRegistrationModal has correct number of fields (4)
- AgentRegistrationModal field labels and custom_ids
- AgentRegistrationModal auth_key field is NOT pre-filled with a value
- Auth key NOT displayed in agent status embed — only "[configured]" shown
- RemoveAgentView construction: has a Select component
- RemoveAgentView.interaction_check enforces original-user-only access
- ServerControlView construction: has a server Select and disabled control buttons
- ServerControlView.enable_controls() enables all buttons
- ModInstallationModal has a CurseForge ID field
- ModInstallationModal stores selected_server and agent_manager references
- ServerSelect placeholder text and min/max values
- RemoteAgentGUI cog instantiation
- RemoteAgentGUI has /remote_management slash command
- Backward-compatibility alias RemoteServerManagementView = AgentControlView
- AgentRegistrationModal port field has default value "8080"

Uses real discord.py objects — no mocks.
All async tests use @pytest.mark.asyncio.
"""

import pytest
import asyncio
import inspect
from types import SimpleNamespace

import discord
from discord import SelectOption


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_manager():
    """Minimal RemoteAgentManager stand-in with no network access."""
    from bot.cogs.remote_agent import RemoteAgentManager
    return RemoteAgentManager()


def _make_user(user_id: int = 123456789):
    """Lightweight discord.User-like object."""
    user = SimpleNamespace()
    user.id = user_id
    return user


def _make_interaction(user_id: int = 123456789):
    """Minimal discord.Interaction-like object for interaction_check tests."""
    interaction = SimpleNamespace()
    interaction.user = _make_user(user_id)
    return interaction


# ---------------------------------------------------------------------------
# 1. Module imports
# ---------------------------------------------------------------------------

class TestImports:
    def test_import_agent_registration_modal(self):
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        assert AgentRegistrationModal is not None

    def test_import_agent_control_view(self):
        from bot.cogs.remote_agent_gui import AgentControlView
        assert AgentControlView is not None

    def test_import_remove_agent_view(self):
        from bot.cogs.remote_agent_gui import RemoveAgentView
        assert RemoveAgentView is not None

    def test_import_server_control_view(self):
        from bot.cogs.remote_agent_gui import ServerControlView
        assert ServerControlView is not None

    def test_import_mod_installation_modal(self):
        from bot.cogs.remote_agent_gui import ModInstallationModal
        assert ModInstallationModal is not None

    def test_import_server_select(self):
        from bot.cogs.remote_agent_gui import ServerSelect
        assert ServerSelect is not None

    def test_import_remote_agent_gui_cog(self):
        from bot.cogs.remote_agent_gui import RemoteAgentGUI
        assert RemoteAgentGUI is not None

    def test_backward_compat_alias(self):
        """RemoteServerManagementView must be an alias for AgentControlView."""
        from bot.cogs.remote_agent_gui import RemoteServerManagementView, AgentControlView
        assert RemoteServerManagementView is AgentControlView


# ---------------------------------------------------------------------------
# 2. AgentControlView — button structure
# ---------------------------------------------------------------------------

class TestAgentControlViewButtons:
    @pytest.mark.asyncio
    async def test_view_has_three_buttons(self):
        from bot.cogs.remote_agent_gui import AgentControlView
        mgr = _make_agent_manager()
        user = _make_user()
        view = AgentControlView(guild_id=1, user=user, agent_manager=mgr)
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 3

    @pytest.mark.asyncio
    async def test_view_has_register_button(self):
        from bot.cogs.remote_agent_gui import AgentControlView
        mgr = _make_agent_manager()
        view = AgentControlView(guild_id=1, user=_make_user(), agent_manager=mgr)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Register" in lbl for lbl in labels)

    @pytest.mark.asyncio
    async def test_view_has_status_button(self):
        from bot.cogs.remote_agent_gui import AgentControlView
        mgr = _make_agent_manager()
        view = AgentControlView(guild_id=1, user=_make_user(), agent_manager=mgr)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Status" in lbl for lbl in labels)

    @pytest.mark.asyncio
    async def test_view_has_remove_button(self):
        from bot.cogs.remote_agent_gui import AgentControlView
        mgr = _make_agent_manager()
        view = AgentControlView(guild_id=1, user=_make_user(), agent_manager=mgr)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Remove" in lbl for lbl in labels)

    @pytest.mark.asyncio
    async def test_register_button_style_is_primary(self):
        from bot.cogs.remote_agent_gui import AgentControlView
        mgr = _make_agent_manager()
        view = AgentControlView(guild_id=1, user=_make_user(), agent_manager=mgr)
        register_btn = next(
            (c for c in view.children if isinstance(c, discord.ui.Button) and "Register" in (c.label or "")),
            None,
        )
        assert register_btn is not None
        assert register_btn.style == discord.ButtonStyle.primary

    @pytest.mark.asyncio
    async def test_remove_button_style_is_danger(self):
        from bot.cogs.remote_agent_gui import AgentControlView
        mgr = _make_agent_manager()
        view = AgentControlView(guild_id=1, user=_make_user(), agent_manager=mgr)
        remove_btn = next(
            (c for c in view.children if isinstance(c, discord.ui.Button) and "Remove" in (c.label or "")),
            None,
        )
        assert remove_btn is not None
        assert remove_btn.style == discord.ButtonStyle.danger

    @pytest.mark.asyncio
    async def test_view_stores_guild_id(self):
        from bot.cogs.remote_agent_gui import AgentControlView
        mgr = _make_agent_manager()
        view = AgentControlView(guild_id=99, user=_make_user(), agent_manager=mgr)
        assert view.guild_id == 99

    @pytest.mark.asyncio
    async def test_view_stores_agent_manager(self):
        from bot.cogs.remote_agent_gui import AgentControlView
        mgr = _make_agent_manager()
        view = AgentControlView(guild_id=1, user=_make_user(), agent_manager=mgr)
        assert view.agent_manager is mgr


# ---------------------------------------------------------------------------
# 3. AgentControlView — interaction_check
# ---------------------------------------------------------------------------

class TestAgentControlViewInteractionCheck:
    @pytest.mark.asyncio
    async def test_interaction_check_allows_original_user(self):
        from bot.cogs.remote_agent_gui import AgentControlView
        user = _make_user(111)
        view = AgentControlView(guild_id=1, user=user, agent_manager=_make_agent_manager())
        interaction = _make_interaction(user_id=111)
        result = await view.interaction_check(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_interaction_check_blocks_other_users(self):
        from bot.cogs.remote_agent_gui import AgentControlView
        user = _make_user(111)
        view = AgentControlView(guild_id=1, user=user, agent_manager=_make_agent_manager())
        other_interaction = _make_interaction(user_id=999)
        result = await view.interaction_check(other_interaction)
        assert result is False


# ---------------------------------------------------------------------------
# 4. AgentRegistrationModal — fields
# ---------------------------------------------------------------------------

class TestAgentRegistrationModal:
    @pytest.mark.asyncio
    async def test_modal_has_four_fields(self):
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        modal = AgentRegistrationModal()
        assert len(modal.children) == 4

    @pytest.mark.asyncio
    async def test_modal_has_ip_field(self):
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        modal = AgentRegistrationModal()
        labels = [c.label for c in modal.children]
        assert any("IP" in lbl or "ip" in lbl.lower() for lbl in labels)

    @pytest.mark.asyncio
    async def test_modal_has_port_field(self):
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        modal = AgentRegistrationModal()
        labels = [c.label for c in modal.children]
        assert any("Port" in lbl or "port" in lbl.lower() for lbl in labels)

    @pytest.mark.asyncio
    async def test_modal_has_auth_key_field(self):
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        modal = AgentRegistrationModal()
        labels = [c.label for c in modal.children]
        assert any("Auth" in lbl or "Key" in lbl or "key" in lbl.lower() for lbl in labels)

    @pytest.mark.asyncio
    async def test_modal_has_display_name_field(self):
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        modal = AgentRegistrationModal()
        labels = [c.label for c in modal.children]
        assert any("Name" in lbl or "Display" in lbl for lbl in labels)

    @pytest.mark.asyncio
    async def test_port_field_has_default_8080(self):
        """The port field must ship with a default of '8080' to reduce friction."""
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        modal = AgentRegistrationModal()
        # The port field is at index 1 per source
        port_item = modal.children[1]
        assert port_item.default == "8080"

    @pytest.mark.asyncio
    async def test_ip_field_is_required(self):
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        modal = AgentRegistrationModal()
        ip_item = modal.children[0]
        assert ip_item.required is True

    @pytest.mark.asyncio
    async def test_auth_key_field_is_required(self):
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        modal = AgentRegistrationModal()
        auth_item = modal.children[2]
        assert auth_item.required is True

    @pytest.mark.asyncio
    async def test_display_name_field_is_optional(self):
        """Display Name must be optional — agents can exist without a friendly name."""
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        modal = AgentRegistrationModal()
        display_item = modal.children[3]
        assert display_item.required is False

    @pytest.mark.asyncio
    async def test_auth_key_field_has_no_pre_filled_value(self):
        """The auth key field must NOT be pre-populated (security: no default secret)."""
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        modal = AgentRegistrationModal()
        auth_item = modal.children[2]
        # default should be None or empty string — never a real key
        assert (auth_item.default is None) or (auth_item.default == "")

    @pytest.mark.asyncio
    async def test_modal_custom_ids(self):
        """Verify the custom_id values match what on_submit reads."""
        from bot.cogs.remote_agent_gui import AgentRegistrationModal
        modal = AgentRegistrationModal()
        custom_ids = [c.custom_id for c in modal.children]
        assert "agent_ip" in custom_ids
        assert "agent_port" in custom_ids
        assert "auth_key" in custom_ids
        assert "display_name" in custom_ids


# ---------------------------------------------------------------------------
# 5. Security: auth key NOT shown in status embed
# ---------------------------------------------------------------------------

class TestAuthKeyNotExposedInStatus:
    def test_status_embed_shows_configured_not_actual_key(self):
        """The handle_agent_status method must show '[configured]' not the real key.

        This verifies the security requirement that auth keys are never displayed
        in Discord messages where they could be screenshot or leaked.
        """
        # We inspect the source to confirm the auth key display pattern
        import inspect as ins
        from bot.cogs.remote_agent_gui import AgentControlView
        source = ins.getsource(AgentControlView.handle_agent_status)

        # The source must contain the safe placeholder string
        assert "[configured]" in source

        # The source must NOT contain a pattern that would render the raw auth_key
        # We verify that auth_key value from agent dict is not directly f-string'd
        # into the embed (it would be quoted: `{agent['auth_key']}` or similar)
        assert "agent['auth_key']" not in source
        assert 'agent["auth_key"]' not in source


# ---------------------------------------------------------------------------
# 6. RemoveAgentView — structure
# ---------------------------------------------------------------------------

class TestRemoveAgentView:
    @pytest.mark.asyncio
    async def test_remove_agent_view_has_select_component(self):
        from bot.cogs.remote_agent_gui import RemoveAgentView
        options = [SelectOption(label="10.0.0.1:8080", value="10.0.0.1:8080")]
        view = RemoveAgentView(
            guild_id=1,
            user=_make_user(),
            agent_manager=_make_agent_manager(),
            options=options,
        )
        selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
        assert len(selects) == 1

    @pytest.mark.asyncio
    async def test_remove_agent_view_select_has_options(self):
        from bot.cogs.remote_agent_gui import RemoveAgentView
        options = [
            SelectOption(label="10.0.0.1:8080", value="10.0.0.1:8080"),
            SelectOption(label="10.0.0.2:9090", value="10.0.0.2:9090"),
        ]
        view = RemoveAgentView(
            guild_id=1,
            user=_make_user(),
            agent_manager=_make_agent_manager(),
            options=options,
        )
        select_component = next(c for c in view.children if isinstance(c, discord.ui.Select))
        assert len(select_component.options) == 2

    @pytest.mark.asyncio
    async def test_remove_agent_view_selected_agent_id_starts_none(self):
        from bot.cogs.remote_agent_gui import RemoveAgentView
        options = [SelectOption(label="10.0.0.1:8080", value="10.0.0.1:8080")]
        view = RemoveAgentView(
            guild_id=1,
            user=_make_user(),
            agent_manager=_make_agent_manager(),
            options=options,
        )
        assert view.selected_agent_id is None

    @pytest.mark.asyncio
    async def test_remove_agent_view_interaction_check_allows_owner(self):
        from bot.cogs.remote_agent_gui import RemoveAgentView
        user = _make_user(555)
        options = [SelectOption(label="1.2.3.4:8080", value="1.2.3.4:8080")]
        view = RemoveAgentView(
            guild_id=1, user=user, agent_manager=_make_agent_manager(), options=options
        )
        interaction = _make_interaction(user_id=555)
        result = await view.interaction_check(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_remove_agent_view_interaction_check_blocks_others(self):
        from bot.cogs.remote_agent_gui import RemoveAgentView
        user = _make_user(555)
        options = [SelectOption(label="1.2.3.4:8080", value="1.2.3.4:8080")]
        view = RemoveAgentView(
            guild_id=1, user=user, agent_manager=_make_agent_manager(), options=options
        )
        other = _make_interaction(user_id=777)
        result = await view.interaction_check(other)
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_agent_view_timeout(self):
        """RemoveAgentView has a finite timeout to prevent stale interactions."""
        from bot.cogs.remote_agent_gui import RemoveAgentView

        agent_manager = _make_agent_manager()
        user = _make_user()
        options = [SelectOption(label="test:8080", value="test:8080")]

        view = RemoveAgentView(guild_id=123, user=user, agent_manager=agent_manager, options=options)
        assert view.timeout == 300


# ---------------------------------------------------------------------------
# 7. ServerControlView — construction
# ---------------------------------------------------------------------------

class TestServerControlView:
    @pytest.mark.asyncio
    async def test_server_control_view_has_select_component(self):
        from bot.cogs.remote_agent_gui import ServerControlView
        options = [SelectOption(label="MyServer", value="10.0.0.1:8080:MyServer")]
        view = ServerControlView(
            guild_id=1,
            user=_make_user(),
            agent_manager=_make_agent_manager(),
            server_options=options,
        )
        selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
        assert len(selects) == 1

    @pytest.mark.asyncio
    async def test_server_control_view_buttons_start_disabled(self):
        """All control buttons must be disabled until a server is selected."""
        from bot.cogs.remote_agent_gui import ServerControlView
        options = [SelectOption(label="MyServer", value="10.0.0.1:8080:MyServer")]
        view = ServerControlView(
            guild_id=1,
            user=_make_user(),
            agent_manager=_make_agent_manager(),
            server_options=options,
        )
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert all(btn.disabled for btn in buttons)

    @pytest.mark.asyncio
    async def test_server_control_view_enable_controls(self):
        """enable_controls() must flip all buttons to disabled=False."""
        from bot.cogs.remote_agent_gui import ServerControlView
        options = [SelectOption(label="MyServer", value="10.0.0.1:8080:MyServer")]
        view = ServerControlView(
            guild_id=1,
            user=_make_user(),
            agent_manager=_make_agent_manager(),
            server_options=options,
        )
        view.enable_controls()
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert all(not btn.disabled for btn in buttons)

    @pytest.mark.asyncio
    async def test_server_control_view_selected_server_starts_none(self):
        from bot.cogs.remote_agent_gui import ServerControlView
        options = [SelectOption(label="MyServer", value="10.0.0.1:8080:MyServer")]
        view = ServerControlView(
            guild_id=1,
            user=_make_user(),
            agent_manager=_make_agent_manager(),
            server_options=options,
        )
        assert view.selected_server is None

    @pytest.mark.asyncio
    async def test_server_control_view_interaction_check_allows_owner(self):
        from bot.cogs.remote_agent_gui import ServerControlView
        user = _make_user(321)
        options = [SelectOption(label="S", value="v")]
        view = ServerControlView(
            guild_id=1, user=user, agent_manager=_make_agent_manager(), server_options=options
        )
        interaction = _make_interaction(user_id=321)
        result = await view.interaction_check(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_server_control_view_has_seven_control_buttons(self):
        """ServerControlView has start/stop/restart/status/update/backup/mods = 7 buttons."""
        from bot.cogs.remote_agent_gui import ServerControlView
        options = [SelectOption(label="MyServer", value="10.0.0.1:8080:MyServer")]
        view = ServerControlView(
            guild_id=1,
            user=_make_user(),
            agent_manager=_make_agent_manager(),
            server_options=options,
        )
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 7


# ---------------------------------------------------------------------------
# 8. ModInstallationModal — construction
# ---------------------------------------------------------------------------

class TestModInstallationModal:
    @pytest.mark.asyncio
    async def test_modal_has_curseforge_id_field(self):
        from bot.cogs.remote_agent_gui import ModInstallationModal
        modal = ModInstallationModal(selected_server="1.2.3.4:8080:MyServer", agent_manager=_make_agent_manager())
        assert len(modal.children) == 1
        assert modal.children[0].custom_id == "curseforge_id"

    @pytest.mark.asyncio
    async def test_modal_stores_selected_server(self):
        from bot.cogs.remote_agent_gui import ModInstallationModal
        modal = ModInstallationModal(selected_server="1.2.3.4:8080:MyServer", agent_manager=_make_agent_manager())
        assert modal.selected_server == "1.2.3.4:8080:MyServer"

    @pytest.mark.asyncio
    async def test_modal_stores_agent_manager(self):
        from bot.cogs.remote_agent_gui import ModInstallationModal
        mgr = _make_agent_manager()
        modal = ModInstallationModal(selected_server="1.2.3.4:8080:MyServer", agent_manager=mgr)
        assert modal.agent_manager is mgr

    @pytest.mark.asyncio
    async def test_modal_curseforge_field_is_required(self):
        from bot.cogs.remote_agent_gui import ModInstallationModal
        modal = ModInstallationModal(selected_server="1.2.3.4:8080:MyServer", agent_manager=_make_agent_manager())
        assert modal.children[0].required is True


# ---------------------------------------------------------------------------
# 9. ServerSelect — construction
# ---------------------------------------------------------------------------

class TestServerSelect:
    @pytest.mark.asyncio
    async def test_server_select_placeholder(self):
        from bot.cogs.remote_agent_gui import ServerSelect
        options = [SelectOption(label="Server1", value="v1")]
        select = ServerSelect(options=options)
        assert select.placeholder is not None
        assert len(select.placeholder) > 0

    @pytest.mark.asyncio
    async def test_server_select_min_max_values(self):
        from bot.cogs.remote_agent_gui import ServerSelect
        options = [SelectOption(label="Server1", value="v1")]
        select = ServerSelect(options=options)
        assert select.min_values == 1
        assert select.max_values == 1

    @pytest.mark.asyncio
    async def test_server_select_custom_id(self):
        from bot.cogs.remote_agent_gui import ServerSelect
        options = [SelectOption(label="Server1", value="v1")]
        select = ServerSelect(options=options)
        assert select.custom_id == "server_select"


# ---------------------------------------------------------------------------
# 10. RemoteAgentGUI cog — instantiation and commands
# ---------------------------------------------------------------------------

class TestRemoteAgentGUICog:
    def test_cog_can_be_instantiated(self):
        from bot.cogs.remote_agent_gui import RemoteAgentGUI
        bot = SimpleNamespace()
        cog = RemoteAgentGUI(bot)
        assert cog.bot is bot

    def test_cog_has_remote_management_command(self):
        from bot.cogs.remote_agent_gui import RemoteAgentGUI
        bot = SimpleNamespace()
        cog = RemoteAgentGUI(bot)
        command_names = [cmd.name for cmd in cog.get_app_commands()]
        assert "remote_management" in command_names

    def test_setup_function_exists(self):
        import bot.cogs.remote_agent_gui as module
        assert hasattr(module, "setup")
        assert inspect.iscoroutinefunction(module.setup)

    def test_cog_is_commands_cog_subclass(self):
        from bot.cogs.remote_agent_gui import RemoteAgentGUI
        from discord.ext import commands
        assert issubclass(RemoteAgentGUI, commands.Cog)


# ---------------------------------------------------------------------------
# 11. Agent control view timeout
# ---------------------------------------------------------------------------

class TestViewTimeouts:
    @pytest.mark.asyncio
    async def test_agent_control_view_timeout(self):
        """AgentControlView has a finite timeout to prevent stale interactions."""
        from bot.cogs.remote_agent_gui import AgentControlView

        agent_manager = _make_agent_manager()
        user = _make_user()

        view = AgentControlView(guild_id=123, user=user, agent_manager=agent_manager)
        assert view.timeout == 300
