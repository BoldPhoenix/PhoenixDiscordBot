"""
Maintenance database operations - backup schedules, jobs, and history.
"""

import aiosqlite
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from bot.utils.config import Config

logger = logging.getLogger("MaintenanceDB")

_db_path = lambda: Config.DATABASE_PATH


async def init_maintenance_tables():
    """Create maintenance tables if they don't exist."""
    async with aiosqlite.connect(_db_path()) as db:
        # Maintenance config per guild
        await db.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_config (
                guild_id INTEGER PRIMARY KEY,
                backup_enabled INTEGER DEFAULT 0,
                backup_type TEXT DEFAULT 'essentials',
                backup_schedule_type TEXT DEFAULT 'daily',
                backup_time TEXT DEFAULT '02:00',
                backup_day_of_week INTEGER DEFAULT 0,
                backup_retention_days INTEGER DEFAULT 30,
                backup_min_keep INTEGER DEFAULT 5,
                backup_root_path TEXT,
                update_enabled INTEGER DEFAULT 0,
                update_schedule_type TEXT DEFAULT 'weekly',
                update_time TEXT DEFAULT '03:00',
                update_day_of_week INTEGER DEFAULT 0,
                enable_pre_update_backup INTEGER DEFAULT 1,
                enable_saveworld INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add backup_type column if it doesn't exist (migration)
        try:
            await db.execute("ALTER TABLE maintenance_config ADD COLUMN backup_type TEXT DEFAULT 'essentials'")
        except:
            pass

        # Maintenance job history
        await db.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT,
                backup_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Backup history
        await db.execute("""
            CREATE TABLE IF NOT EXISTS backup_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                backup_path TEXT NOT NULL,
                backup_size_bytes INTEGER,
                status TEXT NOT NULL DEFAULT 'success',
                error_message TEXT,
                backup_type TEXT DEFAULT 'essentials',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add backup_type column if it doesn't exist (migration)
        try:
            await db.execute("ALTER TABLE backup_history ADD COLUMN backup_type TEXT DEFAULT 'essentials'")
        except:
            pass

        # Backup schedules table (multiple schedules per guild)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS backup_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                backup_type TEXT DEFAULT 'essentials',
                schedule_type TEXT DEFAULT 'daily',
                backup_time TEXT DEFAULT '02:00',
                day_of_week INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                target_directory TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add target_directory column if it doesn't exist (migration for existing DBs)
        try:
            await db.execute("ALTER TABLE backup_schedules ADD COLUMN target_directory TEXT")
        except:
            pass

        await db.commit()


async def get_maintenance_config(guild_id: int) -> Optional[dict]:
    """Get maintenance config for a guild."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM maintenance_config WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


_ALLOWED_MAINTENANCE_CONFIG_COLUMNS = {
    "backup_enabled", "backup_type", "backup_schedule_type", "backup_time",
    "backup_day_of_week", "backup_retention_days", "backup_min_keep",
    "backup_root_path", "update_enabled", "update_schedule_type",
    "update_time", "update_day_of_week", "enable_pre_update_backup",
    "enable_saveworld",
}


async def update_maintenance_config(guild_id: int, **kwargs) -> bool:
    """Update maintenance config for a guild."""
    kwargs = {k: v for k, v in kwargs.items() if k in _ALLOWED_MAINTENANCE_CONFIG_COLUMNS}
    if not kwargs:
        return False

    try:
        async with aiosqlite.connect(_db_path()) as db:
            set_parts = [f"{k} = excluded.{k}" for k in kwargs.keys()]
            set_clause = ", ".join(set_parts)
            columns = ", ".join(kwargs.keys())
            values = list(kwargs.values())
            
            await db.execute(
                f"""INSERT INTO maintenance_config (guild_id, {columns})
                VALUES (?, {', '.join(['?'] * len(kwargs))})
                ON CONFLICT(guild_id) DO UPDATE SET {set_clause}, updated_at = CURRENT_TIMESTAMP""",
                [guild_id] + values
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"update_maintenance_config error: {e}")
        return False


async def create_maintenance_job(
    guild_id: int,
    server_name: str,
    job_type: str,
) -> int:
    """Create a new maintenance job record. Returns job ID."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            cursor = await db.execute(
                """
                INSERT INTO maintenance_jobs (guild_id, server_name, job_type, status, started_at)
                VALUES (?, ?, ?, 'running', datetime('now'))
                """,
                (guild_id, server_name, job_type),
            )
            await db.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"create_maintenance_job error: {e}")
        return 0


async def update_maintenance_job(
    job_id: int,
    status: str,
    error_message: Optional[str] = None,
    backup_path: Optional[str] = None,
) -> bool:
    """Update a maintenance job record."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            if status == "completed":
                await db.execute(
                    """
                    UPDATE maintenance_jobs 
                    SET status = ?, completed_at = datetime('now'), backup_path = ?, error_message = ?
                    WHERE id = ?
                    """,
                    (status, backup_path, error_message, job_id),
                )
            else:
                await db.execute(
                    "UPDATE maintenance_jobs SET status = ?, error_message = ? WHERE id = ?",
                    (status, error_message, job_id),
                )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"update_maintenance_job error: {e}")
        return False


async def get_maintenance_jobs(guild_id: int, limit: int = 20) -> list:
    """Get maintenance job history for a guild."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM maintenance_jobs 
            WHERE guild_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (guild_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def add_backup_history(
    guild_id: int,
    server_name: str,
    backup_path: str,
    backup_size_bytes: Optional[int] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    backup_type: str = "essentials",
) -> bool:
    """Add a backup to history."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                """
                INSERT INTO backup_history 
                (guild_id, server_name, backup_path, backup_size_bytes, status, error_message, backup_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, server_name, backup_path, backup_size_bytes, status, error_message, backup_type),
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"add_backup_history error: {e}")
        return False


async def get_backup_history(guild_id: int, server_name: str = None, limit: int = 20) -> list:
    """Get backup history for a guild (optionally filtered by server)."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        if server_name:
            async with db.execute(
                """
                SELECT * FROM backup_history 
                WHERE guild_id = ? AND server_name = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (guild_id, server_name, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """
                SELECT * FROM backup_history 
                WHERE guild_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (guild_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def cleanup_old_backups(guild_id: int, retention_days: int, min_keep: int) -> int:
    """Clean up backups older than retention_days. Returns count of deleted records."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            # First get count of current backups
            cursor = await db.execute(
                "SELECT COUNT(*) FROM backup_history WHERE guild_id = ?",
                (guild_id,),
            )
            count = (await cursor.fetchone())[0]

            if count <= min_keep:
                return 0  # Don't delete if at min_keep

            # Delete old records
            await db.execute(
                """
                DELETE FROM backup_history 
                WHERE guild_id = ? 
                AND created_at < datetime('now', '-' || ? || ' days')
                AND id NOT IN (
                    SELECT id FROM backup_history 
                    WHERE guild_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                )
                """,
                (guild_id, retention_days, guild_id, min_keep),
            )
            await db.commit()
            return db.total_changes
    except Exception as e:
        logger.error(f"cleanup_old_backups error: {e}")
        return 0


# ---------------------------------------------------------------------------
# Backup schedules CRUD (multiple schedules per guild)
# ---------------------------------------------------------------------------

async def get_backup_schedules(guild_id: int) -> list:
    """Get all backup schedules for a guild."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM backup_schedules WHERE guild_id = ? ORDER BY id",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def add_backup_schedule(
    guild_id: int,
    name: str,
    backup_type: str = "essentials",
    schedule_type: str = "daily",
    backup_time: str = "02:00",
    day_of_week: int = 0,
    enabled: int = 1,
    target_directory: str = None,
) -> int:
    """Add a new backup schedule. Returns new schedule id (0 on error)."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            cursor = await db.execute(
                """
                INSERT INTO backup_schedules
                    (guild_id, name, backup_type, schedule_type, backup_time, day_of_week, enabled, target_directory)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, name, backup_type, schedule_type, backup_time, day_of_week, enabled, target_directory),
            )
            await db.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"add_backup_schedule error: {e}")
        return 0


_ALLOWED_BACKUP_SCHEDULE_COLUMNS = {
    "name", "backup_type", "schedule_type", "backup_time",
    "day_of_week", "enabled", "target_directory",
}


async def update_backup_schedule(schedule_id: int, **kwargs) -> bool:
    """Update fields on an existing backup schedule."""
    kwargs = {k: v for k, v in kwargs.items() if k in _ALLOWED_BACKUP_SCHEDULE_COLUMNS}
    if not kwargs:
        return False
    try:
        async with aiosqlite.connect(_db_path()) as db:
            set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
            await db.execute(
                f"UPDATE backup_schedules SET {set_clause} WHERE id = ?",
                list(kwargs.values()) + [schedule_id],
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"update_backup_schedule error: {e}")
        return False


async def delete_backup_schedule(schedule_id: int, guild_id: int) -> bool:
    """Delete a backup schedule (guild_id guards against cross-guild deletes)."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                "DELETE FROM backup_schedules WHERE id = ? AND guild_id = ?",
                (schedule_id, guild_id),
            )
            await db.commit()
        return True
    except Exception as e:
        logger.error(f"delete_backup_schedule error: {e}")
        return False


async def get_all_enabled_backup_schedules() -> list:
    """Get all enabled backup schedules across all guilds (used by scheduler)."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM backup_schedules WHERE enabled = 1 ORDER BY guild_id, id",
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_all_enabled_update_configs() -> list:
    """Get all guilds with update_enabled=1 (used by update scheduler)."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM maintenance_config WHERE update_enabled = 1 ORDER BY guild_id",
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
