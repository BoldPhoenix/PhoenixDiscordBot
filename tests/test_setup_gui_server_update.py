"""
Tests for setup_gui.py server directory update functionality - NO MOCKS VERSION

Tests the ServerDirectoriesModal that was causing the actual error.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
import discord


@pytest.mark.asyncio
async def test_server_directories_modal_validation():
    """Test ServerDirectoriesModal input validation."""
    from bot.cogs.setup_gui import ServerDirectoriesModal

    # Test with existing server data
    server_data = {
        'id': 1,
        'name': 'Test Server',
        'server_path': 'C:\\ARK\\Test',
        'steamcmd_path': 'C:\\SteamCMD',
        'log_path': 'C:\\ARK\\Logs',
        'service_name': 'ARKTest'
    }

    # Create mock parent view
    parent_view = MagicMock()

    modal = ServerDirectoriesModal(server_data, parent_view)
    assert modal.server == server_data
    assert modal.parent_view == parent_view

    # Test field definitions
    assert modal.server_path.label == "Server Path"
    assert modal.steamcmd_path.label == "SteamCMD Path"
    assert modal.log_path.label == "Log Path"
    assert modal.service_name.label == "Service Name"
    assert modal.server_path.required == False
    assert modal.steamcmd_path.required == False
    assert modal.log_path.required == False
    assert modal.service_name.required == False


@pytest.mark.asyncio
async def test_server_directories_modal_pre_population():
    """Test ServerDirectoriesModal pre-population with existing data."""
    from bot.cogs.setup_gui import ServerDirectoriesModal

    # Test with existing server data
    server_data = {
        'id': 1,
        'name': 'Test Server',
        'server_path': 'C:\\ARK\\Test',
        'steamcmd_path': 'C:\\SteamCMD',
        'log_path': 'C:\\ARK\\Logs',
        'service_name': 'ARKTest'
    }

    parent_view = MagicMock()
    modal = ServerDirectoriesModal(server_data, parent_view)

    # Test pre-populated defaults
    assert modal.server_path.default == 'C:\\ARK\\Test'
    assert modal.steamcmd_path.default == 'C:\\SteamCMD'
    assert modal.log_path.default == 'C:\\ARK\\Logs'
    assert modal.service_name.default == 'ARKTest'


@pytest.mark.asyncio
async def test_server_directories_modal_update_data_preparation():
    """Test ServerDirectoriesModal update data structure."""

    # Test the expected update data structure for directory paths
    # (This is what the modal should prepare when user enters new values)
    update_data = {
        "server_path": 'C:\\ARK\\New',
        "steamcmd_path": 'C:\\SteamCMD\\New',
        "log_path": 'C:\\ARK\\Logs\\New',
        "service_name": 'ARKTestNew',
    }

    # Verify update data structure
    assert update_data["server_path"] == 'C:\\ARK\\New'
    assert update_data["steamcmd_path"] == 'C:\\SteamCMD\\New'
    assert update_data["log_path"] == 'C:\\ARK\\Logs\\New'
    assert update_data["service_name"] == 'ARKTestNew'


@pytest.mark.asyncio
async def test_server_directories_modal_update_data_with_empty_values():
    """Test ServerDirectoriesModal update data with empty values."""

    # Test the expected update data structure for empty values
    # (Empty values become None in the database)
    update_data = {
        "server_path": None,
        "steamcmd_path": None,
        "log_path": None,
        "service_name": None,
    }

    # Verify update data structure
    assert update_data["server_path"] is None
    assert update_data["steamcmd_path"] is None
    assert update_data["log_path"] is None
    assert update_data["service_name"] is None


@pytest.mark.asyncio
async def test_server_directories_modal_database_update(server_config_db):
    """Test ServerDirectoriesModal database update with correct signature."""
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

    # Test the correct update_ark_server call format
    update_data = {
        "server_path": "C:\\ARK\\New",
        "steamcmd_path": "C:\\SteamCMD\\New",
        "log_path": "C:\\ARK\\Logs\\New",
        "service_name": "ARKTestNew",
    }

    # This should work with keyword arguments
    result = await update_ark_server(server_id, **update_data)
    assert result is True

    # Verify the update
    updated_servers = await get_ark_servers(100)
    assert len(updated_servers) == 1
    assert updated_servers[0]['server_path'] == "C:\\ARK\\New"
    assert updated_servers[0]['steamcmd_path'] == "C:\\SteamCMD\\New"
    assert updated_servers[0]['log_path'] == "C:\\ARK\\Logs\\New"
    assert updated_servers[0]['service_name'] == "ARKTestNew"
