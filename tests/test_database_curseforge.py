"""
Tests for CurseForge mod cache database operations.
"""

import pytest
import aiosqlite


class TestCurseforgeModsTable:
    @pytest.mark.asyncio
    async def test_table_created_on_init(self, initialized_db):
        """CurseForge mods table is created by initialize_database."""
        async with aiosqlite.connect(initialized_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='curseforge_mods'"
            )
            row = await cursor.fetchone()
        assert row is not None

    @pytest.mark.asyncio
    async def test_indexes_created(self, initialized_db):
        """Indexes on name and date_modified are created."""
        async with aiosqlite.connect(initialized_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='curseforge_mods'"
            )
            indexes = [row[0] for row in await cursor.fetchall()]
        assert "idx_mod_name_search" in indexes
        assert "idx_mod_updated" in indexes


class TestUpsertMod:
    @pytest.mark.asyncio
    async def test_insert_new_mod(self, initialized_db):
        """Insert a new mod into the cache."""
        from bot.database import curseforge_db

        result = await curseforge_db.upsert_mod(
            mod_id=12345,
            name="Test Mod",
            summary="A test mod",
            author="TestAuthor",
            download_count=1000,
        )
        assert result is True

        mod = await curseforge_db.get_mod_by_id(12345)
        assert mod is not None
        assert mod["name"] == "Test Mod"
        assert mod["author"] == "TestAuthor"
        assert mod["download_count"] == 1000

    @pytest.mark.asyncio
    async def test_update_existing_mod(self, initialized_db):
        """Update an existing mod in the cache."""
        from bot.database import curseforge_db

        await curseforge_db.upsert_mod(
            mod_id=99999,
            name="Old Name",
            download_count=100,
        )

        await curseforge_db.upsert_mod(
            mod_id=99999,
            name="New Name",
            download_count=500,
        )

        mod = await curseforge_db.get_mod_by_id(99999)
        assert mod["name"] == "New Name"
        assert mod["download_count"] == 500


class TestSearchMods:
    @pytest.mark.asyncio
    async def test_search_by_name(self, initialized_db):
        """Search for mods by partial name match."""
        from bot.database import curseforge_db

        await curseforge_db.upsert_mod(1, "Super Spyglass", author="A")
        await curseforge_db.upsert_mod(2, "Awesome Spyglass", author="B")
        await curseforge_db.upsert_mod(3, "Structures Plus", author="C")
        await curseforge_db.upsert_mod(4, "Dino Spyglass", author="D")

        results = await curseforge_db.search_mods("spyglass")
        assert len(results) == 3
        names = [r["name"] for r in results]
        assert "Super Spyglass" in names
        assert "Awesome Spyglass" in names
        assert "Dino Spyglass" in names
        assert "Structures Plus" not in names

    @pytest.mark.asyncio
    async def test_search_by_author(self, initialized_db):
        """Search for mods by author name."""
        from bot.database import curseforge_db

        await curseforge_db.upsert_mod(101, "Mod Alpha", author="Biggumzzz")
        await curseforge_db.upsert_mod(102, "Mod Beta", author="Biggumzzz")
        await curseforge_db.upsert_mod(103, "Mod Gamma", author="OtherAuthor")

        results = await curseforge_db.search_mods("Biggumzzz")
        assert len(results) == 2
        for r in results:
            assert r["author"] == "Biggumzzz"

    @pytest.mark.asyncio
    async def test_search_by_mod_id(self, initialized_db):
        """Search for mods by mod ID."""
        from bot.database import curseforge_db

        await curseforge_db.upsert_mod(939055, "ARKomatic", author="Biggumzzz")
        await curseforge_db.upsert_mod(123456, "Other Mod", author="Someone")

        results = await curseforge_db.search_mods("939055")
        assert len(results) == 1
        assert results[0]["mod_id"] == 939055
        assert results[0]["name"] == "ARKomatic"

    @pytest.mark.asyncio
    async def test_search_by_description(self, initialized_db):
        """Search for mods by description/summary."""
        from bot.database import curseforge_db

        await curseforge_db.upsert_mod(201, "Structures Mod", summary="Adds new structures and buildings")
        await curseforge_db.upsert_mod(202, "Dino Mod", summary="Adds new dinosaurs")
        await curseforge_db.upsert_mod(203, "Utility Mod", summary="Quality of life structures")

        results = await curseforge_db.search_mods("structures")
        assert len(results) == 2
        names = [r["name"] for r in results]
        assert "Structures Mod" in names
        assert "Utility Mod" in names
        assert "Dino Mod" not in names

    @pytest.mark.asyncio
    async def test_search_returns_summary_and_date(self, initialized_db):
        """Search results include summary and date_modified fields."""
        from bot.database import curseforge_db

        await curseforge_db.upsert_mod(
            301, 
            "Test Mod", 
            summary="This is a test summary",
            date_modified="2025-06-15T10:30:00Z"
        )

        results = await curseforge_db.search_mods("Test")
        assert len(results) == 1
        assert results[0]["summary"] == "This is a test summary"
        assert results[0]["date_modified"] == "2025-06-15T10:30:00Z"

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, initialized_db):
        """Search respects the limit parameter."""
        from bot.database import curseforge_db

        for i in range(50):
            await curseforge_db.upsert_mod(i, f"Test Mod {i}")

        results = await curseforge_db.search_mods("Test", limit=10)
        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_search_no_order_by(self, initialized_db):
        """Search does not pre-sort by downloads (sorting done in UI)."""
        from bot.database import curseforge_db

        await curseforge_db.upsert_mod(1, "Zebra Mod", download_count=1000)
        await curseforge_db.upsert_mod(2, "Alpha Mod", download_count=100)
        await curseforge_db.upsert_mod(3, "Beta Mod", download_count=500)

        results = await curseforge_db.search_mods("Mod")
        names = [r["name"] for r in results]
        # Results should NOT be sorted by downloads (UI handles sorting)
        # They may be in any order from SQLite
        assert len(results) == 3
        assert set(names) == {"Zebra Mod", "Alpha Mod", "Beta Mod"}


class TestGetAllMods:
    @pytest.mark.asyncio
    async def test_get_all_mods(self, initialized_db):
        """Retrieve all mods with pagination."""
        from bot.database import curseforge_db

        for i in range(25):
            await curseforge_db.upsert_mod(i, f"Mod {i}")

        page1 = await curseforge_db.get_all_mods(limit=10, offset=0)
        assert len(page1) == 10

        page2 = await curseforge_db.get_all_mods(limit=10, offset=10)
        assert len(page2) == 10

        ids1 = {m["mod_id"] for m in page1}
        ids2 = {m["mod_id"] for m in page2}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_get_mod_count(self, initialized_db):
        """Get total count of cached mods."""
        from bot.database import curseforge_db

        initial_count = await curseforge_db.get_mod_count()
        assert initial_count == 0

        for i in range(10):
            await curseforge_db.upsert_mod(i, f"Mod {i}")

        count = await curseforge_db.get_mod_count()
        assert count == 10


class TestBatchUpsert:
    @pytest.mark.asyncio
    async def test_batch_upsert(self, initialized_db):
        """Batch insert multiple mods."""
        from bot.database import curseforge_db

        mods = [
            {"id": 1, "name": "Mod 1", "author": "A"},
            {"id": 2, "name": "Mod 2", "author": "B"},
            {"id": 3, "name": "Mod 3", "author": "C"},
        ]

        count = await curseforge_db.upsert_mods_batch(mods)
        assert count == 3

        total = await curseforge_db.get_mod_count()
        assert total == 3


class TestGetRecentlyUpdated:
    @pytest.mark.asyncio
    async def test_get_recently_updated(self, initialized_db):
        """Get mods sorted by recent update."""
        from bot.database import curseforge_db

        await curseforge_db.upsert_mod(1, "Mod A", date_modified="2024-01-01")
        await curseforge_db.upsert_mod(2, "Mod B", date_modified="2024-01-15")
        await curseforge_db.upsert_mod(3, "Mod C", date_modified="2024-01-10")

        results = await curseforge_db.get_recently_updated()
        assert len(results) == 3
        assert results[0]["mod_id"] == 2
        assert results[1]["mod_id"] == 3
        assert results[2]["mod_id"] == 1


class TestGetTopDownloaded:
    @pytest.mark.asyncio
    async def test_get_top_downloaded(self, initialized_db):
        """Get mods sorted by download count."""
        from bot.database import curseforge_db

        await curseforge_db.upsert_mod(1, "Mod A", download_count=100)
        await curseforge_db.upsert_mod(2, "Mod B", download_count=500)
        await curseforge_db.upsert_mod(3, "Mod C", download_count=250)

        results = await curseforge_db.get_top_downloaded()
        assert len(results) == 3
        assert results[0]["mod_id"] == 2
        assert results[1]["mod_id"] == 3
        assert results[2]["mod_id"] == 1


class TestMarkUnavailable:
    @pytest.mark.asyncio
    async def test_mark_mod_unavailable(self, initialized_db):
        """Mark a mod as unavailable."""
        from bot.database import curseforge_db

        await curseforge_db.upsert_mod(1, "Test Mod")

        result = await curseforge_db.mark_mod_unavailable(1)
        assert result is True

        results = await curseforge_db.search_mods("Test")
        assert len(results) == 0

        mod = await curseforge_db.get_mod_by_id(1)
        assert mod is not None
        assert mod["is_available"] == 0
