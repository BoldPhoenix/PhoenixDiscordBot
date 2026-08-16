"""
Configuration module for the bot.
Simplified - only bot token required in .env!
All other configuration stored in database per-server.
"""

import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Bot configuration - minimal .env, everything else in database."""

    # Required: Bot Token
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

    # Database path (can override, but has sensible default)
    DATABASE_PATH = os.getenv("DATABASE_PATH", "bot.db")
    
    # Bot owner Discord ID for admin-only commands
    BOT_OWNER_DISCORD_ID = int(os.getenv("BOT_OWNER_DISCORD_ID", "0")) if os.getenv("BOT_OWNER_DISCORD_ID") else None
    
    # Server management paths (for self-hosted servers)
    STEAMCMD_PATH = os.getenv("STEAMCMD_PATH", r"C:\SteamCMD\steamcmd.exe")

    # Logging configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "logs/bot.log")

    # =========================================================================
    # LEGACY .ENV SUPPORT (Fallback Compatibility)
    # These are read from .env for backward compatibility
    # Database configuration takes precedence when available
    # =========================================================================

    DISCORD_GUILD_ID = (
        int(os.getenv("DISCORD_GUILD_ID", "0")) if os.getenv("DISCORD_GUILD_ID") else None
    )
    CHAT_CHANNEL_ID = (
        int(os.getenv("CHAT_CHANNEL_ID", "0")) if os.getenv("CHAT_CHANNEL_ID") else None
    )
    ADMIN_LOG_CHANNEL_ID = (
        int(os.getenv("ADMIN_LOG_CHANNEL_ID", "0")) if os.getenv("ADMIN_LOG_CHANNEL_ID") else None
    )
    STATUS_CHANNEL_ID = (
        int(os.getenv("STATUS_CHANNEL_ID", "0")) if os.getenv("STATUS_CHANNEL_ID") else None
    )
    SHOP_CHANNEL_ID = (
        int(os.getenv("SHOP_CHANNEL_ID", "0")) if os.getenv("SHOP_CHANNEL_ID") else None
    )
    LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0")) if os.getenv("LOG_CHANNEL_ID") else None
    SHOP_ANNOUNCEMENT_CHANNEL = (
        int(os.getenv("SHOP_ANNOUNCEMENT_CHANNEL", "0"))
        if os.getenv("SHOP_ANNOUNCEMENT_CHANNEL")
        else None
    )
    ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID", "0")) if os.getenv("ADMIN_ROLE_ID") else None

    # Legacy ARK server config (for fallback)
    ARK_SERVERS = json.loads(os.getenv("ARK_SERVERS", "[]"))

    # Legacy bot config (for fallback)
    BOT_PREFIX = os.getenv("BOT_PREFIX", "!")
    CURRENCY_NAME = os.getenv("CURRENCY_NAME", "Phoenix Coins")
    CURRENCY_EMOJI = os.getenv("CURRENCY_EMOJI", "🪙")
    STATUS_UPDATE_INTERVAL = int(os.getenv("STATUS_UPDATE_INTERVAL", "60"))
    CHAT_POLL_INTERVAL = int(os.getenv("CHAT_POLL_INTERVAL", "5"))

    # Legacy shop config (for fallback)
    SHOP_ENABLED = os.getenv("SHOP_ENABLED", "true").lower() == "true"
    SHOP_ITEMS_PER_PAGE = int(os.getenv("SHOP_ITEMS_PER_PAGE", "10"))
    SHOP_STARTING_BALANCE = int(os.getenv("SHOP_STARTING_BALANCE", "1000"))
    SHOP_DAILY_LOGIN_BONUS = int(os.getenv("SHOP_DAILY_LOGIN_BONUS", "100"))
    SHOP_ALLOW_REFUNDS = os.getenv("SHOP_ALLOW_REFUNDS", "false").lower() == "true"
    SHOP_REFUND_PERCENTAGE = int(os.getenv("SHOP_REFUND_PERCENTAGE", "50"))
    SHOP_MAX_PURCHASE_PER_DAY = int(os.getenv("SHOP_MAX_PURCHASE_PER_DAY", "0"))
    SHOP_DELIVERY_COOLDOWN = int(os.getenv("SHOP_DELIVERY_COOLDOWN", "60"))
    SHOP_REQUIRE_LINKED_ACCOUNT = (
        os.getenv("SHOP_REQUIRE_LINKED_ACCOUNT", "false").lower() == "true"
    )

    # ASA parsing config
    ASA_CLUSTER_ROOT = os.getenv("ASA_CLUSTER_ROOT", None)
    ASA_XP_TABLE_JSON = os.getenv("ASA_XP_TABLE_JSON", "config/xp_table_asa.json")
    
    # PhoenixAI configuration
    PHOENIX_GEMINI_API_KEY = os.getenv("PHOENIX_GEMINI_API_KEY", "")
    PHOENIX_RAG_DB_PATH = os.getenv("PHOENIX_RAG_DB_PATH", "data/phoenixark.db")
    
    # Stripe payment links for subscriptions
    # BILLING IS OFF unless you deliberately turn it on.
    #
    # This bot was originally run as a hosted, multi-tenant service, so features were split into
    # free and premium tiers and gated by a Stripe subscription. Self-hosted, that split makes no
    # sense: you own the instance, you pay for the hardware, and there is nobody to bill you.
    # With no STRIPE_SECRET_KEY set — the default — BILLING_ENABLED is False and every feature is
    # unlocked (see bot/utils/subscription_checker.check_feature).
    #
    # If you genuinely want to run this as a paid service for other people, set the Stripe
    # variables and the original tier gating comes back. That is your undertaking, including the
    # legal and tax parts of it; nothing here is configured for you.
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PREMIUM_LINK = os.getenv("STRIPE_PREMIUM_LINK", "")
    STRIPE_LIFETIME_LINK = os.getenv("STRIPE_LIFETIME_LINK", "")

    #: True only when a Stripe secret key is configured. Everything tier-related keys off this.
    BILLING_ENABLED = bool(os.getenv("STRIPE_SECRET_KEY", "").strip())

    @classmethod
    def load_ark_servers(cls):
        """Load ARK servers from .env (legacy fallback)."""
        pass  # Already loaded in class definition
