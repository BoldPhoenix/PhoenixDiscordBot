"""
Tests for rcon_admin.py - RconAdmin cog.

Tests cover:
- RconAdmin instantiation and initial state
- Expected slash commands present
- execute_rcon method existence
- get_server_choices method existence
- is_admin pure logic (administrator flag path)
- setup function existence

Uses SimpleNamespace for fake bot and fake interaction — no Discord API calls.
"""

import pytest
import inspect
from types import SimpleNamespace

from discord.ext import commands


def _make_bot():
    """Minimal fake bot."""
    return SimpleNamespace()


def _make_admin_interaction(is_admin: bool = True, roles=None):
    """Build a fake interaction where user has (or lacks) administrator permission."""
    if roles is None:
        roles = []
    return SimpleNamespace(
        user=SimpleNamespace(
            guild_permissions=SimpleNamespace(administrator=is_admin),
            roles=roles,
            display_name="TestUser",
        ),
        guild_id=123456,
        guild=SimpleNamespace(get_role=lambda x: None),
    )


# ---------------------------------------------------------------------------
# Cog init tests
# ---------------------------------------------------------------------------

class TestRconAdminInit:
    def test_cog_instantiation(self):
        """RconAdmin can be instantiated with a fake bot."""
        from bot.cogs.rcon_admin import RconAdmin
        bot = _make_bot()
        cog = RconAdmin(bot)
        assert cog is not None
        assert cog.bot is bot

    def test_rcon_manager_starts_as_none(self):
        """RconAdmin.rcon_manager is None immediately after init."""
        from bot.cogs.rcon_admin import RconAdmin
        cog = RconAdmin(_make_bot())
        assert cog.rcon_manager is None

    def test_cog_inherits_from_commands_cog(self):
        """RconAdmin inherits from discord.ext.commands.Cog."""
        from bot.cogs.rcon_admin import RconAdmin
        assert issubclass(RconAdmin, commands.Cog)


# ---------------------------------------------------------------------------
# Command presence tests
# ---------------------------------------------------------------------------

class TestRconAdminCommands:
    def test_has_saveworld_command(self):
        """RconAdmin has a save_world (saveworld) command."""
        from bot.cogs.rcon_admin import RconAdmin
        assert hasattr(RconAdmin, "save_world")

    def test_has_destroywilddinos_command(self):
        """RconAdmin has a destroy_wild_dinos (destroywilddinos) command."""
        from bot.cogs.rcon_admin import RconAdmin
        assert hasattr(RconAdmin, "destroy_wild_dinos")

    def test_has_getchat_command(self):
        """RconAdmin has a get_chat (getchat) command."""
        from bot.cogs.rcon_admin import RconAdmin
        assert hasattr(RconAdmin, "get_chat")


# ---------------------------------------------------------------------------
# execute_rcon and get_server_choices method existence tests
# ---------------------------------------------------------------------------

class TestRconAdminMethods:
    def test_execute_rcon_exists(self):
        """RconAdmin has an execute_rcon method."""
        from bot.cogs.rcon_admin import RconAdmin
        assert hasattr(RconAdmin, "execute_rcon")

    def test_execute_rcon_is_coroutine(self):
        """execute_rcon is an async coroutine function."""
        from bot.cogs.rcon_admin import RconAdmin
        assert inspect.iscoroutinefunction(RconAdmin.execute_rcon)

    def test_get_server_choices_exists(self):
        """RconAdmin has a get_server_choices method."""
        from bot.cogs.rcon_admin import RconAdmin
        assert hasattr(RconAdmin, "get_server_choices")

    def test_get_server_choices_is_coroutine(self):
        """get_server_choices is an async coroutine function."""
        from bot.cogs.rcon_admin import RconAdmin
        assert inspect.iscoroutinefunction(RconAdmin.get_server_choices)

    def test_is_admin_exists(self):
        """RconAdmin has an is_admin method."""
        from bot.cogs.rcon_admin import RconAdmin
        assert hasattr(RconAdmin, "is_admin")

    def test_is_admin_is_coroutine(self):
        """is_admin is an async coroutine function."""
        from bot.cogs.rcon_admin import RconAdmin
        assert inspect.iscoroutinefunction(RconAdmin.is_admin)

    def test_get_servers_for_guild_exists(self):
        """RconAdmin has a get_servers_for_guild method."""
        from bot.cogs.rcon_admin import RconAdmin
        assert hasattr(RconAdmin, "get_servers_for_guild")

    def test_get_servers_for_guild_is_coroutine(self):
        """get_servers_for_guild is an async coroutine function."""
        from bot.cogs.rcon_admin import RconAdmin
        assert inspect.iscoroutinefunction(RconAdmin.get_servers_for_guild)


# ---------------------------------------------------------------------------
# is_admin pure logic tests (administrator flag path — no DB call needed)
# ---------------------------------------------------------------------------

class TestIsAdminLogic:
    @pytest.mark.asyncio
    async def test_administrator_flag_grants_access(self):
        """is_admin returns True immediately when user.guild_permissions.administrator is True."""
        from bot.cogs.rcon_admin import RconAdmin
        cog = RconAdmin(_make_bot())
        interaction = _make_admin_interaction(is_admin=True)
        # is_admin calls DB on non-admin path; for the admin path it returns True
        # before hitting the DB so this is safe to call directly.
        result = await cog.is_admin(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_non_administrator_without_db_config_returns_false(self):
        """is_admin returns False for non-admin with no DB config and no matching roles."""
        from bot.cogs.rcon_admin import RconAdmin
        import unittest.mock as mock

        cog = RconAdmin(_make_bot())
        interaction = _make_admin_interaction(is_admin=False)

        # Patch server_config_db.get_server_config to return None (no DB config)
        with mock.patch(
            "bot.cogs.rcon_admin.server_config_db.get_server_config",
            return_value=None,
        ):
            result = await cog.is_admin(interaction)

        assert result is False


# ---------------------------------------------------------------------------
# setup function tests
# ---------------------------------------------------------------------------

class TestRconAdminSetup:
    def test_setup_function_exists(self):
        """Module-level setup() function exists in rcon_admin."""
        import bot.cogs.rcon_admin as module
        assert hasattr(module, "setup")

    def test_setup_is_callable(self):
        """setup() is callable."""
        import bot.cogs.rcon_admin as module
        assert callable(module.setup)

    def test_setup_is_coroutine_function(self):
        """setup() is an async/coroutine function."""
        import bot.cogs.rcon_admin as module
        assert inspect.iscoroutinefunction(module.setup)


# ---------------------------------------------------------------------------
# execute_rcon return shape tests (structural, no real RCON connection)
# ---------------------------------------------------------------------------

class TestExecuteRconSignature:
    def test_execute_rcon_signature_has_server_config_and_command(self):
        """execute_rcon accepts server_config (dict) and command (str) as positional args."""
        from bot.cogs.rcon_admin import RconAdmin
        sig = inspect.signature(RconAdmin.execute_rcon)
        params = list(sig.parameters.keys())
        # Expected: self, server_config, command
        assert "server_config" in params
        assert "command" in params

    def test_get_servers_for_guild_signature_has_guild_id(self):
        """get_servers_for_guild accepts guild_id as a parameter."""
        from bot.cogs.rcon_admin import RconAdmin
        sig = inspect.signature(RconAdmin.get_servers_for_guild)
        params = list(sig.parameters.keys())
        assert "guild_id" in params


# ---------------------------------------------------------------------------
# All admin commands log to admin channel (consistency regression)
# ---------------------------------------------------------------------------

class TestRconAdminAllCommandsHaveLogging:
    """Every RCON command that performs a player or server action must log to
    the guild admin log channel, consistent with kick_player / ban_player."""

    def _source(self, method_name: str) -> str:
        from bot.cogs.rcon_admin import RconAdmin
        attr = getattr(RconAdmin, method_name)
        # @app_commands.command wraps the function; unwrap via .callback
        fn = getattr(attr, "callback", attr)
        return inspect.getsource(fn)

    def test_whitelist_player_logs_to_admin_channel(self):
        assert "admin_log_channel_id" in self._source("whitelist_player"), (
            "whitelist_player is missing admin log channel send."
        )

    def test_save_world_logs_to_admin_channel(self):
        assert "admin_log_channel_id" in self._source("save_world"), (
            "save_world is missing admin log channel send."
        )

    def test_destroy_wild_dinos_logs_to_admin_channel(self):
        assert "admin_log_channel_id" in self._source("destroy_wild_dinos"), (
            "destroy_wild_dinos is missing admin log channel send."
        )

