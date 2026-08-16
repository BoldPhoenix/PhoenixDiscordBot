"""
Tests for economy migration: coins on players table (EOS ID-based).
"""

import pytest
import pytest_asyncio
import aiosqlite
from pathlib import Path

from bot.utils.config import Config
from bot.database import players_db
from bot.database.init_db import initialize_database


GUILD_ID = 123456789
EOS_ID = "abc123def456"
DISCORD_USER_ID = 987654321


@pytest_asyncio.fixture
async def economy_db(config_db_path):
    """Initialize database and seed a linked player with balance=0."""
    await initialize_database()

    # Insert a linked player
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO players (guild_id, discord_user_id, eos_id, character_name,
                                 balance, updated_at, created_at)
            VALUES (?, ?, ?, 'TestChar', 0, datetime('now'), datetime('now'))
            """,
            (GUILD_ID, DISCORD_USER_ID, EOS_ID),
        )
        await db.commit()

    yield config_db_path


# ---------- get_balance ----------


@pytest.mark.asyncio
async def test_get_balance_existing_player(economy_db):
    """Returns correct balance for an existing player."""
    # Give them coins first
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE players SET balance = 500 WHERE guild_id = ? AND eos_id = ?",
            (GUILD_ID, EOS_ID),
        )
        await db.commit()

    balance = await players_db.get_balance(GUILD_ID, EOS_ID)
    assert balance == 500


@pytest.mark.asyncio
async def test_get_balance_no_player(economy_db):
    """Returns 0 for a nonexistent player."""
    balance = await players_db.get_balance(GUILD_ID, "nonexistent_eos")
    assert balance == 0


# ---------- get_balance_by_discord_id ----------


@pytest.mark.asyncio
async def test_get_balance_by_discord_id_linked(economy_db):
    """Returns (balance, eos_id) for a linked Discord user."""
    # Set a known balance
    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE players SET balance = 250 WHERE guild_id = ? AND eos_id = ?",
            (GUILD_ID, EOS_ID),
        )
        await db.commit()

    balance, eos_id = await players_db.get_balance_by_discord_id(GUILD_ID, DISCORD_USER_ID)
    assert balance == 250
    assert eos_id == EOS_ID


@pytest.mark.asyncio
async def test_get_balance_by_discord_id_not_linked(economy_db):
    """Returns (0, None) for a Discord user with no linked player."""
    balance, eos_id = await players_db.get_balance_by_discord_id(GUILD_ID, 111111111)
    assert balance == 0
    assert eos_id is None


# ---------- add_coins ----------


@pytest.mark.asyncio
async def test_add_coins_returns_new_balance(economy_db):
    """add_coins returns the updated balance."""
    new_balance = await players_db.add_coins(GUILD_ID, EOS_ID, 100, "Test grant")
    assert new_balance == 100

    new_balance = await players_db.add_coins(GUILD_ID, EOS_ID, 50, "Another grant")
    assert new_balance == 150


@pytest.mark.asyncio
async def test_add_coins_logs_transaction_with_eos_id(economy_db):
    """add_coins creates a coin_transactions record with eos_id."""
    await players_db.add_coins(GUILD_ID, EOS_ID, 200, "Test reason", admin_id=42)

    db_path = Path(Config.DATABASE_PATH)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM coin_transactions WHERE guild_id = ? AND eos_id = ?",
            (GUILD_ID, EOS_ID),
        ) as cursor:
            row = await cursor.fetchone()

    assert row is not None
    tx = dict(row)
    assert tx["eos_id"] == EOS_ID
    assert tx["amount"] == 200
    assert tx["transaction_type"] == "credit"
    assert tx["reason"] == "Test reason"
    assert tx["admin_id"] == 42


# ---------- deduct_coins ----------


@pytest.mark.asyncio
async def test_deduct_coins_success(economy_db):
    """deduct_coins succeeds when balance is sufficient."""
    await players_db.add_coins(GUILD_ID, EOS_ID, 300, "Setup")

    success = await players_db.deduct_coins(GUILD_ID, EOS_ID, 100, "Purchase")
    assert success is True

    balance = await players_db.get_balance(GUILD_ID, EOS_ID)
    assert balance == 200


@pytest.mark.asyncio
async def test_deduct_coins_insufficient_balance(economy_db):
    """deduct_coins returns False and doesn't change balance when insufficient."""
    await players_db.add_coins(GUILD_ID, EOS_ID, 50, "Setup")

    success = await players_db.deduct_coins(GUILD_ID, EOS_ID, 100, "Too expensive")
    assert success is False

    # Balance unchanged
    balance = await players_db.get_balance(GUILD_ID, EOS_ID)
    assert balance == 50


@pytest.mark.asyncio
async def test_deduct_coins_race_safe(economy_db):
    """deduct_coins uses WHERE balance >= ? for race safety."""
    # Give exact amount
    await players_db.add_coins(GUILD_ID, EOS_ID, 100, "Setup")

    # Deduct exact amount should work
    success = await players_db.deduct_coins(GUILD_ID, EOS_ID, 100, "Exact deduction")
    assert success is True

    balance = await players_db.get_balance(GUILD_ID, EOS_ID)
    assert balance == 0

    # Second deduction should fail (balance is now 0)
    success = await players_db.deduct_coins(GUILD_ID, EOS_ID, 1, "Should fail")
    assert success is False


# ---------- get_coin_history ----------


@pytest.mark.asyncio
async def test_get_coin_history_ordered(economy_db):
    """get_coin_history returns all transactions for the player."""
    await players_db.add_coins(GUILD_ID, EOS_ID, 100, "First")
    await players_db.add_coins(GUILD_ID, EOS_ID, 200, "Second")
    await players_db.deduct_coins(GUILD_ID, EOS_ID, 50, "Third")

    history = await players_db.get_coin_history(GUILD_ID, EOS_ID, limit=10)
    assert len(history) == 3
    reasons = {tx["reason"] for tx in history}
    assert reasons == {"First", "Second", "Third"}
    # Verify transaction types
    types = {tx["reason"]: tx["transaction_type"] for tx in history}
    assert types["First"] == "credit"
    assert types["Second"] == "credit"
    assert types["Third"] == "debit"


@pytest.mark.asyncio
async def test_get_coin_history_empty(economy_db):
    """get_coin_history returns empty list when no transactions."""
    history = await players_db.get_coin_history(GUILD_ID, EOS_ID, limit=10)
    assert history == []
