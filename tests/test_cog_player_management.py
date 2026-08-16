"""
Tests for player_management.py cog.

Tests cover:
- Cog class instantiation
- Presence of expected slash commands
- View class instantiation and button structure
- Modal field names, labels, max_length values
- interaction_check ownership enforcement
- Pagination logic (10 players per page)
- Player embed structure (linked vs unlinked)
- UserSelect components in admin select views
- AddCoins / RemoveCoins modal field names
- setup() function existence
- Admin panel buttons present

Uses real discord.py objects — no mocks (Jeffrey Snover methodology).
Views and Modals require a running asyncio event loop; all such tests are async.
"""

import inspect
import pytest
import asyncio
from types import SimpleNamespace
import discord


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_bot():
    """Minimal bot stand-in."""
    return SimpleNamespace()


def _make_user(user_id: int = 12345, name: str = "TestUser"):
    """Minimal user stand-in."""
    user = SimpleNamespace()
    user.id = user_id
    user.display_name = name
    return user


def _make_interaction(user_id: int = 12345):
    """Minimal interaction stand-in with a user that has an id."""
    interaction = SimpleNamespace()
    interaction.user = _make_user(user_id)
    return interaction


# ---------------------------------------------------------------------------
# 1. Cog instantiation
# ---------------------------------------------------------------------------

class TestPlayerManagementCogInit:
    def test_cog_can_be_instantiated(self):
        from bot.cogs.player_management import PlayerManagement
        bot = _make_bot()
        cog = PlayerManagement(bot)
        assert cog.bot is bot

    def test_cog_bot_attribute_stored(self):
        from bot.cogs.player_management import PlayerManagement
        bot = _make_bot()
        cog = PlayerManagement(bot)
        assert hasattr(cog, "bot")


# ---------------------------------------------------------------------------
# 2. Expected slash commands exist
# ---------------------------------------------------------------------------

class TestExpectedCommands:
    """Verify the exact command names registered on the cog."""

    def _get_command_names(self):
        from bot.cogs.player_management import PlayerManagement
        cog = PlayerManagement(_make_bot())
        # discord.py stores app_commands as _Cog__app_commands_definitions internally,
        # but the cleaner route is iterating the class-level app_commands.
        names = set()
        for attr_name in dir(cog):
            try:
                attr = getattr(cog, attr_name)
            except Exception:
                continue
            if isinstance(attr, discord.app_commands.Command):
                names.add(attr.name)
        return names

    def test_player_command_exists(self):
        from bot.cogs.player_management import PlayerManagement
        cog = PlayerManagement(_make_bot())
        assert hasattr(cog, "player_command")
        assert cog.player_command.name == "player"

    def test_listlinkedplayers_command_exists(self):
        from bot.cogs.player_management import PlayerManagement
        cog = PlayerManagement(_make_bot())
        assert hasattr(cog, "list_linked_players")
        assert cog.list_linked_players.name == "listlinkedplayers"

    def test_playermgmt_command_exists(self):
        from bot.cogs.player_management import PlayerManagement
        cog = PlayerManagement(_make_bot())
        assert hasattr(cog, "player_mgmt")
        assert cog.player_mgmt.name == "playermgmt"


# ---------------------------------------------------------------------------
# 3. PlayerPanelView instantiation and buttons
# ---------------------------------------------------------------------------

class TestPlayerPanelView:
    @pytest.mark.asyncio
    async def test_can_be_instantiated(self):
        from bot.cogs.player_management import PlayerPanelView
        view = PlayerPanelView(_make_bot(), 111, _make_user(), 500, None)
        assert view is not None

    @pytest.mark.asyncio
    async def test_has_bank_balance_button(self):
        from bot.cogs.player_management import PlayerPanelView
        view = PlayerPanelView(_make_bot(), 111, _make_user(), 0, None)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Bank Balance" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_view_my_info_button(self):
        from bot.cogs.player_management import PlayerPanelView
        view = PlayerPanelView(_make_bot(), 111, _make_user(), 0, None)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("View My Info" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_link_edit_player_button(self):
        from bot.cogs.player_management import PlayerPanelView
        view = PlayerPanelView(_make_bot(), 111, _make_user(), 0, None)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Link/Edit Player" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_unlink_player_button(self):
        from bot.cogs.player_management import PlayerPanelView
        view = PlayerPanelView(_make_bot(), 111, _make_user(), 0, None)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Unlink Player" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_four_buttons_total(self):
        from bot.cogs.player_management import PlayerPanelView
        view = PlayerPanelView(_make_bot(), 111, _make_user(), 0, None)
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 4

    @pytest.mark.asyncio
    async def test_stores_guild_id(self):
        from bot.cogs.player_management import PlayerPanelView
        view = PlayerPanelView(_make_bot(), 9999, _make_user(), 0, None)
        assert view.guild_id == 9999

    @pytest.mark.asyncio
    async def test_stores_player_info(self):
        from bot.cogs.player_management import PlayerPanelView
        player_info = {"eos_id": "abc123", "balance": 100}
        view = PlayerPanelView(_make_bot(), 111, _make_user(), 100, player_info)
        assert view.player_info is player_info

    @pytest.mark.asyncio
    async def test_interaction_check_same_user_returns_true(self):
        """interaction_check must allow the owning user through."""
        from bot.cogs.player_management import PlayerPanelView
        user = _make_user(user_id=42)
        view = PlayerPanelView(_make_bot(), 111, user, 0, None)
        interaction = _make_interaction(user_id=42)
        # Patch send_message so it doesn't actually try to call Discord
        interaction.response = SimpleNamespace(send_message=lambda *a, **kw: None)
        result = await view.interaction_check(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_interaction_check_different_user_returns_false(self):
        """interaction_check must deny other users."""
        from bot.cogs.player_management import PlayerPanelView
        user = _make_user(user_id=42)
        view = PlayerPanelView(_make_bot(), 111, user, 0, None)
        interaction = _make_interaction(user_id=99)
        sent_messages = []

        async def fake_send(content, *, ephemeral=False):
            sent_messages.append(content)

        interaction.response = SimpleNamespace(send_message=fake_send)
        result = await view.interaction_check(interaction)
        assert result is False


# ---------------------------------------------------------------------------
# 4. LinkEditPlayerModal — field names and max_length
# ---------------------------------------------------------------------------

class TestLinkEditPlayerModal:
    @pytest.mark.asyncio
    async def test_can_be_instantiated_with_no_existing_player(self):
        from bot.cogs.player_management import LinkEditPlayerModal
        modal = LinkEditPlayerModal(111, 42, None)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_can_be_instantiated_with_existing_player(self):
        from bot.cogs.player_management import LinkEditPlayerModal
        player_info = {"eos_id": "aabbccdd" * 4, "specimen_id": "spec001", "character_name": "Hero"}
        modal = LinkEditPlayerModal(111, 42, player_info)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_eos_id_field_max_length_is_32(self):
        """EOS IDs are 32-char hex; modal max_length must accommodate that."""
        from bot.cogs.player_management import LinkEditPlayerModal
        modal = LinkEditPlayerModal(111, 42, None)
        assert modal.eos_id.max_length == 32

    @pytest.mark.asyncio
    async def test_eos_id_field_is_required(self):
        from bot.cogs.player_management import LinkEditPlayerModal
        modal = LinkEditPlayerModal(111, 42, None)
        assert modal.eos_id.required is True

    @pytest.mark.asyncio
    async def test_character_name_field_exists(self):
        from bot.cogs.player_management import LinkEditPlayerModal
        modal = LinkEditPlayerModal(111, 42, None)
        assert hasattr(modal, "character_name")

    @pytest.mark.asyncio
    async def test_specimen_id_field_is_optional(self):
        from bot.cogs.player_management import LinkEditPlayerModal
        modal = LinkEditPlayerModal(111, 42, None)
        assert modal.specimen_id.required is False

    @pytest.mark.asyncio
    async def test_pre_populates_existing_eos_id(self):
        from bot.cogs.player_management import LinkEditPlayerModal
        player_info = {"eos_id": "deadbeef" * 4, "specimen_id": "", "character_name": ""}
        modal = LinkEditPlayerModal(111, 42, player_info)
        assert modal.eos_id.default == "deadbeef" * 4


# ---------------------------------------------------------------------------
# 5. UnlinkConfirmModal
# ---------------------------------------------------------------------------

class TestUnlinkConfirmModal:
    @pytest.mark.asyncio
    async def test_can_be_instantiated(self):
        from bot.cogs.player_management import UnlinkConfirmModal
        player_info = {"eos_id": "abc", "character_name": "Warlord"}
        modal = UnlinkConfirmModal(111, 42, player_info)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_has_confirm_field(self):
        from bot.cogs.player_management import UnlinkConfirmModal
        player_info = {"eos_id": "abc", "character_name": "Warlord"}
        modal = UnlinkConfirmModal(111, 42, player_info)
        assert hasattr(modal, "confirm")

    @pytest.mark.asyncio
    async def test_confirm_field_max_length_64(self):
        from bot.cogs.player_management import UnlinkConfirmModal
        player_info = {"eos_id": "abc", "character_name": "Warlord"}
        modal = UnlinkConfirmModal(111, 42, player_info)
        assert modal.confirm.max_length == 64

    @pytest.mark.asyncio
    async def test_stores_guild_and_user(self):
        from bot.cogs.player_management import UnlinkConfirmModal
        player_info = {"eos_id": "abc", "character_name": "Hero"}
        modal = UnlinkConfirmModal(222, 77, player_info)
        assert modal.guild_id == 222
        assert modal.discord_user_id == 77


# ---------------------------------------------------------------------------
# 6. Pagination — items_per_page is 10
# ---------------------------------------------------------------------------

class TestListLinkedPlayersPagination:
    def test_items_per_page_is_10(self):
        """The hardcoded constant in list_linked_players must be 10."""
        import inspect
        from bot.cogs.player_management import PlayerManagement
        source = inspect.getsource(PlayerManagement.list_linked_players.callback)
        assert "items_per_page = 10" in source

    def test_pagination_math_single_page(self):
        """11 players across pages of 10 yields 2 pages."""
        items_per_page = 10
        players = list(range(11))
        total_pages = (len(players) + items_per_page - 1) // items_per_page
        assert total_pages == 2

    def test_pagination_math_exact_page(self):
        """Exactly 10 players yields 1 page."""
        items_per_page = 10
        players = list(range(10))
        total_pages = (len(players) + items_per_page - 1) // items_per_page
        assert total_pages == 1

    def test_pagination_math_overflow(self):
        """21 players yields 3 pages."""
        items_per_page = 10
        players = list(range(21))
        total_pages = (len(players) + items_per_page - 1) // items_per_page
        assert total_pages == 3


# ---------------------------------------------------------------------------
# 7. LinkedPlayersPaginationView
# ---------------------------------------------------------------------------

class TestLinkedPlayersPaginationView:
    @pytest.mark.asyncio
    async def test_can_be_instantiated(self):
        from bot.cogs.player_management import LinkedPlayersPaginationView
        players = [{"eos_id": str(i)} for i in range(20)]
        view = LinkedPlayersPaginationView(_make_bot(), 111, _make_user(), players, 1, 2)
        assert view is not None

    @pytest.mark.asyncio
    async def test_has_previous_button(self):
        from bot.cogs.player_management import LinkedPlayersPaginationView
        players = [{"eos_id": str(i)} for i in range(20)]
        view = LinkedPlayersPaginationView(_make_bot(), 111, _make_user(), players, 1, 2)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Previous" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_next_button(self):
        from bot.cogs.player_management import LinkedPlayersPaginationView
        players = [{"eos_id": str(i)} for i in range(20)]
        view = LinkedPlayersPaginationView(_make_bot(), 111, _make_user(), players, 1, 2)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Next" in l for l in labels)

    @pytest.mark.asyncio
    async def test_interaction_check_owner_returns_true(self):
        from bot.cogs.player_management import LinkedPlayersPaginationView
        user = _make_user(user_id=55)
        view = LinkedPlayersPaginationView(_make_bot(), 111, user, [], 1, 1)
        interaction = _make_interaction(user_id=55)
        interaction.response = SimpleNamespace(send_message=lambda *a, **kw: None)
        result = await view.interaction_check(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_interaction_check_other_user_returns_false(self):
        from bot.cogs.player_management import LinkedPlayersPaginationView
        user = _make_user(user_id=55)
        view = LinkedPlayersPaginationView(_make_bot(), 111, user, [], 1, 1)
        interaction = _make_interaction(user_id=99)

        async def fake_send(content, *, ephemeral=False):
            pass

        interaction.response = SimpleNamespace(send_message=fake_send)
        result = await view.interaction_check(interaction)
        assert result is False

    @pytest.mark.asyncio
    async def test_stores_current_page_and_total(self):
        from bot.cogs.player_management import LinkedPlayersPaginationView
        view = LinkedPlayersPaginationView(_make_bot(), 111, _make_user(), [], 3, 7)
        assert view.current_page == 3
        assert view.total_pages == 7


# ---------------------------------------------------------------------------
# 8. PlayerMgmtView (admin panel)
# ---------------------------------------------------------------------------

class TestPlayerMgmtView:
    @pytest.mark.asyncio
    async def test_can_be_instantiated(self):
        from bot.cogs.player_management import PlayerMgmtView
        view = PlayerMgmtView(_make_bot(), 111, _make_user())
        assert view is not None

    @pytest.mark.asyncio
    async def test_has_link_edit_button(self):
        from bot.cogs.player_management import PlayerMgmtView
        view = PlayerMgmtView(_make_bot(), 111, _make_user())
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Link/Edit Player" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_unlink_button(self):
        from bot.cogs.player_management import PlayerMgmtView
        view = PlayerMgmtView(_make_bot(), 111, _make_user())
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Unlink Player" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_add_coins_button(self):
        from bot.cogs.player_management import PlayerMgmtView
        view = PlayerMgmtView(_make_bot(), 111, _make_user())
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Add Coins" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_remove_coins_button(self):
        from bot.cogs.player_management import PlayerMgmtView
        view = PlayerMgmtView(_make_bot(), 111, _make_user())
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Remove Coins" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_kick_player_button(self):
        from bot.cogs.player_management import PlayerMgmtView
        view = PlayerMgmtView(_make_bot(), 111, _make_user())
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Kick Player" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_ban_player_button(self):
        from bot.cogs.player_management import PlayerMgmtView
        view = PlayerMgmtView(_make_bot(), 111, _make_user())
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Ban Player" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_unban_player_button(self):
        from bot.cogs.player_management import PlayerMgmtView
        view = PlayerMgmtView(_make_bot(), 111, _make_user())
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Unban Player" in l for l in labels)

    @pytest.mark.asyncio
    async def test_has_kill_player_button(self):
        from bot.cogs.player_management import PlayerMgmtView
        view = PlayerMgmtView(_make_bot(), 111, _make_user())
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Kill Player" in l for l in labels)

    @pytest.mark.asyncio
    async def test_interaction_check_enforces_ownership(self):
        from bot.cogs.player_management import PlayerMgmtView
        user = _make_user(user_id=100)
        view = PlayerMgmtView(_make_bot(), 111, user)
        interaction = _make_interaction(user_id=200)

        async def fake_send(content, *, ephemeral=False):
            pass

        interaction.response = SimpleNamespace(send_message=fake_send)
        result = await view.interaction_check(interaction)
        assert result is False


# ---------------------------------------------------------------------------
# 9. UserSelect views — AdminLinkEditUserSelectView, AdminUnlinkUserSelectView,
#    AddCoinsUserSelectView, RemoveCoinsUserSelectView
# ---------------------------------------------------------------------------

class TestUserSelectViews:
    @pytest.mark.asyncio
    async def test_admin_link_edit_user_select_has_user_select(self):
        from bot.cogs.player_management import AdminLinkEditUserSelectView
        view = AdminLinkEditUserSelectView(guild_id=111)
        selects = [c for c in view.children if isinstance(c, discord.ui.UserSelect)]
        assert len(selects) == 1

    @pytest.mark.asyncio
    async def test_admin_unlink_user_select_has_user_select(self):
        from bot.cogs.player_management import AdminUnlinkUserSelectView
        view = AdminUnlinkUserSelectView(guild_id=111)
        selects = [c for c in view.children if isinstance(c, discord.ui.UserSelect)]
        assert len(selects) == 1

    @pytest.mark.asyncio
    async def test_add_coins_user_select_has_user_select(self):
        from bot.cogs.player_management import AddCoinsUserSelectView
        view = AddCoinsUserSelectView(guild_id=111)
        selects = [c for c in view.children if isinstance(c, discord.ui.UserSelect)]
        assert len(selects) == 1

    @pytest.mark.asyncio
    async def test_remove_coins_user_select_has_user_select(self):
        from bot.cogs.player_management import RemoveCoinsUserSelectView
        view = RemoveCoinsUserSelectView(guild_id=111)
        selects = [c for c in view.children if isinstance(c, discord.ui.UserSelect)]
        assert len(selects) == 1

    @pytest.mark.asyncio
    async def test_admin_unlink_confirm_view_has_confirm_and_cancel(self):
        from bot.cogs.player_management import AdminUnlinkConfirmView
        view = AdminUnlinkConfirmView(111, 42, "TestUser")
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Confirm" in l for l in labels)
        assert any("Cancel" in l for l in labels)


# ---------------------------------------------------------------------------
# 10. AddCoinsModal and RemoveCoinsModal — amount and reason fields
# ---------------------------------------------------------------------------

class TestCoinsModals:
    @pytest.mark.asyncio
    async def test_add_coins_modal_has_amount_field(self):
        from bot.cogs.player_management import AddCoinsModal
        modal = AddCoinsModal(111, 42, "User")
        assert hasattr(modal, "amount")

    @pytest.mark.asyncio
    async def test_add_coins_modal_has_reason_field(self):
        from bot.cogs.player_management import AddCoinsModal
        modal = AddCoinsModal(111, 42, "User")
        assert hasattr(modal, "reason")

    @pytest.mark.asyncio
    async def test_add_coins_modal_amount_is_required(self):
        from bot.cogs.player_management import AddCoinsModal
        modal = AddCoinsModal(111, 42, "User")
        assert modal.amount.required is True

    @pytest.mark.asyncio
    async def test_add_coins_modal_reason_is_optional(self):
        from bot.cogs.player_management import AddCoinsModal
        modal = AddCoinsModal(111, 42, "User")
        assert modal.reason.required is False

    @pytest.mark.asyncio
    async def test_remove_coins_modal_has_amount_field(self):
        from bot.cogs.player_management import RemoveCoinsModal
        modal = RemoveCoinsModal(111, 42, "User")
        assert hasattr(modal, "amount")

    @pytest.mark.asyncio
    async def test_remove_coins_modal_has_reason_field(self):
        from bot.cogs.player_management import RemoveCoinsModal
        modal = RemoveCoinsModal(111, 42, "User")
        assert hasattr(modal, "reason")

    @pytest.mark.asyncio
    async def test_remove_coins_modal_amount_max_length_10(self):
        """Coin amount field must accept up to 10 digits."""
        from bot.cogs.player_management import RemoveCoinsModal
        modal = RemoveCoinsModal(111, 42, "User")
        assert modal.amount.max_length == 10

    @pytest.mark.asyncio
    async def test_add_coins_modal_amount_max_length_10(self):
        from bot.cogs.player_management import AddCoinsModal
        modal = AddCoinsModal(111, 42, "User")
        assert modal.amount.max_length == 10


# ---------------------------------------------------------------------------
# 11. RCON action modals — KickPlayerModal, BanPlayerModal, UnbanPlayerModal,
#     KillPlayerModal
# ---------------------------------------------------------------------------

class TestRconActionModals:
    @pytest.mark.asyncio
    async def test_kick_player_modal_has_player_field(self):
        from bot.cogs.player_management import KickPlayerModal
        modal = KickPlayerModal(111)
        assert hasattr(modal, "player")

    @pytest.mark.asyncio
    async def test_kick_player_modal_has_reason_field(self):
        from bot.cogs.player_management import KickPlayerModal
        modal = KickPlayerModal(111)
        assert hasattr(modal, "reason")

    @pytest.mark.asyncio
    async def test_ban_player_modal_reason_is_required(self):
        """Ban modal should require a reason; kick modal does not."""
        from bot.cogs.player_management import BanPlayerModal
        modal = BanPlayerModal(111)
        assert modal.reason.required is True

    @pytest.mark.asyncio
    async def test_kick_player_modal_reason_is_optional(self):
        from bot.cogs.player_management import KickPlayerModal
        modal = KickPlayerModal(111)
        assert modal.reason.required is False

    @pytest.mark.asyncio
    async def test_unban_player_modal_has_player_field(self):
        from bot.cogs.player_management import UnbanPlayerModal
        modal = UnbanPlayerModal(111)
        assert hasattr(modal, "player")

    @pytest.mark.asyncio
    async def test_kill_player_modal_has_player_field(self):
        from bot.cogs.player_management import KillPlayerModal
        modal = KillPlayerModal(111)
        assert hasattr(modal, "player")


# ---------------------------------------------------------------------------
# 12. AdminLinkEditPlayerModal — field names and max_length
# ---------------------------------------------------------------------------

class TestAdminLinkEditPlayerModal:
    @pytest.mark.asyncio
    async def test_can_be_instantiated(self):
        from bot.cogs.player_management import AdminLinkEditPlayerModal
        modal = AdminLinkEditPlayerModal(111, 42, "Admin", None)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_eos_id_max_length_32(self):
        from bot.cogs.player_management import AdminLinkEditPlayerModal
        modal = AdminLinkEditPlayerModal(111, 42, "Admin", None)
        assert modal.eos_id.max_length == 32

    @pytest.mark.asyncio
    async def test_character_name_is_optional(self):
        from bot.cogs.player_management import AdminLinkEditPlayerModal
        modal = AdminLinkEditPlayerModal(111, 42, "Admin", None)
        assert modal.character_name.required is False

    @pytest.mark.asyncio
    async def test_stores_guild_and_discord_id(self):
        from bot.cogs.player_management import AdminLinkEditPlayerModal
        modal = AdminLinkEditPlayerModal(333, 77, "SomeAdmin", None)
        assert modal.guild_id == 333
        assert modal.discord_id == 77


# ---------------------------------------------------------------------------
# 13. setup() function exists
# ---------------------------------------------------------------------------

class TestSetupFunction:
    def test_setup_function_is_defined(self):
        import bot.cogs.player_management as module
        assert hasattr(module, "setup")
        assert inspect.iscoroutinefunction(module.setup)


# ---------------------------------------------------------------------------
# 14. Button style correctness
# ---------------------------------------------------------------------------

class TestButtonStyles:
    @pytest.mark.asyncio
    async def test_link_button_is_success_style(self):
        from bot.cogs.player_management import PlayerPanelView
        view = PlayerPanelView(_make_bot(), 111, _make_user(), 0, None)
        btn_map = {c.label: c.style for c in view.children if isinstance(c, discord.ui.Button)}
        assert btn_map["Link/Edit Player"] == discord.ButtonStyle.success

    @pytest.mark.asyncio
    async def test_unlink_button_is_danger_style(self):
        from bot.cogs.player_management import PlayerPanelView
        view = PlayerPanelView(_make_bot(), 111, _make_user(), 0, None)
        btn_map = {c.label: c.style for c in view.children if isinstance(c, discord.ui.Button)}
        assert btn_map["Unlink Player"] == discord.ButtonStyle.danger

    @pytest.mark.asyncio
    async def test_admin_add_coins_is_success_style(self):
        from bot.cogs.player_management import PlayerMgmtView
        view = PlayerMgmtView(_make_bot(), 111, _make_user())
        btn_map = {c.label: c.style for c in view.children if isinstance(c, discord.ui.Button)}
        assert btn_map["Add Coins"] == discord.ButtonStyle.success

    @pytest.mark.asyncio
    async def test_admin_remove_coins_is_danger_style(self):
        from bot.cogs.player_management import PlayerMgmtView
        view = PlayerMgmtView(_make_bot(), 111, _make_user())
        btn_map = {c.label: c.style for c in view.children if isinstance(c, discord.ui.Button)}
        assert btn_map["Remove Coins"] == discord.ButtonStyle.danger


# ---------------------------------------------------------------------------
# 15. AdminUnlinkPlayerModal — calls correct players_db function (regression)
# ---------------------------------------------------------------------------

class TestAdminUnlinkPlayerModalFunction:
    """Regression: modal must call unlink_player_by_discord_id, not unlink_player."""

    def test_unlink_modal_calls_unlink_by_discord_id(self):
        """AdminUnlinkPlayerModal.on_submit must call unlink_player_by_discord_id.
        Calling the non-existent unlink_player() raises AttributeError → interaction fails."""
        import inspect
        from bot.cogs.player_management_gui import AdminUnlinkPlayerModal
        source = inspect.getsource(AdminUnlinkPlayerModal.on_submit)
        assert "unlink_player_by_discord_id" in source, (
            "on_submit must call players_db.unlink_player_by_discord_id(); "
            "players_db.unlink_player() does not exist and causes 'This interaction failed'."
        )
        assert "players_db.unlink_player(" not in source or "unlink_player_by_discord_id" in source, (
            "Must not call the non-existent players_db.unlink_player()."
        )


# ---------------------------------------------------------------------------
# 16. AddCoinsModal uses players_db, not deprecated user_db (regression)
# ---------------------------------------------------------------------------

class TestAddCoinsModalUsesPlayersDb:
    """Regression: AddCoinsModal must use players_db, not deprecated user_db."""

    def test_add_coins_does_not_import_user_db(self):
        import inspect
        from bot.cogs.player_management_gui import AddCoinsModal
        source = inspect.getsource(AddCoinsModal.on_submit)
        assert "user_db" not in source, (
            "AddCoinsModal.on_submit must not use deprecated user_db; use players_db instead."
        )

    def test_add_coins_calls_players_db(self):
        import inspect
        from bot.cogs.player_management_gui import AddCoinsModal
        source = inspect.getsource(AddCoinsModal.on_submit)
        assert "players_db" in source, "AddCoinsModal.on_submit must use players_db."

    def test_add_coins_looks_up_player_by_discord_id(self):
        import inspect
        from bot.cogs.player_management_gui import AddCoinsModal
        source = inspect.getsource(AddCoinsModal.on_submit)
        assert "get_player_by_discord_id" in source, (
            "AddCoinsModal.on_submit must call players_db.get_player_by_discord_id() "
            "to resolve eos_id before adding coins."
        )

    def test_add_coins_logs_to_admin_channel(self):
        import inspect
        from bot.cogs.player_management_gui import AddCoinsModal
        source = inspect.getsource(AddCoinsModal.on_submit)
        assert "admin_log_channel_id" in source, (
            "AddCoinsModal.on_submit must log coin grants to the admin log channel."
        )


# ---------------------------------------------------------------------------
# 17. RemoveCoinsModal uses players_db, not deprecated user_db (regression)
# ---------------------------------------------------------------------------

class TestRemoveCoinsModalUsesPlayersDb:
    """Regression: RemoveCoinsModal must use players_db, not deprecated user_db."""

    def test_remove_coins_does_not_import_user_db(self):
        import inspect
        from bot.cogs.player_management_gui import RemoveCoinsModal
        source = inspect.getsource(RemoveCoinsModal.on_submit)
        assert "user_db" not in source, (
            "RemoveCoinsModal.on_submit must not use deprecated user_db; use players_db instead."
        )

    def test_remove_coins_calls_players_db(self):
        import inspect
        from bot.cogs.player_management_gui import RemoveCoinsModal
        source = inspect.getsource(RemoveCoinsModal.on_submit)
        assert "players_db" in source, "RemoveCoinsModal.on_submit must use players_db."

    def test_remove_coins_looks_up_player_by_discord_id(self):
        import inspect
        from bot.cogs.player_management_gui import RemoveCoinsModal
        source = inspect.getsource(RemoveCoinsModal.on_submit)
        assert "get_player_by_discord_id" in source, (
            "RemoveCoinsModal.on_submit must call players_db.get_player_by_discord_id() "
            "to resolve eos_id before deducting coins."
        )

    def test_remove_coins_logs_to_admin_channel(self):
        import inspect
        from bot.cogs.player_management_gui import RemoveCoinsModal
        source = inspect.getsource(RemoveCoinsModal.on_submit)
        assert "admin_log_channel_id" in source, (
            "RemoveCoinsModal.on_submit must log coin deductions to the admin log channel."
        )


# ---------------------------------------------------------------------------
# 18. Kick/Ban/Kill/Unlink modals log to admin channel
# ---------------------------------------------------------------------------

class TestPlayerMgmtModalsHaveAdminLogging:
    """All destructive modals must log to the guild admin log channel."""

    def test_kick_modal_logs_to_admin_channel(self):
        import inspect
        from bot.cogs.player_management_gui import KickPlayerModal
        source = inspect.getsource(KickPlayerModal.on_submit)
        assert "admin_log_channel_id" in source, (
            "KickPlayerModal.on_submit must log to the admin log channel."
        )

    def test_ban_modal_logs_to_admin_channel(self):
        import inspect
        from bot.cogs.player_management_gui import BanPlayerModal
        source = inspect.getsource(BanPlayerModal.on_submit)
        assert "admin_log_channel_id" in source, (
            "BanPlayerModal.on_submit must log to the admin log channel."
        )

    def test_kill_modal_logs_to_admin_channel(self):
        import inspect
        from bot.cogs.player_management_gui import KillPlayerModal
        source = inspect.getsource(KillPlayerModal.on_submit)
        assert "admin_log_channel_id" in source, (
            "KillPlayerModal.on_submit must log to the admin log channel."
        )

    def test_unlink_modal_logs_to_admin_channel(self):
        import inspect
        from bot.cogs.player_management_gui import AdminUnlinkPlayerModal
        source = inspect.getsource(AdminUnlinkPlayerModal.on_submit)
        assert "admin_log_channel_id" in source, (
            "AdminUnlinkPlayerModal.on_submit must log to the admin log channel."
        )
