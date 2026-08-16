"""
Tests for bot/database/shop_db.py
"""

import pytest
import pytest_asyncio

from bot.database import shop_db
from bot.database.init_db import initialize_database

GUILD_ID = 111222333
GUILD_ID_2 = 444555666
DISCORD_ID = 999888777
EOS_ID = "eos_abc123"


@pytest_asyncio.fixture
async def shop_database(config_db_path):
    """Initialized database with all shop tables."""
    await initialize_database()
    yield config_db_path


async def _add_item(
    guild_id=GUILD_ID,
    name="Test Sword",
    description="A sword",
    cost=100,
    ark_command='/Game/PrimalEarth/Test.Test',
    category="weapons",
    supports_quality=False,
):
    """Helper: add a store item and return its item_id."""
    return await shop_db.add_store_item(
        guild_id=guild_id,
        name=name,
        description=description,
        cost=cost,
        ark_command=ark_command,
        category=category,
        supports_quality=supports_quality,
    )


# ---------------------------------------------------------------------------
# get_shop_config / update_shop_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_shop_config_defaults(shop_database):
    """Returns default values when no row exists."""
    config = await shop_db.get_shop_config(GUILD_ID)
    assert config["guild_id"] == GUILD_ID
    assert config["shop_enabled"] == 1
    assert config["require_linked_account"] == 1
    assert config["shop_channel_id"] is None


@pytest.mark.asyncio
async def test_update_shop_config_creates_row(shop_database):
    """update_shop_config creates a new row on first call."""
    result = await shop_db.update_shop_config(GUILD_ID, shop_enabled=0)
    assert result is True
    config = await shop_db.get_shop_config(GUILD_ID)
    assert config["shop_enabled"] == 0


@pytest.mark.asyncio
async def test_update_shop_config_upsert(shop_database):
    """Multiple updates accumulate correctly."""
    await shop_db.update_shop_config(GUILD_ID, shop_channel_id=123456)
    await shop_db.update_shop_config(GUILD_ID, log_channel_id=789012)
    config = await shop_db.get_shop_config(GUILD_ID)
    assert config["shop_channel_id"] == 123456
    assert config["log_channel_id"] == 789012


@pytest.mark.asyncio
async def test_update_shop_config_invalid_keys(shop_database):
    """update_shop_config ignores unknown keys."""
    result = await shop_db.update_shop_config(GUILD_ID, nonexistent="value")
    assert result is False


@pytest.mark.asyncio
async def test_shop_config_guild_isolation(shop_database):
    """Shop config is isolated per guild."""
    await shop_db.update_shop_config(GUILD_ID, shop_enabled=1)
    await shop_db.update_shop_config(GUILD_ID_2, shop_enabled=0)
    c1 = await shop_db.get_shop_config(GUILD_ID)
    c2 = await shop_db.get_shop_config(GUILD_ID_2)
    assert c1["shop_enabled"] == 1
    assert c2["shop_enabled"] == 0


# ---------------------------------------------------------------------------
# add_store_item / get_store_item / get_store_items / get_categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_store_item_returns_id(shop_database):
    """add_store_item returns a positive item_id."""
    item_id = await _add_item()
    assert isinstance(item_id, int)
    assert item_id > 0


@pytest.mark.asyncio
async def test_get_store_item_by_id(shop_database):
    """get_store_item returns the item with correct data."""
    item_id = await _add_item(name="Magic Staff", cost=200, category="magic")
    item = await shop_db.get_store_item(item_id)
    assert item is not None
    assert item["name"] == "Magic Staff"
    assert item["cost"] == 200
    assert item["category"] == "magic"
    assert item["enabled"] == 1


@pytest.mark.asyncio
async def test_get_store_item_not_found(shop_database):
    """get_store_item returns None for unknown id."""
    item = await shop_db.get_store_item(99999)
    assert item is None


@pytest.mark.asyncio
async def test_get_store_items_empty(shop_database):
    """get_store_items returns empty list when no items exist."""
    items = await shop_db.get_store_items(GUILD_ID)
    assert items == []


@pytest.mark.asyncio
async def test_get_store_items_with_items(shop_database):
    """get_store_items returns all enabled items for guild."""
    await _add_item(name="Item A", category="weapons")
    await _add_item(name="Item B", category="armor")
    items = await shop_db.get_store_items(GUILD_ID)
    assert len(items) == 2
    names = {i["name"] for i in items}
    assert names == {"Item A", "Item B"}


@pytest.mark.asyncio
async def test_get_store_items_guild_isolation(shop_database):
    """get_store_items only returns items for the specified guild."""
    await _add_item(guild_id=GUILD_ID, name="Guild1 Item")
    await _add_item(guild_id=GUILD_ID_2, name="Guild2 Item")
    items = await shop_db.get_store_items(GUILD_ID)
    assert len(items) == 1
    assert items[0]["name"] == "Guild1 Item"


@pytest.mark.asyncio
async def test_get_store_items_category_filter(shop_database):
    """get_store_items filtered by category returns only matching items."""
    await _add_item(name="Sword", category="weapons")
    await _add_item(name="Shield", category="armor")
    items = await shop_db.get_store_items(GUILD_ID, category="weapons")
    assert len(items) == 1
    assert items[0]["name"] == "Sword"


@pytest.mark.asyncio
async def test_get_categories(shop_database):
    """get_categories returns distinct category names with counts."""
    await _add_item(name="Sword", category="weapons")
    await _add_item(name="Axe", category="weapons")
    await _add_item(name="Shield", category="armor")
    cats = await shop_db.get_categories(GUILD_ID)
    cats_dict = {c["category"]: c["count"] for c in cats}
    assert cats_dict["weapons"] == 2
    assert cats_dict["armor"] == 1


@pytest.mark.asyncio
async def test_get_categories_empty(shop_database):
    """get_categories returns empty list when no items."""
    cats = await shop_db.get_categories(GUILD_ID)
    assert cats == []


# ---------------------------------------------------------------------------
# update_store_item / delete_store_item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_store_item(shop_database):
    """update_store_item changes the specified fields."""
    item_id = await _add_item(name="Old Name", cost=50)
    result = await shop_db.update_store_item(item_id, name="New Name", cost=99)
    assert result is True
    item = await shop_db.get_store_item(item_id)
    assert item["name"] == "New Name"
    assert item["cost"] == 99


@pytest.mark.asyncio
async def test_update_store_item_no_valid_keys(shop_database):
    """update_store_item returns False when no valid keys provided."""
    item_id = await _add_item()
    result = await shop_db.update_store_item(item_id, bad_column="value")
    assert result is False


@pytest.mark.asyncio
async def test_delete_store_item(shop_database):
    """delete_store_item removes the item."""
    item_id = await _add_item()
    result = await shop_db.delete_store_item(item_id)
    assert result is True
    item = await shop_db.get_store_item(item_id)
    assert item is None


# ---------------------------------------------------------------------------
# Cart: add_to_cart / get_cart / remove_from_cart / clear_cart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_to_cart_new_item(shop_database):
    """add_to_cart adds a new cart entry."""
    item_id = await _add_item()
    result = await shop_db.add_to_cart(GUILD_ID, DISCORD_ID, item_id, quantity=1, quality=1, blueprint=False)
    assert result is True
    cart = await shop_db.get_cart(GUILD_ID, DISCORD_ID)
    assert len(cart) == 1
    assert cart[0]["quantity"] == 1


@pytest.mark.asyncio
async def test_add_to_cart_combines_quantity(shop_database):
    """Adding identical item+quality+blueprint increments quantity."""
    item_id = await _add_item()
    await shop_db.add_to_cart(GUILD_ID, DISCORD_ID, item_id, quantity=2, quality=1, blueprint=False)
    await shop_db.add_to_cart(GUILD_ID, DISCORD_ID, item_id, quantity=3, quality=1, blueprint=False)
    cart = await shop_db.get_cart(GUILD_ID, DISCORD_ID)
    assert len(cart) == 1
    assert cart[0]["quantity"] == 5


@pytest.mark.asyncio
async def test_add_to_cart_different_quality_separate_entries(shop_database):
    """Different quality = separate cart entry."""
    item_id = await _add_item()
    await shop_db.add_to_cart(GUILD_ID, DISCORD_ID, item_id, quantity=1, quality=1, blueprint=False)
    await shop_db.add_to_cart(GUILD_ID, DISCORD_ID, item_id, quantity=1, quality=10, blueprint=False)
    cart = await shop_db.get_cart(GUILD_ID, DISCORD_ID)
    assert len(cart) == 2


@pytest.mark.asyncio
async def test_get_cart_empty(shop_database):
    """get_cart returns empty list for user with no items."""
    cart = await shop_db.get_cart(GUILD_ID, DISCORD_ID)
    assert cart == []


@pytest.mark.asyncio
async def test_get_cart_includes_ark_command(shop_database):
    """get_cart joins store_items and includes ark_command."""
    item_id = await _add_item(ark_command="/Game/TestBlueprint")
    await shop_db.add_to_cart(GUILD_ID, DISCORD_ID, item_id, 1, 1, False)
    cart = await shop_db.get_cart(GUILD_ID, DISCORD_ID)
    assert cart[0]["ark_command"] == "/Game/TestBlueprint"


@pytest.mark.asyncio
async def test_remove_from_cart(shop_database):
    """remove_from_cart deletes the specified cart entry."""
    item_id = await _add_item()
    await shop_db.add_to_cart(GUILD_ID, DISCORD_ID, item_id, 1, 1, False)
    cart = await shop_db.get_cart(GUILD_ID, DISCORD_ID)
    cart_id = cart[0]["cart_id"]

    result = await shop_db.remove_from_cart(cart_id)
    assert result is True
    cart = await shop_db.get_cart(GUILD_ID, DISCORD_ID)
    assert cart == []


@pytest.mark.asyncio
async def test_clear_cart(shop_database):
    """clear_cart removes all items for a user."""
    item_id = await _add_item()
    await shop_db.add_to_cart(GUILD_ID, DISCORD_ID, item_id, 1, 1, False)
    await shop_db.add_to_cart(GUILD_ID, DISCORD_ID, item_id, 1, 2, False)

    result = await shop_db.clear_cart(GUILD_ID, DISCORD_ID)
    assert result is True
    cart = await shop_db.get_cart(GUILD_ID, DISCORD_ID)
    assert cart == []


# ---------------------------------------------------------------------------
# record_transaction / update_transaction_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_transaction_returns_id(shop_database):
    """record_transaction returns a positive transaction_id."""
    item_id = await _add_item()
    tx_id = await shop_db.record_transaction(
        guild_id=GUILD_ID, discord_id=DISCORD_ID, item_id=item_id,
        cost=100, quantity=1, server_name="Test Server"
    )
    assert isinstance(tx_id, int)
    assert tx_id > 0


@pytest.mark.asyncio
async def test_update_transaction_status(shop_database):
    """update_transaction_status changes the status field."""
    import aiosqlite
    from pathlib import Path
    from bot.utils.config import Config

    item_id = await _add_item()
    tx_id = await shop_db.record_transaction(GUILD_ID, DISCORD_ID, item_id, 100)
    result = await shop_db.update_transaction_status(tx_id, "delivered")
    assert result is True

    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status FROM transactions WHERE transaction_id = ?", (tx_id,)
        ) as cursor:
            row = await cursor.fetchone()
    assert row["status"] == "delivered"


@pytest.mark.asyncio
async def test_update_transaction_status_with_error(shop_database):
    """update_transaction_status stores error_message."""
    import aiosqlite
    from pathlib import Path
    from bot.utils.config import Config

    item_id = await _add_item()
    tx_id = await shop_db.record_transaction(GUILD_ID, DISCORD_ID, item_id, 100)
    await shop_db.update_transaction_status(tx_id, "failed", "Player not online")

    async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status, error_message FROM transactions WHERE transaction_id = ?", (tx_id,)
        ) as cursor:
            row = await cursor.fetchone()
    assert row["status"] == "failed"
    assert row["error_message"] == "Player not online"


# ---------------------------------------------------------------------------
# add_pending_delivery / get_pending_deliveries / delete_pending_delivery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_pending_delivery_returns_id(shop_database):
    """add_pending_delivery returns a positive delivery_id."""
    delivery_id = await shop_db.add_pending_delivery(
        guild_id=GUILD_ID,
        discord_user_id=DISCORD_ID,
        eos_id=EOS_ID,
        server_name="Test Server",
        item_blueprint="/Game/TestBlueprint",
        quantity=1,
        quality=4,
    )
    assert isinstance(delivery_id, int)
    assert delivery_id > 0


@pytest.mark.asyncio
async def test_get_pending_deliveries_for_guild(shop_database):
    """get_pending_deliveries returns deliveries for the specified guild."""
    await shop_db.add_pending_delivery(GUILD_ID, DISCORD_ID, EOS_ID, "Server1", "/bp1")
    await shop_db.add_pending_delivery(GUILD_ID_2, DISCORD_ID, EOS_ID, "Server2", "/bp2")

    deliveries = await shop_db.get_pending_deliveries(GUILD_ID)
    assert len(deliveries) == 1
    assert deliveries[0]["guild_id"] == GUILD_ID


@pytest.mark.asyncio
async def test_get_pending_deliveries_all(shop_database):
    """get_pending_deliveries with no guild_id returns all."""
    await shop_db.add_pending_delivery(GUILD_ID, DISCORD_ID, EOS_ID, "Server1", "/bp1")
    await shop_db.add_pending_delivery(GUILD_ID_2, DISCORD_ID, EOS_ID, "Server2", "/bp2")

    deliveries = await shop_db.get_pending_deliveries()
    assert len(deliveries) == 2


@pytest.mark.asyncio
async def test_delete_pending_delivery(shop_database):
    """delete_pending_delivery removes the specified record."""
    delivery_id = await shop_db.add_pending_delivery(
        GUILD_ID, DISCORD_ID, EOS_ID, "Server1", "/bp1"
    )
    result = await shop_db.delete_pending_delivery(delivery_id)
    assert result is True

    deliveries = await shop_db.get_pending_deliveries(GUILD_ID)
    assert deliveries == []
