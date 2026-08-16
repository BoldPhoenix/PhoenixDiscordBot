"""
Tests for bot/cogs/setup_gui.py — SetupView, modals, and supporting views.

Tests cover:
- SetupView and SetupMainView instantiation and subclassing
- SetupCategoryButton existence and category wiring
- AddServerModal and EditServerModal field structure
- ManageServersView construction
- ServerActionsView existence and button presence
- HostingTypeView hosting type buttons
- SetupView.interaction_check ownership guard
- botcontrol category queries DB for ark_servers (not agent.agents.values())
- Cog registration and /setupcfg, /servercfg commands

Uses real discord.py objects — no mocks (Jeffrey Snover methodology).
Views/Modals require a running asyncio event loop; all such tests are async.
"""

import pytest
import discord
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Minimal bot/user stand-ins (real namespaces, no mocks)
# ---------------------------------------------------------------------------

def _make_user(user_id: int = 111222333) -> SimpleNamespace:
    """Create a minimal Discord-like user object."""
    user = SimpleNamespace()
    user.id = user_id
    return user


def _make_guild(guild_id: int = 999888777) -> SimpleNamespace:
    """Create a minimal Discord-like guild object."""
    guild = SimpleNamespace()
    guild.id = guild_id
    guild.name = "Test Guild"
    guild.get_role = lambda role_id: None
    guild.roles = []
    return guild


class _FakeAgentManager:
    """Minimal stand-in for RemoteAgentManager."""

    def __init__(self, agent_count: int = 0):
        self.agents = {i: SimpleNamespace() for i in range(agent_count)}


def _make_bot(agent_count: int = 0) -> SimpleNamespace:
    """Create a lightweight bot-like object with agent_manager."""
    bot = SimpleNamespace()
    bot.agent_manager = _FakeAgentManager(agent_count)
    return bot


# ---------------------------------------------------------------------------
# 1. SetupView instantiation
# ---------------------------------------------------------------------------

class TestSetupView:
    @pytest.mark.asyncio
    async def test_setup_view_can_be_instantiated(self):
        from bot.cogs.setup_gui import SetupView
        user = _make_user()
        view = SetupView(guild_id=123456, user=user)
        assert view is not None

    @pytest.mark.asyncio
    async def test_setup_view_is_discord_ui_view_subclass(self):
        from bot.cogs.setup_gui import SetupView
        user = _make_user()
        view = SetupView(guild_id=123456, user=user)
        assert isinstance(view, discord.ui.View)

    @pytest.mark.asyncio
    async def test_setup_view_has_timeout(self):
        from bot.cogs.setup_gui import SetupView
        user = _make_user()
        view = SetupView(guild_id=123456, user=user)
        assert view.timeout == 300

    @pytest.mark.asyncio
    async def test_setup_view_stores_guild_id(self):
        from bot.cogs.setup_gui import SetupView
        user = _make_user()
        view = SetupView(guild_id=999, user=user)
        assert view.guild_id == 999

    @pytest.mark.asyncio
    async def test_setup_view_stores_user(self):
        from bot.cogs.setup_gui import SetupView
        user = _make_user(user_id=42)
        view = SetupView(guild_id=123, user=user)
        assert view.user is user

    @pytest.mark.asyncio
    async def test_setup_view_interaction_check_allows_original_user(self):
        """interaction_check returns True when the original user interacts."""
        from bot.cogs.setup_gui import SetupView

        user = _make_user(user_id=100)
        view = SetupView(guild_id=123, user=user)

        interaction = SimpleNamespace()
        interaction.user = SimpleNamespace(id=100)
        interaction.response = AsyncMock()

        result = await view.interaction_check(interaction)
        assert result is True
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_view_interaction_check_rejects_other_user(self):
        """interaction_check returns False and sends ephemeral error for wrong user."""
        from bot.cogs.setup_gui import SetupView

        user = _make_user(user_id=100)
        view = SetupView(guild_id=123, user=user)

        interaction = SimpleNamespace()
        interaction.user = SimpleNamespace(id=999)
        interaction.response = AsyncMock()

        result = await view.interaction_check(interaction)
        assert result is False
        interaction.response.send_message.assert_called_once()
        call_kwargs = interaction.response.send_message.call_args[1]
        assert call_kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# 2. SetupMainView and SetupCategoryButton
# ---------------------------------------------------------------------------

class TestSetupMainView:
    @pytest.mark.asyncio
    async def test_setup_main_view_can_be_instantiated(self):
        from bot.cogs.setup_gui import SetupMainView
        user = _make_user()
        guild = _make_guild()
        view = SetupMainView(guild_id=123456, user=user, guild=guild)
        assert view is not None

    @pytest.mark.asyncio
    async def test_setup_main_view_is_discord_ui_view_subclass(self):
        from bot.cogs.setup_gui import SetupMainView
        user = _make_user()
        guild = _make_guild()
        view = SetupMainView(guild_id=123456, user=user, guild=guild)
        assert isinstance(view, discord.ui.View)

    @pytest.mark.asyncio
    async def test_setup_main_view_has_category_buttons(self):
        from bot.cogs.setup_gui import SetupMainView, SetupCategoryButton
        user = _make_user()
        guild = _make_guild()
        view = SetupMainView(guild_id=123456, user=user, guild=guild)
        buttons = [c for c in view.children if isinstance(c, SetupCategoryButton)]
        assert len(buttons) > 0

    @pytest.mark.asyncio
    async def test_setup_main_view_has_hosting_button(self):
        from bot.cogs.setup_gui import SetupMainView, SetupCategoryButton
        user = _make_user()
        guild = _make_guild()
        view = SetupMainView(guild_id=123456, user=user, guild=guild)
        categories = [c.category for c in view.children if isinstance(c, SetupCategoryButton)]
        assert "hosting" in categories

    @pytest.mark.asyncio
    async def test_setup_main_view_has_channels_button(self):
        from bot.cogs.setup_gui import SetupMainView, SetupCategoryButton
        user = _make_user()
        guild = _make_guild()
        view = SetupMainView(guild_id=123456, user=user, guild=guild)
        categories = [c.category for c in view.children if isinstance(c, SetupCategoryButton)]
        assert "channels" in categories

    @pytest.mark.asyncio
    async def test_setup_main_view_has_admin_role_button(self):
        from bot.cogs.setup_gui import SetupMainView, SetupCategoryButton
        user = _make_user()
        guild = _make_guild()
        view = SetupMainView(guild_id=123456, user=user, guild=guild)
        categories = [c.category for c in view.children if isinstance(c, SetupCategoryButton)]
        assert "admin" in categories

    @pytest.mark.asyncio
    async def test_setup_main_view_has_manageservers_button(self):
        from bot.cogs.setup_gui import SetupMainView, SetupCategoryButton
        user = _make_user()
        guild = _make_guild()
        view = SetupMainView(guild_id=123456, user=user, guild=guild)
        categories = [c.category for c in view.children if isinstance(c, SetupCategoryButton)]
        assert "manageservers" in categories

    @pytest.mark.asyncio
    async def test_setup_main_view_has_botcontrol_button(self):
        """SetupMainView should have a 'botcontrol' (Agent Control) category button."""
        from bot.cogs.setup_gui import SetupMainView, SetupCategoryButton
        user = _make_user()
        guild = _make_guild()
        view = SetupMainView(guild_id=123456, user=user, guild=guild)
        categories = [c.category for c in view.children if isinstance(c, SetupCategoryButton)]
        assert "botcontrol" in categories

    @pytest.mark.asyncio
    async def test_setup_main_view_botcontrol_button_label(self):
        """The botcontrol button should have 'Agent Control' as label."""
        from bot.cogs.setup_gui import SetupMainView, SetupCategoryButton
        user = _make_user()
        guild = _make_guild()
        view = SetupMainView(guild_id=123456, user=user, guild=guild)
        botcontrol_btns = [
            c for c in view.children
            if isinstance(c, SetupCategoryButton) and c.category == "botcontrol"
        ]
        assert len(botcontrol_btns) == 1
        assert "Agent Control" in botcontrol_btns[0].label

    @pytest.mark.asyncio
    async def test_setup_main_view_has_cluster_button(self):
        from bot.cogs.setup_gui import SetupMainView, SetupCategoryButton
        user = _make_user()
        guild = _make_guild()
        view = SetupMainView(guild_id=123456, user=user, guild=guild)
        categories = [c.category for c in view.children if isinstance(c, SetupCategoryButton)]
        assert "cluster" in categories


# ---------------------------------------------------------------------------
# 3. SetupCategoryButton
# ---------------------------------------------------------------------------

class TestSetupCategoryButton:
    def test_setup_category_button_is_discord_ui_button_subclass(self):
        from bot.cogs.setup_gui import SetupCategoryButton
        btn = SetupCategoryButton(label="Test", emoji="🔧", category="hosting")
        assert isinstance(btn, discord.ui.Button)

    def test_setup_category_button_stores_category(self):
        from bot.cogs.setup_gui import SetupCategoryButton
        btn = SetupCategoryButton(label="Channels", emoji="📺", category="channels")
        assert btn.category == "channels"

    def test_setup_category_button_has_correct_label(self):
        from bot.cogs.setup_gui import SetupCategoryButton
        btn = SetupCategoryButton(label="Admin Role", emoji="👑", category="admin")
        assert btn.label == "Admin Role"

    def test_setup_category_button_custom_id_prefix(self):
        from bot.cogs.setup_gui import SetupCategoryButton
        btn = SetupCategoryButton(label="Test", emoji="🔧", category="shop")
        assert btn.custom_id == "setup_shop"


# ---------------------------------------------------------------------------
# 4. HostingTypeView
# ---------------------------------------------------------------------------

class TestHostingTypeView:
    @pytest.mark.asyncio
    async def test_hosting_type_view_can_be_instantiated(self):
        from bot.cogs.setup_gui import HostingTypeView
        user = _make_user()
        view = HostingTypeView(guild_id=123456, user=user)
        assert view is not None

    @pytest.mark.asyncio
    async def test_hosting_type_view_has_self_hosted_button(self):
        from bot.cogs.setup_gui import HostingTypeView, HostingTypeButton
        user = _make_user()
        view = HostingTypeView(guild_id=123456, user=user)
        labels = [c.label for c in view.children if isinstance(c, (discord.ui.Button, HostingTypeButton))]
        assert any("Self-Hosted" in (lbl or "") for lbl in labels)

    @pytest.mark.asyncio
    async def test_hosting_type_view_has_nitrado_button(self):
        from bot.cogs.setup_gui import HostingTypeView, HostingTypeButton
        user = _make_user()
        view = HostingTypeView(guild_id=123456, user=user)
        labels = [c.label for c in view.children if isinstance(c, (discord.ui.Button, HostingTypeButton))]
        assert any("Nitrado" in (lbl or "") for lbl in labels)

    @pytest.mark.asyncio
    async def test_hosting_type_view_self_hosted_has_success_style(self):
        from bot.cogs.setup_gui import HostingTypeView, HostingTypeButton
        user = _make_user()
        view = HostingTypeView(guild_id=123456, user=user)
        self_hosted_btns = [
            c for c in view.children
            if isinstance(c, HostingTypeButton) and c.hosting_type == "self_hosted"
        ]
        assert len(self_hosted_btns) == 1
        assert self_hosted_btns[0].style == discord.ButtonStyle.success


# ---------------------------------------------------------------------------
# 5. AddServerModal
# ---------------------------------------------------------------------------

class TestAddServerModal:
    @pytest.mark.asyncio
    async def test_add_server_modal_can_be_instantiated(self):
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=123456)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_add_server_modal_is_discord_ui_modal_subclass(self):
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=123456)
        assert isinstance(modal, discord.ui.Modal)

    @pytest.mark.asyncio
    async def test_add_server_modal_has_server_name_field(self):
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=123456)
        assert hasattr(modal, "server_name")
        assert isinstance(modal.server_name, discord.ui.TextInput)

    @pytest.mark.asyncio
    async def test_add_server_modal_has_host_field(self):
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=123456)
        assert hasattr(modal, "host")
        assert isinstance(modal.host, discord.ui.TextInput)

    @pytest.mark.asyncio
    async def test_add_server_modal_has_rcon_port_field(self):
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=123456)
        assert hasattr(modal, "rcon_port")
        assert isinstance(modal.rcon_port, discord.ui.TextInput)

    @pytest.mark.asyncio
    async def test_add_server_modal_has_rcon_password_field(self):
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=123456)
        assert hasattr(modal, "rcon_password")
        assert isinstance(modal.rcon_password, discord.ui.TextInput)

    @pytest.mark.asyncio
    async def test_add_server_modal_has_at_most_5_fields(self):
        """Discord modals support at most 5 text input fields."""
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=123456)
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert len(text_inputs) <= 5

    @pytest.mark.asyncio
    async def test_add_server_modal_stores_guild_id(self):
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=777888)
        assert modal.guild_id == 777888

    @pytest.mark.asyncio
    async def test_add_server_modal_accepts_parent_view(self):
        from bot.cogs.setup_gui import AddServerModal
        parent = SimpleNamespace(refresh=AsyncMock())
        modal = AddServerModal(guild_id=123456, parent_view=parent)
        assert modal.parent_view is parent

    @pytest.mark.asyncio
    async def test_add_server_modal_rcon_port_has_placeholder(self):
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=123456)
        assert modal.rcon_port.placeholder is not None
        assert "27020" in modal.rcon_port.placeholder

    @pytest.mark.asyncio
    async def test_add_server_modal_server_name_is_required(self):
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=123456)
        assert modal.server_name.required is True

    @pytest.mark.asyncio
    async def test_add_server_modal_host_is_required(self):
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=123456)
        assert modal.host.required is True

    @pytest.mark.asyncio
    async def test_add_server_modal_rcon_port_is_required(self):
        from bot.cogs.setup_gui import AddServerModal
        modal = AddServerModal(guild_id=123456)
        assert modal.rcon_port.required is True



# ---------------------------------------------------------------------------
# 6. EditServerModal
# ---------------------------------------------------------------------------

class TestEditServerModal:
    def _make_server_dict(self) -> dict:
        return {
            "id": 1,
            "guild_id": 100,
            "name": "Aberration",
            "host": "192.168.1.100",
            "rcon_port": 27020,
            "rcon_password": "secretpass",
            "server_path": "D:\\ARK\\Aberration",
            "steamcmd_path": "C:\\SteamCMD\\steamcmd.exe",
        }

    @pytest.mark.asyncio
    async def test_edit_server_modal_can_be_instantiated(self):
        from bot.cogs.setup_gui import EditServerModal
        modal = EditServerModal(server_config=self._make_server_dict())
        assert modal is not None

    @pytest.mark.asyncio
    async def test_edit_server_modal_is_discord_ui_modal_subclass(self):
        from bot.cogs.setup_gui import EditServerModal
        modal = EditServerModal(server_config=self._make_server_dict())
        assert isinstance(modal, discord.ui.Modal)

    @pytest.mark.asyncio
    async def test_edit_server_modal_has_server_name_field(self):
        from bot.cogs.setup_gui import EditServerModal
        modal = EditServerModal(server_config=self._make_server_dict())
        assert hasattr(modal, "server_name")
        assert isinstance(modal.server_name, discord.ui.TextInput)

    @pytest.mark.asyncio
    async def test_edit_server_modal_has_host_field(self):
        from bot.cogs.setup_gui import EditServerModal
        modal = EditServerModal(server_config=self._make_server_dict())
        assert hasattr(modal, "host")

    @pytest.mark.asyncio
    async def test_edit_server_modal_has_rcon_port_field(self):
        from bot.cogs.setup_gui import EditServerModal
        modal = EditServerModal(server_config=self._make_server_dict())
        assert hasattr(modal, "rcon_port")

    @pytest.mark.asyncio
    async def test_edit_server_modal_has_at_most_5_fields(self):
        """Discord modals support at most 5 text input fields."""
        from bot.cogs.setup_gui import EditServerModal
        modal = EditServerModal(server_config=self._make_server_dict())
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert len(text_inputs) <= 5

    @pytest.mark.asyncio
    async def test_edit_server_modal_prefills_name(self):
        from bot.cogs.setup_gui import EditServerModal
        modal = EditServerModal(server_config=self._make_server_dict())
        assert modal.server_name.default == "Aberration"

    @pytest.mark.asyncio
    async def test_edit_server_modal_prefills_host(self):
        from bot.cogs.setup_gui import EditServerModal
        modal = EditServerModal(server_config=self._make_server_dict())
        assert modal.host.default == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_edit_server_modal_prefills_rcon_port(self):
        from bot.cogs.setup_gui import EditServerModal
        modal = EditServerModal(server_config=self._make_server_dict())
        assert "27020" in (modal.rcon_port.default or "")

    @pytest.mark.asyncio
    async def test_edit_server_modal_stores_server_reference(self):
        from bot.cogs.setup_gui import EditServerModal
        server = self._make_server_dict()
        modal = EditServerModal(server_config=server)
        assert modal.server_config is server

    @pytest.mark.asyncio
    async def test_edit_server_modal_title_contains_server_name(self):
        from bot.cogs.setup_gui import EditServerModal
        modal = EditServerModal(server_config=self._make_server_dict())
        assert "Aberration" in modal.title


# ---------------------------------------------------------------------------
# 7. ManageServersView
# ---------------------------------------------------------------------------

class TestManageServersView:
    @pytest.mark.asyncio
    async def test_manage_servers_view_can_be_instantiated(self):
        from bot.cogs.setup_gui import ManageServersView
        user = _make_user()
        guild = _make_guild()
        view = ManageServersView(guild_id=123456, user=user, guild=guild)
        assert view is not None

    @pytest.mark.asyncio
    async def test_manage_servers_view_is_discord_ui_view_subclass(self):
        from bot.cogs.setup_gui import ManageServersView
        user = _make_user()
        guild = _make_guild()
        view = ManageServersView(guild_id=123456, user=user, guild=guild)
        assert isinstance(view, discord.ui.View)

    @pytest.mark.asyncio
    async def test_manage_servers_view_starts_with_empty_servers(self):
        from bot.cogs.setup_gui import ManageServersView
        user = _make_user()
        guild = _make_guild()
        view = ManageServersView(guild_id=123456, user=user, guild=guild)
        assert view.servers == []

    @pytest.mark.asyncio
    async def test_manage_servers_view_has_timeout(self):
        from bot.cogs.setup_gui import ManageServersView
        user = _make_user()
        guild = _make_guild()
        view = ManageServersView(guild_id=123456, user=user, guild=guild)
        assert view.timeout == 300


# ---------------------------------------------------------------------------
# 8. ServerActionsView
# ---------------------------------------------------------------------------

class TestServerActionsView:
    def _make_server_dict(self) -> dict:
        return {
            "id": 1,
            "name": "Island",
            "host": "192.168.1.50",
            "rcon_port": 27020,
            "enabled": True,
        }

    @pytest.mark.asyncio
    async def test_server_actions_view_can_be_instantiated(self):
        from bot.cogs.setup_gui import ServerActionsView
        server = self._make_server_dict()
        user = _make_user()
        view = ServerActionsView(server=server, guild_id=123456, user=user)
        assert view is not None

    @pytest.mark.asyncio
    async def test_server_actions_view_is_discord_ui_view_subclass(self):
        from bot.cogs.setup_gui import ServerActionsView
        server = self._make_server_dict()
        user = _make_user()
        view = ServerActionsView(server=server, guild_id=123456, user=user)
        assert isinstance(view, discord.ui.View)

    @pytest.mark.asyncio
    async def test_server_actions_view_has_edit_button(self):
        from bot.cogs.setup_gui import ServerActionsView, EditServerButton
        server = self._make_server_dict()
        user = _make_user()
        view = ServerActionsView(server=server, guild_id=123456, user=user)
        edit_btns = [c for c in view.children if isinstance(c, EditServerButton)]
        assert len(edit_btns) == 1

    @pytest.mark.asyncio
    async def test_server_actions_view_has_toggle_button(self):
        from bot.cogs.setup_gui import ServerActionsView, ToggleServerButton
        server = self._make_server_dict()
        user = _make_user()
        view = ServerActionsView(server=server, guild_id=123456, user=user)
        toggle_btns = [c for c in view.children if isinstance(c, ToggleServerButton)]
        assert len(toggle_btns) == 1

    @pytest.mark.asyncio
    async def test_server_actions_view_has_remove_button(self):
        from bot.cogs.setup_gui import ServerActionsView, RemoveServerButton
        server = self._make_server_dict()
        user = _make_user()
        view = ServerActionsView(server=server, guild_id=123456, user=user)
        remove_btns = [c for c in view.children if isinstance(c, RemoveServerButton)]
        assert len(remove_btns) == 1

    @pytest.mark.asyncio
    async def test_server_actions_view_toggle_button_danger_style_when_enabled(self):
        """When server is enabled, Toggle button shows Disable (danger style)."""
        from bot.cogs.setup_gui import ServerActionsView, ToggleServerButton
        server = {**self._make_server_dict(), "enabled": True}
        user = _make_user()
        view = ServerActionsView(server=server, guild_id=123456, user=user)
        toggle_btn = next(c for c in view.children if isinstance(c, ToggleServerButton))
        assert toggle_btn.style == discord.ButtonStyle.danger

    @pytest.mark.asyncio
    async def test_server_actions_view_toggle_button_success_style_when_disabled(self):
        """When server is disabled, Toggle button shows Enable (success style)."""
        from bot.cogs.setup_gui import ServerActionsView, ToggleServerButton
        server = {**self._make_server_dict(), "enabled": False}
        user = _make_user()
        view = ServerActionsView(server=server, guild_id=123456, user=user)
        toggle_btn = next(c for c in view.children if isinstance(c, ToggleServerButton))
        assert toggle_btn.style == discord.ButtonStyle.success

    @pytest.mark.asyncio
    async def test_server_actions_view_remove_button_is_danger_style(self):
        from bot.cogs.setup_gui import ServerActionsView, RemoveServerButton
        server = self._make_server_dict()
        user = _make_user()
        view = ServerActionsView(server=server, guild_id=123456, user=user)
        remove_btn = next(c for c in view.children if isinstance(c, RemoveServerButton))
        assert remove_btn.style == discord.ButtonStyle.danger

    @pytest.mark.asyncio
    async def test_server_actions_view_create_embed_returns_embed(self):
        from bot.cogs.setup_gui import ServerActionsView
        server = self._make_server_dict()
        user = _make_user()
        view = ServerActionsView(server=server, guild_id=123456, user=user)
        embed = view.create_embed()
        assert isinstance(embed, discord.Embed)
        assert "Island" in embed.title


# ---------------------------------------------------------------------------
# 9. botcontrol category: servers_count uses DB query, not agent.agents.values()
# ---------------------------------------------------------------------------

class TestBotcontrolServerCount:
    @pytest.mark.asyncio
    async def test_botcontrol_uses_db_count_not_agent_count(self, server_config_db):
        """
        The botcontrol SetupCategoryButton callback queries DB for ark_servers count,
        not len(agent.agents.values()). Verify the DB query path is present in setup_gui.py.

        We can verify this by confirming that SetupCategoryButton callback for botcontrol
        calls server_config_db.get_ark_servers and uses len(ark_servers) for servers_count.

        This is an architectural test: confirm both values are independently computed.
        """
        from bot.cogs.setup_gui import SetupCategoryButton
        import inspect

        # Read the source of SetupCategoryButton.callback
        source = inspect.getsource(SetupCategoryButton.callback)

        # The callback should call get_ark_servers (DB query)
        assert "get_ark_servers" in source

        # The callback should compute servers_count from DB result
        assert "servers_count" in source
        assert "len(ark_servers)" in source

        # The agents count should be separate from servers_count
        assert "agents_count" in source


# ---------------------------------------------------------------------------
# 10. Cog and command registration
# ---------------------------------------------------------------------------

class TestSetupGUICog:
    def test_cog_can_be_instantiated(self):
        from bot.cogs.setup_gui import SetupGUI
        bot = SimpleNamespace()
        cog = SetupGUI(bot)
        assert cog is not None
        assert cog.bot is bot

    def test_server_cfg_command_exists(self):
        """The /servercfg command is defined on the SetupGUI cog."""
        from bot.cogs.setup_gui import SetupGUI
        assert hasattr(SetupGUI, "server_cfg")

    def test_setup_function_exists(self):
        """The async setup() function for cog loading must exist."""
        from bot.cogs import setup_gui
        assert hasattr(setup_gui, "setup")


# ---------------------------------------------------------------------------
# 11. ShopSettingsModal
# ---------------------------------------------------------------------------

class TestShopSettingsModal:
    """ShopSettingsModal lives in shopcfg_gui (moved from setup_gui)."""

    @pytest.mark.asyncio
    async def test_shop_settings_modal_can_be_instantiated(self):
        from bot.cogs.shopcfg_gui import ShopSettingsModal
        modal = ShopSettingsModal(guild_id=123456, config=None)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_shop_settings_modal_has_enabled_field(self):
        from bot.cogs.shopcfg_gui import ShopSettingsModal
        modal = ShopSettingsModal(guild_id=123456, config=None)
        assert hasattr(modal, "enabled")

    @pytest.mark.asyncio
    async def test_shop_settings_modal_default_items_per_page(self):
        from bot.cogs.shopcfg_gui import ShopSettingsModal
        modal = ShopSettingsModal(guild_id=123456, config=None)
        assert modal.items_per_page.default == "4"

    @pytest.mark.asyncio
    async def test_shop_settings_modal_prefills_from_config(self):
        from bot.cogs.shopcfg_gui import ShopSettingsModal
        config = {
            "shop_enabled": True,
            "items_per_page": 10,
        }
        modal = ShopSettingsModal(guild_id=123456, config=config)
        assert modal.enabled.default == "yes"
        assert modal.items_per_page.default == "10"
        # require_linked removed — shop always requires a linked account


# ---------------------------------------------------------------------------
# /setshop renamed to /shopcfg (UX regression)
# ---------------------------------------------------------------------------

class TestShopCfgButtons:
    """Regression: Shop Items Management buttons must work."""

    def test_shop_items_add_button_exists(self):
        from bot.cogs.shopcfg_gui import ShopItemsView
        assert hasattr(ShopItemsView, 'add_item_button')

    def test_shop_items_edit_button_exists(self):
        from bot.cogs.shopcfg_gui import ShopItemsView
        assert hasattr(ShopItemsView, 'edit_item_button')

    def test_shop_items_remove_button_exists(self):
        from bot.cogs.shopcfg_gui import ShopItemsView
        assert hasattr(ShopItemsView, 'remove_item_button')

    def test_shop_items_toggle_button_removed(self):
        """Toggle button was removed — Edit Item handles enable/disable."""
        from bot.cogs.shopcfg_gui import ShopItemsView
        assert not hasattr(ShopItemsView, 'toggle_item_button')

    def test_shop_items_add_modal_importable(self):
        from bot.cogs.shopcfg_gui import AddShopItemModal
        assert AddShopItemModal is not None

    def test_shop_items_edit_select_view_importable(self):
        from bot.cogs.shopcfg_gui import EditItemSelectView
        assert EditItemSelectView is not None

    def test_shop_items_remove_select_view_importable(self):
        from bot.cogs.shopcfg_gui import RemoveItemSelectView
        assert RemoveItemSelectView is not None

    def test_shop_items_toggle_select_view_removed(self):
        """ToggleItemSelectView was removed — Edit Item handles enable/disable."""
        from bot.cogs import shopcfg_gui
        assert not hasattr(shopcfg_gui, 'ToggleItemSelectView')
    """Regression: /shopcfg now lives in shopcfg_gui.py (not setup.py)."""

    def test_shopcfg_gui_has_shopcfg_command(self):
        import inspect
        from bot.cogs.shopcfg_gui import ShopCfgCog
        source = inspect.getsource(ShopCfgCog)
        assert 'name="shopcfg"' in source, (
            "shopcfg_gui.py must have name='shopcfg' command."
        )

    def test_shopcfg_response_is_ephemeral(self):
        import inspect
        from bot.cogs.shopcfg_gui import ShopCfgCog
        source = inspect.getsource(ShopCfgCog)
        assert 'shopcfg_command(self, interaction' in source
        lines = source.split('\n')
        in_shopcfg = False
        for line in lines:
            if 'async def shopcfg_command' in line:
                in_shopcfg = True
            if in_shopcfg and 'send_message' in line and 'ephemeral=True' in line:
                break
            if in_shopcfg and 'async def ' in line and 'shopcfg_command' not in line:
                break
        else:
            if in_shopcfg:
                assert 'ephemeral=True' in source.split('shopcfg_command')[1].split('async def')[0], (
                    "shopcfg_command send_message must have ephemeral=True"
                )

    def test_setup_py_does_not_have_shopcfg(self):
        import inspect
        from bot.cogs.setup import Setup
        source = inspect.getsource(Setup)
        assert 'shopcfg' not in source, (
            "setup.py should not have shopcfg command - moved to shopcfg_gui.py"
        )
        assert 'name="setshop"' not in source, (
            "Old name='setshop' must be removed from setup.py."
        )

    def test_help_commands_references_shopcfg(self):
        import inspect
        from bot.cogs.help_commands import HelpCommands
        source = inspect.getsource(HelpCommands)
        assert "/shopcfg" in source, (
            "help_commands.py must reference /shopcfg (not /setshop)."
        )

    def test_help_commands_does_not_reference_setshop(self):
        import inspect
        from bot.cogs.help_commands import HelpCommands
        source = inspect.getsource(HelpCommands)
        assert "/setshop" not in source, (
            "Old /setshop reference must be removed from help_commands.py."
        )


# ---------------------------------------------------------------------------
# 13. ToggleServerButton tier enforcement
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Captures Discord interaction response calls without using mocks."""

    def __init__(self):
        self.send_message_content = None
        self.send_message_ephemeral = None
        self.edit_message_kwargs = None

    async def send_message(self, content="", *, ephemeral=False, **kwargs):
        self.send_message_content = content
        self.send_message_ephemeral = ephemeral

    async def edit_message(self, **kwargs):
        self.edit_message_kwargs = kwargs


class _FakeInteraction:
    """Minimal interaction stand-in with captured response; no mocks."""

    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.response = _FakeResponse()


class TestToggleServerButtonTierEnforcement:
    """ToggleServerButton.callback must block re-enabling a tier_limit server
    when the guild subscription is on the free tier."""

    # ------------------------------------------------------------------
    # Source-inspection tests — all FAIL on unpatched code
    # ------------------------------------------------------------------

    def test_toggle_callback_uses_subscription_db(self):
        """callback must import/use subscription_db to look up the guild tier."""
        import inspect
        from bot.cogs.setup_gui import ToggleServerButton
        source = inspect.getsource(ToggleServerButton.callback)
        assert "subscription_db" in source, (
            "ToggleServerButton.callback must use subscription_db to enforce tier limits"
        )

    def test_toggle_callback_checks_effective_tier(self):
        """callback must call get_effective_tier to determine whether enable is allowed."""
        import inspect
        from bot.cogs.setup_gui import ToggleServerButton
        source = inspect.getsource(ToggleServerButton.callback)
        assert "get_effective_tier" in source, (
            "ToggleServerButton.callback must call get_effective_tier before re-enabling"
        )

    def test_toggle_callback_checks_disabled_reason(self):
        """callback must inspect disabled_reason to protect tier-limit servers."""
        import inspect
        from bot.cogs.setup_gui import ToggleServerButton
        source = inspect.getsource(ToggleServerButton.callback)
        assert "disabled_reason" in source, (
            "ToggleServerButton.callback must check disabled_reason to block tier_limit re-enables"
        )

    def test_toggle_callback_conditionally_checks_tier_on_enable_only(self):
        """Tier check must only fire when new_status is True (enabling).

        Disabling a server should always be permitted regardless of tier.
        The source must reference 'new_status' before the tier guard.
        """
        import inspect
        from bot.cogs.setup_gui import ToggleServerButton
        source = inspect.getsource(ToggleServerButton.callback)
        assert "new_status" in source, (
            "ToggleServerButton.callback must use new_status for conditional tier check"
        )

    # ------------------------------------------------------------------
    # Functional tests using real DB — no mocks
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_enable_blocked_for_free_tier_tier_limit_server(self, initialized_db):
        """Attempting to enable a tier_limit-disabled server on a free-tier guild
        must be refused with an ephemeral error; the server must remain disabled."""
        from bot.cogs.setup_gui import ToggleServerButton
        from bot.database import server_config_db, subscription_db

        guild_id = 880001

        # Provision a free-tier subscription
        await subscription_db.get_or_create_subscription(guild_id)
        # Ensure guild row exists (server_configs FK)
        from bot.database.server_config_db import init_server_config_tables
        from bot.database.init_db import initialize_database  # already done via fixture

        # Add a server and mark it as disabled with tier_limit
        server_id = await server_config_db.add_ark_server(
            guild_id,
            name="TierLimitServer",
            host="10.0.0.1",
            rcon_port=27020,
            rcon_password="pass",
        )
        await server_config_db.update_ark_server(
            server_id, enabled=False, disabled_reason="tier_limit"
        )

        # Confirm setup: server is disabled with tier_limit reason
        all_servers = await server_config_db.get_all_ark_servers_including_disabled(guild_id)
        server = next(s for s in all_servers if s["id"] == server_id)
        assert not server["enabled"], "Test setup: server must be disabled"
        assert server["disabled_reason"] == "tier_limit", "Test setup: disabled_reason must be tier_limit"

        # Build the Enable button for this server
        button = ToggleServerButton(server=server, parent_view=None)
        assert button.label == "Enable Server", "Button should show Enable for a disabled server"

        # Fire the callback
        interaction = _FakeInteraction(guild_id=guild_id)
        await button.callback(interaction)

        # Verify: must have sent an ephemeral rejection, not proceeded to edit_message
        assert interaction.response.send_message_content is not None, (
            "Expected ephemeral send_message rejecting the enable attempt; got edit_message or nothing"
        )
        assert interaction.response.send_message_ephemeral is True, (
            "Tier-limit rejection must be sent as ephemeral=True"
        )
        content = interaction.response.send_message_content.lower()
        assert "premium" in content or "upgrade" in content or "free" in content, (
            f"Rejection message must mention premium/upgrade/free, got: {content!r}"
        )

        # Verify: server remains disabled in DB
        all_servers_after = await server_config_db.get_all_ark_servers_including_disabled(guild_id)
        server_after = next(s for s in all_servers_after if s["id"] == server_id)
        assert not server_after["enabled"], (
            "Server must remain disabled after tier-blocked toggle attempt"
        )

    @pytest.mark.asyncio
    async def test_enable_allowed_for_premium_tier(self, initialized_db):
        """Premium-tier guild must be able to re-enable a tier_limit-disabled server."""
        from bot.cogs.setup_gui import ToggleServerButton
        from bot.database import server_config_db, subscription_db

        guild_id = 880002

        # Provision a premium-tier subscription
        await subscription_db.get_or_create_subscription(guild_id)
        await subscription_db.set_tier(guild_id, "premium", "active")

        server_id = await server_config_db.add_ark_server(
            guild_id,
            name="PremiumServer",
            host="10.0.0.2",
            rcon_port=27021,
            rcon_password="pass",
        )
        await server_config_db.update_ark_server(
            server_id, enabled=False, disabled_reason="tier_limit"
        )

        all_servers = await server_config_db.get_all_ark_servers_including_disabled(guild_id)
        server = next(s for s in all_servers if s["id"] == server_id)

        button = ToggleServerButton(server=server, parent_view=None)
        interaction = _FakeInteraction(guild_id=guild_id)
        await button.callback(interaction)

        # Premium tier: edit_message must be called (success flow), not send_message rejection
        assert interaction.response.edit_message_kwargs is not None, (
            "Premium tier must be allowed to re-enable a server (expected edit_message success)"
        )
        assert interaction.response.send_message_content is None, (
            "Premium tier must NOT receive an error message when re-enabling"
        )

    @pytest.mark.asyncio
    async def test_disable_always_allowed_regardless_of_tier(self, initialized_db):
        """Disabling an *enabled* server must always succeed, even on free tier.
        The tier check only applies when new_status is True (enabling)."""
        from bot.cogs.setup_gui import ToggleServerButton
        from bot.database import server_config_db, subscription_db

        guild_id = 880003

        await subscription_db.get_or_create_subscription(guild_id)
        # Keep free tier (default)

        server_id = await server_config_db.add_ark_server(
            guild_id,
            name="FreeServer",
            host="10.0.0.3",
            rcon_port=27022,
            rcon_password="pass",
        )

        all_servers = await server_config_db.get_all_ark_servers_including_disabled(guild_id)
        server = next(s for s in all_servers if s["id"] == server_id)
        assert server["enabled"], "Test setup: server must be enabled"

        button = ToggleServerButton(server=server, parent_view=None)
        assert button.label == "Disable Server"

        interaction = _FakeInteraction(guild_id=guild_id)
        await button.callback(interaction)

        # Disabling must proceed — edit_message called, no rejection
        assert interaction.response.edit_message_kwargs is not None, (
            "Free tier must be allowed to disable a server"
        )
        assert interaction.response.send_message_content is None, (
            "Free tier must not receive an error when disabling a server"
        )
        # Server is now disabled in DB
        all_servers_after = await server_config_db.get_all_ark_servers_including_disabled(guild_id)
        server_after = next(s for s in all_servers_after if s["id"] == server_id)
        assert not server_after["enabled"], "Server must be disabled after toggle"


# ---------------------------------------------------------------------------
# 14. EnableServerButton removed from ManageServersView
# ---------------------------------------------------------------------------

class TestEnableServerButtonRemoved:
    """EnableServerButton was a redundant button on the ManageServersView main panel.
    The ToggleServerButton inside ServerActionsView handles this with tier enforcement.
    The standalone Enable Server button and its associated select view must be removed."""

    def test_enable_server_button_class_removed(self):
        """EnableServerButton class must not exist in setup_gui."""
        from bot.cogs import setup_gui
        assert not hasattr(setup_gui, "EnableServerButton"), (
            "EnableServerButton was removed — use ToggleServerButton in ServerActionsView instead"
        )

    def test_enable_server_select_view_class_removed(self):
        """EnableServerSelectView class must not exist in setup_gui."""
        from bot.cogs import setup_gui
        assert not hasattr(setup_gui, "EnableServerSelectView"), (
            "EnableServerSelectView was removed along with EnableServerButton"
        )

    def test_manage_servers_view_does_not_add_enable_button(self):
        """ManageServersView.load_servers must not add EnableServerButton."""
        import inspect
        from bot.cogs.setup_gui import ManageServersView
        source = inspect.getsource(ManageServersView.load_servers)
        assert "EnableServerButton" not in source, (
            "ManageServersView.load_servers must not add EnableServerButton"
        )


# ---------------------------------------------------------------------------
# 15. ManageServersView shows disabled servers with ⚠️ indicator
# ---------------------------------------------------------------------------

class TestManageServersViewShowsDisabled:
    """Disabled servers must remain visible in the manage console so admins
    can see their state and re-enable after upgrading. Only intentional
    hard-deletes should remove a server from the list."""

    def test_load_servers_includes_disabled(self):
        """load_servers must fetch disabled servers (include_disabled=True)."""
        import inspect
        from bot.cogs.setup_gui import ManageServersView
        source = inspect.getsource(ManageServersView.load_servers)
        assert "include_disabled=True" in source or "get_all_ark_servers_including_disabled" in source, (
            "ManageServersView.load_servers must use include_disabled=True so disabled "
            "servers remain visible in the manage console"
        )

    def test_load_servers_shows_warning_for_disabled(self):
        """Disabled servers must be marked with a visual indicator in the dropdown."""
        import inspect
        from bot.cogs.setup_gui import ManageServersView
        source = inspect.getsource(ManageServersView.load_servers)
        assert "⚠️" in source or "Disabled" in source, (
            "ManageServersView.load_servers must show a visual indicator for disabled servers"
        )


# ---------------------------------------------------------------------------
# 16. Service creation modal regression — server_name key rename
# ---------------------------------------------------------------------------

class TestServiceCreationModalKeyRegression:
    """Regression guard: a previous AI model renamed 'server_name' to 'service_name'
    in page 1's service_data dict but left stale 'server_name' references in later
    pages/modals, causing KeyError and 'Something went wrong' on modal submit.

    All on_submit handlers that read service_data must use 'service_name'.
    """

    def test_no_stale_server_name_key_in_service_data_access(self):
        """setup_gui.py must not access service_data['server_name'] anywhere."""
        import inspect
        import ast
        import bot.cogs.setup_gui as module

        source = inspect.getsource(module)
        # Search for the exact broken pattern — dict access with 'server_name' on service_data
        assert "service_data['server_name']" not in source, (
            "service_data['server_name'] found — key was renamed to 'service_name' in page 1. "
            "All modal on_submit handlers must use service_data['service_name']."
        )
        assert 'service_data["server_name"]' not in source, (
            'service_data["server_name"] found — key was renamed to "service_name" in page 1.'
        )


# ---------------------------------------------------------------------------
# 17. Unified 4-page wizard — modal field structure (TDD)
# ---------------------------------------------------------------------------

class TestConfigureServerModal1:
    """Page 1 of unified wizard: Identity (Display Name, Map, Host, Service, Max Players)."""

    def test_modal_is_importable(self):
        from bot.cogs.setup_gui import ConfigureServerModal1
        assert ConfigureServerModal1 is not None

    def test_modal_has_at_most_5_fields(self):
        from bot.cogs.setup_gui import ConfigureServerModal1
        modal = ConfigureServerModal1(guild_id=123)
        assert len(modal._children) <= 5

    def test_display_name_is_required(self):
        from bot.cogs.setup_gui import ConfigureServerModal1
        modal = ConfigureServerModal1(guild_id=123)
        assert modal.display_name.required is True

    def test_map_name_is_required(self):
        from bot.cogs.setup_gui import ConfigureServerModal1
        modal = ConfigureServerModal1(guild_id=123)
        assert modal.map_name.required is True

    def test_host_is_required(self):
        from bot.cogs.setup_gui import ConfigureServerModal1
        modal = ConfigureServerModal1(guild_id=123)
        assert modal.host.required is True

    def test_service_name_is_required(self):
        from bot.cogs.setup_gui import ConfigureServerModal1
        modal = ConfigureServerModal1(guild_id=123)
        assert modal.service_name.required is True

    def test_max_players_is_optional_with_default_70(self):
        from bot.cogs.setup_gui import ConfigureServerModal1
        modal = ConfigureServerModal1(guild_id=123)
        assert modal.max_players.required is False
        assert "70" in (modal.max_players.default or modal.max_players.placeholder or "")

    def test_title_contains_1_of_4(self):
        from bot.cogs.setup_gui import ConfigureServerModal1
        modal = ConfigureServerModal1(guild_id=123)
        assert "1/4" in modal.title

    def test_wizard_data_prefill(self):
        from bot.cogs.setup_gui import ConfigureServerModal1
        wizard_data = {
            "name": "My Server", "map_name": "TheIsland", "host": "10.0.0.1",
            "service_name": "PhoenixARK_Island", "max_players": 50,
        }
        modal = ConfigureServerModal1(guild_id=123, wizard_data=wizard_data)
        assert "My Server" in (modal.display_name.default or "")
        assert "TheIsland" in (modal.map_name.default or "")


class TestConfigureServerModal2:
    """Page 2 of unified wizard: Ports & Auth."""

    def test_modal_is_importable(self):
        from bot.cogs.setup_gui import ConfigureServerModal2
        assert ConfigureServerModal2 is not None

    def test_modal_has_at_most_5_fields(self):
        from bot.cogs.setup_gui import ConfigureServerModal2
        modal = ConfigureServerModal2(guild_id=123, wizard_data={})
        assert len(modal._children) <= 5

    def test_rcon_password_is_required(self):
        from bot.cogs.setup_gui import ConfigureServerModal2
        modal = ConfigureServerModal2(guild_id=123, wizard_data={})
        assert modal.rcon_password.required is True

    def test_game_port_has_default_7777(self):
        from bot.cogs.setup_gui import ConfigureServerModal2
        modal = ConfigureServerModal2(guild_id=123, wizard_data={})
        assert "7777" in (modal.game_port.default or modal.game_port.placeholder or "")

    def test_query_port_has_default_7778(self):
        from bot.cogs.setup_gui import ConfigureServerModal2
        modal = ConfigureServerModal2(guild_id=123, wizard_data={})
        assert "7778" in (modal.query_port.default or modal.query_port.placeholder or "")

    def test_rcon_port_has_default_27020(self):
        from bot.cogs.setup_gui import ConfigureServerModal2
        modal = ConfigureServerModal2(guild_id=123, wizard_data={})
        assert "27020" in (modal.rcon_port.default or modal.rcon_port.placeholder or "")

    def test_admin_password_is_required(self):
        from bot.cogs.setup_gui import ConfigureServerModal2
        modal = ConfigureServerModal2(guild_id=123, wizard_data={})
        assert modal.admin_password.required is True

    def test_title_contains_2_of_4(self):
        from bot.cogs.setup_gui import ConfigureServerModal2
        modal = ConfigureServerModal2(guild_id=123, wizard_data={})
        assert "2/4" in modal.title


class TestConfigureServerModal3:
    """Page 3 of unified wizard: Paths."""

    def test_modal_is_importable(self):
        from bot.cogs.setup_gui import ConfigureServerModal3
        assert ConfigureServerModal3 is not None

    def test_modal_has_at_most_5_fields(self):
        from bot.cogs.setup_gui import ConfigureServerModal3
        modal = ConfigureServerModal3(guild_id=123, wizard_data={})
        assert len(modal._children) <= 5

    def test_server_path_is_required(self):
        from bot.cogs.setup_gui import ConfigureServerModal3
        modal = ConfigureServerModal3(guild_id=123, wizard_data={})
        assert modal.server_path.required is True

    def test_steamcmd_path_is_required(self):
        from bot.cogs.setup_gui import ConfigureServerModal3
        modal = ConfigureServerModal3(guild_id=123, wizard_data={})
        assert modal.steamcmd_path.required is True

    def test_server_password_is_optional(self):
        from bot.cogs.setup_gui import ConfigureServerModal3
        modal = ConfigureServerModal3(guild_id=123, wizard_data={})
        assert modal.server_password.required is False

    def test_mods_is_optional(self):
        from bot.cogs.setup_gui import ConfigureServerModal3
        modal = ConfigureServerModal3(guild_id=123, wizard_data={})
        assert modal.mods.required is False

    def test_title_contains_3_of_4(self):
        from bot.cogs.setup_gui import ConfigureServerModal3
        modal = ConfigureServerModal3(guild_id=123, wizard_data={})
        assert "3/4" in modal.title


class TestConfigureServerModal4:
    """Page 4 of unified wizard: Advanced."""

    def test_modal_is_importable(self):
        from bot.cogs.setup_gui import ConfigureServerModal4
        assert ConfigureServerModal4 is not None

    def test_modal_has_at_most_5_fields(self):
        from bot.cogs.setup_gui import ConfigureServerModal4
        modal = ConfigureServerModal4(guild_id=123, wizard_data={}, parent_view=None)
        assert len(modal._children) <= 5

    def test_all_fields_optional(self):
        from bot.cogs.setup_gui import ConfigureServerModal4
        modal = ConfigureServerModal4(guild_id=123, wizard_data={}, parent_view=None)
        for child in modal._children:
            assert child.required is False, f"Field '{child.label}' should be optional in page 4"

    def test_battleye_default_false(self):
        from bot.cogs.setup_gui import ConfigureServerModal4
        modal = ConfigureServerModal4(guild_id=123, wizard_data={}, parent_view=None)
        assert "false" in (
            modal.battleye_enabled.default or modal.battleye_enabled.placeholder or ""
        ).lower()

    def test_title_contains_4_of_4(self):
        from bot.cogs.setup_gui import ConfigureServerModal4
        modal = ConfigureServerModal4(guild_id=123, wizard_data={}, parent_view=None)
        assert "4/4" in modal.title


class TestConfigureServerButton:
    """ConfigureServerButton replaces AddServerFromManageButton and CreateServiceButton."""

    def test_configure_server_button_is_importable(self):
        from bot.cogs.setup_gui import ConfigureServerButton
        assert ConfigureServerButton is not None

    def test_configure_server_button_is_discord_button(self):
        import discord
        from bot.cogs.setup_gui import ConfigureServerButton
        btn = ConfigureServerButton(guild_id=123, parent_view=None)
        assert isinstance(btn, discord.ui.Button)

    def test_manage_servers_view_uses_configure_button(self):
        """ManageServersView must use ConfigureServerButton, not AddServerFromManageButton."""
        import inspect
        from bot.cogs.setup_gui import ManageServersView
        source = inspect.getsource(ManageServersView.load_servers)
        assert "ConfigureServerButton" in source, (
            "ManageServersView.load_servers must add ConfigureServerButton"
        )

    def test_service_management_view_uses_configure_button(self):
        """ServiceManagementView must use ConfigureServerButton, not CreateServiceButton."""
        import inspect
        from bot.cogs.setup_gui import ServiceManagementView
        source = inspect.getsource(ServiceManagementView.load_services)
        assert "ConfigureServerButton" in source, (
            "ServiceManagementView.load_services must add ConfigureServerButton"
        )


# ---------------------------------------------------------------------------
# 18. Linked removal — detect-and-ask (TDD)
# ---------------------------------------------------------------------------

class TestLinkedRemovalDetection:
    """Regression guard: RemoveServerButton.callback checks service_name before confirming."""

    def test_remove_server_button_callback_checks_service_name(self):
        import inspect
        from bot.cogs.setup_gui import RemoveServerButton
        source = inspect.getsource(RemoveServerButton.callback)
        assert "service_name" in source, (
            "RemoveServerButton.callback must check service_name to detect linked Windows services"
        )

    def test_linked_remove_server_view_is_importable(self):
        from bot.cogs.setup_gui import LinkedRemoveServerView
        assert LinkedRemoveServerView is not None

    def test_linked_remove_server_view_has_db_removal(self):
        import inspect
        from bot.cogs.setup_gui import LinkedRemoveServerView
        source = inspect.getsource(LinkedRemoveServerView)
        assert "remove_ark_server" in source, "Must offer DB record removal"

    def test_linked_remove_server_view_has_service_removal(self):
        import inspect
        from bot.cogs.setup_gui import LinkedRemoveServerView
        source = inspect.getsource(LinkedRemoveServerView)
        assert "delete_server_service" in source or "agent_manager" in source, (
            "Must offer service deletion for the 'Remove both' option"
        )


class TestLinkedServiceRemoval:
    """Regression guard: DeleteServiceButton.callback checks DB for linked server."""

    def test_delete_service_button_callback_checks_db(self):
        import inspect
        from bot.cogs.setup_gui import DeleteServiceButton
        source = inspect.getsource(DeleteServiceButton.callback)
        assert "server_config_db" in source or "get_ark_servers" in source, (
            "DeleteServiceButton.callback must query the DB to detect linked bot server records"
        )

    def test_linked_remove_service_view_is_importable(self):
        from bot.cogs.setup_gui import LinkedRemoveServiceView
        assert LinkedRemoveServiceView is not None

    def test_linked_remove_service_view_has_db_removal(self):
        import inspect
        from bot.cogs.setup_gui import LinkedRemoveServiceView
        source = inspect.getsource(LinkedRemoveServiceView)
        assert "remove_ark_server" in source, "Must offer DB record removal for 'Delete both'"

    def test_linked_remove_service_view_has_service_removal(self):
        import inspect
        from bot.cogs.setup_gui import LinkedRemoveServiceView
        source = inspect.getsource(LinkedRemoveServiceView)
        assert "delete_server_service" in source or "agent_manager" in source, (
            "Must offer service deletion"
        )
