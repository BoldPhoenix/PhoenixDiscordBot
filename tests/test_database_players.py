"""
Tests for bot/database/players_db.py

Covers: init_players_tables, link_player, unlink_player_by_discord_id,
unlink_player_by_eos_id, get_player_by_discord_id, get_player_by_eos_id,
get_all_linked_players, get_balance, get_balance_by_discord_id,
add_coins, deduct_coins, get_coin_history.

Fixture naming note:
  - The conftest fixture named `players_db` yields the DB path string.
  - We receive it under the parameter name `db_path` in every test to avoid
    shadowing the module-level `players_db` import alias.
  - The conftest fixture named `full_db` is also received as `db_path`.
"""

import pytest
import aiosqlite
from pathlib import Path

import bot.database.players_db as players_db
from bot.utils.config import Config

GUILD_ID = 111222333
GUILD_ID_2 = 444555666
DISCORD_ID = 100200300
DISCORD_ID_2 = 400500600
DISCORD_ID_3 = 700800900
EOS_ID = "eos_abc123def456"
EOS_ID_2 = "eos_xyz789uvw012"


# ---------------------------------------------------------------------------
# init_players_tables
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_players_tables_creates_table(players_db):  # noqa: F811
    """init_players_tables creates the players table."""
    # `players_db` here is the conftest fixture (yields str path).
    # The module is accessed via the file-level `players_db` alias,
    # but pytest injects the fixture under this parameter name.
    # We resolve the conflict by always importing the module explicitly below.
    import bot.database.players_db as _pdb
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='players'"
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "players"


@pytest.mark.asyncio
async def test_init_players_tables_idempotent(players_db):  # noqa: F811
    """Calling init_players_tables twice does not raise an error."""
    import bot.database.players_db as _pdb
    await _pdb.init_players_tables()
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='players'"
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# link_player
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_link_player_happy_path(players_db):  # noqa: F811
    """link_player returns True and the player is retrievable."""
    import bot.database.players_db as _pdb
    result = await _pdb.link_player(
        GUILD_ID,
        DISCORD_ID,
        EOS_ID,
        discord_username="TestUser#0001",
        discord_display_name="TestUser",
    )
    assert result is True

    player = await _pdb.get_player_by_discord_id(GUILD_ID, DISCORD_ID)
    assert player is not None
    assert player["discord_user_id"] == DISCORD_ID
    assert player["eos_id"] == EOS_ID


@pytest.mark.asyncio
async def test_link_player_stores_usernames(players_db):  # noqa: F811
    """link_player stores discord_username and discord_display_name."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(
        GUILD_ID,
        DISCORD_ID,
        EOS_ID,
        discord_username="StoredUser#1234",
        discord_display_name="StoredDisplay",
    )
    player = await _pdb.get_player_by_discord_id(GUILD_ID, DISCORD_ID)
    assert player["discord_username"] == "StoredUser#1234"
    assert player["discord_display_name"] == "StoredDisplay"


@pytest.mark.asyncio
async def test_link_player_stores_specimen_id(players_db):  # noqa: F811
    """link_player stores specimen_id when provided."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID, specimen_id="99887766")
    player = await _pdb.get_player_by_discord_id(GUILD_ID, DISCORD_ID)
    assert player["specimen_id"] == "99887766"


@pytest.mark.asyncio
async def test_link_player_duplicate_eos_different_user_returns_false(players_db):  # noqa: F811
    """link_player returns False when EOS ID is already linked to a different Discord user."""
    import bot.database.players_db as _pdb
    result1 = await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    assert result1 is True

    result2 = await _pdb.link_player(GUILD_ID, DISCORD_ID_2, EOS_ID)
    assert result2 is False


@pytest.mark.asyncio
async def test_link_player_same_user_twice_returns_true(players_db):  # noqa: F811
    """Linking the same Discord user twice (update) returns True and updates fields."""
    import bot.database.players_db as _pdb
    result1 = await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID, discord_username="OldName")
    assert result1 is True

    result2 = await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID, discord_username="NewName")
    assert result2 is True

    player = await _pdb.get_player_by_discord_id(GUILD_ID, DISCORD_ID)
    assert player["discord_username"] == "NewName"


# ---------------------------------------------------------------------------
# unlink_player_by_discord_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlink_player_by_discord_id_clears_eos_but_keeps_balance(full_db):  # noqa: F811
    """unlink_player_by_discord_id clears EOS ID but preserves the player record and balance."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    await _pdb.add_coins(GUILD_ID, EOS_ID, 500, "test", discord_id=DISCORD_ID)
    
    result = await _pdb.unlink_player_by_discord_id(GUILD_ID, DISCORD_ID)
    assert result is True

    # Player record should still exist
    player = await _pdb.get_player_by_discord_id(GUILD_ID, DISCORD_ID)
    assert player is not None
    # EOS ID should be cleared
    assert player["eos_id"] is None
    # Balance should be preserved
    assert player["balance"] == 500


@pytest.mark.asyncio
async def test_unlink_player_by_discord_id_nonexistent_returns_true(players_db):  # noqa: F811
    """unlink_player_by_discord_id on a non-existent user still returns True."""
    import bot.database.players_db as _pdb
    result = await _pdb.unlink_player_by_discord_id(GUILD_ID, 99999999)
    assert result is True


# ---------------------------------------------------------------------------
# unlink_player_by_eos_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unlink_player_by_eos_id_clears_eos_but_keeps_balance(full_db):  # noqa: F811
    """unlink_player_by_eos_id clears EOS ID but preserves the player record and balance."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    await _pdb.add_coins(GUILD_ID, EOS_ID, 500, "test", discord_id=DISCORD_ID)
    
    result = await _pdb.unlink_player_by_eos_id(GUILD_ID, EOS_ID)
    assert result is True

    # Player record should still exist by Discord ID
    player = await _pdb.get_player_by_discord_id(GUILD_ID, DISCORD_ID)
    assert player is not None
    # EOS ID should be cleared
    assert player["eos_id"] is None
    # Balance should be preserved
    assert player["balance"] == 500


@pytest.mark.asyncio
async def test_unlink_player_by_eos_id_nonexistent_returns_true(players_db):  # noqa: F811
    """unlink_player_by_eos_id on a non-existent EOS ID still returns True."""
    import bot.database.players_db as _pdb
    result = await _pdb.unlink_player_by_eos_id(GUILD_ID, "eos_doesnotexist")
    assert result is True


# ---------------------------------------------------------------------------
# get_player_by_discord_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_player_by_discord_id_found(players_db):  # noqa: F811
    """get_player_by_discord_id returns the correct player dict."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID, discord_username="FindMe")
    player = await _pdb.get_player_by_discord_id(GUILD_ID, DISCORD_ID)
    assert player is not None
    assert player["discord_user_id"] == DISCORD_ID
    assert player["eos_id"] == EOS_ID
    assert player["discord_username"] == "FindMe"


@pytest.mark.asyncio
async def test_get_player_by_discord_id_not_found(players_db):  # noqa: F811
    """get_player_by_discord_id returns None for an unknown Discord ID."""
    import bot.database.players_db as _pdb
    player = await _pdb.get_player_by_discord_id(99999999)
    assert player is None


@pytest.mark.asyncio
async def test_get_player_by_discord_id_single_arg_signature(players_db):  # noqa: F811
    """get_player_by_discord_id(discord_user_id) single-arg call works."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    player = await _pdb.get_player_by_discord_id(DISCORD_ID)
    assert player is not None
    assert player["discord_user_id"] == DISCORD_ID


@pytest.mark.asyncio
async def test_get_player_by_discord_id_two_arg_signature(players_db):  # noqa: F811
    """get_player_by_discord_id(guild_id, discord_user_id) two-arg call works."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    player = await _pdb.get_player_by_discord_id(GUILD_ID, DISCORD_ID)
    assert player is not None
    assert player["discord_user_id"] == DISCORD_ID


# ---------------------------------------------------------------------------
# get_player_by_eos_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_player_by_eos_id_found(players_db):  # noqa: F811
    """get_player_by_eos_id returns the correct player dict."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID, discord_display_name="EosLookup")
    player = await _pdb.get_player_by_eos_id(EOS_ID)
    assert player is not None
    assert player["eos_id"] == EOS_ID
    assert player["discord_user_id"] == DISCORD_ID


@pytest.mark.asyncio
async def test_get_player_by_eos_id_not_found(players_db):  # noqa: F811
    """get_player_by_eos_id returns None for an unknown EOS ID."""
    import bot.database.players_db as _pdb
    player = await _pdb.get_player_by_eos_id("eos_unknown_999")
    assert player is None


# ---------------------------------------------------------------------------
# get_all_linked_players
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_linked_players_empty(players_db):  # noqa: F811
    """get_all_linked_players returns empty list when no players exist."""
    import bot.database.players_db as _pdb
    result = await _pdb.get_all_linked_players()
    assert result == []


@pytest.mark.asyncio
async def test_get_all_linked_players_returns_all(players_db):  # noqa: F811
    """get_all_linked_players returns all inserted players."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID, discord_display_name="Alpha")
    await _pdb.link_player(GUILD_ID, DISCORD_ID_2, EOS_ID_2, discord_display_name="Beta")

    result = await _pdb.get_all_linked_players()
    assert len(result) == 2
    discord_ids = {p["discord_user_id"] for p in result}
    assert DISCORD_ID in discord_ids
    assert DISCORD_ID_2 in discord_ids


# ---------------------------------------------------------------------------
# get_balance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_balance_nonexistent_player_returns_zero(full_db):
    """get_balance returns 0 for a player not in the DB."""
    import bot.database.players_db as _pdb
    balance = await _pdb.get_balance(GUILD_ID, "eos_ghost_player")
    assert balance == 0


@pytest.mark.asyncio
async def test_get_balance_returns_actual_balance(full_db):
    """get_balance returns the player's stored balance."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE players SET guild_id = ?, balance = 250 WHERE discord_user_id = ?",
            (GUILD_ID, DISCORD_ID),
        )
        await db.commit()

    balance = await _pdb.get_balance(GUILD_ID, EOS_ID)
    assert balance == 250


# ---------------------------------------------------------------------------
# get_balance_by_discord_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_balance_by_discord_id_unlinked_returns_zero_none(full_db):
    """get_balance_by_discord_id returns (0, None) for an unlinked user."""
    import bot.database.players_db as _pdb
    balance, eos = await _pdb.get_balance_by_discord_id(GUILD_ID, 99999999)
    assert balance == 0
    assert eos is None


@pytest.mark.asyncio
async def test_get_balance_by_discord_id_returns_balance_and_eos_id(full_db):
    """get_balance_by_discord_id returns (balance, eos_id) for a linked player."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE players SET guild_id = ?, balance = 500 WHERE discord_user_id = ?",
            (GUILD_ID, DISCORD_ID),
        )
        await db.commit()

    balance, returned_eos = await _pdb.get_balance_by_discord_id(GUILD_ID, DISCORD_ID)
    assert balance == 500
    assert returned_eos == EOS_ID


# ---------------------------------------------------------------------------
# add_coins
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_coins_increases_balance(full_db):
    """add_coins increases the player's balance and returns the new balance."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE players SET guild_id = ? WHERE discord_user_id = ?",
            (GUILD_ID, DISCORD_ID),
        )
        await db.commit()

    new_balance = await _pdb.add_coins(GUILD_ID, EOS_ID, 100, reason="test award")
    assert new_balance == 100


@pytest.mark.asyncio
async def test_add_coins_accumulates(full_db):
    """Multiple add_coins calls accumulate correctly."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE players SET guild_id = ? WHERE discord_user_id = ?",
            (GUILD_ID, DISCORD_ID),
        )
        await db.commit()

    await _pdb.add_coins(GUILD_ID, EOS_ID, 50)
    new_balance = await _pdb.add_coins(GUILD_ID, EOS_ID, 75)
    assert new_balance == 125


@pytest.mark.asyncio
async def test_add_coins_logs_transaction(full_db):
    """add_coins inserts a row into coin_transactions."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE players SET guild_id = ? WHERE discord_user_id = ?",
            (GUILD_ID, DISCORD_ID),
        )
        await db.commit()

    await _pdb.add_coins(
        GUILD_ID, EOS_ID, 200, reason="payday", discord_id=DISCORD_ID
    )

    history = await _pdb.get_coin_history(GUILD_ID, eos_id=EOS_ID)
    assert len(history) >= 1
    assert history[0]["amount"] == 200
    assert history[0]["transaction_type"] == "credit"
    assert history[0]["reason"] == "payday"


# ---------------------------------------------------------------------------
# deduct_coins
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deduct_coins_sufficient_balance_succeeds(full_db):
    """deduct_coins returns True when balance is sufficient."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE players SET guild_id = ?, balance = 300 WHERE discord_user_id = ?",
            (GUILD_ID, DISCORD_ID),
        )
        await db.commit()

    result = await _pdb.deduct_coins(GUILD_ID, EOS_ID, 100, reason="shop purchase")
    assert result is True

    balance = await _pdb.get_balance(GUILD_ID, EOS_ID)
    assert balance == 200


@pytest.mark.asyncio
async def test_deduct_coins_insufficient_balance_returns_false(full_db):
    """deduct_coins returns False when balance is insufficient (race-safe check)."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE players SET guild_id = ?, balance = 50 WHERE discord_user_id = ?",
            (GUILD_ID, DISCORD_ID),
        )
        await db.commit()

    result = await _pdb.deduct_coins(GUILD_ID, EOS_ID, 100)
    assert result is False

    balance = await _pdb.get_balance(GUILD_ID, EOS_ID)
    assert balance == 50


@pytest.mark.asyncio
async def test_deduct_coins_exact_balance_succeeds(full_db):
    """deduct_coins with amount == balance returns True (boundary case)."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE players SET guild_id = ?, balance = 100 WHERE discord_user_id = ?",
            (GUILD_ID, DISCORD_ID),
        )
        await db.commit()

    result = await _pdb.deduct_coins(GUILD_ID, EOS_ID, 100)
    assert result is True

    balance = await _pdb.get_balance(GUILD_ID, EOS_ID)
    assert balance == 0


# ---------------------------------------------------------------------------
# get_coin_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_coin_history_by_eos_id(full_db):
    """get_coin_history returns transactions when queried by eos_id."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE players SET guild_id = ? WHERE discord_user_id = ?",
            (GUILD_ID, DISCORD_ID),
        )
        await db.commit()

    await _pdb.add_coins(GUILD_ID, EOS_ID, 10, reason="first")
    await _pdb.add_coins(GUILD_ID, EOS_ID, 20, reason="second")
    await _pdb.add_coins(GUILD_ID, EOS_ID, 30, reason="third")

    history = await _pdb.get_coin_history(GUILD_ID, eos_id=EOS_ID)
    assert len(history) == 3
    # Verify all three amounts are present (order by created_at may be same-second ties)
    amounts = {row["amount"] for row in history}
    assert amounts == {10, 20, 30}


@pytest.mark.asyncio
async def test_get_coin_history_by_discord_id(full_db):
    """get_coin_history returns transactions when queried by discord_id."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE players SET guild_id = ? WHERE discord_user_id = ?",
            (GUILD_ID, DISCORD_ID),
        )
        await db.commit()

    await _pdb.add_coins(
        GUILD_ID, EOS_ID, 55, reason="discord lookup", discord_id=DISCORD_ID
    )

    history = await _pdb.get_coin_history(GUILD_ID, discord_id=DISCORD_ID)
    assert len(history) >= 1
    assert history[0]["amount"] == 55
    assert history[0]["discord_id"] == DISCORD_ID


@pytest.mark.asyncio
async def test_get_coin_history_respects_limit(full_db):
    """get_coin_history honours the limit parameter."""
    import bot.database.players_db as _pdb
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID)
    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        await db.execute(
            "UPDATE players SET guild_id = ? WHERE discord_user_id = ?",
            (GUILD_ID, DISCORD_ID),
        )
        await db.commit()

    for i in range(5):
        await _pdb.add_coins(GUILD_ID, EOS_ID, i + 1)

    history = await _pdb.get_coin_history(GUILD_ID, eos_id=EOS_ID, limit=3)
    assert len(history) == 3


@pytest.mark.asyncio
async def test_get_coin_history_empty_for_unknown_player(full_db):
    """get_coin_history returns an empty list for a player with no transactions."""
    import bot.database.players_db as _pdb
    history = await _pdb.get_coin_history(GUILD_ID, eos_id="eos_nobody")
    assert history == []


# ---------------------------------------------------------------------------
# Player Session Tracking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_player_session_creates_session(full_db):
    """start_player_session creates a new session and returns session_id."""
    import bot.database.players_db as _pdb
    session_id = await _pdb.start_player_session(
        guild_id=GUILD_ID,
        eos_id=EOS_ID,
        discord_id=DISCORD_ID,
        character_name="TestChar",
        server_name="TestServer",
    )
    assert session_id is not None
    assert session_id > 0


@pytest.mark.asyncio
async def test_start_player_session_returns_existing_if_active(full_db):
    """start_player_session returns existing session ID if one is already active."""
    import bot.database.players_db as _pdb
    session_id_1 = await _pdb.start_player_session(
        guild_id=GUILD_ID,
        eos_id=EOS_ID,
        server_name="TestServer",
    )
    session_id_2 = await _pdb.start_player_session(
        guild_id=GUILD_ID,
        eos_id=EOS_ID,
        server_name="TestServer",
    )
    assert session_id_1 == session_id_2


@pytest.mark.asyncio
async def test_end_player_session_sets_leave_time(full_db):
    """end_player_session sets leave_time on the active session."""
    import bot.database.players_db as _pdb
    await _pdb.start_player_session(
        guild_id=GUILD_ID,
        eos_id=EOS_ID,
        server_name="TestServer",
    )
    result = await _pdb.end_player_session(
        guild_id=GUILD_ID,
        eos_id=EOS_ID,
        server_name="TestServer",
    )
    assert result is True

    session = await _pdb.get_active_player_session(GUILD_ID, EOS_ID, "TestServer")
    assert session is None


@pytest.mark.asyncio
async def test_end_player_session_returns_false_if_no_active(full_db):
    """end_player_session returns False if no active session exists."""
    import bot.database.players_db as _pdb
    result = await _pdb.end_player_session(
        guild_id=GUILD_ID,
        eos_id=EOS_ID,
        server_name="TestServer",
    )
    assert result is False


@pytest.mark.asyncio
async def test_get_active_player_session_returns_session(full_db):
    """get_active_player_session returns the active session dict."""
    import bot.database.players_db as _pdb
    await _pdb.start_player_session(
        guild_id=GUILD_ID,
        eos_id=EOS_ID,
        discord_id=DISCORD_ID,
        character_name="TestChar",
        server_name="TestServer",
    )
    session = await _pdb.get_active_player_session(GUILD_ID, EOS_ID, "TestServer")
    assert session is not None
    assert session["eos_id"] == EOS_ID
    assert session["server_name"] == "TestServer"
    assert session["leave_time"] is None


@pytest.mark.asyncio
async def test_get_player_session_history_returns_sessions(full_db):
    """get_player_session_history returns sessions in reverse chronological order."""
    import bot.database.players_db as _pdb
    import asyncio

    await _pdb.start_player_session(
        guild_id=GUILD_ID, eos_id=EOS_ID, server_name="Server1"
    )
    await _pdb.end_player_session(GUILD_ID, EOS_ID, "Server1")
    await asyncio.sleep(0.01)
    await _pdb.start_player_session(
        guild_id=GUILD_ID, eos_id=EOS_ID, server_name="Server2"
    )
    await _pdb.end_player_session(GUILD_ID, EOS_ID, "Server2")

    history = await _pdb.get_player_session_history(GUILD_ID, EOS_ID, limit=10)
    assert len(history) >= 2
    assert history[0]["server_name"] == "Server2"


@pytest.mark.asyncio
async def test_get_server_active_sessions_returns_only_active(full_db):
    """get_server_active_sessions returns only sessions with no leave_time."""
    import bot.database.players_db as _pdb
    await _pdb.start_player_session(
        guild_id=GUILD_ID, eos_id=EOS_ID, server_name="TestServer"
    )
    await _pdb.start_player_session(
        guild_id=GUILD_ID, eos_id=EOS_ID_2, server_name="TestServer"
    )
    await _pdb.end_player_session(GUILD_ID, EOS_ID_2, "TestServer")

    active = await _pdb.get_server_active_sessions(GUILD_ID, "TestServer")
    assert len(active) == 1
    assert active[0]["eos_id"] == EOS_ID


@pytest.mark.asyncio
async def test_end_all_server_sessions_ends_all_for_server(full_db):
    """end_all_server_sessions ends all active sessions for a server."""
    import bot.database.players_db as _pdb
    await _pdb.start_player_session(
        guild_id=GUILD_ID, eos_id=EOS_ID, server_name="Server1"
    )
    await _pdb.start_player_session(
        guild_id=GUILD_ID, eos_id=EOS_ID_2, server_name="Server1"
    )
    await _pdb.start_player_session(
        guild_id=GUILD_ID, eos_id="eos_third", server_name="Server2"
    )

    count = await _pdb.end_all_server_sessions(GUILD_ID, "Server1")
    assert count == 2

    active_server1 = await _pdb.get_server_active_sessions(GUILD_ID, "Server1")
    active_server2 = await _pdb.get_server_active_sessions(GUILD_ID, "Server2")
    assert len(active_server1) == 0
    assert len(active_server2) == 1


@pytest.mark.asyncio
async def test_link_player_backfills_session_discord_id(full_db):
    """link_player updates discord_id on existing sessions for the EOS ID."""
    import bot.database.players_db as _pdb

    # Start a session WITHOUT a linked player (discord_id will be NULL)
    await _pdb.start_player_session(
        guild_id=GUILD_ID,
        eos_id=EOS_ID,
        discord_id=None,
        character_name="TestChar",
        server_name="TestServer",
    )

    # Verify session has no discord_id
    session = await _pdb.get_active_player_session(GUILD_ID, EOS_ID, "TestServer")
    assert session is not None
    assert session["discord_id"] is None

    # Now link the player
    result = await _pdb.link_player(
        GUILD_ID,
        DISCORD_ID,
        EOS_ID,
        discord_username="TestUser",
        discord_display_name="TestUser",
    )
    assert result is True

    # Verify session now has discord_id
    session = await _pdb.get_active_player_session(GUILD_ID, EOS_ID, "TestServer")
    assert session is not None
    assert session["discord_id"] == DISCORD_ID


# ---------------------------------------------------------------------------
# Leaderboard and Balance Reports
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_top_balances_returns_sorted(full_db):
    """get_top_balances returns linked players sorted by balance descending."""
    import bot.database.players_db as _pdb

    # Link players first (required before adding coins)
    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID, "User1", "User1")
    await _pdb.link_player(GUILD_ID, DISCORD_ID_2, EOS_ID_2, "User2", "User2")

    # Add coins to create balances
    await _pdb.add_coins(GUILD_ID, EOS_ID, 500, "test", discord_id=DISCORD_ID)
    await _pdb.add_coins(GUILD_ID, EOS_ID_2, 1000, "test", discord_id=DISCORD_ID_2)

    top = await _pdb.get_top_balances(GUILD_ID, limit=10)
    assert len(top) >= 2
    # Should be sorted by balance descending
    assert top[0]["balance"] >= top[1]["balance"]


@pytest.mark.asyncio
async def test_get_top_balances_respects_limit(full_db):
    """get_top_balances respects the limit parameter."""
    import bot.database.players_db as _pdb

    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID, "User1", "User1")
    await _pdb.link_player(GUILD_ID, DISCORD_ID_2, EOS_ID_2, "User2", "User2")

    await _pdb.add_coins(GUILD_ID, EOS_ID, 100, "test", discord_id=DISCORD_ID)
    await _pdb.add_coins(GUILD_ID, EOS_ID_2, 200, "test", discord_id=DISCORD_ID_2)

    top = await _pdb.get_top_balances(GUILD_ID, limit=1)
    assert len(top) == 1


@pytest.mark.asyncio
async def test_get_all_balances_returns_all(full_db):
    """get_all_balances returns all linked players with balances."""
    import bot.database.players_db as _pdb

    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID, "User1", "User1")
    await _pdb.link_player(GUILD_ID, DISCORD_ID_2, EOS_ID_2, "User2", "User2")

    await _pdb.add_coins(GUILD_ID, EOS_ID, 100, "test", discord_id=DISCORD_ID)
    await _pdb.add_coins(GUILD_ID, EOS_ID_2, 200, "test", discord_id=DISCORD_ID_2)

    all_balances = await _pdb.get_all_balances(GUILD_ID, limit=100)
    assert len(all_balances) >= 2
    # Should be sorted by balance descending
    assert all_balances[0]["balance"] >= all_balances[1]["balance"]


@pytest.mark.asyncio
async def test_get_all_balances_respects_limit(full_db):
    """get_all_balances respects the limit parameter."""
    import bot.database.players_db as _pdb

    await _pdb.link_player(GUILD_ID, DISCORD_ID, EOS_ID, "User1", "User1")
    await _pdb.link_player(GUILD_ID, DISCORD_ID_2, EOS_ID_2, "User2", "User2")

    await _pdb.add_coins(GUILD_ID, EOS_ID, 100, "test", discord_id=DISCORD_ID)
    await _pdb.add_coins(GUILD_ID, EOS_ID_2, 200, "test", discord_id=DISCORD_ID_2)

    all_balances = await _pdb.get_all_balances(GUILD_ID, limit=1)
    assert len(all_balances) == 1
