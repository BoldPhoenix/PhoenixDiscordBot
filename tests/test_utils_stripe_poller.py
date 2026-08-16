"""
Tests for bot/utils/stripe_poller.py

Covers:
- poll_checkout_sessions upgrades guild to premium on subscription checkout
- poll_checkout_sessions upgrades guild to lifetime on one-time payment
- poll_checkout_sessions skips sessions with no client_reference_id
- poll_checkout_sessions skips already-active guilds with same subscription ID
- poll_active_subscriptions starts grace when Stripe subscription is canceled
- poll_active_subscriptions refreshes subscription_end for active subs
- run_full_poll calls both pollers and returns summary dict
- No crash when STRIPE_SECRET_KEY is empty
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(
    payment_status="paid",
    client_reference_id="12345",
    mode="subscription",
    session_id="cs_test_001",
    sub_id="sub_test_001",
    customer_id="cus_test_001",
    period_end=None,
):
    """Build a minimal fake Stripe Checkout Session object."""
    session = MagicMock()
    session.id = session_id
    session.payment_status = payment_status
    session.client_reference_id = client_reference_id
    session.mode = mode
    session.customer = customer_id
    session.get = lambda k, d=None: {
        "payment_status": payment_status,
        "client_reference_id": client_reference_id,
        "mode": mode,
        "customer": customer_id,
    }.get(k, d)

    if mode == "subscription":
        stripe_sub = MagicMock()
        stripe_sub.id = sub_id
        stripe_sub.current_period_end = period_end or int(
            (datetime.utcnow() + timedelta(days=30)).timestamp()
        )
        session.subscription = stripe_sub
        session.get = lambda k, d=None: {
            "payment_status": payment_status,
            "client_reference_id": client_reference_id,
            "mode": mode,
            "customer": customer_id,
            "subscription": stripe_sub,
        }.get(k, d)
    else:
        session.subscription = None

    return session


def _make_db_sub(
    guild_id=12345,
    tier="free",
    status="trial",
    stripe_subscription_id=None,
    subscription_end=None,
):
    return {
        "guild_id": guild_id,
        "tier": tier,
        "status": status,
        "stripe_subscription_id": stripe_subscription_id,
        "stripe_customer_id": None,
        "subscription_end": subscription_end,
        "grace_end": None,
    }


# ---------------------------------------------------------------------------
# 1. Module imports
# ---------------------------------------------------------------------------

class TestStripePollerImports:
    def test_module_importable(self):
        import bot.utils.stripe_poller  # noqa

    def test_poll_checkout_sessions_importable(self):
        from bot.utils.stripe_poller import poll_checkout_sessions
        assert callable(poll_checkout_sessions)

    def test_poll_active_subscriptions_importable(self):
        from bot.utils.stripe_poller import poll_active_subscriptions
        assert callable(poll_active_subscriptions)

    def test_run_full_poll_importable(self):
        from bot.utils.stripe_poller import run_full_poll
        assert callable(run_full_poll)


# ---------------------------------------------------------------------------
# 2. poll_checkout_sessions — subscription (Premium)
# ---------------------------------------------------------------------------

class TestPollCheckoutSessionsSubscription:
    @pytest.mark.asyncio
    async def test_upgrades_guild_to_premium(self):
        from bot.utils.stripe_poller import poll_checkout_sessions

        session = _make_session(mode="subscription", client_reference_id="12345")
        mock_set_tier = AsyncMock(return_value=True)
        mock_get_sub = AsyncMock(return_value=None)  # No existing sub
        mock_get_or_create = AsyncMock(return_value=_make_db_sub())

        with patch("bot.utils.stripe_poller._fetch_recent_sessions", return_value=[session]), \
             patch("bot.database.subscription_db.get_subscription", mock_get_sub), \
             patch("bot.database.subscription_db.get_or_create_subscription", mock_get_or_create), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            count = await poll_checkout_sessions()

        assert count == 1
        mock_set_tier.assert_called_once()
        args = mock_set_tier.call_args.args
        assert args[0] == 12345
        assert args[1] == "premium"
        assert args[2] == "active"

    @pytest.mark.asyncio
    async def test_skips_unpaid_session(self):
        from bot.utils.stripe_poller import poll_checkout_sessions

        session = _make_session(payment_status="unpaid")
        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.utils.stripe_poller._fetch_recent_sessions", return_value=[session]), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            count = await poll_checkout_sessions()

        assert count == 0
        mock_set_tier.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_session_without_client_reference_id(self):
        from bot.utils.stripe_poller import poll_checkout_sessions

        session = _make_session(client_reference_id=None)
        session.get = lambda k, d=None: {
            "payment_status": "paid",
            "mode": "subscription",
            "customer": "cus_001",
        }.get(k, d)
        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.utils.stripe_poller._fetch_recent_sessions", return_value=[session]), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            count = await poll_checkout_sessions()

        assert count == 0
        mock_set_tier.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_already_active_same_sub_id(self):
        """Should not re-process a session if guild already active with same stripe_subscription_id."""
        from bot.utils.stripe_poller import poll_checkout_sessions

        session = _make_session(mode="subscription", sub_id="sub_existing_001")
        existing_sub = _make_db_sub(tier="premium", status="active", stripe_subscription_id="sub_existing_001")
        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.utils.stripe_poller._fetch_recent_sessions", return_value=[session]), \
             patch("bot.database.subscription_db.get_subscription", AsyncMock(return_value=existing_sub)), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            count = await poll_checkout_sessions()

        assert count == 0
        mock_set_tier.assert_not_called()


# ---------------------------------------------------------------------------
# 3. poll_checkout_sessions — one-time payment (Lifetime)
# ---------------------------------------------------------------------------

class TestPollCheckoutSessionsLifetime:
    @pytest.mark.asyncio
    async def test_upgrades_guild_to_lifetime(self):
        from bot.utils.stripe_poller import poll_checkout_sessions

        session = _make_session(mode="payment", client_reference_id="99999")
        mock_set_tier = AsyncMock(return_value=True)
        mock_get_sub = AsyncMock(return_value=None)
        mock_get_or_create = AsyncMock(return_value=_make_db_sub(guild_id=99999))

        with patch("bot.utils.stripe_poller._fetch_recent_sessions", return_value=[session]), \
             patch("bot.database.subscription_db.get_subscription", mock_get_sub), \
             patch("bot.database.subscription_db.get_or_create_subscription", mock_get_or_create), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            count = await poll_checkout_sessions()

        assert count == 1
        args = mock_set_tier.call_args.args
        assert args[0] == 99999
        assert args[1] == "lifetime"
        assert args[2] == "active"

    @pytest.mark.asyncio
    async def test_skips_already_lifetime_guild(self):
        from bot.utils.stripe_poller import poll_checkout_sessions

        session = _make_session(mode="payment", client_reference_id="77777")
        existing = _make_db_sub(guild_id=77777, tier="lifetime", status="active")
        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.utils.stripe_poller._fetch_recent_sessions", return_value=[session]), \
             patch("bot.database.subscription_db.get_subscription", AsyncMock(return_value=existing)), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            count = await poll_checkout_sessions()

        assert count == 0
        mock_set_tier.assert_not_called()


# ---------------------------------------------------------------------------
# 4. poll_active_subscriptions — cancellation → grace
# ---------------------------------------------------------------------------

class TestPollActiveSubscriptions:
    @pytest.mark.asyncio
    async def test_starts_grace_when_stripe_sub_canceled(self):
        from bot.utils.stripe_poller import poll_active_subscriptions

        db_sub = _make_db_sub(tier="premium", status="active", stripe_subscription_id="sub_cancel_001")
        stripe_sub = MagicMock()
        stripe_sub.get = lambda k, d=None: {"status": "canceled", "current_period_end": None}.get(k, d)

        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.database.subscription_db.get_all_subscriptions", AsyncMock(return_value=[db_sub])), \
             patch("bot.utils.stripe_poller._fetch_subscription", return_value=stripe_sub), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            count = await poll_active_subscriptions()

        assert count == 1
        args = mock_set_tier.call_args.args
        assert args[1] == "premium"
        assert args[2] == "grace"
        assert "grace_end" in mock_set_tier.call_args.kwargs

    @pytest.mark.asyncio
    async def test_does_not_double_grace_already_in_grace(self):
        from bot.utils.stripe_poller import poll_active_subscriptions

        db_sub = _make_db_sub(tier="premium", status="grace", stripe_subscription_id="sub_grace_001")
        stripe_sub = MagicMock()
        stripe_sub.get = lambda k, d=None: {"status": "canceled"}.get(k, d)

        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.database.subscription_db.get_all_subscriptions", AsyncMock(return_value=[db_sub])), \
             patch("bot.utils.stripe_poller._fetch_subscription", return_value=stripe_sub), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            count = await poll_active_subscriptions()

        assert count == 0
        mock_set_tier.assert_not_called()

    @pytest.mark.asyncio
    async def test_refreshes_subscription_end_for_active_sub(self):
        from bot.utils.stripe_poller import poll_active_subscriptions

        future_ts = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        db_sub = _make_db_sub(
            tier="premium", status="active",
            stripe_subscription_id="sub_active_001",
            subscription_end="2026-01-01T00:00:00",  # stale date
        )
        stripe_sub = MagicMock()
        stripe_sub.get = lambda k, d=None: {
            "status": "active",
            "current_period_end": future_ts,
        }.get(k, d)

        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.database.subscription_db.get_all_subscriptions", AsyncMock(return_value=[db_sub])), \
             patch("bot.utils.stripe_poller._fetch_subscription", return_value=stripe_sub), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            await poll_active_subscriptions()

        # set_tier should be called to refresh the date
        mock_set_tier.assert_called_once()
        kwargs = mock_set_tier.call_args.kwargs
        assert "subscription_end" in kwargs

    @pytest.mark.asyncio
    async def test_skips_guilds_without_stripe_subscription_id(self):
        from bot.utils.stripe_poller import poll_active_subscriptions

        db_sub = _make_db_sub(tier="premium", status="active", stripe_subscription_id=None)
        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.database.subscription_db.get_all_subscriptions", AsyncMock(return_value=[db_sub])), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            await poll_active_subscriptions()

        mock_set_tier.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_lifetime_guilds(self):
        from bot.utils.stripe_poller import poll_active_subscriptions

        db_sub = _make_db_sub(tier="lifetime", status="active", stripe_subscription_id="sub_life_001")
        mock_set_tier = AsyncMock(return_value=True)

        with patch("bot.database.subscription_db.get_all_subscriptions", AsyncMock(return_value=[db_sub])), \
             patch("bot.database.subscription_db.set_tier", mock_set_tier):
            await poll_active_subscriptions()

        mock_set_tier.assert_not_called()


# ---------------------------------------------------------------------------
# 5. run_full_poll
# ---------------------------------------------------------------------------

class TestRunFullPoll:
    @pytest.mark.asyncio
    async def test_returns_summary_dict(self):
        from bot.utils.stripe_poller import run_full_poll

        with patch("bot.utils.stripe_poller.poll_checkout_sessions", AsyncMock(return_value=2)), \
             patch("bot.utils.stripe_poller.poll_active_subscriptions", AsyncMock(return_value=1)):
            result = await run_full_poll()

        assert result == {"upgraded": 2, "grace_started": 1}

    @pytest.mark.asyncio
    async def test_handles_checkout_error_gracefully(self):
        from bot.utils.stripe_poller import run_full_poll

        with patch("bot.utils.stripe_poller.poll_checkout_sessions", AsyncMock(side_effect=Exception("API error"))), \
             patch("bot.utils.stripe_poller.poll_active_subscriptions", AsyncMock(return_value=0)):
            result = await run_full_poll()

        assert result["upgraded"] == 0
        assert result["grace_started"] == 0

    @pytest.mark.asyncio
    async def test_handles_subscription_error_gracefully(self):
        from bot.utils.stripe_poller import run_full_poll

        with patch("bot.utils.stripe_poller.poll_checkout_sessions", AsyncMock(return_value=1)), \
             patch("bot.utils.stripe_poller.poll_active_subscriptions", AsyncMock(side_effect=Exception("API error"))):
            result = await run_full_poll()

        assert result["upgraded"] == 1
        assert result["grace_started"] == 0


# ---------------------------------------------------------------------------
# 6. No crash when Stripe key is missing
# ---------------------------------------------------------------------------

class TestNoStripeKey:
    @pytest.mark.asyncio
    async def test_fetch_sessions_returns_empty_without_key(self):
        from bot.utils.stripe_poller import _fetch_recent_sessions
        from bot.utils.config import Config

        original = Config.STRIPE_SECRET_KEY
        Config.STRIPE_SECRET_KEY = ""
        try:
            result = _fetch_recent_sessions(0)
            assert result == []
        finally:
            Config.STRIPE_SECRET_KEY = original

    @pytest.mark.asyncio
    async def test_poll_checkout_returns_zero_without_key(self):
        from bot.utils.stripe_poller import poll_checkout_sessions
        from bot.utils.config import Config

        original = Config.STRIPE_SECRET_KEY
        Config.STRIPE_SECRET_KEY = ""
        try:
            with patch("bot.utils.stripe_poller._fetch_recent_sessions", return_value=[]):
                count = await poll_checkout_sessions()
            assert count == 0
        finally:
            Config.STRIPE_SECRET_KEY = original
