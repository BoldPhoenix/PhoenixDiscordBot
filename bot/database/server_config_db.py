"""
Server configuration database for multi-server bot deployment.
Each Discord server gets its own configuration stored in the database.
"""

import aiosqlite
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime

from bot.utils.config import Config

logger = logging.getLogger("ServerConfigDB")


async def init_server_config_tables():
    """Initialize server configuration tables."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        # Server-specific configuration
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS server_configs (
                guild_id INTEGER PRIMARY KEY,
                guild_name TEXT,
                
                -- Channel Configuration
                chat_channel_id INTEGER,
                status_channel_id INTEGER,
                shop_channel_id INTEGER,
                admin_log_channel_id INTEGER,
                server_log_channel_id INTEGER,
                events_channel_id INTEGER,
                economy_channel_id INTEGER,
                shop_announcement_channel_id INTEGER,
                mod_channel_id INTEGER,
                voice_category_id INTEGER,
                
                -- Admin Configuration
                admin_role_id INTEGER,
                user_role_id INTEGER,
                
                -- Bot Configuration
                bot_prefix TEXT DEFAULT '!',
                currency_name TEXT DEFAULT 'Phoenix Coins',
                currency_emoji TEXT DEFAULT '🪙',
                status_update_interval INTEGER DEFAULT 60,
                chat_poll_interval INTEGER DEFAULT 5,
                
                -- Shop Configuration
                shop_enabled BOOLEAN DEFAULT 1,
                shop_items_per_page INTEGER DEFAULT 10,
                shop_starting_balance INTEGER DEFAULT 1000,
                shop_daily_login_bonus INTEGER DEFAULT 100,
                shop_allow_refunds BOOLEAN DEFAULT 0,
                shop_refund_percentage INTEGER DEFAULT 50,
                shop_max_purchase_per_day INTEGER DEFAULT 0,
                shop_delivery_cooldown INTEGER DEFAULT 60,
                shop_require_linked_account BOOLEAN DEFAULT 0,
                
                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Server ARK servers configuration
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ark_servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                game_port INTEGER,
                query_port INTEGER,
                rcon_port INTEGER NOT NULL,
                rcon_password TEXT NOT NULL,
                service_name TEXT,
                max_players INTEGER DEFAULT 70,
                chat_enabled BOOLEAN DEFAULT 1,
                log_path TEXT,
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (guild_id) REFERENCES server_configs(guild_id) ON DELETE CASCADE
            )
        """
        )

        # Add game_port column if it doesn't exist (migration)
        try:
            await db.execute("ALTER TABLE ark_servers ADD COLUMN game_port INTEGER")
            await db.commit()
        except:
            pass  # Column already exists

        # Simple voice channel mapping table (works with .env or DB config)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS voice_channel_mappings (
                guild_id INTEGER NOT NULL,
                rcon_port INTEGER NOT NULL,
                voice_channel_id INTEGER NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, rcon_port)
            )
        """
        )

        await db.commit()
        logger.info("Server configuration tables initialized")

    # Ensure new columns exist (lightweight migrations)
    async with aiosqlite.connect(db_path) as db:
        try:
            async with db.execute("PRAGMA table_info('ark_servers')") as cursor:
                cols = [row[1] async for row in cursor]
            if "voice_channel_id" not in cols:
                await db.execute(
                    "ALTER TABLE ark_servers ADD COLUMN voice_channel_id INTEGER"
                )
                await db.commit()
                logger.info("Added column voice_channel_id to ark_servers")
            if "server_path" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN server_path TEXT")
                await db.commit()
                logger.info(
                    "Added column server_path to ark_servers (for self-hosted servers)"
                )
            if "steamcmd_path" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN steamcmd_path TEXT")
                await db.commit()
                logger.info(
                    "Added column steamcmd_path to ark_servers (for per-server SteamCMD)"
                )
            if "display_name" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN display_name TEXT")
                await db.execute("UPDATE ark_servers SET display_name = name WHERE display_name IS NULL")
                await db.commit()
                logger.info("Added column display_name to ark_servers (populated from name)")
            if "disabled_reason" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN disabled_reason TEXT")
                await db.commit()
                logger.info("Added column disabled_reason to ark_servers")
        except Exception as e:
            logger.warning(f"Migration check warning: {e}")

        # Ensure mod_channel_id exists (may already from setup_gui migration)
        try:
            async with db.execute("PRAGMA table_info('server_configs')") as cursor:
                config_cols = [row[1] async for row in cursor]
            if "mod_channel_id" not in config_cols:
                await db.execute(
                    "ALTER TABLE server_configs ADD COLUMN mod_channel_id INTEGER"
                )
                await db.commit()
                logger.info("Added column mod_channel_id to server_configs")
            if "admin_log_channel_id" not in config_cols:
                await db.execute(
                    "ALTER TABLE server_configs ADD COLUMN admin_log_channel_id INTEGER"
                )
                await db.commit()
                logger.info("Added column admin_log_channel_id to server_configs")
            if "server_log_channel_id" not in config_cols:
                await db.execute(
                    "ALTER TABLE server_configs ADD COLUMN server_log_channel_id INTEGER"
                )
                await db.commit()
                logger.info("Added column server_log_channel_id to server_configs")
            if "events_channel_id" not in config_cols:
                await db.execute(
                    "ALTER TABLE server_configs ADD COLUMN events_channel_id INTEGER"
                )
                await db.commit()
                logger.info("Added column events_channel_id to server_configs")
            if "economy_channel_id" not in config_cols:
                await db.execute(
                    "ALTER TABLE server_configs ADD COLUMN economy_channel_id INTEGER"
                )
                await db.commit()
                logger.info("Added column economy_channel_id to server_configs")
            if "voice_category_id" not in config_cols:
                await db.execute(
                    "ALTER TABLE server_configs ADD COLUMN voice_category_id INTEGER"
                )
                await db.commit()
                logger.info("Added column voice_category_id to server_configs")
        except Exception as e:
            logger.warning(f"Migration check warning for server_configs: {e}")
            if "ark_version" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN ark_version TEXT")
                await db.commit()
                logger.info(
                    "Added column ark_version to ark_servers (for ARK version tracking)"
                )
            if "update_needed" not in cols:
                await db.execute(
                    "ALTER TABLE ark_servers ADD COLUMN update_needed BOOLEAN DEFAULT 0"
                )
                await db.commit()
                logger.info(
                    "Added column update_needed to ark_servers (for update tracking)"
                )
            if "latest_build_id" not in cols:
                await db.execute(
                    "ALTER TABLE ark_servers ADD COLUMN latest_build_id TEXT"
                )
                await db.commit()
                logger.info(
                    "Added column latest_build_id to ark_servers (for build tracking)"
                )
        except Exception as e:
            logger.error(f"Failed ensuring columns: {e}")

    # Wizard-related columns for ark_servers (map_name, mods, cluster_id, cluster_path, battleye_enabled)
    async with aiosqlite.connect(db_path) as db:
        try:
            async with db.execute("PRAGMA table_info('ark_servers')") as cursor:
                cols = [row[1] async for row in cursor]
            if "map_name" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN map_name TEXT")
                await db.commit()
                logger.info("Added column map_name to ark_servers")
            if "mods" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN mods TEXT")
                await db.commit()
                logger.info("Added column mods to ark_servers")
            if "cluster_id" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN cluster_id TEXT")
                await db.commit()
                logger.info("Added column cluster_id to ark_servers")
            if "cluster_path" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN cluster_path TEXT")
                await db.commit()
                logger.info("Added column cluster_path to ark_servers")
            if "battleye_enabled" not in cols:
                await db.execute(
                    "ALTER TABLE ark_servers ADD COLUMN battleye_enabled BOOLEAN DEFAULT 0"
                )
                await db.commit()
                logger.info("Added column battleye_enabled to ark_servers")
            if "active_event" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN active_event TEXT")
                await db.commit()
                logger.info("Added column active_event to ark_servers")
        except Exception as e:
            logger.warning(f"Migration warning for wizard columns: {e}")

    # Ensure hosting_type column exists in server_configs
    async with aiosqlite.connect(db_path) as db:
        try:
            async with db.execute("PRAGMA table_info('server_configs')") as cursor:
                cols = [row[1] async for row in cursor]
            if "hosting_type" not in cols:
                await db.execute(
                    "ALTER TABLE server_configs ADD COLUMN hosting_type TEXT DEFAULT 'self_hosted'"
                )
                await db.commit()
                logger.info("Added column hosting_type to server_configs")
            if "voice_category_id" not in cols:
                await db.execute("ALTER TABLE server_configs ADD COLUMN voice_category_id INTEGER")
                await db.commit()
                logger.info("Added column voice_category_id to server_configs")
            if "user_role_id" not in cols:
                await db.execute("ALTER TABLE server_configs ADD COLUMN user_role_id INTEGER")
                await db.commit()
                logger.info("Added column user_role_id to server_configs (verified user role)")
            if "cluster_root_path" not in cols:
                await db.execute("ALTER TABLE server_configs ADD COLUMN cluster_root_path TEXT")
                await db.commit()
                logger.info("Added column cluster_root_path to server_configs")
            if "cluster_id" not in cols:
                await db.execute("ALTER TABLE server_configs ADD COLUMN cluster_id TEXT")
                await db.commit()
                logger.info("Added column cluster_id to server_configs")
            if "cluster_folder_path" not in cols:
                await db.execute("ALTER TABLE server_configs ADD COLUMN cluster_folder_path TEXT")
                await db.commit()
                logger.info("Added column cluster_folder_path to server_configs")
            if "server_channel_id" not in cols:
                await db.execute("ALTER TABLE server_configs ADD COLUMN server_channel_id INTEGER")
                await db.commit()
                logger.info("Added column server_channel_id to server_configs")
            if "mod_channel_id" not in cols:
                await db.execute("ALTER TABLE server_configs ADD COLUMN mod_channel_id INTEGER")
                await db.commit()
                logger.info("Added column mod_channel_id to server_configs")
            if "economy_channel_id" not in cols:
                await db.execute("ALTER TABLE server_configs ADD COLUMN economy_channel_id INTEGER")
                await db.commit()
                logger.info("Added column economy_channel_id to server_configs")
            if "events_channel_id" not in cols:
                await db.execute("ALTER TABLE server_configs ADD COLUMN events_channel_id INTEGER")
                await db.commit()
                logger.info("Added column events_channel_id to server_configs")
        except Exception as e:
            logger.error(f"Failed ensuring columns in server_configs: {e}")


async def get_server_config(guild_id: int) -> Optional[Dict[str, Any]]:
    """Get configuration for a specific server."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM server_configs WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def set_admin_log_channel_id(guild_id: int, admin_log_channel_id: int) -> bool:
    """Set admin log channel ID for a guild."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO server_configs (guild_id, admin_log_channel_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET admin_log_channel_id=excluded.admin_log_channel_id, updated_at=CURRENT_TIMESTAMP
            """,
            (guild_id, admin_log_channel_id),
        )
        await db.commit()
    return True


async def get_hosting_type(guild_id: int) -> str:
    """Get the hosting type for a guild (self_hosted or nitrado)."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT hosting_type FROM server_configs WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            # Default to self_hosted if not set
            return row[0] if row and row[0] else "self_hosted"


async def set_hosting_type(guild_id: int, hosting_type: str) -> bool:
    """Set the hosting type for a guild (self_hosted or nitrado)."""
    if hosting_type not in ("self_hosted", "nitrado"):
        raise ValueError("hosting_type must be 'self_hosted' or 'nitrado'")

    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE server_configs SET hosting_type = ? WHERE guild_id = ?",
            (hosting_type, guild_id),
        )
        await db.commit()
        return True


async def is_self_hosted(guild_id: int) -> bool:
    """Check if a guild is using self-hosted servers."""
    return await get_hosting_type(guild_id) == "self_hosted"


_ALLOWED_SERVER_CONFIG_COLUMNS = {
    # Channel Configuration
    "chat_channel_id", "status_channel_id", "shop_channel_id",
    "admin_log_channel_id", "server_log_channel_id", "events_channel_id",
    "economy_channel_id", "shop_announcement_channel_id", "mod_channel_id",
    "voice_category_id", "server_channel_id",
    # Admin Configuration
    "admin_role_id", "user_role_id",
    # Bot Configuration
    "bot_prefix", "currency_name", "currency_emoji",
    "status_update_interval", "chat_poll_interval",
    # Shop Configuration
    "shop_enabled", "shop_items_per_page", "shop_starting_balance",
    "shop_daily_login_bonus", "shop_allow_refunds", "shop_refund_percentage",
    "shop_max_purchase_per_day", "shop_delivery_cooldown",
    "shop_require_linked_account",
    # Hosting
    "hosting_type", "cluster_root_path", "cluster_id", "cluster_folder_path",
}


async def create_or_update_server_config(guild_id: int, guild_name: str, **kwargs) -> bool:
    """Create or update server configuration."""
    kwargs = {k: v for k, v in kwargs.items() if k in _ALLOWED_SERVER_CONFIG_COLUMNS}
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        # Check if config exists
        async with db.execute(
            "SELECT guild_id FROM server_configs WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            exists = await cursor.fetchone()

        if exists:
            # Update existing config
            set_clauses = ["guild_name = ?", "updated_at = CURRENT_TIMESTAMP"]
            values = [guild_name]

            for key, value in kwargs.items():
                set_clauses.append(f"{key} = ?")
                values.append(value)

            values.append(guild_id)

            await db.execute(
                f"UPDATE server_configs SET {', '.join(set_clauses)} WHERE guild_id = ?", values
            )
        else:
            # Insert new config with defaults
            columns = ["guild_id", "guild_name"] + list(kwargs.keys())
            placeholders = ["?"] * len(columns)
            values = [guild_id, guild_name] + list(kwargs.values())

            await db.execute(
                f"INSERT INTO server_configs ({', '.join(columns)}) VALUES ({', '.join(placeholders)})",
                values,
            )

        await db.commit()
        return True


async def get_ark_servers(guild_id: int, include_disabled: bool = False) -> List[Dict[str, Any]]:
    """Get ARK servers for a guild. By default, only returns enabled servers.
    
    Args:
        guild_id: The Discord guild ID
        include_disabled: If True, returns all servers including disabled ones.
                         If False (default), only returns enabled servers.
    """
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM ark_servers WHERE guild_id = ?"
        if not include_disabled:
            query += " AND enabled = 1"
        query += " ORDER BY name"
        
        async with db.execute(query, (guild_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_all_ark_servers_including_disabled(guild_id: int) -> List[Dict[str, Any]]:
    """Get all ARK servers for a guild including disabled ones."""
    return await get_ark_servers(guild_id, include_disabled=True)


async def get_ark_server_by_port(guild_id: int, rcon_port: int) -> Optional[Dict[str, Any]]:
    """Get a single ARK server by rcon_port for a guild."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM ark_servers WHERE guild_id = ? AND rcon_port = ? AND enabled = 1",
            (guild_id, rcon_port),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_ark_server_by_id(server_id: int) -> Optional[Dict[str, Any]]:
    """Get a single ARK server by ID."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM ark_servers WHERE id = ?",
            (server_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_ark_server_by_name(guild_id: int, server_name: str) -> Optional[Dict[str, Any]]:
    """Get a single ARK server by name within a guild."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM ark_servers WHERE guild_id = ? AND name = ?",
            (guild_id, server_name),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_ark_server_by_service_name(guild_id: int, service_name: str) -> Optional[Dict[str, Any]]:
    """Get a single ARK server by its Windows service name within a guild."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM ark_servers WHERE guild_id = ? AND service_name = ?",
            (guild_id, service_name),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def add_ark_server(guild_id: int, **server_config) -> int:
    """Add an ARK server configuration."""
    db_path = Path(Config.DATABASE_PATH)

    required_fields = ["name", "host", "rcon_port", "rcon_password"]
    for field in required_fields:
        if field not in server_config:
            raise ValueError(f"Missing required field: {field}")

    async with aiosqlite.connect(db_path) as db:
        # Check if rcon_host column exists (for backward compatibility)
        cursor = await db.execute("PRAGMA table_info(ark_servers)")
        columns = [row[1] for row in await cursor.fetchall()]
        has_rcon_host = "rcon_host" in columns

        if has_rcon_host:
            # Old schema with rcon_host column
            cursor = await db.execute(
                """
                INSERT INTO ark_servers
                (guild_id, name, host, rcon_host, game_port, query_port, rcon_port, rcon_password,
                 service_name, max_players, chat_enabled, log_path, server_path, steamcmd_path,
                 map_name, mods, cluster_id, cluster_path, battleye_enabled, active_event)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    server_config["name"],
                    server_config["host"],
                    server_config["host"],  # rcon_host same as host
                    server_config.get("game_port"),
                    server_config.get("query_port"),
                    server_config["rcon_port"],
                    server_config["rcon_password"],
                    server_config.get("service_name"),
                    server_config.get("max_players", 70),
                    server_config.get("chat_enabled", True),
                    server_config.get("log_path"),
                    server_config.get("server_path"),
                    server_config.get("steamcmd_path"),
                    server_config.get("map_name"),
                    server_config.get("mods"),
                    server_config.get("cluster_id"),
                    server_config.get("cluster_path"),
                    server_config.get("battleye_enabled", False),
                    server_config.get("active_event"),
                ),
            )
        else:
            # New schema without rcon_host
            cursor = await db.execute(
                """
                INSERT INTO ark_servers
                (guild_id, name, host, game_port, query_port, rcon_port, rcon_password,
                 service_name, max_players, chat_enabled, log_path, server_path, steamcmd_path,
                 map_name, mods, cluster_id, cluster_path, battleye_enabled, active_event)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    server_config["name"],
                    server_config["host"],
                    server_config.get("game_port"),
                    server_config.get("query_port"),
                    server_config["rcon_port"],
                    server_config["rcon_password"],
                    server_config.get("service_name"),
                    server_config.get("max_players", 70),
                    server_config.get("chat_enabled", True),
                    server_config.get("log_path"),
                    server_config.get("server_path"),
                    server_config.get("steamcmd_path"),
                    server_config.get("map_name"),
                    server_config.get("mods"),
                    server_config.get("cluster_id"),
                    server_config.get("cluster_path"),
                    server_config.get("battleye_enabled", False),
                    server_config.get("active_event"),
                ),
            )
        await db.commit()
        return cursor.lastrowid


_ALLOWED_ARK_SERVER_COLUMNS = {
    "name", "host", "rcon_host", "rcon_port", "rcon_password", "query_port",
    "game_port", "map_name", "max_players", "server_path", "steamcmd_path",
    "service_name", "display_name", "voice_channel_id", "chat_enabled",
    "log_path", "enabled", "disabled_reason", "ark_version",
    "update_needed", "latest_build_id", "mods", "cluster_id", "cluster_path",
    "battleye_enabled", "active_event", "server_password", "admin_password",
    "rcon_name", "motd", "motd_duration",
}


async def update_ark_server(server_id: int, **updates) -> bool:
    """Update an ARK server configuration."""
    updates = {k: v for k, v in updates.items() if k in _ALLOWED_ARK_SERVER_COLUMNS}
    db_path = Path(Config.DATABASE_PATH)

    if not updates:
        return False

    set_clauses = [f"{key} = ?" for key in updates.keys()]
    values = list(updates.values()) + [server_id]

    async with aiosqlite.connect(db_path) as db:
        # Handle backward compatibility: if updating host and rcon_host exists, update both
        if "host" in updates:
            async with db.execute("PRAGMA table_info(ark_servers)") as cursor:
                columns = [row[1] async for row in cursor]
            if "rcon_host" in columns and "rcon_host" not in updates:
                updates["rcon_host"] = updates["host"]
                set_clauses = [f"{key} = ?" for key in updates.keys()]
                values = list(updates.values()) + [server_id]

        await db.execute(
            f"UPDATE ark_servers SET {', '.join(set_clauses)} WHERE id = ?", values
        )
        await db.commit()
        return True


async def update_server_ark_version(server_id: int, ark_version: str) -> bool:
    """Update the ARK version for a server."""
    return await update_ark_server(server_id, ark_version=ark_version)


async def update_server_update_status(
    server_id: int, update_needed: bool, latest_build_id: Optional[str] = None
) -> bool:
    """
    Update the update_needed status and latest_build_id for a server.
    
    Args:
        server_id: Server ID to update
        update_needed: Whether an update is available
        latest_build_id: Latest build ID from SteamCMD
        
    Returns:
        True if successful, False otherwise
    """
    updates = {"update_needed": update_needed}
    if latest_build_id:
        updates["latest_build_id"] = latest_build_id
    
    return await update_ark_server(server_id, **updates)


async def update_ark_server_by_port(guild_id: int, rcon_port: int, **updates) -> bool:
    """Update an ARK server identified by (guild_id, rcon_port)."""
    updates = {k: v for k, v in updates.items() if k in _ALLOWED_ARK_SERVER_COLUMNS}
    if not updates:
        return False
    db_path = Path(Config.DATABASE_PATH)
    set_clauses = [f"{key} = ?" for key in updates.keys()]
    values = list(updates.values()) + [guild_id, rcon_port]
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"UPDATE ark_servers SET {', '.join(set_clauses)} WHERE guild_id = ? AND rcon_port = ?",
            values,
        )
        await db.commit()
        return True


async def set_server_voice_channel_id(guild_id: int, rcon_port: int, channel_id: int) -> bool:
    """Persist the Discord voice channel ID for the given server rcon_port."""
    # Try the simple mapping table first (works with .env config)
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                INSERT INTO voice_channel_mappings (guild_id, rcon_port, voice_channel_id, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id, rcon_port) 
                DO UPDATE SET voice_channel_id = ?, updated_at = CURRENT_TIMESTAMP
            """,
                (guild_id, rcon_port, channel_id, channel_id),
            )
            await db.commit()
            logger.debug(
                f"Saved voice channel mapping: guild {guild_id}, port {rcon_port} -> channel {channel_id}"
            )
            return True
    except Exception as e:
        logger.error(f"Failed to save voice channel mapping: {e}")
        # Fallback to the ark_servers table if it exists
        return await update_ark_server_by_port(guild_id, rcon_port, voice_channel_id=channel_id)


async def get_voice_channel_id(guild_id: int, rcon_port: int) -> Optional[int]:
    """Get the stored voice channel ID for a server port."""
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT voice_channel_id FROM voice_channel_mappings WHERE guild_id = ? AND rcon_port = ?",
                (guild_id, rcon_port),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
    except Exception as e:
        logger.error(f"Failed to get voice channel mapping: {e}")
        # Fallback to ark_servers table
        row = await get_ark_server_by_port(guild_id, rcon_port)
        return row.get("voice_channel_id") if row else None


async def clear_server_voice_channel_id(guild_id: int, rcon_port: int) -> bool:
    """Clear the stored voice channel ID for the given server rcon_port."""
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "DELETE FROM voice_channel_mappings WHERE guild_id = ? AND rcon_port = ?",
                (guild_id, rcon_port),
            )
            await db.commit()
            logger.debug(f"Cleared voice channel mapping: guild {guild_id}, port {rcon_port}")
            return True
    except Exception as e:
        logger.error(f"Failed to clear voice channel mapping: {e}")
        # Fallback to ark_servers table
        return await update_ark_server_by_port(guild_id, rcon_port, voice_channel_id=None)


async def remove_ark_server(server_id: int) -> bool:
    """Remove (delete) an ARK server from the database."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        # Get guild_id for notification before deletion
        async with db.execute("SELECT guild_id FROM ark_servers WHERE id = ?", (server_id,)) as cursor:
            row = await cursor.fetchone()
            guild_id = row[0] if row else None
        
        # Actually delete the server from database
        cursor = await db.execute("DELETE FROM ark_servers WHERE id = ?", (server_id,))
        await db.commit()
        
        # Notify subscribers that servers changed
        if guild_id:
            from bot.utils.server_events import server_events
            await server_events.notify_servers_changed(guild_id)
        
        return cursor.rowcount > 0


async def get_all_guild_ids() -> List[int]:
    """Get all configured guild IDs."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT guild_id FROM server_configs") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_server_motd(guild_id: int, rcon_port: int) -> tuple[Optional[str], Optional[int]]:
    """Get the stored MOTD and duration for a server.

    Returns:
        Tuple of (motd_message, duration_seconds)
    """
    db_path = Path(Config.DATABASE_PATH)

    # First ensure the motd and motd_duration columns exist
    async with aiosqlite.connect(db_path) as db:
        try:
            async with db.execute("PRAGMA table_info('ark_servers')") as cursor:
                cols = [row[1] async for row in cursor]
            if "motd" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN motd TEXT")
            if "motd_duration" not in cols:
                await db.execute(
                    "ALTER TABLE ark_servers ADD COLUMN motd_duration INTEGER DEFAULT 30"
                )
            await db.commit()
        except Exception:
            pass

        async with db.execute(
            "SELECT motd, motd_duration FROM ark_servers WHERE guild_id = ? AND rcon_port = ?",
            (guild_id, rcon_port),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return (row[0] if row[0] else None, row[1] if row[1] else 30)
            return (None, 30)


async def set_server_motd(guild_id: int, rcon_port: int, motd: str, duration: int = 30) -> bool:
    """Store the MOTD and duration for a server."""
    db_path = Path(Config.DATABASE_PATH)

    # First ensure the motd and motd_duration columns exist
    async with aiosqlite.connect(db_path) as db:
        try:
            async with db.execute("PRAGMA table_info('ark_servers')") as cursor:
                cols = [row[1] async for row in cursor]
            if "motd" not in cols:
                await db.execute("ALTER TABLE ark_servers ADD COLUMN motd TEXT")
            if "motd_duration" not in cols:
                await db.execute(
                    "ALTER TABLE ark_servers ADD COLUMN motd_duration INTEGER DEFAULT 30"
                )
            await db.commit()
        except Exception:
            pass

        await db.execute(
            "UPDATE ark_servers SET motd = ?, motd_duration = ? WHERE guild_id = ? AND rcon_port = ?",
            (motd, duration, guild_id, rcon_port),
        )
        await db.commit()
        return True


# =============================================================================
# Server Path Helper Functions (Self-Hosted Only)
# =============================================================================


def get_server_ini_path(server_path: str) -> Optional[Path]:
    """Get the GameUserSettings.ini path for a server.

    Args:
        server_path: Root installation path of the ARK server

    Returns:
        Path to GameUserSettings.ini or None if not found
    """
    if not server_path:
        return None

    ini_path = (
        Path(server_path)
        / "ShooterGame"
        / "Saved"
        / "Config"
        / "WindowsServer"
        / "GameUserSettings.ini"
    )
    return ini_path if ini_path.exists() else None


def get_server_log_path(server_path: str) -> Optional[Path]:
    """Get the ShooterGame.log path for a server.

    Args:
        server_path: Root installation path of the ARK server

    Returns:
        Path to ShooterGame.log or None if not found
    """
    if not server_path:
        return None

    log_path = Path(server_path) / "ShooterGame" / "Saved" / "Logs" / "ShooterGame.log"
    return log_path if log_path.exists() else None


def get_server_game_ini_path(server_path: str) -> Optional[Path]:
    """Get the Game.ini path for a server.

    Args:
        server_path: Root installation path of the ARK server

    Returns:
        Path to Game.ini or None if not found
    """
    if not server_path:
        return None

    ini_path = Path(server_path) / "ShooterGame" / "Saved" / "Config" / "WindowsServer" / "Game.ini"
    return ini_path if ini_path.exists() else None


async def get_server_path(guild_id: int, rcon_port: int) -> Optional[str]:
    """Get the server_path for a specific server.

    Args:
        guild_id: Discord guild ID
        rcon_port: Server's RCON port

    Returns:
        Server installation path or None
    """
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT server_path FROM ark_servers WHERE guild_id = ? AND rcon_port = ?",
            (guild_id, rcon_port),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else None


# =============================================================================
# Crash Event Tracking (Self-Hosted Only)
# =============================================================================


async def _ensure_crash_events_table():
    """Ensure the crash_events table exists."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS crash_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                rcon_port INTEGER NOT NULL,
                crash_time TIMESTAMP NOT NULL,
                log_snippet TEXT,
                possible_cause TEXT,
                errors TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create index for faster queries
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_crash_events_guild_server 
            ON crash_events(guild_id, server_name, crash_time DESC)
        """
        )

        await db.commit()


async def record_crash_event(
    guild_id: int,
    server_name: str,
    rcon_port: int,
    crash_time: datetime,
    log_snippet: str = "",
    possible_cause: str = "Unknown",
    errors: str = "",
) -> bool:
    """Record a server crash event.

    Args:
        guild_id: Discord guild ID
        server_name: Name of the server that crashed
        rcon_port: Server's RCON port
        crash_time: When the crash was detected
        log_snippet: Tail of the log file at crash time
        possible_cause: Detected cause category
        errors: Error messages extracted from log

    Returns:
        True if recorded successfully
    """
    await _ensure_crash_events_table()
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO crash_events 
               (guild_id, server_name, rcon_port, crash_time, log_snippet, possible_cause, errors)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (guild_id, server_name, rcon_port, crash_time, log_snippet, possible_cause, errors),
        )
        await db.commit()
        return True


async def get_crash_history(
    guild_id: int, server_name: Optional[str] = None, days: int = 7, limit: int = 50
) -> List[dict]:
    """Get crash history for a guild's servers.

    Args:
        guild_id: Discord guild ID
        server_name: Optional filter by server name
        days: Number of days to look back
        limit: Maximum number of results

    Returns:
        List of crash event dictionaries
    """
    from datetime import datetime, timedelta

    await _ensure_crash_events_table()
    db_path = Path(Config.DATABASE_PATH)

    cutoff = datetime.now() - timedelta(days=days)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        if server_name:
            async with db.execute(
                """SELECT * FROM crash_events 
                   WHERE guild_id = ? AND server_name = ? AND crash_time > ?
                   ORDER BY crash_time DESC LIMIT ?""",
                (guild_id, server_name, cutoff, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        else:
            async with db.execute(
                """SELECT * FROM crash_events 
                   WHERE guild_id = ? AND crash_time > ?
                   ORDER BY crash_time DESC LIMIT ?""",
                (guild_id, cutoff, limit),
            ) as cursor:
                rows = await cursor.fetchall()

        return [dict(row) for row in rows]


async def get_latest_crash(guild_id: int, server_name: str) -> Optional[dict]:
    """Get the most recent crash for a specific server.

    Args:
        guild_id: Discord guild ID
        server_name: Server name

    Returns:
        Crash event dictionary or None
    """
    await _ensure_crash_events_table()
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """SELECT * FROM crash_events 
               WHERE guild_id = ? AND server_name = ?
               ORDER BY crash_time DESC LIMIT 1""",
            (guild_id, server_name),
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_crash_stats(guild_id: int, days: int = 30) -> Dict[str, dict]:
    """Get crash statistics by server.

    Args:
        guild_id: Discord guild ID
        days: Number of days to analyze

    Returns:
        Dictionary of server_name -> {count, most_common_cause, last_crash}
    """
    from datetime import datetime, timedelta
    from collections import Counter

    await _ensure_crash_events_table()
    db_path = Path(Config.DATABASE_PATH)

    cutoff = datetime.now() - timedelta(days=days)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            """SELECT server_name, possible_cause, crash_time FROM crash_events 
               WHERE guild_id = ? AND crash_time > ?
               ORDER BY crash_time DESC""",
            (guild_id, cutoff),
        ) as cursor:
            rows = await cursor.fetchall()

    stats: Dict[str, dict] = {}

    for row in rows:
        name = row["server_name"]
        if name not in stats:
            stats[name] = {"count": 0, "causes": [], "last_crash": row["crash_time"]}
        stats[name]["count"] += 1
        stats[name]["causes"].append(row["possible_cause"])

    # Calculate most common cause for each server
    for name in stats:
        cause_counts = Counter(stats[name]["causes"])
        stats[name]["most_common_cause"] = (
            cause_counts.most_common(1)[0][0] if cause_counts else "Unknown"
        )
        del stats[name]["causes"]  # Remove raw list

    return stats


async def get_mod_embed_channel_id(guild_id: int) -> Optional[int]:
    """Get the mod channel ID for a guild."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT mod_channel_id FROM server_configs WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] else None


async def set_mod_embed_channel_id(guild_id: int, channel_id: int) -> bool:
    """Set the mod channel ID for a guild."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO server_configs (guild_id, mod_channel_id) 
               VALUES (?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET mod_channel_id = ?, updated_at = CURRENT_TIMESTAMP""",
            (guild_id, channel_id, channel_id),
        )
        await db.commit()
    return True


async def disable_servers_beyond_limit(guild_id: int, limit: int, reason: str = "tier_limit") -> List[str]:
    """Disable servers beyond the specified limit for a guild.
    
    Keeps the oldest servers (lowest IDs) enabled, disables the rest.
    
    Args:
        guild_id: The Discord guild ID
        limit: Maximum number of servers to keep enabled
        reason: The reason for disabling ('tier_limit' or 'manual')
    
    Returns:
        List of server names that were disabled
    """
    db_path = Path(Config.DATABASE_PATH)
    
    # Get all enabled servers ordered by ID (oldest first)
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """SELECT id, name FROM ark_servers 
               WHERE guild_id = ? AND enabled = 1 
               ORDER BY id ASC""",
            (guild_id,)
        )
        servers = await cursor.fetchall()
    
    if len(servers) <= limit:
        return []  # No servers need to be disabled
    
    # Disable servers beyond the limit
    disabled_names = []
    servers_to_disable = servers[limit:]  # Skip first N, disable the rest
    
    async with aiosqlite.connect(db_path) as db:
        for server_id, server_name in servers_to_disable:
            await db.execute(
                "UPDATE ark_servers SET enabled = 0, disabled_reason = ? WHERE id = ?",
                (reason, server_id)
            )
            disabled_names.append(server_name)
        await db.commit()
    
    return disabled_names


async def enable_server(server_id: int) -> bool:
    """Re-enable a previously disabled server.
    
    Args:
        server_id: The server ID to enable
    
    Returns:
        True if successful, False if server not found
    """
    db_path = Path(Config.DATABASE_PATH)
    
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "UPDATE ark_servers SET enabled = 1, disabled_reason = NULL WHERE id = ?",
            (server_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def enable_all_servers(guild_id: int) -> int:
    """Re-enable all servers for a guild (e.g., when upgrading to premium).
    
    Args:
        guild_id: The Discord guild ID
    
    Returns:
        Number of servers re-enabled
    """
    db_path = Path(Config.DATABASE_PATH)
    
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "UPDATE ark_servers SET enabled = 1, disabled_reason = NULL WHERE guild_id = ?",
            (guild_id,)
        )
        await db.commit()
        return cursor.rowcount


async def enable_tier_limited_servers(guild_id: int) -> List[str]:
    """Re-enable servers that were disabled due to a subscription tier limit.

    Only affects servers with disabled_reason='tier_limit'. Servers disabled
    manually by the admin (disabled_reason IS NULL) are left untouched.

    Returns:
        List of server names that were re-enabled.
    """
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        # Fetch names of servers that will be re-enabled
        async with db.execute(
            "SELECT name FROM ark_servers WHERE guild_id = ? AND disabled_reason = 'tier_limit'",
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        reenabled_names = [row["name"] for row in rows]

        if reenabled_names:
            await db.execute(
                "UPDATE ark_servers SET enabled = 1, disabled_reason = NULL "
                "WHERE guild_id = ? AND disabled_reason = 'tier_limit'",
                (guild_id,),
            )
            await db.commit()
            logger.info(
                f"Subscription upgrade: re-enabled {len(reenabled_names)} servers for guild {guild_id}: "
                f"{reenabled_names}"
            )

    return reenabled_names


# ---------------------------------------------------------------------------
# Guild Lifecycle Management (soft delete on bot kick)
# ---------------------------------------------------------------------------

async def mark_guild_inactive(guild_id: int) -> bool:
    """Mark a guild as inactive when the bot is removed.
    
    Performs a soft delete - data is preserved but guild is marked inactive.
    
    Args:
        guild_id: The Discord guild ID
        
    Returns:
        True if successfully marked inactive, False otherwise
    """
    db_path = Path(Config.DATABASE_PATH)
    
    async with aiosqlite.connect(db_path) as db:
        try:
            await db.execute(
                """
                UPDATE guilds 
                SET is_active = 0, left_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
            await db.commit()
            logger.info(f"Guild {guild_id} marked as inactive (soft delete)")
            return True
        except Exception as e:
            logger.error(f"Failed to mark guild {guild_id} inactive: {e}")
            return False


async def mark_guild_active(guild_id: int) -> bool:
    """Mark a guild as active when the bot rejoins.
    
    Args:
        guild_id: The Discord guild ID
        
    Returns:
        True if successfully marked active, False otherwise
    """
    db_path = Path(Config.DATABASE_PATH)
    
    async with aiosqlite.connect(db_path) as db:
        try:
            await db.execute(
                """
                UPDATE guilds 
                SET is_active = 1, left_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
            await db.commit()
            logger.info(f"Guild {guild_id} marked as active (rejoined)")
            return True
        except Exception as e:
            logger.error(f"Failed to mark guild {guild_id} active: {e}")
            return False


async def get_active_guilds() -> List[Dict[str, Any]]:
    """Get all active guilds.
    
    Returns:
        List of active guild records
    """
    db_path = Path(Config.DATABASE_PATH)
    
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM guilds WHERE is_active = 1 ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_guild_stats() -> Dict[str, Any]:
    """Get aggregate guild statistics for dashboard.
    
    Returns:
        Dict with total_guilds, active_guilds, inactive_guilds counts
    """
    db_path = Path(Config.DATABASE_PATH)
    
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT is_active, COUNT(*) as count FROM guilds GROUP BY is_active"
        ) as cursor:
            rows = await cursor.fetchall()
        
        stats = {"total_guilds": 0, "active_guilds": 0, "inactive_guilds": 0}
        for row in rows:
            stats["total_guilds"] += row["count"]
            if row["is_active"] == 1:
                stats["active_guilds"] = row["count"]
            else:
                stats["inactive_guilds"] = row["count"]
        
        if not rows:
            stats["total_guilds"] = 0
            
        return stats
