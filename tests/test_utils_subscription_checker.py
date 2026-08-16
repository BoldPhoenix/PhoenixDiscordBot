"""
Tests for bot/utils/subscription_checker.py

Covers:
- Free feature passes on free tier (no DB call needed)
- Premium feature blocked on free tier → sends embed, returns False
- Premium feature passes on premium tier
- Lifetime feature blocked on premium tier
- Lifetime feature passes on lifetime tier
- Premium feature passes during grace period (effective = premium)
- TIER_LEVELS, FEATURE_TIERS, SERVER_LIMITS, VOICE_LIMITS exports exist
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers to build fake interactions
# ---------------------------------------------------------------------------

def _make_interaction(guild_id=12345):
    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.response = MagicMock()
    interaction.response.is_done = MagicMock(return_value=False)
    interaction.response.send_message = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _make_sub(tier="free", status="trial"):
    return {
        "guild_id": 12345,
        "tier": tier,
        "status": status,
        "trial_start": "2026-01-01T00:00:00",
        "trial_end": "2026-01-31T00:00:00",
        "grace_end": None,
        "notes": None,
    }


# ---------------------------------------------------------------------------
# 1. Module imports
# ---------------------------------------------------------------------------

class TestSubscriptionCheckerImports:
    def test_module_importable(self):
        import bot.utils.subscription_checker  # noqa

    def test_check_feature_importable(self):
        from bot.utils.subscription_checker import check_feature
        assert callable(check_feature)

    def test_tier_levels_exported(self):
        from bot.utils.subscription_checker import TIER_LEVELS
        assert "free" in TIER_LEVELS
        assert "premium" in TIER_LEVELS
        assert "lifetime" in TIER_LEVELS

    def test_feature_tiers_exported(self):
        from bot.utils.subscription_checker import FEATURE_TIERS
        assert "economy" in FEATURE_TIERS
        assert "ini_management" in FEATURE_TIERS
        assert "server_monitoring" in FEATURE_TIERS

    def test_server_limits_exported(self):
        from bot.utils.subscription_checker import SERVER_LIMITS
        assert SERVER_LIMITS["free"] == 2
        # lifetime mirrors premium — same server limit, different payment model
        assert SERVER_LIMITS["premium"] == SERVER_LIMITS["lifetime"]

    def test_voice_limits_exported(self):
        from bot.utils.subscription_checker import VOICE_LIMITS
        assert VOICE_LIMITS["free"] == 2
        assert VOICE_LIMITS["premium"] == 10


# ---------------------------------------------------------------------------
# 2. Free feature always passes
# ---------------------------------------------------------------------------

class TestFreeFeatureAlwaysPasses:
    @pytest.mark.asyncio
    async def test_server_monitoring_passes_free(self):
        from bot.utils.subscription_checker import check_feature
        interaction = _make_interaction()
        result = await check_feature(interaction, "server_monitoring")
        assert result is True
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_basic_rcon_passes_free(self):
        from bot.utils.subscription_checker import check_feature
        interaction = _make_interaction()
        result = await check_feature(interaction, "basic_rcon")
        assert result is True


# ---------------------------------------------------------------------------
# 3. Premium feature blocked on free tier
# ---------------------------------------------------------------------------

class TestPremiumFeatureBlockedOnFree:
    @pytest.mark.asyncio
    async def test_economy_blocked_on_free_trial(self):
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("free", "trial")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="free"):
            result = await check_feature(interaction, "economy")

        assert result is False
        interaction.response.send_message.assert_called_once()
        # Check ephemeral=True
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_games_blocked_on_free(self):
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("free", "trial")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="free"):
            result = await check_feature(interaction, "games")

        assert result is False


# ---------------------------------------------------------------------------
# 4. Premium feature passes on premium tier
# ---------------------------------------------------------------------------

class TestPremiumFeaturePassesOnPremium:
    @pytest.mark.asyncio
    async def test_economy_passes_on_premium(self):
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("premium", "active")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="premium"):
            result = await check_feature(interaction, "economy")

        assert result is True
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_shop_passes_on_premium(self):
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("premium", "active")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="premium"):
            result = await check_feature(interaction, "shop")

        assert result is True


# ---------------------------------------------------------------------------
# 5. Server-management features are FREE (no DB call, no upgrade prompt)
#    Rule: anything that operates on servers themselves = free (limited to 2)
#          anything that requires linked players = premium
# ---------------------------------------------------------------------------

class TestServerFeaturesAreFree:
    """All server-side features must pass on free tier without a DB call."""

    @pytest.mark.asyncio
    async def test_ini_management_free(self):
        from bot.utils.subscription_checker import check_feature
        interaction = _make_interaction()
        result = await check_feature(interaction, "ini_management")
        assert result is True
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_mod_management_free(self):
        from bot.utils.subscription_checker import check_feature
        interaction = _make_interaction()
        result = await check_feature(interaction, "mod_management")
        assert result is True
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_maintenance_free(self):
        from bot.utils.subscription_checker import check_feature
        interaction = _make_interaction()
        result = await check_feature(interaction, "maintenance")
        assert result is True
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_viewer_is_premium(self):
        """log_viewer is premium — on DB error it should deny (fail closed)."""
        from bot.utils.subscription_checker import check_feature
        interaction = _make_interaction()
        result = await check_feature(interaction, "log_viewer")
        assert result is False

    @pytest.mark.asyncio
    async def test_loot_crates_is_premium(self):
        """loot_crates is premium — on DB error it should deny (fail closed)."""
        from bot.utils.subscription_checker import check_feature
        interaction = _make_interaction()
        result = await check_feature(interaction, "loot_crates")
        assert result is False

    @pytest.mark.asyncio
    async def test_rcon_advanced_is_premium(self):
        """rcon_advanced is premium — on DB error it should deny (fail closed)."""
        from bot.utils.subscription_checker import check_feature
        interaction = _make_interaction()
        result = await check_feature(interaction, "rcon_advanced")
        assert result is False

    @pytest.mark.asyncio
    async def test_server_management_free(self):
        from bot.utils.subscription_checker import check_feature
        interaction = _make_interaction()
        result = await check_feature(interaction, "server_management")
        assert result is True
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_remote_agent_free(self):
        from bot.utils.subscription_checker import check_feature
        interaction = _make_interaction()
        result = await check_feature(interaction, "remote_agent")
        assert result is True
        interaction.response.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# 5b. Player-linking features are PREMIUM (blocked on free)
# ---------------------------------------------------------------------------

class TestPlayerLinkingFeaturesArePremium:
    """Features that require linked players must be blocked on free tier."""

    @pytest.mark.asyncio
    async def test_kits_blocked_on_free(self):
        """kits require linked player + specimen ID — blocked on free tier."""
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("free", "trial")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="free"):
            result = await check_feature(interaction, "kits")

        assert result is False
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_player_management_blocked_on_free(self):
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("free", "trial")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="free"):
            result = await check_feature(interaction, "player_management")

        assert result is False

    @pytest.mark.asyncio
    async def test_analytics_blocked_on_free(self):
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("free", "trial")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="free"):
            result = await check_feature(interaction, "analytics")

        assert result is False

    @pytest.mark.asyncio
    async def test_kits_passes_on_premium(self):
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("premium", "active")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="premium"):
            result = await check_feature(interaction, "kits")

        assert result is True
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_kits_passes_on_lifetime(self):
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("lifetime", "active")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="lifetime"):
            result = await check_feature(interaction, "kits")

        assert result is True


# ---------------------------------------------------------------------------
# 6. Lifetime tier passes all features (same as premium)
# ---------------------------------------------------------------------------

class TestLifetimeTierPassesAll:
    @pytest.mark.asyncio
    async def test_economy_passes_on_lifetime(self):
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("lifetime", "active")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="lifetime"):
            result = await check_feature(interaction, "economy")

        assert result is True

    @pytest.mark.asyncio
    async def test_ask_phoenix_passes_on_lifetime(self):
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("lifetime", "active")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="lifetime"):
            result = await check_feature(interaction, "ask_phoenix")

        assert result is True


# ---------------------------------------------------------------------------
# 7. Premium passes during grace period
# ---------------------------------------------------------------------------

class TestPremiumDuringGracePeriod:
    @pytest.mark.asyncio
    async def test_economy_passes_on_grace(self):
        from bot.utils.subscription_checker import check_feature

        sub = _make_sub("premium", "grace")
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.get_effective_tier", return_value="premium"):
            result = await check_feature(interaction, "economy")

        assert result is True


# ---------------------------------------------------------------------------
# 8. DM context (no guild) is denied
# ---------------------------------------------------------------------------

class TestDMContextDenied:
    @pytest.mark.asyncio
    async def test_premium_feature_denied_in_dm(self):
        from bot.utils.subscription_checker import check_feature

        interaction = _make_interaction(guild_id=None)
        result = await check_feature(interaction, "economy")
        assert result is False


# ---------------------------------------------------------------------------
# 9. Tier level ordering
# ---------------------------------------------------------------------------

class TestTierLevelOrdering:
    def test_free_lt_premium(self):
        from bot.utils.subscription_checker import TIER_LEVELS
        assert TIER_LEVELS["free"] < TIER_LEVELS["premium"]

    def test_premium_lt_lifetime(self):
        from bot.utils.subscription_checker import TIER_LEVELS
        assert TIER_LEVELS["premium"] < TIER_LEVELS["lifetime"]
