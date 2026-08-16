"""
Tests for bot/database/analytics_db.py

Covers:
- All four get_X_report_data() functions return dicts with all expected keys
- Empty database returns empty lists / zeros — no crash
- Date filtering excludes records outside the time window
- Null leave_time handled gracefully in avg-duration query
"""

import pytest
import pytest_asyncio
import aiosqlite
from datetime import datetime, timedelta

from bot.database.init_db import initialize_database
from bot.database import analytics_db
from bot.utils.config import Config
from pathlib import Path

GUILD_ID   = 111222333
GUILD_ID_2 = 999888777   # isolated guild — should never appear in GUILD_ID results


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def analytics_db_fixture(config_db_path):
    """Initialised DB with player_sessions, payday_history, coin_transactions,
    transactions, store_items, players tables."""
    await initialize_database()

    # Create the tables that analytics_db queries (some may not be in init_db)
    async with aiosqlite.connect(Config.DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS player_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                discord_id INTEGER,
                server_name TEXT,
                join_time TEXT,
                leave_time TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payday_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                total_amount INTEGER DEFAULT 0,
                recipient_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS coin_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                discord_id INTEGER,
                eos_id TEXT,
                amount INTEGER DEFAULT 0,
                transaction_type TEXT,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                discord_user_id INTEGER,
                item_id INTEGER,
                cost INTEGER DEFAULT 0,
                status TEXT DEFAULT 'completed',
                purchase_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS store_items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT,
                category TEXT DEFAULT 'general',
                ark_command TEXT,
                cost INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1
            )
        """)
        await db.commit()
    yield config_db_path


# ---------------------------------------------------------------------------
# Helper — insert test data
# ---------------------------------------------------------------------------

async def _insert_sessions(guild_id: int, rows: list):
    """Insert player_sessions rows. Each row: (discord_id, server, join, leave)."""
    async with aiosqlite.connect(Config.DATABASE_PATH) as db:
        for discord_id, server, join, leave in rows:
            await db.execute(
                "INSERT INTO player_sessions (guild_id, discord_id, server_name, join_time, leave_time) VALUES (?,?,?,?,?)",
                (guild_id, discord_id, server, join, leave),
            )
        await db.commit()


async def _insert_paydays(guild_id: int, rows: list):
    """Insert payday_history rows. Each row: (total_amount, created_at).
    Uses discord_id=1 and base_amount=total_amount to satisfy NOT NULL constraints."""
    async with aiosqlite.connect(Config.DATABASE_PATH) as db:
        for amount, created_at in rows:
            await db.execute(
                """INSERT INTO payday_history
                   (guild_id, discord_id, base_amount, total_amount, created_at)
                   VALUES (?,?,?,?,?)""",
                (guild_id, 1, amount, amount, created_at),
            )
        await db.commit()


async def _insert_coin_txns(guild_id: int, rows: list):
    """Insert coin_transactions rows. Each row: (amount, type, created_at)."""
    async with aiosqlite.connect(Config.DATABASE_PATH) as db:
        for amount, txn_type, created_at in rows:
            await db.execute(
                "INSERT INTO coin_transactions (guild_id, amount, transaction_type, created_at) VALUES (?,?,?,?)",
                (guild_id, amount, txn_type, created_at),
            )
        await db.commit()


async def _insert_shop_txns(guild_id: int, items: list, txns: list):
    """Insert store_items then transactions.
    items: [(item_id, name, category, cost), ...]
    txns:  [(item_id, cost, date), ...]
    Uses ark_command placeholder and discord_id=1 to satisfy NOT NULL constraints."""
    async with aiosqlite.connect(Config.DATABASE_PATH) as db:
        for item_id, name, category, cost in items:
            await db.execute(
                """INSERT OR REPLACE INTO store_items
                   (item_id, guild_id, name, category, cost, ark_command)
                   VALUES (?,?,?,?,?,?)""",
                (item_id, guild_id, name, category, cost, f"#test_{name}"),
            )
        for item_id, cost, date in txns:
            await db.execute(
                """INSERT INTO transactions
                   (guild_id, discord_id, item_id, cost, status, purchase_date)
                   VALUES (?,?,?,?,'completed',?)""",
                (guild_id, 1, item_id, cost, date),
            )
        await db.commit()


# ---------------------------------------------------------------------------
# get_player_report_data
# ---------------------------------------------------------------------------

class TestGetPlayerReportData:

    @pytest.mark.asyncio
    async def test_returns_all_keys_empty_db(self, analytics_db_fixture):
        """Returns dict with all 4 expected keys even when DB is empty."""
        since = datetime.utcnow() - timedelta(days=7)
        data = await analytics_db.get_player_report_data(GUILD_ID, since)
        assert set(data.keys()) == {
            "daily_active", "sessions_by_server",
            "avg_duration_by_server", "sessions_by_hour",
        }
        for v in data.values():
            assert isinstance(v, list)
            assert len(v) == 0

    @pytest.mark.asyncio
    async def test_daily_active_players(self, analytics_db_fixture):
        """Counts distinct discord_ids per day."""
        now = datetime.utcnow()
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        two_days   = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        await _insert_sessions(GUILD_ID, [
            (1, "Island", yesterday, None),
            (2, "Island", yesterday, None),   # same day → count 2
            (1, "Island", two_days, None),    # different day → 1
        ])
        since = now - timedelta(days=7)
        data = await analytics_db.get_player_report_data(GUILD_ID, since)
        rows = data["daily_active"]
        assert len(rows) == 2
        counts = {r["date"]: r["count"] for r in rows}
        assert counts[two_days[:10]] == 1
        assert counts[yesterday[:10]] == 2

    @pytest.mark.asyncio
    async def test_sessions_by_server(self, analytics_db_fixture):
        """Groups session count by server_name."""
        now = datetime.utcnow()
        ts = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        await _insert_sessions(GUILD_ID, [
            (1, "Island", ts, None),
            (2, "Island", ts, None),
            (3, "Fjordur", ts, None),
        ])
        since = now - timedelta(days=1)
        data = await analytics_db.get_player_report_data(GUILD_ID, since)
        by_server = {r["server"]: r["count"] for r in data["sessions_by_server"]}
        assert by_server["Island"] == 2
        assert by_server["Fjordur"] == 1

    @pytest.mark.asyncio
    async def test_avg_duration_skips_null_leave_time(self, analytics_db_fixture):
        """Sessions with null leave_time are excluded from avg duration calculation."""
        now = datetime.utcnow()
        join = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        leave = now.strftime("%Y-%m-%d %H:%M:%S")
        await _insert_sessions(GUILD_ID, [
            (1, "Island", join, leave),   # 120 min duration
            (2, "Island", join, None),    # no leave → excluded
        ])
        since = now - timedelta(days=1)
        data = await analytics_db.get_player_report_data(GUILD_ID, since)
        dur_rows = data["avg_duration_by_server"]
        assert len(dur_rows) == 1
        assert dur_rows[0]["server"] == "Island"
        assert abs(dur_rows[0]["avg_minutes"] - 120.0) < 2   # allow 2 min rounding

    @pytest.mark.asyncio
    async def test_sessions_by_hour(self, analytics_db_fixture):
        """Counts sessions per hour of day."""
        now = datetime.utcnow()
        ts_14 = now.replace(hour=14, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
        ts_18 = now.replace(hour=18, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
        await _insert_sessions(GUILD_ID, [
            (1, "Island", ts_14, None),
            (2, "Island", ts_14, None),
            (3, "Island", ts_18, None),
        ])
        since = now - timedelta(days=1)
        data = await analytics_db.get_player_report_data(GUILD_ID, since)
        by_hour = {r["hour"]: r["count"] for r in data["sessions_by_hour"]}
        assert by_hour[14] == 2
        assert by_hour[18] == 1

    @pytest.mark.asyncio
    async def test_date_filter_excludes_old_records(self, analytics_db_fixture):
        """Records before `since` are excluded."""
        now = datetime.utcnow()
        old = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        await _insert_sessions(GUILD_ID, [(1, "Island", old, None)])
        since = now - timedelta(days=7)
        data = await analytics_db.get_player_report_data(GUILD_ID, since)
        assert data["daily_active"] == []
        assert data["sessions_by_server"] == []

    @pytest.mark.asyncio
    async def test_guild_isolation(self, analytics_db_fixture):
        """Data from guild_id_2 does not appear in guild_id results."""
        now = datetime.utcnow()
        ts = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        await _insert_sessions(GUILD_ID_2, [(99, "Crystal", ts, None)])
        since = now - timedelta(days=1)
        data = await analytics_db.get_player_report_data(GUILD_ID, since)
        assert data["sessions_by_server"] == []


# ---------------------------------------------------------------------------
# get_economy_report_data
# ---------------------------------------------------------------------------

class TestGetEconomyReportData:

    @pytest.mark.asyncio
    async def test_returns_all_keys_empty_db(self, analytics_db_fixture):
        """Returns dict with all 4 expected keys even when DB is empty."""
        since = datetime.utcnow() - timedelta(days=7)
        data = await analytics_db.get_economy_report_data(GUILD_ID, since)
        assert set(data.keys()) == {
            "payday_by_day", "type_breakdown",
            "top_balances", "cumulative_coins",
        }

    @pytest.mark.asyncio
    async def test_payday_by_day(self, analytics_db_fixture):
        """Aggregates payday amounts by day."""
        now = datetime.utcnow()
        today = now.strftime("%Y-%m-%d %H:%M:%S")
        await _insert_paydays(GUILD_ID, [(500, today), (300, today)])
        since = now - timedelta(days=1)
        data = await analytics_db.get_economy_report_data(GUILD_ID, since)
        assert len(data["payday_by_day"]) == 1
        assert data["payday_by_day"][0]["total"] == 800

    @pytest.mark.asyncio
    async def test_type_breakdown(self, analytics_db_fixture):
        """Counts coin transactions by type."""
        now = datetime.utcnow()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        await _insert_coin_txns(GUILD_ID, [
            (100, "payday", ts),
            (200, "payday", ts),
            (-50, "shop",   ts),
        ])
        since = now - timedelta(days=1)
        data = await analytics_db.get_economy_report_data(GUILD_ID, since)
        by_type = {r["type"]: r["count"] for r in data["type_breakdown"]}
        assert by_type["payday"] == 2
        assert by_type["shop"] == 1

    @pytest.mark.asyncio
    async def test_top_balances(self, analytics_db_fixture):
        """Returns top players ordered by balance descending."""
        # Players already in DB from init; add some with balances
        async with aiosqlite.connect(Config.DATABASE_PATH) as db:
            for i, bal in enumerate([1000, 500, 2000], start=1):
                await db.execute(
                    "INSERT OR REPLACE INTO players (guild_id, discord_user_id, eos_id, balance) VALUES (?,?,?,?)",
                    (GUILD_ID, i, f"eos_{i}", bal),
                )
            await db.commit()
        since = datetime.utcnow() - timedelta(days=1)
        data = await analytics_db.get_economy_report_data(GUILD_ID, since)
        balances = [r["balance"] for r in data["top_balances"]]
        assert balances == sorted(balances, reverse=True)
        assert balances[0] == 2000

    @pytest.mark.asyncio
    async def test_cumulative_coins_running_total(self, analytics_db_fixture):
        """Cumulative coins is a running sum over time."""
        now = datetime.utcnow()
        day1 = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        day2 = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        await _insert_coin_txns(GUILD_ID, [
            (100, "payday", day1),
            (200, "payday", day2),
        ])
        since = now - timedelta(days=7)
        data = await analytics_db.get_economy_report_data(GUILD_ID, since)
        totals = [r["running_total"] for r in data["cumulative_coins"]]
        assert len(totals) == 2
        assert totals[0] == 100
        assert totals[1] == 300


# ---------------------------------------------------------------------------
# get_shop_report_data
# ---------------------------------------------------------------------------

class TestGetShopReportData:

    @pytest.mark.asyncio
    async def test_returns_all_keys_empty_db(self, analytics_db_fixture):
        since = datetime.utcnow() - timedelta(days=7)
        data = await analytics_db.get_shop_report_data(GUILD_ID, since)
        assert set(data.keys()) == {
            "purchases_by_day", "top_items",
            "spend_by_category", "coins_by_day",
        }
        for v in data.values():
            assert isinstance(v, list)

    @pytest.mark.asyncio
    async def test_purchases_by_day(self, analytics_db_fixture):
        """Counts completed transactions per day."""
        now = datetime.utcnow()
        today = now.strftime("%Y-%m-%d %H:%M:%S")
        await _insert_shop_txns(GUILD_ID,
            [(1, "Rifle", "weapons", 200)],
            [(1, 200, today), (1, 200, today)],
        )
        since = now - timedelta(days=1)
        data = await analytics_db.get_shop_report_data(GUILD_ID, since)
        assert data["purchases_by_day"][0]["count"] == 2

    @pytest.mark.asyncio
    async def test_top_items(self, analytics_db_fixture):
        """Returns top 10 items ordered by purchase count."""
        now = datetime.utcnow()
        today = now.strftime("%Y-%m-%d %H:%M:%S")
        await _insert_shop_txns(GUILD_ID,
            [(10, "Rifle", "weapons", 200), (11, "Ammo", "consumables", 50)],
            [(10, 200, today), (10, 200, today), (11, 50, today)],
        )
        since = now - timedelta(days=1)
        data = await analytics_db.get_shop_report_data(GUILD_ID, since)
        top = data["top_items"]
        assert top[0]["name"] == "Rifle"
        assert top[0]["count"] == 2

    @pytest.mark.asyncio
    async def test_spend_by_category(self, analytics_db_fixture):
        """Sums spend by item category."""
        now = datetime.utcnow()
        today = now.strftime("%Y-%m-%d %H:%M:%S")
        await _insert_shop_txns(GUILD_ID,
            [(20, "Sword", "melee", 300), (21, "Bow", "ranged", 150)],
            [(20, 300, today), (21, 150, today)],
        )
        since = now - timedelta(days=1)
        data = await analytics_db.get_shop_report_data(GUILD_ID, since)
        by_cat = {r["category"]: r["total"] for r in data["spend_by_category"]}
        assert by_cat["melee"] == 300
        assert by_cat["ranged"] == 150

    @pytest.mark.asyncio
    async def test_date_filter_excludes_old_shop_records(self, analytics_db_fixture):
        """Old transactions are excluded by the since filter."""
        now = datetime.utcnow()
        old = (now - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
        await _insert_shop_txns(GUILD_ID,
            [(30, "OldGun", "weapons", 100)],
            [(30, 100, old)],
        )
        since = now - timedelta(days=7)
        data = await analytics_db.get_shop_report_data(GUILD_ID, since)
        assert data["purchases_by_day"] == []


# ---------------------------------------------------------------------------
# get_server_report_data
# ---------------------------------------------------------------------------

class TestGetServerReportData:

    @pytest.mark.asyncio
    async def test_returns_all_keys_empty_db(self, analytics_db_fixture):
        since = datetime.utcnow() - timedelta(days=7)
        data = await analytics_db.get_server_report_data(GUILD_ID, since)
        assert set(data.keys()) == {
            "sessions_by_server_day", "total_by_server",
            "new_players_by_day", "activity_by_hour",
        }
        for v in data.values():
            assert isinstance(v, list)

    @pytest.mark.asyncio
    async def test_sessions_by_server_day(self, analytics_db_fixture):
        """Groups sessions by server AND day."""
        now = datetime.utcnow()
        ts = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        await _insert_sessions(GUILD_ID, [
            (1, "Island",  ts, None),
            (2, "Island",  ts, None),
            (3, "Fjordur", ts, None),
        ])
        since = now - timedelta(days=1)
        data = await analytics_db.get_server_report_data(GUILD_ID, since)
        rows = data["sessions_by_server_day"]
        by_server = {r["server"]: r["count"] for r in rows}
        assert by_server["Island"] == 2
        assert by_server["Fjordur"] == 1

    @pytest.mark.asyncio
    async def test_new_players_by_day(self, analytics_db_fixture):
        """Counts players created per day."""
        now = datetime.utcnow()
        today = now.strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(Config.DATABASE_PATH) as db:
            for i in range(3):
                await db.execute(
                    "INSERT INTO players (guild_id, discord_user_id, eos_id, balance, created_at) VALUES (?,?,?,0,?)",
                    (GUILD_ID, 100 + i, f"eos_new_{i}", today),
                )
            await db.commit()
        since = now - timedelta(days=1)
        data = await analytics_db.get_server_report_data(GUILD_ID, since)
        assert data["new_players_by_day"][0]["count"] == 3

    @pytest.mark.asyncio
    async def test_activity_by_hour(self, analytics_db_fixture):
        """Groups sessions by hour."""
        now = datetime.utcnow()
        ts_8  = now.replace(hour=8, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
        ts_20 = now.replace(hour=20, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
        await _insert_sessions(GUILD_ID, [
            (1, "Island", ts_8, None),
            (2, "Island", ts_8, None),
            (3, "Island", ts_20, None),
        ])
        since = now - timedelta(days=1)
        data = await analytics_db.get_server_report_data(GUILD_ID, since)
        by_hour = {r["hour"]: r["count"] for r in data["activity_by_hour"]}
        assert by_hour[8] == 2
        assert by_hour[20] == 1
