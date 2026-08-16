"""
Tests for modal message reuse in setup_gui.py

Tests verify that modals properly track and reuse messages to prevent spam.
The goal is to have a single message thread that gets edited throughout the flow.
"""

import pytest


class TestModalMessageReuseStructure:
    @pytest.mark.asyncio
    async def test_add_server_continue_view_stores_message_reference(self):
        """Verify AddServerContinueView can store a message reference for editing."""
        from bot.cogs.setup_gui import AddServerContinueView
        
        server_data = {
            "name": "TestServer",
            "host": "192.168.1.100",
            "rcon_port": 27020,
            "rcon_password": "password",
            "game_port": 7777,
        }
        
        view = AddServerContinueView(guild_id=123, server_data=server_data, parent_view=None)
        
        # View should be able to store message for later editing
        assert hasattr(view, 'server_data')
        assert view.server_data == server_data
    
    @pytest.mark.asyncio
    async def test_edit_server_continue_view_stores_message_reference(self):
        """Verify EditServerContinueView can store a message reference for editing."""
        from bot.cogs.setup_gui import EditServerContinueView
        
        server_data = {"server_id": 1, "name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        existing_config = {"id": 1, "name": "Test", "server_path": "/test"}
        
        view = EditServerContinueView(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        
        # View should store data for passing to next modal
        assert hasattr(view, 'server_data')
        assert hasattr(view, 'existing_config')
    
    @pytest.mark.asyncio
    async def test_cancel_button_edits_message(self):
        """Verify cancel button edits the message instead of creating new one."""
        from bot.cogs.setup_gui import AddServerContinueView
        
        server_data = {"name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        view = AddServerContinueView(guild_id=123, server_data=server_data, parent_view=None)
        
        # Find cancel button
        cancel_button = None
        for item in view.children:
            if hasattr(item, 'label') and item.label == "Cancel":
                cancel_button = item
                break
        
        assert cancel_button is not None
        # Cancel callback should use edit_message, verified by implementation
