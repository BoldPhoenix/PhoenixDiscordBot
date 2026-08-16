"""Test that servers are actually deleted from database, not just disabled."""

import pytest
import tempfile
from pathlib import Path
from bot.database import server_config_db
from bot.utils.config import Config


@pytest.mark.asyncio
async def test_remove_ark_server_actually_deletes():
    """Test that remove_ark_server actually deletes the server from database."""
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        temp_db_path = f.name
    
    original_path = Config.DATABASE_PATH
    Config.DATABASE_PATH = temp_db_path
    
    try:
        # Initialize database
        from bot.database.init_db import initialize_database
        await initialize_database()
        
        # Create test guild config
        await server_config_db.create_or_update_server_config(
            guild_id=12345,
            guild_name="Test Guild"
        )
        
        # Add a server
        server_id = await server_config_db.add_ark_server(
            guild_id=12345,
            name="TestServer",
            host="192.168.1.100",
            rcon_port=27020,
            rcon_password="testpass"
        )
        
        # Verify server exists
        servers = await server_config_db.get_ark_servers(12345)
        assert len(servers) == 1
        assert servers[0]["id"] == server_id
        assert servers[0]["name"] == "TestServer"
        
        # Remove the server
        result = await server_config_db.remove_ark_server(server_id)
        assert result is True
        
        # Verify server is completely deleted (not just disabled)
        servers = await server_config_db.get_ark_servers(12345)
        assert len(servers) == 0
        
        # Verify it's not in the database at all (including disabled)
        all_servers = await server_config_db.get_all_ark_servers_including_disabled(12345)
        assert len(all_servers) == 0
        
        # Verify can't find it by ID
        server = await server_config_db.get_ark_server_by_id(server_id)
        assert server is None
        
    finally:
        # Cleanup
        Config.DATABASE_PATH = original_path
        Path(temp_db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_remove_nonexistent_server_returns_false():
    """Test that removing a non-existent server returns False."""
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        temp_db_path = f.name
    
    original_path = Config.DATABASE_PATH
    Config.DATABASE_PATH = temp_db_path
    
    try:
        # Initialize database
        from bot.database.init_db import initialize_database
        await initialize_database()
        
        # Try to remove non-existent server
        result = await server_config_db.remove_ark_server(99999)
        assert result is False
        
    finally:
        # Cleanup
        Config.DATABASE_PATH = original_path
        Path(temp_db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_can_recreate_server_after_deletion():
    """Test that a server can be recreated after deletion without conflicts."""
    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        temp_db_path = f.name
    
    original_path = Config.DATABASE_PATH
    Config.DATABASE_PATH = temp_db_path
    
    try:
        # Initialize database
        from bot.database.init_db import initialize_database
        await initialize_database()
        
        # Create test guild config
        await server_config_db.create_or_update_server_config(
            guild_id=12345,
            guild_name="Test Guild"
        )
        
        # Add a server
        server_id_1 = await server_config_db.add_ark_server(
            guild_id=12345,
            name="TestServer",
            host="192.168.1.100",
            rcon_port=27020,
            rcon_password="testpass"
        )
        
        # Remove the server
        result = await server_config_db.remove_ark_server(server_id_1)
        assert result is True
        
        # Recreate server with same details
        server_id_2 = await server_config_db.add_ark_server(
            guild_id=12345,
            name="TestServer",
            host="192.168.1.100",
            rcon_port=27020,
            rcon_password="testpass"
        )
        
        # Verify new server exists and has different ID
        servers = await server_config_db.get_ark_servers(12345)
        assert len(servers) == 1
        assert servers[0]["id"] == server_id_2
        assert servers[0]["name"] == "TestServer"
        assert server_id_2 != server_id_1  # Different ID because it's a new record
        
        # Verify only one server exists in database
        all_servers = await server_config_db.get_all_ark_servers_including_disabled(12345)
        assert len(all_servers) == 1
        
    finally:
        # Cleanup
        Config.DATABASE_PATH = original_path
        Path(temp_db_path).unlink(missing_ok=True)
