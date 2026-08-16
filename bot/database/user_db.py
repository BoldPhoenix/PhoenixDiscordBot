"""
Database queries and operations for users.
"""

import aiosqlite
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from bot.utils.config import Config

logger = logging.getLogger("UserDB")


async def get_user(discord_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
    """Get user by Discord ID and guild ID."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE discord_id = ? AND guild_id = ?", (discord_id, guild_id)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_or_update_user(discord_id: int, guild_id: int, username: str, steam_id: Optional[str] = None) -> None:
    """Create a new user or update existing user."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        if steam_id:
            await db.execute(
                """
                INSERT INTO users (discord_id, guild_id, username, steam_id, phoenix_coins)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(discord_id, guild_id) DO UPDATE SET
                    username = excluded.username,
                    steam_id = excluded.steam_id,
                    last_seen = CURRENT_TIMESTAMP
            """,
                (discord_id, guild_id, username, steam_id, Config.SHOP_STARTING_BALANCE),
            )
        else:
            await db.execute(
                """
                INSERT INTO users (discord_id, guild_id, username, phoenix_coins)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(discord_id, guild_id) DO UPDATE SET
                    username = excluded.username,
                    last_seen = CURRENT_TIMESTAMP
            """,
                (discord_id, guild_id, username, Config.SHOP_STARTING_BALANCE),
            )
        await db.commit()


async def get_balance(discord_id: int, guild_id: int) -> int:
    """DEPRECATED: Use players_db.get_balance() instead. Get user's Phoenix Coin balance."""
    user = await get_user(discord_id, guild_id)
    return user["phoenix_coins"] if user else 0


async def add_coins(
    discord_id: int, guild_id: int, amount: int, reason: str = "Admin grant", admin_id: Optional[int] = None
) -> int:
    """DEPRECATED: Use players_db.add_coins() instead. Add Phoenix Coins to a user's balance."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        # Ensure user exists (username is NOT NULL, so provide a default)
        await db.execute(
            """
            INSERT OR IGNORE INTO users (discord_id, guild_id, username, phoenix_coins)
            VALUES (?, ?, ?, 0)
            """,
            (discord_id, guild_id, f"User_{discord_id}"),
        )

        # Update user balance
        await db.execute(
            """
            UPDATE users SET phoenix_coins = phoenix_coins + ?
            WHERE discord_id = ? AND guild_id = ?
        """,
            (amount, discord_id, guild_id),
        )

        # Log transaction
        await db.execute(
            """
            INSERT INTO coin_transactions (guild_id, discord_id, amount, transaction_type, reason, admin_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (guild_id, discord_id, amount, "credit", reason, admin_id),
        )

        await db.commit()

        # Return new balance
        return await get_balance(discord_id, guild_id)


async def deduct_coins(discord_id: int, guild_id: int, amount: int, reason: str = "Purchase") -> bool:
    """DEPRECATED: Use players_db.deduct_coins() instead. Deduct Phoenix Coins from a user's balance. Returns True if successful."""
    db_path = Path(Config.DATABASE_PATH)

    current_balance = await get_balance(discord_id, guild_id)
    if current_balance < amount:
        return False

    async with aiosqlite.connect(db_path) as db:
        # Ensure user exists (username is NOT NULL, so provide a default)
        await db.execute(
            """
            INSERT OR IGNORE INTO users (discord_id, guild_id, username, phoenix_coins)
            VALUES (?, ?, ?, 0)
            """,
            (discord_id, guild_id, f"User_{discord_id}"),
        )
        # Deduct from balance
        await db.execute(
            """
            UPDATE users SET phoenix_coins = phoenix_coins - ?
            WHERE discord_id = ? AND guild_id = ?
        """,
            (amount, discord_id, guild_id),
        )

        # Log transaction
        await db.execute(
            """
            INSERT INTO coin_transactions (guild_id, discord_id, amount, transaction_type, reason)
            VALUES (?, ?, ?, ?, ?)
        """,
            (guild_id, discord_id, -amount, "debit", reason),
        )

        await db.commit()
        return True


async def get_coin_history(discord_id: int, guild_id: int, limit: int = 10) -> list:
    """DEPRECATED: Use players_db.get_coin_history() instead. Get coin transaction history for a user."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM coin_transactions
            WHERE discord_id = ? AND guild_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (discord_id, guild_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
