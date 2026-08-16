"""
Database queries and operations for store.
"""

import aiosqlite
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

from bot.utils.config import Config

logger = logging.getLogger("StoreDB")


async def get_all_items(
    category: Optional[str] = None, enabled_only: bool = True
) -> List[Dict[str, Any]]:
    """Get all store items, optionally filtered by category."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        if category:
            query = "SELECT * FROM store_items WHERE category = ?"
            params = (category,)
        else:
            query = "SELECT * FROM store_items"
            params = ()

        if enabled_only:
            query += " AND enabled = 1" if "WHERE" in query else " WHERE enabled = 1"

        query += " ORDER BY category, cost"

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_item(item_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific store item by ID."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM store_items WHERE item_id = ?", (item_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def add_item(
    name: str, description: str, cost: int, ark_command: str, category: str = "general"
) -> int:
    """Add a new item to the store."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO store_items (name, description, cost, ark_command, category)
            VALUES (?, ?, ?, ?, ?)
        """,
            (name, description, cost, ark_command, category),
        )
        await db.commit()
        return cursor.lastrowid


async def remove_item(item_id: int) -> bool:
    """Remove an item from the store."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("DELETE FROM store_items WHERE item_id = ?", (item_id,))
        await db.commit()
        return cursor.rowcount > 0


async def update_item_price(item_id: int, new_price: int) -> bool:
    """Update an item's price."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            UPDATE store_items SET cost = ?
            WHERE item_id = ?
        """,
            (new_price, item_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def record_purchase(
    discord_id: int, item_id: int, cost: int, server_name: str, status: str = "completed"
) -> int:
    """Record a purchase transaction."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO transactions (discord_id, item_id, cost, server_name, status)
            VALUES (?, ?, ?, ?, ?)
        """,
            (discord_id, item_id, cost, server_name, status),
        )
        await db.commit()
        return cursor.lastrowid


async def update_transaction_status(
    transaction_id: int, status: str, error_message: Optional[str] = None
) -> None:
    """Update the status of a transaction."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE transactions 
            SET status = ?, error_message = ?
            WHERE transaction_id = ?
        """,
            (status, error_message, transaction_id),
        )
        await db.commit()


async def get_user_purchases(discord_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get purchase history for a user."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT t.*, s.name as item_name
            FROM transactions t
            JOIN store_items s ON t.item_id = s.item_id
            WHERE t.discord_id = ?
            ORDER BY t.purchase_date DESC
            LIMIT ?
        """,
            (discord_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_categories() -> List[str]:
    """Get all unique categories."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            """
            SELECT DISTINCT category FROM store_items WHERE enabled = 1
            ORDER BY category
        """
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def count_items() -> int:
    """Count total number of items in the store."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT COUNT(*) FROM store_items") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_items_by_category() -> Dict[str, int]:
    """Get count of items per category."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            """
            SELECT category, COUNT(*) as count 
            FROM store_items 
            GROUP BY category 
            ORDER BY category
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}


async def clear_all_items() -> bool:
    """Delete all items from the store. WARNING: Cannot be undone."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM store_items")
        await db.commit()
        return True
