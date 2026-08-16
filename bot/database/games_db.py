"""
Database module for Phoenix Gaming Terminal.
Handles game settings, stats, and leaderboards.
"""

import aiosqlite
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

from bot.utils.config import Config

logger = logging.getLogger("GamesDB")


async def init_games_tables():
    """Initialize games tables."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS game_settings (
                guild_id INTEGER PRIMARY KEY,
                games_enabled INTEGER DEFAULT 1,
                house_edge_percent INTEGER DEFAULT 10,
                min_wager INTEGER DEFAULT 10,
                max_wager INTEGER DEFAULT 1000,
                daily_limit INTEGER DEFAULT 999999999,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (guild_id) REFERENCES guilds(guild_id)
            )
            """
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS game_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                game_name TEXT NOT NULL,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                total_wagered INTEGER DEFAULT 0,
                total_won INTEGER DEFAULT 0,
                biggest_win INTEGER DEFAULT 0,
                last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, user_id, game_name)
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_game_stats_user ON game_stats(guild_id, user_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_game_stats_game ON game_stats(guild_id, game_name)"
        )

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS game_leaderboard (
                guild_id INTEGER NOT NULL,
                game_name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                score INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, game_name, user_id)
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_leaderboard_score ON game_leaderboard(guild_id, game_name, score DESC)"
        )

        await db.commit()
        logger.info("Games tables initialized")


async def get_game_settings(guild_id: int) -> Dict[str, Any]:
    """Get game settings for a guild. Returns defaults if not set."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM game_settings WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)

    return {
        "games_enabled": 1,
        "house_edge_percent": 10,
        "min_wager": 10,
        "max_wager": 1000,
        "daily_limit": 999999999,
    }


async def update_game_settings(guild_id: int, **kwargs) -> bool:
    """Update game settings for a guild."""
    db_path = Path(Config.DATABASE_PATH)

    valid_fields = {"games_enabled", "house_edge_percent", "min_wager", "max_wager", "daily_limit"}
    updates = {k: v for k, v in kwargs.items() if k in valid_fields}
    
    if not updates:
        return False

    async with aiosqlite.connect(db_path) as db:
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        set_clause += ", updated_at = CURRENT_TIMESTAMP"
        
        await db.execute(
            f"""
            INSERT INTO game_settings (guild_id, {', '.join(updates.keys())})
            VALUES (?, {', '.join(['?'] * len(updates))})
            ON CONFLICT(guild_id) DO UPDATE SET {set_clause}
            """,
            [guild_id] + list(updates.values()) + list(updates.values())
        )
        await db.commit()
        return True


async def record_game(
    guild_id: int,
    user_id: int,
    game_name: str,
    wager: int,
    won: bool,
    payout: int,
) -> bool:
    """Record a game play in stats table."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO game_stats (guild_id, user_id, game_name, games_played, games_won, 
                                    total_wagered, total_won, biggest_win, last_played)
            VALUES (?, ?, ?, 1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id, user_id, game_name) DO UPDATE SET
                games_played = games_played + 1,
                games_won = games_won + ?,
                total_wagered = total_wagered + ?,
                total_won = total_won + ?,
                biggest_win = MAX(biggest_win, ?),
                last_played = CURRENT_TIMESTAMP
            """,
            (
                guild_id, user_id, game_name,
                1 if won else 0, wager, payout,
                payout if won else 0,
                1 if won else 0, wager, payout,
                payout if won else 0
            )
        )
        await db.commit()
        return True


async def get_user_stats(guild_id: int, user_id: int, game_name: str = None) -> Optional[Dict[str, Any]]:
    """Get stats for a user, optionally filtered by game."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        
        if game_name:
            async with db.execute(
                "SELECT * FROM game_stats WHERE guild_id = ? AND user_id = ? AND game_name = ?",
                (guild_id, user_id, game_name)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
        else:
            async with db.execute(
                "SELECT * FROM game_stats WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows] if rows else []


async def get_game_leaderboard(guild_id: int, game_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get leaderboard for a specific game."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT gs.user_id, gs.games_played, gs.games_won, gs.total_won, gs.biggest_win
            FROM game_stats gs
            WHERE gs.guild_id = ? AND gs.game_name = ?
            ORDER BY gs.total_won DESC
            LIMIT ?
            """,
            (guild_id, game_name, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_overall_leaderboard(guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get overall gaming leaderboard across all games."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT user_id, 
                   SUM(games_played) as total_games,
                   SUM(games_won) as total_wins,
                   SUM(total_wagered) as total_wagered,
                   SUM(total_won) as total_won,
                   MAX(biggest_win) as biggest_win
            FROM game_stats
            WHERE guild_id = ?
            GROUP BY user_id
            ORDER BY total_won DESC
            LIMIT ?
            """,
            (guild_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_daily_spent(guild_id: int, user_id: int) -> int:
    """Get total wagered today by a user."""
    db_path = Path(Config.DATABASE_PATH)

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            """
            SELECT COALESCE(SUM(total_wagered), 0) as total
            FROM game_stats
            WHERE guild_id = ? AND user_id = ? 
            AND date(last_played) = date('now')
            """,
            (guild_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def check_daily_limit(guild_id: int, user_id: int, wager: int) -> tuple[bool, int]:
    """Check if user can wager this amount within daily limit.
    
    Returns (can_play, current_spent)
    """
    settings = await get_game_settings(guild_id)
    daily_limit = settings.get("daily_limit", 5000)
    
    if daily_limit <= 0:
        return True, 0
    
    spent = await get_daily_spent(guild_id, user_id)
    
    if spent + wager > daily_limit:
        return False, spent
    
    return True, spent