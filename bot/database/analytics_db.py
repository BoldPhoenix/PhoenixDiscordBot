"""
Analytics database queries for visual report generation.
Provides four async functions that gather data from SQLite for the /report commands.
All queries are guild-scoped and date-filtered.
"""

import aiosqlite
import logging
from datetime import datetime
from pathlib import Path

from bot.utils.config import Config

logger = logging.getLogger("AnalyticsDB")


def _db_path() -> Path:
    return Path(Config.DATABASE_PATH)


# ---------------------------------------------------------------------------
# Player Report Data
# ---------------------------------------------------------------------------

async def get_player_report_data(guild_id: int, since: datetime) -> dict:
    """
    Gather player-session data for the /report players chart.

    Returns:
        {
            "daily_active":          [{"date": str, "count": int}, ...],
            "sessions_by_server":    [{"server": str, "count": int}, ...],
            "avg_duration_by_server":[{"server": str, "avg_minutes": float}, ...],
            "sessions_by_hour":      [{"hour": int, "count": int}, ...],
        }
    """
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    result = {
        "daily_active": [],
        "sessions_by_server": [],
        "avg_duration_by_server": [],
        "sessions_by_hour": [],
    }

    try:
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row

            # Panel 1: Daily active players (distinct discord_id per day)
            cursor = await db.execute(
                """
                SELECT DATE(join_time) AS date, COUNT(DISTINCT discord_id) AS count
                FROM player_sessions
                WHERE guild_id = ? AND join_time >= ?
                GROUP BY DATE(join_time)
                ORDER BY date
                """,
                (guild_id, since_str),
            )
            result["daily_active"] = [dict(r) for r in await cursor.fetchall()]

            # Panel 2: Total sessions per server
            cursor = await db.execute(
                """
                SELECT server_name AS server, COUNT(*) AS count
                FROM player_sessions
                WHERE guild_id = ? AND join_time >= ?
                GROUP BY server_name
                ORDER BY count DESC
                """,
                (guild_id, since_str),
            )
            result["sessions_by_server"] = [dict(r) for r in await cursor.fetchall()]

            # Panel 3: Avg session duration per server (only sessions with leave_time)
            cursor = await db.execute(
                """
                SELECT
                    server_name AS server,
                    AVG(
                        (JULIANDAY(leave_time) - JULIANDAY(join_time)) * 1440.0
                    ) AS avg_minutes
                FROM player_sessions
                WHERE guild_id = ?
                  AND join_time >= ?
                  AND leave_time IS NOT NULL
                  AND leave_time != ''
                GROUP BY server_name
                ORDER BY avg_minutes DESC
                """,
                (guild_id, since_str),
            )
            result["avg_duration_by_server"] = [
                {"server": r["server"], "avg_minutes": round(r["avg_minutes"] or 0, 1)}
                for r in await cursor.fetchall()
            ]

            # Panel 4: Sessions by hour of day
            cursor = await db.execute(
                """
                SELECT
                    CAST(strftime('%H', join_time) AS INTEGER) AS hour,
                    COUNT(*) AS count
                FROM player_sessions
                WHERE guild_id = ? AND join_time >= ?
                GROUP BY hour
                ORDER BY hour
                """,
                (guild_id, since_str),
            )
            result["sessions_by_hour"] = [dict(r) for r in await cursor.fetchall()]

    except Exception as e:
        logger.error(f"get_player_report_data error: {e}", exc_info=True)

    return result


# ---------------------------------------------------------------------------
# Economy Report Data
# ---------------------------------------------------------------------------

async def get_economy_report_data(guild_id: int, since: datetime) -> dict:
    """
    Gather economy data for the /report economy chart.

    Returns:
        {
            "payday_by_day":    [{"date": str, "total": int}, ...],
            "type_breakdown":   [{"type": str, "count": int}, ...],
            "top_balances":     [{"name": str, "balance": int}, ...],
            "cumulative_coins": [{"date": str, "running_total": int}, ...],
        }
    """
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    result = {
        "payday_by_day": [],
        "type_breakdown": [],
        "top_balances": [],
        "cumulative_coins": [],
    }

    try:
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row

            # Panel 1: Coins distributed per day via payday
            cursor = await db.execute(
                """
                SELECT DATE(created_at) AS date, SUM(total_amount) AS total
                FROM payday_history
                WHERE guild_id = ? AND created_at >= ?
                GROUP BY DATE(created_at)
                ORDER BY date
                """,
                (guild_id, since_str),
            )
            result["payday_by_day"] = [dict(r) for r in await cursor.fetchall()]

            # Panel 2: Transaction type breakdown
            cursor = await db.execute(
                """
                SELECT transaction_type AS type, COUNT(*) AS count
                FROM coin_transactions
                WHERE guild_id = ? AND created_at >= ?
                GROUP BY transaction_type
                ORDER BY count DESC
                """,
                (guild_id, since_str),
            )
            result["type_breakdown"] = [dict(r) for r in await cursor.fetchall()]

            # Panel 3: Top 10 player balances
            cursor = await db.execute(
                """
                SELECT
                    COALESCE(discord_display_name, discord_username, eos_id, 'Unknown') AS name,
                    balance
                FROM players
                WHERE guild_id = ?
                ORDER BY balance DESC
                LIMIT 10
                """,
                (guild_id,),
            )
            result["top_balances"] = [dict(r) for r in await cursor.fetchall()]

            # Panel 4: Cumulative coins in circulation over time
            cursor = await db.execute(
                """
                SELECT DATE(created_at) AS date, SUM(amount) AS daily_net
                FROM coin_transactions
                WHERE guild_id = ? AND created_at >= ?
                GROUP BY DATE(created_at)
                ORDER BY date
                """,
                (guild_id, since_str),
            )
            rows = await cursor.fetchall()
            running = 0
            cumulative = []
            for r in rows:
                running += (r["daily_net"] or 0)
                cumulative.append({"date": r["date"], "running_total": running})
            result["cumulative_coins"] = cumulative

    except Exception as e:
        logger.error(f"get_economy_report_data error: {e}", exc_info=True)

    return result


# ---------------------------------------------------------------------------
# Shop Report Data
# ---------------------------------------------------------------------------

async def get_shop_report_data(guild_id: int, since: datetime) -> dict:
    """
    Gather shop/transaction data for the /report shop chart.

    Returns:
        {
            "purchases_by_day":   [{"date": str, "count": int}, ...],
            "top_items":          [{"name": str, "count": int}, ...],
            "spend_by_category":  [{"category": str, "total": int}, ...],
            "coins_by_day":       [{"date": str, "total": int}, ...],
        }
    """
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    result = {
        "purchases_by_day": [],
        "top_items": [],
        "spend_by_category": [],
        "coins_by_day": [],
    }

    try:
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row

            # Panel 1: Purchases per day
            cursor = await db.execute(
                """
                SELECT DATE(purchase_date) AS date, COUNT(*) AS count
                FROM transactions
                WHERE guild_id = ? AND purchase_date >= ? AND status = 'completed'
                GROUP BY DATE(purchase_date)
                ORDER BY date
                """,
                (guild_id, since_str),
            )
            result["purchases_by_day"] = [dict(r) for r in await cursor.fetchall()]

            # Panel 2: Top 10 items purchased
            cursor = await db.execute(
                """
                SELECT s.name, COUNT(*) AS count
                FROM transactions t
                JOIN store_items s ON t.item_id = s.item_id AND t.guild_id = s.guild_id
                WHERE t.guild_id = ? AND t.purchase_date >= ? AND t.status = 'completed'
                GROUP BY s.name
                ORDER BY count DESC
                LIMIT 10
                """,
                (guild_id, since_str),
            )
            result["top_items"] = [dict(r) for r in await cursor.fetchall()]

            # Panel 3: Spend by category
            cursor = await db.execute(
                """
                SELECT s.category, SUM(t.cost) AS total
                FROM transactions t
                JOIN store_items s ON t.item_id = s.item_id AND t.guild_id = s.guild_id
                WHERE t.guild_id = ? AND t.purchase_date >= ? AND t.status = 'completed'
                GROUP BY s.category
                ORDER BY total DESC
                """,
                (guild_id, since_str),
            )
            result["spend_by_category"] = [dict(r) for r in await cursor.fetchall()]

            # Panel 4: Coins spent per day
            cursor = await db.execute(
                """
                SELECT DATE(purchase_date) AS date, SUM(cost) AS total
                FROM transactions
                WHERE guild_id = ? AND purchase_date >= ? AND status = 'completed'
                GROUP BY DATE(purchase_date)
                ORDER BY date
                """,
                (guild_id, since_str),
            )
            result["coins_by_day"] = [dict(r) for r in await cursor.fetchall()]

    except Exception as e:
        logger.error(f"get_shop_report_data error: {e}", exc_info=True)

    return result


# ---------------------------------------------------------------------------
# Server Report Data
# ---------------------------------------------------------------------------

async def get_server_report_data(guild_id: int, since: datetime) -> dict:
    """
    Gather server-activity data for the /report servers chart.

    Returns:
        {
            "sessions_by_server_day": [{"server": str, "date": str, "count": int}, ...],
            "total_by_server":        [{"server": str, "count": int}, ...],
            "new_players_by_day":     [{"date": str, "count": int}, ...],
            "activity_by_hour":       [{"hour": int, "count": int}, ...],
        }
    """
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    result = {
        "sessions_by_server_day": [],
        "total_by_server": [],
        "new_players_by_day": [],
        "activity_by_hour": [],
    }

    try:
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row

            # Panel 1: Session count per server per day (multi-line data)
            cursor = await db.execute(
                """
                SELECT server_name AS server, DATE(join_time) AS date, COUNT(*) AS count
                FROM player_sessions
                WHERE guild_id = ? AND join_time >= ?
                GROUP BY server_name, DATE(join_time)
                ORDER BY date, server_name
                """,
                (guild_id, since_str),
            )
            result["sessions_by_server_day"] = [dict(r) for r in await cursor.fetchall()]

            # Panel 2: Total sessions per server
            cursor = await db.execute(
                """
                SELECT server_name AS server, COUNT(*) AS count
                FROM player_sessions
                WHERE guild_id = ? AND join_time >= ?
                GROUP BY server_name
                ORDER BY count DESC
                """,
                (guild_id, since_str),
            )
            result["total_by_server"] = [dict(r) for r in await cursor.fetchall()]

            # Panel 3: New players over time
            cursor = await db.execute(
                """
                SELECT DATE(created_at) AS date, COUNT(*) AS count
                FROM players
                WHERE guild_id = ? AND created_at >= ?
                GROUP BY DATE(created_at)
                ORDER BY date
                """,
                (guild_id, since_str),
            )
            result["new_players_by_day"] = [dict(r) for r in await cursor.fetchall()]

            # Panel 4: Activity by hour of day
            cursor = await db.execute(
                """
                SELECT
                    CAST(strftime('%H', join_time) AS INTEGER) AS hour,
                    COUNT(*) AS count
                FROM player_sessions
                WHERE guild_id = ? AND join_time >= ?
                GROUP BY hour
                ORDER BY hour
                """,
                (guild_id, since_str),
            )
            result["activity_by_hour"] = [dict(r) for r in await cursor.fetchall()]

    except Exception as e:
        logger.error(f"get_server_report_data error: {e}", exc_info=True)

    return result
