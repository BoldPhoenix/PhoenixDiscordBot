"""
Remote agent database operations.
Handles CRUD operations for remote agents.
"""

import aiosqlite
import logging
from datetime import datetime
from bot.utils.config import Config

logger = logging.getLogger(__name__)


async def check_auth_key_guild_binding(auth_key: str) -> tuple[bool, int | None]:
    """Check if an auth_key is already bound to a guild.
    
    Returns:
        tuple: (is_bound: bool, bound_guild_id: int | None)
        - If key is not bound: (False, None)
        - If key is bound: (True, guild_id)
    """
    db_path = Config.DATABASE_PATH
    
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                """
                SELECT guild_id FROM remote_agents
                WHERE auth_key = ? AND is_active = 1
                LIMIT 1
                """,
                (auth_key,),
            )
            
            row = await cursor.fetchone()
            if row:
                return (True, row[0])
            return (False, None)
    
    except Exception as e:
        logger.error(f"Failed to check auth_key binding: {e}")
        return (False, None)


async def check_auth_key_binding_to_different_guild(auth_key: str, guild_id: int) -> bool:
    """Check if an auth_key is already bound to a different guild.
    
    Returns:
        bool: True if key is bound to a different guild, False otherwise
    """
    db_path = Config.DATABASE_PATH
    
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                """
                SELECT guild_id FROM remote_agents
                WHERE auth_key = ? AND guild_id != ? AND is_active = 1
                LIMIT 1
                """,
                (auth_key, guild_id),
            )
            
            row = await cursor.fetchone()
            if row:
                return True
            return False
    
    except Exception as e:
        logger.error(f"Failed to check auth_key binding to different guild: {e}")
        return False


async def create_remote_agent(guild_id: int, agent_id: str, agent_ip: str, agent_port: int, auth_key: str) -> bool:
    """Create a new remote agent record.
    
    Note: This does NOT check auth_key binding - caller must validate first.
    """
    db_path = Config.DATABASE_PATH

    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO remote_agents 
                (guild_id, agent_id, agent_ip, agent_port, auth_key, last_connected, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
                (guild_id, agent_id, agent_ip, agent_port, auth_key, datetime.now()),
            )

            await db.commit()
            logger.info(f"Created remote agent {agent_id} for guild {guild_id}")
            return True

    except Exception as e:
        logger.error(f"Failed to create remote agent: {e}")
        return False


async def get_remote_agents(guild_id: int) -> list:
    """Get all remote agents for a guild."""
    db_path = Config.DATABASE_PATH

    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                """
                SELECT guild_id, agent_id, agent_ip, agent_port, auth_key, created_at, last_connected, is_active
                FROM remote_agents
                WHERE guild_id = ? AND is_active = 1
                ORDER BY created_at DESC
            """,
                (guild_id,),
            )

            rows = await cursor.fetchall()

            agents = []
            for row in rows:
                agents.append(
                    {
                        "guild_id": row[0],
                        "agent_id": row[1],
                        "ip": row[2],
                        "port": row[3],
                        "auth_key": row[4],
                        "created_at": row[5],
                        "last_connected": row[6],
                        "is_active": row[7],
                    }
                )

            return agents

    except Exception as e:
        logger.error(f"Failed to get remote agents: {e}")
        return []


async def get_all_remote_agents() -> list:
    """Get all remote agents (for any guild)."""
    db_path = Config.DATABASE_PATH

    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                """
                SELECT guild_id, agent_id, agent_ip, agent_port, auth_key, created_at, last_connected, is_active
                FROM remote_agents
                WHERE is_active = 1
                ORDER BY created_at DESC
            """
            )

            rows = await cursor.fetchall()

            agents = []
            for row in rows:
                agents.append(
                    {
                        "guild_id": row[0],
                        "agent_id": row[1],
                        "ip": row[2],
                        "port": row[3],
                        "auth_key": row[4],
                        "created_at": row[5],
                        "last_connected": row[6],
                        "is_active": row[7],
                    }
                )

            return agents

    except Exception as e:
        logger.error(f"Failed to get all remote agents: {e}")
        return []


async def get_all_remote_agents() -> list:
    """Get all remote agents (for reconnect recovery)."""
    db_path = Config.DATABASE_PATH

    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                """
                SELECT guild_id, agent_id, agent_ip, agent_port, auth_key, created_at, last_connected, is_active
                FROM remote_agents
                WHERE is_active = 1
                ORDER BY created_at DESC
            """
            )

            rows = await cursor.fetchall()

            agents = []
            for row in rows:
                agents.append(
                    {
                        "guild_id": row[0],
                        "agent_id": row[1],
                        "ip": row[2],
                        "port": row[3],
                        "auth_key": row[4],
                        "created_at": row[5],
                        "last_connected": row[6],
                        "is_active": row[7],
                    }
                )

            return agents

    except Exception as e:
        logger.error(f"Failed to get all remote agents: {e}")
        return []


async def update_agent_connection(agent_id: str, connected: bool = True) -> bool:
    """Update agent connection status."""
    db_path = Config.DATABASE_PATH

    try:
        async with aiosqlite.connect(db_path) as db:
            if connected:
                await db.execute(
                    """
                    UPDATE remote_agents 
                    SET last_connected = ?, is_active = 1
                    WHERE agent_id = ?
                """,
                    (datetime.now(), agent_id),
                )
            else:
                await db.execute(
                    """
                    UPDATE remote_agents
                    SET last_connected = ?
                    WHERE agent_id = ?
                """,
                    (datetime.now(), agent_id),
                )

            await db.commit()
            return True

    except Exception as e:
        logger.error(f"Failed to update agent connection: {e}")
        return False


async def delete_remote_agent(guild_id: int, agent_id: str) -> bool:
    """Delete a remote agent."""
    db_path = Config.DATABASE_PATH

    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                DELETE FROM remote_agents 
                WHERE guild_id = ? AND agent_id = ?
            """,
                (guild_id, agent_id),
            )

            await db.commit()
            logger.info(f"Deleted remote agent {agent_id} for guild {guild_id}")
            return True

    except Exception as e:
        logger.error(f"Failed to delete remote agent: {e}")
        return False


async def get_agent_by_id(guild_id: int, agent_id: str) -> dict:
    """Get a specific agent by ID."""
    db_path = Config.DATABASE_PATH

    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                """
                SELECT agent_id, agent_ip, agent_port, auth_key, created_at, last_connected, is_active
                FROM remote_agents 
                WHERE guild_id = ? AND agent_id = ? AND is_active = 1
            """,
                (guild_id, agent_id),
            )

            row = await cursor.fetchone()

            if row:
                return {
                    "agent_id": row[0],
                    "ip": row[1],
                    "port": row[2],
                    "auth_key": row[3],
                    "created_at": row[4],
                    "last_connected": row[5],
                    "is_active": row[6],
                }

            return None

    except Exception as e:
        logger.error(f"Failed to get agent by ID: {e}")
        return None
