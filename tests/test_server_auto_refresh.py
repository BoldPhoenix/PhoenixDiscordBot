"""Test automatic server refresh functionality."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from bot.database import server_config_db
from bot.cogs.server_management import ServerManagementView
from bot.utils.server_events import server_events


@pytest.mark.asyncio
async def test_server_event_system():
    """Test that the server event system works correctly."""
    # Clear any existing subscribers
    server_events._subscribers.clear()
    
    guild_id = 12345
    callback_called = False
    
    async def test_callback():
        nonlocal callback_called
        callback_called = True
    
    # Subscribe to events
    server_events.subscribe(guild_id, test_callback)
    assert guild_id in server_events._subscribers
    assert test_callback in server_events._subscribers[guild_id]
    
    # Notify subscribers
    await server_events.notify_servers_changed(guild_id)
    assert callback_called
    
    # Unsubscribe
    server_events.unsubscribe(guild_id, test_callback)
    assert guild_id not in server_events._subscribers  # Should be empty now


@pytest.mark.asyncio
async def test_server_management_auto_refresh():
    """Test that ServerManagementView auto-refreshes when servers change."""
    from bot.utils.config import Config
    from pathlib import Path
    import tempfile
    
    # Create temp database
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
        
        # Add test servers
        server1_id = await server_config_db.add_ark_server(
            guild_id=12345,
            name="Server1",
            host="192.168.1.100",
            rcon_port=27020,
            rcon_password="testpass1"
        )
        
        server2_id = await server_config_db.add_ark_server(
            guild_id=12345,
            name="Server2", 
            host="192.168.1.101",
            rcon_port=27021,
            rcon_password="testpass2"
        )
        
        # Create ServerManagementView
        servers = await server_config_db.get_ark_servers(12345)
        mock_bot = AsyncMock()
        view = ServerManagementView(guild_id=12345, bot=mock_bot, servers=servers)
        
        # Mock message for auto-refresh
        mock_message = AsyncMock()
        view.message = mock_message
        
        # View should have 2 servers initially
        assert len(view.servers) == 2
        
        # Remove one server (this should trigger auto-refresh)
        await server_config_db.remove_ark_server(server1_id)
        
        # Give a moment for the event to propagate
        await asyncio.sleep(0.1)
        
        # View should now have 1 server (auto-refreshed)
        assert len(view.servers) == 1
        assert view.servers[0]["name"] == "Server2"
        
        # Verify message was updated
        mock_message.edit.assert_called()
        
        # Verify dropdown was updated
        select_items = [item for item in view.children if hasattr(item, 'options')]
        assert len(select_items) == 1
        select = select_items[0]
        assert len(select.options) == 1
        assert select.options[0].label == "Server2"
        
    finally:
        # Cleanup
        Config.DATABASE_PATH = original_path
        Path(temp_db_path).unlink(missing_ok=True)
        server_events._subscribers.clear()


@pytest.mark.asyncio
async def test_server_management_cleanup():
    """Test that ServerManagementView cleans up event subscriptions."""
    guild_id = 12345
    servers = [{"name": "Test"}]
    mock_bot = AsyncMock()
    
    # Create view
    view = ServerManagementView(guild_id, mock_bot, servers)
    
    # Should be subscribed
    assert guild_id in server_events._subscribers
    assert view._on_servers_changed in server_events._subscribers[guild_id]
    
    # Stop view
    view.stop()
    
    # Should be unsubscribed
    assert guild_id not in server_events._subscribers
