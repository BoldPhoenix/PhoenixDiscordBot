"""
Test for the specific server update issue - NO MOCKS VERSION

Tests the update_ark_server function to identify the exact error.
"""

import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_update_ark_server_function(server_config_db):
    """Test update_ark_server function with proper signature."""
    from bot.database.server_config_db import add_ark_server, update_ark_server, get_ark_servers
    
    # Create guild config
    from bot.database.server_config_db import create_or_update_server_config
    await create_or_update_server_config(100, "Test Guild")
    
    # Add a server first
    await add_ark_server(
        100, name="Test Server", host="192.168.1.100", 
        rcon_port=27060, rcon_password="password123"
    )
    
    # Get the server to get its ID
    servers = await get_ark_servers(100)
    assert len(servers) == 1
    server_id = servers[0]['id']
    
    # Test update_ark_server with keyword arguments (correct way)
    result = await update_ark_server(
        server_id,
        name="Updated Server",
        host="192.168.1.200",
        rcon_port=27061,
        rcon_password="newpass123",
        max_players=80,
        enabled=True
    )
    assert result is True
    
    # Verify the update
    updated_servers = await get_ark_servers(100)
    assert len(updated_servers) == 1
    assert updated_servers[0]['name'] == "Updated Server"
    assert updated_servers[0]['host'] == "192.168.1.200"
    assert updated_servers[0]['rcon_port'] == 27061
    assert updated_servers[0]['max_players'] == 80


@pytest.mark.asyncio 
async def test_update_ark_server_with_optional_fields(server_config_db):
    """Test update_ark_server with optional fields."""
    from bot.database.server_config_db import add_ark_server, update_ark_server, get_ark_servers
    
    # Create guild config
    from bot.database.server_config_db import create_or_update_server_config
    await create_or_update_server_config(100, "Test Guild")
    
    # Add a server first
    await add_ark_server(
        100, name="Test Server", host="192.168.1.100", 
        rcon_port=27060, rcon_password="password123"
    )
    
    # Get the server to get its ID
    servers = await get_ark_servers(100)
    server_id = servers[0]['id']
    
    # Test update with optional fields (only existing DB columns)
    update_data = {
        'name': 'Server with Paths',
        'host': '192.168.1.150',
        'rcon_port': 27062,
        'rcon_password': 'pathpass',
        'max_players': 60,
        'enabled': True,
        'server_path': 'C:\\ARK\\ServerWithPaths',
        'service_name': 'ARKWithPath',
        'query_port': 27015
    }
    
    result = await update_ark_server(server_id, **update_data)
    assert result is True
    
    # Verify the update
    updated_servers = await get_ark_servers(100)
    assert len(updated_servers) == 1
    assert updated_servers[0]['name'] == 'Server with Paths'
    assert updated_servers[0]['server_path'] == 'C:\\ARK\\ServerWithPaths'
    assert updated_servers[0]['service_name'] == 'ARKWithPath'
    assert updated_servers[0]['query_port'] == 27015


@pytest.mark.asyncio
async def test_update_ark_server_minimal_data(server_config_db):
    """Test update_ark_server with minimal required fields."""
    from bot.database.server_config_db import add_ark_server, update_ark_server
    from bot.utils.config import Config
    import aiosqlite
    
    # Create guild config
    from bot.database.server_config_db import create_or_update_server_config
    await create_or_update_server_config(100, "Test Guild")
    
    # Add a server first
    await add_ark_server(
        100, name="Test Server", host="192.168.1.100", 
        rcon_port=27060, rcon_password="password123"
    )
    
    # Get the server to get its ID (using enabled servers)
    from bot.database.server_config_db import get_ark_servers
    servers = await get_ark_servers(100)
    server_id = servers[0]['id']
    
    # Test update with minimal data (no optional fields)
    update_data = {
        'name': 'Minimal Server',
        'host': '192.168.1.50',
        'rcon_port': 27063,
        'rcon_password': 'minpass',
        'max_players': 20,
        'enabled': False
    }
    
    result = await update_ark_server(server_id, **update_data)
    assert result is True
    
    # Verify the update using direct DB query (since get_ark_servers filters enabled)
    db_path = Config.DATABASE_PATH
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM ark_servers WHERE guild_id = ? AND id = ?",
            (100, server_id),
        ) as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            updated_server = dict(rows[0])
            assert updated_server['name'] == 'Minimal Server'
            assert updated_server['enabled'] == False
            assert updated_server['server_path'] is None  # Should remain None
            assert updated_server['service_name'] is None  # Should remain None
