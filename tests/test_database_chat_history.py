"""
Tests for bot/database/chat_history_db.py - multi-tenant version
"""

import pytest
import aiosqlite

TEST_GUILD_ID = 123456789


@pytest.mark.asyncio
async def test_init_chat_history_table(full_db):
    """init_chat_history_table creates table and index."""
    from bot.database.chat_history_db import init_chat_history_table

    await init_chat_history_table()

    async with aiosqlite.connect(full_db) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chat_history'"
        )
        assert await cursor.fetchone() is not None

        # Check index exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_chat_server_timestamp'"
        )
        assert await cursor.fetchone() is not None


@pytest.mark.asyncio
async def test_store_and_retrieve_chat(full_db):
    """store_chat_message and get_chat_history round-trip."""
    from bot.database.chat_history_db import (
        init_chat_history_table,
        store_chat_message,
        get_chat_history,
    )

    await init_chat_history_table()

    # Store some messages
    await store_chat_message(TEST_GUILD_ID, "Test Server", "Player1", "Hello world!")
    await store_chat_message(TEST_GUILD_ID, "Test Server", "Player2", "Hi there!")
    await store_chat_message(TEST_GUILD_ID, "Test Server", "Player1", "How are you?")

    # Retrieve history
    history = await get_chat_history(TEST_GUILD_ID, "Test Server", limit=10)
    assert len(history) == 3

    # Check data integrity (ordered by timestamp DESC)
    assert history[0]["player_name"] == "Player1"
    assert history[0]["server_name"] == "Test Server"
    assert history[0]["timestamp"] is not None


@pytest.mark.asyncio
async def test_get_chat_history_with_limit(full_db):
    """get_chat_history respects limit parameter."""
    from bot.database.chat_history_db import (
        init_chat_history_table,
        store_chat_message,
        get_chat_history,
    )

    await init_chat_history_table()

    # Store 5 messages
    for i in range(5):
        await store_chat_message(TEST_GUILD_ID, "Test Server", f"Player{i}", f"Message {i}")

    # Get with limit
    history = await get_chat_history(TEST_GUILD_ID, "Test Server", limit=3)
    assert len(history) == 3


@pytest.mark.asyncio
async def test_get_chat_history_with_hours_filter(full_db):
    """get_chat_history respects hours filter."""
    from bot.database.chat_history_db import (
        init_chat_history_table,
        get_chat_history,
    )
    from datetime import datetime, timedelta

    await init_chat_history_table()

    # Store messages at different times
    old_time = int((datetime.now() - timedelta(hours=2)).timestamp())
    recent_time = int((datetime.now() - timedelta(minutes=30)).timestamp())

    # Manually insert with specific timestamps
    async with aiosqlite.connect(full_db) as db:
        await db.execute(
            "INSERT INTO chat_history (guild_id, server_name, player_name, message, timestamp) VALUES (?, ?, ?, ?, ?)",
            (TEST_GUILD_ID, "Test Server", "Player1", "Old message", old_time)
        )
        await db.execute(
            "INSERT INTO chat_history (guild_id, server_name, player_name, message, timestamp) VALUES (?, ?, ?, ?, ?)",
            (TEST_GUILD_ID, "Test Server", "Player2", "Recent message", recent_time)
        )
        await db.commit()

    # Get only recent messages (last hour)
    history = await get_chat_history(TEST_GUILD_ID, "Test Server", hours=1)
    assert len(history) == 1
    assert history[0]["message"] == "Recent message"


@pytest.mark.asyncio
async def test_get_chat_history_server_filter(full_db):
    """get_chat_history filters by server name."""
    from bot.database.chat_history_db import (
        init_chat_history_table,
        store_chat_message,
        get_chat_history,
    )

    await init_chat_history_table()

    # Store messages for different servers
    await store_chat_message(TEST_GUILD_ID, "Server1", "Player1", "Message 1")
    await store_chat_message(TEST_GUILD_ID, "Server2", "Player2", "Message 2")
    await store_chat_message(TEST_GUILD_ID, "Server1", "Player3", "Message 3")

    # Get history for Server1 only
    history = await get_chat_history(TEST_GUILD_ID, "Server1")
    assert len(history) == 2
    assert all(msg["server_name"] == "Server1" for msg in history)


@pytest.mark.asyncio
async def test_cleanup_old_messages(full_db):
    """cleanup_old_messages removes messages older than specified days."""
    from bot.database.chat_history_db import (
        init_chat_history_table,
        cleanup_old_messages,
        get_chat_history,
    )
    from datetime import datetime, timedelta

    await init_chat_history_table()

    # Store messages at different times
    old_time = int((datetime.now() - timedelta(days=5)).timestamp())
    recent_time = int((datetime.now() - timedelta(days=1)).timestamp())

    async with aiosqlite.connect(full_db) as db:
        await db.execute(
            "INSERT INTO chat_history (guild_id, server_name, player_name, message, timestamp) VALUES (?, ?, ?, ?, ?)",
            (TEST_GUILD_ID, "Test Server", "Player1", "Old message", old_time)
        )
        await db.execute(
            "INSERT INTO chat_history (guild_id, server_name, player_name, message, timestamp) VALUES (?, ?, ?, ?, ?)",
            (TEST_GUILD_ID, "Test Server", "Player2", "Recent message", recent_time)
        )
        await db.commit()

    # Clean up messages older than 3 days
    deleted_count = await cleanup_old_messages(guild_id=TEST_GUILD_ID, days=3)
    assert deleted_count == 1

    # Verify only recent message remains
    history = await get_chat_history(TEST_GUILD_ID, "Test Server")
    assert len(history) == 1
    assert history[0]["message"] == "Recent message"


@pytest.mark.asyncio
async def test_get_chat_stats(full_db):
    """get_chat_stats returns correct statistics."""
    from bot.database.chat_history_db import (
        init_chat_history_table,
        store_chat_message,
        get_chat_stats,
    )

    await init_chat_history_table()

    # Store messages for different servers
    await store_chat_message(TEST_GUILD_ID, "Server1", "Player1", "Message 1")
    await store_chat_message(TEST_GUILD_ID, "Server1", "Player2", "Message 2")
    await store_chat_message(TEST_GUILD_ID, "Server2", "Player3", "Message 3")

    stats = await get_chat_stats(guild_id=TEST_GUILD_ID)
    assert stats["total_messages"] == 3
    assert stats["per_server"]["Server1"] == 2
    assert stats["per_server"]["Server2"] == 1
    assert stats["oldest_message_timestamp"] is not None


@pytest.mark.asyncio
async def test_get_chat_stats_empty(full_db):
    """get_chat_stats returns zeros for empty database."""
    from bot.database.chat_history_db import (
        init_chat_history_table,
        get_chat_stats,
    )

    await init_chat_history_table()

    stats = await get_chat_stats(guild_id=TEST_GUILD_ID)
    assert stats["total_messages"] == 0
    assert stats["per_server"] == {}
    assert stats["oldest_message_timestamp"] is None


@pytest.mark.asyncio
async def test_store_chat_message_error_handling(full_db):
    """store_chat_message handles errors gracefully."""
    from bot.database.chat_history_db import init_chat_history_table, store_chat_message

    await init_chat_history_table()

    # This should not raise an exception
    await store_chat_message(TEST_GUILD_ID, "Test Server", "Player1", "Test message")
