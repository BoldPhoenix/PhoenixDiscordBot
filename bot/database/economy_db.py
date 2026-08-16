"""
Economy database functions.
Handles economy_settings, economy_roles, and payday_history tables.
"""

import aiosqlite
import logging
from pathlib import Path
from datetime import datetime

from bot.utils.config import Config

logger = logging.getLogger("EconomyDB")


def _db_path() -> Path:
    return Path(Config.DATABASE_PATH)


# ---------------------------------------------------------------------------
# Economy Settings
# ---------------------------------------------------------------------------

async def get_economy_settings(guild_id: int) -> dict:
    """Get economy settings for a guild, returning defaults if not configured."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM economy_settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        # Return defaults without creating a row yet
        return {
            "guild_id": guild_id,
            "base_payday_amount": 100,
            "currency_name": "Phoenix Coins",
            "currency_icon": "🪙",
            "economy_log_channel_id": None,
            "payday_enabled": 1,
            "payday_interval_hours": 24,
            "payday_eligibility_role_id": None,
            "payday_schedule_type": "daily",
            "payday_day_of_week": 0,
            "payday_time": "12:00",
            "payday_active_only": 0,
        }


async def update_economy_settings(guild_id: int, **kwargs) -> bool:
    """Create or update economy settings for a guild."""
    valid = {
        "base_payday_amount", "currency_name", "currency_icon",
        "economy_log_channel_id", "payday_enabled", "payday_interval_hours",
        "payday_eligibility_role_id", "payday_schedule_type",
        "payday_day_of_week", "payday_time", "payday_active_only",
    }
    updates = {k: v for k, v in kwargs.items() if k in valid}
    if not updates:
        return False
    try:
        async with aiosqlite.connect(_db_path()) as db:
            # Upsert
            await db.execute(
                "INSERT OR IGNORE INTO economy_settings (guild_id) VALUES (?)", (guild_id,)
            )
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            set_clause += ", updated_at = ?"
            values = list(updates.values()) + [datetime.now().isoformat(), guild_id]
            await db.execute(
                f"UPDATE economy_settings SET {set_clause} WHERE guild_id = ?", values
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"update_economy_settings error: {e}")
        return False


# ---------------------------------------------------------------------------
# Economy Roles (role-based payday bonuses)
# ---------------------------------------------------------------------------

async def get_economy_roles(guild_id: int) -> list:
    """Get all role bonus definitions for a guild."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM economy_roles WHERE guild_id = ? ORDER BY bonus_amount DESC",
                (guild_id,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_economy_roles error: {e}")
        return []


async def set_economy_role(guild_id: int, role_id: int, role_name: str, bonus_amount: int) -> bool:
    """Add or update a role bonus. Use bonus_amount=0 to effectively remove the bonus."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                """
                INSERT INTO economy_roles (guild_id, role_id, role_name, bonus_amount)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, role_id) DO UPDATE SET
                    role_name = excluded.role_name,
                    bonus_amount = excluded.bonus_amount
                """,
                (guild_id, str(role_id), role_name, bonus_amount),
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"set_economy_role error: {e}")
        return False


async def remove_economy_role(guild_id: int, role_id: int) -> bool:
    """Remove a role bonus definition."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                "DELETE FROM economy_roles WHERE guild_id = ? AND role_id = ?",
                (guild_id, str(role_id)),
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"remove_economy_role error: {e}")
        return False


# ---------------------------------------------------------------------------
# Payday History
# ---------------------------------------------------------------------------

async def record_payday(
    guild_id: int, discord_id: int, eos_id: str,
    base_amount: int, role_bonus: int, total_amount: int,
) -> bool:
    """Record a payday event."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                """
                INSERT INTO payday_history
                    (guild_id, discord_id, eos_id, base_amount, role_bonus, total_amount)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (guild_id, discord_id, eos_id, base_amount, role_bonus, total_amount),
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"record_payday error: {e}")
        return False


async def get_last_payday(guild_id: int, discord_id: int) -> dict | None:
    """Get the most recent payday record for a player."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM payday_history
                WHERE guild_id = ? AND discord_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (guild_id, discord_id),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_last_payday error: {e}")
        return None
