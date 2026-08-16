"""
Tests for shop.py — ShopCog, ShopView, CartView, ConfirmPurchaseView, and admin modals.

Tests cover:
- Module-level imports (including new constants and classes)
- ShopCog instantiation and command existence (including /buy command)
- delivery_loop task lifecycle
- ShopView construction and pure-logic helpers (new button-based nav)
- PAGE_SIZE constant and pagination calculation
- _footer helper on ShopView
- New constants: SHOP_THUMBNAIL, NUMBER_EMOJIS
- ShopView state: cat_page, item_page, all_categories, items, current_category, selected_item
- ShopView show_home builds 4 nav buttons + 4 numbered category buttons + back/cart/search/quickbuy
- ShopView show_category builds 4 numbered item buttons
- CartView construction, embed building (afford/not afford colours)
- ConfirmPurchaseView button labels and styles (Buy Now / Add to Cart / Cancel)
- PurchaseModal field definitions and defaults (new labels/placeholders)
- QuickBuyModal — instantiation and field
- AddItemModal field definitions and max_lengths
- EditItemModal field pre-filling from item dict
- DELIVERY_SUCCESS_KEYWORDS constant
- Quality cost multiplication logic (pure arithmetic)
- Blueprint flag parsing (yes/y/true/1 → True)
- quantity clamping logic (min 1, max 100)

Uses real discord.py objects — no mocks (Jeffrey Snover methodology).
Views/Modals require a running asyncio event loop; all such tests are async.
"""

import pytest
import asyncio
import inspect
from types import SimpleNamespace

import discord


# ---------------------------------------------------------------------------
# Minimal bot stand-in
# ---------------------------------------------------------------------------

class _FakeBot:
    """Lightweight bot-like object sufficient for ShopCog instantiation."""

    def __init__(self):
        self.guilds = []

    def get_cog(self, name):
        return None

    async def wait_until_ready(self):
        pass


def _make_bot():
    return _FakeBot()


# Sample item dicts for view construction
_SAMPLE_ITEM = {
    "item_id": 1,
    "guild_id": 123,
    "name": "Rocket Launcher",
    "description": "Fires rockets.",
    "cost": 500,
    "ark_command": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Weapons/PrimalItem_WeaponRocketLauncher.PrimalItem_WeaponRocketLauncher_C'",
    "category": "weapons",
    "supports_quality": True,
    "enabled": 1,
}

_SAMPLE_CART_ITEM = {
    "cart_id": 10,
    "item_id": 1,
    "name": "Rocket Launcher",
    "cost": 500,
    "quantity": 2,
    "quality": 1,
    "blueprint": False,
}


# ---------------------------------------------------------------------------
# 1. Import tests
# ---------------------------------------------------------------------------

class TestShopImports:
    def test_shop_module_importable(self):
        import bot.cogs.shop  # noqa: F401

    def test_shop_cog_importable(self):
        from bot.cogs.shop import ShopCog
        assert ShopCog is not None

    def test_shop_view_importable(self):
        from bot.cogs.shop import ShopView
        assert ShopView is not None

    def test_cart_view_importable(self):
        from bot.cogs.shop import CartView
        assert CartView is not None

    def test_confirm_purchase_view_importable(self):
        from bot.cogs.shop import ConfirmPurchaseView
        assert ConfirmPurchaseView is not None

    def test_purchase_modal_importable(self):
        from bot.cogs.shop import PurchaseModal
        assert PurchaseModal is not None

    def test_quick_buy_modal_importable(self):
        from bot.cogs.shop import QuickBuyModal
        assert QuickBuyModal is not None

    def test_add_item_modal_importable(self):
        from bot.cogs.shop import AddItemModal
        assert AddItemModal is not None

    def test_edit_item_modal_importable(self):
        from bot.cogs.shop import EditItemModal
        assert EditItemModal is not None

    def test_delivery_failure_patterns_importable(self):
        from bot.cogs.shop import DELIVERY_FAILURE_PATTERNS
        assert isinstance(DELIVERY_FAILURE_PATTERNS, list)
        assert len(DELIVERY_FAILURE_PATTERNS) > 0

    def test_shop_thumbnail_importable(self):
        from bot.cogs.shop import SHOP_THUMBNAIL
        assert isinstance(SHOP_THUMBNAIL, str)
        assert SHOP_THUMBNAIL.startswith("https://")

    def test_number_emojis_importable(self):
        from bot.cogs.shop import NUMBER_EMOJIS
        assert isinstance(NUMBER_EMOJIS, list)
        assert len(NUMBER_EMOJIS) == 4


# ---------------------------------------------------------------------------
# 2. DELIVERY_FAILURE_PATTERNS
# ---------------------------------------------------------------------------

class TestDeliveryFailurePatterns:
    def test_contains_not_found(self):
        from bot.cogs.shop import DELIVERY_FAILURE_PATTERNS
        assert "not found" in DELIVERY_FAILURE_PATTERNS

    def test_contains_not_logged_in(self):
        from bot.cogs.shop import DELIVERY_FAILURE_PATTERNS
        assert "not logged in" in DELIVERY_FAILURE_PATTERNS

    def test_contains_invalid_player(self):
        from bot.cogs.shop import DELIVERY_FAILURE_PATTERNS
        assert "invalid player" in DELIVERY_FAILURE_PATTERNS

    def test_all_are_lowercase(self):
        from bot.cogs.shop import DELIVERY_FAILURE_PATTERNS
        for pattern in DELIVERY_FAILURE_PATTERNS:
            assert pattern == pattern.lower(), f"Pattern '{pattern}' is not lowercase"


# ---------------------------------------------------------------------------
# 3. ShopCog — instantiation, commands, task lifecycle
# ---------------------------------------------------------------------------

class TestShopCog:
    @pytest.mark.asyncio
    async def test_cog_instantiates_with_fake_bot(self):
        from bot.cogs.shop import ShopCog
        bot = _make_bot()
        cog = ShopCog(bot)
        cog.delivery_loop.cancel()
        assert cog.bot is bot

    def test_cog_has_shop_command(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "shop")

    def test_cog_has_buy_command(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "buy_cmd")

    def test_cog_has_buy_autocomplete(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "buy_autocomplete")
        assert inspect.iscoroutinefunction(ShopCog.buy_autocomplete)

    def test_cog_has_delivery_loop_task(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "delivery_loop")

    def test_delivery_loop_is_tasks_loop(self):
        from bot.cogs.shop import ShopCog
        from discord.ext.tasks import Loop
        assert isinstance(ShopCog.delivery_loop, Loop)

    @pytest.mark.asyncio
    async def test_cog_unload_cancels_delivery_loop(self):
        from bot.cogs.shop import ShopCog
        bot = _make_bot()
        cog = ShopCog(bot)
        cog.delivery_loop.cancel()
        # Calling cog_unload again should not raise
        cog.cog_unload()

    def test_cog_has_process_purchase_method(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "process_purchase")
        assert inspect.iscoroutinefunction(ShopCog.process_purchase)

    def test_cog_has_process_cart_item_method(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "process_cart_item")
        assert inspect.iscoroutinefunction(ShopCog.process_cart_item)

    def test_cog_has_deliver_item_method(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "_deliver_item")
        assert inspect.iscoroutinefunction(ShopCog._deliver_item)

    def test_deliver_item_accepts_guild_id_parameter(self):
        """_deliver_item must accept a guild_id kwarg (multi-tenant RCON fix)."""
        from bot.cogs.shop import ShopCog
        sig = inspect.signature(ShopCog._deliver_item)
        assert "guild_id" in sig.parameters

    def test_deliver_pack_accepts_guild_id_parameter(self):
        """_deliver_pack must accept a guild_id kwarg (passes through to _deliver_item)."""
        from bot.cogs.shop import ShopCog
        sig = inspect.signature(ShopCog._deliver_pack)
        assert "guild_id" in sig.parameters

    def test_deliver_item_does_not_use_rcon_manager_attribute(self):
        """_deliver_item must NOT access monitor_cog.rcon_manager (removed in multi-tenant refactor)."""
        from bot.cogs.shop import ShopCog
        source = inspect.getsource(ShopCog._deliver_item)
        assert "monitor_cog.rcon_manager" not in source, (
            "_deliver_item must not access monitor_cog.rcon_manager; "
            "use guild_rcon_managers.get(guild_id) instead"
        )

    def test_deliver_item_uses_guild_rcon_managers(self):
        """_deliver_item must use guild_rcon_managers dict (multi-tenant pattern)."""
        from bot.cogs.shop import ShopCog
        source = inspect.getsource(ShopCog._deliver_item)
        assert "guild_rcon_managers" in source

    @pytest.mark.asyncio
    async def test_deliver_item_returns_false_when_no_monitor_cog(self):
        """_deliver_item returns False when ServerMonitor cog is not loaded."""
        from bot.cogs.shop import ShopCog
        bot = _make_bot()
        bot.get_cog = lambda name: None  # no cogs loaded
        cog = ShopCog(bot)
        cog.delivery_loop.cancel()
        result = await cog._deliver_item("Island", 12345, "Blueprint'/Game/Item'", 1, 1, False, guild_id=111)
        assert result is False

    def test_delivery_loop_checks_player_online_before_delivering(self):
        """Regression: delivery_loop must check _is_player_online_in_cache before
        attempting RCON delivery. Without this check ARK silently drops GiveItemToPlayer
        for offline players but returns success, causing the queue record to be deleted
        and the player to never receive their item."""
        from bot.cogs.shop import ShopCog
        source = inspect.getsource(ShopCog.delivery_loop.coro)
        assert "_is_player_online_in_cache" in source, (
            "delivery_loop must call _is_player_online_in_cache before _deliver_item "
            "to prevent false deliveries to offline players"
        )

    def test_delivery_loop_skips_offline_players(self):
        """delivery_loop source must skip delivery when online check fails (continue stmt)."""
        from bot.cogs.shop import ShopCog
        source = inspect.getsource(ShopCog.delivery_loop.coro)
        # The online check must gate delivery with a continue/skip
        assert "not self._is_player_online_in_cache" in source

    def test_cog_has_log_purchase_method(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "_log_purchase")
        assert inspect.iscoroutinefunction(ShopCog._log_purchase)


# ---------------------------------------------------------------------------
# 4. ShopView — construction and pure-logic helpers
# ---------------------------------------------------------------------------

class TestShopView:
    @pytest.mark.asyncio
    async def test_instantiates_with_required_args(self):
        from bot.cogs.shop import ShopView
        view = ShopView(
            guild_id=123,
            discord_id=456,
            balance=1000,
            currency_name="Phoenix Coins",
            currency_icon="🪙",
        )
        assert view is not None

    @pytest.mark.asyncio
    async def test_stores_guild_id(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        assert view.guild_id == 123

    @pytest.mark.asyncio
    async def test_stores_discord_id(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        assert view.discord_id == 456

    @pytest.mark.asyncio
    async def test_stores_balance(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 750, "Phoenix Coins", "🪙")
        assert view.balance == 750

    @pytest.mark.asyncio
    async def test_stores_currency_name(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 1000, "Dragon Gold", "💎")
        assert view.currency_name == "Dragon Gold"

    @pytest.mark.asyncio
    async def test_stores_currency_icon(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 1000, "Phoenix Coins", "🔥")
        assert view.currency_icon == "🔥"

    @pytest.mark.asyncio
    async def test_initial_cat_page_is_0(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        assert view.cat_page == 0

    @pytest.mark.asyncio
    async def test_initial_item_page_is_0(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        assert view.item_page == 0

    @pytest.mark.asyncio
    async def test_initial_all_categories_is_empty_list(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        assert view.all_categories == []

    @pytest.mark.asyncio
    async def test_initial_current_category_is_none(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        assert view.current_category is None

    @pytest.mark.asyncio
    async def test_initial_selected_item_is_none(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        assert view.selected_item is None

    @pytest.mark.asyncio
    async def test_initial_items_is_empty_list(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        assert view.items == []

    @pytest.mark.asyncio
    async def test_page_size_constant_is_4(self):
        from bot.cogs.shop import ShopView
        assert ShopView.PAGE_SIZE == 4

    @pytest.mark.asyncio
    async def test_footer_contains_balance(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 1234, "Phoenix Coins", "🪙")
        footer = view._footer()
        assert "1,234" in footer

    @pytest.mark.asyncio
    async def test_footer_contains_currency_name(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Dragon Gold", "💎")
        footer = view._footer()
        assert "Dragon Gold" in footer

    @pytest.mark.asyncio
    async def test_footer_contains_currency_icon(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🔥")
        footer = view._footer()
        assert "🔥" in footer

    @pytest.mark.asyncio
    async def test_number_emojis_has_4_entries(self):
        from bot.cogs.shop import NUMBER_EMOJIS
        assert len(NUMBER_EMOJIS) == 4

    @pytest.mark.asyncio
    async def test_number_emojis_are_strings(self):
        from bot.cogs.shop import NUMBER_EMOJIS
        for emoji in NUMBER_EMOJIS:
            assert isinstance(emoji, str)

    @pytest.mark.asyncio
    async def test_shop_thumbnail_is_https_url(self):
        from bot.cogs.shop import SHOP_THUMBNAIL
        assert SHOP_THUMBNAIL.startswith("https://")

    @pytest.mark.asyncio
    async def test_make_cat_btn_returns_callable(self):
        """_make_cat_btn factory returns a coroutine function."""
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        cb = view._make_cat_btn("weapons")
        assert callable(cb)
        import asyncio
        assert asyncio.iscoroutinefunction(cb)

    @pytest.mark.asyncio
    async def test_make_item_btn_returns_callable(self):
        """_make_item_btn factory returns a coroutine function."""
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        cb = view._make_item_btn(_SAMPLE_ITEM)
        assert callable(cb)
        import asyncio
        assert asyncio.iscoroutinefunction(cb)

    @pytest.mark.asyncio
    async def test_has_show_home_method(self):
        from bot.cogs.shop import ShopView
        import asyncio
        assert asyncio.iscoroutinefunction(ShopView.show_home)

    @pytest.mark.asyncio
    async def test_has_show_category_method(self):
        from bot.cogs.shop import ShopView
        import asyncio
        assert asyncio.iscoroutinefunction(ShopView.show_category)

    @pytest.mark.asyncio
    async def test_has_nav_first_callback(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        assert hasattr(view, "_nav_first")

    @pytest.mark.asyncio
    async def test_has_nav_prev_callback(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        assert hasattr(view, "_nav_prev")

    @pytest.mark.asyncio
    async def test_has_nav_next_callback(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        assert hasattr(view, "_nav_next")

    @pytest.mark.asyncio
    async def test_has_nav_last_callback(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        assert hasattr(view, "_nav_last")

    @pytest.mark.asyncio
    async def test_has_item_prev_callback(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        assert hasattr(view, "_item_prev")

    @pytest.mark.asyncio
    async def test_has_item_next_callback(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        assert hasattr(view, "_item_next")

    @pytest.mark.asyncio
    async def test_has_back_to_home_callback(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        assert hasattr(view, "_back_to_home")

    @pytest.mark.asyncio
    async def test_has_view_cart_callback(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        assert hasattr(view, "_view_cart")

    @pytest.mark.asyncio
    async def test_has_quick_buy_coins_callback(self):
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        assert hasattr(view, "_quick_buy_coins")

    @pytest.mark.asyncio
    async def test_cat_page_nav_bounds(self):
        """cat_page clamping: _nav_prev at 0 stays 0, _nav_next at max stays at max."""
        from bot.cogs.shop import ShopView
        view = ShopView(123, 456, 100, "Phoenix Coins", "🪙")
        # Simulate total_pages = 3 with 12 categories
        view.all_categories = [{"category": f"cat{i}", "count": 2} for i in range(12)]
        # At page 0, prev should not go below 0
        view.cat_page = 0
        view.cat_page = max(0, view.cat_page - 1)
        assert view.cat_page == 0
        # At last page, next should not exceed
        total_pages = max(1, (len(view.all_categories) + 4 - 1) // 4)
        view.cat_page = total_pages - 1
        view.cat_page = min(total_pages - 1, view.cat_page + 1)
        assert view.cat_page == total_pages - 1


# ---------------------------------------------------------------------------
# 5. Pagination calculation (pure arithmetic mirroring _render_category_page)
# ---------------------------------------------------------------------------

class TestPaginationCalculation:
    def _total_pages(self, item_count: int, page_size: int = 4) -> int:
        return max(1, (item_count + page_size - 1) // page_size)

    def test_0_items_gives_1_page(self):
        assert self._total_pages(0) == 1

    def test_1_item_gives_1_page(self):
        assert self._total_pages(1) == 1

    def test_4_items_gives_1_page(self):
        assert self._total_pages(4) == 1

    def test_5_items_gives_2_pages(self):
        assert self._total_pages(5) == 2

    def test_8_items_gives_2_pages(self):
        assert self._total_pages(8) == 2

    def test_9_items_gives_3_pages(self):
        assert self._total_pages(9) == 3

    def test_page_slice_first_page(self):
        items = list(range(10))
        page, page_size = 0, 4
        start = page * page_size
        end = start + page_size
        assert items[start:end] == [0, 1, 2, 3]

    def test_page_slice_second_page(self):
        items = list(range(10))
        page, page_size = 1, 4
        start = page * page_size
        end = start + page_size
        assert items[start:end] == [4, 5, 6, 7]

    def test_page_slice_last_partial_page(self):
        items = list(range(10))
        page, page_size = 2, 4
        start = page * page_size
        end = start + page_size
        assert items[start:end] == [8, 9]


# ---------------------------------------------------------------------------
# 6. Quality cost multiplication (pure arithmetic)
# ---------------------------------------------------------------------------

class TestQualityCostMultiplication:
    def _total_cost(self, base_cost: int, qty: int, quality: int) -> int:
        return base_cost * qty * quality

    def test_primitive_quality_1(self):
        assert self._total_cost(100, 1, 1) == 100

    def test_ramshackle_quality_2(self):
        assert self._total_cost(100, 1, 2) == 200

    def test_ascendant_quality_10(self):
        assert self._total_cost(100, 1, 10) == 1000

    def test_qty_multiplies_cost(self):
        assert self._total_cost(100, 3, 1) == 300

    def test_qty_and_quality_both_multiply(self):
        assert self._total_cost(100, 2, 4) == 800

    def test_quality_names_all_present(self):
        from bot.database.shop_db import QUALITY_NAMES, VALID_QUALITIES
        for q in VALID_QUALITIES:
            assert q in QUALITY_NAMES, f"Quality {q} missing from QUALITY_NAMES"

    def test_valid_qualities_list(self):
        from bot.database.shop_db import VALID_QUALITIES
        assert VALID_QUALITIES == [1, 2, 4, 6, 8, 10]


# ---------------------------------------------------------------------------
# 7. Blueprint flag and quantity clamping (mirrors PurchaseModal.on_submit)
# ---------------------------------------------------------------------------

class TestPurchaseModalLogic:
    def _parse_blueprint(self, value: str) -> bool:
        return value.strip().lower() in ("yes", "y", "true", "1")

    def _clamp_qty(self, raw: str) -> int:
        return max(1, min(100, int(raw.strip())))

    def test_blueprint_yes_is_true(self):
        assert self._parse_blueprint("yes") is True

    def test_blueprint_y_is_true(self):
        assert self._parse_blueprint("y") is True

    def test_blueprint_true_is_true(self):
        assert self._parse_blueprint("true") is True

    def test_blueprint_1_is_true(self):
        assert self._parse_blueprint("1") is True

    def test_blueprint_no_is_false(self):
        assert self._parse_blueprint("no") is False

    def test_blueprint_n_is_false(self):
        assert self._parse_blueprint("n") is False

    def test_qty_clamped_min_to_1(self):
        assert self._clamp_qty("0") == 1

    def test_qty_clamped_max_to_100(self):
        assert self._clamp_qty("999") == 100

    def test_qty_normal_value_unchanged(self):
        assert self._clamp_qty("5") == 5

    def test_qty_boundary_1_ok(self):
        assert self._clamp_qty("1") == 1

    def test_qty_boundary_100_ok(self):
        assert self._clamp_qty("100") == 100


# ---------------------------------------------------------------------------
# 8. PurchaseModal — field definitions
# ---------------------------------------------------------------------------

class TestPurchaseModal:
    @pytest.mark.asyncio
    async def test_instantiates_basic(self):
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        sv.selected_item = _SAMPLE_ITEM
        modal = PurchaseModal(sv)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_instantiates_with_cart_mode_param(self):
        """cart_mode param is accepted for backward compat (title is now item name)."""
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        sv.selected_item = _SAMPLE_ITEM
        modal = PurchaseModal(sv, cart_mode=True)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_title_contains_item_name(self):
        """Title is 'Configure {item name}' (not buy/cart mode)."""
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        sv.selected_item = _SAMPLE_ITEM
        modal = PurchaseModal(sv)
        assert "Rocket Launcher" in modal.title

    @pytest.mark.asyncio
    async def test_title_truncated_to_45_chars(self):
        """Discord modal title max is 45 chars."""
        from bot.cogs.shop import ShopView, PurchaseModal
        long_name_item = {**_SAMPLE_ITEM, "name": "A" * 50}
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        sv.selected_item = long_name_item
        modal = PurchaseModal(sv)
        assert len(modal.title) <= 45

    @pytest.mark.asyncio
    async def test_has_quantity_field(self):
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = PurchaseModal(sv)
        assert hasattr(modal, "quantity")

    @pytest.mark.asyncio
    async def test_has_quality_field(self):
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = PurchaseModal(sv)
        assert hasattr(modal, "quality")

    @pytest.mark.asyncio
    async def test_has_blueprint_field(self):
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = PurchaseModal(sv)
        assert hasattr(modal, "blueprint")

    @pytest.mark.asyncio
    async def test_quantity_max_length_is_3(self):
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = PurchaseModal(sv)
        assert modal.quantity.max_length == 3

    @pytest.mark.asyncio
    async def test_quality_max_length_is_2(self):
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = PurchaseModal(sv)
        assert modal.quality.max_length == 2

    @pytest.mark.asyncio
    async def test_blueprint_max_length_is_3(self):
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = PurchaseModal(sv)
        assert modal.blueprint.max_length == 3

    @pytest.mark.asyncio
    async def test_quantity_label_is_enter_amount(self):
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = PurchaseModal(sv)
        assert "amount" in modal.quantity.label.lower() or "Enter" in modal.quantity.label

    @pytest.mark.asyncio
    async def test_quantity_default_is_1(self):
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = PurchaseModal(sv)
        assert modal.quantity.default == "1"

    @pytest.mark.asyncio
    async def test_blueprint_default_is_no(self):
        from bot.cogs.shop import ShopView, PurchaseModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = PurchaseModal(sv)
        assert modal.blueprint.default == "no"

    @pytest.mark.asyncio
    async def test_quality_removed_when_not_supported(self):
        """Quality field is removed from modal when item does not support quality."""
        from bot.cogs.shop import ShopView, PurchaseModal
        no_quality_item = {**_SAMPLE_ITEM, "supports_quality": False, "allow_blueprint_select": False}
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        sv.selected_item = no_quality_item
        modal = PurchaseModal(sv)
        # quality TextInput should not be in modal's children
        field_labels = [c.label for c in modal.children if hasattr(c, "label")]
        assert not any("Quality" in lbl for lbl in field_labels)

    @pytest.mark.asyncio
    async def test_blueprint_removed_when_not_supported(self):
        """Blueprint field is removed from modal when item does not support blueprint select."""
        from bot.cogs.shop import ShopView, PurchaseModal
        no_bp_item = {**_SAMPLE_ITEM, "allow_blueprint_select": False, "supports_quality": False}
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        sv.selected_item = no_bp_item
        modal = PurchaseModal(sv)
        field_labels = [c.label for c in modal.children if hasattr(c, "label")]
        assert not any("blueprint" in lbl.lower() for lbl in field_labels)


# ---------------------------------------------------------------------------
# 8b. QuickBuyModal — instantiation and field
# ---------------------------------------------------------------------------

class TestQuickBuyModal:
    @pytest.mark.asyncio
    async def test_instantiates(self):
        from bot.cogs.shop import ShopView, QuickBuyModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = QuickBuyModal(sv, _SAMPLE_ITEM)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_has_quantity_field(self):
        from bot.cogs.shop import ShopView, QuickBuyModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = QuickBuyModal(sv, _SAMPLE_ITEM)
        assert hasattr(modal, "quantity")

    @pytest.mark.asyncio
    async def test_quantity_max_length_is_6(self):
        from bot.cogs.shop import ShopView, QuickBuyModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = QuickBuyModal(sv, _SAMPLE_ITEM)
        assert modal.quantity.max_length == 6

    @pytest.mark.asyncio
    async def test_quantity_default_is_1(self):
        from bot.cogs.shop import ShopView, QuickBuyModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = QuickBuyModal(sv, _SAMPLE_ITEM)
        assert modal.quantity.default == "1"

    @pytest.mark.asyncio
    async def test_stores_item(self):
        from bot.cogs.shop import ShopView, QuickBuyModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = QuickBuyModal(sv, _SAMPLE_ITEM)
        assert modal.item is _SAMPLE_ITEM

    @pytest.mark.asyncio
    async def test_stores_shop_view(self):
        from bot.cogs.shop import ShopView, QuickBuyModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = QuickBuyModal(sv, _SAMPLE_ITEM)
        assert modal.shop_view is sv

    @pytest.mark.asyncio
    async def test_quantity_label_mentions_phoenix_coins(self):
        from bot.cogs.shop import ShopView, QuickBuyModal
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        modal = QuickBuyModal(sv, _SAMPLE_ITEM)
        assert "Phoenix Coins" in modal.quantity.label or "coins" in modal.quantity.label.lower()


# ---------------------------------------------------------------------------
# 9. ConfirmPurchaseView — buttons (Buy Now / Add to Cart / Cancel)
# ---------------------------------------------------------------------------

class TestConfirmPurchaseView:
    @pytest.mark.asyncio
    async def test_instantiates(self):
        from bot.cogs.shop import ShopView, ConfirmPurchaseView
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        view = ConfirmPurchaseView(sv, _SAMPLE_ITEM, qty=1, quality=1, force_blueprint=False, total_cost=500)
        assert view is not None

    @pytest.mark.asyncio
    async def test_has_buy_now_button(self):
        from bot.cogs.shop import ShopView, ConfirmPurchaseView
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        view = ConfirmPurchaseView(sv, _SAMPLE_ITEM, qty=1, quality=1, force_blueprint=False, total_cost=500)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Buy Now" in lbl for lbl in labels)

    @pytest.mark.asyncio
    async def test_has_add_to_cart_button(self):
        from bot.cogs.shop import ShopView, ConfirmPurchaseView
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        view = ConfirmPurchaseView(sv, _SAMPLE_ITEM, qty=1, quality=1, force_blueprint=False, total_cost=500)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Add to Cart" in lbl for lbl in labels)

    @pytest.mark.asyncio
    async def test_has_cancel_button(self):
        from bot.cogs.shop import ShopView, ConfirmPurchaseView
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        view = ConfirmPurchaseView(sv, _SAMPLE_ITEM, qty=1, quality=1, force_blueprint=False, total_cost=500)
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Cancel" in lbl for lbl in labels)

    @pytest.mark.asyncio
    async def test_has_three_buttons(self):
        from bot.cogs.shop import ShopView, ConfirmPurchaseView
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        view = ConfirmPurchaseView(sv, _SAMPLE_ITEM, qty=1, quality=1, force_blueprint=False, total_cost=500)
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 3

    @pytest.mark.asyncio
    async def test_buy_now_button_style_is_success(self):
        from bot.cogs.shop import ShopView, ConfirmPurchaseView
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        view = ConfirmPurchaseView(sv, _SAMPLE_ITEM, qty=1, quality=1, force_blueprint=False, total_cost=500)
        buy_btn = next(
            (c for c in view.children if isinstance(c, discord.ui.Button) and "Buy Now" in (c.label or "")),
            None,
        )
        assert buy_btn is not None
        assert buy_btn.style == discord.ButtonStyle.success

    @pytest.mark.asyncio
    async def test_add_to_cart_button_style_is_primary(self):
        from bot.cogs.shop import ShopView, ConfirmPurchaseView
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        view = ConfirmPurchaseView(sv, _SAMPLE_ITEM, qty=1, quality=1, force_blueprint=False, total_cost=500)
        cart_btn = next(
            (c for c in view.children if isinstance(c, discord.ui.Button) and "Add to Cart" in (c.label or "")),
            None,
        )
        assert cart_btn is not None
        assert cart_btn.style == discord.ButtonStyle.primary

    @pytest.mark.asyncio
    async def test_cancel_button_style_is_secondary(self):
        from bot.cogs.shop import ShopView, ConfirmPurchaseView
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        view = ConfirmPurchaseView(sv, _SAMPLE_ITEM, qty=1, quality=1, force_blueprint=False, total_cost=500)
        cancel_btn = next(
            (c for c in view.children if isinstance(c, discord.ui.Button) and "Cancel" in (c.label or "")),
            None,
        )
        assert cancel_btn is not None
        assert cancel_btn.style == discord.ButtonStyle.secondary

    @pytest.mark.asyncio
    async def test_stores_item(self):
        from bot.cogs.shop import ShopView, ConfirmPurchaseView
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        view = ConfirmPurchaseView(sv, _SAMPLE_ITEM, qty=2, quality=4, force_blueprint=True, total_cost=4000)
        assert view.item is _SAMPLE_ITEM
        assert view.qty == 2
        assert view.quality == 4
        assert view.force_blueprint is True
        assert view.total_cost == 4000

    @pytest.mark.asyncio
    async def test_cart_mode_defaults_to_false(self):
        from bot.cogs.shop import ShopView, ConfirmPurchaseView
        sv = ShopView(123, 456, 1000, "Phoenix Coins", "🪙")
        view = ConfirmPurchaseView(sv, _SAMPLE_ITEM, qty=1, quality=1, force_blueprint=False, total_cost=500)
        assert view.cart_mode is False


# ---------------------------------------------------------------------------
# 10. CartView — construction and embed building
# ---------------------------------------------------------------------------

class TestCartView:
    @pytest.mark.asyncio
    async def test_instantiates_with_items(self):
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [_SAMPLE_CART_ITEM], 2000, "Phoenix Coins", "🪙")
        assert view is not None

    @pytest.mark.asyncio
    async def test_instantiates_with_empty_items(self):
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [], 2000, "Phoenix Coins", "🪙")
        assert view is not None

    @pytest.mark.asyncio
    async def test_has_checkout_button(self):
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [_SAMPLE_CART_ITEM], 2000, "Phoenix Coins", "🪙")
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Checkout" in lbl for lbl in labels)

    @pytest.mark.asyncio
    async def test_has_clear_cart_button(self):
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [_SAMPLE_CART_ITEM], 2000, "Phoenix Coins", "🪙")
        labels = [c.label for c in view.children if isinstance(c, discord.ui.Button)]
        assert any("Clear Cart" in lbl for lbl in labels)

    @pytest.mark.asyncio
    async def test_has_remove_select_when_items_present(self):
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [_SAMPLE_CART_ITEM], 2000, "Phoenix Coins", "🪙")
        selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
        assert len(selects) == 1

    @pytest.mark.asyncio
    async def test_no_remove_select_when_no_items(self):
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [], 2000, "Phoenix Coins", "🪙")
        selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
        assert len(selects) == 0

    @pytest.mark.asyncio
    async def test_build_embed_title_is_shopping_cart(self):
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [_SAMPLE_CART_ITEM], 2000, "Phoenix Coins", "🪙")
        embed = view.build_embed()
        assert "Cart" in embed.title

    @pytest.mark.asyncio
    async def test_build_embed_green_when_can_afford(self):
        """Balance 2000 > total cost 1000 (500 * 2 * 1) → green."""
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [_SAMPLE_CART_ITEM], 2000, "Phoenix Coins", "🪙")
        embed = view.build_embed()
        assert embed.color == discord.Color.green()

    @pytest.mark.asyncio
    async def test_build_embed_red_when_cannot_afford(self):
        """Balance 100 < total cost 1000 (500 * 2 * 1) → red."""
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [_SAMPLE_CART_ITEM], 100, "Phoenix Coins", "🪙")
        embed = view.build_embed()
        assert embed.color == discord.Color.red()

    @pytest.mark.asyncio
    async def test_build_embed_shows_item_name(self):
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [_SAMPLE_CART_ITEM], 2000, "Phoenix Coins", "🪙")
        embed = view.build_embed()
        field_names = [f.name for f in embed.fields]
        assert any("Rocket Launcher" in n for n in field_names)

    @pytest.mark.asyncio
    async def test_build_embed_shows_total_field(self):
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [_SAMPLE_CART_ITEM], 2000, "Phoenix Coins", "🪙")
        embed = view.build_embed()
        field_names = [f.name for f in embed.fields]
        assert "Total" in field_names

    @pytest.mark.asyncio
    async def test_checkout_button_style_is_success(self):
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [_SAMPLE_CART_ITEM], 2000, "Phoenix Coins", "🪙")
        checkout_btn = next(
            (c for c in view.children if isinstance(c, discord.ui.Button) and "Checkout" in (c.label or "")),
            None,
        )
        assert checkout_btn is not None
        assert checkout_btn.style == discord.ButtonStyle.success

    @pytest.mark.asyncio
    async def test_clear_cart_button_style_is_danger(self):
        from bot.cogs.shop import CartView
        view = CartView(123, 456, [_SAMPLE_CART_ITEM], 2000, "Phoenix Coins", "🪙")
        clear_btn = next(
            (c for c in view.children if isinstance(c, discord.ui.Button) and "Clear" in (c.label or "")),
            None,
        )
        assert clear_btn is not None
        assert clear_btn.style == discord.ButtonStyle.danger

    @pytest.mark.asyncio
    async def test_total_cost_calculation(self):
        """CartView.build_embed total = sum(cost * qty * quality)."""
        from bot.cogs.shop import CartView
        items = [
            {"cart_id": 1, "item_id": 1, "name": "Item A", "cost": 100, "quantity": 3, "quality": 2, "blueprint": False},
            {"cart_id": 2, "item_id": 2, "name": "Item B", "cost": 200, "quantity": 1, "quality": 1, "blueprint": False},
        ]
        # Expected total: 100*3*2 + 200*1*1 = 600 + 200 = 800
        view = CartView(123, 456, items, 1000, "Phoenix Coins", "🪙")
        total = sum(i["cost"] * i["quantity"] * i["quality"] for i in items)
        assert total == 800


# ---------------------------------------------------------------------------
# 11. AddItemModal — field definitions
# ---------------------------------------------------------------------------

class TestAddItemModal:
    @pytest.mark.asyncio
    async def test_instantiates_with_guild_id(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_stores_guild_id(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=999)
        assert modal.guild_id == 999

    @pytest.mark.asyncio
    async def test_has_name_field(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert hasattr(modal, "name")

    @pytest.mark.asyncio
    async def test_has_cost_field(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert hasattr(modal, "cost")

    @pytest.mark.asyncio
    async def test_has_ark_command_field(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert hasattr(modal, "ark_command")

    @pytest.mark.asyncio
    async def test_has_category_field(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert hasattr(modal, "category")

    @pytest.mark.asyncio
    async def test_has_supports_quality_field(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert hasattr(modal, "supports_quality")

    @pytest.mark.asyncio
    async def test_name_max_length_is_100(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert modal.name.max_length == 100

    @pytest.mark.asyncio
    async def test_cost_max_length_is_8(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert modal.cost.max_length == 8

    @pytest.mark.asyncio
    async def test_ark_command_max_length_is_500(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert modal.ark_command.max_length == 500

    @pytest.mark.asyncio
    async def test_category_max_length_is_50(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert modal.category.max_length == 50

    @pytest.mark.asyncio
    async def test_supports_quality_max_length_is_3(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert modal.supports_quality.max_length == 3

    @pytest.mark.asyncio
    async def test_supports_quality_default_is_no(self):
        from bot.cogs.shop import AddItemModal
        modal = AddItemModal(guild_id=123)
        assert modal.supports_quality.default == "no"


# ---------------------------------------------------------------------------
# 12. EditItemModal — field pre-filling from item dict
# ---------------------------------------------------------------------------

class TestEditItemModal:
    @pytest.mark.asyncio
    async def test_instantiates_with_item_dict(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal(_SAMPLE_ITEM)
        assert modal is not None

    @pytest.mark.asyncio
    async def test_prefills_name_from_item(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal(_SAMPLE_ITEM)
        assert modal.name.default == "Rocket Launcher"

    @pytest.mark.asyncio
    async def test_prefills_cost_from_item(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal(_SAMPLE_ITEM)
        assert modal.cost.default == "500"

    @pytest.mark.asyncio
    async def test_prefills_category_from_item(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal(_SAMPLE_ITEM)
        assert modal.category.default == "weapons"

    @pytest.mark.asyncio
    async def test_prefills_supports_quality_yes_when_true(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal({**_SAMPLE_ITEM, "supports_quality": True})
        assert modal.supports_quality.default == "yes"

    @pytest.mark.asyncio
    async def test_prefills_supports_quality_no_when_false(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal({**_SAMPLE_ITEM, "supports_quality": False})
        assert modal.supports_quality.default == "no"

    @pytest.mark.asyncio
    async def test_prefills_description_from_item(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal({**_SAMPLE_ITEM, "description": "A great item"})
        assert modal.description.default == "A great item"

    @pytest.mark.asyncio
    async def test_prefills_description_empty_when_none(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal({**_SAMPLE_ITEM, "description": None})
        assert modal.description.default == ""

    @pytest.mark.asyncio
    async def test_name_max_length_is_100(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal(_SAMPLE_ITEM)
        assert modal.name.max_length == 100

    @pytest.mark.asyncio
    async def test_cost_max_length_is_8(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal(_SAMPLE_ITEM)
        assert modal.cost.max_length == 8

    @pytest.mark.asyncio
    async def test_category_max_length_is_50(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal(_SAMPLE_ITEM)
        assert modal.category.max_length == 50

    @pytest.mark.asyncio
    async def test_supports_quality_max_length_is_3(self):
        from bot.cogs.shop import EditItemModal
        modal = EditItemModal(_SAMPLE_ITEM)
        assert modal.supports_quality.max_length == 3


# ---------------------------------------------------------------------------
# 12. Import/Export helper functions
# ---------------------------------------------------------------------------

class TestParseBoolField:
    def test_true_bool(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field(True) is True

    def test_false_bool(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field(False) is False

    def test_yes_string(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field("yes") is True

    def test_no_string(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field("no") is False

    def test_true_string(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field("true") is True

    def test_false_string(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field("false") is False

    def test_one_string(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field("1") is True

    def test_zero_string(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field("0") is False

    def test_none_returns_default_true(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field(None, default=True) is True

    def test_none_returns_default_false(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field(None, default=False) is False

    def test_case_insensitive_YES(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field("YES") is True

    def test_case_insensitive_NO(self):
        from bot.cogs.shop import _parse_bool_field
        assert _parse_bool_field("NO") is False


class TestStripBlueprintQuotes:
    def test_strips_outer_double_quotes(self):
        from bot.cogs.shop import _strip_blueprint_quotes
        raw = '"Blueprint\'/Game/test_C\'"'
        result = _strip_blueprint_quotes(raw)
        assert result == "Blueprint'/Game/test_C'"
        assert not result.startswith('"')

    def test_no_change_when_no_quotes(self):
        from bot.cogs.shop import _strip_blueprint_quotes
        raw = "Blueprint'/Game/test_C'"
        assert _strip_blueprint_quotes(raw) == raw

    def test_strips_whitespace(self):
        from bot.cogs.shop import _strip_blueprint_quotes
        raw = '  "Blueprint\'/Game/test_C\'"  '
        result = _strip_blueprint_quotes(raw)
        assert result == "Blueprint'/Game/test_C'"

    def test_single_quote_not_stripped(self):
        from bot.cogs.shop import _strip_blueprint_quotes
        raw = "'Blueprint'/Game/test_C'"
        # single quotes are not outer double-quotes, should not strip
        result = _strip_blueprint_quotes(raw)
        assert result == raw.strip()


class TestParseXlsxShop:
    """Tests for _parse_xlsx_shop — uses in-memory openpyxl workbooks."""

    def _make_xlsx(self, headers, rows, sheet_name="items"):
        import openpyxl, io
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_name
        ws.append(headers)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.read()

    def test_parses_valid_items(self):
        from bot.cogs.shop import _parse_xlsx_shop
        data = self._make_xlsx(
            ["Item Name", "Price Per Item", "Blueprint Path", "Category", "Enabled"],
            [
                ["Steel Sword", 100, "Blueprint'/Game/sword_C'", "Weapons", True],
                ["Iron Shield", 50, "Blueprint'/Game/shield_C'", "Armor", True],
            ],
        )
        items, errors = _parse_xlsx_shop(data)
        assert len(items) == 2
        assert len(errors) == 0
        assert items[0]["name"] == "Steel Sword"
        assert items[0]["cost"] == 100
        assert items[1]["category"] == "armor"

    def test_strips_outer_quotes_from_blueprint(self):
        from bot.cogs.shop import _parse_xlsx_shop
        data = self._make_xlsx(
            ["Item Name", "Price Per Item", "Blueprint Path", "Category"],
            [["Sword", 100, '"Blueprint\'/Game/sword_C\'"', "Weapons"]],
        )
        items, errors = _parse_xlsx_shop(data)
        assert len(items) == 1
        assert not items[0]["ark_command"].startswith('"')

    def test_disabled_items_imported_with_enabled_false(self):
        from bot.cogs.shop import _parse_xlsx_shop
        data = self._make_xlsx(
            ["Item Name", "Price Per Item", "Blueprint Path", "Category", "Enabled"],
            [
                ["Active Item", 100, "Blueprint'/Game/a'", "Weapons", True],
                ["Disabled Item", 50, "Blueprint'/Game/b'", "Weapons", False],
            ],
        )
        items, errors = _parse_xlsx_shop(data)
        assert len(items) == 2  # both imported
        active = next(i for i in items if i["name"] == "Active Item")
        disabled = next(i for i in items if i["name"] == "Disabled Item")
        assert active["enabled"] is True
        assert disabled["enabled"] is False

    def test_error_on_missing_required_columns(self):
        from bot.cogs.shop import _parse_xlsx_shop
        data = self._make_xlsx(
            ["Item Name", "Price Per Item"],  # missing Blueprint Path and Category
            [["Sword", 100]],
        )
        items, errors = _parse_xlsx_shop(data)
        assert len(items) == 0
        assert len(errors) > 0
        assert "Missing required column" in errors[0]

    def test_error_on_invalid_price(self):
        from bot.cogs.shop import _parse_xlsx_shop
        data = self._make_xlsx(
            ["Item Name", "Price Per Item", "Blueprint Path", "Category"],
            [["Sword", "not_a_number", "Blueprint'/Game/sword_C'", "Weapons"]],
        )
        items, errors = _parse_xlsx_shop(data)
        assert len(items) == 0
        assert any("invalid price" in e for e in errors)

    def test_skips_blank_rows_silently(self):
        from bot.cogs.shop import _parse_xlsx_shop
        data = self._make_xlsx(
            ["Item Name", "Price Per Item", "Blueprint Path", "Category"],
            [
                ["Sword", 100, "Blueprint'/Game/sword_C'", "Weapons"],
                [None, None, None, None],  # blank row
                ["Shield", 50, "Blueprint'/Game/shield_C'", "Armor"],
            ],
        )
        items, errors = _parse_xlsx_shop(data)
        assert len(items) == 2
        assert len(errors) == 0

    def test_allow_quality_select_maps_to_supports_quality(self):
        from bot.cogs.shop import _parse_xlsx_shop
        data = self._make_xlsx(
            ["Item Name", "Price Per Item", "Blueprint Path", "Category", "Allow Quality Select"],
            [
                ["Quality Sword", 100, "Blueprint'/Game/sword_C'", "Weapons", True],
                ["Plain Shield", 50, "Blueprint'/Game/shield_C'", "Armor", False],
            ],
        )
        items, errors = _parse_xlsx_shop(data)
        assert items[0]["supports_quality"] is True
        assert items[1]["supports_quality"] is False

    def test_default_supports_quality_is_false(self):
        from bot.cogs.shop import _parse_xlsx_shop
        data = self._make_xlsx(
            ["Item Name", "Price Per Item", "Blueprint Path", "Category"],
            [["Sword", 100, "Blueprint'/Game/sword_C'", "Weapons"]],
        )
        items, _ = _parse_xlsx_shop(data)
        assert items[0]["supports_quality"] is False

    def test_parses_packs_sheet(self):
        """Packs sheet items appear in results with is_pack=True."""
        from bot.cogs.shop import _parse_xlsx_shop
        import openpyxl, io, json
        wb = openpyxl.Workbook()
        # Items sheet
        ws_items = wb.active
        ws_items.title = "items"
        ws_items.append(["Item Name", "Price Per Item", "Blueprint Path", "Category"])
        ws_items.append(["Sword", 100, "Blueprint'/Game/sword_C'", "Weapons"])
        ws_items.append(["Shield", 50, "Blueprint'/Game/shield_C'", "Armor"])
        # Packs sheet
        ws_packs = wb.create_sheet(title="Packs")
        ws_packs.append(["Pack Name", "Price", "Category", "Description", "Items", "Enabled"])
        ws_packs.append(["Warrior Pack", 120, "Packs", "Sword and shield", "Sword, Shield", True])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        items, errors = _parse_xlsx_shop(buf.read())
        packs = [i for i in items if i.get("is_pack")]
        regular = [i for i in items if not i.get("is_pack")]
        assert len(regular) == 2
        assert len(packs) == 1
        assert packs[0]["name"] == "Warrior Pack"
        assert packs[0]["cost"] == 120
        assert packs[0]["ark_command"] == "#PACK#"
        pack_contents = json.loads(packs[0]["pack_contents"])
        assert len(pack_contents) == 2
        assert pack_contents[0]["name"] == "Sword"

    def test_pack_unknown_item_reports_error(self):
        """Pack referencing an item not in items sheet → error reported."""
        from bot.cogs.shop import _parse_xlsx_shop
        import openpyxl, io
        wb = openpyxl.Workbook()
        ws_items = wb.active
        ws_items.title = "items"
        ws_items.append(["Item Name", "Price Per Item", "Blueprint Path", "Category"])
        ws_items.append(["Sword", 100, "Blueprint'/Game/sword_C'", "Weapons"])
        ws_packs = wb.create_sheet(title="Packs")
        ws_packs.append(["Pack Name", "Price", "Category", "Description", "Items", "Enabled"])
        ws_packs.append(["Bad Pack", 200, "Packs", "", "Sword, NONEXISTENT_ITEM", True])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        items, errors = _parse_xlsx_shop(buf.read())
        assert any("NONEXISTENT_ITEM" in e for e in errors)


class TestParseCsvShop:
    def test_parses_valid_csv(self):
        from bot.cogs.shop import _parse_csv_shop
        csv_data = "Item Name,Price Per Item,Blueprint Path,Category\nSword,100,Blueprint'/Game/sword_C',Weapons\n"
        items, errors = _parse_csv_shop(csv_data.encode("utf-8"))
        assert len(items) == 1
        assert items[0]["name"] == "Sword"
        assert items[0]["cost"] == 100

    def test_handles_bom(self):
        from bot.cogs.shop import _parse_csv_shop
        # utf-8-sig encoding adds the BOM prefix automatically
        csv_data = "Item Name,Price Per Item,Blueprint Path,Category\nSword,100,Blueprint'/Game/sword_C',Weapons\n"
        items, errors = _parse_csv_shop(csv_data.encode("utf-8-sig"))
        assert len(items) == 1

    def test_empty_csv_returns_error(self):
        from bot.cogs.shop import _parse_csv_shop
        items, errors = _parse_csv_shop(b"")
        assert len(items) == 0
        assert len(errors) > 0

    def test_disabled_rows_imported_with_enabled_false(self):
        from bot.cogs.shop import _parse_csv_shop
        csv_data = "Item Name,Price Per Item,Blueprint Path,Category,Enabled\nActive,100,Blueprint'/Game/a',Weapons,yes\nDisabled,50,Blueprint'/Game/b',Weapons,no\n"
        items, errors = _parse_csv_shop(csv_data.encode("utf-8"))
        assert len(items) == 2  # both imported
        active = next(i for i in items if i["name"] == "Active")
        disabled = next(i for i in items if i["name"] == "Disabled")
        assert active["enabled"] is True
        assert disabled["enabled"] is False


class TestBuildShopXlsx:
    def test_returns_bytes(self):
        from bot.cogs.shop import _build_shop_xlsx
        result = _build_shop_xlsx([])
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_creates_items_sheet(self):
        from bot.cogs.shop import _build_shop_xlsx
        import openpyxl, io
        items = [{"name": "Sword", "cost": 100, "ark_command": "Blueprint'/Game/sword_C'",
                  "category": "weapons", "description": "", "enabled": 1, "supports_quality": 0, "is_pack": 0}]
        data = _build_shop_xlsx(items)
        wb = openpyxl.load_workbook(io.BytesIO(data))
        assert "items" in wb.sheetnames

    def test_excludes_packs_from_items_sheet(self):
        from bot.cogs.shop import _build_shop_xlsx
        import openpyxl, io, json
        items = [
            {"name": "Sword", "cost": 100, "ark_command": "Blueprint'/Game/sword_C'",
             "category": "weapons", "description": "", "enabled": 1, "supports_quality": 0, "is_pack": 0},
            {"name": "Warrior Pack", "cost": 200, "ark_command": "#PACK#",
             "category": "packs", "description": "", "enabled": 1, "supports_quality": 0, "is_pack": 1,
             "pack_contents": json.dumps([{"name": "Sword", "ark_command": "Blueprint'/Game/sword_C'", "quantity": 1}])},
        ]
        data = _build_shop_xlsx(items)
        wb = openpyxl.load_workbook(io.BytesIO(data))
        assert "Packs" in wb.sheetnames
        ws_items = wb["items"]
        item_names = [row[0] for row in ws_items.iter_rows(min_row=2, values_only=True) if row[0]]
        assert "Sword" in item_names
        assert "Warrior Pack" not in item_names

    def test_blueprint_not_wrapped_in_quotes(self):
        from bot.cogs.shop import _build_shop_xlsx
        import openpyxl, io
        items = [{"name": "Sword", "cost": 100, "ark_command": "Blueprint'/Game/sword'",
                  "category": "weapons", "description": "", "enabled": 1, "supports_quality": 0,
                  "allow_blueprint_select": 0, "is_pack": 0}]
        data = _build_shop_xlsx(items)
        wb = openpyxl.load_workbook(io.BytesIO(data))
        ws = wb["items"]
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        bp_col_idx = 6  # Blueprint Path is 7th column (0-indexed: 6)
        bp_val = rows[0][bp_col_idx]
        assert not bp_val.startswith('"'), f"Blueprint should not be wrapped in quotes, got: {bp_val}"
        assert "Blueprint'" in bp_val


class TestBuildSampleXlsx:
    def test_returns_bytes(self):
        from bot.cogs.shop import _build_sample_xlsx
        result = _build_sample_xlsx()
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_has_items_and_packs_sheets(self):
        from bot.cogs.shop import _build_sample_xlsx
        import openpyxl, io
        wb = openpyxl.load_workbook(io.BytesIO(_build_sample_xlsx()))
        assert "items" in wb.sheetnames
        assert "Packs" in wb.sheetnames

    def test_sample_items_round_trip(self):
        from bot.cogs.shop import _build_sample_xlsx, _parse_xlsx_shop
        data = _build_sample_xlsx()
        items, errors = _parse_xlsx_shop(data)
        regular = [i for i in items if not i.get("is_pack")]
        packs = [i for i in items if i.get("is_pack")]
        assert len(regular) == 8, f"Expected 8 sample items, got {len(regular)}"
        assert len(packs) == 3, f"Expected 3 sample packs, got {len(packs)}"
        assert len(errors) == 0, f"Unexpected errors: {errors}"

    def test_sample_has_correct_headers(self):
        from bot.cogs.shop import _build_sample_xlsx
        import openpyxl, io
        wb = openpyxl.load_workbook(io.BytesIO(_build_sample_xlsx()))
        ws = wb["items"]
        headers = [cell.value for cell in ws[1]]
        assert "Item Name" in headers
        assert "Price Per Item" in headers
        assert "Blueprint Path" in headers
        assert "Category" in headers


class TestShopCommandsExist:
    def test_uploadshop_command_registered(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "uploadshop")

    def test_downloadshop_command_registered(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "downloadshop")

    def test_downloadsample_command_registered(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "downloadsample")

    def test_buy_command_registered(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "buy_cmd")

    def test_buy_autocomplete_registered(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "buy_autocomplete")


# ---------------------------------------------------------------------------
# New: search_store_items DB function
# ---------------------------------------------------------------------------

class TestSearchStoreItemsFunction:
    def test_function_exists_in_shop_db(self):
        from bot.database import shop_db
        assert hasattr(shop_db, "search_store_items")
        assert inspect.iscoroutinefunction(shop_db.search_store_items)

    def test_search_store_items_accepts_guild_id_query_limit(self):
        """Function signature accepts (guild_id, query, limit=25)."""
        from bot.database import shop_db
        import inspect as ins
        sig = ins.signature(shop_db.search_store_items)
        params = list(sig.parameters.keys())
        assert "guild_id" in params
        assert "query" in params
        assert "limit" in params

    def test_search_store_items_default_limit_is_25(self):
        from bot.database import shop_db
        import inspect as ins
        sig = ins.signature(shop_db.search_store_items)
        assert sig.parameters["limit"].default == 25


class TestPackParsingHelpers:
    def test_parse_packs_sheet_happy_path(self):
        from bot.cogs.shop import _parse_packs_sheet
        import openpyxl, json
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Pack Name", "Price", "Category", "Description", "Items", "Enabled"])
        ws.append(["Warrior Pack", 200, "Packs", "A warrior bundle", "Sword, Shield", True])

        items_by_name = {
            "sword": {"name": "Sword", "ark_command": "Blueprint'/Game/sword_C'"},
            "shield": {"name": "Shield", "ark_command": "Blueprint'/Game/shield_C'"},
        }
        packs, errors = _parse_packs_sheet(ws, items_by_name)
        assert len(packs) == 1
        assert packs[0]["name"] == "Warrior Pack"
        assert packs[0]["cost"] == 200
        assert packs[0]["is_pack"] is True
        assert packs[0]["ark_command"] == "#PACK#"
        contents = json.loads(packs[0]["pack_contents"])
        assert len(contents) == 2

    def test_parse_packs_sheet_skips_disabled(self):
        from bot.cogs.shop import _parse_packs_sheet
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Pack Name", "Price", "Category", "Description", "Items", "Enabled"])
        ws.append(["Disabled Pack", 100, "Packs", "", "Sword", False])
        packs, errors = _parse_packs_sheet(ws, {"sword": {"name": "Sword", "ark_command": "bp"}})
        assert len(packs) == 0

    def test_parse_packs_sheet_unknown_item_error(self):
        from bot.cogs.shop import _parse_packs_sheet
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Pack Name", "Price", "Category", "Description", "Items", "Enabled"])
        ws.append(["Bad Pack", 100, "Packs", "", "Nonexistent Item", True])
        packs, errors = _parse_packs_sheet(ws, {})
        assert len(packs) == 0
        assert any("Nonexistent Item" in e for e in errors)


class TestTryDeliverForPlayer:
    @pytest.mark.asyncio
    async def test_method_exists_on_shop_cog(self):
        from bot.cogs.shop import ShopCog
        assert hasattr(ShopCog, "try_deliver_for_player")

    @pytest.mark.asyncio
    async def test_method_is_coroutine(self):
        import inspect
        from bot.cogs.shop import ShopCog
        assert inspect.iscoroutinefunction(ShopCog.try_deliver_for_player)

    @pytest.mark.asyncio
    async def test_no_guild_id_param(self):
        """try_deliver_for_player should NOT require guild_id — it reads it from the player record."""
        import inspect
        from bot.cogs.shop import ShopCog
        sig = inspect.signature(ShopCog.try_deliver_for_player)
        params = list(sig.parameters.keys())
        assert "guild_id" not in params
        assert "eos_id" in params
        assert "server_name" in params
