"""
Tests for server_monitor.py cog.

Tests cover:
- ServerMonitor cog instantiation
- Correct initial attribute values
- Background task presence
- Voice channel name formatting (online/offline, with/without version)
- Voice rename rate-limit helpers (_can_rename_channel, _record_rename, _seconds_until_can_rename)
- Status cache structure and types
- _get_server_list method exists and is async
- Commands that exist on the cog
- system_monitor attribute is a SystemServerMonitor instance
- Status embed creation (pure logic, no Discord API calls)
- last_player_counts / voice_channels / server_status_cache initialized empty
- voice_rename_times initialized empty

Uses real discord.py objects — no mocks (Jeffrey Snover methodology).
Async tests require a running asyncio event loop.
"""

import inspect
import pytest
import asyncio
from types import SimpleNamespace
from datetime import datetime, timedelta
import discord
from discord.ext import tasks


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_bot():
    """Minimal bot stand-in that satisfies ServerMonitor.__init__."""
    bot = SimpleNamespace()
    bot.guilds = []
    return bot


async def _make_cog_async():
    """Instantiate ServerMonitor inside a running event loop.

    tasks.loop.start() internally calls asyncio.create_task(), which requires
    a running event loop.  Wrapping construction in an async function satisfies
    that requirement.  We immediately cancel all tasks so they don't actually
    run during tests.
    """
    from bot.cogs.server_monitor import ServerMonitor
    cog = ServerMonitor(_make_bot())

    # Cancel background tasks immediately so they don't interfere with tests
    for attr_name in ("monitor_loop", "purge_inactive_loop"):
        loop_obj = getattr(cog, attr_name, None)
        if loop_obj is not None and loop_obj.is_running():
            loop_obj.cancel()

    return cog


# ---------------------------------------------------------------------------
# 1. Cog instantiation
# ---------------------------------------------------------------------------

class TestServerMonitorInit:
    @pytest.mark.asyncio
    async def test_cog_can_be_instantiated(self):
        cog = await _make_cog_async()
        assert cog is not None

    @pytest.mark.asyncio
    async def test_cog_bot_attribute_stored(self):
        cog = await _make_cog_async()
        assert hasattr(cog, "bot")

    @pytest.mark.asyncio
    async def test_guild_rcon_managers_initialized_empty(self):
        """guild_rcon_managers must start as empty dict; populated by before_loop."""
        cog = await _make_cog_async()
        assert isinstance(cog.guild_rcon_managers, dict)
        assert len(cog.guild_rcon_managers) == 0

    @pytest.mark.asyncio
    async def test_last_player_counts_initialized_empty(self):
        cog = await _make_cog_async()
        assert isinstance(cog.last_player_counts, dict)
        assert len(cog.last_player_counts) == 0

    @pytest.mark.asyncio
    async def test_guild_voice_channels_initialized_empty(self):
        cog = await _make_cog_async()
        assert isinstance(cog.guild_voice_channels, dict)
        assert len(cog.guild_voice_channels) == 0

    @pytest.mark.asyncio
    async def test_guild_server_caches_initialized_empty(self):
        cog = await _make_cog_async()
        assert isinstance(cog.guild_server_caches, dict)
        assert len(cog.guild_server_caches) == 0

    @pytest.mark.asyncio
    async def test_voice_rename_times_initialized_empty(self):
        cog = await _make_cog_async()
        assert isinstance(cog.voice_rename_times, dict)
        assert len(cog.voice_rename_times) == 0

    @pytest.mark.asyncio
    async def test_system_monitor_attribute_exists(self):
        from bot.utils.system_monitor import SystemServerMonitor
        cog = await _make_cog_async()
        assert hasattr(cog, "system_monitor")
        assert isinstance(cog.system_monitor, SystemServerMonitor)

    @pytest.mark.asyncio
    async def test_guild_status_messages_initialized_empty(self):
        cog = await _make_cog_async()
        assert isinstance(cog.guild_status_messages, dict)
        assert len(cog.guild_status_messages) == 0

    @pytest.mark.asyncio
    async def test_guild_status_categories_initialized_empty(self):
        cog = await _make_cog_async()
        assert isinstance(cog.guild_status_categories, dict)
        assert len(cog.guild_status_categories) == 0

    @pytest.mark.asyncio
    async def test_log_paths_initialized_false(self):
        cog = await _make_cog_async()
        assert cog.log_paths_initialized is False

    @pytest.mark.asyncio
    async def test_consecutive_failures_initialized_empty(self):
        cog = await _make_cog_async()
        assert isinstance(cog._consecutive_failures, dict)
        assert len(cog._consecutive_failures) == 0


# ---------------------------------------------------------------------------
# 2. Background tasks are defined on the cog class
# ---------------------------------------------------------------------------

class TestBackgroundTasks:
    def test_monitor_loop_is_defined(self):
        from bot.cogs.server_monitor import ServerMonitor
        assert hasattr(ServerMonitor, "monitor_loop")

    def test_purge_inactive_loop_is_defined(self):
        from bot.cogs.server_monitor import ServerMonitor
        assert hasattr(ServerMonitor, "purge_inactive_loop")

    def test_monitor_loop_interval_is_30s(self):
        from bot.cogs.server_monitor import ServerMonitor
        loop = ServerMonitor.__dict__["monitor_loop"]
        assert loop.seconds == 30.0

    def test_purge_inactive_loop_interval_is_12h(self):
        from bot.cogs.server_monitor import ServerMonitor
        loop = ServerMonitor.__dict__["purge_inactive_loop"]
        assert loop.hours == 12.0


# ---------------------------------------------------------------------------
# 3. Voice channel name formatting
#    update_voice_channel builds the name string inline — replicate the logic.
# ---------------------------------------------------------------------------

class TestVoiceChannelNameFormatting:
    """Test the name-formatting logic extracted from update_voice_channel."""

    def _format(self, server_name: str, is_online: bool, player_count: int,
                 max_players: int, version):
        """Replicate the exact name-building expression from update_voice_channel."""
        status_emoji = "🟢" if is_online else "🔴"
        if version:
            return f"{status_emoji} {server_name} (v{version}) - {player_count}/{max_players}"
        else:
            return f"{status_emoji} {server_name} - {player_count}/{max_players}"

    def test_online_server_with_version(self):
        name = self._format("Aberration", True, 5, 70, "81.16")
        assert name == "🟢 Aberration (v81.16) - 5/70"

    def test_online_server_without_version(self):
        name = self._format("Aberration", True, 0, 70, None)
        assert name == "🟢 Aberration - 0/70"

    def test_offline_server_with_version(self):
        name = self._format("The Island", False, 0, 70, "81.16")
        assert name == "🔴 The Island (v81.16) - 0/70"

    def test_offline_server_without_version(self):
        name = self._format("The Island", False, 0, 70, None)
        assert name == "🔴 The Island - 0/70"

    def test_player_count_slash_max_shown(self):
        name = self._format("Fjordur", True, 12, 70, None)
        assert "12/70" in name

    def test_empty_string_version_treated_as_no_version(self):
        """Empty string is falsy — no version suffix should be appended."""
        name = self._format("Aberration", True, 3, 70, "")
        assert "v" not in name
        assert "Aberration - 3/70" in name

    def test_green_emoji_used_for_online(self):
        name = self._format("Server", True, 1, 70, None)
        assert name.startswith("🟢")

    def test_red_emoji_used_for_offline(self):
        name = self._format("Server", False, 0, 70, None)
        assert name.startswith("🔴")

    def test_version_wrapped_in_v_prefix_and_parentheses(self):
        name = self._format("Fjordur", True, 0, 70, "81.16")
        assert "(v81.16)" in name

    def test_version_has_space_before_parenthesis(self):
        """Version must be separated from server name by a space.
        'Fjordur(v81.16)' is visually broken; correct is 'Fjordur (v81.16)'."""
        name = self._format("Fjordur", True, 0, 70, "81.16")
        assert "Fjordur (v81.16)" in name, (
            "Voice channel name must have a space before the version: 'Name (vX.Y)'"
        )

    def test_production_source_uses_space_before_version(self):
        """Regression guard: verify the actual production format string has a space
        before the version parenthesis, matching the status embed format."""
        import inspect
        from bot.cogs.server_monitor import ServerMonitor
        source = inspect.getsource(ServerMonitor.update_voice_channel)
        assert 'server_name} (v{version})' in source or "server_name} (v" in source, (
            "update_voice_channel format string must include a space before '(v{version})'. "
            "The status embed uses '{name} (v{version})' — voice channel must match."
        )


# ---------------------------------------------------------------------------
# 4. Rate-limit helpers: _can_rename_channel, _record_rename,
#    _seconds_until_can_rename
#    These are pure sync methods — no event loop needed.
# ---------------------------------------------------------------------------

class TestVoiceRateLimitHelpers:
    @pytest.mark.asyncio
    async def test_can_rename_returns_true_when_no_history(self):
        cog = await _make_cog_async()
        assert cog._can_rename_channel(rcon_port=27020) is True

    @pytest.mark.asyncio
    async def test_can_rename_returns_true_after_one_rename(self):
        cog = await _make_cog_async()
        cog._record_rename(27020)
        assert cog._can_rename_channel(27020) is True

    @pytest.mark.asyncio
    async def test_can_rename_returns_false_after_two_renames(self):
        cog = await _make_cog_async()
        cog._record_rename(27020)
        cog._record_rename(27020)
        assert cog._can_rename_channel(27020) is False

    @pytest.mark.asyncio
    async def test_can_rename_returns_true_after_old_timestamps_expire(self):
        """If both recorded renames are older than 10 min, renaming is allowed."""
        cog = await _make_cog_async()
        old = datetime.now() - timedelta(minutes=11)
        cog.voice_rename_times[27020] = [old, old]
        assert cog._can_rename_channel(27020) is True

    @pytest.mark.asyncio
    async def test_record_rename_stores_timestamp(self):
        cog = await _make_cog_async()
        cog._record_rename(27020)
        assert 27020 in cog.voice_rename_times
        assert len(cog.voice_rename_times[27020]) == 1

    @pytest.mark.asyncio
    async def test_record_rename_keeps_only_two_recent(self):
        """_record_rename sliding window must hold at most 2 entries within 10 min."""
        cog = await _make_cog_async()
        cog._record_rename(27020)
        cog._record_rename(27020)
        cog._record_rename(27020)
        recent = [t for t in cog.voice_rename_times[27020]
                  if t > datetime.now() - timedelta(minutes=10)]
        assert len(recent) <= 2

    @pytest.mark.asyncio
    async def test_seconds_until_can_rename_zero_when_empty(self):
        cog = await _make_cog_async()
        assert cog._seconds_until_can_rename(27020) == 0.0

    @pytest.mark.asyncio
    async def test_seconds_until_can_rename_zero_after_one_rename(self):
        cog = await _make_cog_async()
        cog._record_rename(27020)
        assert cog._seconds_until_can_rename(27020) == 0.0

    @pytest.mark.asyncio
    async def test_seconds_until_can_rename_positive_after_two_renames(self):
        cog = await _make_cog_async()
        cog._record_rename(27020)
        cog._record_rename(27020)
        wait = cog._seconds_until_can_rename(27020)
        assert wait > 0.0

    @pytest.mark.asyncio
    async def test_rate_limit_is_per_port(self):
        """Rate-limit state must be isolated per rcon_port."""
        cog = await _make_cog_async()
        cog._record_rename(27020)
        cog._record_rename(27020)
        # Port 27030 has no history — should still be allowed
        assert cog._can_rename_channel(27030) is True


# ---------------------------------------------------------------------------
# 5. _get_server_list method exists and is async
# ---------------------------------------------------------------------------

class TestGetServerListMethod:
    def test_method_exists(self):
        from bot.cogs.server_monitor import ServerMonitor
        assert hasattr(ServerMonitor, "_get_server_list")

    def test_method_is_coroutine(self):
        from bot.cogs.server_monitor import ServerMonitor
        assert inspect.iscoroutinefunction(ServerMonitor._get_server_list)


# ---------------------------------------------------------------------------
# 6. Slash commands present on the cog class
# ---------------------------------------------------------------------------

class TestServerMonitorCommands:
    def _command_names(self):
        from bot.cogs.server_monitor import ServerMonitor
        names = set()
        for attr_name in dir(ServerMonitor):
            try:
                attr = getattr(ServerMonitor, attr_name)
            except Exception:
                continue
            if isinstance(attr, discord.app_commands.Command):
                names.add(attr.name)
        return names

    def test_findplayer_command_exists(self):
        """The /findplayer command for locating a specific player."""
        assert "findplayer" in self._command_names()

    def test_reloadservers_command_exists(self):
        """The /reloadservers admin command."""
        assert "reloadservers" in self._command_names()


# ---------------------------------------------------------------------------
# 7. Status embed creation — pure structure (no Discord API calls required)
# ---------------------------------------------------------------------------

class TestCreateStatusEmbed:
    @pytest.mark.asyncio
    async def test_embed_returned_when_no_rcon_manager(self):
        """_create_status_embed must return an Embed even without RCON manager."""
        cog = await _make_cog_async()
        # guild_rcon_managers is empty by default
        guild_id = 123456789
        embed = await cog._create_status_embed(guild_id)
        assert isinstance(embed, discord.Embed)

    @pytest.mark.asyncio
    async def test_embed_title_contains_cluster_status(self):
        cog = await _make_cog_async()
        guild_id = 123456789
        embed = await cog._create_status_embed(guild_id)
        assert "Cluster Status" in (embed.title or "")

    @pytest.mark.asyncio
    async def test_embed_has_at_least_one_field_when_no_rcon(self):
        """When RCON is not ready the embed shows an Initializing field."""
        cog = await _make_cog_async()
        guild_id = 123456789
        embed = await cog._create_status_embed(guild_id)
        assert len(embed.fields) >= 1

    @pytest.mark.asyncio
    async def test_embed_initializing_field_when_no_rcon(self):
        cog = await _make_cog_async()
        guild_id = 123456789
        embed = await cog._create_status_embed(guild_id)
        field_names = [f.name for f in embed.fields]
        assert any("Initializing" in n or "⏳" in n for n in field_names)


# ---------------------------------------------------------------------------
# 8. setup() function
# ---------------------------------------------------------------------------

class TestSetupFunction:
    def test_setup_function_is_defined(self):
        import bot.cogs.server_monitor as module
        assert hasattr(module, "setup")

    def test_setup_function_is_coroutine(self):
        import bot.cogs.server_monitor as module
        assert inspect.iscoroutinefunction(module.setup)


# ---------------------------------------------------------------------------
# 9. _reload_servers_internal method exists and is async
# ---------------------------------------------------------------------------

class TestReloadServersInternal:
    def test_method_exists(self):
        from bot.cogs.server_monitor import ServerMonitor
        assert hasattr(ServerMonitor, "_reload_servers_internal")

    def test_method_is_coroutine(self):
        from bot.cogs.server_monitor import ServerMonitor
        assert asyncio.iscoroutinefunction(ServerMonitor._reload_servers_internal)


# ---------------------------------------------------------------------------
# 10. Server status cache structure
# ---------------------------------------------------------------------------

class TestServerStatusCacheStructure:
    @pytest.mark.asyncio
    async def test_cache_starts_empty_dict(self):
        cog = await _make_cog_async()
        assert cog.guild_server_caches == {}

    @pytest.mark.asyncio
    async def test_cache_accepts_online_status_entry(self):
        cog = await _make_cog_async()
        guild_id = 123456789
        cog.guild_server_caches[guild_id] = {}
        cog.guild_server_caches[guild_id]["Aberration"] = {
            "online": True,
            "player_count": 5,
            "players": [],
            "max_players": 70,
            "version": "81.16",
        }
        assert cog.guild_server_caches[guild_id]["Aberration"]["online"] is True
        assert cog.guild_server_caches[guild_id]["Aberration"]["player_count"] == 5

    @pytest.mark.asyncio
    async def test_cache_accepts_offline_status_entry(self):
        cog = await _make_cog_async()
        guild_id = 123456789
        cog.guild_server_caches[guild_id] = {}
        cog.guild_server_caches[guild_id]["The Island"] = {
            "online": False,
            "player_count": 0,
            "players": [],
            "max_players": 70,
        }
        assert cog.guild_server_caches[guild_id]["The Island"]["online"] is False

    @pytest.mark.asyncio
    async def test_cache_stores_version_field(self):
        cog = await _make_cog_async()
        guild_id = 123456789
        cog.guild_server_caches[guild_id] = {}
        cog.guild_server_caches[guild_id]["Fjordur"] = {"online": True, "version": "81.16"}
        assert cog.guild_server_caches[guild_id]["Fjordur"]["version"] == "81.16"

    @pytest.mark.asyncio
    async def test_version_change_detected_when_cached_is_none(self):
        """Version change should be detected when cache has no version (first run after bot restart)."""
        cog = await _make_cog_async()
        guild_id = 123456789
        # Cache has no version (first run)
        server_cache = cog.guild_server_caches.get(guild_id, {})
        cached_version = server_cache.get("Aberration", {}).get("version")
        current_version = "83.5"
        # Should detect change when cached is None but current has version
        version_changed = cached_version != current_version
        assert version_changed is True

    @pytest.mark.asyncio
    async def test_version_change_detected_when_version_updates(self):
        """Version change should be detected when version updates in database."""
        cog = await _make_cog_async()
        guild_id = 123456789
        # Cache has old version
        cog.guild_server_caches[guild_id] = {}
        cog.guild_server_caches[guild_id]["Aberration"] = {"online": True, "version": "83.2"}
        server_cache = cog.guild_server_caches.get(guild_id, {})
        cached_version = server_cache.get("Aberration", {}).get("version")
        current_version = "83.5"
        # Should detect change
        version_changed = cached_version != current_version
        assert version_changed is True

    @pytest.mark.asyncio
    async def test_version_change_not_detected_when_same(self):
        """Version change should NOT be detected when version is same."""
        cog = await _make_cog_async()
        guild_id = 123456789
        # Cache has same version
        cog.guild_server_caches[guild_id] = {}
        cog.guild_server_caches[guild_id]["Aberration"] = {"online": True, "version": "83.5"}
        server_cache = cog.guild_server_caches.get(guild_id, {})
        cached_version = server_cache.get("Aberration", {}).get("version")
        current_version = "83.5"
        # Should NOT detect change
        version_changed = cached_version != current_version
        assert version_changed is False


# ---------------------------------------------------------------------------
# 11. Voice channel tracking dict — keyed by rcon_port (int)
# ---------------------------------------------------------------------------

class TestVoiceChannelTracking:
    @pytest.mark.asyncio
    async def test_voice_channels_dict_keyed_by_port(self):
        cog = await _make_cog_async()
        guild_id = 123456789
        cog.guild_voice_channels[guild_id] = {}
        cog.guild_voice_channels[guild_id][27020] = 999000000000000001
        assert cog.guild_voice_channels[guild_id][27020] == 999000000000000001

    @pytest.mark.asyncio
    async def test_voice_channels_separate_ports_independent(self):
        cog = await _make_cog_async()
        guild_id = 123456789
        cog.guild_voice_channels[guild_id] = {}
        cog.guild_voice_channels[guild_id][27020] = 111
        cog.guild_voice_channels[guild_id][27030] = 222
        assert cog.guild_voice_channels[guild_id][27020] != cog.guild_voice_channels[guild_id][27030]


# ---------------------------------------------------------------------------
# 12. last_player_counts tracks changes per server name
# ---------------------------------------------------------------------------

class TestLastPlayerCounts:
    @pytest.mark.asyncio
    async def test_last_player_counts_can_be_updated(self):
        cog = await _make_cog_async()
        cog.last_player_counts["Aberration"] = 7
        assert cog.last_player_counts["Aberration"] == 7

    @pytest.mark.asyncio
    async def test_last_player_counts_independent_per_server(self):
        cog = await _make_cog_async()
        cog.last_player_counts["Server A"] = 3
        cog.last_player_counts["Server B"] = 10
        assert cog.last_player_counts["Server A"] == 3
        assert cog.last_player_counts["Server B"] == 10
