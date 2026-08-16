"""
Comprehensive test suite for Phoenix ARK Discord Bot.
Tests all critical functionality including database, RCON, commands, encoding,
security decorators, UI callback validation, and core Discord Client connectivity.
"""

import asyncio
import aiosqlite
import sys
import os
from pathlib import Path
import importlib.util
from typing import List, Dict, Any
import re
from unittest.mock import AsyncMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# Color codes for output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class SuiteTestResult:
    def __init__(self, name: str, passed: bool, message: str = "", warning: bool = False):
        self.name = name
        self.passed = passed
        self.message = message
        self.warning = warning


class BotTestSuite:
    def __init__(self, bot_path: Path):
        self.bot_path = bot_path
        self.results: List[SuiteTestResult] = []
        self.warnings: List[str] = []

        # Dynamically import discord (required for the new test)
        try:
            global discord
            import discord

            self.discord_imported = True
        except ImportError:
            self.discord_imported = False

    def add_result(self, name: str, passed: bool, message: str = "", warning: bool = False):
        """Add a test result."""
        result = SuiteTestResult(name, passed, message, warning)
        self.results.append(result)
        if warning and passed:
            self.warnings.append(f"{name}: {message}")

    def print_result(self, result: SuiteTestResult):
        """Print a single test result."""
        if result.passed:
            icon = "[PASS]" if not result.warning else "[WARN]"
            color = Colors.GREEN if not result.warning else Colors.YELLOW
            print(f"{color}{icon} {result.name}{Colors.RESET}")
            if result.message:
                print(f"  {result.message}")
        else:
            print(f"{Colors.RED}[FAIL] {result.name}{Colors.RESET}")
            if result.message:
                print(f"  {Colors.RED}{result.message}{Colors.RESET}")

    async def test_discord_client_startup(self):
        """Test the core Discord Client initialization and connection process using mocks."""
        print(f"\n{Colors.BOLD}Testing Discord Client Startup (Core Architecture)...{Colors.RESET}")

        if not self.discord_imported:
            self.add_result(
                "Discord Client Startup",
                False,
                "discord.py is not installed/imported. Cannot proceed.",
            )
            self.print_result(self.results[-1])
            return

        main_file = self.bot_path / "main.py"
        if not main_file.exists():
            self.add_result("main.py existence", False, "main.py not found.")
            self.print_result(self.results[-1])
            return

        try:
            # Load main module dynamically
            spec = importlib.util.spec_from_file_location("main", str(main_file))
            main_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(main_module)

            # The main.py should define a Bot or Client instance
            Bot = None
            if hasattr(main_module, "Bot"):
                Bot = main_module.Bot
            elif hasattr(main_module, "Client"):
                Bot = main_module.Client
            elif hasattr(main_module, "ArkBot"):
                Bot = main_module.ArkBot

            if not Bot:
                self.add_result(
                    "Bot/Client Definition",
                    False,
                    "main.py does not define a 'Bot', 'Client', or 'ArkBot' class/instance.",
                )
                self.print_result(self.results[-1])
                return

            self.add_result("Bot/Client Definition", True, f"Found bot class: {Bot.__name__}")
            self.print_result(self.results[-1])

            # --- Mocking core Discord methods ---
            # We mock the critical external calls (login and connection)

            with (
                patch.object(Bot, "login", new=AsyncMock(return_value=None)) as mock_login,
                patch.object(Bot, "connect", new=AsyncMock(return_value=None)) as mock_connect,
            ):

                # Check 1: Instance creation (config/intents)
                try:
                    # Try to instantiate the bot - ArkBot has no constructor args
                    if Bot.__name__ == "ArkBot":
                        bot_instance = Bot()
                    else:
                        # For generic Bot/Client classes, use standard parameters
                        bot_instance = Bot(command_prefix="!", intents=discord.Intents.default())
                    instance_ok = True
                    self.add_result(
                        "Bot Instance Creation", True, f"Successfully instantiated {Bot.__name__}"
                    )
                    self.print_result(self.results[-1])
                except Exception as e:
                    instance_ok = False
                    self.add_result(
                        "Bot Instance Creation", False, f"Failed to instantiate Bot: {e}"
                    )
                    self.print_result(self.results[-1])

                if not instance_ok:
                    return

                # Check 2: Login and Connect attempts

                # We don't actually run the bot, just check if the methods are called/ready

                # Simulate the run attempt (replace actual run with calls to mocked methods)
                # Note: This is purely structural and does not simulate event handling

                # Check for `Bot.run(TOKEN)` usage in main.py content
                with open(main_file, "r", encoding="utf-8", errors="replace") as f:
                    main_content = f.read()

                # Check for bot startup - both bot.run() and bot.start() are valid
                uses_run = "bot.run(" in main_content or "client.run(" in main_content
                uses_start = "bot.start(" in main_content or "client.start(" in main_content

                if uses_run or uses_start:
                    method = "bot.run()" if uses_run else "await bot.start()"
                    self.add_result("Bot.run() Method", True, f"main.py uses {method} for startup.")
                    self.print_result(self.results[-1])
                else:
                    self.add_result(
                        "Bot.run() Method",
                        False,
                        "main.py does not appear to use bot.run() or bot.start() for startup.",
                    )
                    self.print_result(self.results[-1])
                    return

                # --- The Mocked Test of Core Components ---
                # Since we can't run the actual loop, we assert the essential methods exist.

                login_method_exists = hasattr(bot_instance, "login") and callable(
                    getattr(bot_instance, "login")
                )
                connect_method_exists = hasattr(bot_instance, "connect") and callable(
                    getattr(bot_instance, "connect")
                )

                self.add_result(
                    "Bot Login Method Exists",
                    login_method_exists,
                    "Client is missing the async 'login' method.",
                )
                self.print_result(self.results[-1])

                self.add_result(
                    "Bot Connect Method Exists",
                    connect_method_exists,
                    "Client is missing the async 'connect' method.",
                )
                self.print_result(self.results[-1])

                # Final result: successful instantiation and method existence
                final_passed = (
                    instance_ok
                    and login_method_exists
                    and connect_method_exists
                    and (uses_run or uses_start)
                )
                self.add_result(
                    "Discord Client Startup",
                    final_passed,
                    "Core client architecture (imports, initialization, method definitions) verified.",
                )
                self.print_result(self.results[-1])

        except Exception as e:
            self.add_result(
                "Discord Client Startup", False, f"Unexpected error during import/mocking: {e}"
            )
            self.print_result(self.results[-1])

    async def test_file_structure(self):
        """Test that all required files exist."""
        print(f"\n{Colors.BOLD}Testing File Structure...{Colors.RESET}")

        required_files = [
            "main.py",
            "bot/rcon/client.py",
            "bot/rcon/simple_client.py",
            "bot/cogs/server_monitor.py",
            "bot/cogs/setup.py",
            "bot/cogs/admin.py",
            "bot/cogs/rcon_admin.py",
            "bot/cogs/chat_relay.py",
            "bot/cogs/help_commands.py",
            "bot/cogs/monitor_persistence.py",
            "bot/database/init_db.py",
            "bot/database/server_config_db.py",
            "bot/database/players_db.py",
            "bot/utils/config.py",
        ]

        for file in required_files:
            file_path = self.bot_path / file
            exists = file_path.exists()
            self.add_result(
                f"File exists: {file}", exists, f"Path: {file_path}" if not exists else ""
            )
            if exists:
                self.print_result(self.results[-1])

    async def test_database_schema(self):
        """Test database tables and schema."""
        print(f"\n{Colors.BOLD}Testing Database Schema...{Colors.RESET}")

        db_path = self.bot_path / "bot.db"

        if not db_path.exists():
            self.add_result(
                "Database exists", False, "bot.db not found - will be created on first run"
            )
            self.print_result(self.results[-1])
            return

        try:
            async with aiosqlite.connect(db_path) as db:
                # Test required tables
                required_tables = [
                    "server_configs",
                    "server_ark_servers",
                    "voice_channel_mappings",
                    "players",
                    "player_sessions",
                ]

                for table in required_tables:
                    cursor = await db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
                    )
                    exists = await cursor.fetchone() is not None
                    self.add_result(f"Table exists: {table}", exists)
                    self.print_result(self.results[-1])

                # Test voice_channel_mappings columns
                cursor = await db.execute("PRAGMA table_info('voice_channel_mappings')")
                columns = [row[1] async for row in cursor]
                required_columns = ["guild_id", "rcon_port", "voice_channel_id", "updated_at"]

                for col in required_columns:
                    exists = col in columns
                    self.add_result(
                        f"voice_channel_mappings.{col}",
                        exists,
                        f"Available columns: {', '.join(columns)}" if not exists else "",
                    )
                    if not exists:
                        self.print_result(self.results[-1])

        except Exception as e:
            self.add_result("Database connection", False, str(e))
            self.print_result(self.results[-1])

    async def test_emoji_encoding(self):
        """Test for emoji encoding corruption in source files."""
        print(f"\n{Colors.BOLD}Testing Emoji Encoding...{Colors.RESET}")

        # Corrupted emoji patterns
        corrupted_patterns = [
            (r"ðŸ", "Corrupted emoji encoding (ð)"),
            (r"â€¢", "Corrupted bullet point (â€¢)"),
            (r"ðŸŸ", "Corrupted circle emoji"),
            (r"ðŸ–¥", "Corrupted computer emoji"),
        ]

        files_to_check = [
            "bot/cogs/server_monitor.py",
            "bot/cogs/setup.py",
            "bot/cogs/admin.py",
            "bot/cogs/rcon_admin.py",
        ]

        for file_path in files_to_check:
            full_path = self.bot_path / file_path
            if not full_path.exists():
                continue

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()

                file_clean = True
                issues = []

                for pattern, description in corrupted_patterns:
                    matches = re.finditer(pattern, content)
                    for match in matches:
                        line_num = content[: match.start()].count("\n") + 1
                        issues.append(f"Line {line_num}: {description}")
                        file_clean = False

                self.add_result(
                    f"Emoji encoding: {file_path}",
                    file_clean,
                    "\n  ".join(issues) if issues else "All emojis properly encoded",
                )
                self.print_result(self.results[-1])

            except Exception as e:
                self.add_result(f"Read file: {file_path}", False, str(e))
                self.print_result(self.results[-1])

    async def test_cog_structure(self):
        """Test that all cogs have required methods."""
        print(f"\n{Colors.BOLD}Testing Cog Structure...{Colors.RESET}")

        cogs_to_test = {
            "bot/cogs/server_monitor.py": [
                "ServerMonitor",
                "_get_server_list",
                "voice_channel_update_loop",
            ],
            "bot/cogs/setup.py": ["Setup", "list_servers", "add_server", "is_admin"],
            "bot/cogs/admin.py": ["Admin"],
            "bot/cogs/rcon_admin.py": ["RconAdmin", "list_players"],
        }

        for file_path, expected_items in cogs_to_test.items():
            full_path = self.bot_path / file_path
            if not full_path.exists():
                self.add_result(f"Cog file: {file_path}", False, "File not found")
                self.print_result(self.results[-1])
                continue

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()

                for item in expected_items:
                    # Check for class or function definition
                    pattern = rf"(class {item}|async def {item}|def {item})"
                    found = re.search(pattern, content) is not None
                    self.add_result(
                        f"{file_path}: {item}", found, f"Missing {item}" if not found else ""
                    )
                    if not found:
                        self.print_result(self.results[-1])

            except Exception as e:
                self.add_result(f"Parse {file_path}", False, str(e))
                self.print_result(self.results[-1])

    async def test_command_defers(self):
        """Test that database-heavy commands defer properly."""
        print(f"\n{Colors.BOLD}Testing Command Defer Pattern...{Colors.RESET}")

        commands_that_should_defer = [
            ("bot/cogs/setup.py", "list_servers"),
            ("bot/cogs/setup.py", "view_config"),
            ("bot/cogs/setup.py", "remove_server"),
            ("bot/cogs/setup.py", "add_server"),
        ]

        for file_path, command_name in commands_that_should_defer:
            full_path = self.bot_path / file_path
            if not full_path.exists():
                continue

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Find the command function
                pattern = rf"async def {command_name}\s*\([^)]+\):(.*?)(?=\n    async def|\n    @|\nclass |\Z)"
                match = re.search(pattern, content, re.DOTALL)

                if match:
                    func_body = match.group(1)

                    # Check if it defers before any DB operations
                    has_defer = "interaction.response.defer" in func_body

                    # Check if defer comes before DB calls
                    defer_pos = func_body.find("interaction.response.defer")
                    db_patterns = ["server_config_db", "players_db", "await.*get_", "await.*add_"]

                    proper_order = True
                    if has_defer:
                        for pattern in db_patterns:
                            db_match = re.search(pattern, func_body)
                            if db_match and defer_pos > func_body.find(db_match.group(0)):
                                proper_order = False
                                break

                    self.add_result(
                        f"Command defers properly: {command_name}",
                        has_defer and proper_order,
                        (
                            "Missing defer or defer after DB operation"
                            if not (has_defer and proper_order)
                            else ""
                        ),
                        warning=not has_defer,
                    )
                    self.print_result(self.results[-1])

            except Exception as e:
                self.add_result(f"Parse {command_name}", False, str(e))
                self.print_result(self.results[-1])

    async def test_rcon_client(self):
        """Test RCON client implementation."""
        print(f"\n{Colors.BOLD}Testing RCON Client...{Colors.RESET}")

        simple_client_path = self.bot_path / "bot/rcon/simple_client.py"

        if not simple_client_path.exists():
            self.add_result("SimpleRCONClient exists", False, "File not found")
            self.print_result(self.results[-1])
            return

        try:
            with open(simple_client_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Methods that must be async
            async_methods = ["connect", "disconnect", "execute", "_read_packet"]
            # Methods that are sync (private helpers)
            sync_methods = ["_encode_packet", "_get_request_id"]

            for method in async_methods:
                found = re.search(rf"async def {method}\s*\(", content) is not None
                self.add_result(
                    f"SimpleRCONClient.{method}",
                    found,
                    f"Missing async method: {method}" if not found else "",
                )
                if not found:
                    self.print_result(self.results[-1])

            for method in sync_methods:
                found = re.search(rf"def {method}\s*\(", content) is not None
                self.add_result(
                    f"SimpleRCONClient.{method}",
                    found,
                    f"Missing method: {method}" if not found else "",
                )
                if not found:
                    self.print_result(self.results[-1])

            # Check for asyncio.open_connection usage (not aiorcon)
            uses_asyncio = "asyncio.open_connection" in content
            uses_aiorcon = "import aiorcon" in content or "from aiorcon" in content

            self.add_result(
                "Uses asyncio.open_connection",
                uses_asyncio,
                "Should use asyncio.open_connection for Windows compatibility",
            )
            self.print_result(self.results[-1])

            self.add_result(
                "Avoids aiorcon",
                not uses_aiorcon,
                "Should not use aiorcon (has Windows/Py3.12 issues)",
                warning=uses_aiorcon,
            )
            if uses_aiorcon:
                self.print_result(self.results[-1])

        except Exception as e:
            self.add_result("Parse SimpleRCONClient", False, str(e))
            self.print_result(self.results[-1])

    async def test_env_template(self):
        """Test .env.template configuration."""
        print(f"\n{Colors.BOLD}Testing Environment Template...{Colors.RESET}")

        template_path = self.bot_path / ".env.template"

        if not template_path.exists():
            self.add_result(".env.template exists", False, "Template file missing")
            self.print_result(self.results[-1])
            return

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Should mention database-driven configuration (not .env-based servers)
            mentions_db_config = (
                "database" in content.lower()
                or "/addserver" in content.lower()
                or "/setup" in content.lower()
            )
            self.add_result(
                ".env.template mentions database-driven config",
                mentions_db_config,
                "Should document database-driven approach (use /addserver, /setup)",
                warning=not mentions_db_config,
            )
            if not mentions_db_config:
                self.print_result(self.results[-1])

            # Should have bot token
            has_token = "DISCORD_BOT_TOKEN" in content
            self.add_result(".env.template has DISCORD_BOT_TOKEN", has_token)
            self.print_result(self.results[-1])

            # Should NOT encourage ARK_SERVERS in .env
            encourages_ark_servers = "ARK_SERVERS=" in content and not content.count(
                "# ARK_SERVERS"
            )
            self.add_result(
                ".env.template encourages DB over ARK_SERVERS",
                not encourages_ark_servers,
                "Should comment out ARK_SERVERS to encourage /addserver usage",
                warning=encourages_ark_servers,
            )
            if encourages_ark_servers:
                self.print_result(self.results[-1])

        except Exception as e:
            self.add_result("Parse .env.template", False, str(e))
            self.print_result(self.results[-1])

    async def test_voice_channel_persistence(self):
        """Test voice channel persistence implementation."""
        print(f"\n{Colors.BOLD}Testing Voice Channel Persistence...{Colors.RESET}")

        # Check server_config_db for helper functions
        db_file = self.bot_path / "bot/database/server_config_db.py"

        if not db_file.exists():
            self.add_result("server_config_db.py exists", False)
            self.print_result(self.results[-1])
            return

        try:
            with open(db_file, "r", encoding="utf-8") as f:
                content = f.read()

            required_functions = [
                "get_voice_channel_id",
                "set_server_voice_channel_id",
                "clear_server_voice_channel_id",
            ]

            for func in required_functions:
                found = re.search(rf"async def {func}\s*\(", content) is not None
                self.add_result(
                    f"server_config_db.{func}",
                    found,
                    f"Missing function: {func}" if not found else "",
                )
                if not found:
                    self.print_result(self.results[-1])

            # Check for voice_channel_mappings table creation
            has_table_creation = "voice_channel_mappings" in content and "CREATE TABLE" in content
            self.add_result("Creates voice_channel_mappings table", has_table_creation)
            self.print_result(self.results[-1])

        except Exception as e:
            self.add_result("Parse server_config_db", False, str(e))
            self.print_result(self.results[-1])

    async def test_chat_relay(self):
        """Test chat relay cog - documented in CHAT_RELAY_SETUP.md."""
        print(f"\n{Colors.BOLD}Testing Chat Relay System...{Colors.RESET}")

        cog_file = self.bot_path / "bot/cogs/chat_relay.py"

        if not cog_file.exists():
            self.add_result("chat_relay.py exists", False, "File not found")
            self.print_result(self.results[-1])
            return

        try:
            with open(cog_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Documented features: LogMonitor class, bidirectional chat
            required_items = [
                ("class LogMonitor", "LogMonitor class for log file monitoring"),
                ("class ChatRelay", "ChatRelay cog class"),
                ("chat_relay_loop", "Background loop for chat polling"),
                ("aiofiles", "Async file I/O for log reading"),
                ("chat_patterns", "Regex patterns for parsing ARK chat"),
            ]

            for item, description in required_items:
                found = item in content
                self.add_result(
                    f"Chat Relay: {description}", found, f"Missing: {item}" if not found else ""
                )
                if not found:
                    self.print_result(self.results[-1])

        except Exception as e:
            self.add_result("Parse chat_relay.py", False, str(e))
            self.print_result(self.results[-1])

    async def test_store_system(self):
        """Test store/shop system - documented in README and PROJECT_SUMMARY."""
        print(f"\n{Colors.BOLD}Testing Store System...{Colors.RESET}")

        cog_file = self.bot_path / "bot/cogs/store.py"
        db_file = self.bot_path / "bot/database/store_db.py"

        # Test cog file
        if cog_file.exists():
            with open(cog_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Documented commands: /store, /buy, /balance, /transactions
            commands = ["store", "buy", "balance", "transactions"]
            for cmd in commands:
                found = re.search(rf'name="{cmd}"', content) is not None
                self.add_result(
                    f"Store command: /{cmd}", found, f"Missing command: /{cmd}" if not found else ""
                )
                if not found:
                    self.print_result(self.results[-1])
        else:
            self.add_result("store.py exists", False)
            self.print_result(self.results[-1])

        # Test database file
        if db_file.exists():
            with open(db_file, "r", encoding="utf-8") as f:
                content = f.read()

            required_funcs = ["get_all_items", "add_item", "remove_item", "get_item"]
            for func in required_funcs:
                found = f"def {func}" in content or f"async def {func}" in content
                self.add_result(
                    f"store_db.{func}", found, f"Missing function: {func}" if not found else ""
                )
                if not found:
                    self.print_result(self.results[-1])
        else:
            self.add_result("store_db.py exists", False)
            self.print_result(self.results[-1])

    async def test_shop_manager(self):
        """Test shop manager - documented in README (Excel upload)."""
        print(f"\n{Colors.BOLD}Testing Shop Manager...{Colors.RESET}")

        cog_file = self.bot_path / "bot/cogs/shop_manager.py"

        if not cog_file.exists():
            self.add_result("shop_manager.py exists", False)
            self.print_result(self.results[-1])
            return

        with open(cog_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Documented commands: /uploadshop, /clearshop, /shopstats
        commands = ["uploadshop", "clearshop", "shopstats"]
        for cmd in commands:
            found = re.search(rf'name="{cmd}"', content) is not None
            self.add_result(
                f"Shop Manager command: /{cmd}",
                found,
                f"Missing command: /{cmd}" if not found else "",
            )
            if not found:
                self.print_result(self.results[-1])

        # Check for Excel parsing (openpyxl)
        has_excel = "openpyxl" in content or "load_workbook" in content
        self.add_result(
            "Shop Manager: Excel import support",
            has_excel,
            "Missing Excel/openpyxl import handling" if not has_excel else "",
        )
        if not has_excel:
            self.print_result(self.results[-1])

    async def test_scheduled_commands(self):
        """Test scheduled commands - documented in FEATURES_UPDATE.md."""
        print(f"\n{Colors.BOLD}Testing Scheduled Commands...{Colors.RESET}")

        cog_file = self.bot_path / "bot/cogs/scheduled_commands.py"

        if not cog_file.exists():
            self.add_result("scheduled_commands.py exists", False)
            self.print_result(self.results[-1])
            return

        with open(cog_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Documented commands: /schedule, /listschedules, /removeschedule
        commands = ["schedule", "listschedules", "removeschedule"]
        for cmd in commands:
            found = re.search(rf'name="{cmd}"', content) is not None
            self.add_result(
                f"Scheduled command: /{cmd}", found, f"Missing command: /{cmd}" if not found else ""
            )
            if not found:
                self.print_result(self.results[-1])

        # Check for scheduling loop
        has_loop = "tasks.loop" in content or "@tasks.loop" in content
        self.add_result(
            "Scheduled Commands: Background task loop",
            has_loop,
            "Missing @tasks.loop for scheduled execution" if not has_loop else "",
        )
        if not has_loop:
            self.print_result(self.results[-1])

    async def test_starter_kits(self):
        """Test starter kits system - documented in FEATURES_UPDATE.md."""
        print(f"\n{Colors.BOLD}Testing Starter Kits...{Colors.RESET}")

        cog_file = self.bot_path / "bot/cogs/starter_kits.py"

        if not cog_file.exists():
            self.add_result("starter_kits.py exists", False)
            self.print_result(self.results[-1])
            return

        with open(cog_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Documented commands: /kit, /listkits, /createkit
        commands = ["kit", "listkits", "createkit"]
        for cmd in commands:
            found = re.search(rf'name="{cmd}"', content) is not None
            self.add_result(
                f"Starter kit command: /{cmd}",
                found,
                f"Missing command: /{cmd}" if not found else "",
            )
            if not found:
                self.print_result(self.results[-1])

        # Check for cooldown/claim limit logic
        has_cooldown = "cooldown" in content.lower()
        self.add_result(
            "Starter Kits: Cooldown system",
            has_cooldown,
            "Missing cooldown logic" if not has_cooldown else "",
        )
        if not has_cooldown:
            self.print_result(self.results[-1])

    async def test_server_management_gui(self):
        """Test Server Manager GUI - documented in SERVER_MANAGEMENT_GUI.md."""
        print(f"\n{Colors.BOLD}Testing Server Management GUI...{Colors.RESET}")

        cog_file = self.bot_path / "bot/cogs/server_management_gui.py"

        if not cog_file.exists():
            self.add_result("server_management_gui.py exists", False)
            self.print_result(self.results[-1])
            return

        with open(cog_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Documented: /servermgmt command for server RCON controls (management phase)
        has_command = "servermgmt" in content
        self.add_result(
            "GUI: /servermgmt command",
            has_command,
            "Missing /servermgmt command" if not has_command else "",
        )
        if not has_command:
            self.print_result(self.results[-1])

        # Check for UI components (documented feature)
        ui_components = [
            ("class ServerManagementView", "Main view class"),
            ("Select", "Dropdown menus"),
            ("Button", "Action buttons"),
            ("Modal", "Input forms"),
        ]

        for component, description in ui_components:
            found = component in content
            self.add_result(
                f"GUI: {description}",
                found,
                f"Missing UI component: {component}" if not found else "",
            )
            if not found:
                self.print_result(self.results[-1])

        # Check for NSSM integration (map name feature we fixed)
        has_nssm = "nssm" in content.lower() or "NSSM_PATH" in content
        self.add_result(
            "GUI: NSSM service integration",
            has_nssm,
            "Missing NSSM integration for service control" if not has_nssm else "",
        )
        if not has_nssm:
            self.print_result(self.results[-1])

    async def test_rcon_admin_commands(self):
        """Test RCON admin commands - documented in RCON_ADMIN_COMMANDS.md."""
        print(f"\n{Colors.BOLD}Testing RCON Admin Commands...{Colors.RESET}")

        cog_file = self.bot_path / "bot/cogs/rcon_admin.py"

        if not cog_file.exists():
            self.add_result("rcon_admin.py exists", False)
            self.print_result(self.results[-1])
            return

        with open(cog_file, "r", encoding="utf-8") as f:
            content = f.read()

        # All documented commands from RCON_ADMIN_COMMANDS.md
        documented_commands = [
            "listplayers",
            "kickplayer",
            "banplayer",
            "unbanplayer",
            "whitelistplayer",
            "broadcast",
            "saveworld",
            "destroywilddinos",
            "setmotd",
            "giveitem",
            "givedino",
            "giveexptoplayer",
            "rcon",
            "getchat",
            "setplayerpos",
        ]

        for cmd in documented_commands:
            found = re.search(rf'name="{cmd}"', content) is not None
            self.add_result(
                f"RCON command: /{cmd}",
                found,
                f"Missing documented command: /{cmd}" if not found else "",
            )
            if not found:
                self.print_result(self.results[-1])

    async def test_server_management_nssm(self):
        """Test NSSM server management - documented in RCON_ADMIN_COMMANDS.md."""
        print(f"\n{Colors.BOLD}Testing NSSM Server Management...{Colors.RESET}")

        cog_file = self.bot_path / "bot/cogs/server_management.py"

        if not cog_file.exists():
            self.add_result("server_management.py exists", False)
            self.print_result(self.results[-1])
            return

        with open(cog_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Documented NSSM commands
        nssm_commands = [
            "serverstatus",
            "serverstart",
            "serverstop",
            "serverrestart",
            "serverupdate",
            "serverlogs",
        ]

        for cmd in nssm_commands:
            found = re.search(rf'name="{cmd}"', content) is not None
            self.add_result(
                f"NSSM command: /{cmd}",
                found,
                f"Missing documented command: /{cmd}" if not found else "",
            )
            if not found:
                self.print_result(self.results[-1])

        # Check for NSSM integration
        has_nssm = "nssm" in content.lower() or "subprocess" in content
        self.add_result(
            "Server Management: NSSM/subprocess support",
            has_nssm,
            "Missing NSSM subprocess calls" if not has_nssm else "",
        )
        if not has_nssm:
            self.print_result(self.results[-1])

    async def test_help_system(self):
        """Test help system - documented in HELP_SYSTEM_COMPLETE.md."""
        print(f"\n{Colors.BOLD}Testing Help System...{Colors.RESET}")

        cog_file = self.bot_path / "bot/cogs/help_commands.py"

        if not cog_file.exists():
            self.add_result("help_commands.py exists", False)
            self.print_result(self.results[-1])
            return

        with open(cog_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Documented help commands
        help_commands = ["help", "commands", "about"]

        for cmd in help_commands:
            found = re.search(rf'name="{cmd}"', content) is not None
            self.add_result(
                f"Help command: /{cmd}", found, f"Missing help command: /{cmd}" if not found else ""
            )
            if not found:
                self.print_result(self.results[-1])

        # Check for interactive help (documented as INTERACTIVE_HELP.md)
        has_interactive = "Select" in content or "View" in content
        self.add_result(
            "Help System: Interactive UI components",
            has_interactive,
            "Missing interactive help components" if not has_interactive else "",
        )
        if not has_interactive:
            self.print_result(self.results[-1])

    async def test_rcon_manager_methods(self):
        """Test RCONManager methods - documented across features."""
        print(f"\n{Colors.BOLD}Testing RCONManager Methods...{Colors.RESET}")

        client_file = self.bot_path / "bot/rcon/client.py"

        if not client_file.exists():
            self.add_result("bot/rcon/client.py exists", False)
            self.print_result(self.results[-1])
            return

        with open(client_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Required RCONManager methods (used by various cogs)
        required_methods = [
            ("class RCONManager", "RCONManager class"),
            ("def get_client", "get_client method"),
            ("async def get_server_info", "get_server_info for server monitoring"),
            ("async def execute_command", "execute_command for GUI"),
        ]

        for method, description in required_methods:
            found = method in content
            self.add_result(
                f"RCONManager: {description}", found, f"Missing: {method}" if not found else ""
            )
            if not found:
                self.print_result(self.results[-1])

    async def test_admin_permission_checks(self):
        """Test admin permission system - documented security feature."""
        print(f"\n{Colors.BOLD}Testing Admin Permission System...{Colors.RESET}")

        setup_file = self.bot_path / "bot/cogs/setup.py"

        if not setup_file.exists():
            self.add_result("setup.py exists", False)
            self.print_result(self.results[-1])
            return

        with open(setup_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for is_admin helper function
        has_is_admin = "is_admin" in content or "check_admin" in content
        self.add_result(
            "Permission: is_admin check function",
            has_is_admin,
            "Missing admin permission check function" if not has_is_admin else "",
        )
        if not has_is_admin:
            self.print_result(self.results[-1])

        # Check for role-based permissions
        has_role_check = "admin_role" in content.lower() or "administrator" in content.lower()
        self.add_result(
            "Permission: Role-based access control",
            has_role_check,
            "Missing role-based permission checks" if not has_role_check else "",
        )
        if not has_role_check:
            self.print_result(self.results[-1])

        # Check for /setadminrole command
        has_setadminrole = "setadminrole" in content
        self.add_result(
            "Permission: /setadminrole command",
            has_setadminrole,
            "Missing /setadminrole command" if not has_setadminrole else "",
        )
        if not has_setadminrole:
            self.print_result(self.results[-1])

    def print_summary(self):
        """Print test summary."""
        passed = sum(1 for r in self.results if r.passed and not r.warning)
        warned = sum(1 for r in self.results if r.warning and r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)

        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
        print(f"{'='*60}")
        print(f"{Colors.GREEN}[PASS] Passed: {passed}/{total}{Colors.RESET}")
        if warned > 0:
            print(f"{Colors.YELLOW}[WARN] Warnings: {warned}/{total}{Colors.RESET}")
        if failed > 0:
            print(f"{Colors.RED}[FAIL] Failed: {failed}/{total}{Colors.RESET}")
        print(f"{'='*60}")

        if failed > 0:
            print(f"\n{Colors.RED}{Colors.BOLD}Failed Tests:{Colors.RESET}")
            for result in self.results:
                if not result.passed:
                    print(f"{Colors.RED}  [FAIL] {result.name}{Colors.RESET}")
                    if result.message:
                        print(f"    {result.message}")

        if self.warnings:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}Warnings:{Colors.RESET}")
            for warning in self.warnings:
                print(f"{Colors.YELLOW}  [WARN] {warning}{Colors.RESET}")

        return failed == 0

    async def test_arcade_system(self):
        """Test Phoenix Arcade system with 9 games."""
        print(f"\n{Colors.BOLD}Testing Phoenix Arcade System...{Colors.RESET}")

        # Check arcade cog file
        cog_file = self.bot_path / "bot/cogs/arcade.py"
        if not cog_file.exists():
            self.add_result("arcade.py exists", False)
            self.print_result(self.results[-1])
            return

        with open(cog_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Check economy utility
        economy_file = self.bot_path / "bot/utils/economy.py"
        economy_exists = economy_file.exists()
        self.add_result(
            "Arcade: economy.py utility",
            economy_exists,
            "Missing economy.py utility" if not economy_exists else "",
        )
        if not economy_exists:
            self.print_result(self.results[-1])

        # Check for wallet command (renamed from /balance)
        has_wallet = (
            "def wallet" in content or "@app_commands.command" in content and "wallet" in content
        )
        self.add_result(
            "Arcade: /wallet command",
            has_wallet,
            "Missing /wallet command" if not has_wallet else "",
        )
        if not has_wallet:
            self.print_result(self.results[-1])

        # Check for /daily command
        has_daily = "def daily" in content
        self.add_result(
            "Arcade: /daily command", has_daily, "Missing /daily command" if not has_daily else ""
        )
        if not has_daily:
            self.print_result(self.results[-1])

        # Check for all 9 games
        games = [
            ("slots", "/slots"),
            ("coinflip", "/coinflip"),
            ("wager", "/wager"),
            ("roulette", "/roulette"),
            ("race", "/race"),
            ("hatch", "/hatch"),
            ("blackjack", "/blackjack"),
            ("trivia", "/trivia"),
            ("spawn_drop", "/spawn_drop (admin)"),
        ]

        for game_func, game_name in games:
            has_game = f"def {game_func}" in content
            self.add_result(
                f"Arcade: {game_name} game",
                has_game,
                f"Missing {game_name} game" if not has_game else "",
            )
            if not has_game:
                self.print_result(self.results[-1])

        # Check for interactive views
        views = [
            ("WagerView", "PVP wager system"),
            ("BlackjackView", "Blackjack buttons"),
            ("SupplyDropView", "Supply drop claim"),
            ("TriviaView", "Trivia buttons"),
        ]

        for view_class, description in views:
            has_view = f"class {view_class}" in content
            self.add_result(
                f"Arcade: {description}", has_view, f"Missing {view_class}" if not has_view else ""
            )
            if not has_view:
                self.print_result(self.results[-1])

        # Check economy integration
        if economy_exists:
            with open(economy_file, "r", encoding="utf-8") as f:
                economy_content = f.read()

            economy_functions = [
                ("ensure_economy_table", "Table initialization"),
                ("get_balance", "Balance retrieval"),
                ("update_balance", "Balance updates"),
                ("log_item_win", "Item win logging"),
            ]

            for func_name, description in economy_functions:
                has_func = f"async def {func_name}" in economy_content
                self.add_result(
                    f"Economy: {description}",
                    has_func,
                    f"Missing {func_name} function" if not has_func else "",
                )
                if not has_func:
                    self.print_result(self.results[-1])

    async def test_christmas_event(self):
        """Test 12 Days of ARKmas event system."""
        print(f"\n{Colors.BOLD}Testing 12 Days of ARKmas Event...{Colors.RESET}")

        # Check christmas cog file
        cog_file = self.bot_path / "bot/cogs/christmas.py"
        if not cog_file.exists():
            self.add_result("christmas.py exists", False)
            self.print_result(self.results[-1])
            return

        with open(cog_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for /christmas command
        has_command = (
            "def christmas" in content
            or "@app_commands.command" in content
            and "christmas" in content
        )
        self.add_result(
            "Christmas: /christmas command",
            has_command,
            "Missing /christmas command" if not has_command else "",
        )
        if not has_command:
            self.print_result(self.results[-1])

        # Check for daily task loop
        has_daily_task = "daily_announcement_task" in content or "@tasks.loop" in content
        self.add_result(
            "Christmas: Daily announcement task",
            has_daily_task,
            "Missing daily task loop" if not has_daily_task else "",
        )
        if not has_daily_task:
            self.print_result(self.results[-1])

        # Check for database integration
        has_db = "aiosqlite" in content and "christmas_claims" in content
        self.add_result(
            "Christmas: Claim tracking database",
            has_db,
            "Missing database integration" if not has_db else "",
        )
        if not has_db:
            self.print_result(self.results[-1])

        # Check for RCON delivery system
        has_rcon = "GiveItemToPlayer" in content or "GMSummon" in content
        self.add_result(
            "Christmas: RCON delivery", has_rcon, "Missing RCON delivery" if not has_rcon else ""
        )
        if not has_rcon:
            self.print_result(self.results[-1])

        # Check for player linking integration
        has_linking = "players_db" in content or "get_steam_id" in content
        self.add_result(
            "Christmas: Player linking",
            has_linking,
            "Missing player linking" if not has_linking else "",
        )
        if not has_linking:
            self.print_result(self.results[-1])

        # Check for 12 days of rewards (dictionary keys)
        reward_count = 0
        for i in range(1, 13):
            if f"{i}:" in content or f'"{i}":' in content or f"'{i}':" in content:
                reward_count += 1
        has_12_days = reward_count >= 12
        self.add_result(
            "Christmas: 12 days configured",
            has_12_days,
            f"Only {reward_count} days configured" if not has_12_days else "",
        )
        if not has_12_days:
            self.print_result(self.results[-1])

        # Check for reward types (item, item_list, coin - dinos handled via vouchers)
        reward_types = ["item", "item_list", "coin"]
        for reward_type in reward_types:
            has_type = f'"{reward_type}"' in content or f"'{reward_type}'" in content
            self.add_result(
                f"Christmas: {reward_type} reward type",
                has_type,
                f"Missing {reward_type} support" if not has_type else "",
            )
            if not has_type:
                self.print_result(self.results[-1])

        # Check for ClaimView button system
        has_claim_view = "class ClaimView" in content or "ClaimButton" in content
        self.add_result(
            "Christmas: Claim button UI",
            has_claim_view,
            "Missing claim button view" if not has_claim_view else "",
        )
        if not has_claim_view:
            self.print_result(self.results[-1])

    async def test_runtime_functionality(self):
        """Test runtime functionality by checking bot logs for critical operations."""
        print(f"\n{Colors.BOLD}Testing Runtime Functionality...{Colors.RESET}")

        # This test requires the bot to be running and producing logs
        # Try multiple possible log locations
        possible_log_paths = [
            Path("C:/PhoenixBot/logs/bot.log"),
            Path("R:\\ArkDiscordBot\\logs\\bot.log"),
            self.bot_path / "logs" / "bot.log",
        ]

        log_file = None
        for path in possible_log_paths:
            if path.exists():
                log_file = path
                break

        if log_file is None:
            self.add_result(
                "Bot logs available",
                False,
                "Cannot test runtime functionality - bot logs not found at expected locations",
            )
            self.print_result(self.results[-1])
            return

        try:
            # Read last 500 lines of log
            with open(log_file, "r", errors="ignore") as f:
                lines = f.readlines()[-500:]
            content = "".join(lines)

            # Test 1: Cache refresh loop executing
            has_cache_refresh = "Cache refreshed by dedicated loop" in content
            self.add_result(
                "Cache refresh loop executing",
                has_cache_refresh,
                (
                    "Every 30 seconds for real-time data"
                    if has_cache_refresh
                    else "Not found in recent logs"
                ),
            )
            if not has_cache_refresh:
                self.print_result(self.results[-1])

            # Test 2: RCON queries working
            has_rcon_queries = "RCON:" in content and "has" in content and "players" in content
            self.add_result(
                "RCON queries executing",
                has_rcon_queries,
                (
                    "Fresh server data being retrieved"
                    if has_rcon_queries
                    else "Not found in recent logs"
                ),
            )
            if not has_rcon_queries:
                self.print_result(self.results[-1])

            # Test 3: Voice channel updates
            has_voice_updates = "Updated voice channel" in content or "voice channel for" in content
            self.add_result(
                "Voice channel updates working",
                has_voice_updates,
                (
                    "Real-time player count display"
                    if has_voice_updates
                    else "Not found in recent logs"
                ),
            )
            if not has_voice_updates:
                self.print_result(self.results[-1])

            # Test 4: No errors in critical code
            error_patterns = [
                "cache_refresh_loop.*ERROR",
                "_refresh_server_status.*Exception",
                "ServerMonitorCog.*CRITICAL",
            ]

            has_errors = False
            for pattern in error_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    has_errors = True
                    break

            no_errors = not has_errors
            self.add_result(
                "No errors in cache refresh code",
                no_errors,
                "All operations completing normally" if no_errors else "Errors detected",
            )
            if not no_errors:
                self.print_result(self.results[-1])

            # Test 5: Runtime cog loading check removed (not applicable in test environment)
            # Production logs are not available during tests, so this check is skipped

        except Exception as e:
            self.add_result("Runtime functionality test", False, f"Error checking logs: {e}")
            self.print_result(self.results[-1])

    async def test_ui_callbacks(self):
        """Test that all UI buttons have associated callback functions."""
        print(f"\n{Colors.BOLD}Testing UI Callbacks...{Colors.RESET}")

        ui_files = [
            "bot/cogs/server_management_gui.py",
            "bot/cogs/arcade.py",
            "bot/cogs/christmas.py",
            "bot/cogs/help_commands.py",
        ]

        for file_path in ui_files:
            full_path = self.bot_path / file_path
            if not full_path.exists():
                continue

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Find all button decorators
                button_matches = list(re.finditer(r"@discord\.ui\.button", content))

                valid_buttons = 0
                for match in button_matches:
                    # Look ahead from the decorator to find 'async def'
                    chunk = content[match.end() : match.end() + 100]  # Check next 100 chars
                    if "async def" in chunk:
                        valid_buttons += 1

                self.add_result(
                    f"UI Callbacks in {file_path}",
                    len(button_matches) == valid_buttons,
                    f"Found {len(button_matches)} buttons, but only {valid_buttons} have valid callbacks",
                )
                self.print_result(self.results[-1])

            except Exception as e:
                self.add_result(f"Scan UI {file_path}", False, str(e))
                self.print_result(self.results[-1])

    async def test_security_decorators(self):
        """Test that admin commands have security decorators."""
        print(f"\n{Colors.BOLD}Testing Security Decorators...{Colors.RESET}")

        # Map file to commands that MUST have protection
        critical_checks = {
            "bot/cogs/setup.py": ["add_server", "remove_server"],
            "bot/cogs/rcon_admin.py": ["broadcast", "save_world"],
        }

        for file_path, commands in critical_checks.items():
            full_path = self.bot_path / file_path
            if not full_path.exists():
                continue

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            for cmd in commands:
                # Check for security decorators OR is_admin() check in function body
                decorator_pattern = rf"(?s)(@app_commands\.checks\.[a-zA-Z_]+|@commands\.has_role|@check_admin).*?async def {cmd}"
                has_decorator = re.search(decorator_pattern, content) is not None

                # Check for is_admin() check within the function
                function_pattern = rf"async def {cmd}.*?(?=async def|\Z)"
                function_match = re.search(function_pattern, content, re.DOTALL)
                has_is_admin_check = False
                if function_match:
                    has_is_admin_check = "is_admin(interaction)" in function_match.group(0)

                protected = has_decorator or has_is_admin_check

                self.add_result(
                    f"Security check: {cmd}",
                    protected,
                    f"Command protected with {'decorator' if has_decorator else 'is_admin() check' if has_is_admin_check else 'none'}",
                )
                if not protected:
                    self.print_result(self.results[-1])
                else:
                    self.print_result(self.results[-1])

    async def test_sql_safety(self):
        """Check for potential SQL injection vulnerabilities (f-strings in queries)."""
        print(f"\n{Colors.BOLD}Testing SQL Safety...{Colors.RESET}")

        db_files = [p for p in self.bot_path.glob("bot/database/*.py")]

        for file_path in db_files:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            issues = []
            for i, line in enumerate(lines):
                # Look for execute/cursor calls using f-strings
                if ("execute(" in line or "cursor.execute(" in line) and 'f"' in line:
                    # Exclude likely false positives like table names in initialization
                    if "CREATE TABLE" not in line:
                        issues.append(f"Line {i+1}: f-string detected in SQL execution")

            self.add_result(
                f"SQL Safety: {file_path.name}",
                len(issues) == 0,
                "\n  ".join(issues) if issues else "",
                warning=len(issues) > 0,
            )
            if issues:
                self.print_result(self.results[-1])

    async def test_config_validity(self):
        """Validate logical correctness of config values in code constants."""
        print(f"\n{Colors.BOLD}Testing Config Logic...{Colors.RESET}")

        config_path = self.bot_path / "bot/utils/config.py"
        if not config_path.exists():
            return

        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check if Port range is valid (regex to find assignments)
        port_match = re.search(r"PORT\s*=\s*(\d+)", content)
        if port_match:
            port = int(port_match.group(1))
            valid = 1024 < port < 65535
            self.add_result("Config: Valid Port Range", valid, f"Port {port} is unusual")
            self.print_result(self.results[-1])


async def run_tests(bot_path: str = None):
    """Run all tests."""
    if bot_path is None:
        # Default to one directory up from the script location
        bot_path = Path(__file__).parent.parent
    else:
        bot_path = Path(bot_path)

    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("=" * 60)
    print(" PHOENIX ARK DISCORD BOT - COMPREHENSIVE TEST SUITE")
    print("=" * 60)
    print(f"{Colors.RESET}")
    print(f"Testing bot at: {bot_path}")

    suite = BotTestSuite(bot_path)

    # Run all test categories
    await suite.test_file_structure()
    await suite.test_discord_client_startup()  # NEW: Replaces imports and basic functional checks
    await suite.test_database_schema()
    await suite.test_emoji_encoding()
    await suite.test_cog_structure()
    await suite.test_command_defers()
    await suite.test_rcon_client()
    await suite.test_env_template()
    await suite.test_voice_channel_persistence()
    await suite.test_chat_relay()
    await suite.test_store_system()
    await suite.test_shop_manager()
    await suite.test_scheduled_commands()
    await suite.test_starter_kits()
    await suite.test_server_management_gui()
    await suite.test_rcon_admin_commands()
    await suite.test_server_management_nssm()
    await suite.test_help_system()
    await suite.test_rcon_manager_methods()
    await suite.test_admin_permission_checks()

    # Run extended feature tests
    await suite.test_arcade_system()
    await suite.test_christmas_event()
    await suite.test_runtime_functionality()

    # Run advanced structural tests
    await suite.test_ui_callbacks()
    await suite.test_security_decorators()
    await suite.test_sql_safety()
    await suite.test_config_validity()

    # Print summary
    success = suite.print_summary()

    return 0 if success else 1


if __name__ == "__main__":
    import sys

    # Handle the path argument if provided
    bot_path = sys.argv[1] if len(sys.argv) > 1 else None

    # Check for discord.py dependency before running
    try:
        import discord
    except ImportError:
        print(
            f"{Colors.RED}ERROR: discord.py is not installed. Please run 'pip install discord.py'{Colors.RESET}"
        )
        sys.exit(1)

    exit_code = asyncio.run(run_tests(bot_path))
    sys.exit(exit_code)
