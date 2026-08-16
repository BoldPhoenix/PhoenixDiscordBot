"""
Tests for bot/database/remote_agent_db.py

Covers: create_remote_agent, get_remote_agents, get_all_remote_agents,
update_agent_connection, delete_remote_agent, get_agent_by_id.

All tests use the `initialized_db` fixture because the remote_agents table
is created by initialize_database().
"""

import pytest
import aiosqlite
from pathlib import Path

from bot.database import remote_agent_db
from bot.utils.config import Config

GUILD_ID = 111222333
GUILD_ID_2 = 444555666

AGENT_ID = "agent-abc-001"
AGENT_ID_2 = "agent-xyz-002"
AGENT_ID_3 = "agent-qrs-003"

AGENT_IP = "192.168.1.100"
AGENT_PORT = 8080
AUTH_KEY = "super-secret-key-1"

AGENT_IP_2 = "10.0.0.200"
AGENT_PORT_2 = 8081
AUTH_KEY_2 = "another-secret-key-2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create(
    guild_id=GUILD_ID,
    agent_id=AGENT_ID,
    agent_ip=AGENT_IP,
    agent_port=AGENT_PORT,
    auth_key=AUTH_KEY,
) -> bool:
    return await remote_agent_db.create_remote_agent(
        guild_id=guild_id,
        agent_id=agent_id,
        agent_ip=agent_ip,
        agent_port=agent_port,
        auth_key=auth_key,
    )


# ---------------------------------------------------------------------------
# create_remote_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_remote_agent_returns_true(initialized_db):
    """create_remote_agent returns True on success."""
    result = await _create()
    assert result is True


@pytest.mark.asyncio
async def test_create_remote_agent_is_retrievable(initialized_db):
    """Agent created by create_remote_agent is returned by get_remote_agents."""
    await _create()
    agents = await remote_agent_db.get_remote_agents(GUILD_ID)
    assert len(agents) == 1
    assert agents[0]["agent_id"] == AGENT_ID


@pytest.mark.asyncio
async def test_create_remote_agent_insert_or_replace(initialized_db):
    """create_remote_agent with the same (guild_id, agent_id) replaces the row."""
    await _create(agent_ip="1.1.1.1", auth_key="old-key")
    await _create(agent_ip="2.2.2.2", auth_key="new-key")

    agents = await remote_agent_db.get_remote_agents(GUILD_ID)
    assert len(agents) == 1
    assert agents[0]["ip"] == "2.2.2.2"
    assert agents[0]["auth_key"] == "new-key"


# ---------------------------------------------------------------------------
# get_remote_agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_remote_agents_returns_correct_guild(initialized_db):
    """get_remote_agents returns only agents for the specified guild."""
    await _create(guild_id=GUILD_ID, agent_id=AGENT_ID)
    await _create(guild_id=GUILD_ID_2, agent_id=AGENT_ID_2)

    agents = await remote_agent_db.get_remote_agents(GUILD_ID)
    assert len(agents) == 1
    assert agents[0]["agent_id"] == AGENT_ID
    assert agents[0]["guild_id"] == GUILD_ID


@pytest.mark.asyncio
async def test_get_remote_agents_returns_empty_for_unknown_guild(initialized_db):
    """get_remote_agents returns an empty list for a guild with no agents."""
    agents = await remote_agent_db.get_remote_agents(99999999)
    assert agents == []


@pytest.mark.asyncio
async def test_get_remote_agents_correct_keys(initialized_db):
    """get_remote_agents returns dicts with the expected keys."""
    await _create()
    agents = await remote_agent_db.get_remote_agents(GUILD_ID)
    agent = agents[0]

    expected_keys = {"guild_id", "agent_id", "ip", "port", "auth_key",
                     "created_at", "last_connected", "is_active"}
    assert expected_keys.issubset(set(agent.keys()))


@pytest.mark.asyncio
async def test_get_remote_agents_correct_values(initialized_db):
    """get_remote_agents returns correct ip, port, and auth_key values."""
    await _create(agent_ip=AGENT_IP, agent_port=AGENT_PORT, auth_key=AUTH_KEY)
    agents = await remote_agent_db.get_remote_agents(GUILD_ID)
    agent = agents[0]

    assert agent["ip"] == AGENT_IP
    assert agent["port"] == AGENT_PORT
    assert agent["auth_key"] == AUTH_KEY


# ---------------------------------------------------------------------------
# get_all_remote_agents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_remote_agents_returns_all_guilds(initialized_db):
    """get_all_remote_agents returns agents from every guild."""
    await _create(guild_id=GUILD_ID, agent_id=AGENT_ID)
    await _create(guild_id=GUILD_ID_2, agent_id=AGENT_ID_2)

    agents = await remote_agent_db.get_all_remote_agents()
    assert len(agents) == 2
    guild_ids = {a["guild_id"] for a in agents}
    assert GUILD_ID in guild_ids
    assert GUILD_ID_2 in guild_ids


@pytest.mark.asyncio
async def test_get_all_remote_agents_empty_when_none_exist(initialized_db):
    """get_all_remote_agents returns empty list when no agents are registered."""
    agents = await remote_agent_db.get_all_remote_agents()
    assert agents == []


# ---------------------------------------------------------------------------
# update_agent_connection(connected=True)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_agent_connection_true_sets_active(initialized_db):
    """update_agent_connection(True) sets is_active=1."""
    await _create()

    # Manually set is_active=0 to confirm the update actually fires
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE remote_agents SET is_active = 0 WHERE agent_id = ?", (AGENT_ID,)
        )
        await db.commit()

    result = await remote_agent_db.update_agent_connection(AGENT_ID, connected=True)
    assert result is True

    agent = await remote_agent_db.get_agent_by_id(GUILD_ID, AGENT_ID)
    assert agent is not None
    assert agent["is_active"] == 1


@pytest.mark.asyncio
async def test_update_agent_connection_true_updates_last_connected(initialized_db):
    """update_agent_connection(True) updates the last_connected timestamp."""
    await _create()

    # Zero out last_connected first
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE remote_agents SET last_connected = NULL WHERE agent_id = ?", (AGENT_ID,)
        )
        await db.commit()

    await remote_agent_db.update_agent_connection(AGENT_ID, connected=True)

    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        async with db.execute(
            "SELECT last_connected FROM remote_agents WHERE agent_id = ?", (AGENT_ID,)
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None
    assert row[0] is not None


# ---------------------------------------------------------------------------
# update_agent_connection(connected=False) — CRITICAL BEHAVIOUR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_agent_connection_false_does_not_clear_is_active(initialized_db):
    """
    CRITICAL: update_agent_connection(False) must NOT set is_active=0.
    It should only update last_connected, leaving is_active unchanged.
    """
    await _create()

    # Verify the agent starts as active
    agent_before = await remote_agent_db.get_agent_by_id(GUILD_ID, AGENT_ID)
    assert agent_before["is_active"] == 1

    # Disconnect
    result = await remote_agent_db.update_agent_connection(AGENT_ID, connected=False)
    assert result is True

    # is_active must still be 1 — not deactivated on disconnect
    agent_after = await remote_agent_db.get_agent_by_id(GUILD_ID, AGENT_ID)
    assert agent_after is not None
    assert agent_after["is_active"] == 1, (
        "update_agent_connection(False) incorrectly set is_active=0. "
        "Disconnect should only update last_connected."
    )


@pytest.mark.asyncio
async def test_update_agent_connection_false_updates_last_connected(initialized_db):
    """update_agent_connection(False) still updates last_connected."""
    await _create()

    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE remote_agents SET last_connected = NULL WHERE agent_id = ?", (AGENT_ID,)
        )
        await db.commit()

    await remote_agent_db.update_agent_connection(AGENT_ID, connected=False)

    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        async with db.execute(
            "SELECT last_connected FROM remote_agents WHERE agent_id = ?", (AGENT_ID,)
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None
    assert row[0] is not None


# ---------------------------------------------------------------------------
# delete_remote_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_remote_agent_returns_true(initialized_db):
    """delete_remote_agent returns True on success."""
    await _create()
    result = await remote_agent_db.delete_remote_agent(GUILD_ID, AGENT_ID)
    assert result is True


@pytest.mark.asyncio
async def test_delete_remote_agent_agent_no_longer_returned(initialized_db):
    """Deleted agent is not returned by get_remote_agents."""
    await _create()
    await remote_agent_db.delete_remote_agent(GUILD_ID, AGENT_ID)

    agents = await remote_agent_db.get_remote_agents(GUILD_ID)
    assert agents == []


@pytest.mark.asyncio
async def test_delete_remote_agent_only_removes_target(initialized_db):
    """delete_remote_agent removes only the targeted agent, not others."""
    await _create(guild_id=GUILD_ID, agent_id=AGENT_ID)
    await _create(guild_id=GUILD_ID, agent_id=AGENT_ID_2,
                  agent_ip=AGENT_IP_2, agent_port=AGENT_PORT_2, auth_key=AUTH_KEY_2)

    await remote_agent_db.delete_remote_agent(GUILD_ID, AGENT_ID)

    agents = await remote_agent_db.get_remote_agents(GUILD_ID)
    assert len(agents) == 1
    assert agents[0]["agent_id"] == AGENT_ID_2


# ---------------------------------------------------------------------------
# get_agent_by_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_agent_by_id_found(initialized_db):
    """get_agent_by_id returns the correct agent dict."""
    await _create(agent_ip=AGENT_IP, agent_port=AGENT_PORT, auth_key=AUTH_KEY)
    agent = await remote_agent_db.get_agent_by_id(GUILD_ID, AGENT_ID)

    assert agent is not None
    assert agent["agent_id"] == AGENT_ID
    assert agent["ip"] == AGENT_IP
    assert agent["port"] == AGENT_PORT
    assert agent["auth_key"] == AUTH_KEY
    assert agent["is_active"] == 1


@pytest.mark.asyncio
async def test_get_agent_by_id_not_found_returns_none(initialized_db):
    """get_agent_by_id returns None for an unknown agent."""
    agent = await remote_agent_db.get_agent_by_id(GUILD_ID, "agent-does-not-exist")
    assert agent is None


@pytest.mark.asyncio
async def test_get_agent_by_id_wrong_guild_returns_none(initialized_db):
    """get_agent_by_id returns None when guild_id does not match."""
    await _create(guild_id=GUILD_ID, agent_id=AGENT_ID)
    agent = await remote_agent_db.get_agent_by_id(GUILD_ID_2, AGENT_ID)
    assert agent is None
