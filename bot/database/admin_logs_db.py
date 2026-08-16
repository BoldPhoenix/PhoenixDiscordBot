"""
Admin action logging database module.
Stores all admin commands and their results for audit trail and notifications.
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger("AdminLogsDB")

# Database path
DB_PATH = Path(__file__).parent / "admin_logs.db"


async def init_admin_logs_table():
    """Initialize the admin logs table if it doesn't exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                admin_id INTEGER NOT NULL,
                admin_name TEXT NOT NULL,
                action_type TEXT NOT NULL,
                servers_affected TEXT,
                target_player TEXT,
                target_player_id TEXT,
                details TEXT,
                status TEXT,
                results TEXT,
                message_id INTEGER,
                guild_id INTEGER
            )
            """
        )

        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_admin_id ON admin_logs(admin_id)
            """
        )

        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_timestamp ON admin_logs(timestamp)
            """
        )

        c.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_action_type ON admin_logs(action_type)
            """
        )

        conn.commit()
        conn.close()
        logger.info("Admin logs table initialized")
    except Exception as e:
        logger.error(f"Error initializing admin logs table: {e}")


async def log_admin_action(
    admin_id: int,
    admin_name: str,
    action_type: str,
    servers_affected: List[str],
    guild_id: int,
    target_player: Optional[str] = None,
    target_player_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    status: str = "pending",
    results: Optional[str] = None,
    message_id: Optional[int] = None,
) -> int:
    """
    Log an admin action to the database.
    
    Args:
        admin_id: Discord ID of the admin
        admin_name: Display name of the admin
        action_type: Type of action (kick, ban, update, etc)
        servers_affected: List of server names affected
        guild_id: Guild ID for context
        target_player: Name of player affected (if applicable)
        target_player_id: ID of player affected (if applicable)
        details: Dict with full command details
        status: Action status (pending/success/failed/partial)
        results: Results of the action
        message_id: Discord message ID for cross-reference
    
    Returns:
        The log entry ID
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        servers_json = json.dumps(servers_affected) if servers_affected else "[]"
        details_json = json.dumps(details) if details else "{}"

        c.execute(
            """
            INSERT INTO admin_logs 
            (admin_id, admin_name, action_type, servers_affected, guild_id, 
             target_player, target_player_id, details, status, results, message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                admin_id,
                admin_name,
                action_type,
                servers_json,
                guild_id,
                target_player,
                target_player_id,
                details_json,
                status,
                results,
                message_id,
            ),
        )

        conn.commit()
        log_id = c.lastrowid
        conn.close()

        logger.info(f"Logged admin action: {action_type} by {admin_name} (ID: {log_id})")
        return log_id

    except Exception as e:
        logger.error(f"Error logging admin action: {e}")
        return -1


async def update_admin_action(
    log_id: int,
    status: Optional[str] = None,
    results: Optional[str] = None,
    message_id: Optional[int] = None,
):
    """Update an admin action log entry."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        updates = []
        params = []

        if status:
            updates.append("status = ?")
            params.append(status)

        if results:
            updates.append("results = ?")
            params.append(results)

        if message_id:
            updates.append("message_id = ?")
            params.append(message_id)

        if not updates:
            conn.close()
            return

        params.append(log_id)
        query = f"UPDATE admin_logs SET {', '.join(updates)} WHERE id = ?"

        c.execute(query, params)
        conn.commit()
        conn.close()

    except Exception as e:
        logger.error(f"Error updating admin action log: {e}")


async def get_admin_logs(
    admin_id: Optional[int] = None,
    action_type: Optional[str] = None,
    guild_id: Optional[int] = None,
    limit: int = 50,
    days: int = 7,
) -> List[Dict[str, Any]]:
    """
    Retrieve admin logs with optional filters.
    
    Args:
        admin_id: Filter by admin ID
        action_type: Filter by action type
        guild_id: Filter by guild ID
        limit: Maximum number of results
        days: Only return logs from last N days
    
    Returns:
        List of admin log entries
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        query = "SELECT * FROM admin_logs WHERE timestamp >= datetime('now', '-' || ? || ' days')"
        params = [days]

        if admin_id:
            query += " AND admin_id = ?"
            params.append(admin_id)

        if action_type:
            query += " AND action_type = ?"
            params.append(action_type)

        if guild_id:
            query += " AND guild_id = ?"
            params.append(guild_id)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        # Convert to list of dicts
        columns = [description[0] for description in c.description]
        logs = []
        for row in rows:
            log = dict(zip(columns, row))
            log["servers_affected"] = json.loads(log.get("servers_affected", "[]"))
            log["details"] = json.loads(log.get("details", "{}"))
            logs.append(log)

        return logs

    except Exception as e:
        logger.error(f"Error retrieving admin logs: {e}")
        return []


async def get_log_by_id(log_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a specific admin log entry by ID."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("SELECT * FROM admin_logs WHERE id = ?", (log_id,))
        row = c.fetchone()
        conn.close()

        if not row:
            return None

        columns = [description[0] for description in c.description]
        log = dict(zip(columns, row))
        log["servers_affected"] = json.loads(log.get("servers_affected", "[]"))
        log["details"] = json.loads(log.get("details", "{}"))

        return log

    except Exception as e:
        logger.error(f"Error retrieving admin log: {e}")
        return None


async def cleanup_old_logs(days: int = 90):
    """Delete admin logs older than specified days."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute(
            "DELETE FROM admin_logs WHERE timestamp < datetime('now', '-' || ? || ' days')",
            (days,),
        )

        deleted = c.rowcount
        conn.commit()
        conn.close()

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old admin log entries")

    except Exception as e:
        logger.error(f"Error cleaning up admin logs: {e}")
