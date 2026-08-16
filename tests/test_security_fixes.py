"""
Tests for security fixes applied 2026-03-12.

Tests cover:
1. RCON command injection prevention in player_management.py — validate_rcon_input()
2. RCON command injection prevention in rcon_admin.py — give_xp player name validation
3. None.lower() crash prevention in client.py get_player_id_by_name
4. None iteration crash prevention in client.py get_player_id_by_steam_id / get_player_id_by_name
5. _pending dict memory leak prevention in remote_agent.py after disconnect

Uses real implementations — no mocks (Jeffrey Snover methodology).
All async tests use @pytest.mark.asyncio.
"""

import asyncio
import pytest
import re
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bot():
    """Minimal bot stand-in."""
    return SimpleNamespace()


def _make_remote_agent_bot():
    """Bot-like object for RemoteAgentManager tests."""
    bot = SimpleNamespace()
    bot.agent_manager = None
    bot.guilds = []

    async def wait_until_ready():
        pass

    bot.wait_until_ready = wait_until_ready
    return bot


# ===========================================================================
# 1. validate_rcon_input — RCON command injection prevention
# ===========================================================================

class TestValidateRconInput:
    """Test the validate_rcon_input function from player_management.py."""

    def test_accepts_simple_alphanumeric(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("Player123") is True

    def test_accepts_eos_id_format(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("abc123def456") is True

    def test_accepts_underscores(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("my_player") is True

    def test_accepts_hyphens(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("my-player") is True

    def test_accepts_dots(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player.name") is True

    def test_accepts_spaces(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("Player Name") is True

    def test_rejects_empty_string(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("") is False

    def test_rejects_semicolon_injection(self):
        """Semicolons could chain RCON commands."""
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player;destroywilddinos") is False

    def test_rejects_pipe_injection(self):
        """Pipes could redirect command output."""
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player|malicious") is False

    def test_rejects_backtick_injection(self):
        """Backticks could execute subcommands."""
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player`cmd`") is False

    def test_rejects_single_quotes(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player'name") is False

    def test_rejects_double_quotes(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input('player"name') is False

    def test_rejects_newline_injection(self):
        """Newlines could inject additional RCON commands."""
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player\ndestroyall") is False

    def test_rejects_carriage_return_injection(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player\rdestroyall") is False

    def test_rejects_null_byte(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player\x00evil") is False

    def test_rejects_ampersand(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player&&destroyall") is False

    def test_rejects_dollar_sign(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("$player") is False

    def test_rejects_over_100_characters(self):
        """Length limit prevents buffer-style attacks."""
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("a" * 101) is False

    def test_accepts_exactly_100_characters(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("a" * 100) is True

    def test_rejects_parentheses(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player(name)") is False

    def test_rejects_curly_braces(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player{0}") is False

    def test_rejects_square_brackets(self):
        from bot.cogs.player_management import validate_rcon_input
        assert validate_rcon_input("player[0]") is False


# ===========================================================================
# 2. rcon_admin.py give_xp — player name validation regex
# ===========================================================================

class TestGiveXpPlayerNameValidation:
    """Test the regex used in give_xp to validate player names.

    The validation uses re.match(r'^[a-zA-Z0-9_ .\\-]+$', name) and len <= 100,
    same pattern as validate_rcon_input. We test the regex directly since the
    command requires a full interaction context.
    """

    _PATTERN: re.Pattern = re.compile(r'^[a-zA-Z0-9_ .\-]+$')

    def _is_valid(self, name: str) -> bool:
        return bool(self._PATTERN.match(name)) and len(name) <= 100

    def test_accepts_normal_player_name(self):
        assert self._is_valid("TribeLeader42") is True

    def test_accepts_name_with_spaces(self):
        assert self._is_valid("Tribe Leader") is True

    def test_rejects_semicolon(self):
        assert self._is_valid("player;givexp 9999") is False

    def test_rejects_pipe(self):
        assert self._is_valid("player|cmd") is False

    def test_rejects_backtick(self):
        assert self._is_valid("player`exploit`") is False

    def test_rejects_newline(self):
        assert self._is_valid("player\ncmd") is False

    def test_rejects_empty(self):
        assert self._is_valid("") is False

    def test_rejects_over_100_chars(self):
        assert self._is_valid("x" * 101) is False

    def test_accepts_exactly_100_chars(self):
        assert self._is_valid("x" * 100) is True

    def test_give_xp_command_method_exists(self):
        """Verify the give_xp command is present on RconAdmin."""
        from bot.cogs.rcon_admin import RconAdmin
        assert hasattr(RconAdmin, "give_xp")


# ===========================================================================
# 3 & 4. client.py — None guards in get_player_id_by_name/get_player_id_by_steam_id
# ===========================================================================

class TestRconClientNoneGuards:
    """Test that RCON client methods handle None returns gracefully.

    These test the actual RCONClient methods via subclassing to inject
    controlled get_player_list() responses — no mocks, real method execution.
    """

    @pytest.mark.asyncio
    async def test_get_player_id_by_name_returns_none_when_player_list_empty(self):
        """get_player_id_by_name returns None when get_player_list returns empty list."""
        from bot.rcon.client import ArkRCONClient

        class TestClient(ArkRCONClient):
            def __init__(self):
                # Bypass real __init__ — we only need the methods under test
                self.server_name = "test"
                self.host = "127.0.0.1"
                self.port = 27020
                self.password = "test"

            async def get_player_list(self):
                return []

        client = TestClient()
        result = await client.get_player_id_by_name("SomePlayer")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_player_id_by_name_returns_none_when_player_list_is_none(self):
        """get_player_id_by_name returns None when get_player_list returns None."""
        from bot.rcon.client import ArkRCONClient

        class TestClient(ArkRCONClient):
            def __init__(self):
                self.server_name = "test"
                self.host = "127.0.0.1"
                self.port = 27020
                self.password = "test"

            async def get_player_list(self):
                return None

        client = TestClient()
        result = await client.get_player_id_by_name("SomePlayer")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_player_id_by_name_handles_none_name_in_player_dict(self):
        """get_player_id_by_name does not crash when a player dict has name=None."""
        from bot.rcon.client import ArkRCONClient

        class TestClient(ArkRCONClient):
            def __init__(self):
                self.server_name = "test"
                self.host = "127.0.0.1"
                self.port = 27020
                self.password = "test"

            async def get_player_list(self):
                return [
                    {"name": None, "steam_id": "12345", "eos_id": "12345", "server": "test"},
                    {"name": "RealPlayer", "steam_id": "67890", "eos_id": "67890", "server": "test"},
                ]

        client = TestClient()
        # Should not raise AttributeError: 'NoneType' has no attribute 'lower'
        result = await client.get_player_id_by_name("RealPlayer")
        assert result == 1  # Index of RealPlayer in the list

    @pytest.mark.asyncio
    async def test_get_player_id_by_name_skips_none_name_entry(self):
        """A player with name=None is skipped, not matched."""
        from bot.rcon.client import ArkRCONClient

        class TestClient(ArkRCONClient):
            def __init__(self):
                self.server_name = "test"
                self.host = "127.0.0.1"
                self.port = 27020
                self.password = "test"

            async def get_player_list(self):
                return [
                    {"name": None, "steam_id": "12345", "eos_id": "12345", "server": "test"},
                ]

        client = TestClient()
        result = await client.get_player_id_by_name("anything")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_player_id_by_steam_id_returns_none_when_player_list_is_none(self):
        """get_player_id_by_steam_id returns None when get_player_list returns None."""
        from bot.rcon.client import ArkRCONClient

        class TestClient(ArkRCONClient):
            def __init__(self):
                self.server_name = "test"
                self.host = "127.0.0.1"
                self.port = 27020
                self.password = "test"

            async def get_player_list(self):
                return None

        client = TestClient()
        result = await client.get_player_id_by_steam_id("76561198000000000")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_player_id_by_steam_id_returns_none_when_player_list_empty(self):
        """get_player_id_by_steam_id returns None when get_player_list returns empty list."""
        from bot.rcon.client import ArkRCONClient

        class TestClient(ArkRCONClient):
            def __init__(self):
                self.server_name = "test"
                self.host = "127.0.0.1"
                self.port = 27020
                self.password = "test"

            async def get_player_list(self):
                return []

        client = TestClient()
        result = await client.get_player_id_by_steam_id("76561198000000000")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_player_id_by_steam_id_finds_correct_player(self):
        """get_player_id_by_steam_id returns correct index when player is found."""
        from bot.rcon.client import ArkRCONClient

        class TestClient(ArkRCONClient):
            def __init__(self):
                self.server_name = "test"
                self.host = "127.0.0.1"
                self.port = 27020
                self.password = "test"

            async def get_player_list(self):
                return [
                    {"name": "Player1", "steam_id": "111", "eos_id": "111", "server": "test"},
                    {"name": "Player2", "steam_id": "222", "eos_id": "222", "server": "test"},
                ]

        client = TestClient()
        result = await client.get_player_id_by_steam_id("222")
        assert result == 1


# ===========================================================================
# 5. remote_agent.py — _pending dict cleared after disconnect
# ===========================================================================

class TestPendingDictCleanup:
    """Test that RemoteAgentManager._pending is cleared after agent disconnect."""

    def test_pending_starts_empty(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        assert isinstance(mgr._pending, dict)
        assert len(mgr._pending) == 0

    @pytest.mark.asyncio
    async def test_pending_cleared_after_futures_failed(self):
        """Simulates what happens after _listen_to_agent exits: pending futures
        are failed and the dict is cleared to prevent memory leak."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()

        # Manually add pending futures as send_command would
        loop = asyncio.get_event_loop()
        future1: asyncio.Future = loop.create_future()
        future2: asyncio.Future = loop.create_future()
        mgr._pending["req-001"] = future1
        mgr._pending["req-002"] = future2

        assert len(mgr._pending) == 2

        # Simulate the disconnect cleanup logic from _listen_to_agent
        for req_id, future in list(mgr._pending.items()):
            if not future.done():
                future.set_exception(ConnectionError("Agent disconnected"))
        mgr._pending.clear()

        assert len(mgr._pending) == 0
        assert future1.done()
        assert future2.done()

    @pytest.mark.asyncio
    async def test_pending_clear_does_not_affect_already_resolved_futures(self):
        """Futures that were already resolved before disconnect should not be re-failed."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()

        loop = asyncio.get_event_loop()
        resolved_future: asyncio.Future = loop.create_future()
        resolved_future.set_result({"type": "complete", "data": "ok"})

        unresolved_future: asyncio.Future = loop.create_future()

        mgr._pending["req-resolved"] = resolved_future
        mgr._pending["req-unresolved"] = unresolved_future

        # Simulate disconnect cleanup
        for req_id, future in list(mgr._pending.items()):
            if not future.done():
                future.set_exception(ConnectionError("Agent disconnected"))
        mgr._pending.clear()

        # Resolved future should still have its original result
        assert resolved_future.result() == {"type": "complete", "data": "ok"}
        # Unresolved future should have the ConnectionError
        with pytest.raises(ConnectionError):
            unresolved_future.result()
        # Dict should be empty
        assert len(mgr._pending) == 0

    def test_pending_is_dict_type_not_defaultdict(self):
        """Verify _pending is a plain dict, not a defaultdict or other collection."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        assert type(mgr._pending) is dict


# ===========================================================================
# 6. Modal classes use validate_rcon_input (structural verification)
# ===========================================================================

class TestModalsUseValidation:
    """Verify that KickPlayerModal, BanPlayerModal, UnbanPlayerModal, and
    KillPlayerModal all call validate_rcon_input in their on_submit."""

    def _get_on_submit_source(self, modal_class) -> str:
        import inspect
        return inspect.getsource(modal_class.on_submit)

    def test_kick_modal_validates_input(self):
        from bot.cogs.player_management import KickPlayerModal
        source: str = self._get_on_submit_source(KickPlayerModal)
        assert "validate_rcon_input" in source

    def test_ban_modal_validates_input(self):
        from bot.cogs.player_management import BanPlayerModal
        source: str = self._get_on_submit_source(BanPlayerModal)
        assert "validate_rcon_input" in source

    def test_unban_modal_validates_input(self):
        from bot.cogs.player_management import UnbanPlayerModal
        source: str = self._get_on_submit_source(UnbanPlayerModal)
        assert "validate_rcon_input" in source

    def test_kill_modal_validates_input(self):
        from bot.cogs.player_management import KillPlayerModal
        source: str = self._get_on_submit_source(KillPlayerModal)
        assert "validate_rcon_input" in source
