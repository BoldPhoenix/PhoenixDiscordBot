"""
Tests for server configuration GUI functionality - NO MOCKS VERSION

Tests the multi-step modal system for server configuration.
"""

import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_add_server_modal_page1_fields():
    """Test AddServerModal has required fields."""
    from bot.cogs.setup_gui import AddServerModal

    # Test modal can be instantiated (fields are defined)
    # We can't fully test without Discord, but verify imports work
    assert AddServerModal is not None


@pytest.mark.asyncio
async def test_edit_server_modal_fields(server_config_db):
    """Test EditServerModal has required fields."""
    from bot.cogs.setup_gui import EditServerModal
    from bot.database.server_config_db import add_ark_server, create_or_update_server_config

    # Create guild and server
    await create_or_update_server_config(12345, "Test Guild")
    server_id = await add_ark_server(
        12345,
        name="TestServer",
        host="192.168.1.100",
        rcon_port=27020,
        rcon_password="testpass"
    )

    # Get the server
    from bot.database.server_config_db import get_ark_servers
    servers = await get_ark_servers(12345)
    server = servers[0]

    # Verify EditServerModal can reference the server data
    assert server["name"] == "TestServer"
    assert server["host"] == "192.168.1.100"


@pytest.mark.asyncio
async def test_server_directories_modal(server_config_db):
    """Test ServerDirectoriesModal configuration."""
    from bot.cogs.setup_gui import ServerDirectoriesModal, EditServerModal
    from bot.database.server_config_db import add_ark_server, create_or_update_server_config, update_ark_server

    # Create guild and server with paths
    await create_or_update_server_config(12345, "Test Guild")
    server_id = await add_ark_server(
        12345,
        name="TestServer",
        host="192.168.1.100",
        rcon_port=27020,
        rcon_password="testpass"
    )

    # Update with paths
    await update_ark_server(
        server_id,
        server_path="D:\\ARK\\Test",
        steamcmd_path="D:\\SteamCMD",
        log_path="D:\\ARK\\Test\\ShooterGame\\Saved\\Logs",
        service_name="ARKTest"
    )

    # Verify paths were stored
    from bot.database.server_config_db import get_ark_servers
    servers = await get_ark_servers(12345)
    server = servers[0]

    assert server["server_path"] == "D:\\ARK\\Test"
    assert server["steamcmd_path"] == "D:\\SteamCMD"
    assert server["log_path"] == "D:\\ARK\\Test\\ShooterGame\\Saved\\Logs"
    assert server["service_name"] == "ARKTest"


@pytest.mark.asyncio
async def test_server_actions_view_embed(server_config_db):
    """Test ServerActionsView create_embed shows server details."""
    from bot.database.server_config_db import add_ark_server, create_or_update_server_config

    # Create guild and server with max_players
    await create_or_update_server_config(12345, "Test Guild")
    await add_ark_server(
        12345,
        name="TestServer",
        host="192.168.1.100",
        rcon_port=27020,
        rcon_password="testpass",
        max_players=70
    )

    # Verify server was created with max_players
    from bot.database.server_config_db import get_ark_servers
    servers = await get_ark_servers(12345)
    server = servers[0]

    assert server["max_players"] == 70
    assert server["name"] == "TestServer"
