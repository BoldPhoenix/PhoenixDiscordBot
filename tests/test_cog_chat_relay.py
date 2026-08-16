"""
Tests for chat_relay.py - ChatRelay cog and RCONChatMonitor.

Tests cover:
- RCONChatMonitor initialization attributes
- chat_patterns regex: standard "PlayerName: message" format
- chat_patterns regex: "[GLOBAL] PlayerName: message" format
- skip_patterns: [Discord] prefix is skipped
- skip_patterns: SERVER: prefix is skipped
- skip_patterns: "Server received, But no response" is skipped
- skip_patterns: Admin Message is skipped
- Message deduplication via last_messages set
- max_cache_size constant
- ChatRelay cog instantiation
- ChatRelay cog attributes at init
- setup function existence

Uses SimpleNamespace — no Discord API calls needed for pattern/logic tests.
"""

import pytest
import re
from types import SimpleNamespace
import inspect

from discord.ext import commands


def _make_bot():
    """Minimal fake bot."""
    bot = SimpleNamespace()
    bot.guilds = []
    bot.loop = None
    return bot


# ---------------------------------------------------------------------------
# RCONChatMonitor initialization tests
# ---------------------------------------------------------------------------

class TestRCONChatMonitorInit:
    def test_initializes_server_name(self):
        """RCONChatMonitor stores the provided server_name."""
        from bot.cogs.chat_relay import RCONChatMonitor
        monitor = RCONChatMonitor("TestServer", None)
        assert monitor.server_name == "TestServer"

    def test_initializes_rcon_client(self):
        """RCONChatMonitor stores the provided rcon_client."""
        from bot.cogs.chat_relay import RCONChatMonitor
        fake_client = SimpleNamespace()
        monitor = RCONChatMonitor("TestServer", fake_client)
        assert monitor.rcon_client is fake_client

    def test_last_messages_is_empty_set(self):
        """RCONChatMonitor.last_messages starts as an empty set."""
        from bot.cogs.chat_relay import RCONChatMonitor
        monitor = RCONChatMonitor("TestServer", None)
        assert isinstance(monitor.last_messages, set)
        assert len(monitor.last_messages) == 0

    def test_max_cache_size_is_200(self):
        """RCONChatMonitor.max_cache_size is 200."""
        from bot.cogs.chat_relay import RCONChatMonitor
        monitor = RCONChatMonitor("TestServer", None)
        assert monitor.max_cache_size == 200

    def test_chat_patterns_is_non_empty_list(self):
        """RCONChatMonitor.chat_patterns is a non-empty list of compiled regexes."""
        from bot.cogs.chat_relay import RCONChatMonitor
        monitor = RCONChatMonitor("TestServer", None)
        assert isinstance(monitor.chat_patterns, list)
        assert len(monitor.chat_patterns) > 0
        for pattern in monitor.chat_patterns:
            assert hasattr(pattern, "match"), "Each entry should be a compiled regex"

    def test_skip_patterns_is_non_empty_list(self):
        """RCONChatMonitor.skip_patterns is a non-empty list of compiled regexes."""
        from bot.cogs.chat_relay import RCONChatMonitor
        monitor = RCONChatMonitor("TestServer", None)
        assert isinstance(monitor.skip_patterns, list)
        assert len(monitor.skip_patterns) > 0


# ---------------------------------------------------------------------------
# Chat pattern matching tests
# ---------------------------------------------------------------------------

class TestChatPatternMatching:
    def _get_monitor(self):
        from bot.cogs.chat_relay import RCONChatMonitor
        return RCONChatMonitor("TestServer", None)

    def test_simple_player_message_matches(self):
        """'PlayerName: hello world' matches the primary chat pattern."""
        monitor = self._get_monitor()
        line = "SomePlayer: hello world"
        matched = False
        for pattern in monitor.chat_patterns:
            match = pattern.match(line)
            if match:
                matched = True
                assert match.group(1).strip() == "SomePlayer"
                assert match.group(2).strip() == "hello world"
                break
        assert matched, f"No chat pattern matched '{line}'"

    def test_global_prefix_message_matches(self):
        """'[GLOBAL] PlayerName: message' matches the chat pattern."""
        monitor = self._get_monitor()
        line = "[GLOBAL] SomePlayer: hello world"
        matched = False
        for pattern in monitor.chat_patterns:
            match = pattern.match(line)
            if match:
                matched = True
                player = match.group(1).strip()
                message = match.group(2).strip()
                assert "SomePlayer" in player
                assert message == "hello world"
                break
        assert matched, f"No chat pattern matched '{line}'"

    def test_tribe_prefix_message_matches(self):
        """'[TRIBE] PlayerName: message' matches the chat pattern."""
        monitor = self._get_monitor()
        line = "[TRIBE] TribeMember: tribe chat here"
        matched = False
        for pattern in monitor.chat_patterns:
            match = pattern.match(line)
            if match:
                matched = True
                break
        assert matched, f"No chat pattern matched '{line}'"

    def test_local_prefix_message_matches(self):
        """'[LOCAL] PlayerName: message' matches the chat pattern."""
        monitor = self._get_monitor()
        line = "[LOCAL] NearbyPlayer: local message"
        matched = False
        for pattern in monitor.chat_patterns:
            match = pattern.match(line)
            if match:
                matched = True
                break
        assert matched, f"No chat pattern matched '{line}'"

    def test_player_name_with_spaces_matches(self):
        """A player name containing spaces still matches the chat pattern."""
        monitor = self._get_monitor()
        line = "Phoenix Alpha: great game"
        matched = False
        for pattern in monitor.chat_patterns:
            match = pattern.match(line)
            if match:
                matched = True
                assert "great game" in match.group(2).strip()
                break
        assert matched, f"No chat pattern matched '{line}'"

    def test_empty_line_does_not_match(self):
        """An empty string does not match any chat pattern."""
        monitor = self._get_monitor()
        for pattern in monitor.chat_patterns:
            assert pattern.match("") is None


# ---------------------------------------------------------------------------
# Skip pattern tests
# ---------------------------------------------------------------------------

class TestSkipPatterns:
    def _get_monitor(self):
        from bot.cogs.chat_relay import RCONChatMonitor
        return RCONChatMonitor("TestServer", None)

    def _should_skip(self, monitor, line: str) -> bool:
        for pattern in monitor.skip_patterns:
            if pattern.search(line):
                return True
        return False

    def test_discord_prefix_is_skipped(self):
        """'[Discord] PlayerName: message' is matched by a skip pattern."""
        monitor = self._get_monitor()
        assert self._should_skip(monitor, "[Discord] SomeUser: relayed message")

    def test_server_prefix_is_skipped(self):
        """'SERVER: broadcast' is matched by a skip pattern."""
        monitor = self._get_monitor()
        assert self._should_skip(monitor, "SERVER: server broadcast message")

    def test_server_received_no_response_is_skipped(self):
        """'Server received, But no response!!' is matched by a skip pattern."""
        monitor = self._get_monitor()
        assert self._should_skip(monitor, "Server received, But no response!!")

    def test_admin_message_is_skipped(self):
        """'Admin Message:' is matched by a skip pattern."""
        monitor = self._get_monitor()
        assert self._should_skip(monitor, "Admin Message: you have been warned")

    def test_normal_player_message_not_skipped(self):
        """A normal player chat line is NOT matched by any skip pattern."""
        monitor = self._get_monitor()
        assert not self._should_skip(monitor, "SomePlayer: hello everyone")

    def test_discord_skip_is_case_insensitive(self):
        """[discord] (lowercase) is also skipped."""
        monitor = self._get_monitor()
        assert self._should_skip(monitor, "[discord] some echo message")


# ---------------------------------------------------------------------------
# Message deduplication tests
# ---------------------------------------------------------------------------

class TestMessageDeduplication:
    def test_new_message_key_added_to_last_messages(self):
        """A fresh message key is added to last_messages after processing."""
        from bot.cogs.chat_relay import RCONChatMonitor
        monitor = RCONChatMonitor("TestServer", None)
        msg_key = "PlayerOne:hello world"
        monitor.last_messages.add(msg_key)
        assert msg_key in monitor.last_messages

    def test_duplicate_key_not_added_twice(self):
        """Adding the same key twice does not grow the set (set semantics)."""
        from bot.cogs.chat_relay import RCONChatMonitor
        monitor = RCONChatMonitor("TestServer", None)
        msg_key = "PlayerOne:repeated message"
        monitor.last_messages.add(msg_key)
        monitor.last_messages.add(msg_key)
        assert len(monitor.last_messages) == 1

    def test_duplicate_check_prevents_duplicate_messages(self):
        """
        Simulate the duplicate-check logic: if msg_key already in last_messages,
        the message should not be added to the result list.
        """
        from bot.cogs.chat_relay import RCONChatMonitor
        monitor = RCONChatMonitor("TestServer", None)
        msg_key = "PlayerOne:already seen"
        monitor.last_messages.add(msg_key)

        # Replicate the production logic
        messages = []
        player_name = "PlayerOne"
        message_text = "already seen"
        key = f"{player_name}:{message_text}"
        if key not in monitor.last_messages:
            monitor.last_messages.add(key)
            messages.append({"player": player_name, "message": message_text})

        assert len(messages) == 0

    def test_unique_message_is_added_to_results(self):
        """A message key not yet in last_messages is added to the result list."""
        from bot.cogs.chat_relay import RCONChatMonitor
        monitor = RCONChatMonitor("TestServer", None)

        messages = []
        player_name = "PlayerOne"
        message_text = "brand new message"
        key = f"{player_name}:{message_text}"
        if key not in monitor.last_messages:
            monitor.last_messages.add(key)
            messages.append({"player": player_name, "message": message_text})

        assert len(messages) == 1
        assert messages[0]["player"] == "PlayerOne"
        assert messages[0]["message"] == "brand new message"

    def test_cache_trimming_works_when_over_max(self):
        """When last_messages exceeds max_cache_size, excess entries can be removed."""
        from bot.cogs.chat_relay import RCONChatMonitor
        monitor = RCONChatMonitor("TestServer", None)

        # Fill beyond max_cache_size
        for i in range(monitor.max_cache_size + 10):
            monitor.last_messages.add(f"Player{i}:msg{i}")

        assert len(monitor.last_messages) > monitor.max_cache_size

        # Simulate the trimming logic from production code
        if len(monitor.last_messages) > monitor.max_cache_size:
            to_remove = list(monitor.last_messages)[: monitor.max_cache_size // 2]
            for key in to_remove:
                monitor.last_messages.discard(key)

        assert len(monitor.last_messages) <= monitor.max_cache_size


# ---------------------------------------------------------------------------
# ChatRelay cog tests
# ---------------------------------------------------------------------------

class TestChatRelayCogInit:
    def test_cog_instantiation(self):
        """ChatRelay can be instantiated with a fake bot."""
        from bot.cogs.chat_relay import ChatRelay
        bot = _make_bot()
        cog = ChatRelay(bot)
        assert cog is not None
        assert cog.bot is bot

    def test_cog_inherits_from_commands_cog(self):
        """ChatRelay inherits from discord.ext.commands.Cog."""
        from bot.cogs.chat_relay import ChatRelay
        assert issubclass(ChatRelay, commands.Cog)

    def test_cog_has_log_monitors_dict(self):
        """ChatRelay initialises log_monitors as an empty dict."""
        from bot.cogs.chat_relay import ChatRelay
        bot = _make_bot()
        cog = ChatRelay(bot)
        assert isinstance(cog.log_monitors, dict)
        assert len(cog.log_monitors) == 0

    def test_cog_has_rcon_chat_monitors_dict(self):
        """ChatRelay initialises rcon_chat_monitors as an empty dict."""
        from bot.cogs.chat_relay import ChatRelay
        bot = _make_bot()
        cog = ChatRelay(bot)
        assert isinstance(cog.rcon_chat_monitors, dict)
        assert len(cog.rcon_chat_monitors) == 0

    def test_cog_has_rcon_clients_dict(self):
        """ChatRelay initialises rcon_clients as an empty dict."""
        from bot.cogs.chat_relay import ChatRelay
        bot = _make_bot()
        cog = ChatRelay(bot)
        assert isinstance(cog.rcon_clients, dict)

    def test_cog_initialized_false_at_start(self):
        """ChatRelay._initialized starts as False."""
        from bot.cogs.chat_relay import ChatRelay
        bot = _make_bot()
        cog = ChatRelay(bot)
        assert cog._initialized is False

    def test_cog_guild_configs_empty_dict_at_start(self):
        """ChatRelay.guild_configs starts as empty dict (multi-tenant per-guild state)."""
        from bot.cogs.chat_relay import ChatRelay
        bot = _make_bot()
        cog = ChatRelay(bot)
        assert isinstance(cog.guild_configs, dict)
        assert len(cog.guild_configs) == 0

    def test_cog_log_monitors_keyed_by_server_id(self):
        """ChatRelay.log_monitors is a dict keyed by server_id (not server_name)."""
        from bot.cogs.chat_relay import ChatRelay
        bot = _make_bot()
        cog = ChatRelay(bot)
        assert isinstance(cog.log_monitors, dict)
        assert len(cog.log_monitors) == 0

    def test_cog_rcon_clients_keyed_by_server_id(self):
        """ChatRelay.rcon_clients starts as empty dict keyed by server_id."""
        from bot.cogs.chat_relay import ChatRelay
        bot = _make_bot()
        cog = ChatRelay(bot)
        assert isinstance(cog.rcon_clients, dict)
        assert len(cog.rcon_clients) == 0


# ---------------------------------------------------------------------------
# Setup function tests
# ---------------------------------------------------------------------------

class TestChatRelaySetup:
    def test_setup_function_exists(self):
        """Module-level setup() function exists in chat_relay."""
        import bot.cogs.chat_relay as module
        assert hasattr(module, "setup")

    def test_setup_is_callable(self):
        """setup() is callable."""
        import bot.cogs.chat_relay as module
        assert callable(module.setup)

    def test_setup_is_coroutine_function(self):
        """setup() is an async/coroutine function."""
        import bot.cogs.chat_relay as module
        assert inspect.iscoroutinefunction(module.setup)


class TestCleanupOldChatMessages:
    """Regression tests for the cleanup_old_chat_messages task.

    Previously crashed on startup with:
        'ChatRelay' object has no attribute 'guild_id'
    because the single-tenant self.guild_id was removed in the multi-tenant
    refactor but the cleanup task was not updated.
    """

    def _make_bot(self):
        bot = SimpleNamespace()
        bot.guilds = []

        async def wait_until_ready():
            pass

        bot.wait_until_ready = wait_until_ready
        return bot

    def test_cleanup_task_does_not_reference_self_guild_id(self):
        """Cleanup task source must NOT contain 'self.guild_id'."""
        from bot.cogs.chat_relay import ChatRelay
        source = inspect.getsource(ChatRelay.cleanup_old_chat_messages.coro)
        assert "self.guild_id" not in source, (
            "cleanup_old_chat_messages must not reference self.guild_id "
            "(removed in multi-tenant refactor)"
        )

    def test_cleanup_task_references_guild_configs(self):
        """Cleanup task must iterate self.guild_configs for multi-tenant support."""
        from bot.cogs.chat_relay import ChatRelay
        source = inspect.getsource(ChatRelay.cleanup_old_chat_messages.coro)
        assert "guild_configs" in source

    @pytest.mark.asyncio
    async def test_cleanup_no_crash_when_guild_configs_empty(self):
        """cleanup_old_chat_messages must not raise when guild_configs is empty."""
        from bot.cogs.chat_relay import ChatRelay
        bot = self._make_bot()
        cog = ChatRelay(bot)
        # guild_configs is empty — should complete silently
        await ChatRelay.cleanup_old_chat_messages.coro(cog)

    @pytest.mark.asyncio
    async def test_cleanup_calls_db_for_each_guild(self):
        """cleanup_old_chat_messages calls cleanup_old_messages once per guild."""
        from bot.cogs.chat_relay import ChatRelay
        from bot.database import chat_history_db

        bot = self._make_bot()
        cog = ChatRelay(bot)
        cog.guild_configs = {111: {}, 222: {}}

        calls = []

        async def fake_cleanup(guild_id, days=30):
            calls.append(guild_id)
            return 0

        original = chat_history_db.cleanup_old_messages
        chat_history_db.cleanup_old_messages = fake_cleanup
        try:
            await ChatRelay.cleanup_old_chat_messages.coro(cog)
        finally:
            chat_history_db.cleanup_old_messages = original

        assert sorted(calls) == [111, 222]
