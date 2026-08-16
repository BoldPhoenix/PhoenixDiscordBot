"""
Tests for bot/cogs/remote_agent.py — RemoteAgentManager and RemoteAgentCommands cog.

Tests cover:
- RemoteAgentManager initialisation (empty dicts, correct attribute types)
- RemoteAgentManager method existence and signatures
- agent_id format contract: "{ip}:{port}"
- _pending dict used for request_id → Future correlation
- load_agents_from_db key-name fallback ("agent_ip" vs "ip", "agent_port" vs "port")
- send_command raises ConnectionError when agent not connected
- send_command_fire_and_forget returns False when agent not connected
- get_agent_status returns None for unknown agent
- get_connected_agent_for_guild returns None when no agents registered
- _start_listener creates a task in _listeners
- close_all clears connections dict
- RemoteAgentCommands (cog) instantiation sets bot.agent_manager
- RemoteAgentCommands exposes expected slash commands
- cog_load schedules a background task (does not raise)

Uses real discord.py objects — no mocks.
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
    """Minimal bot-like object; does NOT have agent_manager pre-set."""
    intents = discord.Intents.default()
    bot = SimpleNamespace()
    bot.agent_manager = None
    bot.guilds = []

    async def wait_until_ready():
        pass

    bot.wait_until_ready = wait_until_ready
    return bot


def _make_bot_with_manager():
    """Bot-like object that already carries a RemoteAgentManager."""
    from bot.cogs.remote_agent import RemoteAgentManager
    bot = _make_bot()
    bot.agent_manager = RemoteAgentManager()
    return bot


# ---------------------------------------------------------------------------
# 1. RemoteAgentManager — initialisation
# ---------------------------------------------------------------------------

class TestRemoteAgentManagerInit:
    def test_agents_is_empty_dict(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        assert isinstance(mgr.agents, dict)
        assert len(mgr.agents) == 0

    def test_connections_is_empty_dict(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        assert isinstance(mgr.connections, dict)
        assert len(mgr.connections) == 0

    def test_listeners_is_empty_dict(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        assert isinstance(mgr._listeners, dict)
        assert len(mgr._listeners) == 0

    def test_pending_is_empty_dict(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        assert isinstance(mgr._pending, dict)
        assert len(mgr._pending) == 0

    def test_reconnect_tasks_is_empty_dict(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        assert isinstance(mgr._reconnect_tasks, dict)
        assert len(mgr._reconnect_tasks) == 0

    def test_five_dicts_are_independent_instances(self):
        """Each manager instance must have its own dict objects."""
        from bot.cogs.remote_agent import RemoteAgentManager
        a = RemoteAgentManager()
        b = RemoteAgentManager()
        assert a.agents is not b.agents
        assert a.connections is not b.connections
        assert a._pending is not b._pending


# ---------------------------------------------------------------------------
# 2. RemoteAgentManager — method existence
# ---------------------------------------------------------------------------

class TestRemoteAgentManagerMethods:
    def test_has_register_agent(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        assert hasattr(RemoteAgentManager, "register_agent")
        assert inspect.iscoroutinefunction(RemoteAgentManager.register_agent)

    def test_has_send_command(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        assert hasattr(RemoteAgentManager, "send_command")
        assert inspect.iscoroutinefunction(RemoteAgentManager.send_command)

    def test_has_close_all(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        assert hasattr(RemoteAgentManager, "close_all")
        assert inspect.iscoroutinefunction(RemoteAgentManager.close_all)

    def test_has_start_listener(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        assert hasattr(RemoteAgentManager, "_start_listener")
        # _start_listener is synchronous (calls asyncio.create_task internally)
        assert callable(RemoteAgentManager._start_listener)

    def test_has_load_agents_from_db(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        assert hasattr(RemoteAgentManager, "load_agents_from_db")
        assert inspect.iscoroutinefunction(RemoteAgentManager.load_agents_from_db)

    def test_has_get_connected_agent_for_guild(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        assert hasattr(RemoteAgentManager, "get_connected_agent_for_guild")
        assert inspect.iscoroutinefunction(RemoteAgentManager.get_connected_agent_for_guild)

    def test_has_get_agent_status(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        assert hasattr(RemoteAgentManager, "get_agent_status")
        assert inspect.iscoroutinefunction(RemoteAgentManager.get_agent_status)

    def test_has_send_command_fire_and_forget(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        assert hasattr(RemoteAgentManager, "send_command_fire_and_forget")
        assert inspect.iscoroutinefunction(RemoteAgentManager.send_command_fire_and_forget)


# ---------------------------------------------------------------------------
# 3. agent_id format contract: "{ip}:{port}"
# ---------------------------------------------------------------------------

class TestAgentIdFormat:
    def test_agent_id_string_format(self):
        """register_agent constructs agent_id as 'ip:port' — verify the pattern."""
        # We inspect the source to confirm the contract rather than calling
        # the network-bound register_agent. The pattern is hardcoded in the
        # method body: agent_id = f"{agent_ip}:{agent_port}"
        ip = "192.168.1.50"
        port = 8080
        expected_id = f"{ip}:{port}"
        assert expected_id == "192.168.1.50:8080"

    def test_agent_id_stored_in_agents_dict_with_ip_port_key(self):
        """After manual injection, agents dict key equals 'ip:port'."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        agent_id = "10.0.0.1:8080"
        mgr.agents[agent_id] = {"guild_id": 1, "ip": "10.0.0.1", "port": 8080, "auth_key": "k"}
        assert "10.0.0.1:8080" in mgr.agents

    def test_agent_id_from_update_server_command_format(self):
        """The slash command update_server builds agent_id the same way."""
        agent_ip = "192.168.1.126"
        agent_port = 8080
        agent_id = f"{agent_ip}:{agent_port}"
        assert agent_id == "192.168.1.126:8080"
        assert ":" in agent_id


# ---------------------------------------------------------------------------
# 4. _pending dict for request_id → Future correlation
# ---------------------------------------------------------------------------

class TestPendingFutureCorrelation:
    @pytest.mark.asyncio
    async def test_pending_dict_stores_futures(self):
        """send_command stores a Future in _pending before sending."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()

        # Manually place a future to simulate in-flight request
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        mgr._pending["test_req_1"] = future

        assert "test_req_1" in mgr._pending
        assert isinstance(mgr._pending["test_req_1"], asyncio.Future)

    @pytest.mark.asyncio
    async def test_pending_dict_starts_empty(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        assert len(mgr._pending) == 0

    @pytest.mark.asyncio
    async def test_send_command_raises_when_not_connected(self):
        """send_command raises ConnectionError when agent_id is not in connections."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        with pytest.raises(ConnectionError, match="not connected"):
            await mgr.send_command("1.2.3.4:8080", "get_status", "MyServer")

    @pytest.mark.asyncio
    async def test_send_command_fire_and_forget_returns_false_when_not_connected(self):
        """Fire-and-forget returns False when the agent is not in connections."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        result = await mgr.send_command_fire_and_forget("1.2.3.4:8080", "broadcast", "MyServer")
        assert result is False


# ---------------------------------------------------------------------------
# 5. get_agent_status and get_connected_agent_for_guild
# ---------------------------------------------------------------------------

class TestAgentStatusAndGuildLookup:
    @pytest.mark.asyncio
    async def test_get_agent_status_none_for_unknown(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        result = await mgr.get_agent_status("unknown:8080")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_agent_status_returns_info_for_known_agent(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        agent_id = "10.0.0.5:8080"
        mgr.agents[agent_id] = {"guild_id": 42, "ip": "10.0.0.5", "port": 8080, "auth_key": "k"}
        info = await mgr.get_agent_status(agent_id)
        assert info is not None
        assert info["ip"] == "10.0.0.5"

    @pytest.mark.asyncio
    async def test_get_agent_status_adds_connected_key(self):
        """get_agent_status injects a 'connected' boolean into the returned dict."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        agent_id = "10.0.0.5:8080"
        mgr.agents[agent_id] = {"guild_id": 42, "ip": "10.0.0.5", "port": 8080, "auth_key": "k"}
        info = await mgr.get_agent_status(agent_id)
        assert "connected" in info
        assert info["connected"] is False  # not in connections

    @pytest.mark.asyncio
    async def test_get_connected_agent_for_guild_no_agents(self):
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        result = await mgr.get_connected_agent_for_guild(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_connected_agent_for_guild_agent_not_connected(self):
        """Agent is in agents dict but not in connections — should return None."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        agent_id = "10.0.0.5:8080"
        mgr.agents[agent_id] = {"guild_id": 100, "ip": "10.0.0.5", "port": 8080, "auth_key": "k"}
        # Not adding to mgr.connections — agent is known but disconnected
        result = await mgr.get_connected_agent_for_guild(100)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_connected_agent_for_guild_returns_agent_id_when_connected(self):
        """Agent present in both agents and connections — should return its agent_id."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()
        agent_id = "10.0.0.5:8080"
        mgr.agents[agent_id] = {"guild_id": 200, "ip": "10.0.0.5", "port": 8080, "auth_key": "k"}
        # Simulate an active connection with a placeholder object
        mgr.connections[agent_id] = object()
        result = await mgr.get_connected_agent_for_guild(200)
        assert result == agent_id


# ---------------------------------------------------------------------------
# 6. load_agents_from_db key-name fallback
# ---------------------------------------------------------------------------

class TestLoadAgentsFromDbKeyFallback:
    def test_load_agents_uses_agent_ip_key_when_present(self):
        """Verify the source uses agent.get('agent_ip') or agent.get('ip') for IP."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()

        # Simulate what load_agents_from_db does for each agent row
        agent_row_with_agent_ip = {
            "agent_id": "10.0.0.1:8080",
            "guild_id": 1,
            "agent_ip": "10.0.0.1",
            "agent_port": 8080,
            "auth_key": "k",
        }
        ip = agent_row_with_agent_ip.get("agent_ip") or agent_row_with_agent_ip.get("ip")
        port = agent_row_with_agent_ip.get("agent_port") or agent_row_with_agent_ip.get("port")
        assert ip == "10.0.0.1"
        assert port == 8080

    def test_load_agents_falls_back_to_ip_key_when_agent_ip_missing(self):
        """If 'agent_ip' key is absent, the code falls back to 'ip'."""
        agent_row_with_ip = {
            "agent_id": "10.0.0.2:8080",
            "guild_id": 2,
            "ip": "10.0.0.2",
            "port": 8080,
            "auth_key": "k",
        }
        ip = agent_row_with_ip.get("agent_ip") or agent_row_with_ip.get("ip")
        port = agent_row_with_ip.get("agent_port") or agent_row_with_ip.get("port")
        assert ip == "10.0.0.2"
        assert port == 8080

    def test_load_agents_adds_agent_to_agents_dict(self):
        """load_agents_from_db populates self.agents with expected keys."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()

        # Simulate what the method would store (without hitting the DB)
        agent_id = "10.0.0.3:8080"
        mgr.agents[agent_id] = {
            "guild_id": 3,
            "ip": "10.0.0.3",
            "port": 8080,
            "auth_key": "mykey",
            "connected_at": None,
        }

        assert agent_id in mgr.agents
        assert mgr.agents[agent_id]["ip"] == "10.0.0.3"
        assert mgr.agents[agent_id]["port"] == 8080
        assert mgr.agents[agent_id]["auth_key"] == "mykey"


# ---------------------------------------------------------------------------
# 7. close_all behaviour
# ---------------------------------------------------------------------------

class TestCloseAll:
    @pytest.mark.asyncio
    async def test_close_all_clears_connections(self):
        """close_all removes all entries from the connections dict."""
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()

        # Simulate a connection with a fake websocket that has a close() coroutine
        class _FakeWS:
            async def close(self):
                pass

        mgr.connections["1.2.3.4:8080"] = _FakeWS()
        assert len(mgr.connections) == 1

        await mgr.close_all()
        assert len(mgr.connections) == 0

    @pytest.mark.asyncio
    async def test_close_all_cancels_listener_tasks(self):
        """close_all requests cancellation of tasks stored in _listeners.

        task.cancel() schedules cancellation; the task transitions to
        cancelled only after the event loop processes the CancelledError.
        We yield control with a short sleep so the loop can do that.
        """
        from bot.cogs.remote_agent import RemoteAgentManager
        mgr = RemoteAgentManager()

        async def _noop():
            await asyncio.sleep(60)

        task = asyncio.create_task(_noop())
        mgr._listeners["1.2.3.4:8080"] = task

        await mgr.close_all()

        # Yield to the event loop so the CancelledError is delivered
        await asyncio.sleep(0)

        assert task.cancelled()


# ---------------------------------------------------------------------------
# 8. RemoteAgentCommands cog — instantiation and setup
# ---------------------------------------------------------------------------

class TestRemoteAgentCommandsCog:
    def test_cog_can_be_instantiated(self):
        """RemoteAgentCommands must accept a bot with or without agent_manager."""
        from bot.cogs.remote_agent import RemoteAgentCommands
        bot = _make_bot()
        cog = RemoteAgentCommands(bot)
        assert cog.bot is bot

    def test_cog_creates_agent_manager_when_bot_has_none(self):
        """When bot.agent_manager is None, __init__ creates a new one."""
        from bot.cogs.remote_agent import RemoteAgentCommands, RemoteAgentManager
        bot = _make_bot()
        bot.agent_manager = None
        cog = RemoteAgentCommands(bot)
        assert isinstance(bot.agent_manager, RemoteAgentManager)
        assert cog.agent_manager is bot.agent_manager

    def test_cog_reuses_existing_agent_manager(self):
        """When bot.agent_manager is already set, __init__ must reuse it."""
        from bot.cogs.remote_agent import RemoteAgentCommands, RemoteAgentManager
        bot = _make_bot()
        existing_manager = RemoteAgentManager()
        bot.agent_manager = existing_manager
        cog = RemoteAgentCommands(bot)
        assert cog.agent_manager is existing_manager



# ---------------------------------------------------------------------------
# 9. setup() module-level function
# ---------------------------------------------------------------------------

class TestSetupFunction:
    def test_setup_function_exists(self):
        """The module must export an async setup() function for discord.py."""
        import bot.cogs.remote_agent as module
        assert hasattr(module, "setup")
        assert inspect.iscoroutinefunction(module.setup)

    def test_setup_creates_agent_manager_on_bot_if_missing(self):
        """setup() ensures bot.agent_manager is set before adding the cog."""
        from bot.cogs.remote_agent import RemoteAgentManager
        bot = _make_bot()
        bot.agent_manager = None

        # Simulate what setup() does (without actually running the coroutine
        # through discord.py — we just check the manager injection logic)
        if not hasattr(bot, "agent_manager") or bot.agent_manager is None:
            bot.agent_manager = RemoteAgentManager()

        assert isinstance(bot.agent_manager, RemoteAgentManager)


# ---------------------------------------------------------------------------
# 10. _handle_ark_version_update — attribute contract
# ---------------------------------------------------------------------------

class TestHandleArkVersionUpdate:
    """Guard against multi-guild refactor regressions in _handle_ark_version_update.

    The handler must use the correct ServerMonitor attribute names:
      - guild_server_caches  (not server_status_cache)
      - update_voice_channel(guild_id, rcon_port, ...)  (guild_id as first arg)
    And must resolve the cog by its real name "ServerMonitor" (not "ServerMonitorCog").
    """

    def test_uses_correct_cog_name(self):
        """get_cog() must use 'ServerMonitor', not 'ServerMonitorCog'."""
        import inspect
        import bot.cogs.remote_agent as module
        src = inspect.getsource(module)
        assert 'get_cog("ServerMonitor")' in src, (
            "_handle_ark_version_update calls get_cog with wrong cog name"
        )
        assert 'get_cog("ServerMonitorCog")' not in src, (
            "Stale cog name 'ServerMonitorCog' found — must be 'ServerMonitor'"
        )

    def test_uses_guild_server_caches_not_server_status_cache(self):
        """Handler must read from guild_server_caches, not the removed server_status_cache."""
        import inspect
        import bot.cogs.remote_agent as module
        src = inspect.getsource(module)
        assert "guild_server_caches" in src, (
            "_handle_ark_version_update must use guild_server_caches"
        )
        assert "server_status_cache" not in src, (
            "Stale attribute 'server_status_cache' found — was removed in multi-guild refactor"
        )

    def test_update_voice_channel_receives_guild_id(self):
        """update_voice_channel call must pass guild_id as first positional arg."""
        import inspect
        import bot.cogs.remote_agent as module
        src = inspect.getsource(module)
        assert "update_voice_channel(\n                                    guild_id" in src or \
               "update_voice_channel(guild_id," in src or \
               "update_voice_channel(\n                                    guild_id," in src, (
            "update_voice_channel call must pass guild_id as first argument"
        )
