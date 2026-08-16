"""
Tests for shopcfg_gui.py — ShopCfgCog, ShopItemsView, AddShopItemModal,
AddShopItemConfirmView, EditItemSelectView, EditShopItemModal, EditShopItemResultView,
RemoveItemSelectView, RemoveShopItemConfirmView, BackToShopItemsView, ShopSettingsModal.

Bugs caught by these tests:
1. AddShopItemModal had 6 TextInputs — Discord limit is 5
2. EditItemSelectView called without items arg + had duplicate @discord.ui.select
3. EditShopItemModal used default_value= (invalid) instead of default=
4. EditShopItemModal loop variable "item" shadowed self.item dict
5. RemoveItemSelectView @discord.ui.select had no options (empty select)
6. edit/remove/list buttons didn't fetch items before creating select views
7. ShopSettingsModal had two on_submit definitions; require_linked not in __init__
8. Every button opened new ephemeral message instead of reusing existing one
9. No quality/blueprint fields available when adding items
"""

import inspect
import pytest
import discord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cog():
    from types import SimpleNamespace
    return SimpleNamespace()


# ---------------------------------------------------------------------------
# AddShopItemModal — must have ≤ 5 TextInput fields (Discord limit)
# ---------------------------------------------------------------------------

class TestAddShopItemModalFieldCount:
    @pytest.mark.asyncio
    async def test_add_modal_has_at_most_five_text_inputs(self):
        """Discord modals only allow 5 components. AddShopItemModal must not exceed this."""
        from bot.cogs.shopcfg_gui import AddShopItemModal
        modal = AddShopItemModal(_make_cog())
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert len(text_inputs) <= 5, (
            f"AddShopItemModal has {len(text_inputs)} TextInputs but Discord only allows 5."
        )

    @pytest.mark.asyncio
    async def test_add_modal_has_required_fields(self):
        """name, cost, ark_command must all be present."""
        from bot.cogs.shopcfg_gui import AddShopItemModal
        modal = AddShopItemModal(_make_cog())
        assert hasattr(modal, "name")
        assert hasattr(modal, "cost")
        assert hasattr(modal, "ark_command")

    @pytest.mark.asyncio
    async def test_add_modal_accepts_cog_parameter(self):
        """AddShopItemModal must accept a cog parameter to allow navigation after submit."""
        from bot.cogs.shopcfg_gui import AddShopItemModal
        cog = _make_cog()
        modal = AddShopItemModal(cog)
        assert modal.cog is cog


# ---------------------------------------------------------------------------
# AddShopItemConfirmView — must have quality/blueprint toggle buttons
# ---------------------------------------------------------------------------

class TestAddShopItemConfirmViewQualityBlueprint:
    def _make_view(self):
        from bot.cogs.shopcfg_gui import AddShopItemConfirmView
        return AddShopItemConfirmView(
            cog=_make_cog(),
            name="Test Item",
            description="A test item",
            cost=100,
            ark_command="Blueprint'/Game/Test.Test'",
            category="general",
            guild_id=123,
        )

    def test_confirm_view_has_quality_toggle(self):
        """AddShopItemConfirmView must expose quality toggle button."""
        view = self._make_view()
        assert hasattr(view, "toggle_quality_button"), (
            "AddShopItemConfirmView must have toggle_quality_button for setting supports_quality."
        )

    def test_confirm_view_has_blueprint_toggle(self):
        """AddShopItemConfirmView must expose blueprint select toggle button."""
        view = self._make_view()
        assert hasattr(view, "toggle_blueprint_button"), (
            "AddShopItemConfirmView must have toggle_blueprint_button for allow_blueprint_select."
        )

    def test_confirm_view_quality_defaults_off(self):
        """supports_quality defaults to False."""
        view = self._make_view()
        assert view.supports_quality is False

    def test_confirm_view_blueprint_defaults_off(self):
        """allow_blueprint_select defaults to False."""
        view = self._make_view()
        assert view.allow_blueprint_select is False

    def test_confirm_view_has_confirm_and_cancel_buttons(self):
        """Must have confirm and cancel buttons."""
        view = self._make_view()
        assert hasattr(view, "confirm")
        assert hasattr(view, "cancel")

    def test_confirm_view_build_embed_shows_quality_state(self):
        """_build_embed must reflect current quality/blueprint state."""
        view = self._make_view()
        embed = view._build_embed()
        field_names = [f.name for f in embed.fields]
        assert "Supports Quality" in field_names
        assert "Blueprint Select" in field_names


# ---------------------------------------------------------------------------
# EditItemSelectView — constructor must accept items list; no empty class select
# ---------------------------------------------------------------------------

class TestEditItemSelectViewConstructor:
    def test_constructor_accepts_items_parameter(self):
        """EditItemSelectView.__init__ must accept items list to populate options."""
        from bot.cogs.shopcfg_gui import EditItemSelectView
        sig = inspect.signature(EditItemSelectView.__init__)
        assert "items" in sig.parameters, (
            "EditItemSelectView.__init__ must accept 'items' parameter. "
            "The edit_item_button must fetch items and pass them in."
        )

    @pytest.mark.asyncio
    async def test_no_class_level_empty_select(self):
        """@discord.ui.select() with no options causes Discord error. Must not exist."""
        from bot.cogs.shopcfg_gui import EditItemSelectView
        source = inspect.getsource(EditItemSelectView)
        assert "@discord.ui.select()" not in source, (
            "EditItemSelectView must not use @discord.ui.select() with no options — "
            "Discord rejects empty selects. Use dynamic add_item() with options instead."
        )

    @pytest.mark.asyncio
    async def test_can_instantiate_with_items(self):
        """Must be instantiable with a list of items."""
        from bot.cogs.shopcfg_gui import EditItemSelectView
        items = [{"item_id": 1, "name": "Test Item"}]
        view = EditItemSelectView(_make_cog(), items)
        assert view is not None

    def test_back_button_returns_to_shop_items_not_main(self):
        """back_button must return to ShopItemsView, not the main ShopCfgMainView."""
        from bot.cogs.shopcfg_gui import EditItemSelectView, ShopItemsView
        source = inspect.getsource(EditItemSelectView.back_button)
        assert "ShopItemsView" in source, (
            "EditItemSelectView.back_button must navigate to ShopItemsView, not main menu."
        )


# ---------------------------------------------------------------------------
# EditShopItemModal — default= not default_value=; loop var must not shadow self.item
# ---------------------------------------------------------------------------

class TestEditShopItemModalDefaults:
    def test_uses_default_not_default_value(self):
        """discord.ui.TextInput uses default= not default_value=. Wrong kwarg silently breaks."""
        from bot.cogs.shopcfg_gui import EditShopItemModal
        source = inspect.getsource(EditShopItemModal.__init__)
        assert "default_value=" not in source, (
            "EditShopItemModal uses default_value= which is not a valid TextInput parameter. "
            "Use default= instead."
        )

    def test_loop_var_does_not_shadow_self_item(self):
        """'for item in [...]' would overwrite self.item (the dict). Must use different var name."""
        from bot.cogs.shopcfg_gui import EditShopItemModal
        source = inspect.getsource(EditShopItemModal.__init__)
        assert "for item in [" not in source, (
            "EditShopItemModal uses 'for item in [...]' which overwrites self.item (the dict). "
            "Rename the loop variable to e.g. 'field'."
        )

    @pytest.mark.asyncio
    async def test_can_instantiate_with_item_dict_and_cog(self):
        from bot.cogs.shopcfg_gui import EditShopItemModal
        item = {
            "item_id": 1,
            "guild_id": 123,
            "name": "Test",
            "description": "Desc",
            "cost": 100,
            "ark_command": "GiveItem ...",
            "category": "general",
            "enabled": 1,
        }
        modal = EditShopItemModal(item, _make_cog())
        assert modal.item["item_id"] == 1  # self.item must still be the dict


# ---------------------------------------------------------------------------
# EditShopItemResultView — new class for quality/blueprint toggles after edit
# ---------------------------------------------------------------------------

class TestEditShopItemResultView:
    def _make_view(self, supports_quality=False, allow_blueprint_select=False):
        from bot.cogs.shopcfg_gui import EditShopItemResultView
        return EditShopItemResultView(
            cog=_make_cog(),
            item_id=1,
            item_name="Test Item",
            supports_quality=supports_quality,
            allow_blueprint_select=allow_blueprint_select,
        )

    def test_result_view_exists(self):
        """EditShopItemResultView must exist in shopcfg_gui."""
        from bot.cogs import shopcfg_gui
        assert hasattr(shopcfg_gui, "EditShopItemResultView"), (
            "EditShopItemResultView class must exist to show quality/blueprint toggles after edit."
        )

    def test_result_view_has_quality_toggle(self):
        view = self._make_view()
        assert hasattr(view, "toggle_quality_button")

    def test_result_view_has_blueprint_toggle(self):
        view = self._make_view()
        assert hasattr(view, "toggle_blueprint_button")

    def test_result_view_has_back_button(self):
        view = self._make_view()
        assert hasattr(view, "back_button")

    def test_result_view_embed_shows_quality_state(self):
        view = self._make_view(supports_quality=True, allow_blueprint_select=False)
        embed = view._build_embed()
        field_names = [f.name for f in embed.fields]
        assert "Supports Quality" in field_names
        assert "Blueprint Select" in field_names

    def test_result_view_back_goes_to_shop_items(self):
        """back_button must navigate to ShopItemsView."""
        from bot.cogs.shopcfg_gui import EditShopItemResultView, ShopItemsView
        source = inspect.getsource(EditShopItemResultView.back_button)
        assert "ShopItemsView" in source


# ---------------------------------------------------------------------------
# RemoveItemSelectView — must accept items; no empty class-level select
# ---------------------------------------------------------------------------

class TestRemoveItemSelectViewConstructor:
    def test_constructor_accepts_items_parameter(self):
        """RemoveItemSelectView.__init__ must accept items to populate select options."""
        from bot.cogs.shopcfg_gui import RemoveItemSelectView
        sig = inspect.signature(RemoveItemSelectView.__init__)
        assert "items" in sig.parameters, (
            "RemoveItemSelectView.__init__ must accept 'items' parameter."
        )

    def test_no_class_level_empty_select(self):
        """@discord.ui.select() with no options causes Discord HTTP error."""
        from bot.cogs.shopcfg_gui import RemoveItemSelectView
        source = inspect.getsource(RemoveItemSelectView)
        assert "@discord.ui.select(\n        placeholder=" not in source or "options=" in source, (
            "RemoveItemSelectView @discord.ui.select() must have options. "
            "Use dynamic add_item() with a pre-fetched items list instead."
        )

    @pytest.mark.asyncio
    async def test_can_instantiate_with_items(self):
        from bot.cogs.shopcfg_gui import RemoveItemSelectView
        items = [{"item_id": 1, "name": "Test"}]
        view = RemoveItemSelectView(_make_cog(), items)
        assert view is not None

    def test_back_button_returns_to_shop_items_not_main(self):
        """back_button must return to ShopItemsView, not the main menu."""
        from bot.cogs.shopcfg_gui import RemoveItemSelectView, ShopItemsView
        source = inspect.getsource(RemoveItemSelectView.back_button)
        assert "ShopItemsView" in source


# ---------------------------------------------------------------------------
# ShopItemsView — toggle button removed; action buttons use edit_message
# ---------------------------------------------------------------------------

class TestShopItemsViewButtonSources:
    def _source(self, method_name):
        from bot.cogs.shopcfg_gui import ShopItemsView
        fn = getattr(ShopItemsView, method_name)
        fn = getattr(fn, "callback", fn)
        return inspect.getsource(fn)

    def test_edit_button_fetches_items(self):
        """edit_item_button must fetch items from DB before building EditItemSelectView."""
        source = self._source("edit_item_button")
        assert "get_store_items" in source, (
            "edit_item_button must call shop_db.get_store_items() to populate the select."
        )

    def test_remove_button_fetches_items(self):
        source = self._source("remove_item_button")
        assert "get_store_items" in source, (
            "remove_item_button must call shop_db.get_store_items() to populate the select."
        )

    def test_toggle_item_button_removed(self):
        """toggle_item_button is redundant with Edit Item and must be removed."""
        from bot.cogs.shopcfg_gui import ShopItemsView
        assert not hasattr(ShopItemsView, "toggle_item_button"), (
            "toggle_item_button must be removed from ShopItemsView — "
            "use Edit Item to enable/disable items instead."
        )

    def test_edit_button_uses_edit_message(self):
        """edit_item_button must use edit_message to reuse the existing ephemeral message."""
        source = self._source("edit_item_button")
        assert "edit_message" in source, (
            "edit_item_button must call edit_message (not send_message) to avoid creating "
            "a new ephemeral message on every click."
        )

    def test_remove_button_uses_edit_message(self):
        """remove_item_button must use edit_message to reuse the existing ephemeral message."""
        source = self._source("remove_item_button")
        assert "edit_message" in source, (
            "remove_item_button must call edit_message (not send_message)."
        )

    def test_list_button_uses_edit_message(self):
        """list_items_button must use edit_message to reuse the existing ephemeral message."""
        source = self._source("list_items_button")
        assert "edit_message" in source, (
            "list_items_button must call edit_message (not send_message)."
        )

    def test_build_embed_has_no_toggle_item_reference(self):
        """build_embed must not mention Toggle Item since the button is removed."""
        from bot.cogs.shopcfg_gui import ShopItemsView
        source = inspect.getsource(ShopItemsView.build_embed)
        assert "Toggle Item" not in source, (
            "ShopItemsView.build_embed still mentions Toggle Item which has been removed."
        )


# ---------------------------------------------------------------------------
# Item list display — item_id must not appear in list lines
# ---------------------------------------------------------------------------

class TestItemListNoItemId:
    def test_shop_items_view_list_embed_no_item_id(self):
        """_build_list_embed must not show item_id — it's an internal field."""
        from bot.cogs.shopcfg_gui import ShopItemsView
        source = inspect.getsource(ShopItemsView._build_list_embed)
        assert "item_id" not in source or "item['item_id']" not in source, (
            "_build_list_embed still shows item_id in the item listing. "
            "Remove it — item_id is internal and not useful to admins."
        )

    def test_pagination_view_build_embed_no_item_id(self):
        """ShopItemsPaginationView._build_embed must not show item_id."""
        from bot.cogs.shopcfg_gui import ShopItemsPaginationView
        source = inspect.getsource(ShopItemsPaginationView._build_embed)
        assert "item['item_id']" not in source, (
            "ShopItemsPaginationView._build_embed still shows item_id in the listing."
        )

    def test_pagination_back_goes_to_shop_items(self):
        """Pagination back button must return to ShopItemsView not main menu."""
        from bot.cogs.shopcfg_gui import ShopItemsPaginationView, ShopItemsView
        source = inspect.getsource(ShopItemsPaginationView.back_button)
        assert "ShopItemsView" in source, (
            "ShopItemsPaginationView.back_button must navigate to ShopItemsView."
        )


# ---------------------------------------------------------------------------
# ToggleItemSelectView — must NOT exist (removed as redundant)
# ---------------------------------------------------------------------------

class TestToggleItemSelectViewRemoved:
    def test_toggle_item_select_view_does_not_exist(self):
        """ToggleItemSelectView was removed as redundant — Edit Item handles enable/disable."""
        from bot.cogs import shopcfg_gui
        assert not hasattr(shopcfg_gui, "ToggleItemSelectView"), (
            "ToggleItemSelectView must be removed — use Edit Item to toggle enabled/disabled."
        )


# ---------------------------------------------------------------------------
# ShopSettingsModal — require_linked removed; one on_submit; ≤5 fields
# ---------------------------------------------------------------------------

class TestShopSettingsModalStructure:
    @pytest.mark.asyncio
    async def test_require_linked_field_removed(self):
        """require_linked must be removed from ShopSettingsModal — shop always requires it."""
        from bot.cogs.shopcfg_gui import ShopSettingsModal
        modal = ShopSettingsModal(guild_id=123)
        assert not hasattr(modal, "require_linked"), (
            "ShopSettingsModal must NOT have require_linked — shop always requires a linked "
            "account, exposing this field is misleading and risky."
        )

    def test_single_on_submit_definition(self):
        """Two on_submit defs — Python uses the last one. First is dead code."""
        from bot.cogs.shopcfg_gui import ShopSettingsModal
        source = inspect.getsource(ShopSettingsModal)
        count = source.count("async def on_submit")
        assert count == 1, (
            f"ShopSettingsModal has {count} on_submit definitions. "
            "Python uses only the last; the first is unreachable dead code. "
            "Consolidate into a single on_submit."
        )

    @pytest.mark.asyncio
    async def test_max_five_text_inputs(self):
        from bot.cogs.shopcfg_gui import ShopSettingsModal
        modal = ShopSettingsModal(guild_id=123)
        text_inputs = [c for c in modal.children if isinstance(c, discord.ui.TextInput)]
        assert len(text_inputs) <= 5, (
            f"ShopSettingsModal has {len(text_inputs)} TextInputs but Discord only allows 5."
        )

    @pytest.mark.asyncio
    async def test_has_enabled_and_items_per_page_fields(self):
        """Must keep core fields: enabled and items_per_page."""
        from bot.cogs.shopcfg_gui import ShopSettingsModal
        modal = ShopSettingsModal(guild_id=123)
        assert hasattr(modal, "enabled")
        assert hasattr(modal, "items_per_page")

    @pytest.mark.asyncio
    async def test_prefills_from_config(self):
        """Must prefill from existing config."""
        from bot.cogs.shopcfg_gui import ShopSettingsModal
        config = {"shop_enabled": False, "items_per_page": 10}
        modal = ShopSettingsModal(guild_id=123, config=config)
        assert modal.enabled.default == "no"
        assert modal.items_per_page.default == "10"


# ---------------------------------------------------------------------------
# ShopCfgMainView.shop_settings_button — must use create_embed() not build_embed()
# ---------------------------------------------------------------------------

class TestShopSettingsButtonMethod:
    """Regression: shop_settings_button called ShopSettingsView.build_embed() (doesn't
    exist) instead of instantiating the view and calling create_embed(), causing
    'This interaction failed' on every click."""

    def test_shop_settings_button_uses_create_embed_not_build_embed(self):
        """shop_settings_button must NOT call ShopSettingsView.build_embed."""
        import inspect
        from bot.cogs.shopcfg_gui import ShopCfgMainView
        source = inspect.getsource(ShopCfgMainView.shop_settings_button)
        assert "build_embed" not in source, (
            "shop_settings_button called ShopSettingsView.build_embed() which doesn't exist. "
            "Instantiate the view first, then call create_embed() on the instance."
        )
        assert "create_embed" in source, (
            "shop_settings_button must call create_embed() on a ShopSettingsView instance."
        )

    @pytest.mark.asyncio
    async def test_shop_settings_view_has_create_embed_not_build_embed(self):
        """ShopSettingsView must expose create_embed() as an async instance method."""
        from bot.cogs.shopcfg_gui import ShopSettingsView
        import inspect
        assert hasattr(ShopSettingsView, "create_embed"), (
            "ShopSettingsView must have create_embed() method."
        )
        assert not hasattr(ShopSettingsView, "build_embed"), (
            "ShopSettingsView.build_embed does not exist — callers must use create_embed()."
        )
        assert inspect.iscoroutinefunction(ShopSettingsView.create_embed), (
            "ShopSettingsView.create_embed must be async."
        )


# ---------------------------------------------------------------------------
# BackToShopItemsView — helper view for returning to items list
# ---------------------------------------------------------------------------

class TestBackToShopItemsView:
    def test_back_to_shop_items_view_exists(self):
        """BackToShopItemsView must exist as a helper for post-action navigation."""
        from bot.cogs import shopcfg_gui
        assert hasattr(shopcfg_gui, "BackToShopItemsView"), (
            "BackToShopItemsView must exist to let users return to items list after add/remove."
        )

    def test_back_to_shop_items_view_has_back_button(self):
        from bot.cogs.shopcfg_gui import BackToShopItemsView
        view = BackToShopItemsView(_make_cog())
        assert hasattr(view, "back_button")

    def test_back_button_navigates_to_shop_items_view(self):
        from bot.cogs.shopcfg_gui import BackToShopItemsView, ShopItemsView
        source = inspect.getsource(BackToShopItemsView.back_button)
        assert "ShopItemsView" in source
