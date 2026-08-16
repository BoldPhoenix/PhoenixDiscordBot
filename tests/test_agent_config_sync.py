"""
Tests for agent config sync on server add/edit/remove.

Field bug (2026-07-03): Carl added a new server ('Genesis') for the new ARK map via
/setup. The bot wrote the DB, created the service and registry entry, updated the
status channel — but the already-connected agent's in-memory server list was never
refreshed (configure_servers is only pushed on agent connect/reconnect or agent
startup request). maintain_server then failed with:
    "Maintenance for Genesis FAILED: Server 'Genesis' not found in config"

Fix under test:
1. RemoteAgentManager.push_server_config(guild_id) — pushes configure_servers to
   every CONNECTED agent belonging to that guild.
2. setup_gui._sync_agent_config(bot, guild_id) — fire-safe glue called after every
   ark-server write in the GUI.

Jeffrey Snover methodology: real RemoteAgentManager, real DB via initialized_db,
no mocks of internal functions. The websocket is an external boundary -> a minimal
capturing stand-in class (same pattern as CapturingAgentManager).
"""

import json
import pytest


class CapturingWebSocket:
    """External-boundary stand-in: records every frame sent to the agent."""

    def __init__(self):
        self.sent: list = []

    async def send(self, payload: str):
        self.sent.append(json.loads(payload))


def _make_manager():
    from bot.cogs.remote_agent import RemoteAgentManager
    return RemoteAgentManager()


async def _seed_guild_with_server(guild_id: int, name: str):
    from bot.database import server_config_db
    await server_config_db.create_or_update_server_config(guild_id, "Test Guild")
    await server_config_db.add_ark_server(
        guild_id, name=name, host="127.0.0.1",
        rcon_port=27020, rcon_password="test",
        service_name=f"PhoenixARK_{name}",
    )


class TestPushServerConfig:
    """RemoteAgentManager.push_server_config(guild_id)."""

    @pytest.mark.asyncio
    async def test_pushes_configure_servers_to_connected_guild_agent(self, initialized_db):
        guild_id = 123
        await _seed_guild_with_server(guild_id, "Genesis")

        manager = _make_manager()
        ws = CapturingWebSocket()
        manager.agents["agent-1"] = {"guild_id": guild_id}
        manager.connections["agent-1"] = ws

        await manager.push_server_config(guild_id)

        assert len(ws.sent) == 1, "exactly one configure_servers push expected"
        cmd = ws.sent[0]
        assert cmd["type"] == "configure_servers"
        names = [s["name"] for s in cmd["params"]]
        assert "Genesis" in names, "newly added server must reach the agent"

    @pytest.mark.asyncio
    async def test_newly_added_server_is_included_on_next_push(self, initialized_db):
        """The exact field scenario: add a server AFTER the agent connected."""
        guild_id = 123
        await _seed_guild_with_server(guild_id, "Ragnarok")

        manager = _make_manager()
        ws = CapturingWebSocket()
        manager.agents["agent-1"] = {"guild_id": guild_id}
        manager.connections["agent-1"] = ws

        await manager.push_server_config(guild_id)  # initial config (pre-Genesis)

        from bot.database import server_config_db
        await server_config_db.add_ark_server(
            guild_id, name="Genesis", host="127.0.0.1",
            rcon_port=27030, rcon_password="test",
            service_name="PhoenixARK_Genesis",
        )
        await manager.push_server_config(guild_id)  # the fix: push after write

        assert len(ws.sent) == 2
        names = [s["name"] for s in ws.sent[-1]["params"]]
        assert "Genesis" in names

    @pytest.mark.asyncio
    async def test_ignores_agents_of_other_guilds(self, initialized_db):
        guild_id = 123
        await _seed_guild_with_server(guild_id, "Genesis")

        manager = _make_manager()
        mine = CapturingWebSocket()
        theirs = CapturingWebSocket()
        manager.agents["agent-mine"] = {"guild_id": guild_id}
        manager.agents["agent-theirs"] = {"guild_id": 999}
        manager.connections["agent-mine"] = mine
        manager.connections["agent-theirs"] = theirs

        await manager.push_server_config(guild_id)

        assert len(mine.sent) == 1
        assert len(theirs.sent) == 0, "other guilds' agents must not receive our config"

    @pytest.mark.asyncio
    async def test_no_connected_agent_is_a_safe_noop(self, initialized_db):
        guild_id = 123
        await _seed_guild_with_server(guild_id, "Genesis")
        manager = _make_manager()
        manager.agents["agent-1"] = {"guild_id": guild_id}
        # registered but NOT connected
        await manager.push_server_config(guild_id)  # must not raise


class TestSetupGuiSyncGlue:
    """setup_gui._sync_agent_config — the glue called after every server write."""

    @pytest.mark.asyncio
    async def test_sync_calls_manager_push(self, initialized_db):
        guild_id = 123
        await _seed_guild_with_server(guild_id, "Genesis")

        manager = _make_manager()
        ws = CapturingWebSocket()
        manager.agents["agent-1"] = {"guild_id": guild_id}
        manager.connections["agent-1"] = ws

        class BotWithManager:
            agent_manager = manager

        from bot.cogs.setup_gui import _sync_agent_config
        await _sync_agent_config(BotWithManager(), guild_id)

        assert len(ws.sent) == 1
        assert ws.sent[0]["type"] == "configure_servers"

    @pytest.mark.asyncio
    async def test_sync_survives_missing_agent_manager(self, initialized_db):
        """Bots without an agent manager (or manager errors) must never break the GUI flow."""
        class BareBot:
            pass

        from bot.cogs.setup_gui import _sync_agent_config
        await _sync_agent_config(BareBot(), 123)  # must not raise
