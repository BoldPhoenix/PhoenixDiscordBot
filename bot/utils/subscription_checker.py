"""
Subscription feature-gating utilities.

Usage in any cog command:
    from bot.utils.subscription_checker import check_feature

    async def my_command(self, interaction):
        if not await check_feature(interaction, "economy"):
            return
        # ... rest of command
"""

import discord
import logging

logger = logging.getLogger("SubscriptionChecker")

# Tier ordering (higher = more access)
TIER_LEVELS = {"free": 0, "premium": 1, "lifetime": 2}

# Feature → minimum tier required
# Note: premium and lifetime have IDENTICAL features — lifetime is just a one-time payment option.
FEATURE_TIERS: dict[str, str] = {
    # Free tier - server management features (limited to 1 agent, 2 servers)
    "server_monitoring": "free",  # Voice channels, status embeds (RCON only)
    "basic_rcon": "free",          # Direct RCON commands (no player-specific data)
    "chat_relay": "free",          # Discord ↔ ARK chat bridge (no linking needed)
    "remote_agent": "free",        # Remote agent management (1 agent, 2 servers on free)
    "mod_management": "free",      # Mod installation/management (free tier: up to 2 servers)
    "ini_management": "free",      # INI file editing (free tier: up to 2 servers)
    "server_management": "free",   # Server control panel (free tier: up to 2 servers)
    "maintenance": "free",        # Backups and updates (free tier: up to 2 servers)
    # Premium (and Lifetime — same feature set)
    # Everything below requires economy/linking infrastructure
    "kits": "premium",             # Requires specimen ID for delivery
    "economy": "premium",          # IS the linking/balance system
    "shop": "premium",             # Requires linking for purchases
    "games": "premium",            # Requires coin balance (economy)
    "ask_phoenix": "premium",      # AI assistant (API quota protection)
    "log_viewer": "premium",       # Server log access
    "player_management": "premium",# IS the linking system
    "rcon_advanced": "premium",    # Advanced RCON features
    "analytics": "premium",       # Analytics dashboard
    "loot_crates": "premium",     # Loot crate configuration
}

# Server / voice channel / AI limits per tier
# Lifetime mirrors Premium — only payment model differs, not access level.
SERVER_LIMITS: dict[str, int | None] = {"free": 2, "premium": 10, "lifetime": 10}
VOICE_LIMITS:  dict[str, int | None] = {"free": 2, "premium": 10, "lifetime": 10}
AI_DAILY_LIMITS: dict[str, int | None] = {"free": 0, "premium": 20, "lifetime": 20}

_TIER_LABELS = {
    "free": "Free",
    "premium": "Premium",
    "lifetime": "Lifetime",
}

_TIER_PRICES = {
    "premium": "$9.99/mo",
    "lifetime": "$199 once",
}


async def check_feature(interaction: discord.Interaction, feature: str) -> bool:
    """Gate a feature by the guild's effective subscription tier.

    Returns True if the guild has access.
    Sends an ephemeral upgrade embed and returns False if access is denied.
    """
    from bot.utils.config import Config

    # SELF-HOSTED INSTANCES GET EVERYTHING.
    #
    # The tier table below describes the hosted service this bot grew up as, where premium paid
    # for someone else's hardware. If you are running your own copy there is nobody to pay and
    # nothing to unlock — so with billing off (no STRIPE_SECRET_KEY, which is the default) every
    # feature is available. Without this, cloning the repo would hand you a crippled bot: no
    # shop, no economy, no games, no kits, no AI, and a two-server cap.
    if not Config.BILLING_ENABLED:
        return True

    from bot.database import subscription_db

    required_tier = FEATURE_TIERS.get(feature, "free")
    if required_tier == "free":
        return True  # Always allowed

    guild_id = interaction.guild_id
    if guild_id is None:
        # DM context — deny
        await _send_upgrade_embed(interaction, feature, required_tier, "free", "Free")
        return False

    try:
        sub = await subscription_db.get_or_create_subscription(guild_id)
        effective = subscription_db.get_effective_tier(sub)
        logger.info(f"check_feature: guild={guild_id}, feature={feature}, required={required_tier}, effective={effective}")
    except Exception as e:
        logger.error(f"check_feature DB error for guild {guild_id}: {e}")
        # Free-tier features fail open (don't block basic functionality on DB errors).
        # Premium features fail closed (deny access when we can't verify the subscription).
        if required_tier == "free":
            return True
        return False

    if TIER_LEVELS.get(effective, 0) >= TIER_LEVELS.get(required_tier, 0):
        logger.info(f"check_feature PASSED: {effective} >= {required_tier}")
        return True

    logger.info(f"check_feature DENIED: {effective} < {required_tier}")

    tier_label = _TIER_LABELS.get(effective, effective.title())
    status = sub.get("status", "trial") if sub else "trial"
    current_label = f"{tier_label} ({'Trial' if status == 'trial' else status.title()})"

    await _send_upgrade_embed(interaction, feature, required_tier, effective, current_label)
    return False


async def _send_upgrade_embed(
    interaction: discord.Interaction,
    feature: str,
    required_tier: str,
    current_tier: str,
    current_label: str,
) -> None:
    """Send an ephemeral embed telling the user they need to upgrade."""
    tier_label = _TIER_LABELS.get(required_tier, required_tier.title())
    price = _TIER_PRICES.get(required_tier, "")
    price_str = f" ({price})" if price else ""

    embed = discord.Embed(
        title=f"⭐ {tier_label} Feature",
        description=(
            f"This feature requires **{tier_label}{price_str}**.\n"
            f"Your current tier: **{current_label}**\n\n"
            "Use `/subscribe` to upgrade or `/subscription` to view your plan."
        ),
        color=discord.Color.gold(),
    )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        logger.warning(f"Failed to send upgrade embed: {e}")
