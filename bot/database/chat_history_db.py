"""
Database operations for chat history tracking.
Stores in-game chat messages for retrieval and moderation.
"""

import aiosqlite
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from bot.utils.config import Config

logger = logging.getLogger("ChatHistoryDB")


def _db_path() -> Path:
    return Path(Config.DATABASE_PATH)


async def init_chat_history_table():
    """Initialize the chat_history table."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL DEFAULT 0,
                server_name TEXT NOT NULL,
                player_name TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migrate: add guild_id to existing table if missing
        try:
            await db.execute("ALTER TABLE chat_history ADD COLUMN guild_id INTEGER NOT NULL DEFAULT 0")
        except Exception as e:
            err_msg = str(e).lower()
            if "duplicate column" not in err_msg and "already exists" not in err_msg:
                logger.warning("Unexpected migration error adding guild_id to chat_history: %s", e)

        # Create indexes for fast queries
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_server_timestamp
            ON chat_history(server_name, timestamp DESC)
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_history_guild ON chat_history(guild_id)"
        )

        await db.commit()
        logger.info("Chat history table initialized")


async def store_chat_message(guild_id: int, server_name: str, player_name: str, message: str):
    """Store a chat message in the database."""
    try:
        timestamp = int(datetime.now().timestamp())

        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                """
                INSERT INTO chat_history (guild_id, server_name, player_name, message, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, server_name, player_name, message, timestamp)
            )
            await db.commit()

    except Exception as e:
        logger.error(f"Error storing chat message: {e}")


async def get_chat_history(
    guild_id: int,
    server_name: str,
    limit: int = 100,
    hours: Optional[int] = None
) -> List[Dict]:
    """
    Get chat history for a server.

    Args:
        guild_id: Guild ID for multi-tenant isolation
        server_name: Name of the server
        limit: Maximum number of messages to return (default 100)
        hours: Only return messages from the last N hours (optional)

    Returns:
        List of chat message dictionaries
    """
    try:
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row

            if hours:
                cutoff_timestamp = int((datetime.now() - timedelta(hours=hours)).timestamp())
                query = """
                    SELECT guild_id, server_name, player_name, message, timestamp, created_at
                    FROM chat_history
                    WHERE guild_id = ? AND server_name = ? AND timestamp >= ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                cursor = await db.execute(query, (guild_id, server_name, cutoff_timestamp, limit))
            else:
                query = """
                    SELECT guild_id, server_name, player_name, message, timestamp, created_at
                    FROM chat_history
                    WHERE guild_id = ? AND server_name = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                cursor = await db.execute(query, (guild_id, server_name, limit))

            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Error getting chat history: {e}")
        return []


async def cleanup_old_messages(guild_id: int, days: int = 30) -> int:
    """
    Delete chat messages older than the specified number of days.

    Args:
        guild_id: Guild ID for multi-tenant isolation
        days: Delete messages older than this many days (default 30)

    Returns:
        Number of messages deleted
    """
    try:
        cutoff_timestamp = int((datetime.now() - timedelta(days=days)).timestamp())

        async with aiosqlite.connect(_db_path()) as db:
            cursor = await db.execute(
                "DELETE FROM chat_history WHERE guild_id = ? AND timestamp < ?",
                (guild_id, cutoff_timestamp)
            )
            await db.commit()
            deleted_count = cursor.rowcount

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} chat messages older than {days} days")

            return deleted_count

    except Exception as e:
        logger.error(f"Error cleaning up old messages: {e}")
        return 0


async def get_chat_stats(guild_id: int) -> Dict:
    """Get statistics about stored chat messages for a guild."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            # Total messages
            cursor = await db.execute(
                "SELECT COUNT(*) FROM chat_history WHERE guild_id = ?", (guild_id,)
            )
            total = (await cursor.fetchone())[0]

            # Messages per server
            cursor = await db.execute("""
                SELECT server_name, COUNT(*) as count
                FROM chat_history
                WHERE guild_id = ?
                GROUP BY server_name
                ORDER BY count DESC
            """, (guild_id,))
            per_server = await cursor.fetchall()

            # Oldest message
            cursor = await db.execute(
                "SELECT MIN(timestamp) FROM chat_history WHERE guild_id = ?", (guild_id,)
            )
            oldest_timestamp = (await cursor.fetchone())[0]

            return {
                "total_messages": total,
                "per_server": {row[0]: row[1] for row in per_server},
                "oldest_message_timestamp": oldest_timestamp
            }

    except Exception as e:
        logger.error(f"Error getting chat stats: {e}")
        return {"total_messages": 0, "per_server": {}, "oldest_message_timestamp": None}
