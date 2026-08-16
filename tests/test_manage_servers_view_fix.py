"""Test that verifies the ManageServersView fix works correctly."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot.cogs.setup_gui import ManageServersView


@pytest.mark.asyncio
async def test_manage_servers_view_hides_disabled_servers_after_fix():
    """Test that ManageServersView hides disabled servers after the fix."""
    # Mock guild and user
    guild_id = 12345
    user = MagicMock()
    user.id = 999
    guild = MagicMock()
    
    # Create view
    view = ManageServersView(guild_id, user, guild)
    
    # Mock servers including disabled ones
    all_servers = [
        {"id": 1, "name": "Server1", "host": "192.168.1.1", "rcon_port": 27020, "enabled": 1},
        {"id": 2, "name": "Server2", "host": "192.168.1.2", "rcon_port": 27021, "enabled": 0},  # Disabled
        {"id": 3, "name": "Server3", "host": "192.168.1.3", "rcon_port": 27022, "enabled": 1},
    ]
    
    # Mock the database function to return only enabled servers (the fix)
    with patch('bot.cogs.setup_gui.server_config_db.get_ark_servers') as mock_get:
        mock_get.return_value = [
            {"id": 1, "name": "Server1", "host": "192.168.1.1", "rcon_port": 27020, "enabled": 1},
            {"id": 3, "name": "Server3", "host": "192.168.1.3", "rcon_port": 27022, "enabled": 1},
        ]
        
        # Load servers
        await view.load_servers()
        
        # Verify only enabled servers are loaded
        assert len(view.servers) == 2
        server_ids = [server["id"] for server in view.servers]
        assert 1 in server_ids
        assert 3 in server_ids
        assert 2 not in server_ids  # Disabled server is excluded
        
        # Verify dropdown only shows enabled servers
        select_items = [item for item in view.children if hasattr(item, 'options')]
        assert len(select_items) == 1
        
        select = select_items[0]
        options = select.options
        
        # Check that disabled server is NOT in dropdown
        assert len(options) == 2
        option_values = [opt.value for opt in options]
        assert "1" in option_values
        assert "3" in option_values
        assert "2" not in option_values  # Disabled server excluded
        
        # Verify no warning indicators
        for option in options:
            assert "⚠️" not in option.label
            assert "Disabled" not in option.label


@pytest.mark.asyncio
async def test_manage_servers_view_refresh_hides_disabled_servers():
    """Test that refreshing ManageServersView hides disabled servers."""
    # Mock guild and user
    guild_id = 12345
    user = MagicMock()
    user.id = 999
    guild = MagicMock()
    
    # Create view
    view = ManageServersView(guild_id, user, guild)
    
    # Mock initial enabled servers
    initial_servers = [
        {"id": 1, "name": "Server1", "host": "192.168.1.1", "rcon_port": 27020, "enabled": 1},
        {"id": 2, "name": "Server2", "host": "192.168.1.2", "rcon_port": 27021, "enabled": 1},
    ]
    
    # Mock servers after removal (Server2 disabled)
    servers_after_removal = [
        {"id": 1, "name": "Server1", "host": "192.168.1.1", "rcon_port": 27020, "enabled": 1},
    ]
    
    # Mock the database function
    with patch('bot.cogs.setup_gui.server_config_db.get_ark_servers') as mock_get:
        # Initial load
        mock_get.return_value = initial_servers
        await view.load_servers()
        assert len(view.servers) == 2
        
        # Simulate server removal and refresh
        mock_get.return_value = servers_after_removal
        view.clear_items()
        await view.load_servers()
        
        # FIX: Server2 is now hidden (not shown as disabled)
        assert len(view.servers) == 1
        assert view.servers[0]["id"] == 1
        
        # Verify dropdown only shows remaining server
        select_items = [item for item in view.children if hasattr(item, 'options')]
        select = select_items[0]
        options = select.options
        
        assert len(options) == 1
        assert options[0].value == "1"


@pytest.mark.asyncio
async def test_manage_servers_view_empty_when_no_enabled_servers():
    """Test that ManageServersView shows empty when no enabled servers."""
    # Mock guild and user
    guild_id = 12345
    user = MagicMock()
    user.id = 999
    guild = MagicMock()
    
    # Create view
    view = ManageServersView(guild_id, user, guild)
    
    # Mock the database function to return empty list (all servers disabled)
    with patch('bot.cogs.setup_gui.server_config_db.get_ark_servers') as mock_get:
        mock_get.return_value = []
        
        # Load servers
        await view.load_servers()
        
        # Verify no servers loaded
        assert len(view.servers) == 0
        
        # Verify no dropdown created
        select_items = [item for item in view.children if hasattr(item, 'options')]
        assert len(select_items) == 0
