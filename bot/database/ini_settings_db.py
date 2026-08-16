"""
INI settings database operations.
Manages server INI settings cache and pending changes queue.
"""

import aiosqlite
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from bot.utils.config import Config

logger = logging.getLogger("IniSettingsDB")


def _db_path() -> str:
    return Config.DATABASE_PATH


# ==================== Server INI Settings ====================

async def import_ini_settings(
    guild_id: int,
    server_name: str,
    file_name: str,
    settings: List[Dict[str, Any]]
) -> int:
    """
    Bulk import INI settings from parsed INI data.
    Clears existing settings for this file first.
    Returns count of imported settings.
    """
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            """
            DELETE FROM server_ini_settings
            WHERE guild_id = ? AND server_name = ? AND file_name = ?
            """,
            (guild_id, server_name, file_name)
        )
        
        count = 0
        for setting in settings:
            try:
                await db.execute(
                    """
                    INSERT INTO server_ini_settings (
                        guild_id, server_name, file_name, section_name,
                        key_name, key_value, value_type, description, is_modified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        guild_id,
                        server_name,
                        file_name,
                        setting["section_name"],
                        setting["key_name"],
                        setting.get("key_value"),
                        setting.get("value_type"),
                        setting.get("description"),
                    )
                )
                count += 1
            except Exception as e:
                logger.warning(f"Failed to import setting {setting.get('key_name')}: {e}")
        
        await db.commit()
        logger.info(f"Imported {count} INI settings for {server_name}/{file_name}")
        return count


async def get_ini_settings(
    guild_id: int,
    server_name: str,
    file_name: str,
    section: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get INI settings for a server file, optionally filtered by section."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        
        if section:
            cursor = await db.execute(
                """
                SELECT * FROM server_ini_settings
                WHERE guild_id = ? AND server_name = ? AND file_name = ? AND section_name = ?
                ORDER BY key_name COLLATE NOCASE
                """,
                (guild_id, server_name, file_name, section)
            )
        else:
            cursor = await db.execute(
                """
                SELECT * FROM server_ini_settings
                WHERE guild_id = ? AND server_name = ? AND file_name = ?
                ORDER BY section_name, key_name COLLATE NOCASE
                """,
                (guild_id, server_name, file_name)
            )
        
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_ini_setting(
    guild_id: int,
    server_name: str,
    file_name: str,
    section: str,
    key: str
) -> Optional[Dict[str, Any]]:
    """Get a single INI setting."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM server_ini_settings
            WHERE guild_id = ? AND server_name = ? AND file_name = ?
              AND section_name = ? AND key_name = ?
            """,
            (guild_id, server_name, file_name, section, key)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_ini_setting(
    guild_id: int,
    server_name: str,
    file_name: str,
    section: str,
    key: str,
    value: str,
    value_type: Optional[str] = None
) -> bool:
    """Update or insert an INI setting. Marks it as modified."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                """
                INSERT INTO server_ini_settings (
                    guild_id, server_name, file_name, section_name,
                    key_name, key_value, value_type, is_modified, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(guild_id, server_name, file_name, section_name, key_name)
                DO UPDATE SET
                    key_value = excluded.key_value,
                    value_type = COALESCE(excluded.value_type, value_type),
                    is_modified = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    guild_id, server_name, file_name, section, key, value,
                    value_type, datetime.utcnow().isoformat()
                )
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to update INI setting {section}.{key}: {e}")
        return False


async def find_ini_setting_by_key(
    guild_id: int,
    server_name: str,
    file_name: str,
    key: str,
) -> Optional[Dict[str, Any]]:
    """Find an INI setting by key name without knowing the section."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM server_ini_settings
            WHERE guild_id = ? AND server_name = ? AND file_name = ?
              AND key_name = ? COLLATE NOCASE
            LIMIT 1
            """,
            (guild_id, server_name, file_name, key)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_ini_setting(
    guild_id: int,
    server_name: str,
    file_name: str,
    section: str,
    key: str
) -> bool:
    """Delete an INI setting."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            cursor = await db.execute(
                """
                DELETE FROM server_ini_settings
                WHERE guild_id = ? AND server_name = ? AND file_name = ?
                  AND section_name = ? AND key_name = ?
                """,
                (guild_id, server_name, file_name, section, key)
            )
            await db.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Failed to delete INI setting {section}.{key}: {e}")
        return False


async def clear_ini_settings(
    guild_id: int,
    server_name: str,
    file_name: str
) -> int:
    """Clear all settings for a file (for reimport). Returns deleted count."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            """
            DELETE FROM server_ini_settings
            WHERE guild_id = ? AND server_name = ? AND file_name = ?
            """,
            (guild_id, server_name, file_name)
        )
        await db.commit()
        return cursor.rowcount


async def get_sections(
    guild_id: int,
    server_name: str,
    file_name: str
) -> List[str]:
    """Get list of unique section names for a file."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            """
            SELECT DISTINCT section_name FROM server_ini_settings
            WHERE guild_id = ? AND server_name = ? AND file_name = ?
            ORDER BY section_name
            """,
            (guild_id, server_name, file_name)
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]


async def get_settings_count(
    guild_id: int,
    server_name: str,
    file_name: str
) -> int:
    """Get count of settings for a file."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            """
            SELECT COUNT(*) FROM server_ini_settings
            WHERE guild_id = ? AND server_name = ? AND file_name = ?
            """,
            (guild_id, server_name, file_name)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


# ==================== Pending INI Changes ====================

async def queue_ini_change(
    guild_id: int,
    server_name: str,
    file_name: str,
    section: str,
    key: str,
    new_value: str,
    old_value: Optional[str],
    queued_by: int
) -> bool:
    """
    Queue an INI change for later application.
    Used for restart-required settings when server is running.
    """
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                """
                INSERT INTO ini_pending_changes (
                    guild_id, server_name, file_name, section_name,
                    key_name, old_value, new_value, queued_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, server_name, file_name, section_name, key_name)
                DO UPDATE SET
                    old_value = excluded.old_value,
                    new_value = excluded.new_value,
                    queued_by = excluded.queued_by,
                    queued_at = CURRENT_TIMESTAMP,
                    applied_at = NULL
                """,
                (guild_id, server_name, file_name, section, key, old_value, new_value, queued_by)
            )
            await db.commit()
            logger.info(f"Queued INI change: {section}.{key} = {new_value} for {server_name}")
            return True
    except Exception as e:
        logger.error(f"Failed to queue INI change: {e}")
        return False


async def get_pending_changes(
    guild_id: int,
    server_name: str
) -> List[Dict[str, Any]]:
    """Get all pending INI changes for a server."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM ini_pending_changes
            WHERE guild_id = ? AND server_name = ? AND applied_at IS NULL
            ORDER BY queued_at
            """,
            (guild_id, server_name)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_pending_changes_count(
    guild_id: int,
    server_name: str
) -> int:
    """Get count of pending changes for a server."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            """
            SELECT COUNT(*) FROM ini_pending_changes
            WHERE guild_id = ? AND server_name = ? AND applied_at IS NULL
            """,
            (guild_id, server_name)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def clear_pending_change(change_id: int) -> bool:
    """Remove a pending change from the queue."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                "DELETE FROM ini_pending_changes WHERE id = ?",
                (change_id,)
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to clear pending change {change_id}: {e}")
        return False


async def clear_all_pending_changes(
    guild_id: int,
    server_name: str
) -> int:
    """Clear all pending changes for a server. Returns deleted count."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            """
            DELETE FROM ini_pending_changes
            WHERE guild_id = ? AND server_name = ? AND applied_at IS NULL
            """,
            (guild_id, server_name)
        )
        await db.commit()
        return cursor.rowcount


async def mark_change_applied(change_id: int) -> bool:
    """Mark a pending change as applied."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                """
                UPDATE ini_pending_changes
                SET applied_at = ? WHERE id = ?
                """,
                (datetime.utcnow().isoformat(), change_id)
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to mark change {change_id} as applied: {e}")
        return False


async def mark_all_applied(
    guild_id: int,
    server_name: str
) -> int:
    """Mark all pending changes for a server as applied. Returns count."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            """
            UPDATE ini_pending_changes
            SET applied_at = ?
            WHERE guild_id = ? AND server_name = ? AND applied_at IS NULL
            """,
            (datetime.utcnow().isoformat(), guild_id, server_name)
        )
        await db.commit()
        return cursor.rowcount
