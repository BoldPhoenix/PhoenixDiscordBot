"""
Tests for bot/database/economy_db.py
"""

import pytest
import pytest_asyncio

from bot.database import economy_db
from bot.database.init_db import initialize_database

GUILD_ID = 111222333
GUILD_ID_2 = 444555666
DISCORD_ID = 999888777
DISCORD_ID_2 = 111111111
EOS_ID = "eos_abc123"


@pytest_asyncio.fixture
async def econ_db(config_db_path):
    """Initialized database with all economy tables."""
    await initialize_database()
    yield config_db_path


# ---------------------------------------------------------------------------
# get_economy_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_economy_settings_defaults(econ_db):
    """Returns default values when no row exists."""
    settings = await economy_db.get_economy_settings(GUILD_ID)
    assert settings["guild_id"] == GUILD_ID
    assert settings["base_payday_amount"] == 100
    assert settings["currency_name"] == "Phoenix Coins"
    assert settings["payday_enabled"] == 1
    assert settings["payday_interval_hours"] == 24


@pytest.mark.asyncio
async def test_get_economy_settings_after_update(econ_db):
    """Returns stored values after update."""
    await economy_db.update_economy_settings(GUILD_ID, base_payday_amount=250, payday_interval_hours=12)
    settings = await economy_db.get_economy_settings(GUILD_ID)
    assert settings["base_payday_amount"] == 250
    assert settings["payday_interval_hours"] == 12


# ---------------------------------------------------------------------------
# update_economy_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_economy_settings_creates_row(econ_db):
    """update_economy_settings creates a new row on first call."""
    result = await economy_db.update_economy_settings(GUILD_ID, base_payday_amount=500)
    assert result is True
    settings = await economy_db.get_economy_settings(GUILD_ID)
    assert settings["base_payday_amount"] == 500


@pytest.mark.asyncio
async def test_update_economy_settings_upsert(econ_db):
    """Multiple updates accumulate correctly."""
    await economy_db.update_economy_settings(GUILD_ID, currency_name="Gold Coins")
    await economy_db.update_economy_settings(GUILD_ID, payday_enabled=0)
    settings = await economy_db.get_economy_settings(GUILD_ID)
    assert settings["currency_name"] == "Gold Coins"
    assert settings["payday_enabled"] == 0


@pytest.mark.asyncio
async def test_update_economy_settings_ignores_invalid_keys(econ_db):
    """update_economy_settings ignores keys not in the valid set."""
    result = await economy_db.update_economy_settings(GUILD_ID, nonexistent_column="value")
    assert result is False  # No valid keys → returns False


@pytest.mark.asyncio
async def test_update_economy_settings_guild_isolation(econ_db):
    """Settings are isolated per guild."""
    await economy_db.update_economy_settings(GUILD_ID, base_payday_amount=100)
    await economy_db.update_economy_settings(GUILD_ID_2, base_payday_amount=999)
    s1 = await economy_db.get_economy_settings(GUILD_ID)
    s2 = await economy_db.get_economy_settings(GUILD_ID_2)
    assert s1["base_payday_amount"] == 100
    assert s2["base_payday_amount"] == 999


# ---------------------------------------------------------------------------
# get_economy_roles / set_economy_role / remove_economy_role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_economy_roles_empty(econ_db):
    """Returns empty list when no roles configured."""
    roles = await economy_db.get_economy_roles(GUILD_ID)
    assert roles == []


@pytest.mark.asyncio
async def test_set_and_get_economy_roles(econ_db):
    """set_economy_role creates role; get_economy_roles returns it."""
    result = await economy_db.set_economy_role(GUILD_ID, role_id=12345, role_name="VIP", bonus_amount=50)
    assert result is True
    roles = await economy_db.get_economy_roles(GUILD_ID)
    assert len(roles) == 1
    assert roles[0]["role_name"] == "VIP"
    assert roles[0]["bonus_amount"] == 50


@pytest.mark.asyncio
async def test_set_economy_role_updates_existing(econ_db):
    """set_economy_role updates an existing role on conflict."""
    await economy_db.set_economy_role(GUILD_ID, role_id=12345, role_name="VIP", bonus_amount=50)
    await economy_db.set_economy_role(GUILD_ID, role_id=12345, role_name="Super VIP", bonus_amount=100)
    roles = await economy_db.get_economy_roles(GUILD_ID)
    assert len(roles) == 1
    assert roles[0]["role_name"] == "Super VIP"
    assert roles[0]["bonus_amount"] == 100


@pytest.mark.asyncio
async def test_get_economy_roles_sorted_by_bonus(econ_db):
    """get_economy_roles returns roles ordered by bonus_amount DESC."""
    await economy_db.set_economy_role(GUILD_ID, 1, "Low", 10)
    await economy_db.set_economy_role(GUILD_ID, 2, "High", 100)
    await economy_db.set_economy_role(GUILD_ID, 3, "Mid", 50)
    roles = await economy_db.get_economy_roles(GUILD_ID)
    bonuses = [r["bonus_amount"] for r in roles]
    assert bonuses == sorted(bonuses, reverse=True)


@pytest.mark.asyncio
async def test_remove_economy_role(econ_db):
    """remove_economy_role deletes the role."""
    await economy_db.set_economy_role(GUILD_ID, 12345, "VIP", 50)
    result = await economy_db.remove_economy_role(GUILD_ID, 12345)
    assert result is True
    roles = await economy_db.get_economy_roles(GUILD_ID)
    assert roles == []


@pytest.mark.asyncio
async def test_economy_roles_guild_isolation(econ_db):
    """Roles are isolated per guild."""
    await economy_db.set_economy_role(GUILD_ID, 1, "VIP", 50)
    await economy_db.set_economy_role(GUILD_ID_2, 2, "Elite", 200)
    r1 = await economy_db.get_economy_roles(GUILD_ID)
    r2 = await economy_db.get_economy_roles(GUILD_ID_2)
    assert len(r1) == 1 and r1[0]["role_name"] == "VIP"
    assert len(r2) == 1 and r2[0]["role_name"] == "Elite"


# ---------------------------------------------------------------------------
# record_payday / get_last_payday
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_last_payday_no_record(econ_db):
    """Returns None when no payday has been recorded."""
    result = await economy_db.get_last_payday(GUILD_ID, DISCORD_ID)
    assert result is None


@pytest.mark.asyncio
async def test_record_and_get_last_payday(econ_db):
    """record_payday stores record; get_last_payday returns it."""
    result = await economy_db.record_payday(
        guild_id=GUILD_ID,
        discord_id=DISCORD_ID,
        eos_id=EOS_ID,
        base_amount=100,
        role_bonus=50,
        total_amount=150,
    )
    assert result is True

    last = await economy_db.get_last_payday(GUILD_ID, DISCORD_ID)
    assert last is not None
    assert last["guild_id"] == GUILD_ID
    assert last["discord_id"] == DISCORD_ID
    assert last["base_amount"] == 100
    assert last["role_bonus"] == 50
    assert last["total_amount"] == 150
    assert last["eos_id"] == EOS_ID


@pytest.mark.asyncio
async def test_get_last_payday_returns_most_recent(econ_db):
    """get_last_payday returns the most recent record."""
    await economy_db.record_payday(GUILD_ID, DISCORD_ID, EOS_ID, 100, 0, 100)
    await economy_db.record_payday(GUILD_ID, DISCORD_ID, EOS_ID, 200, 25, 225)
    last = await economy_db.get_last_payday(GUILD_ID, DISCORD_ID)
    assert last["total_amount"] == 225


@pytest.mark.asyncio
async def test_payday_guild_isolation(econ_db):
    """Payday records are isolated per guild."""
    await economy_db.record_payday(GUILD_ID, DISCORD_ID, EOS_ID, 100, 0, 100)
    result = await economy_db.get_last_payday(GUILD_ID_2, DISCORD_ID)
    assert result is None
