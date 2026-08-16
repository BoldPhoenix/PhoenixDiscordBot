"""
Shop database functions.
Handles store_items, cart_items, shop_config, pending_deliveries, transactions.
"""

import aiosqlite
import logging
from pathlib import Path
from datetime import datetime

from bot.utils.config import Config

logger = logging.getLogger("ShopDB")

QUALITY_NAMES = {
    1: "Primitive",
    2: "Ramshackle",
    4: "Apprentice",
    6: "Journeyman",
    8: "Mastercraft",
    10: "Ascendant",
}
VALID_QUALITIES = [1, 2, 4, 6, 8, 10]


def _db_path() -> Path:
    return Path(Config.DATABASE_PATH)


# ---------------------------------------------------------------------------
# Shop Config
# ---------------------------------------------------------------------------

async def get_shop_config(guild_id: int) -> dict:
    """Get shop configuration, returning defaults if not configured."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM shop_config WHERE guild_id = ?", (guild_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return {
            "guild_id": guild_id,
            "shop_enabled": 1,
            "shop_channel_id": None,
            "log_channel_id": None,
            "items_per_page": 4,
            "require_linked_account": 1,
        }


async def update_shop_config(guild_id: int, **kwargs) -> bool:
    """Create or update shop configuration."""
    valid = {"shop_enabled", "shop_channel_id", "log_channel_id", "items_per_page", "require_linked_account"}
    updates = {k: v for k, v in kwargs.items() if k in valid}
    if not updates:
        return False
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                "INSERT OR IGNORE INTO shop_config (guild_id) VALUES (?)", (guild_id,)
            )
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            set_clause += ", updated_at = ?"
            values = list(updates.values()) + [datetime.now().isoformat(), guild_id]
            await db.execute(
                f"UPDATE shop_config SET {set_clause} WHERE guild_id = ?", values
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"update_shop_config error: {e}")
        return False


# ---------------------------------------------------------------------------
# Store Items
# ---------------------------------------------------------------------------

async def get_categories(guild_id: int) -> list:
    """Return distinct enabled categories with item counts."""
    async with aiosqlite.connect(_db_path()) as db:
        async with db.execute(
            """
            SELECT category, COUNT(*) as item_count
            FROM store_items
            WHERE guild_id = ? AND enabled = 1
            GROUP BY category
            ORDER BY category
            """,
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"category": row[0], "count": row[1]} for row in rows]


async def get_store_items(guild_id: int, category: str = None, enabled_only: bool = True) -> list:
    """Return store items, optionally filtered by category."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM store_items WHERE guild_id = ?"
        params = [guild_id]
        if enabled_only:
            query += " AND enabled = 1"
        if category:
            query += " AND LOWER(category) = LOWER(?)"
            params.append(category)
        query += " ORDER BY name"
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_store_item(item_id: int) -> dict | None:
    """Return a single store item by ID."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM store_items WHERE item_id = ?", (item_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_item_name_by_command(guild_id: int, ark_command: str) -> str | None:
    """Best-effort display name for a blueprint, so a delivery can be logged in human terms.

    `pending_deliveries` stores the raw `item_blueprint` and no name, so a log built straight from
    the queue row reads like
    `Blueprint'/CybersStructures/.../PrimalItemCraftable_OverseerAlphaPack_CS...'`
    which tells an admin nothing at a glance. Returns None if the item has since been renamed or
    removed from the shop — callers fall back to the blueprint, because the delivery still happened
    and must still be logged.
    """
    if not ark_command:
        return None
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT name FROM store_items WHERE guild_id = ? AND ark_command = ? LIMIT 1",
            (guild_id, ark_command),
        ) as cursor:
            row = await cursor.fetchone()
            return row["name"] if row else None


async def add_store_item(
    guild_id: int,
    name: str,
    description: str,
    cost: int,
    ark_command: str,
    category: str,
    supports_quality: bool = False,
    allow_blueprint_select: bool = False,
) -> int:
    """Add a new store item. Returns the new item_id."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            """
            INSERT INTO store_items
                (guild_id, name, description, cost, ark_command, category, enabled,
                 supports_quality, allow_blueprint_select)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                guild_id, name, description, cost, ark_command, category.lower(),
                1 if supports_quality else 0,
                1 if allow_blueprint_select else 0,
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def update_store_item(item_id: int, **kwargs) -> bool:
    """Update store item fields."""
    valid = {"name", "description", "cost", "ark_command", "category", "enabled",
             "supports_quality", "allow_blueprint_select"}
    updates = {k: v for k, v in kwargs.items() if k in valid}
    if not updates:
        return False
    try:
        async with aiosqlite.connect(_db_path()) as db:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [item_id]
            await db.execute(
                f"UPDATE store_items SET {set_clause} WHERE item_id = ?", values
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"update_store_item error: {e}")
        return False


async def delete_store_item(item_id: int) -> bool:
    """Delete a store item by ID."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute("DELETE FROM store_items WHERE item_id = ?", (item_id,))
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"delete_store_item error: {e}")
        return False


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------

async def add_to_cart(
    guild_id: int, discord_id: int, item_id: int, quantity: int, quality: int, blueprint: bool
) -> bool:
    """Add item to cart, combining qty if identical entry exists."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            cursor = await db.execute(
                """
                SELECT cart_id, quantity FROM cart_items
                WHERE guild_id = ? AND discord_id = ? AND item_id = ? AND quality = ? AND blueprint = ?
                """,
                (guild_id, discord_id, item_id, quality, 1 if blueprint else 0),
            )
            existing = await cursor.fetchone()
            if existing:
                await db.execute(
                    "UPDATE cart_items SET quantity = quantity + ? WHERE cart_id = ?",
                    (quantity, existing[0]),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO cart_items (guild_id, discord_id, item_id, quantity, quality, blueprint)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (guild_id, discord_id, item_id, quantity, quality, 1 if blueprint else 0),
                )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"add_to_cart error: {e}")
        return False


async def get_cart(guild_id: int, discord_id: int) -> list:
    """Return cart items joined with item details (includes ark_command)."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT c.cart_id, c.item_id, c.quantity, c.quality, c.blueprint,
                   s.name, s.cost, s.supports_quality, s.enabled, s.ark_command
            FROM cart_items c
            JOIN store_items s ON c.item_id = s.item_id
            WHERE c.guild_id = ? AND c.discord_id = ?
            ORDER BY c.added_at
            """,
            (guild_id, discord_id),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def remove_from_cart(cart_id: int) -> bool:
    """Remove a specific cart item by cart_id."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart_id,))
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"remove_from_cart error: {e}")
        return False


async def clear_cart(guild_id: int, discord_id: int) -> bool:
    """Clear all cart items for a user."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                "DELETE FROM cart_items WHERE guild_id = ? AND discord_id = ?",
                (guild_id, discord_id),
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"clear_cart error: {e}")
        return False


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

async def record_transaction(
    guild_id: int, discord_id: int, item_id: int, cost: int,
    quantity: int = 1, server_name: str = None, status: str = "pending",
) -> int:
    """Record a purchase transaction. Returns transaction_id."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            """
            INSERT INTO transactions (guild_id, discord_id, item_id, cost, server_name, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (guild_id, discord_id, item_id, cost, server_name, status),
        )
        await db.commit()
        return cursor.lastrowid


async def update_transaction_status(
    transaction_id: int, status: str, error_message: str = None
) -> bool:
    """Update transaction status and optional error message."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                "UPDATE transactions SET status = ?, error_message = ? WHERE transaction_id = ?",
                (status, error_message, transaction_id),
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"update_transaction_status error: {e}")
        return False


# ---------------------------------------------------------------------------
# Pending Deliveries
# ---------------------------------------------------------------------------

async def add_pending_delivery(
    guild_id: int,
    discord_user_id: int,
    eos_id: str,
    server_name: str,
    item_blueprint: str,
    quantity: int = 1,
    quality: int = 1,
    force_blueprint: bool = False,
) -> int:
    """Queue a pending delivery. Returns delivery_id."""
    from datetime import datetime
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            """
            INSERT INTO pending_deliveries
                (guild_id, discord_user_id, eos_id, server_name, item_blueprint,
                 quantity, quality, force_blueprint, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id, discord_user_id, eos_id, server_name, item_blueprint,
                quantity, quality, 1 if force_blueprint else 0,
                datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_pending_deliveries(guild_id: int = None) -> list:
    """Return pending deliveries, optionally filtered by guild."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        if guild_id:
            cursor = await db.execute(
                "SELECT * FROM pending_deliveries WHERE guild_id = ? ORDER BY created_at",
                (guild_id,),
            )
        else:
            cursor = await db.execute("SELECT * FROM pending_deliveries ORDER BY created_at")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def delete_pending_delivery(delivery_id: int) -> bool:
    """Delete a pending delivery record (marks as completed)."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute("DELETE FROM pending_deliveries WHERE id = ?", (delivery_id,))
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"delete_pending_delivery error: {e}")
        return False


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def search_store_items(guild_id: int, query: str, limit: int = 25) -> list:
    """Search enabled items by name (case-insensitive LIKE). Used for /buy autocomplete."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT item_id, name, cost, category, supports_quality, allow_blueprint_select, is_pack
               FROM store_items
               WHERE guild_id = ? AND enabled = 1 AND name LIKE ?
               ORDER BY name LIMIT ?""",
            (guild_id, f"%{query}%", limit),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


# ---------------------------------------------------------------------------
# Bulk Import / Export helpers
# ---------------------------------------------------------------------------

async def clear_all_store_items(guild_id: int) -> bool:
    """Delete all store items for a guild (used before a full replace import)."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute("DELETE FROM store_items WHERE guild_id = ?", (guild_id,))
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"clear_all_store_items error: {e}")
        return False


async def bulk_add_store_items(guild_id: int, items: list) -> tuple:
    """Insert multiple store items (regular items and packs) in a single transaction.

    Each item dict may contain:
      name, cost, ark_command, category, description, supports_quality,
      is_pack (bool), pack_contents (JSON string)

    Returns (inserted_count, errors).
    """
    inserted = 0
    errors = []
    try:
        async with aiosqlite.connect(_db_path()) as db:
            for item in items:
                try:
                    is_pack = 1 if item.get("is_pack") else 0
                    pack_contents = item.get("pack_contents")  # JSON str or None
                    ark_cmd = item.get("ark_command", "#PACK#" if is_pack else "")
                    enabled = 1 if item.get("enabled", True) else 0
                    await db.execute(
                        """
                        INSERT INTO store_items
                            (guild_id, name, description, cost, ark_command, category,
                             enabled, supports_quality, allow_blueprint_select, is_pack, pack_contents)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            guild_id,
                            item["name"],
                            item.get("description", ""),
                            item["cost"],
                            ark_cmd,
                            item["category"].lower(),
                            enabled,
                            1 if item.get("supports_quality") else 0,
                            1 if item.get("allow_blueprint_select") else 0,
                            is_pack,
                            pack_contents,
                        ),
                    )
                    inserted += 1
                except Exception as e:
                    errors.append(f"'{item['name']}': {e}")
            await db.commit()
    except Exception as e:
        logger.error(f"bulk_add_store_items error: {e}")
        errors.append(f"Database error: {e}")
    return inserted, errors
