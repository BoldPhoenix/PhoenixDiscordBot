"""
Migration m003_rename_server_table.py
Rename server_ark_servers to ark_servers for cleaner schema
"""

import aiosqlite
import asyncio
from pathlib import Path
from bot.utils.config import Config


async def run_migration():
    """Rename server_ark_servers to ark_servers"""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        # Check if old table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='server_ark_servers'"
        )
        result = await cursor.fetchone()

        if result:
            # Rename the table
            await db.execute("ALTER TABLE server_ark_servers RENAME TO ark_servers")
            await db.commit()
            print("✅ Migration m003: Renamed server_ark_servers to ark_servers")
        else:
            # Check if new table already exists
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ark_servers'"
            )
            result = await cursor.fetchone()
            if result:
                print("ℹ️ Migration m003: ark_servers already exists, skipping")
            else:
                print("⚠️ Migration m003: No server table found to rename")


if __name__ == "__main__":
    asyncio.run(run_migration())
