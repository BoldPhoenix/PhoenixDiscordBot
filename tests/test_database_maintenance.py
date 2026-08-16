"""
Tests for backup_schedules CRUD functions in maintenance_db.py
"""

import pytest
from unittest.mock import patch


class TestBackupSchedulesTable:
    """Verify backup_schedules table is created by init_maintenance_tables."""

    @pytest.mark.asyncio
    async def test_table_created(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()

            import aiosqlite
            async with aiosqlite.connect(tmp_db_path) as db:
                cursor = await db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='backup_schedules'"
                )
                row = await cursor.fetchone()
                assert row is not None, "backup_schedules table must exist after init"

    @pytest.mark.asyncio
    async def test_table_columns(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()

            import aiosqlite
            async with aiosqlite.connect(tmp_db_path) as db:
                cursor = await db.execute("PRAGMA table_info(backup_schedules)")
                cols = {row[1] for row in await cursor.fetchall()}
                for expected in ("id", "guild_id", "name", "backup_type", "schedule_type",
                                 "backup_time", "day_of_week", "enabled", "target_directory", "created_at"):
                    assert expected in cols, f"Column '{expected}' missing from backup_schedules"


class TestGetBackupSchedules:
    """get_backup_schedules returns empty list when none exist."""

    @pytest.mark.asyncio
    async def test_empty_for_unknown_guild(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            result = await maintenance_db.get_backup_schedules(999)
            assert result == []

    @pytest.mark.asyncio
    async def test_returns_only_own_guild(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()

            await maintenance_db.add_backup_schedule(111, "Guild A Daily")
            await maintenance_db.add_backup_schedule(222, "Guild B Daily")

            result_a = await maintenance_db.get_backup_schedules(111)
            result_b = await maintenance_db.get_backup_schedules(222)
            assert len(result_a) == 1 and result_a[0]["name"] == "Guild A Daily"
            assert len(result_b) == 1 and result_b[0]["name"] == "Guild B Daily"


class TestAddBackupSchedule:
    """add_backup_schedule inserts correctly."""

    @pytest.mark.asyncio
    async def test_returns_positive_id(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            new_id = await maintenance_db.add_backup_schedule(123, "Daily Essentials")
            assert new_id > 0

    @pytest.mark.asyncio
    async def test_defaults(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            await maintenance_db.add_backup_schedule(123, "My Schedule")
            schedules = await maintenance_db.get_backup_schedules(123)
            s = schedules[0]
            assert s["backup_type"] == "essentials"
            assert s["schedule_type"] == "daily"
            assert s["backup_time"] == "02:00"
            assert s["day_of_week"] == 0
            assert s["enabled"] == 1
            assert s["target_directory"] is None

    @pytest.mark.asyncio
    async def test_custom_target_directory(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            await maintenance_db.add_backup_schedule(
                123, "With Target", target_directory="D:\\ARK\\Backups"
            )
            schedules = await maintenance_db.get_backup_schedules(123)
            assert schedules[0]["target_directory"] == "D:\\ARK\\Backups"

    @pytest.mark.asyncio
    async def test_update_target_directory(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            sid = await maintenance_db.add_backup_schedule(123, "Sched")
            await maintenance_db.update_backup_schedule(sid, target_directory="E:\\Backups")
            schedules = await maintenance_db.get_backup_schedules(123)
            assert schedules[0]["target_directory"] == "E:\\Backups"

    @pytest.mark.asyncio
    async def test_custom_values(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            await maintenance_db.add_backup_schedule(
                123, "Weekly Full",
                backup_type="full",
                schedule_type="weekly",
                backup_time="03:30",
                day_of_week=6,
                enabled=0,
            )
            schedules = await maintenance_db.get_backup_schedules(123)
            s = schedules[0]
            assert s["backup_type"] == "full"
            assert s["schedule_type"] == "weekly"
            assert s["backup_time"] == "03:30"
            assert s["day_of_week"] == 6
            assert s["enabled"] == 0

    @pytest.mark.asyncio
    async def test_multiple_schedules_per_guild(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            await maintenance_db.add_backup_schedule(123, "Schedule A")
            await maintenance_db.add_backup_schedule(123, "Schedule B")
            schedules = await maintenance_db.get_backup_schedules(123)
            assert len(schedules) == 2
            names = {s["name"] for s in schedules}
            assert names == {"Schedule A", "Schedule B"}


class TestUpdateBackupSchedule:
    """update_backup_schedule modifies the correct row."""

    @pytest.mark.asyncio
    async def test_update_name(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            sid = await maintenance_db.add_backup_schedule(123, "Old Name")
            ok = await maintenance_db.update_backup_schedule(sid, name="New Name")
            assert ok is True
            schedules = await maintenance_db.get_backup_schedules(123)
            assert schedules[0]["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            sid = await maintenance_db.add_backup_schedule(123, "Sched")
            await maintenance_db.update_backup_schedule(
                sid, backup_type="full", backup_time="04:00", enabled=0
            )
            schedules = await maintenance_db.get_backup_schedules(123)
            s = schedules[0]
            assert s["backup_type"] == "full"
            assert s["backup_time"] == "04:00"
            assert s["enabled"] == 0

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_true(self, tmp_db_path):
        """Updating a missing row is a no-op but still returns True (no SQL error)."""
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            ok = await maintenance_db.update_backup_schedule(9999, name="Ghost")
            assert ok is True

    @pytest.mark.asyncio
    async def test_update_with_empty_kwargs_returns_false(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            ok = await maintenance_db.update_backup_schedule(1)
            assert ok is False


class TestDeleteBackupSchedule:
    """delete_backup_schedule removes only the target row with correct guild_id guard."""

    @pytest.mark.asyncio
    async def test_delete_removes_row(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            sid = await maintenance_db.add_backup_schedule(123, "Delete Me")
            ok = await maintenance_db.delete_backup_schedule(sid, 123)
            assert ok is True
            schedules = await maintenance_db.get_backup_schedules(123)
            assert schedules == []

    @pytest.mark.asyncio
    async def test_delete_wrong_guild_does_not_remove(self, tmp_db_path):
        """Cross-guild delete must be blocked by the guild_id guard."""
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            sid = await maintenance_db.add_backup_schedule(123, "Mine")
            await maintenance_db.delete_backup_schedule(sid, 999)  # wrong guild_id
            schedules = await maintenance_db.get_backup_schedules(123)
            assert len(schedules) == 1, "Schedule must still exist after wrong-guild delete"

    @pytest.mark.asyncio
    async def test_delete_only_target_row(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            s1 = await maintenance_db.add_backup_schedule(123, "Keep")
            s2 = await maintenance_db.add_backup_schedule(123, "Remove")
            await maintenance_db.delete_backup_schedule(s2, 123)
            schedules = await maintenance_db.get_backup_schedules(123)
            assert len(schedules) == 1
            assert schedules[0]["name"] == "Keep"


class TestGetAllEnabledBackupSchedules:
    """get_all_enabled_backup_schedules returns only enabled schedules across all guilds."""

    @pytest.mark.asyncio
    async def test_returns_only_enabled(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            await maintenance_db.add_backup_schedule(111, "Enabled A", enabled=1)
            await maintenance_db.add_backup_schedule(111, "Disabled B", enabled=0)
            await maintenance_db.add_backup_schedule(222, "Enabled C", enabled=1)
            results = await maintenance_db.get_all_enabled_backup_schedules()
            names = {r["name"] for r in results}
            assert "Enabled A" in names
            assert "Enabled C" in names
            assert "Disabled B" not in names

    @pytest.mark.asyncio
    async def test_empty_when_no_enabled(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            await maintenance_db.add_backup_schedule(123, "Disabled", enabled=0)
            results = await maintenance_db.get_all_enabled_backup_schedules()
            assert results == []

    @pytest.mark.asyncio
    async def test_cross_guild_returns_all_enabled(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            for gid in [100, 200, 300]:
                await maintenance_db.add_backup_schedule(gid, f"Guild {gid} sched")
            results = await maintenance_db.get_all_enabled_backup_schedules()
            guild_ids = {r["guild_id"] for r in results}
            assert guild_ids == {100, 200, 300}


class TestGetAllEnabledUpdateConfigs:
    """get_all_enabled_update_configs returns only guilds with update_enabled=1."""

    @pytest.mark.asyncio
    async def test_returns_only_enabled(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            await maintenance_db.update_maintenance_config(111, update_enabled=1)
            await maintenance_db.update_maintenance_config(222, update_enabled=0)
            results = await maintenance_db.get_all_enabled_update_configs()
            guild_ids = {r["guild_id"] for r in results}
            assert 111 in guild_ids
            assert 222 not in guild_ids

    @pytest.mark.asyncio
    async def test_empty_when_none_enabled(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            await maintenance_db.update_maintenance_config(123, update_enabled=0)
            results = await maintenance_db.get_all_enabled_update_configs()
            assert results == []

    @pytest.mark.asyncio
    async def test_cross_guild_returns_all_enabled(self, tmp_db_path):
        with patch("bot.database.maintenance_db._db_path", return_value=tmp_db_path):
            from bot.database import maintenance_db
            await maintenance_db.init_maintenance_tables()
            for gid in [100, 200, 300]:
                await maintenance_db.update_maintenance_config(gid, update_enabled=1)
            results = await maintenance_db.get_all_enabled_update_configs()
            guild_ids = {r["guild_id"] for r in results}
            assert guild_ids == {100, 200, 300}
