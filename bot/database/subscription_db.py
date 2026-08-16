"""
Subscription database operations.
Handles guild tier tracking, trial management, and grace period logic.
"""

import aiosqlite
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from bot.utils.config import Config

logger = logging.getLogger("SubscriptionDB")

_db_path = lambda: Config.DATABASE_PATH


async def init_subscription_tables():
    """Create subscription table if it doesn't exist."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id                INTEGER NOT NULL UNIQUE,
                tier                    TEXT NOT NULL DEFAULT 'free',
                status                  TEXT NOT NULL DEFAULT 'trial',
                stripe_customer_id      TEXT,
                stripe_subscription_id  TEXT,
                customer_email          TEXT,
                trial_start             TEXT DEFAULT CURRENT_TIMESTAMP,
                trial_end               TEXT,
                subscription_start      TEXT,
                subscription_end        TEXT,
                grace_end               TEXT,
                notes                   TEXT,
                created_at              TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at              TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Migration: add customer_email to existing installs
        try:
            await db.execute("ALTER TABLE subscriptions ADD COLUMN customer_email TEXT")
        except Exception:
            pass  # Column already exists
        await db.commit()
        logger.info("Subscription table initialized")


def get_effective_tier(sub: Optional[dict]) -> str:
    """Return the effective tier for a subscription record.

    Rules:
    - None / missing → 'free'
    - lifetime tier → 'lifetime' always
    - premium + active or grace → 'premium'
    - everything else → 'free'
    """
    if sub is None:
        return "free"
    if sub.get("tier") == "lifetime":
        return "lifetime"
    if sub.get("tier") == "premium" and sub.get("status") in ("active", "grace"):
        return "premium"
    return "free"


async def get_subscription(guild_id: int) -> Optional[dict]:
    """Return the subscription record for a guild, or None if not found."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_or_create_subscription(guild_id: int) -> dict:
    """Return subscription for guild, creating permanent free tier if not found."""
    existing = await get_subscription(guild_id)
    if existing:
        return existing

    async with aiosqlite.connect(_db_path()) as db:
        trial_end = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)).isoformat()
        await db.execute(
            """
            INSERT OR IGNORE INTO subscriptions
                (guild_id, tier, status, trial_end)
            VALUES (?, 'free', 'active', ?)
            """,
            (guild_id, trial_end),
        )
        await db.commit()

    return await get_subscription(guild_id)


async def set_tier(guild_id: int, tier: str, status: str, **kwargs) -> bool:
    """Update the tier and status for a guild subscription.

    Extra kwargs are merged into the UPDATE (e.g. notes, grace_end, subscription_end).
    
    Triggers tier change handler when tier changes.
    """
    valid_extra = {
        "stripe_customer_id", "stripe_subscription_id",
        "customer_email",
        "subscription_start", "subscription_end",
        "trial_start", "trial_end",
        "grace_end", "notes",
    }
    extra = {k: v for k, v in kwargs.items() if k in valid_extra}

    # Get old tier before update
    old_sub = await get_subscription(guild_id)
    old_tier = get_effective_tier(old_sub) if old_sub else "free"

    set_parts = ["tier = ?", "status = ?", "updated_at = CURRENT_TIMESTAMP"]
    values = [tier, status]
    for col, val in extra.items():
        set_parts.append(f"{col} = ?")
        values.append(val)
    values.append(guild_id)

    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                f"UPDATE subscriptions SET {', '.join(set_parts)} WHERE guild_id = ?",
                values,
            )
            await db.commit()
        
        # Trigger tier change handler if tier changed
        new_tier = tier if tier != "lifetime" else tier  # lifetime stays lifetime
        if old_tier != new_tier:
            await handle_tier_change(guild_id, old_tier, new_tier)
        
        return True
    except Exception as e:
        logger.error(f"set_tier error: {e}")
        return False


async def get_all_subscriptions() -> list:
    """Return all subscription records (used by /subadmin list)."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_expiring_trials(days_ahead: int = 3) -> list:
    """Return guilds whose trial_end falls within the next N days."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM subscriptions
            WHERE status = 'trial'
              AND trial_end IS NOT NULL
              AND trial_end <= datetime('now', ? || ' days')
              AND trial_end >= datetime('now')
            """,
            (f"+{days_ahead}",),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_grace_period_subscriptions() -> list:
    """Return all subscriptions currently in grace period."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE status = 'grace' AND grace_end IS NOT NULL"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def handle_tier_change(guild_id: int, old_tier: str, new_tier: str) -> dict:
    """Handle subscription tier changes and enforce server limits.
    
    When downgrading from Premium/Lifetime to Free:
    - Disable servers beyond the free tier limit (2 servers)
    - Log the changes
    
    When upgrading to Premium/Lifetime:
    - Servers remain as-is (can be manually re-enabled via admin panel)
    
    Args:
        guild_id: The Discord guild ID
        old_tier: The previous tier ('free', 'premium', 'lifetime')
        new_tier: The new tier ('free', 'premium', 'lifetime')
    
    Returns:
        Dict with 'disabled' list of server names, 'action' description
    """
    from bot.database import server_config_db
    
    result = {"disabled": [], "reenabled": [], "action": "none"}

    # Upgrade path: re-enable servers that were disabled due to tier limits
    if old_tier == "free" and new_tier in ("premium", "lifetime"):
        try:
            reenabled = await server_config_db.enable_tier_limited_servers(guild_id)
        except Exception as e:
            logger.warning(f"Could not re-enable tier-limited servers for guild {guild_id}: {e}")
            reenabled = []
        result["action"] = "upgraded"
        result["reenabled"] = reenabled
        return result

    # Only act on downgrade to free tier
    if new_tier != "free":
        return result
    
    # Downgrade to free - enforce 2-server limit
    free_limit = 2
    disabled_servers = await server_config_db.disable_servers_beyond_limit(guild_id, free_limit, "tier_limit")
    
    if disabled_servers:
        result["disabled"] = disabled_servers
        result["action"] = "downgraded"
        logger.info(
            f"Subscription downgrade: Guild {guild_id} downgraded to Free. "
            f"Disabled {len(disabled_servers)} servers: {disabled_servers}"
        )
    else:
        result["action"] = "downgraded_no_change"
    
    return result


async def notify_tier_change_downgrade(guild_id: int, disabled_servers: list, bot) -> None:
    """Send notification to guild about tier downgrade and disabled servers.
    
    Args:
        guild_id: The Discord guild ID
        disabled_servers: List of server names that were disabled
        bot: The discord bot instance
    """
    import discord
    from bot.database import server_config_db
    
    if not disabled_servers:
        return
    
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    
    # Try to get admin log channel or use default
    config = await server_config_db.get_server_config(guild_id)
    channel_id = config.get("admin_log_channel_id") if config else None
    
    if not channel_id:
        # Try to find a suitable channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                channel_id = channel.id
                break
    
    if not channel_id:
        return
    
    channel = guild.get_channel(channel_id)
    if not channel:
        return
    
    servers_list = "\n".join([f"• {name}" for name in disabled_servers])
    
    embed = discord.Embed(
        title="⚠️ Subscription Downgraded to Free Tier",
        description=(
            f"Your subscription has been downgraded to **Free** tier.\n\n"
            f"The following servers have been automatically disabled:\n{servers_list}\n\n"
            f"**Free tier limit: 2 servers**\n\n"
            "Disabled servers are preserved in your configuration but will not:\n"
            "• Appear in status embeds\n"
            "• Receive chat relay\n"
            "• Be monitored for updates\n\n"
            "**To re-enable servers:**\n"
            "Upgrade to Premium or Lifetime to manage unlimited servers."
        ),
        color=discord.Color.orange()
    )
    
    try:
        await channel.send(embed=embed)
    except Exception as e:
        logger.error(f"Failed to send tier downgrade notification: {e}")
