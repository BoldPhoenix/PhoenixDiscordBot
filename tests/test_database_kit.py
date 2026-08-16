"""
Tests for bot/database/kit_db.py

Covers:
- Table creation and required columns
- Kit CRUD operations (create, get, update, delete, count)
- Kit items operations (add, get, update, delete)
- Kit claims operations (record, get, can_claim)
- Cooldown logic and one-time kits
- Guild isolation
"""

import pytest
import aiosqlite
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_db(tmp_db_path):
    return patch("bot.database.kit_db._db_path", return_value=tmp_db_path)


async def _init(tmp_db_path):
    with _patch_db(tmp_db_path):
        from bot.database import kit_db
        await kit_db.init_kit_tables()
    return tmp_db_path


# ---------------------------------------------------------------------------
# 1. Table creation
# ---------------------------------------------------------------------------

class TestKitTableCreation:
    @pytest.mark.asyncio
    async def test_kits_table_exists(self, tmp_db_path):
        await _init(tmp_db_path)
        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='kits'"
            )
            row = await cursor.fetchone()
            assert row is not None, "kits table must exist"

    @pytest.mark.asyncio
    async def test_kit_items_table_exists(self, tmp_db_path):
        await _init(tmp_db_path)
        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='kit_items'"
            )
            row = await cursor.fetchone()
            assert row is not None, "kit_items table must exist"

    @pytest.mark.asyncio
    async def test_kit_claims_table_exists(self, tmp_db_path):
        await _init(tmp_db_path)
        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='kit_claims'"
            )
            row = await cursor.fetchone()
            assert row is not None, "kit_claims table must exist"

    @pytest.mark.asyncio
    async def test_kits_required_columns(self, tmp_db_path):
        await _init(tmp_db_path)
        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute("PRAGMA table_info(kits)")
            cols = {row[1] for row in await cursor.fetchall()}
        expected = {
            "kit_id", "guild_id", "kit_name", "description", "enabled",
            "cooldown_hours", "min_level", "min_playtime_hours",
            "required_role_id", "created_at"
        }
        for col in expected:
            assert col in cols, f"Column '{col}' missing from kits"

    @pytest.mark.asyncio
    async def test_kit_items_required_columns(self, tmp_db_path):
        await _init(tmp_db_path)
        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute("PRAGMA table_info(kit_items)")
            cols = {row[1] for row in await cursor.fetchall()}
        expected = {"kit_item_id", "kit_id", "item_blueprint", "quantity", "quality", "notes"}
        for col in expected:
            assert col in cols, f"Column '{col}' missing from kit_items"

    @pytest.mark.asyncio
    async def test_kit_claims_required_columns(self, tmp_db_path):
        await _init(tmp_db_path)
        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute("PRAGMA table_info(kit_claims)")
            cols = {row[1] for row in await cursor.fetchall()}
        expected = {"claim_id", "guild_id", "kit_id", "user_id", "claimed_at", "next_claim_at"}
        for col in expected:
            assert col in cols, f"Column '{col}' missing from kit_claims"

    @pytest.mark.asyncio
    async def test_init_idempotent(self, tmp_db_path):
        """Calling init twice must not raise."""
        await _init(tmp_db_path)
        await _init(tmp_db_path)


# ---------------------------------------------------------------------------
# 2. Kit CRUD Operations
# ---------------------------------------------------------------------------

class TestKitCRUD:
    @pytest.mark.asyncio
    async def test_create_kit(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(
                guild_id=123,
                kit_name="Starter Kit",
                description="Welcome kit for new players",
                cooldown_hours=24
            )
            assert kit_id > 0

    @pytest.mark.asyncio
    async def test_get_kit_by_name(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            await kit_db.create_kit(123, "Starter Kit", "Test kit")
            kit = await kit_db.get_kit(123, "Starter Kit")
            assert kit is not None
            assert kit["kit_name"] == "Starter Kit"
            assert kit["guild_id"] == 123
            assert kit["description"] == "Test kit"

    @pytest.mark.asyncio
    async def test_get_kit_by_id(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit")
            kit = await kit_db.get_kit_by_id(kit_id)
            assert kit is not None
            assert kit["kit_id"] == kit_id
            assert kit["kit_name"] == "Test Kit"

    @pytest.mark.asyncio
    async def test_get_all_kits(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            await kit_db.create_kit(123, "Kit A")
            await kit_db.create_kit(123, "Kit B")
            await kit_db.create_kit(456, "Kit C")  # Different guild
            
            kits = await kit_db.get_all_kits(123)
            assert len(kits) == 2
            names = {k["kit_name"] for k in kits}
            assert names == {"Kit A", "Kit B"}

    @pytest.mark.asyncio
    async def test_get_all_kits_enabled_only(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            await kit_db.create_kit(123, "Kit A", enabled=1)
            await kit_db.create_kit(123, "Kit B", enabled=0)
            
            all_kits = await kit_db.get_all_kits(123, enabled_only=False)
            assert len(all_kits) == 2
            
            enabled_kits = await kit_db.get_all_kits(123, enabled_only=True)
            assert len(enabled_kits) == 1
            assert enabled_kits[0]["kit_name"] == "Kit A"

    @pytest.mark.asyncio
    async def test_update_kit(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Old Name", cooldown_hours=0)
            
            updated = await kit_db.update_kit(
                kit_id,
                kit_name="New Name",
                cooldown_hours=24,
                min_level=10
            )
            assert updated is True
            
            kit = await kit_db.get_kit_by_id(kit_id)
            assert kit["kit_name"] == "New Name"
            assert kit["cooldown_hours"] == 24
            assert kit["min_level"] == 10

    @pytest.mark.asyncio
    async def test_update_kit_no_changes(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit")
            updated = await kit_db.update_kit(kit_id)
            assert updated is False

    @pytest.mark.asyncio
    async def test_delete_kit(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit")
            deleted = await kit_db.delete_kit(kit_id)
            assert deleted is True
            
            kit = await kit_db.get_kit_by_id(kit_id)
            assert kit is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_kit(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            deleted = await kit_db.delete_kit(99999)
            assert deleted is False

    @pytest.mark.asyncio
    async def test_count_kits(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            count = await kit_db.count_kits(123)
            assert count == 0
            
            await kit_db.create_kit(123, "Kit A")
            await kit_db.create_kit(123, "Kit B")
            await kit_db.create_kit(456, "Kit C")
            
            count = await kit_db.count_kits(123)
            assert count == 2

    @pytest.mark.asyncio
    async def test_kit_name_unique_per_guild(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            await kit_db.create_kit(123, "Starter")
            
            # Same name, different guild - should succeed
            await kit_db.create_kit(456, "Starter")
            
            # Same name, same guild - should fail
            with pytest.raises(aiosqlite.IntegrityError):
                await kit_db.create_kit(123, "Starter")


# ---------------------------------------------------------------------------
# 3. Kit Items Operations
# ---------------------------------------------------------------------------

class TestKitItems:
    @pytest.mark.asyncio
    async def test_add_kit_item(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit")
            item_id = await kit_db.add_kit_item(
                kit_id,
                "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Cloth/PrimalItemArmor_ClothShirt.PrimalItemArmor_ClothShirt'",
                quantity=1,
                quality=1
            )
            assert item_id > 0

    @pytest.mark.asyncio
    async def test_get_kit_items(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit")
            await kit_db.add_kit_item(kit_id, "blueprint_a", 5, 1)
            await kit_db.add_kit_item(kit_id, "blueprint_b", 10, 4)
            
            items = await kit_db.get_kit_items(kit_id)
            assert len(items) == 2
            assert items[0]["quantity"] == 5
            assert items[1]["quantity"] == 10

    @pytest.mark.asyncio
    async def test_update_kit_item(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit")
            item_id = await kit_db.add_kit_item(kit_id, "blueprint", 1, 1)
            
            updated = await kit_db.update_kit_item(item_id, quantity=10, quality=6)
            assert updated is True
            
            items = await kit_db.get_kit_items(kit_id)
            assert items[0]["quantity"] == 10
            assert items[0]["quality"] == 6

    @pytest.mark.asyncio
    async def test_delete_kit_item(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit")
            item_id = await kit_db.add_kit_item(kit_id, "blueprint", 1, 1)
            
            deleted = await kit_db.delete_kit_item(item_id)
            assert deleted is True
            
            items = await kit_db.get_kit_items(kit_id)
            assert len(items) == 0

    @pytest.mark.asyncio
    async def test_delete_all_kit_items(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit")
            await kit_db.add_kit_item(kit_id, "blueprint_a", 1, 1)
            await kit_db.add_kit_item(kit_id, "blueprint_b", 1, 1)
            await kit_db.add_kit_item(kit_id, "blueprint_c", 1, 1)
            
            count = await kit_db.delete_all_kit_items(kit_id)
            assert count == 3
            
            items = await kit_db.get_kit_items(kit_id)
            assert len(items) == 0

    @pytest.mark.asyncio
    async def test_delete_kit_cascades_to_items(self, tmp_db_path):
        """Deleting a kit should delete all its items via CASCADE."""
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit")
            await kit_db.add_kit_item(kit_id, "blueprint_a", 1, 1)
            await kit_db.add_kit_item(kit_id, "blueprint_b", 1, 1)
            
            await kit_db.delete_kit(kit_id)
            
            items = await kit_db.get_kit_items(kit_id)
            assert len(items) == 0


# ---------------------------------------------------------------------------
# 4. Kit Claims Operations
# ---------------------------------------------------------------------------

class TestKitClaims:
    @pytest.mark.asyncio
    async def test_record_claim_no_cooldown(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "One-Time Kit", cooldown_hours=0)
            
            claim_id = await kit_db.record_claim(123, kit_id, 999, cooldown_hours=0)
            assert claim_id > 0
            
            claim = await kit_db.get_last_claim(123, kit_id, 999)
            assert claim is not None
            assert claim["next_claim_at"] is None

    @pytest.mark.asyncio
    async def test_record_claim_with_cooldown(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Daily Kit", cooldown_hours=24)
            
            await kit_db.record_claim(123, kit_id, 999, cooldown_hours=24)
            
            claim = await kit_db.get_last_claim(123, kit_id, 999)
            assert claim["next_claim_at"] is not None
            
            claimed_at = datetime.fromisoformat(claim["claimed_at"])
            next_claim_at = datetime.fromisoformat(claim["next_claim_at"])
            delta = next_claim_at - claimed_at
            assert delta.total_seconds() == 24 * 3600

    @pytest.mark.asyncio
    async def test_can_claim_kit_first_time(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit")
            
            can_claim, next_time = await kit_db.can_claim_kit(123, kit_id, 999)
            assert can_claim is True
            assert next_time is None

    @pytest.mark.asyncio
    async def test_can_claim_kit_one_time_already_claimed(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "One-Time Kit", cooldown_hours=0)
            await kit_db.record_claim(123, kit_id, 999, cooldown_hours=0)
            
            can_claim, next_time = await kit_db.can_claim_kit(123, kit_id, 999)
            assert can_claim is False
            assert next_time is None

    @pytest.mark.asyncio
    async def test_can_claim_kit_cooldown_active(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Daily Kit", cooldown_hours=24)
            await kit_db.record_claim(123, kit_id, 999, cooldown_hours=24)
            
            can_claim, next_time = await kit_db.can_claim_kit(123, kit_id, 999)
            assert can_claim is False
            assert next_time is not None

    @pytest.mark.asyncio
    async def test_can_claim_kit_cooldown_expired(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit")
            
            # Manually insert a claim with expired cooldown
            past_time = datetime.now(timezone.utc) - timedelta(hours=25)
            next_claim_time = datetime.now(timezone.utc) - timedelta(hours=1)
            
            async with aiosqlite.connect(tmp_db_path) as db:
                await db.execute("""
                    INSERT INTO kit_claims (guild_id, kit_id, user_id, claimed_at, next_claim_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (123, kit_id, 999, past_time.isoformat(), next_claim_time.isoformat()))
                await db.commit()
            
            can_claim, next_time = await kit_db.can_claim_kit(123, kit_id, 999)
            assert can_claim is True
            assert next_time is None

    @pytest.mark.asyncio
    async def test_get_claim_count(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit", cooldown_hours=24)
            
            count = await kit_db.get_claim_count(kit_id)
            assert count == 0
            
            await kit_db.record_claim(123, kit_id, 111, cooldown_hours=24)
            await kit_db.record_claim(123, kit_id, 222, cooldown_hours=24)
            await kit_db.record_claim(123, kit_id, 333, cooldown_hours=24)
            
            count = await kit_db.get_claim_count(kit_id)
            assert count == 3

    @pytest.mark.asyncio
    async def test_get_user_claims(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id_a = await kit_db.create_kit(123, "Kit A", cooldown_hours=24)
            kit_id_b = await kit_db.create_kit(123, "Kit B", cooldown_hours=24)
            
            await kit_db.record_claim(123, kit_id_a, 999, cooldown_hours=24)
            await kit_db.record_claim(123, kit_id_b, 999, cooldown_hours=24)
            await kit_db.record_claim(123, kit_id_a, 888, cooldown_hours=24)
            
            claims = await kit_db.get_user_claims(123, 999)
            assert len(claims) == 2
            
            claims = await kit_db.get_user_claims(123, 888)
            assert len(claims) == 1

    @pytest.mark.asyncio
    async def test_delete_kit_cascades_to_claims(self, tmp_db_path):
        """Deleting a kit should delete all claims via CASCADE."""
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id = await kit_db.create_kit(123, "Test Kit", cooldown_hours=24)
            await kit_db.record_claim(123, kit_id, 999, cooldown_hours=24)
            
            await kit_db.delete_kit(kit_id)
            
            claim = await kit_db.get_last_claim(123, kit_id, 999)
            assert claim is None


# ---------------------------------------------------------------------------
# 5. Guild Isolation
# ---------------------------------------------------------------------------

class TestGuildIsolation:
    @pytest.mark.asyncio
    async def test_kits_isolated_by_guild(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            await kit_db.create_kit(123, "Kit A")
            await kit_db.create_kit(456, "Kit B")
            
            kit = await kit_db.get_kit(123, "Kit B")
            assert kit is None
            
            kit = await kit_db.get_kit(456, "Kit A")
            assert kit is None

    @pytest.mark.asyncio
    async def test_claims_isolated_by_guild(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import kit_db
            kit_id_123 = await kit_db.create_kit(123, "Test Kit")
            kit_id_456 = await kit_db.create_kit(456, "Test Kit")
            
            await kit_db.record_claim(123, kit_id_123, 999, cooldown_hours=0)
            
            claim = await kit_db.get_last_claim(456, kit_id_456, 999)
            assert claim is None
