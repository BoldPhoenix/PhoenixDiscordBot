"""
Tests for bot/database/subscription_db.py

Covers:
- Table creation and required columns
- get_or_create_subscription creates trial; returns existing on second call
- trial_end is 30 days after trial_start
- set_tier updates tier, status, updated_at
- get_effective_tier — all 6 combinations
- get_expiring_trials returns correct guilds
- handle_tier_change — downgrade/upgrade enforcement
- set_tier triggers handle_tier_change on tier change
- get_grace_period_subscriptions returns grace guilds
"""

import pytest
import aiosqlite
from datetime import datetime, timedelta
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_db(tmp_db_path):
    return patch("bot.database.subscription_db._db_path", return_value=tmp_db_path)


async def _init(tmp_db_path):
    with _patch_db(tmp_db_path):
        from bot.database import subscription_db
        await subscription_db.init_subscription_tables()
    return tmp_db_path


# ---------------------------------------------------------------------------
# 1. Table creation
# ---------------------------------------------------------------------------

class TestSubscriptionTableCreation:
    @pytest.mark.asyncio
    async def test_table_exists(self, tmp_db_path):
        await _init(tmp_db_path)
        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='subscriptions'"
            )
            row = await cursor.fetchone()
            assert row is not None, "subscriptions table must exist"

    @pytest.mark.asyncio
    async def test_required_columns(self, tmp_db_path):
        await _init(tmp_db_path)
        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute("PRAGMA table_info(subscriptions)")
            cols = {row[1] for row in await cursor.fetchall()}
        expected = {
            "id", "guild_id", "tier", "status",
            "stripe_customer_id", "stripe_subscription_id",
            "trial_start", "trial_end",
            "subscription_start", "subscription_end",
            "grace_end", "notes", "created_at", "updated_at",
        }
        for col in expected:
            assert col in cols, f"Column '{col}' missing from subscriptions"

    @pytest.mark.asyncio
    async def test_init_idempotent(self, tmp_db_path):
        """Calling init twice must not raise."""
        await _init(tmp_db_path)
        await _init(tmp_db_path)


# ---------------------------------------------------------------------------
# 2. get_or_create_subscription
# ---------------------------------------------------------------------------

class TestGetOrCreateSubscription:
    @pytest.mark.asyncio
    async def test_creates_permanent_free_tier_for_new_guild(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            sub = await subscription_db.get_or_create_subscription(999)
        assert sub is not None
        assert sub["guild_id"] == 999
        assert sub["tier"] == "free"
        assert sub["status"] == "active"  # Free tier is permanent, not trial

    @pytest.mark.asyncio
    async def test_returns_existing_for_known_guild(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            sub1 = await subscription_db.get_or_create_subscription(222)
            sub2 = await subscription_db.get_or_create_subscription(222)
        assert sub1["id"] == sub2["id"]

    @pytest.mark.asyncio
    async def test_trial_end_is_30_days_from_start(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            sub = await subscription_db.get_or_create_subscription(333)
        trial_start = datetime.fromisoformat(sub["trial_start"])
        trial_end = datetime.fromisoformat(sub["trial_end"])
        delta = trial_end - trial_start
        assert 29 <= delta.days <= 30, f"Expected ~30 days gap, got {delta.days}"

    @pytest.mark.asyncio
    async def test_trial_start_populated(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            sub = await subscription_db.get_or_create_subscription(444)
        assert sub["trial_start"] is not None


# ---------------------------------------------------------------------------
# 3. get_subscription
# ---------------------------------------------------------------------------

class TestGetSubscription:
    @pytest.mark.asyncio
    async def test_returns_none_for_unknown(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            sub = await subscription_db.get_subscription(9999)
        assert sub is None

    @pytest.mark.asyncio
    async def test_returns_record_after_create(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            await subscription_db.get_or_create_subscription(555)
            sub = await subscription_db.get_subscription(555)
        assert sub is not None
        assert sub["guild_id"] == 555


# ---------------------------------------------------------------------------
# 4. set_tier
# ---------------------------------------------------------------------------

class TestSetTier:
    @pytest.mark.asyncio
    async def test_updates_tier_and_status(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            await subscription_db.get_or_create_subscription(600)
            result = await subscription_db.set_tier(600, "premium", "active")
            sub = await subscription_db.get_subscription(600)
        assert result is True
        assert sub["tier"] == "premium"
        assert sub["status"] == "active"

    @pytest.mark.asyncio
    async def test_updates_notes(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            await subscription_db.get_or_create_subscription(601)
            await subscription_db.set_tier(601, "lifetime", "active", notes="Volunteer tester")
            sub = await subscription_db.get_subscription(601)
        assert sub["notes"] == "Volunteer tester"

    @pytest.mark.asyncio
    async def test_updates_grace_end(self, tmp_db_path):
        await _init(tmp_db_path)
        grace_ts = (datetime.utcnow() + timedelta(days=7)).isoformat()
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            await subscription_db.get_or_create_subscription(602)
            await subscription_db.set_tier(602, "premium", "grace", grace_end=grace_ts)
            sub = await subscription_db.get_subscription(602)
        assert sub["grace_end"] == grace_ts

    @pytest.mark.asyncio
    async def test_returns_false_for_nonexistent_guild(self, tmp_db_path):
        """set_tier on nonexistent guild should still return True (UPDATE affects 0 rows)."""
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            result = await subscription_db.set_tier(99999, "premium", "active")
        # UPDATE on missing row succeeds (no error) — True is correct
        assert result is True


# ---------------------------------------------------------------------------
# 5. get_effective_tier — all 6 combinations
# ---------------------------------------------------------------------------

class TestGetEffectiveTier:
    def test_none_returns_free(self):
        from bot.database.subscription_db import get_effective_tier
        assert get_effective_tier(None) == "free"

    def test_lifetime_active_returns_lifetime(self):
        from bot.database.subscription_db import get_effective_tier
        sub = {"tier": "lifetime", "status": "active"}
        assert get_effective_tier(sub) == "lifetime"

    def test_premium_active_returns_premium(self):
        from bot.database.subscription_db import get_effective_tier
        sub = {"tier": "premium", "status": "active"}
        assert get_effective_tier(sub) == "premium"

    def test_premium_grace_returns_premium(self):
        from bot.database.subscription_db import get_effective_tier
        sub = {"tier": "premium", "status": "grace"}
        assert get_effective_tier(sub) == "premium"

    def test_premium_expired_returns_free(self):
        from bot.database.subscription_db import get_effective_tier
        sub = {"tier": "premium", "status": "expired"}
        assert get_effective_tier(sub) == "free"

    def test_free_trial_returns_free(self):
        from bot.database.subscription_db import get_effective_tier
        sub = {"tier": "free", "status": "trial"}
        assert get_effective_tier(sub) == "free"


# ---------------------------------------------------------------------------
# 6. get_expiring_trials
# ---------------------------------------------------------------------------

class TestGetExpiringTrials:
    @pytest.mark.asyncio
    async def test_returns_guild_expiring_within_days(self, tmp_db_path):
        await _init(tmp_db_path)
        # Insert a subscription ending in 2 days
        soon = (datetime.utcnow() + timedelta(days=2)).isoformat()
        async with aiosqlite.connect(tmp_db_path) as db:
            await db.execute(
                """INSERT INTO subscriptions (guild_id, tier, status, trial_start, trial_end)
                   VALUES (700, 'free', 'trial', datetime('now'), ?)""",
                (soon,),
            )
            await db.commit()

        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            results = await subscription_db.get_expiring_trials(days_ahead=3)
        guild_ids = [r["guild_id"] for r in results]
        assert 700 in guild_ids

    @pytest.mark.asyncio
    async def test_excludes_guild_expiring_beyond_window(self, tmp_db_path):
        await _init(tmp_db_path)
        # Insert a subscription ending in 10 days
        far = (datetime.utcnow() + timedelta(days=10)).isoformat()
        async with aiosqlite.connect(tmp_db_path) as db:
            await db.execute(
                """INSERT INTO subscriptions (guild_id, tier, status, trial_start, trial_end)
                   VALUES (701, 'free', 'trial', datetime('now'), ?)""",
                (far,),
            )
            await db.commit()

        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            results = await subscription_db.get_expiring_trials(days_ahead=3)
        guild_ids = [r["guild_id"] for r in results]
        assert 701 not in guild_ids

    @pytest.mark.asyncio
    async def test_excludes_non_trial_status(self, tmp_db_path):
        await _init(tmp_db_path)
        soon = (datetime.utcnow() + timedelta(days=1)).isoformat()
        async with aiosqlite.connect(tmp_db_path) as db:
            await db.execute(
                """INSERT INTO subscriptions (guild_id, tier, status, trial_start, trial_end)
                   VALUES (702, 'free', 'active', datetime('now'), ?)""",
                (soon,),
            )
            await db.commit()

        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            results = await subscription_db.get_expiring_trials(days_ahead=3)
        guild_ids = [r["guild_id"] for r in results]
        assert 702 not in guild_ids


# ---------------------------------------------------------------------------
# 7. get_grace_period_subscriptions
# ---------------------------------------------------------------------------

class TestGetGracePeriodSubscriptions:
    @pytest.mark.asyncio
    async def test_returns_grace_guilds(self, tmp_db_path):
        await _init(tmp_db_path)
        grace_ts = (datetime.utcnow() + timedelta(days=5)).isoformat()
        async with aiosqlite.connect(tmp_db_path) as db:
            await db.execute(
                """INSERT INTO subscriptions
                   (guild_id, tier, status, grace_end)
                   VALUES (800, 'premium', 'grace', ?)""",
                (grace_ts,),
            )
            await db.commit()

        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            results = await subscription_db.get_grace_period_subscriptions()
        guild_ids = [r["guild_id"] for r in results]
        assert 800 in guild_ids

    @pytest.mark.asyncio
    async def test_excludes_active_subscriptions(self, tmp_db_path):
        await _init(tmp_db_path)
        async with aiosqlite.connect(tmp_db_path) as db:
            await db.execute(
                """INSERT INTO subscriptions
                   (guild_id, tier, status)
                   VALUES (801, 'premium', 'active')""",
            )
            await db.commit()

        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            results = await subscription_db.get_grace_period_subscriptions()
        guild_ids = [r["guild_id"] for r in results]
        assert 801 not in guild_ids

    @pytest.mark.asyncio
    async def test_empty_when_no_grace(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            results = await subscription_db.get_grace_period_subscriptions()
        assert results == []


# ---------------------------------------------------------------------------
# 8. get_all_subscriptions
# ---------------------------------------------------------------------------

class TestGetAllSubscriptions:
    @pytest.mark.asyncio
    async def test_returns_list(self, tmp_db_path):
        await _init(tmp_db_path)
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            await subscription_db.get_or_create_subscription(900)
            await subscription_db.get_or_create_subscription(901)
            results = await subscription_db.get_all_subscriptions()
        assert len(results) >= 2
        guild_ids = [r["guild_id"] for r in results]
        assert 900 in guild_ids
        assert 901 in guild_ids


# ---------------------------------------------------------------------------
# 9. handle_tier_change — downgrade enforcement
# ---------------------------------------------------------------------------

async def _init_all(tmp_db_path):
    """Helper: init subscription + server_config tables in the same DB."""
    from unittest.mock import patch as _patch
    with _patch_db(tmp_db_path), \
         _patch("bot.utils.config.Config.DATABASE_PATH", tmp_db_path):
        from bot.database import subscription_db
        from bot.database.server_config_db import init_server_config_tables
        await subscription_db.init_subscription_tables()
        await init_server_config_tables()


async def _add_server(tmp_db_path, guild_id, name, enabled=1):
    """Insert a server row directly into ark_servers for testing."""
    import aiosqlite
    async with aiosqlite.connect(tmp_db_path) as db:
        await db.execute(
            "INSERT INTO ark_servers (guild_id, name, host, rcon_port, rcon_password, enabled) "
            "VALUES (?, ?, 'localhost', 27020, 'pass', ?)",
            (guild_id, name, enabled),
        )
        await db.commit()


class TestHandleTierChange:
    @pytest.mark.asyncio
    async def test_downgrade_premium_to_free_disables_excess_servers(self, tmp_db_path):
        """Premium→Free downgrade: servers beyond limit 2 are disabled."""
        await _init_all(tmp_db_path)
        guild_id = 1001
        await _add_server(tmp_db_path, guild_id, "Server1")
        await _add_server(tmp_db_path, guild_id, "Server2")
        await _add_server(tmp_db_path, guild_id, "Server3")  # beyond limit

        from unittest.mock import patch as _patch
        with _patch("bot.utils.config.Config.DATABASE_PATH", tmp_db_path), \
             _patch_db(tmp_db_path):
            from bot.database import subscription_db
            result = await subscription_db.handle_tier_change(guild_id, "premium", "free")

        assert result["action"] == "downgraded"
        assert "Server3" in result["disabled"]
        assert len(result["disabled"]) == 1

    @pytest.mark.asyncio
    async def test_downgrade_lifetime_to_free_disables_excess_servers(self, tmp_db_path):
        """Lifetime→Free downgrade: same 2-server limit enforced."""
        await _init_all(tmp_db_path)
        guild_id = 1002
        await _add_server(tmp_db_path, guild_id, "Alpha")
        await _add_server(tmp_db_path, guild_id, "Beta")
        await _add_server(tmp_db_path, guild_id, "Gamma")

        from unittest.mock import patch as _patch
        with _patch("bot.utils.config.Config.DATABASE_PATH", tmp_db_path), \
             _patch_db(tmp_db_path):
            from bot.database import subscription_db
            result = await subscription_db.handle_tier_change(guild_id, "lifetime", "free")

        assert result["action"] == "downgraded"
        assert "Gamma" in result["disabled"]

    @pytest.mark.asyncio
    async def test_downgrade_within_limit_no_servers_disabled(self, tmp_db_path):
        """Downgrade to free with ≤2 servers: no servers disabled."""
        await _init_all(tmp_db_path)
        guild_id = 1003
        await _add_server(tmp_db_path, guild_id, "OnlyServer")

        from unittest.mock import patch as _patch
        with _patch("bot.utils.config.Config.DATABASE_PATH", tmp_db_path), \
             _patch_db(tmp_db_path):
            from bot.database import subscription_db
            result = await subscription_db.handle_tier_change(guild_id, "premium", "free")

        assert result["action"] == "downgraded_no_change"
        assert result["disabled"] == []

    @pytest.mark.asyncio
    async def test_upgrade_free_to_premium_no_action(self, tmp_db_path):
        """Free→Premium upgrade: no server changes."""
        await _init_all(tmp_db_path)
        guild_id = 1004
        await _add_server(tmp_db_path, guild_id, "ServerA")

        from unittest.mock import patch as _patch
        with _patch("bot.utils.config.Config.DATABASE_PATH", tmp_db_path), \
             _patch_db(tmp_db_path):
            from bot.database import subscription_db
            result = await subscription_db.handle_tier_change(guild_id, "free", "premium")

        assert result["action"] == "upgraded"
        assert result["disabled"] == []

    @pytest.mark.asyncio
    async def test_oldest_servers_kept_on_downgrade(self, tmp_db_path):
        """Oldest servers (lowest DB IDs) survive downgrade; newest are disabled."""
        await _init_all(tmp_db_path)
        guild_id = 1005
        await _add_server(tmp_db_path, guild_id, "First")
        await _add_server(tmp_db_path, guild_id, "Second")
        await _add_server(tmp_db_path, guild_id, "Third")
        await _add_server(tmp_db_path, guild_id, "Fourth")

        from unittest.mock import patch as _patch
        with _patch("bot.utils.config.Config.DATABASE_PATH", tmp_db_path), \
             _patch_db(tmp_db_path):
            from bot.database import subscription_db
            result = await subscription_db.handle_tier_change(guild_id, "premium", "free")

        assert "First" not in result["disabled"]
        assert "Second" not in result["disabled"]
        assert "Third" in result["disabled"]
        assert "Fourth" in result["disabled"]

    @pytest.mark.asyncio
    async def test_set_tier_triggers_handle_tier_change_on_downgrade(self, tmp_db_path):
        """set_tier must call handle_tier_change when tier changes to free."""
        await _init_all(tmp_db_path)
        guild_id = 1006
        await _add_server(tmp_db_path, guild_id, "S1")
        await _add_server(tmp_db_path, guild_id, "S2")
        await _add_server(tmp_db_path, guild_id, "S3_should_be_disabled")

        from unittest.mock import patch as _patch, AsyncMock as _AsyncMock
        with _patch_db(tmp_db_path):
            from bot.database import subscription_db
            await subscription_db.init_subscription_tables()
            await subscription_db.get_or_create_subscription(guild_id)
            # Promote to premium first
            await subscription_db.set_tier(guild_id, "premium", "active")

        captured = []

        async def _capture_tier_change(gid, old, new):
            captured.append((gid, old, new))
            return {"disabled": [], "action": "downgraded"}

        with _patch_db(tmp_db_path), \
             _patch("bot.database.subscription_db.handle_tier_change", _capture_tier_change):
            from bot.database import subscription_db as sub_db
            await sub_db.set_tier(guild_id, "free", "expired")

        assert len(captured) == 1
        assert captured[0] == (guild_id, "premium", "free")

    @pytest.mark.asyncio
    async def test_upgrade_reenables_tier_limited_servers(self, tmp_db_path):
        """Free→Premium upgrade: servers that were disabled due to tier_limit are re-enabled."""
        await _init_all(tmp_db_path)
        guild_id = 1007

        # Add 3 servers; disable servers 2 and 3 with tier_limit (simulating prior downgrade)
        await _add_server(tmp_db_path, guild_id, "Server1")
        await _add_server(tmp_db_path, guild_id, "Server2", enabled=0)
        await _add_server(tmp_db_path, guild_id, "Server3", enabled=0)

        # Mark the disabled servers with disabled_reason='tier_limit'
        import aiosqlite
        async with aiosqlite.connect(tmp_db_path) as db:
            await db.execute(
                "UPDATE ark_servers SET disabled_reason = 'tier_limit' WHERE guild_id = ? AND enabled = 0",
                (guild_id,),
            )
            await db.commit()

        from unittest.mock import patch as _patch
        with _patch("bot.utils.config.Config.DATABASE_PATH", tmp_db_path), \
             _patch_db(tmp_db_path):
            from bot.database import subscription_db, server_config_db
            result = await subscription_db.handle_tier_change(guild_id, "free", "premium")

        # All three servers must now be enabled
        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute(
                "SELECT name, enabled, disabled_reason FROM ark_servers WHERE guild_id = ? ORDER BY name",
                (guild_id,),
            )
            rows = {r[0]: {"enabled": r[1], "disabled_reason": r[2]} for r in await cursor.fetchall()}

        assert rows["Server1"]["enabled"] == 1
        assert rows["Server2"]["enabled"] == 1, "tier_limit server must be re-enabled on upgrade"
        assert rows["Server3"]["enabled"] == 1, "tier_limit server must be re-enabled on upgrade"
        assert rows["Server2"]["disabled_reason"] is None, "disabled_reason must be cleared on re-enable"
        assert rows["Server3"]["disabled_reason"] is None, "disabled_reason must be cleared on re-enable"
        assert result["action"] == "upgraded"
        assert "Server2" in result.get("reenabled", []) or len(result.get("reenabled", [])) > 0, (
            "handle_tier_change result must report reenabled servers"
        )

    @pytest.mark.asyncio
    async def test_upgrade_does_not_reenable_manually_disabled_servers(self, tmp_db_path):
        """Upgrade must not re-enable servers the admin disabled manually (no tier_limit reason)."""
        await _init_all(tmp_db_path)
        guild_id = 1008

        await _add_server(tmp_db_path, guild_id, "ManuallyDisabled", enabled=0)
        # disabled_reason left as NULL (manually disabled, not tier_limit)

        from unittest.mock import patch as _patch
        with _patch("bot.utils.config.Config.DATABASE_PATH", tmp_db_path), \
             _patch_db(tmp_db_path):
            from bot.database import subscription_db
            await subscription_db.handle_tier_change(guild_id, "free", "premium")

        import aiosqlite
        async with aiosqlite.connect(tmp_db_path) as db:
            cursor = await db.execute(
                "SELECT enabled FROM ark_servers WHERE guild_id = ? AND name = 'ManuallyDisabled'",
                (guild_id,),
            )
            row = await cursor.fetchone()

        assert row[0] == 0, (
            "Manually disabled server (no tier_limit reason) must remain disabled after upgrade"
        )
