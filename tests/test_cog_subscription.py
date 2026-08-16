"""
Tests for bot/cogs/subscription.py

Covers:
- Module imports and cog instantiation
- /subscription shows tier and status embed
- /subscribe sends embed with payment links
- Non-owner blocked from /subadmin commands
- /subadmin grant_lifetime sets tier=lifetime, status=active
- /subadmin set_tier updates correctly
- subscription_checker_task downgrades expired grace subscriptions
- warning_sender_task sends to log channel
- on_guild_join creates trial subscription
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Minimal bot / interaction helpers
# ---------------------------------------------------------------------------

class _FakeBot:
    def __init__(self):
        self.guilds = []

    def get_channel(self, channel_id):
        return None

    async def wait_until_ready(self):
        pass


def _make_bot():
    return _FakeBot()


def _make_interaction(user_id=999, guild_id=12345, is_owner=False):
    """Build a minimal fake discord.Interaction."""
    # Use a fixed owner ID for tests (will be patched in Config)
    if is_owner:
        user_id = 123456789  # Test owner ID

    interaction = MagicMock()
    interaction.guild_id = guild_id
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.response = MagicMock()
    interaction.response.is_done = MagicMock(return_value=False)
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _make_sub(guild_id=12345, tier="free", status="trial"):
    # Simulate database returning naive ISO strings (no timezone suffix)
    # This is what actually happens when datetime.now(timezone.utc).isoformat() is stored in SQLite
    now = datetime.now(timezone.utc)
    trial_end = now + timedelta(days=25)
    return {
        "id": 1,
        "guild_id": guild_id,
        "tier": tier,
        "status": status,
        "trial_start": now.replace(tzinfo=None).isoformat(),  # Naive datetime like DB returns
        "trial_end": trial_end.replace(tzinfo=None).isoformat(),  # Naive datetime like DB returns
        "subscription_start": None,
        "subscription_end": None,
        "grace_end": None,
        "stripe_customer_id": None,
        "stripe_subscription_id": None,
        "notes": None,
        "created_at": now.replace(tzinfo=None).isoformat(),
        "updated_at": now.replace(tzinfo=None).isoformat(),
    }


# ---------------------------------------------------------------------------
# 1. Import tests
# ---------------------------------------------------------------------------

class TestSubscriptionImports:
    def test_module_importable(self):
        import bot.cogs.subscription  # noqa

    def test_cog_class_importable(self):
        from bot.cogs.subscription import SubscriptionCog
        assert SubscriptionCog is not None

    def test_setup_function_exists(self):
        from bot.cogs.subscription import setup
        assert callable(setup)


# ---------------------------------------------------------------------------
# 2. Cog instantiation
# ---------------------------------------------------------------------------

class TestCogInstantiation:
    def test_cog_instantiates(self):
        from bot.cogs.subscription import SubscriptionCog
        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot
        # Don't start tasks in unit test — just verify it's created
        assert cog.bot is bot


# ---------------------------------------------------------------------------
# 3. /subscription command
# ---------------------------------------------------------------------------

class TestSubscriptionCommand:
    @pytest.mark.asyncio
    async def test_shows_embed_for_guild(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        sub = _make_sub(status="active")  # Free tier is active, not trial
        interaction = _make_interaction()

        with patch("bot.database.subscription_db.get_or_create_subscription", new_callable=AsyncMock, return_value=sub):
            await cog.subscription.callback(cog, interaction)

        interaction.followup.send.assert_called_once()
        call_kwargs = interaction.followup.send.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        assert "embed" in call_kwargs
        # Verify no trial countdown appears for free tier
        embed = call_kwargs["embed"]
        embed_dict = embed.to_dict()
        field_names = [f["name"] for f in embed_dict.get("fields", [])]
        assert "Trial Ends" not in field_names

    @pytest.mark.asyncio
    async def test_rejected_in_dm_context(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        interaction = _make_interaction(guild_id=None)
        await cog.subscription.callback(cog, interaction)

        interaction.followup.send.assert_called_once()
        msg = interaction.followup.send.call_args.args[0] if interaction.followup.send.call_args.args else ""
        assert "server" in msg.lower() or "guild" in msg.lower()


# ---------------------------------------------------------------------------
# 4. /subscribe command
# ---------------------------------------------------------------------------

class TestSubscribeCommand:
    @pytest.mark.asyncio
    async def test_sends_embed_with_view(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        interaction = _make_interaction()
        await cog.subscribe.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        call_kwargs = interaction.response.send_message.call_args.kwargs
        assert call_kwargs.get("ephemeral") is True
        assert "embed" in call_kwargs

    @pytest.mark.asyncio
    async def test_includes_payment_buttons_when_links_configured(self):
        from bot.cogs.subscription import SubscriptionCog
        from bot.utils.config import Config

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        interaction = _make_interaction()

        with patch.object(Config, "STRIPE_PREMIUM_LINK", "https://buy.stripe.com/premium"), \
             patch.object(Config, "STRIPE_LIFETIME_LINK", "https://buy.stripe.com/lifetime"):
            await cog.subscribe.callback(cog, interaction)

        call_kwargs = interaction.response.send_message.call_args.kwargs
        view = call_kwargs.get("view")
        assert view is not None
        # Should have 2 buttons
        button_labels = [item.label for item in view.children]
        assert any("Premium" in label for label in button_labels)
        assert any("Lifetime" in label for label in button_labels)


# ---------------------------------------------------------------------------
# 5. /subadmin — non-owner blocked
# ---------------------------------------------------------------------------

class TestSubadminOwnerGate:
    @pytest.mark.asyncio
    async def test_non_owner_blocked_from_status(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        interaction = _make_interaction(user_id=999)  # not owner
        with patch("bot.utils.config.Config.BOT_OWNER_DISCORD_ID", 123456789):
            await cog.subadmin_status.callback(cog, interaction, guild_id="12345")

        interaction.response.send_message.assert_called_once()
        msg = interaction.response.send_message.call_args.args[0] if interaction.response.send_message.call_args.args else ""
        assert "owner" in msg.lower() or "❌" in msg

    @pytest.mark.asyncio
    async def test_non_owner_blocked_from_set_tier(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        interaction = _make_interaction(user_id=999)
        with patch("bot.utils.config.Config.BOT_OWNER_DISCORD_ID", 123456789):
            await cog.subadmin_set_tier.callback(cog, interaction, guild_id="12345", tier="premium", status="active")

        interaction.response.send_message.assert_called_once()
        msg = interaction.response.send_message.call_args.args[0] if interaction.response.send_message.call_args.args else ""
        assert "owner" in msg.lower() or "❌" in msg

    @pytest.mark.asyncio
    async def test_non_owner_blocked_from_grant_lifetime(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        interaction = _make_interaction(user_id=999)
        with patch("bot.utils.config.Config.BOT_OWNER_DISCORD_ID", 123456789):
            await cog.subadmin_grant_lifetime.callback(cog, interaction, guild_id="12345")

        interaction.response.send_message.assert_called_once()
        msg = interaction.response.send_message.call_args.args[0] if interaction.response.send_message.call_args.args else ""
        assert "owner" in msg.lower() or "❌" in msg

    @pytest.mark.asyncio
    async def test_non_owner_blocked_from_list(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        interaction = _make_interaction(user_id=999)
        with patch("bot.utils.config.Config.BOT_OWNER_DISCORD_ID", 123456789):
            await cog.subadmin_list.callback(cog, interaction)

        interaction.response.send_message.assert_called_once()
        msg = interaction.response.send_message.call_args.args[0] if interaction.response.send_message.call_args.args else ""
        assert "owner" in msg.lower() or "❌" in msg


# ---------------------------------------------------------------------------
# 6. /subadmin grant_lifetime (owner)
# ---------------------------------------------------------------------------

class TestSubadminGrantLifetime:
    @pytest.mark.asyncio
    async def test_grant_lifetime_sets_correct_tier(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        sub = _make_sub()
        interaction = _make_interaction(is_owner=True)
        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.utils.config.Config.BOT_OWNER_DISCORD_ID", 123456789), \
             patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            await cog.subadmin_grant_lifetime.callback(cog, interaction, guild_id="12345")

        mock_set_tier.assert_called_once()
        args = mock_set_tier.call_args.args
        assert args[1] == "lifetime"
        assert args[2] == "active"

    @pytest.mark.asyncio
    async def test_grant_lifetime_with_note(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        sub = _make_sub()
        interaction = _make_interaction(is_owner=True)
        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.utils.config.Config.BOT_OWNER_DISCORD_ID", 123456789), \
             patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            await cog.subadmin_grant_lifetime.callback(cog, interaction, guild_id="12345", note="Volunteer tester")

        kwargs = mock_set_tier.call_args.kwargs
        assert kwargs.get("notes") == "Volunteer tester"


# ---------------------------------------------------------------------------
# 7. /subadmin set_tier (owner)
# ---------------------------------------------------------------------------

class TestSubadminSetTier:
    @pytest.mark.asyncio
    async def test_set_tier_premium_active(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        sub = _make_sub()
        interaction = _make_interaction(is_owner=True)
        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.utils.config.Config.BOT_OWNER_DISCORD_ID", 123456789), \
             patch("bot.database.subscription_db.get_or_create_subscription", AsyncMock(return_value=sub)), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            await cog.subadmin_set_tier.callback(
                cog, interaction, guild_id="12345", tier="premium", status="active"
            )

        mock_set_tier.assert_called_once()
        args = mock_set_tier.call_args.args
        assert args[1] == "premium"
        assert args[2] == "active"

    @pytest.mark.asyncio
    async def test_set_tier_invalid_tier_rejected(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        interaction = _make_interaction(is_owner=True)

        with patch("bot.utils.config.Config.BOT_OWNER_DISCORD_ID", 123456789):
            await cog.subadmin_set_tier.callback(
                cog, interaction, guild_id="12345", tier="invalid", status="active"
            )

        interaction.followup.send.assert_called_once()
        msg = interaction.followup.send.call_args.args[0] if interaction.followup.send.call_args.args else ""
        assert "tier must be" in msg.lower() or "❌" in msg


# ---------------------------------------------------------------------------
# 8. subscription_checker_task downgrades expired grace subs
# ---------------------------------------------------------------------------

class TestSubscriptionCheckerTask:
    @pytest.mark.asyncio
    async def test_downgrades_expired_grace_sub(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        # Grace ended yesterday
        grace_end = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        sub = _make_sub(tier="premium", status="grace")
        sub["grace_end"] = grace_end

        mock_get_grace = AsyncMock(return_value=[sub])
        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.database.subscription_db.get_grace_period_subscriptions", mock_get_grace), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            await cog.subscription_checker_task()

        mock_set_tier.assert_called_once_with(sub["guild_id"], "free", "expired")

    @pytest.mark.asyncio
    async def test_does_not_downgrade_active_grace(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        # Grace ends in 3 days (not yet expired)
        grace_end = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        sub = _make_sub(tier="premium", status="grace")
        sub["grace_end"] = grace_end

        mock_get_grace = AsyncMock(return_value=[sub])
        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.database.subscription_db.get_grace_period_subscriptions", mock_get_grace), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            await cog.subscription_checker_task()

        mock_set_tier.assert_not_called()


# ---------------------------------------------------------------------------
# 9. warning_sender_task sends to log channel
# ---------------------------------------------------------------------------

class TestWarningSenderTask:
    @pytest.mark.asyncio
    async def test_sends_warning_for_grace_sub(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        # Provide a mock channel
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        bot.get_channel = MagicMock(return_value=mock_channel)

        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        grace_end = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        sub = _make_sub(tier="premium", status="grace")
        sub["grace_end"] = grace_end

        mock_config = {"admin_log_channel_id": 999888}

        with patch("bot.database.subscription_db.get_grace_period_subscriptions", AsyncMock(return_value=[sub])), \
             patch("bot.database.subscription_db.get_expiring_trials", AsyncMock(return_value=[])), \
             patch("bot.database.server_config_db.get_server_config", AsyncMock(return_value=mock_config)):
            await cog.warning_sender_task()

        mock_channel.send.assert_called()

    @pytest.mark.asyncio
    async def test_sends_trial_expiry_warning(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        bot.get_channel = MagicMock(return_value=mock_channel)

        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        trial_end = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        sub = _make_sub(tier="free", status="trial")
        sub["trial_end"] = trial_end

        mock_config = {"admin_log_channel_id": 999888}

        with patch("bot.database.subscription_db.get_grace_period_subscriptions", AsyncMock(return_value=[])), \
             patch("bot.database.subscription_db.get_expiring_trials", AsyncMock(return_value=[sub])), \
             patch("bot.database.server_config_db.get_server_config", AsyncMock(return_value=mock_config)):
            await cog.warning_sender_task()

        mock_channel.send.assert_called()


# ---------------------------------------------------------------------------
# 10. on_guild_join creates trial subscription
# ---------------------------------------------------------------------------

class TestOnGuildJoin:
    @pytest.mark.asyncio
    async def test_creates_subscription_on_join(self):
        from bot.cogs.subscription import SubscriptionCog

        bot = _make_bot()
        cog = SubscriptionCog.__new__(SubscriptionCog)
        cog.bot = bot

        guild = MagicMock()
        guild.id = 77777

        sub = _make_sub(guild_id=77777)
        mock_get_or_create = AsyncMock(return_value=sub)

        with patch("bot.database.subscription_db.get_or_create_subscription", mock_get_or_create):
            await cog.on_guild_join(guild)

        mock_get_or_create.assert_called_once_with(77777)


# ---------------------------------------------------------------------------
# 11. Tier-downgrade notification wiring
# ---------------------------------------------------------------------------

class TestTierDowngradeNotification:
    """notify_tier_change_downgrade must be called when a guild is downgraded
    to free tier via /subadmin set_tier or the subscription_checker_task."""

    def test_subadmin_set_tier_source_calls_notify(self):
        """subadmin_set_tier must call notify_tier_change_downgrade so the guild
        admin receives a Discord message listing the disabled servers."""
        import inspect
        from bot.cogs.subscription import SubscriptionCog
        source = inspect.getsource(SubscriptionCog.subadmin_set_tier.callback)
        assert "notify_tier_change_downgrade" in source, (
            "subadmin_set_tier.callback must call notify_tier_change_downgrade "
            "so guild admins are informed when servers are auto-disabled"
        )

    def test_subscription_checker_task_source_calls_notify(self):
        """subscription_checker_task must call notify_tier_change_downgrade when
        it downgrades an expired grace subscription to free."""
        import inspect
        from bot.cogs.subscription import SubscriptionCog
        # subscription_checker_task is a tasks.Loop; the coroutine is in .coro
        task = SubscriptionCog.subscription_checker_task
        coro = getattr(task, "coro", task)
        source = inspect.getsource(coro)
        assert "notify_tier_change_downgrade" in source, (
            "subscription_checker_task must call notify_tier_change_downgrade "
            "so guild admins are informed when their subscription expires"
        )
