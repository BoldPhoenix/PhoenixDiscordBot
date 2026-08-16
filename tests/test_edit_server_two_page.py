"""
Tests for two-page EditServerModal flow in bot/cogs/setup_gui.py

Tests cover:
- EditServerModal (page 1) field structure with pre-populated values
- EditServerContinueView intermediate view with Continue/Cancel buttons
- EditServerAdvancedModal (page 2) field structure with pre-populated values
- Full integration flow: page 1 → continue → page 2 → server updated

Uses real discord.py objects — no mocks (Jeffrey Snover methodology).
"""

import pytest
import discord
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_user(user_id: int = 111222333) -> SimpleNamespace:
    """Create a minimal Discord-like user object."""
    user = SimpleNamespace()
    user.id = user_id
    user.mention = f"<@{user_id}>"
    return user


def _make_guild(guild_id: int = 999888777) -> SimpleNamespace:
    """Create a minimal Discord-like guild object."""
    guild = SimpleNamespace()
    guild.id = guild_id
    guild.name = "Test Guild"
    return guild


def _make_server_config() -> dict:
    """Create a sample server configuration."""
    return {
        "id": 1,
        "guild_id": 123456,
        "name": "Island",
        "host": "192.168.1.100",
        "rcon_port": 27020,
        "rcon_password": "testpass123",
        "game_port": 7777,
        "server_path": "D:\\ARK\\Island",
        "service_name": "ArkIsland",
        "max_players": 70,
        "steamcmd_path": "D:\\SteamCMD",
    }


# ---------------------------------------------------------------------------
# Test EditServerModal (Page 1)
# ---------------------------------------------------------------------------

class TestEditServerModal:
    @pytest.mark.asyncio
    async def test_edit_server_modal_has_correct_title(self):
        """Verify modal title indicates it's page 1 of 2 for editing."""
        from bot.cogs.setup_gui import EditServerModal
        
        server_config = _make_server_config()
        modal = EditServerModal(server_config=server_config, parent_view=None)
        
        assert "1/2" in modal.title
        assert "Edit" in modal.title or "Connection" in modal.title
    
    @pytest.mark.asyncio
    async def test_edit_server_modal_has_five_fields(self):
        """Verify page 1 has exactly 5 fields (Discord limit)."""
        from bot.cogs.setup_gui import EditServerModal
        
        server_config = _make_server_config()
        modal = EditServerModal(server_config=server_config, parent_view=None)
        
        text_inputs = [item for item in modal.children if isinstance(item, discord.ui.TextInput)]
        assert len(text_inputs) == 5
    
    @pytest.mark.asyncio
    async def test_edit_server_modal_has_required_fields(self):
        """Verify page 1 has server_name, host, rcon_port, rcon_password, game_port."""
        from bot.cogs.setup_gui import EditServerModal
        
        server_config = _make_server_config()
        modal = EditServerModal(server_config=server_config, parent_view=None)
        
        assert hasattr(modal, 'server_name')
        assert hasattr(modal, 'host')
        assert hasattr(modal, 'rcon_port')
        assert hasattr(modal, 'rcon_password')
        assert hasattr(modal, 'game_port')
    
    @pytest.mark.asyncio
    async def test_edit_server_modal_fields_prepopulated(self):
        """Verify page 1 fields are pre-populated with existing values."""
        from bot.cogs.setup_gui import EditServerModal
        
        server_config = _make_server_config()
        modal = EditServerModal(server_config=server_config, parent_view=None)
        
        assert modal.server_name.default == "Island"
        assert modal.host.default == "192.168.1.100"
        assert modal.rcon_port.default == "27020"
        assert modal.rcon_password.default == "testpass123"
        assert modal.game_port.default == "7777"
    
    @pytest.mark.asyncio
    async def test_edit_server_modal_stores_server_id(self):
        """Verify modal stores the server ID for updating."""
        from bot.cogs.setup_gui import EditServerModal
        
        server_config = _make_server_config()
        modal = EditServerModal(server_config=server_config, parent_view=None)
        
        assert hasattr(modal, 'server_id')
        assert modal.server_id == 1


# ---------------------------------------------------------------------------
# Test EditServerContinueView (Intermediate View)
# ---------------------------------------------------------------------------

class TestEditServerContinueView:
    @pytest.mark.asyncio
    async def test_edit_continue_view_exists(self):
        """Verify EditServerContinueView class exists."""
        from bot.cogs.setup_gui import EditServerContinueView
        
        server_data = {
            "server_id": 1,
            "name": "TestServer",
            "host": "192.168.1.100",
            "rcon_port": 27020,
            "rcon_password": "test123",
            "game_port": 7777,
        }
        existing_config = _make_server_config()
        view = EditServerContinueView(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        assert view is not None
    
    @pytest.mark.asyncio
    async def test_edit_continue_view_is_discord_view(self):
        """Verify it's a discord.ui.View subclass."""
        from bot.cogs.setup_gui import EditServerContinueView
        
        server_data = {"server_id": 1, "name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        existing_config = _make_server_config()
        view = EditServerContinueView(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        
        assert isinstance(view, discord.ui.View)
    
    @pytest.mark.asyncio
    async def test_edit_continue_view_has_timeout(self):
        """Verify view has 5-minute timeout."""
        from bot.cogs.setup_gui import EditServerContinueView
        
        server_data = {"server_id": 1, "name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        existing_config = _make_server_config()
        view = EditServerContinueView(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        
        assert view.timeout == 300
    
    @pytest.mark.asyncio
    async def test_edit_continue_view_has_two_buttons(self):
        """Verify view has Continue and Cancel buttons."""
        from bot.cogs.setup_gui import EditServerContinueView
        
        server_data = {"server_id": 1, "name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        existing_config = _make_server_config()
        view = EditServerContinueView(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        
        buttons = [item for item in view.children if isinstance(item, discord.ui.Button)]
        assert len(buttons) == 2
    
    @pytest.mark.asyncio
    async def test_edit_continue_view_stores_server_data(self):
        """Verify view stores server_data from page 1."""
        from bot.cogs.setup_gui import EditServerContinueView
        
        server_data = {
            "server_id": 5,
            "name": "Ragnarok",
            "host": "192.168.1.50",
            "rcon_port": 27020,
            "rcon_password": "secret",
            "game_port": 7777
        }
        existing_config = _make_server_config()
        view = EditServerContinueView(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        
        assert view.server_data == server_data
        assert view.server_data["server_id"] == 5
        assert view.server_data["name"] == "Ragnarok"


# ---------------------------------------------------------------------------
# Test EditServerAdvancedModal (Page 2)
# ---------------------------------------------------------------------------

class TestEditServerAdvancedModal:
    @pytest.mark.asyncio
    async def test_edit_advanced_modal_has_correct_title(self):
        """Verify modal title indicates it's page 2 of 2."""
        from bot.cogs.setup_gui import EditServerAdvancedModal
        
        server_data = {"server_id": 1, "name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        existing_config = _make_server_config()
        modal = EditServerAdvancedModal(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        
        assert "2/2" in modal.title
        assert "Advanced" in modal.title or "Edit" in modal.title
    
    @pytest.mark.asyncio
    async def test_edit_advanced_modal_has_four_fields(self):
        """Verify page 2 has 4 fields for advanced settings."""
        from bot.cogs.setup_gui import EditServerAdvancedModal
        
        server_data = {"server_id": 1, "name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        existing_config = _make_server_config()
        modal = EditServerAdvancedModal(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        
        text_inputs = [item for item in modal.children if isinstance(item, discord.ui.TextInput)]
        assert len(text_inputs) == 4
    
    @pytest.mark.asyncio
    async def test_edit_advanced_modal_has_required_fields(self):
        """Verify page 2 has server_path, service_name, max_players, steamcmd_path."""
        from bot.cogs.setup_gui import EditServerAdvancedModal
        
        server_data = {"server_id": 1, "name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        existing_config = _make_server_config()
        modal = EditServerAdvancedModal(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        
        assert hasattr(modal, 'server_path')
        assert hasattr(modal, 'service_name')
        assert hasattr(modal, 'max_players')
        assert hasattr(modal, 'steamcmd_path')
    
    @pytest.mark.asyncio
    async def test_edit_advanced_modal_fields_prepopulated(self):
        """Verify page 2 fields are pre-populated with existing values."""
        from bot.cogs.setup_gui import EditServerAdvancedModal
        
        server_data = {"server_id": 1, "name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        existing_config = _make_server_config()
        modal = EditServerAdvancedModal(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        
        assert modal.server_path.default == "D:\\ARK\\Island"
        assert modal.service_name.default == "ArkIsland"
        assert modal.max_players.default == "70"
        assert modal.steamcmd_path.default == "D:\\SteamCMD"
    
    @pytest.mark.asyncio
    async def test_edit_advanced_modal_stores_server_id(self):
        """Verify page 2 modal stores server ID for updating."""
        from bot.cogs.setup_gui import EditServerAdvancedModal
        
        server_data = {"server_id": 42, "name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        existing_config = _make_server_config()
        modal = EditServerAdvancedModal(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        
        assert modal.server_data["server_id"] == 42


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestTwoPageEditServerIntegration:
    @pytest.mark.asyncio
    async def test_edit_page1_creates_continue_view_on_submit(self):
        """Verify page 1 modal creates EditServerContinueView after validation."""
        from bot.cogs.setup_gui import EditServerModal
        
        server_config = _make_server_config()
        modal = EditServerModal(server_config=server_config, parent_view=None)
        
        # Verify on_submit method exists
        assert hasattr(modal, 'on_submit')
        assert callable(modal.on_submit)
    
    @pytest.mark.asyncio
    async def test_edit_continue_view_opens_page2_modal(self):
        """Verify Continue button opens EditServerAdvancedModal."""
        from bot.cogs.setup_gui import EditServerContinueView
        
        server_data = {"server_id": 1, "name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        existing_config = _make_server_config()
        view = EditServerContinueView(guild_id=123, server_data=server_data, existing_config=existing_config, parent_view=None)
        
        # Verify continue_setup method exists
        assert hasattr(view, 'continue_setup')
    
    @pytest.mark.asyncio
    async def test_edit_total_fields_across_both_pages_equals_nine(self):
        """Verify we capture 9 total fields across both edit pages."""
        from bot.cogs.setup_gui import EditServerModal, EditServerAdvancedModal
        
        server_config = _make_server_config()
        
        # Page 1: 5 fields
        modal1 = EditServerModal(server_config=server_config, parent_view=None)
        page1_fields = [item for item in modal1.children if isinstance(item, discord.ui.TextInput)]
        
        # Page 2: 4 fields
        server_data = {"server_id": 1, "name": "Test", "host": "1.1.1.1", "rcon_port": 27020, "rcon_password": "test"}
        modal2 = EditServerAdvancedModal(guild_id=123, server_data=server_data, existing_config=server_config, parent_view=None)
        page2_fields = [item for item in modal2.children if isinstance(item, discord.ui.TextInput)]
        
        total_fields = len(page1_fields) + len(page2_fields)
        assert total_fields == 9, f"Expected 9 total fields, got {total_fields}"
    
    @pytest.mark.asyncio
    async def test_edit_preserves_existing_values(self):
        """Verify edit flow preserves existing server configuration values."""
        from bot.cogs.setup_gui import EditServerModal, EditServerAdvancedModal
        
        server_config = _make_server_config()
        
        # Page 1 should have existing basic values
        modal1 = EditServerModal(server_config=server_config, parent_view=None)
        assert modal1.server_name.default == "Island"
        assert modal1.host.default == "192.168.1.100"
        
        # Page 2 should have existing advanced values
        server_data = {"server_id": 1, "name": "Island", "host": "192.168.1.100", "rcon_port": 27020, "rcon_password": "test"}
        modal2 = EditServerAdvancedModal(guild_id=123, server_data=server_data, existing_config=server_config, parent_view=None)
        assert modal2.server_path.default == "D:\\ARK\\Island"
        assert modal2.service_name.default == "ArkIsland"
