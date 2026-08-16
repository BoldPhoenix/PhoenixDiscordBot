"""
Kit database functions.
Handles kits, kit_items, and kit_claims tables for starter kit system.
"""

import aiosqlite
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from bot.utils.config import Config

logger = logging.getLogger("KitDB")


def _db_path() -> Path:
    return Path(Config.DATABASE_PATH)


# ---------------------------------------------------------------------------
# Table Initialization
# ---------------------------------------------------------------------------

async def init_kit_tables():
    """Create kit tables if they don't exist."""
    async with aiosqlite.connect(_db_path()) as db:
        # Enable foreign key constraints (required for CASCADE)
        await db.execute("PRAGMA foreign_keys = ON")
        # Kits table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kits (
                kit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                kit_name TEXT NOT NULL,
                description TEXT,
                enabled INTEGER DEFAULT 1,
                cooldown_hours INTEGER DEFAULT 0,
                min_level INTEGER DEFAULT 0,
                min_playtime_hours INTEGER DEFAULT 0,
                required_role_id INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(guild_id, kit_name)
            )
        """)
        
        # Kit items table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kit_items (
                kit_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                kit_id INTEGER NOT NULL,
                item_blueprint TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                quality INTEGER DEFAULT 1,
                notes TEXT,
                FOREIGN KEY (kit_id) REFERENCES kits(kit_id) ON DELETE CASCADE
            )
        """)
        
        # Kit claims table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kit_claims (
                claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                kit_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                claimed_at TEXT NOT NULL,
                next_claim_at TEXT,
                FOREIGN KEY (kit_id) REFERENCES kits(kit_id) ON DELETE CASCADE
            )
        """)
        
        # Indexes for performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_kits_guild ON kits(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_kit_items_kit ON kit_items(kit_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_kit_claims_guild_user ON kit_claims(guild_id, user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_kit_claims_kit ON kit_claims(kit_id)")
        
        await db.commit()
        logger.info("Kit tables initialized")


# ---------------------------------------------------------------------------
# Kit CRUD Operations
# ---------------------------------------------------------------------------

async def create_kit(
    guild_id: int,
    kit_name: str,
    description: str = "",
    enabled: int = 1,
    cooldown_hours: int = 0,
    min_level: int = 0,
    min_playtime_hours: int = 0,
    required_role_id: Optional[int] = None
) -> int:
    """Create a new kit. Returns kit_id."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute("""
            INSERT INTO kits (
                guild_id, kit_name, description, enabled, cooldown_hours,
                min_level, min_playtime_hours, required_role_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            guild_id, kit_name, description, enabled, cooldown_hours,
            min_level, min_playtime_hours, required_role_id,
            datetime.now(timezone.utc).isoformat()
        ))
        await db.commit()
        kit_id = cursor.lastrowid
        logger.info("Created kit '%s' (ID: %s) for guild %s", kit_name, kit_id, guild_id)
        return kit_id


async def create_kit_with_items(
    guild_id: int,
    kit_name: str,
    items: List[Dict[str, Any]],
    description: str = "",
    enabled: int = 1,
    cooldown_hours: int = 0,
    min_level: int = 0,
    min_playtime_hours: int = 0,
    required_role_id: Optional[int] = None,
) -> int:
    """Create a kit and its items atomically within a single transaction.

    If inserting any item fails, the entire operation (including the kit row)
    is rolled back so there are no orphaned kit records.

    Args:
        items: list of dicts with keys: item_blueprint, quantity, quality, notes

    Returns:
        kit_id on success.

    Raises:
        Exception on failure (transaction is rolled back).
    """
    async with aiosqlite.connect(_db_path()) as db:
        # aiosqlite defaults to autocommit=off, so all statements within this
        # connection share an implicit transaction until we call db.commit().
        try:
            cursor = await db.execute("""
                INSERT INTO kits (
                    guild_id, kit_name, description, enabled, cooldown_hours,
                    min_level, min_playtime_hours, required_role_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                guild_id, kit_name, description, enabled, cooldown_hours,
                min_level, min_playtime_hours, required_role_id,
                datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            ))
            kit_id = cursor.lastrowid

            for item in items:
                await db.execute("""
                    INSERT INTO kit_items (kit_id, item_blueprint, quantity, quality, notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    kit_id,
                    item["item_blueprint"],
                    item.get("quantity", 1),
                    item.get("quality", 1),
                    item.get("notes", ""),
                ))

            await db.commit()
            logger.info(
                "Created kit '%s' (ID: %s) with %s items for guild %s",
                kit_name, kit_id, len(items), guild_id,
            )
            return kit_id
        except Exception:
            await db.rollback()
            raise


async def get_kit(guild_id: int, kit_name: str) -> Optional[Dict[str, Any]]:
    """Get a kit by name."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM kits WHERE guild_id = ? AND kit_name = ?",
            (guild_id, kit_name)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_kit_by_id(kit_id: int) -> Optional[Dict[str, Any]]:
    """Get a kit by ID."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM kits WHERE kit_id = ?", (kit_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_kits(guild_id: int, enabled_only: bool = False) -> List[Dict[str, Any]]:
    """Get all kits for a guild."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        if enabled_only:
            cursor = await db.execute(
                "SELECT * FROM kits WHERE guild_id = ? AND enabled = 1 ORDER BY kit_name",
                (guild_id,)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM kits WHERE guild_id = ? ORDER BY kit_name",
                (guild_id,)
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_kit(
    kit_id: int,
    kit_name: Optional[str] = None,
    description: Optional[str] = None,
    enabled: Optional[int] = None,
    cooldown_hours: Optional[int] = None,
    min_level: Optional[int] = None,
    min_playtime_hours: Optional[int] = None,
    required_role_id: Optional[int] = None
) -> bool:
    """Update kit properties. Returns True if updated."""
    updates = []
    params = []
    
    if kit_name is not None:
        updates.append("kit_name = ?")
        params.append(kit_name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if enabled is not None:
        updates.append("enabled = ?")
        params.append(enabled)
    if cooldown_hours is not None:
        updates.append("cooldown_hours = ?")
        params.append(cooldown_hours)
    if min_level is not None:
        updates.append("min_level = ?")
        params.append(min_level)
    if min_playtime_hours is not None:
        updates.append("min_playtime_hours = ?")
        params.append(min_playtime_hours)
    if required_role_id is not None:
        updates.append("required_role_id = ?")
        params.append(required_role_id)
    
    if not updates:
        return False
    
    params.append(kit_id)
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            f"UPDATE kits SET {', '.join(updates)} WHERE kit_id = ?",
            params
        )
        await db.commit()
        logger.info("Updated kit ID %s", kit_id)
        return True


async def delete_kit(kit_id: int) -> bool:
    """Delete a kit and all associated items/claims. Returns True if deleted."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cursor = await db.execute("DELETE FROM kits WHERE kit_id = ?", (kit_id,))
        await db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted kit ID %s", kit_id)
        return deleted


async def count_kits(guild_id: int) -> int:
    """Count total kits for a guild."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM kits WHERE guild_id = ?",
            (guild_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


# ---------------------------------------------------------------------------
# Kit Items Operations
# ---------------------------------------------------------------------------

async def add_kit_item(
    kit_id: int,
    item_blueprint: str,
    quantity: int = 1,
    quality: int = 1,
    notes: str = ""
) -> int:
    """Add an item to a kit. Returns kit_item_id."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute("""
            INSERT INTO kit_items (kit_id, item_blueprint, quantity, quality, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (kit_id, item_blueprint, quantity, quality, notes))
        await db.commit()
        kit_item_id = cursor.lastrowid
        logger.info("Added item to kit %s: %s x%s Q%s", kit_id, item_blueprint, quantity, quality)
        return kit_item_id


async def get_kit_items(kit_id: int) -> List[Dict[str, Any]]:
    """Get all items for a kit."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM kit_items WHERE kit_id = ? ORDER BY kit_item_id",
            (kit_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def update_kit_item(
    kit_item_id: int,
    quantity: Optional[int] = None,
    quality: Optional[int] = None,
    notes: Optional[str] = None
) -> bool:
    """Update a kit item. Returns True if updated."""
    updates = []
    params = []
    
    if quantity is not None:
        updates.append("quantity = ?")
        params.append(quantity)
    if quality is not None:
        updates.append("quality = ?")
        params.append(quality)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    
    if not updates:
        return False
    
    params.append(kit_item_id)
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            f"UPDATE kit_items SET {', '.join(updates)} WHERE kit_item_id = ?",
            params
        )
        await db.commit()
        logger.info("Updated kit item ID %s", kit_item_id)
        return True


async def delete_kit_item(kit_item_id: int) -> bool:
    """Delete a kit item. Returns True if deleted."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute("DELETE FROM kit_items WHERE kit_item_id = ?", (kit_item_id,))
        await db.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted kit item ID %s", kit_item_id)
        return deleted


async def delete_all_kit_items(kit_id: int) -> int:
    """Delete all items from a kit. Returns count deleted."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute("DELETE FROM kit_items WHERE kit_id = ?", (kit_id,))
        await db.commit()
        count = cursor.rowcount
        logger.info("Deleted %s items from kit %s", count, kit_id)
        return count


# ---------------------------------------------------------------------------
# Kit Claims Operations
# ---------------------------------------------------------------------------

async def record_claim(
    guild_id: int,
    kit_id: int,
    user_id: int,
    cooldown_hours: int
) -> int:
    """Record a kit claim. Returns claim_id."""
    claimed_at = datetime.now(timezone.utc)
    next_claim_at = None
    if cooldown_hours > 0:
        next_claim_at = (claimed_at + timedelta(hours=cooldown_hours)).isoformat()
    
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute("""
            INSERT INTO kit_claims (guild_id, kit_id, user_id, claimed_at, next_claim_at)
            VALUES (?, ?, ?, ?, ?)
        """, (guild_id, kit_id, user_id, claimed_at.isoformat(), next_claim_at))
        await db.commit()
        claim_id = cursor.lastrowid
        logger.info("Recorded claim for kit %s by user %s", kit_id, user_id)
        return claim_id


async def get_last_claim(guild_id: int, kit_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Get the most recent claim for a user/kit combination."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM kit_claims
            WHERE guild_id = ? AND kit_id = ? AND user_id = ?
            ORDER BY claimed_at DESC
            LIMIT 1
        """, (guild_id, kit_id, user_id))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def can_claim_kit(guild_id: int, kit_id: int, user_id: int) -> tuple[bool, Optional[str]]:
    """
    Check if a user can claim a kit based on cooldown.
    Returns (can_claim, next_claim_time_iso).
    """
    last_claim = await get_last_claim(guild_id, kit_id, user_id)
    if not last_claim:
        return True, None
    
    next_claim_at = last_claim.get("next_claim_at")
    if not next_claim_at:
        # One-time kit already claimed
        return False, None
    
    # Check if cooldown has expired
    next_claim_time = datetime.fromisoformat(next_claim_at)
    if datetime.now(timezone.utc) >= next_claim_time:
        return True, None
    
    return False, next_claim_at


async def get_claim_count(kit_id: int) -> int:
    """Get total number of claims for a kit."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM kit_claims WHERE kit_id = ?",
            (kit_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def get_user_claims(guild_id: int, user_id: int) -> List[Dict[str, Any]]:
    """Get all claims for a user in a guild."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM kit_claims
            WHERE guild_id = ? AND user_id = ?
            ORDER BY claimed_at DESC
        """, (guild_id, user_id))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
