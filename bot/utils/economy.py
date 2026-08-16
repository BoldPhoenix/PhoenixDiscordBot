"""
bot/utils/economy.py
Handles database interactions for the Phoenix Arcade system.
"""

import aiosqlite
import logging
from datetime import datetime
from pathlib import Path

# Use the same database as the rest of the bot
DB_PATH = Path("bot_database.sqlite")

logger = logging.getLogger("Economy")


async def ensure_economy_table():
    """Creates the economy table and item log if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS arcade_economy (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                last_daily TEXT
            )
        """
        )
        # New table for keeping track of "Egg Hatchery" legendary wins
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS arcade_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_name TEXT,
                date_won TEXT
            )
        """
        )
        await db.commit()
        logger.info("Arcade economy tables initialized")


async def get_balance(user_id: int) -> int:
    """Returns the user's coin balance."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance FROM arcade_economy WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def update_balance(user_id: int, amount: int, is_win: bool = None) -> int:
    """
    Adds or removes coins. Returns the new balance.
    amount: Positive to add, Negative to remove.
    is_win: True to increment wins, False to increment losses, None for neither
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO arcade_economy (user_id, balance) VALUES (?, 0)", (user_id,)
        )
        await db.execute(
            "UPDATE arcade_economy SET balance = balance + ? WHERE user_id = ?", (amount, user_id)
        )

        if is_win is True:
            await db.execute(
                "UPDATE arcade_economy SET wins = wins + 1 WHERE user_id = ?", (user_id,)
            )
        elif is_win is False:
            await db.execute(
                "UPDATE arcade_economy SET losses = losses + 1 WHERE user_id = ?", (user_id,)
            )

        await db.commit()
        return await get_balance(user_id)


async def log_item_win(user_id: int, item_name: str):
    """Logs a special item win for admins to review."""
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now().isoformat()
        await db.execute(
            "INSERT INTO arcade_items (user_id, item_name, date_won) VALUES (?, ?, ?)",
            (user_id, item_name, now),
        )
        await db.commit()
        logger.info(f"Legendary item win logged: {item_name} by user {user_id}")


async def get_stats(user_id: int) -> dict:
    """Returns user's win/loss statistics."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT wins, losses, last_daily FROM arcade_economy WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"wins": row[0], "losses": row[1], "last_daily": row[2]}
            return {"wins": 0, "losses": 0, "last_daily": None}


async def can_claim_daily(user_id: int) -> bool:
    """Check if user can claim their daily reward."""
    stats = await get_stats(user_id)
    if not stats["last_daily"]:
        return True

    last_claim = datetime.fromisoformat(stats["last_daily"])
    now = datetime.now()
    return (now - last_claim).total_seconds() >= 86400  # 24 hours


async def update_daily_claim(user_id: int):
    """Update the last daily claim timestamp."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE arcade_economy SET last_daily = ? WHERE user_id = ?",
            (datetime.now().isoformat(), user_id),
        )
        await db.commit()
