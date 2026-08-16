"""
Tests for bot_control.py - BotControl cog.

Tests cover:
- BotControl class instantiation
- ping command existence
- setup function
- Security: absence of restart/stop commands
- Inheritance from commands.Cog

Uses SimpleNamespace for a fake bot object — no mocks.
"""

import pytest
from types import SimpleNamespace
import inspect

from discord.ext import commands


def _make_bot():
    """Minimal fake bot object."""
    bot = SimpleNamespace()
    bot.latency = 0.042  # 42ms fake latency
    return bot


class TestBotControlInit:
    def test_cog_instantiation(self):
        """BotControl can be instantiated with a fake bot."""
        from bot.cogs.bot_control import BotControl
        bot = _make_bot()
        cog = BotControl(bot)
        assert cog is not None
        assert cog.bot is bot

    def test_cog_stores_bot_reference(self):
        """BotControl stores the bot reference on self.bot."""
        from bot.cogs.bot_control import BotControl
        bot = _make_bot()
        cog = BotControl(bot)
        assert cog.bot is bot

    def test_cog_inherits_from_commands_cog(self):
        """BotControl inherits from discord.ext.commands.Cog."""
        from bot.cogs.bot_control import BotControl
        assert issubclass(BotControl, commands.Cog)


class TestBotControlPingCommand:
    def test_ping_attribute_exists_on_class(self):
        """BotControl has a ping attribute at class level."""
        from bot.cogs.bot_control import BotControl
        assert hasattr(BotControl, "ping")

    def test_ping_attribute_exists_on_instance(self):
        """ping is accessible on a BotControl instance."""
        from bot.cogs.bot_control import BotControl
        bot = _make_bot()
        cog = BotControl(bot)
        assert hasattr(cog, "ping")
        assert cog.ping is not None

    def test_ping_callback_is_callable(self):
        """The underlying callback of the ping app_commands.Command is callable."""
        from bot.cogs.bot_control import BotControl
        bot = _make_bot()
        cog = BotControl(bot)
        # discord.app_commands.Command wraps the async function; the callback is callable
        ping_cmd = cog.ping
        callback = getattr(ping_cmd, "callback", None)
        assert callback is not None
        assert callable(callback)

    def test_ping_is_coroutine_function(self):
        """ping is an async/coroutine function."""
        from bot.cogs.bot_control import BotControl
        # Inspect the underlying callback function
        ping_attr = BotControl.ping
        # app_commands.Command wraps the callback; get at the underlying function
        callback = getattr(ping_attr, "callback", ping_attr)
        assert inspect.iscoroutinefunction(callback)


class TestBotControlSetup:
    def test_setup_function_exists(self):
        """Module-level setup() function exists in bot_control."""
        import bot.cogs.bot_control as module
        assert hasattr(module, "setup")

    def test_setup_is_callable(self):
        """setup() is callable."""
        import bot.cogs.bot_control as module
        assert callable(module.setup)

    def test_setup_is_coroutine_function(self):
        """setup() is an async/coroutine function."""
        import bot.cogs.bot_control as module
        assert inspect.iscoroutinefunction(module.setup)


class TestBotControlSecurityAbsence:
    def test_no_restart_command(self):
        """BotControl intentionally has no /restart command (security: use SSH instead)."""
        from bot.cogs.bot_control import BotControl
        # Check class-level attribute
        assert not hasattr(BotControl, "restart")
        # Also verify via instance
        bot = _make_bot()
        cog = BotControl(bot)
        assert not hasattr(cog, "restart")

    def test_no_stop_command(self):
        """BotControl intentionally has no /stop command (security: use SSH instead)."""
        from bot.cogs.bot_control import BotControl
        assert not hasattr(BotControl, "stop")
        bot = _make_bot()
        cog = BotControl(bot)
        assert not hasattr(cog, "stop")

    def test_no_shutdown_command(self):
        """BotControl has no /shutdown command."""
        from bot.cogs.bot_control import BotControl
        assert not hasattr(BotControl, "shutdown")

    def test_no_kill_command(self):
        """BotControl has no /kill command."""
        from bot.cogs.bot_control import BotControl
        assert not hasattr(BotControl, "kill")
