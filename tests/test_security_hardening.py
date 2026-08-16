"""
Security hardening tests — verifies all findings from the Corporate Bob audit.
"""

import inspect
import os
import re

import pytest


# ==================== H1: Auth Key Masking ====================

class TestH1AuthKeyMasking:
    """H1: Auth keys must never appear in log statements."""

    def test_no_auth_key_logged_in_remote_agent(self):
        """Verify no logger line interpolates a URI containing auth_key."""
        from bot.cogs import remote_agent
        source = inspect.getsource(remote_agent)
        # Find logger calls that reference {uri} — uri contains auth_key
        log_lines = re.findall(r'logger\.\w+\(f["\'].*?\)', source, re.DOTALL)
        for line in log_lines:
            if '{uri}' in line:
                pytest.fail(f"Log line exposes full URI (contains auth_key): {line[:120]}")


# ==================== H3: SQL Column Allowlists ====================

class TestH3SqlColumnAllowlists:
    """H3: All kwargs-to-SQL functions must filter through allowlists."""

    def test_server_config_db_uses_allowlist(self):
        from bot.database import server_config_db
        for func_name in ['create_or_update_server_config', 'update_ark_server', 'update_ark_server_by_port']:
            func_source = inspect.getsource(getattr(server_config_db, func_name))
            has_allowlist = ('_ALLOWED' in func_source or 'allowed' in func_source
                            or 'valid_fields' in func_source or 'validate_sql_columns' in func_source)
            assert has_allowlist, f"{func_name} must use a column allowlist"

    def test_maintenance_db_uses_allowlist(self):
        from bot.database import maintenance_db
        for func_name in ['update_maintenance_config', 'update_backup_schedule']:
            func_source = inspect.getsource(getattr(maintenance_db, func_name))
            has_allowlist = ('_ALLOWED' in func_source or 'allowed' in func_source
                            or 'valid_fields' in func_source or 'validate_sql_columns' in func_source)
            assert has_allowlist, f"{func_name} must use a column allowlist"


# ==================== H4: Service Name Validation ====================

class TestH4ServiceNameValidation:
    """H4: Service names from DB must be validated before subprocess calls."""

    def test_crash_monitor_validates_service_name(self):
        from bot.cogs import crash_monitor
        source = inspect.getsource(crash_monitor)
        assert 'validate_service_name' in source, \
            "crash_monitor.py must validate service names before subprocess.run"

    def test_server_monitor_validates_service_name(self):
        from bot.cogs import server_monitor
        source = inspect.getsource(server_monitor)
        assert 'validate_service_name' in source, \
            "server_monitor.py must validate service names before subprocess.run"

    def test_server_management_gui_validates_service_name(self):
        from bot.cogs import server_management_gui
        source = inspect.getsource(server_management_gui)
        assert 'validate_service_name' in source, \
            "server_management_gui.py must validate service names before subprocess.run"


# ==================== H5: RCON Input Validation ====================

class TestH5RconValidation:
    """H5: All RCON commands built from user input must validate first."""

    def test_admin_py_uses_validate_rcon_input(self):
        from bot.cogs import admin
        source = inspect.getsource(admin)
        assert 'validate_rcon_input' in source, \
            "admin.py must import and use validate_rcon_input"

    def test_player_management_gui_uses_validate_rcon_input(self):
        from bot.cogs import player_management_gui
        source = inspect.getsource(player_management_gui)
        assert 'validate_rcon_input' in source, \
            "player_management_gui.py must import and use validate_rcon_input"

    def test_enhanced_give_item_uses_validate_rcon_input(self):
        from bot.cogs import enhanced_give_item
        source = inspect.getsource(enhanced_give_item)
        assert 'validate_rcon_input' in source, \
            "enhanced_give_item.py must import and use validate_rcon_input"

    def test_player_management_uses_shared_validation(self):
        from bot.cogs import player_management
        source = inspect.getsource(player_management)
        assert 'from bot.utils.validation import validate_rcon_input' in source, \
            "player_management.py should import validate_rcon_input from shared module"


# ==================== M1: Async Sleep ====================

class TestM1AsyncSleep:
    """M1: No blocking time.sleep() in async code."""

    def test_no_time_sleep_in_any_cog(self):
        cogs_dir = os.path.join(os.path.dirname(__file__), '..', 'bot', 'cogs')
        cogs_dir = os.path.normpath(cogs_dir)
        violations = []
        for filename in os.listdir(cogs_dir):
            if filename.endswith('.py') and not filename.startswith('_') and 'backup' not in filename and '.bak' not in filename:
                filepath = os.path.join(cogs_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                if 'time.sleep(' in content:
                    violations.append(filename)
        assert not violations, f"Blocking time.sleep() found in: {', '.join(violations)}"


# ==================== M4: .env Allowlist ====================

class TestM4EnvAllowlist:
    """M4: .env writes from Discord must be restricted to known keys."""

    def test_update_env_file_has_allowlist(self):
        from bot.cogs import admin
        source = inspect.getsource(admin)
        assert '_ALLOWED_ENV_KEYS' in source, \
            "admin.py must define _ALLOWED_ENV_KEYS allowlist"

    def test_update_env_checks_allowlist(self):
        from bot.cogs.admin import Admin
        source = inspect.getsource(Admin._update_env_file)
        assert 'ALLOWED_ENV_KEYS' in source, \
            "_update_env_file must check against _ALLOWED_ENV_KEYS"


# ==================== Validation Utilities ====================

class TestValidationUtilities:
    """Shared validation functions for security boundaries."""

    def test_validate_rcon_input_allows_valid(self):
        from bot.utils.validation import validate_rcon_input
        assert validate_rcon_input("PlayerName123") is True
        assert validate_rcon_input("player_name") is True
        assert validate_rcon_input("player-name") is True
        assert validate_rcon_input("player.name") is True
        assert validate_rcon_input("abc def") is True

    def test_validate_rcon_input_rejects_invalid(self):
        from bot.utils.validation import validate_rcon_input
        assert validate_rcon_input("") is False
        assert validate_rcon_input("player;DROP TABLE") is False
        assert validate_rcon_input('player"name') is False
        assert validate_rcon_input("a" * 101) is False
        assert validate_rcon_input("player\nname") is False

    def test_validate_service_name_allows_valid(self):
        from bot.utils.validation import validate_service_name
        assert validate_service_name("PhoenixARK_TheIsland") is True
        assert validate_service_name("ark-server-1") is True
        assert validate_service_name("MyServer123") is True

    def test_validate_service_name_rejects_invalid(self):
        from bot.utils.validation import validate_service_name
        assert validate_service_name("") is False
        assert validate_service_name("svc;rm -rf /") is False
        assert validate_service_name("svc name with spaces") is False
        assert validate_service_name('svc"injection') is False
        assert validate_service_name("a" * 257) is False

    def test_validate_sql_columns_filters(self):
        from bot.utils.validation import validate_sql_columns
        allowed = {"name", "host", "port"}
        result = validate_sql_columns({"name": "test", "host": "1.2.3.4", "evil_col": "bad"}, allowed)
        assert result == {"name": "test", "host": "1.2.3.4"}
        assert "evil_col" not in result

    def test_validate_sql_columns_empty(self):
        from bot.utils.validation import validate_sql_columns
        result = validate_sql_columns({"bad": "val"}, {"good"})
        assert result == {}
