"""
Tests for INI Management components.

Tests:
- INI parser (parse, serialize, detect types)
- INI classification (dynamic vs restart-required)
- INI settings database operations
- Pending changes queue
"""

import pytest
import pytest_asyncio
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.utils.ini_parser import (
    parse_ini, serialize_ini, detect_value_type,
    merge_ini_changes, extract_settings_list, validate_ini_syntax
)
from bot.utils.ini_classification import (
    is_dynamic_setting, get_setting_category, get_category_icon,
    DYNAMIC_SETTINGS, RESTART_REQUIRED_PATTERNS
)


class TestIniParser:
    """Tests for INI parser functions."""

    def test_parse_simple_section(self):
        content = "[ServerSettings]\nMaxPlayers=70\nServerName=Test"
        result = parse_ini(content)
        
        assert "ServerSettings" in result
        assert result["ServerSettings"]["MaxPlayers"] == "70"
        assert result["ServerSettings"]["ServerName"] == "Test"

    def test_parse_multiple_sections(self):
        content = "[ServerSettings]\nMaxPlayers=70\n\n[SessionSettings]\nSessionName=MyServer"
        result = parse_ini(content)
        
        assert "ServerSettings" in result
        assert "SessionSettings" in result
        assert result["ServerSettings"]["MaxPlayers"] == "70"
        assert result["SessionSettings"]["SessionName"] == "MyServer"

    def test_parse_comments_ignored(self):
        content = "[ServerSettings]\n; This is a comment\nMaxPlayers=70\n# Another comment"
        result = parse_ini(content)
        
        assert "ServerSettings" in result
        assert result["ServerSettings"]["MaxPlayers"] == "70"
        assert "; This is a comment" not in result["ServerSettings"]

    def test_parse_empty_value(self):
        content = "[ServerSettings]\nServerPassword=\nServerName=Test"
        result = parse_ini(content)
        
        assert result["ServerSettings"]["ServerPassword"] == ""
        assert result["ServerSettings"]["ServerName"] == "Test"

    def test_parse_duplicate_keys_skipped(self):
        content = "[ServerSettings]\nMaxPlayers=70\nMaxPlayers=80\nServerName=Test"
        result = parse_ini(content)
        
        assert result["ServerSettings"]["MaxPlayers"] == "70"
        assert "MaxPlayers" in result["ServerSettings"]

    def test_parse_complex_sections_skipped(self):
        from bot.utils.ini_parser import is_complex_key
        
        content = "[/Script/ShooterGame.ShooterGameMode]\nTamingSpeedMultiplier=2.0\nConfigOverrideSupplyCrateItems=(CrateName=Test)"
        result = parse_ini(content)
        
        assert "TamingSpeedMultiplier" in result["/Script/ShooterGame.ShooterGameMode"]
        assert "ConfigOverrideSupplyCrateItems" not in result["/Script/ShooterGame.ShooterGameMode"]

    def test_is_complex_key(self):
        from bot.utils.ini_parser import is_complex_key
        
        assert is_complex_key("ConfigOverrideSupplyCrateItems") is True
        assert is_complex_key("ConfigOverrideItemCraftingCosts") is True
        assert is_complex_key("OverrideEngramEntries") is True
        assert is_complex_key("TamingSpeedMultiplier") is False
        assert is_complex_key("MaxPlayers") is False

    def test_detect_value_type_boolean(self):
        assert detect_value_type("True") == "boolean"
        assert detect_value_type("False") == "boolean"
        assert detect_value_type("true") == "boolean"
        assert detect_value_type("false") == "boolean"
        assert detect_value_type("1") == "boolean"
        assert detect_value_type("0") == "boolean"

    def test_detect_value_type_integer(self):
        assert detect_value_type("70") == "integer"
        assert detect_value_type("12345") == "integer"
        assert detect_value_type("-5") == "integer"

    def test_detect_value_type_float(self):
        assert detect_value_type("1.5") == "float"
        assert detect_value_type("0.5") == "float"
        assert detect_value_type("3.14159") == "float"

    def test_detect_value_type_string(self):
        assert detect_value_type("MyServer") == "string"
        assert detect_value_type("Hello World") == "string"
        assert detect_value_type("some/path/to/file") == "string"

    def test_detect_value_type_multiline(self):
        multiline = "ConfigOverrideSupplyCrateItems=(\n..."
        assert detect_value_type(multiline) == "multiline"

    def test_serialize_simple(self):
        data = {
            "ServerSettings": {"MaxPlayers": "70", "ServerName": "Test"}
        }
        result = serialize_ini(data)
        
        assert "[ServerSettings]" in result
        assert "MaxPlayers=70" in result
        assert "ServerName=Test" in result

    def test_extract_settings_list(self):
        data = {
            "ServerSettings": {"MaxPlayers": "70", "TamingSpeedMultiplier": "2.0"}
        }
        settings = extract_settings_list(data)
        
        assert len(settings) == 2
        
        max_players = next(s for s in settings if s["key_name"] == "MaxPlayers")
        assert max_players["section_name"] == "ServerSettings"
        assert max_players["key_value"] == "70"
        assert max_players["value_type"] == "integer"
        
        taming = next(s for s in settings if s["key_name"] == "TamingSpeedMultiplier")
        assert taming["value_type"] == "float"

    def test_validate_ini_syntax_valid(self):
        content = "[ServerSettings]\nMaxPlayers=70\n\n[SessionSettings]\nSessionName=Test"
        is_valid, error = validate_ini_syntax(content)
        
        assert is_valid is True
        assert error is None

    def test_validate_ini_syntax_invalid_section(self):
        content = "[ServerSettings\nMaxPlayers=70"
        is_valid, error = validate_ini_syntax(content)
        
        assert is_valid is False
        assert "missing ']'" in error.lower()


class TestIniClassification:
    """Tests for INI setting classification."""

    def test_dynamic_settings_are_dynamic(self):
        assert is_dynamic_setting("TamingSpeedMultiplier") is True
        assert is_dynamic_setting("HarvestAmountMultiplier") is True
        assert is_dynamic_setting("XPMultiplier") is True
        assert is_dynamic_setting("BabyMatureSpeedMultiplier") is True
        assert is_dynamic_setting("MatingIntervalMultiplier") is True

    def test_restart_required_settings_not_dynamic(self):
        assert is_dynamic_setting("ServerName") is False
        assert is_dynamic_setting("MaxPlayers") is False
        assert is_dynamic_setting("DifficultyOffset") is False
        assert is_dynamic_setting("ActiveMods") is False

    def test_game_ini_always_restart(self):
        assert is_dynamic_setting("ConfigOverrideSupplyCrateItems", "Game.ini") is False
        assert is_dynamic_setting("PerLevelStatsMultiplier_Player", "Game.ini") is False

    def test_game_user_settings_dynamic_allowed(self):
        assert is_dynamic_setting("TamingSpeedMultiplier", "GameUserSettings.ini") is True

    def test_get_setting_category(self):
        assert get_setting_category("TamingSpeedMultiplier") == "dynamic"
        assert get_setting_category("MaxPlayers") == "restart_required"

    def test_get_category_icon(self):
        assert get_category_icon("TamingSpeedMultiplier") == "🔄"
        assert get_category_icon("MaxPlayers") == "🔴"


class TestIniSettingsDatabase:
    """Tests for INI settings database operations."""

    @pytest_asyncio.fixture
    async def setup_db(self, tmp_path):
        import aiosqlite
        from bot.utils.config import Config
        
        db_path = tmp_path / "test.db"
        original_path = Config.DATABASE_PATH
        Config.DATABASE_PATH = str(db_path)
        
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS server_ini_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    server_name TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    section_name TEXT NOT NULL,
                    key_name TEXT NOT NULL,
                    key_value TEXT,
                    value_type TEXT,
                    description TEXT,
                    is_modified INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(guild_id, server_name, file_name, section_name, key_name)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ini_pending_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    server_name TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    section_name TEXT NOT NULL,
                    key_name TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT NOT NULL,
                    queued_by INTEGER,
                    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    applied_at TIMESTAMP,
                    UNIQUE(guild_id, server_name, file_name, section_name, key_name)
                )
            """)
            await db.commit()
        
        yield str(db_path)
        
        Config.DATABASE_PATH = original_path

    @pytest.mark.asyncio
    async def test_import_ini_settings(self, setup_db):
        from bot.database import ini_settings_db
        
        settings = [
            {"section_name": "ServerSettings", "key_name": "MaxPlayers", "key_value": "70", "value_type": "integer"},
            {"section_name": "ServerSettings", "key_name": "TamingSpeedMultiplier", "key_value": "1.0", "value_type": "float"},
        ]
        
        count = await ini_settings_db.import_ini_settings(12345, "TestServer", "GameUserSettings.ini", settings)
        
        assert count == 2
        
        result = await ini_settings_db.get_ini_settings(12345, "TestServer", "GameUserSettings.ini")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_ini_setting(self, setup_db):
        from bot.database import ini_settings_db
        
        settings = [
            {"section_name": "ServerSettings", "key_name": "MaxPlayers", "key_value": "70", "value_type": "integer"},
        ]
        
        await ini_settings_db.import_ini_settings(12345, "TestServer", "GameUserSettings.ini", settings)
        
        result = await ini_settings_db.get_ini_setting(12345, "TestServer", "GameUserSettings.ini", "ServerSettings", "MaxPlayers")
        
        assert result is not None
        assert result["key_value"] == "70"

    @pytest.mark.asyncio
    async def test_update_ini_setting(self, setup_db):
        from bot.database import ini_settings_db
        
        success = await ini_settings_db.update_ini_setting(
            12345, "TestServer", "GameUserSettings.ini", "ServerSettings", "MaxPlayers", "80"
        )
        
        assert success is True
        
        result = await ini_settings_db.get_ini_setting(12345, "TestServer", "GameUserSettings.ini", "ServerSettings", "MaxPlayers")
        assert result["key_value"] == "80"
        assert result["is_modified"] == 1

    @pytest.mark.asyncio
    async def test_queue_ini_change(self, setup_db):
        from bot.database import ini_settings_db
        
        success = await ini_settings_db.queue_ini_change(
            12345, "TestServer", "GameUserSettings.ini", "ServerSettings", "MaxPlayers", "100", "70", 999
        )
        
        assert success is True
        
        pending = await ini_settings_db.get_pending_changes(12345, "TestServer")
        assert len(pending) == 1
        assert pending[0]["new_value"] == "100"
        assert pending[0]["old_value"] == "70"

    @pytest.mark.asyncio
    async def test_get_pending_changes_count(self, setup_db):
        from bot.database import ini_settings_db
        
        await ini_settings_db.queue_ini_change(
            12345, "TestServer", "GameUserSettings.ini", "ServerSettings", "MaxPlayers", "100", "70", 999
        )
        await ini_settings_db.queue_ini_change(
            12345, "TestServer", "GameUserSettings.ini", "ServerSettings", "ServerName", "NewName", "OldName", 999
        )
        
        count = await ini_settings_db.get_pending_changes_count(12345, "TestServer")
        assert count == 2

    @pytest.mark.asyncio
    async def test_clear_pending_change(self, setup_db):
        from bot.database import ini_settings_db
        
        await ini_settings_db.queue_ini_change(
            12345, "TestServer", "GameUserSettings.ini", "ServerSettings", "MaxPlayers", "100", "70", 999
        )
        
        pending = await ini_settings_db.get_pending_changes(12345, "TestServer")
        assert len(pending) == 1
        
        success = await ini_settings_db.clear_pending_change(pending[0]["id"])
        assert success is True
        
        pending = await ini_settings_db.get_pending_changes(12345, "TestServer")
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_mark_change_applied(self, setup_db):
        from bot.database import ini_settings_db
        
        await ini_settings_db.queue_ini_change(
            12345, "TestServer", "GameUserSettings.ini", "ServerSettings", "MaxPlayers", "100", "70", 999
        )
        
        pending = await ini_settings_db.get_pending_changes(12345, "TestServer")
        assert pending[0]["applied_at"] is None
        
        success = await ini_settings_db.mark_change_applied(pending[0]["id"])
        assert success is True
        
        pending = await ini_settings_db.get_pending_changes(12345, "TestServer")
        assert len(pending) == 0


class TestLifecycleManager:
    """Tests for Server Lifecycle Manager."""

    def test_lifecycle_manager_creation(self):
        from bot.utils.lifecycle_manager import ServerLifecycleManager
        
        mock_agent_manager = object()
        manager = ServerLifecycleManager(mock_agent_manager)
        
        assert manager.agent_manager is mock_agent_manager
        assert len(manager._pre_stop_hooks) == 0
        assert len(manager._post_stop_hooks) == 0

    def test_register_hooks(self):
        from bot.utils.lifecycle_manager import ServerLifecycleManager
        
        manager = ServerLifecycleManager(object())
        
        async def pre_stop_hook(guild_id, server_name, reason):
            pass
        
        async def post_stop_hook(guild_id, server_name, reason):
            pass
        
        manager.register_pre_stop_hook(pre_stop_hook)
        manager.register_post_stop_hook(post_stop_hook)
        
        assert len(manager._pre_stop_hooks) == 1
        assert len(manager._post_stop_hooks) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
