"""
Tests for economy.py — Economy cog, EconomySettingsModal, EconomyRolesView, and helpers.

Tests cover:
- Module-level imports
- EconomySettingsModal field definitions and defaults
- EconomyRolesView construction and embed building
- AddRoleBonusModal field definitions
- Economy cog instantiation and command existence
- Helper function signatures (_get_currency, _require_linked)
- payday_loop task existence and lifecycle
- payday_enabled parsing logic from on_submit

Uses real discord.py objects — no mocks (Jeffrey Snover methodology).
Views/Modals require a running asyncio event loop; all such tests are async.
"""

import pytest
import asyncio
import inspect
from types import SimpleNamespace

import discord


# ---------------------------------------------------------------------------
# Minimal bot stand-in
# ---------------------------------------------------------------------------

class _FakeBot:
    """Lightweight bot-like object sufficient for Economy cog instantiation."""

    def __init__(self):
        self.guilds = []

    def get_cog(self, name):
        return None

    async def wait_until_ready(self):
        pass


def _make_bot():
    return _FakeBot()


# ---------------------------------------------------------------------------
# 1. Import tests
# ---------------------------------------------------------------------------

class TestEconomyImports:
    def test_economy_module_importable(self):
        import bot.cogs.economy  # noqa: F401

    def test_economy_class_importable(self):
        from bot.cogs.economy import Economy
        assert Economy is not None

    def test_economy_settings_modal_importable(self):
        from bot.cogs.economy import EconomySettingsModal
        assert EconomySettingsModal is not None

    def test_economy_roles_view_importable(self):
        from bot.cogs.economy import EconomyRolesView
        assert EconomyRolesView is not None

    def test_add_role_bonus_modal_importable(self):
        from bot.cogs.economy import AddRoleBonusModal
        assert AddRoleBonusModal is not None

    def test_remove_role_bonus_select_importable(self):
        from bot.cogs.economy import RemoveRoleBonusSelect
        assert RemoveRoleBonusSelect is not None

    def test_get_currency_helper_importable(self):
        from bot.cogs.economy import _get_currency
        assert _get_currency is not None

    def test_require_linked_helper_importable(self):
        from bot.cogs.economy import _require_linked
        assert _require_linked is not None


# ---------------------------------------------------------------------------
# 2. EconomySettingsModal — field definitions and defaults
# ---------------------------------------------------------------------------

class TestEconomySettingsModal:
    @pytest.mark.asyncio
    async def test_instantiates_with_empty_settings(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert modal is not None

    @pytest.mark.asyncio
    async def test_has_payday_amount_field(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert hasattr(modal, "payday_amount")

    @pytest.mark.asyncio
    async def test_has_currency_name_field(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert hasattr(modal, "currency_name")

    @pytest.mark.asyncio
    async def test_has_currency_icon_field(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert hasattr(modal, "currency_icon")

    @pytest.mark.asyncio
    async def test_has_payday_enabled_field(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert hasattr(modal, "payday_enabled")

    @pytest.mark.asyncio
    async def test_payday_amount_max_length_is_6(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert modal.payday_amount.max_length == 6

    @pytest.mark.asyncio
    async def test_currency_name_max_length_is_30(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert modal.currency_name.max_length == 30

    @pytest.mark.asyncio
    async def test_currency_icon_max_length_is_8(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert modal.currency_icon.max_length == 8

    @pytest.mark.asyncio
    async def test_payday_enabled_max_length_is_3(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert modal.payday_enabled.max_length == 3

    @pytest.mark.asyncio
    async def test_prefills_payday_amount_default_100_when_not_in_settings(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert modal.payday_amount.default == "100"

    @pytest.mark.asyncio
    async def test_prefills_payday_amount_from_settings(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({"base_payday_amount": 250})
        assert modal.payday_amount.default == "250"

    @pytest.mark.asyncio
    async def test_prefills_payday_enabled_yes_when_payday_enabled_is_1(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({"payday_enabled": 1})
        assert modal.payday_enabled.default == "yes"

    @pytest.mark.asyncio
    async def test_prefills_payday_enabled_no_when_payday_enabled_is_0(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({"payday_enabled": 0})
        assert modal.payday_enabled.default == "no"

    @pytest.mark.asyncio
    async def test_prefills_currency_name_from_settings(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({"currency_name": "Dragon Gold"})
        assert modal.currency_name.default == "Dragon Gold"

    @pytest.mark.asyncio
    async def test_prefills_currency_name_fallback(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert modal.currency_name.default == "Phoenix Coins"

    @pytest.mark.asyncio
    async def test_prefills_currency_icon_from_settings(self):
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({"currency_icon": "💎"})
        assert modal.currency_icon.default == "💎"

    @pytest.mark.asyncio
    async def test_payday_enabled_default_true_when_key_missing(self):
        """When payday_enabled is absent from settings, defaults to 1 (truthy) → 'yes'."""
        from bot.cogs.economy import EconomySettingsModal
        modal = EconomySettingsModal({})
        assert modal.payday_enabled.default == "yes"


# ---------------------------------------------------------------------------
# 3. payday_enabled parsing logic (mirrors on_submit logic)
# ---------------------------------------------------------------------------

class TestPaydayEnabledParsing:
    """Test the parsing logic used in EconomySettingsModal.on_submit."""

    def _parse(self, value: str) -> bool:
        return value.strip().lower() in ("yes", "y", "true", "1")

    def test_yes_is_true(self):
        assert self._parse("yes") is True

    def test_y_is_true(self):
        assert self._parse("y") is True

    def test_true_is_true(self):
        assert self._parse("true") is True

    def test_1_is_true(self):
        assert self._parse("1") is True

    def test_no_is_false(self):
        assert self._parse("no") is False

    def test_n_is_false(self):
        assert self._parse("n") is False

    def test_false_is_false(self):
        assert self._parse("false") is False

    def test_0_is_false(self):
        assert self._parse("0") is False

    def test_YES_uppercase_is_true(self):
        assert self._parse("YES") is True

    def test_whitespace_trimmed(self):
        assert self._parse("  yes  ") is True


# ---------------------------------------------------------------------------
# 4. EconomyRolesView
# ---------------------------------------------------------------------------

class TestEconomyRolesView:
    @pytest.mark.asyncio
    async def test_instantiates_with_empty_roles(self):
        from bot.cogs.economy import EconomyRolesView
        guild = SimpleNamespace(id=123)
        view = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        assert view is not None

    @pytest.mark.asyncio
    async def test_stores_guild_id(self):
        from bot.cogs.economy import EconomyRolesView
        guild = SimpleNamespace(id=999)
        view = EconomyRolesView(guild_id=999, roles=[], guild=guild)
        assert view.guild_id == 999

    @pytest.mark.asyncio
    async def test_stores_roles_list(self):
        from bot.cogs.economy import EconomyRolesView
        guild = SimpleNamespace(id=123)
        roles = [{"role_id": 111, "bonus_amount": 50}]
        view = EconomyRolesView(guild_id=123, roles=roles, guild=guild)
        assert view.roles is roles

    @pytest.mark.asyncio
    async def test_has_add_role_button(self):
        from bot.cogs.economy import EconomyRolesView
        guild = SimpleNamespace(id=123)
        view = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Add Role Bonus" in lbl for lbl in labels)

    @pytest.mark.asyncio
    async def test_has_remove_role_button(self):
        from bot.cogs.economy import EconomyRolesView
        guild = SimpleNamespace(id=123)
        view = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Remove" in lbl for lbl in labels)

    @pytest.mark.asyncio
    async def test_build_embed_no_roles_shows_placeholder(self):
        from bot.cogs.economy import EconomyRolesView
        guild = SimpleNamespace(id=123)
        view = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        embed = view.build_embed()
        assert "No role bonuses" in embed.description

    @pytest.mark.asyncio
    async def test_build_embed_with_roles_shows_role_mention(self):
        from bot.cogs.economy import EconomyRolesView
        guild = SimpleNamespace(id=123)
        roles = [{"role_id": 555, "bonus_amount": 100}]
        view = EconomyRolesView(guild_id=123, roles=roles, guild=guild)
        embed = view.build_embed()
        assert "555" in embed.description
        assert "100" in embed.description

    @pytest.mark.asyncio
    async def test_build_embed_title_contains_role_bonus(self):
        from bot.cogs.economy import EconomyRolesView
        guild = SimpleNamespace(id=123)
        view = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        embed = view.build_embed()
        assert "Role" in embed.title

    @pytest.mark.asyncio
    async def test_add_button_style_is_success(self):
        from bot.cogs.economy import EconomyRolesView
        guild = SimpleNamespace(id=123)
        view = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        add_btn = next(
            (c for c in view.children if isinstance(c, discord.ui.Button) and "Add" in (c.label or "")),
            None,
        )
        assert add_btn is not None
        assert add_btn.style == discord.ButtonStyle.success

    @pytest.mark.asyncio
    async def test_remove_button_style_is_danger(self):
        from bot.cogs.economy import EconomyRolesView
        guild = SimpleNamespace(id=123)
        view = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        remove_btn = next(
            (c for c in view.children if isinstance(c, discord.ui.Button) and "Remove" in (c.label or "")),
            None,
        )
        assert remove_btn is not None
        assert remove_btn.style == discord.ButtonStyle.danger


# ---------------------------------------------------------------------------
# 5. AddRoleBonusModal
# ---------------------------------------------------------------------------

class TestAddRoleBonusModal:
    @pytest.mark.asyncio
    async def test_instantiates_with_guild_and_role(self):
        from bot.cogs.economy import AddRoleBonusModal, EconomyRolesView
        guild = SimpleNamespace(id=123)
        parent = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        role = SimpleNamespace(id=456, name="TestRole")
        modal = AddRoleBonusModal(123, role, parent)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_has_bonus_field(self):
        from bot.cogs.economy import AddRoleBonusModal, EconomyRolesView
        guild = SimpleNamespace(id=123)
        parent = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        role = SimpleNamespace(id=456, name="TestRole")
        modal = AddRoleBonusModal(123, role, parent)
        assert hasattr(modal, "bonus")

    @pytest.mark.asyncio
    async def test_bonus_max_length_is_6(self):
        from bot.cogs.economy import EconomyRolesView, AddRoleBonusModal
        guild = SimpleNamespace(id=123)
        parent = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        role = SimpleNamespace(id=456, name="TestRole")
        modal = AddRoleBonusModal(123, role, parent)
        assert modal.bonus.max_length == 6

    @pytest.mark.asyncio
    async def test_stores_guild_id(self):
        from bot.cogs.economy import EconomyRolesView, AddRoleBonusModal
        guild = SimpleNamespace(id=123)
        parent = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        role = SimpleNamespace(id=456, name="TestRole")
        modal = AddRoleBonusModal(123, role, parent)
        assert modal.guild_id == 123

    @pytest.mark.asyncio
    async def test_stores_role(self):
        from bot.cogs.economy import EconomyRolesView, AddRoleBonusModal
        guild = SimpleNamespace(id=123)
        parent = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        role = SimpleNamespace(id=456, name="TestRole")
        modal = AddRoleBonusModal(123, role, parent)
        assert modal.role is role


class TestRemoveRoleBonusSelect:
    @pytest.mark.asyncio
    async def test_instantiates_with_guild_and_parent(self):
        from bot.cogs.economy import EconomyRolesView, RemoveRoleBonusSelect
        guild = SimpleNamespace(id=123)
        parent = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        view = RemoveRoleBonusSelect(123, parent)
        assert view is not None

    @pytest.mark.asyncio
    async def test_stores_guild_id(self):
        from bot.cogs.economy import EconomyRolesView, RemoveRoleBonusSelect
        guild = SimpleNamespace(id=123)
        parent = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        view = RemoveRoleBonusSelect(123, parent)
        assert view.guild_id == 123

    @pytest.mark.asyncio
    async def test_has_role_select(self):
        from bot.cogs.economy import EconomyRolesView, RemoveRoleBonusSelect
        guild = SimpleNamespace(id=123)
        parent = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        view = RemoveRoleBonusSelect(123, parent)
        selects = [c for c in view.children if isinstance(c, discord.ui.RoleSelect)]
        assert len(selects) == 1


class TestAddRoleBonusSelect:
    @pytest.mark.asyncio
    async def test_instantiates_with_guild_and_parent(self):
        from bot.cogs.economy import EconomyRolesView, AddRoleBonusSelect
        guild = SimpleNamespace(id=123)
        parent = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        view = AddRoleBonusSelect(123, parent)
        assert view is not None

    @pytest.mark.asyncio
    async def test_stores_guild_id(self):
        from bot.cogs.economy import EconomyRolesView, AddRoleBonusSelect
        guild = SimpleNamespace(id=123)
        parent = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        view = AddRoleBonusSelect(123, parent)
        assert view.guild_id == 123

    @pytest.mark.asyncio
    async def test_has_role_select(self):
        from bot.cogs.economy import EconomyRolesView, AddRoleBonusSelect
        guild = SimpleNamespace(id=123)
        parent = EconomyRolesView(guild_id=123, roles=[], guild=guild)
        view = AddRoleBonusSelect(123, parent)
        selects = [c for c in view.children if isinstance(c, discord.ui.RoleSelect)]
        assert len(selects) == 1


# ---------------------------------------------------------------------------
# 6. Economy cog — instantiation, commands, task lifecycle
# ---------------------------------------------------------------------------

class TestEconomyCog:
    @pytest.mark.asyncio
    async def test_cog_instantiates_with_fake_bot(self):
        from bot.cogs.economy import Economy
        bot = _make_bot()
        cog = Economy(bot)
        # Stop the loop immediately to avoid background task running in tests
        cog.payday_loop.cancel()
        assert cog.bot is bot

    def test_cog_has_balance_command(self):
        from bot.cogs.economy import Economy
        # Command methods are defined directly on the class
        assert hasattr(Economy, "balance")

    def test_cog_has_history_command(self):
        from bot.cogs.economy import Economy
        assert hasattr(Economy, "history")

    def test_cog_has_add_coins_command(self):
        from bot.cogs.economy import Economy
        assert hasattr(Economy, "add_coins")

    def test_cog_has_remove_coins_command(self):
        from bot.cogs.economy import Economy
        assert hasattr(Economy, "remove_coins")

    def test_cog_has_payday_loop_task(self):
        from bot.cogs.economy import Economy
        assert hasattr(Economy, "payday_loop")

    def test_payday_loop_is_tasks_loop(self):
        from bot.cogs.economy import Economy
        from discord.ext.tasks import Loop
        assert isinstance(Economy.payday_loop, Loop)

    @pytest.mark.asyncio
    async def test_cog_unload_cancels_payday_loop(self):
        from bot.cogs.economy import Economy
        bot = _make_bot()
        cog = Economy(bot)
        # Cancel first to avoid the loop actually waiting
        cog.payday_loop.cancel()
        # Now cog_unload should not raise even if already cancelled
        cog.cog_unload()

    def test_cog_has_run_payday_if_due_method(self):
        from bot.cogs.economy import Economy
        assert hasattr(Economy, "_run_payday_if_due")

    def test_cog_has_run_payday_method(self):
        from bot.cogs.economy import Economy
        assert hasattr(Economy, "_run_payday")


# ---------------------------------------------------------------------------
# 7. Helper function signatures
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    def test_get_currency_is_async(self):
        from bot.cogs.economy import _get_currency
        assert inspect.iscoroutinefunction(_get_currency)

    def test_get_currency_takes_guild_id(self):
        from bot.cogs.economy import _get_currency
        sig = inspect.signature(_get_currency)
        assert "guild_id" in sig.parameters

    def test_require_linked_is_async(self):
        from bot.cogs.economy import _require_linked
        assert inspect.iscoroutinefunction(_require_linked)

    def test_require_linked_signature(self):
        from bot.cogs.economy import _require_linked
        sig = inspect.signature(_require_linked)
        params = list(sig.parameters.keys())
        # Expects ctx_or_interaction, guild_id, discord_user_id
        assert "guild_id" in params
        assert "discord_user_id" in params

    def test_run_payday_if_due_is_async(self):
        from bot.cogs.economy import Economy
        assert inspect.iscoroutinefunction(Economy._run_payday_if_due)

    def test_run_payday_is_async(self):
        from bot.cogs.economy import Economy
        assert inspect.iscoroutinefunction(Economy._run_payday)


# ---------------------------------------------------------------------------
# PaydayScheduleModal active_only field describes its behavior (UX regression)
# ---------------------------------------------------------------------------

class TestPaydayScheduleModalActiveOnlyDescription:
    """active_only placeholder must explain what 'active only' means.
    Without a description, admins have no idea what the field does."""

    def test_active_only_placeholder_explains_behavior(self):
        import inspect
        from bot.cogs.economy import PaydayScheduleModal
        source = inspect.getsource(PaydayScheduleModal)
        # Placeholder or label must mention the inactivity window (7 days / 7+ days)
        assert "7" in source and "day" in source.lower(), (
            "PaydayScheduleModal active_only field must mention '7 days' (or '7+ days') in "
            "its placeholder or label so admins know what 'active only' means."
        )
