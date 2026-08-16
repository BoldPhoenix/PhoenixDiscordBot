"""
Stripe polling utilities for Phase 11.2.

Polls Stripe for:
1. Newly completed checkout sessions → upgrade guild tier
2. Active subscription status changes → detect cancellations → start grace period

All Stripe API calls are sync (stripe SDK) wrapped in asyncio.to_thread so they
don't block the event loop.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from bot.utils.config import Config
from bot.database import subscription_db

logger = logging.getLogger("StripePoller")

# How far back to look for new checkout sessions on each poll (2x the poll interval)
_SESSION_LOOKBACK_HOURS = 2


def _get_stripe():
    """Return a configured stripe module, or None if key is missing."""
    try:
        import stripe
        key = getattr(Config, "STRIPE_SECRET_KEY", "")
        if not key:
            return None
        stripe.api_key = key
        return stripe
    except ImportError:
        logger.warning("stripe package not installed — Stripe polling disabled")
        return None


# ---------------------------------------------------------------------------
# Checkout session polling (detects new subscriptions / lifetime purchases)
# ---------------------------------------------------------------------------

def _fetch_recent_sessions(since_ts: int) -> list:
    """Synchronous Stripe call — run in executor."""
    stripe = _get_stripe()
    if not stripe:
        return []
    sessions = []
    try:
        page = stripe.checkout.Session.list(
            limit=100,
            created={"gte": since_ts},
            expand=["data.subscription"],
        )
        for session in page.auto_paging_iter():
            sessions.append(session)
    except Exception as e:
        logger.error(f"Stripe session list error: {e}")
    return sessions


async def poll_checkout_sessions() -> int:
    """Poll Stripe for completed checkout sessions and upgrade guilds.

    Returns number of guilds upgraded.
    """
    since_ts = int((datetime.utcnow() - timedelta(hours=_SESSION_LOOKBACK_HOURS)).timestamp())
    sessions = await asyncio.to_thread(_fetch_recent_sessions, since_ts)

    upgraded = 0
    for session in sessions:
        if session.get("payment_status") != "paid":
            continue

        client_ref = session.get("client_reference_id")
        if not client_ref:
            continue

        try:
            guild_id = int(client_ref)
        except (ValueError, TypeError):
            logger.warning(f"Invalid client_reference_id on session {session.id}: {client_ref!r}")
            continue

        existing = await subscription_db.get_subscription(guild_id)

        mode = session.get("mode")
        customer_id = session.get("customer") or ""
        # Email comes from customer_details (filled during checkout) or customer_email field
        customer_details = session.get("customer_details") or {}
        email = (
            customer_details.get("email")
            or session.get("customer_email")
            or ""
        )

        if mode == "subscription":
            stripe_sub = session.get("subscription")
            sub_id = stripe_sub.id if stripe_sub else None
            period_end = (
                datetime.fromtimestamp(stripe_sub.current_period_end).isoformat()
                if stripe_sub and stripe_sub.current_period_end
                else None
            )
            # Skip if already active with this subscription ID (avoid re-processing)
            if (
                existing
                and existing.get("status") == "active"
                and existing.get("stripe_subscription_id") == sub_id
            ):
                continue

            await subscription_db.get_or_create_subscription(guild_id)
            await subscription_db.set_tier(
                guild_id,
                "premium",
                "active",
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
                customer_email=email,
                subscription_start=datetime.utcnow().isoformat(),
                subscription_end=period_end,
            )
            logger.info(f"Guild {guild_id} upgraded to Premium via Stripe session {session.id}")
            upgraded += 1

        elif mode == "payment":
            # One-time payment = Lifetime
            if existing and existing.get("tier") == "lifetime" and existing.get("status") == "active":
                continue

            await subscription_db.get_or_create_subscription(guild_id)
            await subscription_db.set_tier(
                guild_id,
                "lifetime",
                "active",
                stripe_customer_id=customer_id,
                customer_email=email,
                subscription_start=datetime.utcnow().isoformat(),
            )
            logger.info(f"Guild {guild_id} upgraded to Lifetime via Stripe session {session.id}")
            upgraded += 1

    return upgraded


# ---------------------------------------------------------------------------
# Active subscription status polling (detects cancellations)
# ---------------------------------------------------------------------------

def _fetch_subscription(sub_id: str) -> Optional[object]:
    """Synchronous Stripe call — run in executor."""
    stripe = _get_stripe()
    if not stripe:
        return None
    try:
        return stripe.Subscription.retrieve(sub_id)
    except Exception as e:
        logger.error(f"Stripe subscription retrieve error for {sub_id}: {e}")
        return None


async def poll_active_subscriptions() -> int:
    """Check status of all tracked Premium subscriptions.

    Starts grace period for subscriptions that have lapsed in Stripe.
    Returns number of guilds affected.
    """
    all_subs = await subscription_db.get_all_subscriptions()
    affected = 0

    for sub in all_subs:
        stripe_sub_id = sub.get("stripe_subscription_id")
        if not stripe_sub_id:
            continue
        if sub.get("tier") != "premium":
            continue
        if sub.get("status") not in ("active", "grace"):
            continue

        guild_id = sub["guild_id"]
        stripe_sub = await asyncio.to_thread(_fetch_subscription, stripe_sub_id)
        if stripe_sub is None:
            continue

        stripe_status = stripe_sub.get("status", "")
        period_end = stripe_sub.get("current_period_end")

        if stripe_status == "active":
            # Refresh subscription_end date
            new_end = datetime.fromtimestamp(period_end).isoformat() if period_end else None
            if new_end and new_end != sub.get("subscription_end"):
                await subscription_db.set_tier(
                    guild_id, "premium", "active", subscription_end=new_end
                )
            # Ensure not stuck in grace
            if sub.get("status") == "grace":
                await subscription_db.set_tier(
                    guild_id, "premium", "active", subscription_end=new_end, grace_end=None
                )

        elif stripe_status in ("canceled", "unpaid", "past_due"):
            if sub.get("status") != "grace":
                grace_end = (datetime.utcnow() + timedelta(days=7)).isoformat()
                await subscription_db.set_tier(
                    guild_id, "premium", "grace", grace_end=grace_end
                )
                logger.info(
                    f"Guild {guild_id} Premium lapsed (Stripe status={stripe_status}) — 7-day grace started"
                )
                affected += 1

    return affected


async def run_full_poll() -> dict:
    """Run both checkout and subscription polls. Returns summary dict."""
    try:
        upgraded = await poll_checkout_sessions()
    except Exception as e:
        logger.error(f"poll_checkout_sessions error: {e}")
        upgraded = 0

    try:
        affected = await poll_active_subscriptions()
    except Exception as e:
        logger.error(f"poll_active_subscriptions error: {e}")
        affected = 0

    return {"upgraded": upgraded, "grace_started": affected}
