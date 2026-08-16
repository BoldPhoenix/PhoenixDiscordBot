"""Test server management refresh functionality via _on_servers_changed."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.database import server_config_db
from bot.cogs.server_management import ServerManagementView


@pytest.mark.asyncio
async def test_server_management_refresh():
    """Test that ServerManagementView._on_servers_changed refreshes its server list."""
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

        await server_config_db.add_ark_server(
            guild_id=12345,
            name="Server2",
            host="192.168.1.101",
            rcon_port=27021,
            rcon_password="testpass2"
        )

        # Create ServerManagementView with initial servers
        servers = await server_config_db.get_ark_servers(12345)
        assert len(servers) == 2

        mock_bot = AsyncMock()
        view = ServerManagementView(guild_id=12345, bot=mock_bot, servers=servers)

        # View should have 2 servers initially
        assert len(view.servers) == 2

        # Remove one server — server_events fires _on_servers_changed automatically
        await server_config_db.remove_ark_server(server1_id)

        # View should now have 1 server
        assert len(view.servers) == 1
        assert view.servers[0]["name"] == "Server2"

        # Verify dropdown was updated (should have 1 option)
        select_items = [item for item in view.children if hasattr(item, 'options')]
        assert len(select_items) == 1
        assert len(select_items[0].options) == 1
        assert select_items[0].options[0].label == "Server2"

    finally:
        Config.DATABASE_PATH = original_path
        Path(temp_db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_server_management_refresh_callback():
    """Test that _on_servers_changed updates the message ref when set."""
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

        # Add test server
        server1_id = await server_config_db.add_ark_server(
            guild_id=12345,
            name="Server1",
            host="192.168.1.100",
            rcon_port=27020,
            rcon_password="testpass1"
        )

        # Create ServerManagementView
        servers = await server_config_db.get_ark_servers(12345)
        mock_bot = AsyncMock()
        view = ServerManagementView(guild_id=12345, bot=mock_bot, servers=servers)

        # Attach a mock message reference so _on_servers_changed can edit it
        mock_message = AsyncMock()
        view._message_ref = mock_message

        # Remove server — server_events fires _on_servers_changed automatically
        await server_config_db.remove_ark_server(server1_id)

        # Verify the message was edited with an updated embed and view
        mock_message.edit.assert_called_once()
        call_kwargs = mock_message.edit.call_args.kwargs
        assert 'embed' in call_kwargs
        assert 'view' in call_kwargs
        assert call_kwargs['view'] is view

        # Verify view was refreshed (no enabled servers left)
        assert len(view.servers) == 0

    finally:
        Config.DATABASE_PATH = original_path
        Path(temp_db_path).unlink(missing_ok=True)
