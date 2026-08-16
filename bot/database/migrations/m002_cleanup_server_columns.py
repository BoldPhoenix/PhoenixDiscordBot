"""
Migration m002_cleanup_server_columns.py
Remove unused columns from server_ark_servers table
"""

import sqlite3
import asyncio
from pathlib import Path
from bot.core.config import Config

async def run_migration():
    """Remove unused columns from server_ark_servers table"""
    db_path = Path(Config.DATABASE_PATH)
    
    async with sqlite3.connect(db_path) as db:
        # Create new table without unused columns
        await db.execute("""
            CREATE TABLE server_ark_servers_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                rcon_port INTEGER NOT NULL,
                rcon_password TEXT NOT NULL,
                max_players INTEGER DEFAULT 70,
                chat_enabled BOOLEAN DEFAULT 1,
                enabled BOOLEAN DEFAULT 1,
                voice_channel_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- Important fields to keep
                display_name TEXT,
                map_name TEXT,
                service_name TEXT,
                server_path TEXT,
                steamcmd_path TEXT,
                ark_appid INTEGER,
                log_path TEXT,
                ark_version TEXT,
                update_needed INTEGER DEFAULT 0,
                latest_ark_version TEXT,
                
                FOREIGN KEY (guild_id) REFERENCES server_configs(guild_id) ON DELETE CASCADE,
                UNIQUE(guild_id, name)
            )
        """)
        
        # Copy data from old table to new table
        await db.execute("""
            INSERT INTO server_ark_servers_new (
                id, guild_id, name, host, rcon_port, rcon_password, 
                max_players, chat_enabled, enabled, voice_channel_id, created_at,
                display_name, map_name, service_name, server_path, 
                steamcmd_path, ark_appid, log_path, ark_version, 
                update_needed, latest_ark_version
            )
            SELECT 
                id, guild_id, name, host, rcon_port, rcon_password,
                max_players, chat_enabled, enabled, voice_channel_id, created_at,
                display_name, map_name, service_name, server_path,
                steamcmd_path, ark_appid, log_path, ark_version,
                update_needed, latest_ark_version
            FROM server_ark_servers
        """)
        
        # Drop old table and rename new table
        await db.execute("DROP TABLE server_ark_servers")
        await db.execute("ALTER TABLE server_ark_servers_new RENAME TO server_ark_servers")
        
        await db.commit()
        print("✅ Migration m002: Removed unused columns from server_ark_servers")

if __name__ == "__main__":
    asyncio.run(run_migration())
