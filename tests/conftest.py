"""
Shared test fixtures for Phoenix ARK Discord Bot tests - NO MOCKS VERSION.
"""

import asyncio
import os
import tempfile
import shutil
import pytest
import pytest_asyncio
import aiosqlite
from pathlib import Path

# Import RCON test server
from tests.rcon_test_server import RCONTestServer


# Ensure Config sees test environment
os.environ.setdefault("PYTEST_CURRENT_TEST", "1")
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token-not-real")

# Path to production database fixture
PROD_DB_FIXTURE = Path(__file__).parent / "fixtures" / "phoenix_bot_prod.db"


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def tmp_db_path(tmp_path):
    """Create a temporary database file path."""
    return str(tmp_path / "test_phoenix.db")


@pytest.fixture
def config_db_path(tmp_db_path):
    """Direct Config.DATABASE_PATH assignment without mocks."""
    from bot.utils.config import Config
    original_path = Config.DATABASE_PATH
    Config.DATABASE_PATH = tmp_db_path
    yield tmp_db_path
    Config.DATABASE_PATH = original_path


@pytest.fixture
def prod_db_copy(tmp_path):
    """Copy production database to a temp location for testing."""
    if not PROD_DB_FIXTURE.exists():
        pytest.skip("Production database fixture not found. Run: scp from pi-staging/data/phoenix_bot.db to tests/fixtures/phoenix_bot_prod.db")
    
    dest = tmp_path / "test_phoenix.db"
    shutil.copy(PROD_DB_FIXTURE, dest)
    return str(dest)


@pytest.fixture
def config_prod_db(prod_db_copy):
    """Config.DATABASE_PATH pointing to a copy of the production database."""
    from bot.utils.config import Config
    original_path = Config.DATABASE_PATH
    Config.DATABASE_PATH = prod_db_copy
    yield prod_db_copy
    Config.DATABASE_PATH = original_path


@pytest_asyncio.fixture
async def initialized_db(config_db_path):
    """Create a temporary database with all tables initialized.
    
    Uses direct Config assignment instead of patching.
    """
    from bot.database.init_db import initialize_database
    await initialize_database()
    yield config_db_path


@pytest_asyncio.fixture
async def server_config_db(config_db_path):
    """Initialized database with server_config tables ready."""
    from bot.database.server_config_db import init_server_config_tables
    await init_server_config_tables()
    yield config_db_path


@pytest_asyncio.fixture
async def players_db(config_db_path):
    """Initialized database with players tables ready."""
    from bot.database.players_db import init_players_tables
    from bot.database.server_config_db import init_server_config_tables
    from bot.database.init_db import initialize_database
    
    # Initialize core tables first (server_configs needed for subscription checks)
    await initialize_database()
    await init_server_config_tables()
    await init_players_tables()
    yield config_db_path


@pytest_asyncio.fixture
async def full_db(config_db_path):
    """Fully initialized database with ALL tables."""
    from bot.database.init_db import initialize_database
    from bot.database.server_config_db import init_server_config_tables
    from bot.database.players_db import init_players_tables
    from bot.database.chat_history_db import init_chat_history_table

    await initialize_database()
    await init_server_config_tables()
    await init_players_tables()
    await init_chat_history_table()
    yield config_db_path


@pytest_asyncio.fixture
async def prod_db(config_prod_db):
    """Production database copy for integration tests with real schema."""
    yield config_prod_db


@pytest_asyncio.fixture
async def rcon_test_server():
    """Real RCON test server for integration testing."""
    server = RCONTestServer()
    host, port = await server.start_server()
    
    try:
        yield server, host, port
    finally:
        await server.stop_server()


@pytest.fixture
def discord_bot_token():
    """Real Discord bot token from environment for integration tests."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token or token == "test-token-not-real":
        pytest.skip("Real Discord bot token not available")
    return token


@pytest.fixture
def discord_app_id():
    """Real Discord app ID from environment for integration tests."""
    app_id = os.getenv("DISCORD_APP_ID")
    if not app_id:
        pytest.skip("Discord app ID not available")
    return app_id


@pytest.fixture
def discord_guild_id():
    """Real Discord guild ID from environment for integration tests."""
    guild_id = os.getenv("DISCORD_GUILD_ID")
    if not guild_id:
        pytest.skip("Discord guild ID not available")
    return guild_id


@pytest_asyncio.fixture
async def discord_bot(discord_bot_token):
    """Real Discord bot instance for integration testing."""
    import discord
    from discord.ext import commands
    
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    
    bot = commands.Bot(command_prefix="!", intents=intents)
    
    # Minimal setup for testing
    async def on_ready():
        pass
    
    bot.add_listener(on_ready, 'on_ready')
    
    try:
        await bot.start(discord_bot_token)
        yield bot
    finally:
        await bot.close()
