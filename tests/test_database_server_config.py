"""
Tests for bot/database/server_config_db.py - NO MOCKS VERSION - WORKING

Covers: init, CRUD for guild configs, ARK servers, voice channel mappings, MOTD,
        disable_servers_beyond_limit (tier downgrade enforcement).
"""

import pytest
import pytest_asyncio
import aiosqlite


# ---------------------------------------------------------------------------
# Guild config CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_server_config(server_config_db):
    """create_or_update_server_config inserts a new guild row."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        get_server_config,
    )

    result = await create_or_update_server_config(
        guild_id=100, guild_name="Test Guild"
    )
    assert result is True

    config = await get_server_config(100)
    assert config is not None
    assert config["guild_name"] == "Test Guild"
    assert config["hosting_type"] == "self_hosted"  # default


@pytest.mark.asyncio
async def test_update_server_config(server_config_db):
    """create_or_update_server_config updates existing guild rows."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        get_server_config,
    )

    await create_or_update_server_config(100, "Test Guild")
    await create_or_update_server_config(
        100, "Test Guild Renamed", status_channel_id=12345
    )

    config = await get_server_config(100)
    assert config["guild_name"] == "Test Guild Renamed"
    assert config["status_channel_id"] == 12345


@pytest.mark.asyncio
async def test_get_server_config_not_found(server_config_db):
    """get_server_config returns None for non-existent guild."""
    from bot.database.server_config_db import get_server_config

    config = await get_server_config(99999)
    assert config is None


# ---------------------------------------------------------------------------
# ARK server CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_ark_server(server_config_db):
    """add_ark_server inserts a new ARK server."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        add_ark_server,
        get_ark_servers,
    )

    # Create guild config first
    await create_or_update_server_config(100, "Test Guild")

    # Create ARK server with only required fields
    server_id = await add_ark_server(
        guild_id=100,
        name="Test Server",
        host="127.0.0.1",
        rcon_port=27015,
        rcon_password="password123",
    )
    assert server_id is not None
    assert isinstance(server_id, int)

    servers = await get_ark_servers(100)
    assert len(servers) == 1
    server = servers[0]
    assert server["name"] == "Test Server"
    assert server["rcon_port"] == 27015
    assert server["max_players"] == 70  # default


@pytest.mark.asyncio
async def test_get_ark_servers_empty(server_config_db):
    """get_ark_servers returns empty list for guild with no servers."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        get_ark_servers,
    )

    await create_or_update_server_config(100, "Test Guild")
    servers = await get_ark_servers(100)
    assert servers == []


@pytest.mark.asyncio
async def test_get_ark_server_by_port(server_config_db):
    """get_ark_server_by_port returns server by RCON port."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        add_ark_server,
        get_ark_server_by_port,
    )

    # Create guild and server
    await create_or_update_server_config(100, "Test Guild")
    await add_ark_server(
        100, name="Test Server", host="127.0.0.1", rcon_port=27015, rcon_password="password123"
    )

    server = await get_ark_server_by_port(100, 27015)
    assert server is not None
    assert server["name"] == "Test Server"
    assert server["rcon_port"] == 27015

    # Test non-existent port
    server = await get_ark_server_by_port(100, 99999)
    assert server is None


# ---------------------------------------------------------------------------
# Voice channel mappings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_server_voice_channel_id(server_config_db):
    """set_server_voice_channel_id creates or updates mapping."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        add_ark_server,
        set_server_voice_channel_id,
        get_voice_channel_id,
    )

    # Create guild and server
    await create_or_update_server_config(100, "Test Guild")
    await add_ark_server(
        100, name="Test Server", host="127.0.0.1", rcon_port=27015, rcon_password="password123"
    )

    # Set voice channel mapping
    result = await set_server_voice_channel_id(100, 27015, 123456)
    assert result is True

    channel_id = await get_voice_channel_id(100, 27015)
    assert channel_id == 123456


@pytest.mark.asyncio
async def test_clear_server_voice_channel_id(server_config_db):
    """clear_server_voice_channel_id removes mapping."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        add_ark_server,
        set_server_voice_channel_id,
        get_voice_channel_id,
        clear_server_voice_channel_id,
    )

    # Create guild, server, and mapping
    await create_or_update_server_config(100, "Test Guild")
    await add_ark_server(
        100, name="Test Server", host="127.0.0.1", rcon_port=27015, rcon_password="password123"
    )
    await set_server_voice_channel_id(100, 27015, 123456)

    # Verify it exists
    channel_id = await get_voice_channel_id(100, 27015)
    assert channel_id == 123456

    # Clear it
    result = await clear_server_voice_channel_id(100, 27015)
    assert result is True

    # Verify it's gone
    channel_id = await get_voice_channel_id(100, 27015)
    assert channel_id is None


# ---------------------------------------------------------------------------
# MOTD management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_server_motd(server_config_db):
    """set_server_motd updates server MOTD."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        add_ark_server,
        set_server_motd,
        get_server_motd,
    )

    # Create guild and server
    await create_or_update_server_config(100, "Test Guild")
    await add_ark_server(
        100, name="Test Server", host="127.0.0.1", rcon_port=27015, rcon_password="password123"
    )

    result = await set_server_motd(100, 27015, "Welcome to our ARK server!", 60)
    assert result is True

    motd, duration = await get_server_motd(100, 27015)
    assert motd == "Welcome to our ARK server!"
    assert duration == 60


@pytest.mark.asyncio
async def test_get_server_motd_not_set(server_config_db):
    """get_server_motd returns defaults when MOTD is not set."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        add_ark_server,
        get_server_motd,
    )

    # Create guild and server
    await create_or_update_server_config(100, "Test Guild")
    await add_ark_server(
        100, name="Test Server", host="127.0.0.1", rcon_port=27015, rcon_password="password123"
    )

    motd, duration = await get_server_motd(100, 27015)
    assert motd is None
    assert duration == 30  # Default duration


# ---------------------------------------------------------------------------
# Hosting type management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hosting_type_management(server_config_db):
    """Test hosting type get/set functions."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        get_hosting_type,
        set_hosting_type,
        is_self_hosted,
    )

    # Create guild config
    await create_or_update_server_config(100, "Test Guild")

    # Test default
    hosting_type = await get_hosting_type(100)
    assert hosting_type == "self_hosted"
    assert await is_self_hosted(100) is True

    # Set to self_hosted
    result = await set_hosting_type(100, "self_hosted")
    assert result is True

    hosting_type = await get_hosting_type(100)
    assert hosting_type == "self_hosted"
    assert await is_self_hosted(100) is True

    # Set to nitrado
    result = await set_hosting_type(100, "nitrado")
    assert result is True

    hosting_type = await get_hosting_type(100)
    assert hosting_type == "nitrado"
    assert await is_self_hosted(100) is False


@pytest.mark.asyncio
async def test_set_admin_log_channel_id(server_config_db):
    """set_admin_log_channel_id updates admin log channel."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        set_admin_log_channel_id,
        get_server_config,
    )

    await create_or_update_server_config(100, "Test Guild")

    result = await set_admin_log_channel_id(100, 789012)
    assert result is True

    config = await get_server_config(100)
    assert config["admin_log_channel_id"] == 789012


@pytest.mark.asyncio
async def test_get_all_guild_ids(server_config_db):
    """get_all_guild_ids returns all configured guild IDs."""
    from bot.database.server_config_db import (
        create_or_update_server_config,
        get_all_guild_ids,
    )

    # Create multiple guild configs
    await create_or_update_server_config(100, "Guild 1")
    await create_or_update_server_config(200, "Guild 2")
    await create_or_update_server_config(300, "Guild 3")

    guild_ids = await get_all_guild_ids()
    assert set(guild_ids) == {100, 200, 300}


# ---------------------------------------------------------------------------
# disable_servers_beyond_limit — tier downgrade enforcement
# ---------------------------------------------------------------------------

async def _insert_server(config_db_path, guild_id, name, enabled=1):
    """Insert a server row directly for test setup."""
    async with aiosqlite.connect(config_db_path) as db:
        await db.execute(
            "INSERT INTO ark_servers (guild_id, name, host, rcon_port, rcon_password, enabled) "
            "VALUES (?, ?, 'localhost', 27020, 'pass', ?)",
            (guild_id, name, enabled),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_disable_servers_beyond_limit_disables_excess(server_config_db):
    """With 3 servers and limit 2, the 3rd (highest ID) is disabled."""
    from bot.database.server_config_db import disable_servers_beyond_limit
    guild_id = 5001
    await _insert_server(server_config_db, guild_id, "Server1")
    await _insert_server(server_config_db, guild_id, "Server2")
    await _insert_server(server_config_db, guild_id, "Server3")

    disabled = await disable_servers_beyond_limit(guild_id, limit=2)

    assert disabled == ["Server3"]


@pytest.mark.asyncio
async def test_disable_servers_beyond_limit_keeps_oldest(server_config_db):
    """Oldest servers (lowest IDs) are kept; newest are disabled."""
    from bot.database.server_config_db import disable_servers_beyond_limit
    guild_id = 5002
    await _insert_server(server_config_db, guild_id, "Alpha")
    await _insert_server(server_config_db, guild_id, "Beta")
    await _insert_server(server_config_db, guild_id, "Gamma")
    await _insert_server(server_config_db, guild_id, "Delta")

    disabled = await disable_servers_beyond_limit(guild_id, limit=2)

    assert "Alpha" not in disabled
    assert "Beta" not in disabled
    assert "Gamma" in disabled
    assert "Delta" in disabled
    assert len(disabled) == 2


@pytest.mark.asyncio
async def test_disable_servers_beyond_limit_within_limit_returns_empty(server_config_db):
    """With ≤ limit servers, nothing is disabled."""
    from bot.database.server_config_db import disable_servers_beyond_limit
    guild_id = 5003
    await _insert_server(server_config_db, guild_id, "OnlyServer")

    disabled = await disable_servers_beyond_limit(guild_id, limit=2)

    assert disabled == []


@pytest.mark.asyncio
async def test_disable_servers_beyond_limit_exact_limit_returns_empty(server_config_db):
    """Exactly at the limit: no servers disabled."""
    from bot.database.server_config_db import disable_servers_beyond_limit
    guild_id = 5004
    await _insert_server(server_config_db, guild_id, "S1")
    await _insert_server(server_config_db, guild_id, "S2")

    disabled = await disable_servers_beyond_limit(guild_id, limit=2)

    assert disabled == []


@pytest.mark.asyncio
async def test_disable_servers_beyond_limit_skips_already_disabled(server_config_db):
    """Servers already disabled are not counted toward the limit."""
    from bot.database.server_config_db import disable_servers_beyond_limit
    guild_id = 5005
    await _insert_server(server_config_db, guild_id, "Enabled1")
    await _insert_server(server_config_db, guild_id, "Enabled2")
    await _insert_server(server_config_db, guild_id, "AlreadyOff", enabled=0)  # already off

    disabled = await disable_servers_beyond_limit(guild_id, limit=2)

    # Only 2 enabled servers → none should be disabled
    assert disabled == []


@pytest.mark.asyncio
async def test_disable_servers_beyond_limit_marks_enabled_false(server_config_db):
    """Disabled servers must have enabled=0 in the database afterward."""
    from bot.database.server_config_db import disable_servers_beyond_limit
    guild_id = 5006
    await _insert_server(server_config_db, guild_id, "Keep1")
    await _insert_server(server_config_db, guild_id, "Keep2")
    await _insert_server(server_config_db, guild_id, "Disabled3")

    await disable_servers_beyond_limit(guild_id, limit=2, reason="tier_limit")

    async with aiosqlite.connect(server_config_db) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT name, enabled, disabled_reason FROM ark_servers WHERE guild_id = ? ORDER BY id",
            (guild_id,),
        )
        rows = [dict(r) for r in await cursor.fetchall()]

    by_name = {r["name"]: r for r in rows}
    assert by_name["Keep1"]["enabled"] == 1
    assert by_name["Keep2"]["enabled"] == 1
    assert by_name["Disabled3"]["enabled"] == 0
    assert by_name["Disabled3"]["disabled_reason"] == "tier_limit"


@pytest.mark.asyncio
async def test_disable_servers_beyond_limit_guild_isolation(server_config_db):
    """Servers in other guilds are not affected by a downgrade in one guild."""
    from bot.database.server_config_db import disable_servers_beyond_limit
    guild_a = 5007
    guild_b = 5008
    await _insert_server(server_config_db, guild_a, "A1")
    await _insert_server(server_config_db, guild_a, "A2")
    await _insert_server(server_config_db, guild_a, "A3")
    await _insert_server(server_config_db, guild_b, "B1")
    await _insert_server(server_config_db, guild_b, "B2")

    # Downgrade guild_a only
    disabled = await disable_servers_beyond_limit(guild_a, limit=2)

    assert disabled == ["A3"]

    # Guild B servers must remain enabled
    async with aiosqlite.connect(server_config_db) as db:
        cursor = await db.execute(
            "SELECT enabled FROM ark_servers WHERE guild_id = ?", (guild_b,)
        )
        rows = await cursor.fetchall()
    assert all(r[0] == 1 for r in rows), "Guild B servers must remain enabled"


# ---------------------------------------------------------------------------
# enable_tier_limited_servers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enable_tier_limited_servers_function_exists(server_config_db):
    """enable_tier_limited_servers must be importable from server_config_db."""
    from bot.database import server_config_db as scdb
    assert hasattr(scdb, "enable_tier_limited_servers"), (
        "enable_tier_limited_servers must exist in server_config_db"
    )


@pytest.mark.asyncio
async def test_enable_tier_limited_servers_reenables_disabled_servers(server_config_db):
    """Servers disabled with disabled_reason='tier_limit' must be re-enabled."""
    from bot.database import server_config_db as scdb

    guild_id = 9901
    # Set up guild config row (FK requirement)
    await scdb.create_or_update_server_config(guild_id, "TierTest")

    s1 = await scdb.add_ark_server(guild_id, name="Active", host="1.1.1.1", rcon_port=27020, rcon_password="x")
    s2 = await scdb.add_ark_server(guild_id, name="TierDisabled", host="1.1.1.2", rcon_port=27021, rcon_password="x")
    s3 = await scdb.add_ark_server(guild_id, name="AlsoTierDisabled", host="1.1.1.3", rcon_port=27022, rcon_password="x")

    # Disable s2 and s3 as tier_limit
    await scdb.update_ark_server(s2, enabled=False, disabled_reason="tier_limit")
    await scdb.update_ark_server(s3, enabled=False, disabled_reason="tier_limit")

    reenabled = await scdb.enable_tier_limited_servers(guild_id)

    all_servers = await scdb.get_all_ark_servers_including_disabled(guild_id)
    by_id = {s["id"]: s for s in all_servers}

    assert by_id[s1]["enabled"], "Already-enabled server must remain enabled"
    assert by_id[s2]["enabled"], "tier_limit server must be re-enabled"
    assert by_id[s3]["enabled"], "tier_limit server must be re-enabled"
    assert by_id[s2]["disabled_reason"] is None, "disabled_reason must be cleared"
    assert by_id[s3]["disabled_reason"] is None, "disabled_reason must be cleared"
    assert "TierDisabled" in reenabled or "AlsoTierDisabled" in reenabled, (
        "Function must return list of re-enabled server names"
    )


@pytest.mark.asyncio
async def test_enable_tier_limited_servers_leaves_manually_disabled_alone(server_config_db):
    """Servers disabled without tier_limit reason must not be touched."""
    from bot.database import server_config_db as scdb

    guild_id = 9902
    await scdb.create_or_update_server_config(guild_id, "ManualTest")

    s1 = await scdb.add_ark_server(guild_id, name="ManualOff", host="2.2.2.1", rcon_port=27030, rcon_password="x")
    # Disable manually — no disabled_reason set
    await scdb.update_ark_server(s1, enabled=False)

    reenabled = await scdb.enable_tier_limited_servers(guild_id)

    all_servers = await scdb.get_all_ark_servers_including_disabled(guild_id)
    assert not all_servers[0]["enabled"], "Manually disabled server must remain disabled"
    assert reenabled == [], "No servers should have been re-enabled"


@pytest.mark.asyncio
async def test_enable_tier_limited_servers_guild_isolation(server_config_db):
    """enable_tier_limited_servers must only affect the specified guild."""
    from bot.database import server_config_db as scdb

    guild_a, guild_b = 9903, 9904
    await scdb.create_or_update_server_config(guild_a, "GuildA")
    await scdb.create_or_update_server_config(guild_b, "GuildB")

    sa = await scdb.add_ark_server(guild_a, name="A_TierOff", host="3.3.3.1", rcon_port=27040, rcon_password="x")
    sb = await scdb.add_ark_server(guild_b, name="B_TierOff", host="3.3.3.2", rcon_port=27041, rcon_password="x")

    await scdb.update_ark_server(sa, enabled=False, disabled_reason="tier_limit")
    await scdb.update_ark_server(sb, enabled=False, disabled_reason="tier_limit")

    # Only upgrade guild_a
    await scdb.enable_tier_limited_servers(guild_a)

    all_a = await scdb.get_all_ark_servers_including_disabled(guild_a)
    all_b = await scdb.get_all_ark_servers_including_disabled(guild_b)

    assert all_a[0]["enabled"], "Guild A server must be re-enabled"
    assert not all_b[0]["enabled"], "Guild B server must remain disabled (different guild)"

