"""
Subscription management cog.

Provides /subscription, /subscribe, and /subadmin commands.
Background tasks handle grace-period downgrades and warning messages.
"""

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.database import subscription_db, server_config_db
from bot.utils.config import Config
from bot.utils.stripe_poller import run_full_poll

logger = logging.getLogger("SubscriptionCog")

# Tier display labels
_TIER_LABELS = {
    "free": "Free",
    "premium": "Premium",
    "lifetime": "Lifetime",
}

_STATUS_LABELS = {
    "trial": "Trial",
    "active": "Active",
    "grace": "Grace Period",
    "expired": "Expired",
}

_TIER_FEATURES = {
    "free": [
        "✅ Up to 2 ARK servers",
        "✅ Server management (start/stop/restart)",
        "✅ Mod management & INI editing",
        "✅ Maintenance (backups & updates)",
        "✅ Chat relay (Discord ↔ ARK)",
        "✅ Remote agent (1 agent max)",
        "✅ Basic RCON commands",
        "✅ Server monitoring & voice channels",
    ],
    "premium": [
        "✅ Up to 10 ARK servers",
        "✅ Unlimited remote agents",
        "✅ Kits (requires player linking)",
        "✅ Economy & player linking",
        "✅ Shop & Games",
        "✅ Player management & Analytics",
        "✅ Ask PhoenixAI (20 queries/day)",
        "✅ Loot crate configuration",
        "✅ Advanced RCON & log viewer",
    ],
    "lifetime": [
        "✅ Up to 10 ARK servers",
        "✅ Unlimited remote agents",
        "✅ Kits, Economy, Shop & Games",
        "✅ Player management & Analytics",
        "✅ Ask PhoenixAI (20 queries/day)",
        "✅ Loot crate configuration",
        "✅ Advanced RCON & log viewer",
        "✅ One-time payment — no recurring fees",
    ],
}


def _is_owner(interaction: discord.Interaction) -> bool:
    """Return True if the interaction user is the bot owner."""
    return interaction.user.id == Config.BOT_OWNER_DISCORD_ID


def _build_subscription_embed(sub: dict) -> discord.Embed:
    """Build the /subscription status embed."""
    effective = subscription_db.get_effective_tier(sub)
    tier_label = _TIER_LABELS.get(effective, effective.title())
    status = sub.get("status", "trial")
    status_label = _STATUS_LABELS.get(status, status.title())

    # Determine colour
    colours = {"free": discord.Color.blue(), "premium": discord.Color.gold(), "lifetime": discord.Color.purple()}
    colour = colours.get(effective, discord.Color.blue())

    embed = discord.Embed(
        title="📋 Subscription Status",
        color=colour,
    )
    embed.add_field(name="Tier", value=f"**{tier_label}**", inline=True)
    embed.add_field(name="Status", value=f"**{status_label}**", inline=True)

    # Countdown / expiry info
    now = datetime.now(timezone.utc)
    if status == "grace":
        grace_end_str = sub.get("grace_end")
        if grace_end_str:
            try:
                grace_end = datetime.fromisoformat(grace_end_str).replace(tzinfo=timezone.utc)
                remaining = grace_end - now
                days = max(0, remaining.days)
                embed.add_field(
                    name="⚠️ Grace Period",
                    value=f"Premium features active for {days} more day(s). Renew to avoid downgrade.",
                    inline=False,
                )
            except ValueError:
                pass
    elif status == "active":
        sub_end_str = sub.get("subscription_end")
        if sub_end_str:
            try:
                sub_end = datetime.fromisoformat(sub_end_str).replace(tzinfo=timezone.utc)
                remaining = sub_end - now
                days = max(0, remaining.days)
                embed.add_field(name="Renews In", value=f"{days} day(s)", inline=False)
            except ValueError:
                pass

    # Included features
    features = _TIER_FEATURES.get(effective, _TIER_FEATURES["free"])
    embed.add_field(name="Included Features", value="\n".join(features[:6]), inline=False)

    if effective == "free":
        embed.set_footer(text="Use /subscribe to unlock Premium (monthly) or Lifetime (one-time) features.")
    elif effective == "premium":
        embed.set_footer(text="Enjoying Phoenix ARK Bot? Consider Lifetime — same features, no recurring fees.")

    return embed


class SubscriptionCog(commands.Cog, name="Subscription"):
    """Subscription management for the Phoenix ARK Bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.subscription_checker_task.start()
        self.warning_sender_task.start()
        self.stripe_poller_task.start()

    def cog_unload(self):
        self.subscription_checker_task.cancel()
        self.warning_sender_task.cancel()
        self.stripe_poller_task.cancel()

    async def is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions."""
        if not interaction.guild:
            return False
        if interaction.user.guild_permissions.administrator:
            return True
        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_role_id"):
            admin_role = interaction.guild.get_role(config["admin_role_id"])
            if admin_role and admin_role in interaction.user.roles:
                return True
        return False

    # ------------------------------------------------------------------
    # on_guild_join — auto-enroll in trial + notify owner
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Start a 30-day trial when the bot joins a new guild and notify bot owner."""
        try:
            sub = await subscription_db.get_or_create_subscription(guild.id)
            logger.info(f"Guild {guild.id} joined — trial created (status={sub.get('status')})")
            
            await self._notify_owner_of_new_guild(guild, sub)
            
            await self._send_remote_agent_info_to_guild_admin(guild)
            
        except Exception as e:
            logger.error(f"on_guild_join subscription error for guild {guild.id}: {e}")

    async def _notify_owner_of_new_guild(self, guild: discord.Guild, sub: dict):
        """Send DM to bot owner about new guild join."""
        if not Config.BOT_OWNER_DISCORD_ID:
            logger.warning("No BOT_OWNER_DISCORD_ID configured — skipping owner notification")
            return
        
        owner_user = self.bot.get_user(Config.BOT_OWNER_DISCORD_ID)
        if not owner_user:
            logger.warning(f"Could not find bot owner user with ID {Config.BOT_OWNER_DISCORD_ID}")
            return
        
        owner_name = "Unknown"
        if guild.owner:
            owner_name = f"{guild.owner.display_name} ({guild.owner.name})"
        
        embed = discord.Embed(
            title="🆕 New Guild Joined",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Guild", value=f"{guild.name} (`{guild.id}`)", inline=True)
        embed.add_field(name="Owner", value=owner_name, inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Subscription", value=f"{sub.get('tier', 'free').title()} ({sub.get('status', 'trial')})", inline=True)
        
        try:
            await owner_user.send(embed=embed)
            logger.info(f"Sent new guild notification to owner for guild {guild.id}")
        except discord.Forbidden:
            logger.warning(f"Could not DM bot owner (forbidden)")
        except Exception as e:
            logger.error(f"Failed to DM bot owner: {e}")

    async def _send_remote_agent_info_to_guild_admin(self, guild: discord.Guild):
        """Send remote agent installation info to guild owner/admin."""
        if not guild.owner:
            logger.warning(f"Guild {guild.id} has no owner — skipping agent info DM")
            return
        
        embed = discord.Embed(
            title="🤖 Phoenix ARK Bot — Remote Agent Setup",
            description="To enable advanced features (start/stop, mod management, backups, updates), install the remote agent on your ARK server machine.",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="📥 Download",
            value="[GitHub Releases](https://github.com/BoldPhoenix/PhoenixArkAgent/releases)\n*Download the latest `PhoenixArkAgent.exe`*",
            inline=False,
        )
        embed.add_field(
            name="📋 Quick Install",
            value=(
                "1. Download `PhoenixArkAgent.exe`\n"
                "2. Run as Administrator: `PhoenixArkAgent.exe -install`\n"
                "3. Start service: `net start PhoenixArkAgent`\n"
                "4. Note the **Auth Key** from the console output\n"
                "5. Use `/register_agent` in Discord with your IP and auth key"
            ),
            inline=False,
        )
        embed.add_field(
            name="📖 Full Guide",
            value="See the README on GitHub for detailed setup instructions.",
            inline=False,
        )
        embed.set_footer(text="Phoenix ARK Bot — Welcome!")
        
        try:
            await guild.owner.send(embed=embed)
            logger.info(f"Sent remote agent info to guild owner for guild {guild.id}")
        except discord.Forbidden:
            logger.warning(f"Could not DM guild owner for guild {guild.id} (DMs disabled)")
        except Exception as e:
            logger.error(f"Failed to send agent info to guild owner: {e}")

    # ------------------------------------------------------------------
    # on_guild_remove — soft delete guild data
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Mark guild as inactive (soft delete) when bot is removed."""
        try:
            success = await server_config_db.mark_guild_inactive(guild.id)
            if success:
                logger.info(f"Guild {guild.id} ({guild.name}) removed — marked inactive (data preserved)")
            else:
                logger.warning(f"Failed to mark guild {guild.id} as inactive")
        except Exception as e:
            logger.error(f"on_guild_remove error for guild {guild.id}: {e}")

    # ------------------------------------------------------------------
    # Background: downgrade expired grace subscriptions
    # ------------------------------------------------------------------

    @tasks.loop(hours=6)
    async def subscription_checker_task(self):
        """Downgrade guilds whose grace period has ended to free/expired."""
        try:
            grace_subs = await subscription_db.get_grace_period_subscriptions()
            now = datetime.now(timezone.utc)
            for sub in grace_subs:
                grace_end_str = sub.get("grace_end")
                if not grace_end_str:
                    continue
                try:
                    grace_end = datetime.fromisoformat(grace_end_str)
                except ValueError:
                    continue
                if now >= grace_end:
                    guild_id = sub["guild_id"]
                    await subscription_db.set_tier(guild_id, "free", "expired")
                    logger.info(f"Guild {guild_id} grace period ended — downgraded to free/expired")
                    # Notify guild admins about disabled servers
                    all_servers = await server_config_db.get_all_ark_servers_including_disabled(guild_id)
                    disabled_names = [s["name"] for s in all_servers if s.get("disabled_reason") == "tier_limit"]
                    if disabled_names:
                        await subscription_db.notify_tier_change_downgrade(guild_id, disabled_names, self.bot)
        except Exception as e:
            logger.error(f"subscription_checker_task error: {e}")

    @subscription_checker_task.before_loop
    async def before_subscription_checker(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Background: send warnings for grace / expiring trials
    # ------------------------------------------------------------------

    @tasks.loop(hours=12)
    async def warning_sender_task(self):
        """Send warnings to guild owners / admin log channels."""
        try:
            await self._send_grace_warnings()
            await self._send_trial_expiry_warnings()
        except Exception as e:
            logger.error(f"warning_sender_task error: {e}")

    @warning_sender_task.before_loop
    async def before_warning_sender(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Background: Stripe polling — detects new payments + cancellations
    # ------------------------------------------------------------------

    @tasks.loop(minutes=30)
    async def stripe_poller_task(self):
        """Poll Stripe for new checkout completions and subscription changes."""
        key = getattr(Config, "STRIPE_SECRET_KEY", "")
        if not key:
            return  # Stripe not configured — skip silently
        try:
            result = await run_full_poll()
            if result["upgraded"] or result["grace_started"]:
                logger.info(
                    f"Stripe poll: {result['upgraded']} upgraded, "
                    f"{result['grace_started']} grace periods started"
                )
        except Exception as e:
            logger.error(f"stripe_poller_task error: {e}")

    @stripe_poller_task.before_loop
    async def before_stripe_poller(self):
        await self.bot.wait_until_ready()

    async def _send_warning(self, guild_id: int, message: str):
        """Send a warning to the guild's admin log channel."""
        try:
            config = await server_config_db.get_server_config(guild_id)
            if not config:
                return
            channel_id = config.get("admin_log_channel_id")
            if not channel_id:
                return
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await channel.send(message)
        except Exception as e:
            logger.warning(f"Failed to send warning to guild {guild_id}: {e}")

    async def _send_grace_warnings(self):
        grace_subs = await subscription_db.get_grace_period_subscriptions()
        for sub in grace_subs:
            guild_id = sub["guild_id"]
            grace_end_str = sub.get("grace_end")
            msg = (
                "⚠️ **Subscription Warning** — Your Premium subscription has lapsed. "
                f"You have a grace period until `{grace_end_str}`. "
                "After that, the server will be downgraded to **Free tier**. "
                "Use `/subscribe` to renew."
            )
            await self._send_warning(guild_id, msg)

    async def _send_trial_expiry_warnings(self):
        expiring = await subscription_db.get_expiring_trials(days_ahead=3)
        for sub in expiring:
            guild_id = sub["guild_id"]
            trial_end_str = sub.get("trial_end")
            msg = (
                "⏳ **Trial Ending Soon** — Your free trial expires on "
                f"`{trial_end_str}`. After that, you'll be on the **Free tier** "
                "with limited features. Use `/subscribe` to upgrade to Premium or Lifetime."
            )
            await self._send_warning(guild_id, msg)

    # ------------------------------------------------------------------
    # /subscription — user command
    # ------------------------------------------------------------------

    @app_commands.command(name="subscription", description="[ADMIN] View your server's subscription tier and status")
    @app_commands.default_permissions(administrator=True)
    async def subscription(self, interaction: discord.Interaction):
        if not await self.is_admin(interaction):
            await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        if not guild_id:
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return

        try:
            sub = await subscription_db.get_or_create_subscription(guild_id)
            embed = _build_subscription_embed(sub)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"/subscription error for guild {guild_id}: {e}")
            await interaction.followup.send("An error occurred retrieving your subscription.", ephemeral=True)

    # ------------------------------------------------------------------
    # /subscribe — payment links
    # ------------------------------------------------------------------

    @app_commands.command(name="subscribe", description="[ADMIN] Upgrade your server's subscription to Premium or Lifetime")
    @app_commands.default_permissions(administrator=True)
    async def subscribe(self, interaction: discord.Interaction):
        if not await self.is_admin(interaction):
            await interaction.response.send_message("❌ You need admin permissions to use this command.", ephemeral=True)
            return
        premium_link = getattr(Config, "STRIPE_PREMIUM_LINK", "")
        lifetime_link = getattr(Config, "STRIPE_LIFETIME_LINK", "")

        embed = discord.Embed(
            title="⭐ Upgrade Your Subscription",
            description=(
                "Unlock the full power of Phoenix ARK Bot!\n\n"
                "**Premium** — $9.99/mo\n"
                "Economy, Shop, Games, Mod Management, INI editing, Loot crates, Remote Agent, and more.\n\n"
                "**Lifetime** — $199 once\n"
                "Identical to Premium — every feature, forever. No recurring fees.\n\n"
                "After purchasing, your bot will be upgraded automatically within 24 hours."
            ),
            color=discord.Color.gold(),
        )

        # Append guild_id as client_reference_id so Stripe polling can identify the guild
        guild_id = interaction.guild_id
        ref_param = f"?client_reference_id={guild_id}" if guild_id else ""

        view = discord.ui.View(timeout=None)
        if premium_link:
            view.add_item(discord.ui.Button(
                label="Premium Monthly →",
                url=f"{premium_link}{ref_param}",
                style=discord.ButtonStyle.link,
                emoji="⭐",
            ))
        if lifetime_link:
            view.add_item(discord.ui.Button(
                label="Lifetime →",
                url=f"{lifetime_link}{ref_param}",
                style=discord.ButtonStyle.link,
                emoji="🏆",
            ))

        if not premium_link and not lifetime_link:
            embed.add_field(
                name="Contact",
                value="Payment links not yet configured. Contact the bot owner to upgrade.",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ------------------------------------------------------------------
    # /subadmin — owner-only admin group
    # ------------------------------------------------------------------

    subadmin_group = app_commands.Group(name="subadmin", description="[Owner] Subscription administration")

    @subadmin_group.command(name="status", description="[Owner] View full subscription record for a guild")
    @app_commands.describe(guild_id="The guild ID to look up")
    async def subadmin_status(self, interaction: discord.Interaction, guild_id: str):
        if not _is_owner(interaction):
            await interaction.response.send_message("❌ Owner-only command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.followup.send("❌ Invalid guild ID.", ephemeral=True)
            return

        sub = await subscription_db.get_subscription(gid)
        if not sub:
            await interaction.followup.send(f"No subscription record found for guild `{guild_id}`.", ephemeral=True)
            return

        effective = subscription_db.get_effective_tier(sub)
        embed = discord.Embed(title=f"Subscription — Guild {guild_id}", color=discord.Color.blue())
        embed.add_field(name="Tier", value=sub["tier"], inline=True)
        embed.add_field(name="Status", value=sub["status"], inline=True)
        embed.add_field(name="Effective", value=effective, inline=True)
        embed.add_field(name="Trial Start", value=sub.get("trial_start") or "—", inline=True)
        embed.add_field(name="Trial End", value=sub.get("trial_end") or "—", inline=True)
        embed.add_field(name="Sub Start", value=sub.get("subscription_start") or "—", inline=True)
        embed.add_field(name="Sub End", value=sub.get("subscription_end") or "—", inline=True)
        embed.add_field(name="Grace End", value=sub.get("grace_end") or "—", inline=True)
        embed.add_field(name="Stripe Customer", value=sub.get("stripe_customer_id") or "—", inline=True)
        embed.add_field(name="Stripe Sub ID", value=sub.get("stripe_subscription_id") or "—", inline=True)
        embed.add_field(name="Notes", value=sub.get("notes") or "—", inline=False)
        embed.add_field(name="Created", value=sub.get("created_at") or "—", inline=True)
        embed.add_field(name="Updated", value=sub.get("updated_at") or "—", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @subadmin_group.command(name="set_tier", description="[Owner] Set tier and status for a guild")
    @app_commands.describe(guild_id="Guild ID", tier="free/premium/lifetime", status="trial/active/grace/expired")
    async def subadmin_set_tier(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        tier: str,
        status: str,
    ):
        if not _is_owner(interaction):
            await interaction.response.send_message("❌ Owner-only command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        if tier not in ("free", "premium", "lifetime"):
            await interaction.followup.send("❌ Tier must be: free, premium, or lifetime.", ephemeral=True)
            return
        if status not in ("trial", "active", "grace", "expired"):
            await interaction.followup.send("❌ Status must be: trial, active, grace, or expired.", ephemeral=True)
            return

        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.followup.send("❌ Invalid guild ID.", ephemeral=True)
            return

        # Ensure record exists; capture old tier for downgrade notification
        old_sub = await subscription_db.get_or_create_subscription(gid)
        old_tier = subscription_db.get_effective_tier(old_sub)

        result = await subscription_db.set_tier(gid, tier, status)
        if result:
            # If downgraded to free, notify guild admins about disabled servers
            if tier == "free" and old_tier != "free":
                all_servers = await server_config_db.get_all_ark_servers_including_disabled(gid)
                disabled_names = [s["name"] for s in all_servers if s.get("disabled_reason") == "tier_limit"]
                if disabled_names:
                    await subscription_db.notify_tier_change_downgrade(gid, disabled_names, self.bot)
            await interaction.followup.send(
                f"✅ Guild `{guild_id}` set to **{tier}/{status}**.", ephemeral=True
            )
        else:
            await interaction.followup.send("❌ Failed to update subscription.", ephemeral=True)

    @subadmin_group.command(name="grant_lifetime", description="[Owner] Grant lifetime tier to a guild")
    @app_commands.describe(guild_id="Guild ID", note="Optional note (e.g. Volunteer tester)")
    async def subadmin_grant_lifetime(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        note: str = "",
    ):
        if not _is_owner(interaction):
            await interaction.response.send_message("❌ Owner-only command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.followup.send("❌ Invalid guild ID.", ephemeral=True)
            return

        await subscription_db.get_or_create_subscription(gid)
        kwargs = {}
        if note:
            kwargs["notes"] = note
        result = await subscription_db.set_tier(gid, "lifetime", "active", **kwargs)
        if result:
            await interaction.followup.send(
                f"✅ Guild `{guild_id}` granted **Lifetime** tier.{' Note: ' + note if note else ''}",
                ephemeral=True,
            )
        else:
            await interaction.followup.send("❌ Failed to update subscription.", ephemeral=True)

    @subadmin_group.command(name="extend_trial", description="[Owner] Extend trial period for a guild")
    @app_commands.describe(guild_id="Guild ID", days="Number of days to extend")
    async def subadmin_extend_trial(
        self,
        interaction: discord.Interaction,
        guild_id: str,
        days: int,
    ):
        if not _is_owner(interaction):
            await interaction.response.send_message("❌ Owner-only command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.followup.send("❌ Invalid guild ID.", ephemeral=True)
            return

        sub = await subscription_db.get_or_create_subscription(gid)
        # Extend from current trial_end (or now if missing)
        trial_end_str = sub.get("trial_end")
        try:
            base = datetime.fromisoformat(trial_end_str) if trial_end_str else datetime.now(timezone.utc)
        except ValueError:
            base = datetime.now(timezone.utc)
        new_end = base + timedelta(days=days)
        result = await subscription_db.set_tier(
            gid, sub.get("tier", "free"), sub.get("status", "trial"),
            trial_end=new_end.isoformat(),
        )
        if result:
            await interaction.followup.send(
                f"✅ Guild `{guild_id}` trial extended by {days} day(s). New end: `{new_end.date()}`.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send("❌ Failed to extend trial.", ephemeral=True)

    @subadmin_group.command(name="list", description="[Owner] List all guild subscriptions")
    @app_commands.describe(page="Page number (5 per page)")
    async def subadmin_list(self, interaction: discord.Interaction, page: int = 1):
        if not _is_owner(interaction):
            await interaction.response.send_message("❌ Owner-only command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        all_subs = await subscription_db.get_all_subscriptions()
        per_page = 5
        total = len(all_subs)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        page_subs = all_subs[start: start + per_page]

        embed = discord.Embed(
            title=f"Subscriptions — Page {page}/{total_pages} ({total} total)",
            color=discord.Color.blue(),
        )

        tier_icons = {"free": "🔵", "premium": "⭐", "lifetime": "🏆"}
        status_icons = {"trial": "⏳", "active": "✅", "grace": "⚠️", "expired": "❌"}

        for sub in page_subs:
            guild_id = sub["guild_id"]
            effective = subscription_db.get_effective_tier(sub)
            status = sub.get("status", "trial")

            # Try to get guild name + owner from Discord
            guild = self.bot.get_guild(guild_id)
            if guild:
                guild_name = guild.name
                owner = guild.owner
                owner_str = f"{owner.display_name} ({owner.name})" if owner else "Unknown"
            else:
                guild_name = "*(bot not in guild)*"
                owner_str = "—"

            email = sub.get("customer_email") or "—"
            notes = sub.get("notes") or ""

            tier_icon = tier_icons.get(effective, "❓")
            status_icon = status_icons.get(status, "❓")

            value_lines = [
                f"**Guild:** {guild_name}",
                f"**Owner:** {owner_str}",
                f"**Tier:** {tier_icon} {effective.title()} | **Status:** {status_icon} {status.title()}",
                f"**Email:** {email}",
            ]
            if notes:
                value_lines.append(f"**Notes:** {notes}")

            embed.add_field(
                name=f"`{guild_id}`",
                value="\n".join(value_lines),
                inline=False,
            )

        if not page_subs:
            embed.description = "No subscriptions found."

        await interaction.followup.send(embed=embed, ephemeral=True)

    @subadmin_group.command(name="dashboard", description="[Owner] View aggregate subscription statistics")
    async def subadmin_dashboard(self, interaction: discord.Interaction):
        """Show comprehensive subscription dashboard with aggregate stats."""
        if not _is_owner(interaction):
            await interaction.response.send_message("❌ Owner-only command.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        all_subs = await subscription_db.get_all_subscriptions()
        guild_stats = await server_config_db.get_guild_stats()
        
        tier_counts = {"free": 0, "premium": 0, "lifetime": 0}
        status_counts = {"trial": 0, "active": 0, "grace": 0, "expired": 0}
        total_revenue = 0
        premium_active = 0
        
        for sub in all_subs:
            effective_tier = subscription_db.get_effective_tier(sub)
            tier_counts[effective_tier] = tier_counts.get(effective_tier, 0) + 1
            status = sub.get("status", "trial")
            status_counts[status] = status_counts.get(status, 0) + 1
            
            if effective_tier == "premium" and status == "active":
                premium_active += 1
                total_revenue += 9.99
        
        embed = discord.Embed(
            title="📊 Subscription Dashboard",
            color=discord.Color.purple(),
            timestamp=datetime.now(timezone.utc),
        )
        
        embed.add_field(
            name="🏛️ Guild Overview",
            value=(
                f"**Total Guilds:** {guild_stats.get('total_guilds', 0)}\n"
                f"**Active:** {guild_stats.get('active_guilds', 0)} | "
                f"**Inactive:** {guild_stats.get('inactive_guilds', 0)}"
            ),
            inline=False,
        )
        
        tier_lines = [
            f"🔵 **Free:** {tier_counts.get('free', 0)}",
            f"⭐ **Premium:** {tier_counts.get('premium', 0)}",
            f"🏆 **Lifetime:** {tier_counts.get('lifetime', 0)}",
        ]
        embed.add_field(name="📊 Tier Distribution", value="\n".join(tier_lines), inline=True)
        
        status_lines = [
            f"⏳ **Trial:** {status_counts.get('trial', 0)}",
            f"✅ **Active:** {status_counts.get('active', 0)}",
            f"⚠️ **Grace:** {status_counts.get('grace', 0)}",
            f"❌ **Expired:** {status_counts.get('expired', 0)}",
        ]
        embed.add_field(name="📈 Status Distribution", value="\n".join(status_lines), inline=True)
        
        embed.add_field(
            name="💰 Revenue (Monthly Recurring)",
            value=f"**${total_revenue:.2f}**/mo\n*({premium_active} premium @ $9.99/mo)*",
            inline=False,
        )
        
        trial_count = status_counts.get("trial", 0)
        active_paying = tier_counts.get("premium", 0) + tier_counts.get("lifetime", 0)
        conversion_rate = (active_paying / (active_paying + trial_count) * 100) if (active_paying + trial_count) > 0 else 0
        embed.add_field(
            name="📈 Trial Conversion",
            value=f"**{conversion_rate:.1f}%**\n*({active_paying} paying / {active_paying + trial_count} total non-free)*",
            inline=True,
        )
        
        embed.set_footer(text="Use /subadmin list for per-guild details")

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SubscriptionCog(bot))
