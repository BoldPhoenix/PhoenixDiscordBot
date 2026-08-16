"""
Database initialization module.
Creates the SQLite database and tables.

Timestamp convention:
    All timestamps should use datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    for consistency with SQLite CURRENT_TIMESTAMP format.  Avoid .isoformat() which
    produces a 'T' separator that breaks lexicographic comparisons against
    CURRENT_TIMESTAMP-generated values (space separator).
"""

import aiosqlite
import logging
from pathlib import Path

from bot.utils.config import Config
from bot.database import players_db
from bot.database import server_config_db
from bot.database import games_db
from bot.database import maintenance_db
from bot.database import subscription_db
from bot.database import kit_db

logger = logging.getLogger("Database")


async def initialize_database() -> None:
    """Initialize the database with required tables."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        # Guild registry (multi-tenant core)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS guilds (
                guild_id INTEGER PRIMARY KEY,
                guild_name TEXT,
                is_active INTEGER DEFAULT 1,
                left_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Remote agents (WebSocket agent management)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS remote_agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                agent_id TEXT NOT NULL,
                agent_ip TEXT NOT NULL,
                agent_port INTEGER NOT NULL,
                auth_key TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                last_connected TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, agent_id)
            )
        """
        )

        # ARK servers (Pi 5 schema — matches production table name)
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
                chat_enabled INTEGER DEFAULT 1,
                log_path TEXT,
                server_path TEXT,
                cluster_id TEXT,
                cluster_path TEXT,
                hosting_type TEXT DEFAULT 'self_hosted',
                latest_build_id INTEGER,
                installed_build_id INTEGER,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER NOT NULL DEFAULT 0,
                discord_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                phoenix_coins INTEGER DEFAULT 0,
                steam_id TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS store_items (
                guild_id INTEGER NOT NULL DEFAULT 0,
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                cost INTEGER NOT NULL,
                ark_command TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                enabled BOOLEAN DEFAULT 1,
                supports_quality INTEGER DEFAULT 0,
                allow_blueprint_select INTEGER DEFAULT 0,
                purchase_limit INTEGER DEFAULT 0,
                is_pack INTEGER DEFAULT 0,
                pack_contents TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Migrate existing store_items table to add new columns if missing
        for col, definition in [
            ("supports_quality", "INTEGER DEFAULT 0"),
            ("allow_blueprint_select", "INTEGER DEFAULT 0"),
            ("is_pack", "INTEGER DEFAULT 0"),
            ("pack_contents", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE store_items ADD COLUMN {col} {definition}")
            except Exception as e:
                err_msg = str(e).lower()
                if "duplicate column" in err_msg or "already exists" in err_msg:
                    pass  # Column already exists
                else:
                    logger.warning("Unexpected migration error adding %s to store_items: %s", col, e)

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                guild_id INTEGER NOT NULL DEFAULT 0,
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                cost INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                server_name TEXT,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (discord_id) REFERENCES users(discord_id),
                FOREIGN KEY (item_id) REFERENCES store_items(item_id)
            )
        """
        )

        # Migrate existing transactions table
        try:
            await db.execute("ALTER TABLE transactions ADD COLUMN quantity INTEGER DEFAULT 1")
        except Exception as e:
            err_msg = str(e).lower()
            if "duplicate column" in err_msg or "already exists" in err_msg:
                pass  # Column already exists
            else:
                logger.warning("Unexpected migration error adding quantity to transactions: %s", e)

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS player_sessions (
                guild_id INTEGER NOT NULL DEFAULT 0,
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                eos_id TEXT,
                discord_id INTEGER,
                steam_id TEXT,
                character_name TEXT,
                server_name TEXT NOT NULL,
                join_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                leave_time TIMESTAMP
            )
            """
        )

        # Migration: add eos_id column if missing
        try:
            await db.execute("ALTER TABLE player_sessions ADD COLUMN eos_id TEXT")
        except Exception as e:
            err_msg = str(e).lower()
            if "duplicate column" in err_msg or "already exists" in err_msg:
                pass  # Column already exists
            else:
                logger.warning("Unexpected migration error adding eos_id to player_sessions: %s", e)

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS coin_transactions (
                guild_id INTEGER NOT NULL DEFAULT 0,
                coin_transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                eos_id TEXT,
                discord_id INTEGER,
                amount INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                reason TEXT,
                admin_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # --- Economy tables ---
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_settings (
                guild_id INTEGER PRIMARY KEY,
                base_payday_amount INTEGER DEFAULT 100,
                currency_name TEXT DEFAULT 'Phoenix Coins',
                currency_icon TEXT DEFAULT '🪙',
                economy_log_channel_id INTEGER,
                payday_enabled INTEGER DEFAULT 1,
                payday_interval_hours INTEGER DEFAULT 24,
                payday_eligibility_role_id INTEGER,
                payday_schedule_type TEXT DEFAULT 'daily',
                payday_day_of_week INTEGER DEFAULT 0,
                payday_time TEXT DEFAULT '12:00',
                payday_active_only INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                role_id TEXT NOT NULL,
                role_name TEXT,
                bonus_amount INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, role_id)
            )
        """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS payday_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                discord_id INTEGER NOT NULL,
                eos_id TEXT,
                base_amount INTEGER NOT NULL,
                role_bonus INTEGER DEFAULT 0,
                total_amount INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # --- CurseForge mod cache ---
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS curseforge_mods (
                mod_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                summary TEXT,
                author TEXT,
                download_count INTEGER,
                thumbnail_url TEXT,
                date_modified TEXT,
                website_url TEXT,
                wiki_url TEXT,
                slug TEXT,
                is_available INTEGER DEFAULT 1,
                raw_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mod_name_search ON curseforge_mods(name COLLATE NOCASE)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mod_updated ON curseforge_mods(date_modified DESC)"
        )

        # --- INI Management tables ---
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS server_ini_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                file_name TEXT NOT NULL,
                section_name TEXT NOT NULL,
                key_name TEXT NOT NULL,
                key_value TEXT,
                value_type TEXT,
                description TEXT,
                is_modified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, server_name, file_name, section_name, key_name)
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ini_server ON server_ini_settings(guild_id, server_name)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ini_section ON server_ini_settings(section_name)"
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ini_pending_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                file_name TEXT NOT NULL,
                section_name TEXT NOT NULL,
                key_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT NOT NULL,
                queued_by INTEGER,
                queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                applied_at TIMESTAMP,
                UNIQUE(guild_id, server_name, file_name, section_name, key_name)
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_pending_ini_server ON ini_pending_changes(guild_id, server_name)"
        )

        # --- Shop tables ---
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS shop_config (
                guild_id INTEGER PRIMARY KEY,
                shop_enabled INTEGER DEFAULT 1,
                shop_channel_id INTEGER,
                log_channel_id INTEGER,
                items_per_page INTEGER DEFAULT 10,
                require_linked_account INTEGER DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS cart_items (
                cart_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                discord_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                quality INTEGER NOT NULL DEFAULT 1,
                blueprint INTEGER NOT NULL DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES store_items(item_id) ON DELETE CASCADE
            )
        """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                discord_user_id INTEGER NOT NULL,
                eos_id TEXT,
                server_name TEXT NOT NULL,
                item_blueprint TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                quality INTEGER DEFAULT 0,
                force_blueprint INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # --- Indexes for tables created above ---
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_sessions_guild_server ON player_sessions(guild_id, server_name)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_pending_deliveries_guild ON pending_deliveries(guild_id)"
        )

        await db.commit()
        logger.info("Database tables created successfully")

        # Migrations — add columns that may be missing from older installs
        migrations = [
            ("pending_deliveries", "eos_id", "ALTER TABLE pending_deliveries ADD COLUMN eos_id TEXT"),
            ("economy_settings", "payday_eligibility_role_id", "ALTER TABLE economy_settings ADD COLUMN payday_eligibility_role_id INTEGER"),
            ("economy_settings", "payday_schedule_type", "ALTER TABLE economy_settings ADD COLUMN payday_schedule_type TEXT DEFAULT 'daily'"),
            ("economy_settings", "payday_day_of_week", "ALTER TABLE economy_settings ADD COLUMN payday_day_of_week INTEGER DEFAULT 0"),
            ("economy_settings", "payday_time", "ALTER TABLE economy_settings ADD COLUMN payday_time TEXT DEFAULT '12:00'"),
            ("economy_settings", "payday_active_only", "ALTER TABLE economy_settings ADD COLUMN payday_active_only INTEGER DEFAULT 0"),
            ("ark_servers", "disabled_reason", "ALTER TABLE ark_servers ADD COLUMN disabled_reason TEXT"),
            ("guilds", "is_active", "ALTER TABLE guilds ADD COLUMN is_active INTEGER DEFAULT 1"),
            ("guilds", "left_at", "ALTER TABLE guilds ADD COLUMN left_at TIMESTAMP"),
        ]
        for table, column, sql in migrations:
            try:
                await db.execute(sql)
                await db.commit()
                logger.info(f"Migration applied: added {column} to {table}")
            except Exception as e:
                err_msg = str(e).lower()
                if "duplicate column" in err_msg or "already exists" in err_msg:
                    pass  # Column already exists — safe to ignore
                else:
                    logger.warning(
                        "Unexpected migration error adding %s to %s: %s",
                        column, table, e,
                    )

# Initialize players tables
    await players_db.init_players_tables()

    # Indexes for players table (created by players_db)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE INDEX IF NOT EXISTS idx_players_guild ON players(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_players_eos ON players(eos_id)")
        await db.commit()

    # Initialize server configuration tables
    await server_config_db.init_server_config_tables()

    # Initialize games tables
    await games_db.init_games_tables()

    # Initialize maintenance tables
    await maintenance_db.init_maintenance_tables()

    # Initialize subscription tables
    await subscription_db.init_subscription_tables()

    # Initialize kit tables
    await kit_db.init_kit_tables()

    logger.info("Database initialization complete")


async def add_sample_items() -> None:
    """Add sample store items for testing."""
    db_path = Path(Config.DATABASE_PATH)

    sample_items = [
        (
            "Advanced Rifle Bullet (100)",
            "100 Advanced Rifle Bullets",
            50,
            "GiveItemNumToPlayer {player_id} 246 100 0 false",
            "ammunition",
        ),
        (
            "Metal Foundation",
            "Metal Foundation for building",
            25,
            "GiveItemNumToPlayer {player_id} 379 1 0 false",
            "structures",
        ),
        (
            "Industrial Forge",
            "Industrial Forge",
            100,
            "GiveItemNumToPlayer {player_id} 238 1 0 false",
            "crafting",
        ),
        (
            "Tek Generator",
            "Tek Generator",
            250,
            "GiveItemNumToPlayer {player_id} 462 1 0 false",
            "tek",
        ),
        ("Cryopod", "Empty Cryopod", 75, "GiveItemNumToPlayer {player_id} 1 1 0 false", "utility"),
        (
            "Phoenix Coin",
            "Phoenix Coin currency",
            1,
            'GiveItemToPlayer {player_id} "/RiseofPhoenix/Coin/PrimalItemConsumable_PhoenixCoin.PrimalItemConsumable_PhoenixCoin" 1 0 0',
            "currency",
        ),
    ]

    async with aiosqlite.connect(db_path) as db:
        for item in sample_items:
            await db.execute(
                """
                INSERT OR IGNORE INTO store_items (name, description, cost, ark_command, category)
                VALUES (?, ?, ?, ?, ?)
                """,
                item,
            )
        await db.commit()
        logger.info(f"Added {len(sample_items)} sample items to store")


if __name__ == "__main__":
    import asyncio

    asyncio.run(initialize_database())
    asyncio.run(add_sample_items())
    print("Database initialization complete!")
