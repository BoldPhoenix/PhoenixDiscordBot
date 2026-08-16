"""
Tests for Mod Management UX enhancements.
Following Jeffrey Snover methodology: No mocks, real implementations only.
"""

import pytest
import discord
from discord.ui import Button, Select


class TestModSearchResultsView:
    """Tests for the paginated search results view."""

    @pytest.mark.asyncio
    async def test_view_has_first_last_buttons(self):
        """Search results view has First/Last navigation buttons."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [{"mod_id": i, "name": f"Mod {i}"} for i in range(20)]
        view = ModSearchResultsView(results, "test", user_id=12345)

        button_labels = [b.label for b in view.children if isinstance(b, Button)]
        assert "⏮ First" in button_labels
        assert "Last ⏭" in button_labels

    @pytest.mark.asyncio
    async def test_view_has_sort_dropdown(self):
        """Search results view has sort dropdown with all options."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [{"mod_id": i, "name": f"Mod {i}"} for i in range(5)]
        view = ModSearchResultsView(results, "test", user_id=12345)

        selects = [c for c in view.children if isinstance(c, Select)]
        assert len(selects) >= 1  # Sort select + Add select
        
        # Find the sort select
        sort_select = next((s for s in selects if s.placeholder == "Sort by..."), None)
        assert sort_select is not None

        option_values = [o.value for o in sort_select.options]
        assert "name_asc" in option_values
        assert "name_desc" in option_values
        assert "downloads_desc" in option_values
        assert "downloads_asc" in option_values
        assert "date_desc" in option_values
        assert "date_asc" in option_values
        assert "author_asc" in option_values
        assert "author_desc" in option_values
        assert "id_asc" in option_values
        assert "id_desc" in option_values

    @pytest.mark.asyncio
    async def test_default_sort_is_alphabetical(self):
        """Default sort is alphabetical (name_asc)."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [
            {"mod_id": 3, "name": "Zebra Mod"},
            {"mod_id": 1, "name": "Alpha Mod"},
            {"mod_id": 2, "name": "Beta Mod"},
        ]
        view = ModSearchResultsView(results, "test", user_id=12345)

        assert view.current_sort == "name_asc"
        assert view.results[0]["name"] == "Alpha Mod"
        assert view.results[1]["name"] == "Beta Mod"
        assert view.results[2]["name"] == "Zebra Mod"

    @pytest.mark.asyncio
    async def test_pagination_calculates_correctly(self):
        """Pagination calculates total pages correctly."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [{"mod_id": i, "name": f"Mod {i}"} for i in range(23)]
        view = ModSearchResultsView(results, "test", user_id=12345, mods_per_page=5)

        assert view.total_pages == 5

    @pytest.mark.asyncio
    async def test_user_id_stored_for_validation(self):
        """User ID is stored for interaction validation."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [{"mod_id": 1, "name": "Test"}]
        view = ModSearchResultsView(results, "test", user_id=12345)

        assert view.user_id == 12345

    @pytest.mark.asyncio
    async def test_sort_results_by_downloads_desc(self):
        """Sorting by downloads descending works correctly."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [
            {"mod_id": 1, "name": "Low", "download_count": 100},
            {"mod_id": 2, "name": "High", "download_count": 1000},
            {"mod_id": 3, "name": "Mid", "download_count": 500},
        ]
        view = ModSearchResultsView(results, "test", user_id=12345)
        sorted_results = view._sort_results(results.copy(), "downloads_desc")

        assert sorted_results[0]["name"] == "High"
        assert sorted_results[1]["name"] == "Mid"
        assert sorted_results[2]["name"] == "Low"

    @pytest.mark.asyncio
    async def test_sort_results_by_downloads_asc(self):
        """Sorting by downloads ascending works correctly."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [
            {"mod_id": 1, "name": "Low", "download_count": 100},
            {"mod_id": 2, "name": "High", "download_count": 1000},
            {"mod_id": 3, "name": "Mid", "download_count": 500},
        ]
        view = ModSearchResultsView(results, "test", user_id=12345)
        sorted_results = view._sort_results(results.copy(), "downloads_asc")

        assert sorted_results[0]["name"] == "Low"
        assert sorted_results[1]["name"] == "Mid"
        assert sorted_results[2]["name"] == "High"

    @pytest.mark.asyncio
    async def test_sort_results_by_date_desc(self):
        """Sorting by date descending works correctly."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [
            {"mod_id": 1, "name": "Old", "date_modified": "2024-01-01"},
            {"mod_id": 2, "name": "New", "date_modified": "2024-12-01"},
            {"mod_id": 3, "name": "Mid", "date_modified": "2024-06-01"},
        ]
        view = ModSearchResultsView(results, "test", user_id=12345)
        sorted_results = view._sort_results(results.copy(), "date_desc")

        assert sorted_results[0]["name"] == "New"
        assert sorted_results[1]["name"] == "Mid"
        assert sorted_results[2]["name"] == "Old"

    @pytest.mark.asyncio
    async def test_sort_results_by_author_asc(self):
        """Sorting by author ascending works correctly."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [
            {"mod_id": 1, "name": "Mod1", "author": "Zebra"},
            {"mod_id": 2, "name": "Mod2", "author": "Alpha"},
            {"mod_id": 3, "name": "Mod3", "author": "Beta"},
        ]
        view = ModSearchResultsView(results, "test", user_id=12345)
        sorted_results = view._sort_results(results.copy(), "author_asc")

        assert sorted_results[0]["author"] == "Alpha"
        assert sorted_results[1]["author"] == "Beta"
        assert sorted_results[2]["author"] == "Zebra"

    @pytest.mark.asyncio
    async def test_sort_results_by_mod_id_asc(self):
        """Sorting by mod ID ascending works correctly."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [
            {"mod_id": 999, "name": "High ID"},
            {"mod_id": 100, "name": "Low ID"},
            {"mod_id": 500, "name": "Mid ID"},
        ]
        view = ModSearchResultsView(results, "test", user_id=12345)
        sorted_results = view._sort_results(results.copy(), "id_asc")

        assert sorted_results[0]["mod_id"] == 100
        assert sorted_results[1]["mod_id"] == 500
        assert sorted_results[2]["mod_id"] == 999

    @pytest.mark.asyncio
    async def test_sort_results_by_mod_id_desc(self):
        """Sorting by mod ID descending works correctly."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [
            {"mod_id": 999, "name": "High ID"},
            {"mod_id": 100, "name": "Low ID"},
            {"mod_id": 500, "name": "Mid ID"},
        ]
        view = ModSearchResultsView(results, "test", user_id=12345)
        sorted_results = view._sort_results(results.copy(), "id_desc")

        assert sorted_results[0]["mod_id"] == 999
        assert sorted_results[1]["mod_id"] == 500
        assert sorted_results[2]["mod_id"] == 100

    @pytest.mark.asyncio
    async def test_create_embed_shows_correct_count(self):
        """Embed shows correct mod count."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [{"mod_id": i, "name": f"Mod {i}"} for i in range(15)]
        view = ModSearchResultsView(results, "test", user_id=12345, mods_per_page=5)

        embed = view.create_embed()

        assert "15 mods" in embed.description

    @pytest.mark.asyncio
    async def test_navigation_buttons_initial_state(self):
        """Navigation buttons start in correct state on first page."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [{"mod_id": i, "name": f"Mod {i}"} for i in range(15)]
        view = ModSearchResultsView(results, "test", user_id=12345, mods_per_page=5)

        assert view.current_page == 0
        assert view.first_button.disabled is True
        assert view.prev_button.disabled is True
        assert view.next_button.disabled is False
        assert view.last_button.disabled is False


class TestModSearchAddButton:
    """Tests for Add to Server functionality in search results."""

    @pytest.mark.asyncio
    async def test_search_results_have_add_select(self):
        """Search results have an Add to Server select menu."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [
            {"mod_id": 1, "name": "Mod 1"},
            {"mod_id": 2, "name": "Mod 2"},
        ]
        view = ModSearchResultsView(results, "test", user_id=12345)

        add_selects = [s for s in view.children if isinstance(s, Select) and "Add" in (s.placeholder or "")]
        assert len(add_selects) >= 1

    @pytest.mark.asyncio
    async def test_add_select_has_mod_options(self):
        """Add select has options for each mod on current page."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [
            {"mod_id": 1, "name": "Alpha Mod"},
            {"mod_id": 2, "name": "Beta Mod"},
        ]
        view = ModSearchResultsView(results, "test", user_id=12345)

        add_selects = [s for s in view.children if isinstance(s, Select) and "Add" in (s.placeholder or "")]
        if add_selects:
            options = add_selects[0].options
            assert len(options) == 2
            option_values = [o.value for o in options]
            assert "1" in option_values
            assert "2" in option_values

    @pytest.mark.asyncio
    async def test_add_button_custom_id_contains_mod_id(self):
        """Add button custom_id contains the mod ID for identification."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [{"mod_id": 12345, "name": "Test Mod"}]
        view = ModSearchResultsView(results, "test", user_id=12345)

        add_buttons = [b for b in view.children if isinstance(b, Button) and "Add" in (b.label or "")]
        if add_buttons:
            assert "12345" in (add_buttons[0].custom_id or "")


class TestModMainView:
    """Tests for the main mod management view."""

    @pytest.mark.asyncio
    async def test_main_view_has_three_action_buttons(self):
        """Main view has View, Add, Remove buttons."""
        from bot.cogs.mod_management import ModMainView

        class MinimalBot:
            pass

        class MinimalUser:
            id = 12345
            name = "TestUser"
            display_name = "TestUser"

        view = ModMainView(guild_id=12345, user=MinimalUser(), bot=MinimalBot())

        button_labels = [b.label for b in view.children if isinstance(b, Button)]
        assert "View Mods" in button_labels
        assert "Add Mod" in button_labels
        assert "Remove Mod" in button_labels
        assert len(button_labels) == 3  # Only 3 buttons now


class TestAddSelectUpdates:
    """Tests for add select updating on page changes."""

    @pytest.mark.asyncio
    async def test_add_select_updates_on_page_change(self):
        """Add select updates when page changes."""
        from bot.cogs.mod_management import ModSearchResultsView

        # Create mods with names that sort predictably (alphabetical)
        results = [
            {"mod_id": 100, "name": "Alpha"},
            {"mod_id": 200, "name": "Beta"},
            {"mod_id": 300, "name": "Gamma"},
            {"mod_id": 400, "name": "Delta"},
            {"mod_id": 500, "name": "Epsilon"},
            {"mod_id": 600, "name": "Zeta"},
            {"mod_id": 700, "name": "Eta"},
            {"mod_id": 800, "name": "Theta"},
        ]
        view = ModSearchResultsView(results, "test", user_id=12345, mods_per_page=5)

        # Get initial add select options (page 0: Alpha, Beta, Delta, Epsilon, Eta)
        add_selects = [s for s in view.children if isinstance(s, Select) and "Add" in (s.placeholder or "")]
        assert len(add_selects) >= 1
        initial_values = [o.value for o in add_selects[0].options]
        assert "100" in initial_values  # Alpha is on page 0
        assert "600" not in initial_values  # Zeta is not on page 0

        # Simulate page change
        view.current_page = 1
        view._create_add_select()

        # Get updated add select options (page 1: Gamma, Theta, Zeta)
        add_selects = [s for s in view.children if isinstance(s, Select) and "Add" in (s.placeholder or "")]
        updated_values = [o.value for o in add_selects[0].options]
        assert "100" not in updated_values  # Alpha is not on page 1
        assert "600" in updated_values  # Zeta is on page 1


class TestAllSortOptions:
    """Tests for all sort options."""

    @pytest.mark.asyncio
    async def test_all_sort_options_work(self):
        """All 10 sort options produce valid sorted results."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [
            {"mod_id": 3, "name": "Zebra", "author": "Charlie", "download_count": 100, "date_modified": "2024-01-01"},
            {"mod_id": 1, "name": "Alpha", "author": "Alice", "download_count": 300, "date_modified": "2024-03-01"},
            {"mod_id": 2, "name": "Beta", "author": "Bob", "download_count": 200, "date_modified": "2024-02-01"},
        ]

        sort_keys = [
            "name_asc", "name_desc",
            "downloads_asc", "downloads_desc",
            "date_asc", "date_desc",
            "author_asc", "author_desc",
            "id_asc", "id_desc",
        ]

        for sort_key in sort_keys:
            view = ModSearchResultsView(results, "test", user_id=12345)
            sorted_results = view._sort_results(results.copy(), sort_key)
            assert len(sorted_results) == 3, f"Sort {sort_key} lost results"


class TestEmptyResults:
    """Tests for edge cases with empty or minimal results."""

    @pytest.mark.asyncio
    async def test_empty_results_creates_valid_view(self):
        """View handles empty results gracefully."""
        from bot.cogs.mod_management import ModSearchResultsView

        view = ModSearchResultsView([], "test", user_id=12345)

        assert view.total_pages == 1
        embed = view.create_embed()
        assert embed is not None

    @pytest.mark.asyncio
    async def test_single_result_creates_valid_view(self):
        """View handles single result correctly."""
        from bot.cogs.mod_management import ModSearchResultsView

        results = [{"mod_id": 1, "name": "Only Mod"}]
        view = ModSearchResultsView(results, "test", user_id=12345)

        assert view.total_pages == 1
        embed = view.create_embed()
        assert "1 mods" in embed.description


# ---------------------------------------------------------------------------
# ModListView — embed field length (regression: Discord 1024-char field limit)
# ---------------------------------------------------------------------------

class TestModListViewEmbedLength:
    """Regression: ModListView.create_embed() must not exceed Discord's 1024-char field limit."""

    @pytest.mark.asyncio
    async def test_create_embed_no_field_exceeds_1024_chars(self):
        """With 10 mods that have long names, no embed field value exceeds 1024 chars.

        Each mod line: '**N.** [Very Long Mod Name...](url) (`id`)' ~ 120+ chars.
        10 × 120 = 1200 chars → would overflow a single add_field() call.
        The fix moves the list to embed.description (limit 4096) or splits across fields.
        """
        from bot.cogs.mod_management import ModListView

        long_name = "A" * 60  # 60-char mod name, realistic worst-case
        mod_ids = [str(900000 + i) for i in range(10)]
        mod_info = {mid: long_name for mid in mod_ids}

        view = ModListView(
            mod_ids=mod_ids,
            mod_info=mod_info,
            server_name="TestServer",
            user_id=12345,
            mods_per_page=10,
        )
        embed = view.create_embed()

        for field in embed.fields:
            assert len(field.value) <= 1024, (
                f"Embed field '{field.name}' value is {len(field.value)} chars, "
                f"exceeds Discord's 1024-char limit."
            )

    @pytest.mark.asyncio
    async def test_create_embed_description_within_discord_limit(self):
        """Embed description (if used for mod list) must stay within 4096 chars."""
        from bot.cogs.mod_management import ModListView

        long_name = "A" * 60
        mod_ids = [str(900000 + i) for i in range(10)]
        mod_info = {mid: long_name for mid in mod_ids}

        view = ModListView(
            mod_ids=mod_ids,
            mod_info=mod_info,
            server_name="TestServer",
            user_id=12345,
            mods_per_page=10,
        )
        embed = view.create_embed()

        if embed.description:
            assert len(embed.description) <= 4096

    @pytest.mark.asyncio
    async def test_create_embed_still_shows_all_mods_on_page(self):
        """Each mod on the current page must appear somewhere in the embed."""
        from bot.cogs.mod_management import ModListView

        mod_ids = [str(900000 + i) for i in range(5)]
        mod_info = {mid: f"Mod {mid}" for mid in mod_ids}

        view = ModListView(
            mod_ids=mod_ids,
            mod_info=mod_info,
            server_name="TestServer",
            user_id=12345,
            mods_per_page=5,
        )
        embed = view.create_embed()

        # All mod IDs should appear somewhere in description or fields
        embed_text = embed.description or ""
        for field in embed.fields:
            embed_text += field.value or ""

        for mid in mod_ids:
            assert mid in embed_text, f"Mod {mid} missing from embed output"


# ---------------------------------------------------------------------------
# Bug: ModListView URLs — must use website_url (slug) not raw numeric mod ID
# ---------------------------------------------------------------------------

class TestModListViewUrlFix:
    @pytest.mark.asyncio
    async def test_create_embed_uses_slug_url_when_provided(self):
        """create_embed must use slug-based URL from mod_info, not raw numeric ID.

        Bug: _get_mod_names() stored only the name string; create_embed() then
        built URLs as /mods/{numeric_id}. Fix: store {"name": ..., "url": ...}.
        """
        from bot.cogs.mod_management import ModListView

        mod_ids = ["2959149"]
        mod_info = {
            "2959149": {
                "name": "Primal Fear",
                "url": "https://www.curseforge.com/ark-survival-ascended/mods/primalfear",
            }
        }
        view = ModListView(mod_ids=mod_ids, mod_info=mod_info, server_name="Test", user_id=12345)
        embed = view.create_embed()

        # The markdown link must be [name](slug_url), not [dict_repr](numeric_id_url)
        assert "(https://www.curseforge.com/ark-survival-ascended/mods/primalfear)" in embed.description, (
            "create_embed must use the slug URL as the hyperlink href, not the numeric ID URL. "
            "Expected '(https://.../mods/primalfear)' in embed description but got numeric ID URL."
        )
        assert "(https://www.curseforge.com/ark-survival-ascended/mods/2959149)" not in embed.description, (
            "create_embed must NOT use the numeric mod ID as the URL. Use website_url (slug) instead."
        )

    @pytest.mark.asyncio
    async def test_get_mod_names_returns_dict_with_url_key(self, initialized_db):
        """_get_mod_names must return {mod_id: {'name': ..., 'url': ...}} format."""
        from bot.cogs.mod_management import ModListView

        # mod 999999999 won't be in DB — exercises the fallback branch
        result = await ModListView._get_mod_names(["999999999"])
        info = result.get("999999999", {})
        assert isinstance(info, dict), (
            "_get_mod_names must return dict of dicts {mod_id: {name, url}}, "
            "not {mod_id: name_str}."
        )
        assert "name" in info, "Each mod entry must have 'name' key"
        assert "url" in info, "Each mod entry must have 'url' key"

    @pytest.mark.asyncio
    async def test_remove_view_create_embed_uses_slug_url(self):
        """ModRemoveView.create_embed must also use slug URL, not numeric ID."""
        from bot.cogs.mod_management import ModRemoveView

        mod_ids = ["2959149"]
        mod_info = {
            "2959149": {
                "name": "Primal Fear",
                "url": "https://www.curseforge.com/ark-survival-ascended/mods/primalfear",
            }
        }
        view = ModRemoveView(
            mod_ids=mod_ids, mod_info=mod_info,
            server_name="Test", guild_id=123, user_id=12345,
        )
        embed = await view.create_embed()
        embed_text = embed.description or ""
        for f in embed.fields:
            embed_text += f.value or ""
        assert "(https://www.curseforge.com/ark-survival-ascended/mods/primalfear)" in embed_text, (
            "ModRemoveView.create_embed must use slug URL as the hyperlink href, not numeric ID URL."
        )
        assert "(https://www.curseforge.com/ark-survival-ascended/mods/2959149)" not in embed_text, (
            "ModRemoveView.create_embed must NOT use numeric mod ID as the URL."
        )


# ---------------------------------------------------------------------------
# Bug: ModListView missing back button after create_embed() rewrite
# ---------------------------------------------------------------------------

class TestModListViewBackButton:
    @pytest.mark.asyncio
    async def test_has_back_button_when_guild_id_and_bot_provided(self):
        """ModListView must show a Back button when guild_id and bot are provided."""
        from bot.cogs.mod_management import ModListView

        class MinimalBot:
            pass

        view = ModListView(
            mod_ids=["123"],
            mod_info={"123": {"name": "Test Mod", "url": None}},
            server_name="Test",
            user_id=12345,
            guild_id=999,
            bot=MinimalBot(),
        )
        button_labels = [b.label for b in view.children if isinstance(b, Button)]
        assert any("Back" in (lbl or "") for lbl in button_labels), (
            "ModListView must have a Back button when guild_id and bot are provided. "
            "The back button was lost during the create_embed() rewrite."
        )

    @pytest.mark.asyncio
    async def test_no_crash_without_guild_id(self):
        """ModListView must not crash when no guild_id provided (backward compat)."""
        from bot.cogs.mod_management import ModListView

        view = ModListView(
            mod_ids=["123"],
            mod_info={"123": "Test Mod"},  # legacy string format
            server_name="Test",
            user_id=12345,
        )
        assert view is not None

    def test_create_factory_accepts_guild_id_and_bot(self):
        """ModListView.create classmethod must accept guild_id and bot parameters."""
        import inspect
        from bot.cogs.mod_management import ModListView

        sig = inspect.signature(ModListView.create)
        assert "guild_id" in sig.parameters, (
            "ModListView.create must accept guild_id for back-button support."
        )
        assert "bot" in sig.parameters, (
            "ModListView.create must accept bot for back-button support."
        )


# ---------------------------------------------------------------------------
# Bug: Add Mod button opens search modal instead of direct ID entry modal
# ---------------------------------------------------------------------------

class TestAddModButtonUsesAddModal:
    def test_show_add_modal_uses_add_mod_modal(self):
        """_show_add_modal must open AddModModal (direct ID entry), not search modal.

        Bug: _show_add_modal was changed to call ModSearchInputModal (search window)
        instead of AddModModal (direct mod ID entry). Fix: revert to AddModModal.
        """
        import inspect
        from bot.cogs.mod_management import ModActionButton

        source = inspect.getsource(ModActionButton._show_add_modal)
        assert "AddModModal" in source, (
            "_show_add_modal must use AddModModal for direct mod ID entry. "
            "The button opens a search window instead of a single-ID entry modal."
        )

    def test_multi_server_uses_add_mod_action_not_add_mod_search(self):
        """Multi-server path must use action='add_mod', not 'add_mod_search'.

        Bug: ServerSelectMenu was called with action='add_mod_search', which is
        not handled in ServerSelectMenu.callback — silently does nothing.
        """
        import inspect
        from bot.cogs.mod_management import ModActionButton

        source = inspect.getsource(ModActionButton._show_add_modal)
        assert "add_mod_search" not in source, (
            "ServerSelectMenu must use action='add_mod', not 'add_mod_search'. "
            "'add_mod_search' has no handler in ServerSelectMenu.callback."
        )
