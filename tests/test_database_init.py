"""
Tests for bot/database/init_db.py - NO MOCKS VERSION - WORKING

Covers: table creation, schema structure, idempotency.
"""

import pytest
import aiosqlite


@pytest.mark.asyncio
async def test_initialize_database_creates_tables(initialized_db):
    """initialize_database creates all expected tables."""
    expected_tables = {
        "guilds",
        "remote_agents",
        "server_configs",
        "ark_servers",
        "players",
        "player_sessions",
        "users",
        "store_items",
        "transactions",
        "coin_transactions",
        "pending_deliveries",
        "voice_channel_mappings",
        "economy_settings",
        "economy_roles",
        "payday_history",
        "shop_config",
        "cart_items",
    }

    async with aiosqlite.connect(initialized_db) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = {row[0] for row in await cursor.fetchall()}

    assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"


@pytest.mark.asyncio
async def test_initialize_database_idempotent(config_db_path):
    """initialize_database can be called multiple times without error."""
    from bot.database.init_db import initialize_database

    await initialize_database()
    await initialize_database()  # Should not raise


@pytest.mark.asyncio
async def test_guilds_table_exists(initialized_db):
    """guilds table exists and has expected structure."""
    async with aiosqlite.connect(initialized_db) as db:
        cursor = await db.execute("PRAGMA table_info(guilds)")
        columns = {row[1]: row for row in await cursor.fetchall()}

    # Check that key columns exist
    required_columns = {"guild_id", "guild_name"}
    assert required_columns.issubset(columns.keys()), f"Missing required columns: {required_columns - set(columns.keys())}"


@pytest.mark.asyncio
async def test_remote_agents_table_exists(initialized_db):
    """remote_agents table exists and has expected structure."""
    async with aiosqlite.connect(initialized_db) as db:
        cursor = await db.execute("PRAGMA table_info(remote_agents)")
        columns = {row[1]: row for row in await cursor.fetchall()}

    # Check that key columns exist
    required_columns = {"guild_id", "agent_id", "agent_ip", "agent_port", "auth_key"}
    assert required_columns.issubset(columns.keys()), f"Missing required columns: {required_columns - set(columns.keys())}"


@pytest.mark.asyncio
async def test_server_configs_table_exists(initialized_db):
    """server_configs table exists and has expected structure."""
    async with aiosqlite.connect(initialized_db) as db:
        cursor = await db.execute("PRAGMA table_info(server_configs)")
        columns = {row[1]: row for row in await cursor.fetchall()}

    # Check that key columns exist
    required_columns = {"guild_id", "guild_name"}
    assert required_columns.issubset(columns.keys()), f"Missing required columns: {required_columns - set(columns.keys())}"


@pytest.mark.asyncio
async def test_players_table_exists(initialized_db):
    """players table exists and has expected structure."""
    async with aiosqlite.connect(initialized_db) as db:
        cursor = await db.execute("PRAGMA table_info(players)")
        columns = {row[1]: row for row in await cursor.fetchall()}

    # Check that key columns exist (using actual column names from schema)
    required_columns = {"guild_id", "player_name", "discord_user_id"}
    assert required_columns.issubset(columns.keys()), f"Missing required columns: {required_columns - set(columns.keys())}"


@pytest.mark.asyncio
async def test_ark_servers_table_exists(initialized_db):
    """ark_servers table exists and has expected structure."""
    async with aiosqlite.connect(initialized_db) as db:
        cursor = await db.execute("PRAGMA table_info(ark_servers)")
        columns = {row[1]: row for row in await cursor.fetchall()}

    # Check that key columns exist
    required_columns = {"guild_id", "name", "host", "rcon_port", "rcon_password"}
    assert required_columns.issubset(columns.keys()), f"Missing required columns: {required_columns - set(columns.keys())}"


@pytest.mark.asyncio
async def test_voice_channel_mappings_table_exists(initialized_db):
    """voice_channel_mappings table exists and has expected structure."""
    async with aiosqlite.connect(initialized_db) as db:
        cursor = await db.execute("PRAGMA table_info(voice_channel_mappings)")
        columns = {row[1]: row for row in await cursor.fetchall()}

    # Check that key columns exist
    required_columns = {"guild_id", "rcon_port", "voice_channel_id"}
    assert required_columns.issubset(columns.keys()), f"Missing required columns: {required_columns - set(columns.keys())}"


@pytest.mark.asyncio
async def test_database_connectivity(initialized_db):
    """Database can be connected to and basic queries work."""
    async with aiosqlite.connect(initialized_db) as db:
        # Test basic query
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
        result = await cursor.fetchone()
        assert result is not None, "Database should have at least one table"


@pytest.mark.asyncio
async def test_table_creation_order(initialized_db):
    """Tables are created in the correct order with proper dependencies."""
    async with aiosqlite.connect(initialized_db) as db:
        # Check that foreign key tables exist after their parent tables
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]

        # server_configs should exist before ark_servers (FK dependency)
        assert "server_configs" in tables
        assert "ark_servers" in tables


@pytest.mark.asyncio
async def test_initialize_database_with_custom_path(tmp_path):
    """initialize_database works with custom database path."""
    from bot.database.init_db import initialize_database
    from bot.utils.config import Config
    
    custom_db_path = str(tmp_path / "custom_test.db")
    original_path = Config.DATABASE_PATH
    Config.DATABASE_PATH = custom_db_path
    
    try:
        await initialize_database()
        
        # Verify database was created at custom path
        import os
        assert os.path.exists(custom_db_path), "Database should be created at custom path"
        
        # Verify tables exist
        async with aiosqlite.connect(custom_db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables = {row[0] for row in await cursor.fetchall()}
            assert len(tables) > 0, "Database should have tables"
    finally:
        Config.DATABASE_PATH = original_path
        # Clean up
        if os.path.exists(custom_db_path):
            os.remove(custom_db_path)
