"""
Database module for player linking and delivery queue.
Handles EOS ID mapping, PlayerID caching, and pending item deliveries.
"""

import aiosqlite
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

from bot.utils.config import Config

logger = logging.getLogger("PlayersDB")


async def init_players_tables():
    """Initialize players table with full multi-tenant schema matching production."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        # Players table — full schema matching Pi 5 production
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                guild_id INTEGER NOT NULL,
                discord_user_id INTEGER,
                eos_id TEXT,
                character_name TEXT,
                player_name TEXT,
                balance INTEGER DEFAULT 0,
                last_player_id INTEGER,
                last_seen_server TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                discord_username TEXT,
                discord_display_name TEXT,
                level INTEGER DEFAULT 0,
                last_server TEXT,
                last_seen_timestamp INTEGER,
                is_auto_linked INTEGER DEFAULT 0,
                specimen_id TEXT,
                last_seen TEXT,
                UNIQUE(guild_id, eos_id),
                UNIQUE(guild_id, discord_user_id)
            )
            """
        )

        # Migrate existing players table — add any missing columns
        migrations = [
            ("guild_id", "INTEGER NOT NULL DEFAULT 0"),
            ("character_name", "TEXT"),
            ("player_name", "TEXT"),
            ("level", "INTEGER DEFAULT 0"),
            ("balance", "INTEGER DEFAULT 0"),
            ("last_server", "TEXT"),
            ("last_seen_timestamp", "INTEGER"),
            ("specimen_id", "TEXT"),
            ("is_auto_linked", "INTEGER DEFAULT 0"),
            ("last_seen", "TEXT"),
            ("starting_balance_granted", "INTEGER DEFAULT 0"),
        ]
        for col, definition in migrations:
            try:
                await db.execute(f"ALTER TABLE players ADD COLUMN {col} {definition}")
            except Exception:
                pass  # Column already exists

        await db.commit()
        logger.info("Players tables initialized")


async def link_player(
    guild_id: int,
    discord_user_id: int,
    eos_id: str,
    discord_username: str = None,
    discord_display_name: str = None,
    specimen_id: str = None,
) -> bool:
    """Link a Discord user to an EOS ID and optionally specimen ID.
    
    Also backfills discord_user_id on any existing player_sessions for this EOS ID.
    Grants starting balance (1000 coins) for new links on premium/lifetime guilds.
    """
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            # Check if EOS ID is already linked to a different Discord user in this guild
            async with db.execute(
                "SELECT discord_user_id FROM players WHERE guild_id = ? AND eos_id = ? AND discord_user_id != ?",
                (guild_id, eos_id, discord_user_id),
            ) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    logger.warning(f"EOS ID {eos_id} already linked to Discord user {existing[0]}")
                    return False

            # Check if this Discord user has ever received starting balance
            async with db.execute(
                "SELECT starting_balance_granted FROM players WHERE guild_id = ? AND discord_user_id = ?",
                (guild_id, discord_user_id),
            ) as cursor:
                existing_player = await cursor.fetchone()
                already_granted = existing_player and existing_player[0] == 1
            
            # Only grant starting balance if never granted before AND guild is configured
            starting_balance = 0
            grant_flag = 0
            if not already_granted:
                from bot.database import server_config_db
                config = await server_config_db.get_server_config(guild_id)
                # Only grant starting balance if guild has been configured (config exists)
                if config:
                    starting_balance = config.get("shop_starting_balance", 1000)
                    grant_flag = 1

            now = datetime.utcnow().isoformat()
            await db.execute(
                """
                INSERT INTO players (guild_id, discord_user_id, discord_username, discord_display_name, eos_id, specimen_id, balance, starting_balance_granted, updated_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, discord_user_id) DO UPDATE SET
                    discord_username = excluded.discord_username,
                    discord_display_name = excluded.discord_display_name,
                    eos_id = excluded.eos_id,
                    specimen_id = COALESCE(excluded.specimen_id, specimen_id),
                    balance = players.balance + excluded.balance,
                    starting_balance_granted = CASE WHEN excluded.starting_balance_granted = 1 THEN 1 ELSE players.starting_balance_granted END,
                    updated_at = excluded.updated_at
            """,
                (
                    guild_id,
                    discord_user_id,
                    discord_username,
                    discord_display_name,
                    eos_id,
                    specimen_id,
                    starting_balance,
                    grant_flag,
                    now,
                    now,
                ),
            )
            
            # Backfill discord_id on existing sessions for this EOS ID (if table exists)
            try:
                await db.execute(
                    """
                    UPDATE player_sessions SET discord_id = ?
                    WHERE eos_id = ? AND discord_id IS NULL
                    """,
                    (discord_user_id, eos_id),
                )
            except Exception:
                pass  # player_sessions table may not exist yet
            
            await db.commit()
        logger.info(
            f"Linked Discord user {discord_user_id} to EOS {eos_id}"
            + (f" and specimen {specimen_id}" if specimen_id else "")
        )
        return True
    except Exception as e:
        logger.error(f"Error linking player: {e}")
        return False


async def get_player_by_discord_id(guild_id_or_user_id, discord_user_id=None) -> Optional[Dict[str, Any]]:
    """Get player info by Discord ID.
    Accepts both (discord_user_id,) and (guild_id, discord_user_id) call signatures.
    When guild_id is provided, filters by guild to return the correct tenant's record.
    """
    if discord_user_id is not None:
        actual_guild_id = guild_id_or_user_id
        actual_user_id = discord_user_id
    else:
        actual_guild_id = None
        actual_user_id = guild_id_or_user_id

    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if actual_guild_id is not None:
            sql = "SELECT * FROM players WHERE guild_id = ? AND discord_user_id = ?"
            params = (actual_guild_id, actual_user_id)
        else:
            sql = "SELECT * FROM players WHERE discord_user_id = ?"
            params = (actual_user_id,)
        async with db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_all_linked_players(guild_id: int = None) -> list[Dict[str, Any]]:
    """Get all linked players ordered by display name.

    Args:
        guild_id: Optional guild ID to filter by. When None, returns all players (backward compatible).
    """
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if guild_id is not None:
            sql = "SELECT * FROM players WHERE guild_id = ? ORDER BY discord_display_name"
            params = (guild_id,)
        else:
            sql = "SELECT * FROM players ORDER BY discord_display_name"
            params = ()
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def unlink_player_by_discord_id(guild_id: int, discord_user_id: int) -> bool:
    """Unlink a player by Discord ID within a guild.
    
    This clears the EOS ID but KEEPS the player record and balance intact.
    Balance is tied to the Discord account, not the EOS ID.
    """
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE players SET eos_id = NULL, specimen_id = NULL, updated_at = ? WHERE guild_id = ? AND discord_user_id = ?",
                (datetime.utcnow().isoformat(), guild_id, discord_user_id),
            )
            await db.commit()
        logger.info(f"Unlinked player with Discord ID {discord_user_id} in guild {guild_id} (balance preserved)")
        return True
    except Exception as e:
        logger.error(f"Error unlinking player: {e}")
        return False


async def unlink_player_by_eos_id(guild_id: int, eos_id: str) -> bool:
    """Unlink a player by EOS ID within a guild.
    
    This clears the EOS ID but KEEPS the player record and balance intact.
    Balance is tied to the Discord account, not the EOS ID.
    """
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE players SET eos_id = NULL, specimen_id = NULL, updated_at = ? WHERE guild_id = ? AND eos_id = ?",
                (datetime.utcnow().isoformat(), guild_id, eos_id),
            )
            await db.commit()
        logger.info(f"Unlinked player with EOS ID {eos_id} in guild {guild_id} (balance preserved)")
        return True
    except Exception as e:
        logger.error(f"Error unlinking player: {e}")
        return False


async def get_player_by_eos_id(eos_id: str, guild_id: int = None) -> Optional[Dict[str, Any]]:
    """Get player info by EOS ID.

    Args:
        eos_id: Player's EOS ID.
        guild_id: Optional guild ID to filter by. When None, returns first match across all guilds.
    """
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if guild_id is not None:
            sql = "SELECT * FROM players WHERE eos_id = ? AND guild_id = ?"
            params = (eos_id, guild_id)
        else:
            sql = "SELECT * FROM players WHERE eos_id = ?"
            params = (eos_id,)
        async with db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_player_id(discord_user_id: int, player_id: int, server_name: str):
    """Update last known PlayerID and server."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        now = datetime.utcnow().isoformat()
        await db.execute(
            """
            UPDATE players
            SET last_player_id = ?, last_seen_server = ?, updated_at = ?
            WHERE discord_user_id = ?
        """,
            (player_id, server_name, now, discord_user_id),
        )
        await db.commit()
    logger.debug(f"Updated player {discord_user_id} with PlayerID {player_id} on {server_name}")


async def update_player_last_seen(
    eos_id: str, server_name: str, character_name: str = None, player_id: int = None
) -> bool:
    """
    Update player's last seen server, timestamp, and in-game player ID.
    Sets both last_server and last_seen_server (used by shop delivery).
    player_id is the numeric specimen ID from ListPlayers (used for GiveItemToPlayer).
    """
    try:
        db_path = Path(Config.DATABASE_PATH)
        now = datetime.utcnow().isoformat()
        timestamp = int(datetime.utcnow().timestamp())

        async with aiosqlite.connect(db_path) as db:
            # Always update both last_server and last_seen_server, plus timestamp
            if character_name and player_id is not None:
                await db.execute(
                    """
                    UPDATE players
                    SET last_server = ?, last_seen_server = ?, last_seen_timestamp = ?,
                        last_player_id = ?, character_name = ?, updated_at = ?
                    WHERE eos_id = ?
                    """,
                    (server_name, server_name, timestamp, player_id, character_name, now, eos_id),
                )
            elif character_name:
                await db.execute(
                    """
                    UPDATE players
                    SET last_server = ?, last_seen_server = ?, last_seen_timestamp = ?,
                        character_name = ?, updated_at = ?
                    WHERE eos_id = ?
                    """,
                    (server_name, server_name, timestamp, character_name, now, eos_id),
                )
            elif player_id is not None:
                await db.execute(
                    """
                    UPDATE players
                    SET last_server = ?, last_seen_server = ?, last_seen_timestamp = ?,
                        last_player_id = ?, updated_at = ?
                    WHERE eos_id = ?
                    """,
                    (server_name, server_name, timestamp, player_id, now, eos_id),
                )
            else:
                await db.execute(
                    """
                    UPDATE players
                    SET last_server = ?, last_seen_server = ?, last_seen_timestamp = ?,
                        updated_at = ?
                    WHERE eos_id = ?
                    """,
                    (server_name, server_name, timestamp, now, eos_id),
                )
            await db.commit()

        logger.debug(
            f"Updated last seen for EOS {eos_id[:8]} on {server_name}"
            + (f" player_id={player_id}" if player_id is not None else "")
        )
        return True
    except Exception as e:
        logger.error(f"Error updating player last seen: {e}")
        return False


async def get_player_last_seen(discord_user_id: int = None, eos_id: str = None) -> Optional[Dict]:
    """
    Get player's last seen information.
    Can search by discord_user_id or eos_id.
    
    Returns dict with: server, timestamp, character_name, or None if not found.
    """
    if not discord_user_id and not eos_id:
        return None

    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            if discord_user_id:
                query = """
                    SELECT last_server, last_seen_timestamp, character_name, 
                           player_name, eos_id
                    FROM players 
                    WHERE discord_user_id = ?
                """
                params = (discord_user_id,)
            else:
                query = """
                    SELECT last_server, last_seen_timestamp, character_name,
                           player_name, eos_id, discord_user_id
                    FROM players 
                    WHERE eos_id = ?
                """
                params = (eos_id,)

            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None
    except Exception as e:
        logger.error(f"Error getting player last seen: {e}")
        return None


async def update_player_names(
    discord_user_id: int, discord_username: str, discord_display_name: str
):
    """Update Discord username and display name for a player."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        now = datetime.utcnow().isoformat()
        await db.execute(
            """
            UPDATE players
            SET discord_username = ?, discord_display_name = ?, updated_at = ?
            WHERE discord_user_id = ?
        """,
            (discord_username, discord_display_name, now, discord_user_id),
        )
        await db.commit()
    logger.debug(
        f"Updated names for player {discord_user_id}: {discord_username} / {discord_display_name}"
    )


async def update_specimen_id(discord_user_id: int, specimen_id: str) -> bool:
    """Update specimen ID for a player."""
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            now = datetime.utcnow().isoformat()
            await db.execute(
                """
                UPDATE players
                SET specimen_id = ?, updated_at = ?
                WHERE discord_user_id = ?
            """,
                (specimen_id, now, discord_user_id),
            )
            await db.commit()
        logger.info(f"Updated specimen ID for player {discord_user_id}: {specimen_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating specimen ID: {e}")
        return False


async def sync_specimen_id_from_rcon(
    rcon_client, eos_id: str, discord_user_id: int = None
) -> Optional[str]:
    """
    Fetch specimen ID from RCON using GetPlayerIDForEOSID command.

    Args:
        rcon_client: Connected RCON client
        eos_id: Player's EOS ID
        discord_user_id: Optional Discord ID to update in database

    Returns:
        Specimen ID as string if successful, None otherwise
    """
    try:
        # Execute RCON command
        command = f"GetPlayerIDForEOSID {eos_id}"
        response = await rcon_client.execute_command(command)

        # Parse response - should be numeric specimen ID
        specimen_id = response.strip()
        if not specimen_id.isdigit():
            logger.warning(f"GetPlayerIDForEOSID returned non-numeric response: {response}")
            return None

        logger.info(f"Retrieved specimen ID {specimen_id} for EOS {eos_id}")

        # Update database if discord_user_id provided
        if discord_user_id:
            await update_specimen_id(discord_user_id, specimen_id)

        return specimen_id
    except Exception as e:
        logger.error(f"Error fetching specimen ID for {eos_id}: {e}")
        return None


async def queue_delivery(
    discord_user_id: int,
    server_name: str,
    item_blueprint: str,
    quantity: int,
    quality: int = 0,
    force_blueprint: int = 0,
) -> bool:
    """Queue an item delivery for when player comes online."""
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            now = datetime.utcnow().isoformat()
            await db.execute(
                """
                INSERT INTO pending_deliveries 
                (discord_user_id, server_name, item_blueprint, quantity, quality, force_blueprint, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    discord_user_id,
                    server_name,
                    item_blueprint,
                    quantity,
                    quality,
                    force_blueprint,
                    now,
                ),
            )
            await db.commit()
        logger.info(f"Queued delivery for user {discord_user_id} on {server_name}")
        return True
    except Exception as e:
        logger.error(f"Error queuing delivery: {e}")
        return False


async def get_pending_deliveries(discord_user_id: int, server_name: str) -> List[Dict[str, Any]]:
    """Get pending deliveries for a player on a server."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM pending_deliveries
            WHERE discord_user_id = ? AND server_name = ?
            ORDER BY created_at ASC
        """,
            (discord_user_id, server_name),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_all_pending_deliveries(server_name: str) -> List[Dict[str, Any]]:
    """Get all pending deliveries for a server."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM pending_deliveries
            WHERE server_name = ?
            ORDER BY created_at ASC
        """,
            (server_name,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def clear_delivery(delivery_id: int):
    """Remove a delivery from the queue."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM pending_deliveries WHERE id = ?", (delivery_id,))
        await db.commit()
    logger.debug(f"Cleared delivery {delivery_id}")


async def get_all_linked_players(guild_id: int = None) -> List[Dict[str, Any]]:
    """Get all players with linked EOS IDs.

    Args:
        guild_id: Optional guild ID to filter by. When None, returns all players (backward compatible).
    """
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if guild_id is not None:
            sql = "SELECT * FROM players WHERE guild_id = ? ORDER BY updated_at DESC"
            params = (guild_id,)
        else:
            sql = "SELECT * FROM players ORDER BY updated_at DESC"
            params = ()
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def cache_player(
    eos_id: str,
    character_name: str = None,
    player_name: str = None,
    level: int = 0,
    last_server: str = None,
    discord_user_id: int = None,
) -> bool:
    """
    Cache/update player information from RCON or save files.
    If player exists, updates their info. If new, creates entry.

    Args:
        eos_id: Player's EOS ID (required)
        character_name: In-game character name
        player_name: Platform player name
        level: Character level
        last_server: Server name where last seen
        discord_user_id: Optional Discord ID if already linked

    Returns:
        True if successful
    """
    try:
        import time

        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            now = datetime.utcnow().isoformat()
            timestamp = int(time.time())

            # Check if player exists
            async with db.execute(
                "SELECT discord_user_id, is_auto_linked FROM players WHERE eos_id = ?", (eos_id,)
            ) as cursor:
                existing = await cursor.fetchone()

            if existing:
                # Update existing player
                await db.execute(
                    """
                    UPDATE players SET
                        character_name = COALESCE(?, character_name),
                        player_name = COALESCE(?, player_name),
                        level = COALESCE(?, level),
                        last_server = COALESCE(?, last_server),
                        last_seen_timestamp = ?,
                        updated_at = ?
                    WHERE eos_id = ?
                """,
                    (character_name, player_name, level, last_server, timestamp, now, eos_id),
                )
            else:
                # Insert new player (not linked to Discord yet)
                await db.execute(
                    """
                    INSERT INTO players (
                        eos_id, character_name, player_name, level,
                        last_server, last_seen_timestamp, updated_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (eos_id, character_name, player_name, level, last_server, timestamp, now, now),
                )

            await db.commit()
        return True
    except Exception as e:
        logger.error(f"Error caching player {eos_id}: {e}")
        return False


async def get_cached_players(days_since_seen: int = 90, min_level: int = 0) -> List[Dict[str, Any]]:
    """
    Get linked players for dropdowns.

    Notes:
    - The current `players` schema tracks `discord_user_id`, `discord_display_name`, `eos_id`,
      and optional `last_seen_server` / `last_player_id` with `updated_at` timestamps.
    - Older fields like `level` or `last_seen_timestamp` are not present; this function
      returns the available columns and leaves non-existent fields out.

    Args:
        days_since_seen: Ignored for now (kept for API compatibility)
        min_level: Ignored (kept for API compatibility)

    Returns:
        List of player dictionaries from `players` table ordered by most recently updated.
    """
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        # Only return players who have linked a Discord account (discord_user_id present)
        async with db.execute(
            """
            SELECT discord_user_id, discord_username, discord_display_name,
                   eos_id, last_player_id, last_seen_server, updated_at, created_at
            FROM players
            WHERE discord_user_id IS NOT NULL
            ORDER BY datetime(updated_at) DESC
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_linked_players() -> List[Dict[str, Any]]:
    """Return all players that have linked their Discord (discord_user_id IS NOT NULL)."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT discord_user_id, discord_username, discord_display_name,
                   eos_id, last_player_id, last_seen_server, updated_at, created_at
            FROM players
            WHERE discord_user_id IS NOT NULL
            ORDER BY datetime(updated_at) DESC
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_linked_players_for_guild(guild_id: int) -> List[Dict[str, Any]]:
    """Return all players in a guild that have linked their Discord account."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT discord_user_id, discord_username, discord_display_name,
                   eos_id, specimen_id, character_name, last_player_id,
                   balance, last_seen_server, updated_at
            FROM players
            WHERE guild_id = ? AND discord_user_id IS NOT NULL
            ORDER BY discord_username ASC
            """,
            (guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def upsert_player_seen(
    eos_id: str,
    character_name: Optional[str],
    player_name: Optional[str],
    server_name: Optional[str],
    seen_timestamp: Optional[int],
) -> bool:
    """
    Upsert a player record when encountered via RCON scan.

    - Ensures `eos_id` exists in `players` table
    - Updates `last_seen_server` and `updated_at`
    - Stores latest known `last_player_id` only when available via other flows
    - Does not require the player to be Discord-linked yet
    """
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            now_iso = datetime.utcnow().isoformat()
            # Insert stub row if eos_id not present, with NULL discord_user_id
            await db.execute(
                """
                INSERT INTO players (discord_user_id, discord_username, discord_display_name, eos_id, last_seen_server, updated_at, created_at)
                VALUES (NULL, NULL, NULL, ?, ?, ?, ?)
                ON CONFLICT(eos_id) DO UPDATE SET
                    last_seen_server = excluded.last_seen_server,
                    updated_at = excluded.updated_at
                """,
                (eos_id, server_name, now_iso, now_iso),
            )
            await db.commit()
        logger.debug(f"Upserted seen player eos={eos_id} server={server_name}")
        return True
    except Exception as e:
        logger.error(f"Error upserting seen player eos={eos_id}: {e}")
        return False


async def purge_inactive_players(guild_id: int, days: int = 90) -> int:
    """
    Purge players not seen in the last `days` days.

    - Uses `updated_at` as last activity indicator
    - Keeps Discord-linked players regardless (safety) unless their `updated_at` also exceeds cutoff
    Returns number of rows deleted.
    """
    try:
        import time

        cutoff_dt = datetime.utcfromtimestamp(int(time.time()) - days * 24 * 60 * 60)
        cutoff_iso = cutoff_dt.isoformat()
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            # Delete rows where not linked OR linked but stale
            # We will be conservative: delete rows where updated_at < cutoff and discord_user_id IS NULL
            cur = await db.execute(
                """
                DELETE FROM players
                WHERE guild_id = ? AND updated_at < ? AND discord_user_id IS NULL
                """,
                (guild_id, cutoff_iso),
            )
            await db.commit()
            count = cur.rowcount or 0
        if count:
            logger.info(f"Purged {count} inactive unlinked players (>{days}d)")
        return count
    except Exception as e:
        logger.error(f"Error purging inactive players: {e}")
        return 0


async def search_players_by_name(
    search_term: str, days_since_seen: int = 90
) -> List[Dict[str, Any]]:
    """
    Search for players by character or player name.

    Args:
        search_term: Name to search for (case insensitive)
        days_since_seen: Only search players seen within this many days

    Returns:
        List of matching player dictionaries
    """
    import time

    db_path = Path(Config.DATABASE_PATH)
    cutoff_timestamp = int(time.time()) - (days_since_seen * 24 * 60 * 60)
    search_pattern = f"%{search_term}%"

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM players
            WHERE (last_seen_timestamp IS NULL OR last_seen_timestamp >= ?)
            AND (character_name LIKE ? OR player_name LIKE ?)
            ORDER BY last_seen_timestamp DESC, level DESC
        """,
            (cutoff_timestamp, search_pattern, search_pattern),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def auto_link_by_name(guild, days_since_seen: int = 90) -> List[Dict[str, Any]]:
    """
    Automatically link players to Discord accounts based on name matching.
    Only links if there's a 100% confident match.

    Args:
        guild: Discord guild object to search members
        days_since_seen: Only consider players seen within this many days

    Returns:
        List of auto-linked player records
    """
    import time
    from difflib import SequenceMatcher

    db_path = Path(Config.DATABASE_PATH)
    cutoff_timestamp = int(time.time()) - (days_since_seen * 24 * 60 * 60)
    linked = []

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # Get unlinked players seen recently
            async with db.execute(
                """
                SELECT * FROM players
                WHERE discord_user_id IS NULL
                AND (last_seen_timestamp IS NULL OR last_seen_timestamp >= ?)
                AND (character_name IS NOT NULL OR player_name IS NOT NULL)
            """,
                (cutoff_timestamp,),
            ) as cursor:
                unlinked_players = await cursor.fetchall()

            now = datetime.utcnow().isoformat()

            for player in unlinked_players:
                char_name = (player["character_name"] or "").lower().strip()
                plyr_name = (player["player_name"] or "").lower().strip()

                if not char_name and not plyr_name:
                    continue

                # Try to find matching Discord member
                best_match = None
                best_score = 0.0

                for member in guild.members:
                    if member.bot:
                        continue

                    display_name = member.display_name.lower().strip()
                    username = member.name.lower().strip()

                    # Exact match is 100% confident
                    if char_name and (char_name == display_name or char_name == username):
                        best_match = member
                        best_score = 1.0
                        break
                    if plyr_name and (plyr_name == display_name or plyr_name == username):
                        best_match = member
                        best_score = 1.0
                        break

                    # Very close match (>= 95% similar)
                    if char_name:
                        score = max(
                            SequenceMatcher(None, char_name, display_name).ratio(),
                            SequenceMatcher(None, char_name, username).ratio(),
                        )
                        if score >= 0.95 and score > best_score:
                            best_match = member
                            best_score = score

                    if plyr_name:
                        score = max(
                            SequenceMatcher(None, plyr_name, display_name).ratio(),
                            SequenceMatcher(None, plyr_name, username).ratio(),
                        )
                        if score >= 0.95 and score > best_score:
                            best_match = member
                            best_score = score

                # Only auto-link if we have a strong match
                if best_match and best_score >= 0.95:
                    await db.execute(
                        """
                        UPDATE players SET
                            discord_user_id = ?,
                            discord_username = ?,
                            discord_display_name = ?,
                            is_auto_linked = 1,
                            updated_at = ?
                        WHERE eos_id = ?
                    """,
                        (
                            best_match.id,
                            str(best_match),
                            best_match.display_name,
                            now,
                            player["eos_id"],
                        ),
                    )

                    linked_player = dict(player)
                    linked_player["discord_user_id"] = best_match.id
                    linked_player["discord_username"] = str(best_match)
                    linked_player["discord_display_name"] = best_match.display_name
                    linked.append(linked_player)

                    logger.info(
                        f"Auto-linked {char_name or plyr_name} to Discord user {best_match.display_name} (score: {best_score:.2f})"
                    )

            await db.commit()

    except Exception as e:
        logger.error(f"Error in auto-linking: {e}")

    return linked


async def purge_old_players(days_threshold: int = 90) -> int:
    """
    Remove players who haven't been seen in X days and are not manually linked.
    Keeps manually linked players even if inactive.

    Args:
        days_threshold: Number of days of inactivity before purging

    Returns:
        Number of players purged
    """
    import time

    db_path = Path(Config.DATABASE_PATH)
    cutoff_timestamp = int(time.time()) - (days_threshold * 24 * 60 * 60)

    try:
        async with aiosqlite.connect(db_path) as db:
            # Delete players who are:
            # 1. Old (last_seen > threshold)
            # 2. Either auto-linked or never linked (not manually linked)
            async with db.execute(
                """
                DELETE FROM players
                WHERE last_seen_timestamp < ?
                AND (is_auto_linked = 1 OR discord_user_id IS NULL)
            """,
                (cutoff_timestamp,),
            ) as cursor:
                purged_count = cursor.rowcount

            await db.commit()

            if purged_count > 0:
                logger.info(f"Purged {purged_count} players inactive for {days_threshold}+ days")

            return purged_count
    except Exception as e:
        logger.error(f"Error purging old players: {e}")
        return 0


# ---------------------------------------------------------------------------
# Economy — balance & coin transactions (EOS ID-based)
# ---------------------------------------------------------------------------

async def get_balance(guild_id: int, eos_id: str) -> int:
    """Return a player's current balance. Returns 0 if not found."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT balance FROM players WHERE guild_id = ? AND eos_id = ?",
            (guild_id, eos_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_balance_by_discord_id(guild_id: int, discord_user_id: int):
    """Return (balance, eos_id) for a Discord-linked player. Returns (0, None) if not found."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT balance, eos_id FROM players WHERE guild_id = ? AND discord_user_id = ?",
            (guild_id, discord_user_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0], row[1]
            return 0, None


async def add_coins(
    guild_id: int,
    eos_id: str,
    amount: int,
    reason: str = None,
    admin_id: int = None,
    discord_id: int = None,
) -> int:
    """
    Add coins to a player's balance and log the transaction.
    Returns the new balance.
    """
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE players SET balance = balance + ? WHERE guild_id = ? AND eos_id = ?",
            (amount, guild_id, eos_id),
        )
        await db.execute(
            """
            INSERT INTO coin_transactions
                (guild_id, eos_id, discord_id, amount, transaction_type, reason, admin_id)
            VALUES (?, ?, ?, ?, 'credit', ?, ?)
            """,
            (guild_id, eos_id, discord_id, amount, reason, admin_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT balance FROM players WHERE guild_id = ? AND eos_id = ?",
            (guild_id, eos_id),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else amount


async def deduct_coins(
    guild_id: int,
    eos_id: str,
    amount: int,
    reason: str = None,
    admin_id: int = None,
    discord_id: int = None,
) -> bool:
    """
    Deduct coins from a player's balance. Race-safe (WHERE balance >= amount).
    Returns True if successful, False if insufficient funds.
    """
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            """
            UPDATE players SET balance = balance - ?
            WHERE guild_id = ? AND eos_id = ? AND balance >= ?
            """,
            (amount, guild_id, eos_id, amount),
        )
        if cur.rowcount == 0:
            return False
        await db.execute(
            """
            INSERT INTO coin_transactions
                (guild_id, eos_id, discord_id, amount, transaction_type, reason, admin_id)
            VALUES (?, ?, ?, ?, 'debit', ?, ?)
            """,
            (guild_id, eos_id, discord_id, amount, reason, admin_id),
        )
        await db.commit()
        return True


async def get_coin_history(
    guild_id: int, eos_id: str = None, discord_id: int = None, limit: int = 10
) -> List[Dict[str, Any]]:
    """Return recent coin transactions for a player (by EOS ID or Discord ID)."""
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        if eos_id:
            query = """
                SELECT * FROM coin_transactions
                WHERE guild_id = ? AND eos_id = ?
                ORDER BY created_at DESC LIMIT ?
            """
            params = (guild_id, eos_id, limit)
        else:
            query = """
                SELECT * FROM coin_transactions
                WHERE guild_id = ? AND discord_id = ?
                ORDER BY created_at DESC LIMIT ?
            """
            params = (guild_id, discord_id, limit)
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Player Session Tracking
# ---------------------------------------------------------------------------


async def start_player_session(
    guild_id: int,
    eos_id: str,
    discord_id: int = None,
    character_name: str = None,
    server_name: str = None,
) -> Optional[int]:
    """
    Start a new player session. Returns session_id if successful.
    If an active session already exists for this player on this server, returns its ID.
    """
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            existing = await db.execute(
                """
                SELECT session_id FROM player_sessions
                WHERE guild_id = ? AND eos_id = ? AND server_name = ? AND leave_time IS NULL
                """,
                (guild_id, eos_id, server_name),
            )
            row = await existing.fetchone()
            if row:
                logger.debug(f"Active session already exists for EOS {eos_id[:8]} on {server_name}")
                return row[0]

            now = datetime.utcnow().isoformat()
            cur = await db.execute(
                """
                INSERT INTO player_sessions
                    (guild_id, eos_id, discord_id, character_name, server_name, join_time)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (guild_id, eos_id, discord_id, character_name, server_name, now),
            )
            await db.commit()
            session_id = cur.lastrowid
            logger.info(f"Started session {session_id} for EOS {eos_id[:8]} on {server_name}")
            return session_id
    except Exception as e:
        logger.error(f"Error starting player session: {e}")
        return None


async def end_player_session(
    guild_id: int, eos_id: str, server_name: str = None
) -> bool:
    """
    End an active player session. If server_name is None, ends all active sessions for this player.
    Returns True if a session was ended.
    """
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            now = datetime.utcnow().isoformat()
            if server_name:
                cur = await db.execute(
                    """
                    UPDATE player_sessions SET leave_time = ?
                    WHERE guild_id = ? AND eos_id = ? AND server_name = ? AND leave_time IS NULL
                    """,
                    (now, guild_id, eos_id, server_name),
                )
            else:
                cur = await db.execute(
                    """
                    UPDATE player_sessions SET leave_time = ?
                    WHERE guild_id = ? AND eos_id = ? AND leave_time IS NULL
                    """,
                    (now, guild_id, eos_id),
                )
            await db.commit()
            if cur.rowcount > 0:
                logger.info(f"Ended {cur.rowcount} session(s) for EOS {eos_id[:8]}")
                return True
            return False
    except Exception as e:
        logger.error(f"Error ending player session: {e}")
        return False


async def get_active_player_session(
    guild_id: int, eos_id: str, server_name: str
) -> Optional[Dict[str, Any]]:
    """Get the active session for a player on a specific server."""
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM player_sessions
                WHERE guild_id = ? AND eos_id = ? AND server_name = ? AND leave_time IS NULL
                """,
                (guild_id, eos_id, server_name),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error getting active session: {e}")
        return None


async def get_player_session_history(
    guild_id: int, eos_id: str, limit: int = 10
) -> List[Dict[str, Any]]:
    """Get session history for a player (most recent first)."""
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM player_sessions
                WHERE guild_id = ? AND eos_id = ?
                ORDER BY join_time DESC LIMIT ?
                """,
                (guild_id, eos_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting session history: {e}")
        return []


async def get_server_active_sessions(
    guild_id: int, server_name: str
) -> List[Dict[str, Any]]:
    """Get all active sessions on a specific server."""
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM player_sessions
                WHERE guild_id = ? AND server_name = ? AND leave_time IS NULL
                ORDER BY join_time DESC
                """,
                (guild_id, server_name),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting server active sessions: {e}")
        return []


async def end_all_server_sessions(guild_id: int, server_name: str) -> int:
    """
    End all active sessions for a server (call when server goes offline).
    Returns count of sessions ended.
    """
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            now = datetime.utcnow().isoformat()
            cur = await db.execute(
                """
                UPDATE player_sessions SET leave_time = ?
                WHERE guild_id = ? AND server_name = ? AND leave_time IS NULL
                """,
                (now, guild_id, server_name),
            )
            await db.commit()
            count = cur.rowcount
            if count > 0:
                logger.info(f"Ended {count} session(s) for server {server_name} (server offline)")
            return count
    except Exception as e:
        logger.error(f"Error ending all server sessions: {e}")
        return 0


# ---------------------------------------------------------------------------
# Leaderboard and Balance Reports
# ---------------------------------------------------------------------------


async def get_top_balances(guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get top players by balance for a guild."""
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT discord_user_id, discord_username, balance
                FROM players
                WHERE guild_id = ? AND balance > 0
                ORDER BY balance DESC
                LIMIT ?
                """,
                (guild_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting top balances: {e}")
        return []


async def get_all_balances(guild_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    """Get all players with balances for a guild (paginated)."""
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT discord_user_id, discord_username, balance
                FROM players
                WHERE guild_id = ?
                ORDER BY balance DESC
                LIMIT ?
                """,
                (guild_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting all balances: {e}")
        return []


async def get_linked_player_count(guild_id: int) -> int:
    """Get count of linked players for a guild."""
    try:
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM players WHERE guild_id = ? AND eos_id IS NOT NULL",
                (guild_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
    except Exception as e:
        logger.error(f"Error getting linked player count: {e}")
        return 0
