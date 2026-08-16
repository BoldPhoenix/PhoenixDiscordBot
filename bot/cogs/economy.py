"""
Economy cog — Phoenix Coins balance, payday loop, and economy administration.
Balance lives on players.balance (EOS ID-based). All commands require linked ARK account.
"""

import aiosqlite
import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button, Modal, TextInput
import logging
from datetime import datetime, timedelta
from pathlib import Path

from bot.database import players_db
from bot.database import economy_db
from bot.database import server_config_db
from bot.database import games_db
from bot.utils.config import Config
from bot.utils.subscription_checker import check_feature

logger = logging.getLogger("EconomyCog")


async def _log_to_admin_channel(bot, guild_id: int, message: str):
    """Send a message to the guild's configured admin log channel."""
    try:
        config = await server_config_db.get_server_config(guild_id)
        if not config:
            logger.warning(f"No config found for guild {guild_id}")
            return
        channel_id = config.get("admin_log_channel_id")
        if not channel_id:
            logger.warning(f"admin_log_channel_id not configured for guild {guild_id}")
            return
        channel = bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(f"Admin log channel {channel_id} not found for guild {guild_id}")
            return
        await channel.send(message)
    except Exception as e:
        logger.error(f"Failed to send to admin log channel: {e}")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_currency(guild_id: int) -> tuple[str, str]:
    """Return (currency_name, currency_icon) for a guild."""
    settings = await economy_db.get_economy_settings(guild_id)
    return settings.get("currency_name", "Phoenix Coins"), settings.get("currency_icon", "🪙")


async def _require_linked(ctx_or_interaction, guild_id: int, discord_user_id: int):
    """
    Check if user has a linked account.
    Returns (balance, eos_id) or (None, None) and sends error message.
    Works with both Context and Interaction.
    """
    balance, eos_id = await players_db.get_balance_by_discord_id(
        guild_id=guild_id, discord_user_id=discord_user_id
    )
    if eos_id is None:
        msg = "You don't have a linked ARK account. Use `/player` to link your account first."
        if isinstance(ctx_or_interaction, commands.Context):
            await ctx_or_interaction.send(msg, ephemeral=True)
        else:
            await ctx_or_interaction.response.send_message(msg, ephemeral=True)
        return None, None
    return balance, eos_id


# ---------------------------------------------------------------------------
# Economy Settings Modal
# ---------------------------------------------------------------------------

class EconomySettingsModal(Modal, title="⚙️ Economy Settings"):
    payday_amount = TextInput(
        label="Base Payday Amount",
        placeholder="100",
        required=True,
        max_length=6,
    )
    currency_name = TextInput(
        label="Currency Name",
        placeholder="Phoenix Coins",
        required=True,
        max_length=30,
    )
    currency_icon = TextInput(
        label="Currency Icon (emoji)",
        placeholder="🪙",
        required=True,
        max_length=8,
    )
    payday_enabled = TextInput(
        label="Payday Enabled? (yes/no)",
        placeholder="yes",
        required=True,
        max_length=3,
    )

    def __init__(self, settings: dict):
        super().__init__()
        self.payday_amount.default = str(settings.get("base_payday_amount", 100))
        self.currency_name.default = settings.get("currency_name", "Phoenix Coins")
        self.currency_icon.default = settings.get("currency_icon", "🪙")
        self.payday_enabled.default = "yes" if settings.get("payday_enabled", 1) else "no"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.payday_amount.value)
            if amount < 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Payday amount must be a positive number.", ephemeral=True
            )
            return

        enabled = self.payday_enabled.value.strip().lower() in ("yes", "y", "true", "1")

        await economy_db.update_economy_settings(
            interaction.guild_id,
            base_payday_amount=amount,
            currency_name=self.currency_name.value.strip(),
            currency_icon=self.currency_icon.value.strip(),
            payday_enabled=1 if enabled else 0,
        )

        name, icon = self.currency_name.value.strip(), self.currency_icon.value.strip()
        embed = discord.Embed(
            title="✅ Economy Settings Updated",
            color=discord.Color.green(),
        )
        embed.add_field(name="Currency", value=f"{icon} {name}", inline=True)
        embed.add_field(name="Base Payday", value=f"{amount:,}", inline=True)
        embed.add_field(name="Payday Enabled", value="✅ Yes" if enabled else "❌ No", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Log to admin channel
        await _log_to_admin_channel(
            interaction.client, interaction.guild_id,
            f"[Economy] Updated economy settings: {icon} {name}, Base Payday: {amount:,}, Enabled: {enabled}"
        )


# ---------------------------------------------------------------------------
# Eligibility Role Selector
# ---------------------------------------------------------------------------


class EligibilityRoleSelectView(View):
    """View for selecting payday eligibility role."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        select = discord.ui.RoleSelect(placeholder="Select eligibility role...")
        select.callback = self._select_callback
        self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        select = self.children[0]
        role = select.values[0]
        if role.name == "@everyone":
            await economy_db.update_economy_settings(
                self.guild_id, payday_eligibility_role_id=None
            )
            embed = discord.Embed(
                title="✅ Eligibility Role Cleared",
                description="All linked players can receive payday.",
                color=discord.Color.green(),
            )
            await _log_to_admin_channel(
                interaction.client, self.guild_id,
                "[Economy] Eligibility role cleared - all players eligible for payday"
            )
        else:
            await economy_db.update_economy_settings(
                self.guild_id, payday_eligibility_role_id=role.id
            )
            embed = discord.Embed(
                title="✅ Eligibility Role Set",
                description=f"Only members with {role.mention} can receive payday.",
                color=discord.Color.green(),
            )
            await _log_to_admin_channel(
                interaction.client, self.guild_id,
                f"[Economy] Eligibility role set to {role.name} ({role.id})"
            )
        await interaction.response.edit_message(embed=embed, view=None)


class PaydayScheduleModal(Modal, title="📅 Payday Schedule"):
    schedule_type = TextInput(
        label="Schedule Type (daily/weekly)",
        placeholder="daily",
        required=True,
        max_length=10,
    )
    time = TextInput(
        label="Time (HH:MM UTC, 24-hour)",
        placeholder="18:00 for 12:00 PM EST",
        required=True,
        max_length=5,
    )
    day_of_week = TextInput(
        label="Day of Week (0-6, 0=Sunday)",
        placeholder="0",
        required=False,
        max_length=1,
    )
    active_only = TextInput(
        label="Active Players Only? (yes/no)",
        placeholder="no = all linked players, yes = played in last 7 days",
        required=True,
        max_length=3,
    )

    def __init__(self, settings: dict):
        super().__init__()
        self.guild_id = settings.get("guild_id")
        self.schedule_type.default = settings.get("payday_schedule_type", "daily")
        self.time.default = settings.get("payday_time", "12:00")
        self.day_of_week.default = str(settings.get("payday_day_of_week", 0))
        self.active_only.default = "yes" if settings.get("payday_active_only", 0) else "no"

    async def on_submit(self, interaction: discord.Interaction):
        schedule = self.schedule_type.value.strip().lower()
        if schedule not in ("daily", "weekly"):
            await interaction.response.send_message(
                "❌ Schedule type must be 'daily' or 'weekly'.", ephemeral=True
            )
            return

        time_str = self.time.value.strip()
        try:
            parts = time_str.split(":")
            if len(parts) != 2:
                raise ValueError
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Time must be in HH:MM format (24-hour).", ephemeral=True
            )
            return

        day = 0
        if schedule == "weekly":
            try:
                day = int(self.day_of_week.value.strip() or "0")
                if not (0 <= day <= 6):
                    raise ValueError
            except ValueError:
                await interaction.response.send_message(
                    "❌ Day of week must be 0-6 (0=Sunday).", ephemeral=True
                )
                return

        active = self.active_only.value.strip().lower() in ("yes", "y", "true", "1")

        await economy_db.update_economy_settings(
            self.guild_id,
            payday_schedule_type=schedule,
            payday_time=f"{hour:02d}:{minute:02d}",
            payday_day_of_week=day,
            payday_active_only=1 if active else 0,
        )

        days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        schedule_str = f"{hour:02d}:{minute:02d} {'every ' + days[day] if schedule == 'weekly' else 'daily'}"
        if active:
            schedule_str += " (active only)"

        embed = discord.Embed(
            title="✅ Schedule Updated",
            description=f"Payday will run **{schedule_str}**.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Log to admin channel
        active_str = " (active only)" if active else ""
        await _log_to_admin_channel(
            interaction.client, self.guild_id,
            f"[Economy] Schedule updated: {schedule} at {hour:02d}:{minute:02d}{active_str}"
        )


# ---------------------------------------------------------------------------
# Economy Admin Panel (Main GUI)
# ---------------------------------------------------------------------------

class EconomyAdminPanel(View):
    """Main economy administration panel with buttons for all settings."""

    def __init__(self, guild_id: int, settings: dict, roles: list):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self._settings = settings
        self._roles = roles

    def build_embed(self) -> discord.Embed:
        icon = self._settings.get("currency_icon", "🪙")
        name = self._settings.get("currency_name", "Phoenix Coins")
        base = self._settings.get("base_payday_amount", 100)
        enabled = self._settings.get("payday_enabled", 1)
        eligibility_role_id = self._settings.get("payday_eligibility_role_id")
        schedule_type = self._settings.get("payday_schedule_type", "daily")
        payday_time = self._settings.get("payday_time", "12:00")
        active_only = self._settings.get("payday_active_only", 0)
        day_of_week = self._settings.get("payday_day_of_week", 0)

        days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        schedule_str = f"{payday_time} {'every ' + days[day_of_week] if schedule_type == 'weekly' else 'daily'}"
        if active_only:
            schedule_str += " (active only)"

        embed = discord.Embed(
            title=f"{icon} Economy Configuration",
            description=f"Currency: **{icon} {name}**",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Base Payday", value=f"{base:,} {icon}", inline=True)
        embed.add_field(name="Payday Enabled", value="✅ Yes" if enabled else "❌ No", inline=True)
        embed.add_field(
            name="Eligibility Role",
            value=f"<@&{eligibility_role_id}>" if eligibility_role_id else "None (all players)",
            inline=True,
        )
        embed.add_field(
            name="Schedule",
            value=schedule_str,
            inline=True,
        )
        embed.add_field(
            name="Role Bonuses",
            value=f"{len(self._roles)} configured" if self._roles else "None",
            inline=True,
        )
        return embed

    @discord.ui.button(label="⚙️ Settings", style=discord.ButtonStyle.primary)
    async def settings(self, interaction: discord.Interaction, button: Button):
        settings = await economy_db.get_economy_settings(self.guild_id)
        await interaction.response.send_modal(EconomySettingsModal(settings))

    @discord.ui.button(label="🎭 Role Bonuses", style=discord.ButtonStyle.secondary)
    async def role_bonuses(self, interaction: discord.Interaction, button: Button):
        roles = await economy_db.get_economy_roles(self.guild_id)
        view = EconomyRolesView(self.guild_id, roles, interaction.guild)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    @discord.ui.button(label="🎫 Eligibility Role", style=discord.ButtonStyle.secondary)
    async def eligibility_role(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "Select the role required to receive payday (select @everyone to allow all players):",
            view=EligibilityRoleSelectView(self.guild_id),
            ephemeral=True,
        )

    @discord.ui.button(label="📅 Schedule", style=discord.ButtonStyle.secondary)
    async def schedule(self, interaction: discord.Interaction, button: Button):
        settings = await economy_db.get_economy_settings(self.guild_id)
        await interaction.response.send_modal(PaydayScheduleModal(settings))

    @discord.ui.button(label="💰 Trigger Payday", style=discord.ButtonStyle.success, row=1)
    async def trigger_payday(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        settings = await economy_db.get_economy_settings(self.guild_id)
        
        base_amount = settings.get("base_payday_amount", 100)
        currency_name = settings.get("currency_name", "Phoenix Coins")
        icon = settings.get("currency_icon", "🪙")
        eligibility_role_id = settings.get("payday_eligibility_role_id")
        active_only = settings.get("payday_active_only", 0)
        role_bonuses = await economy_db.get_economy_roles(self.guild_id)
        role_bonus_map = {int(r["role_id"]): r["bonus_amount"] for r in role_bonuses}

        linked_players = await players_db.get_linked_players_for_guild(self.guild_id)
        if not linked_players:
            await interaction.followup.send("No linked players found.", ephemeral=True)
            return

        now = datetime.utcnow()
        active_threshold = now - timedelta(days=7)
        paid_count = 0
        total_paid = 0
        skipped_no_role = 0
        skipped_inactive = 0

        for player in linked_players:
            discord_id = player.get("discord_user_id")
            eos_id = player.get("eos_id")
            if not discord_id or not eos_id:
                continue

            member = interaction.guild.get_member(discord_id)
            if member is None:
                continue

            if eligibility_role_id:
                role = interaction.guild.get_role(eligibility_role_id)
                if role and role not in member.roles:
                    skipped_no_role += 1
                    continue

            if active_only:
                last_seen_ts = player.get("last_seen_timestamp")
                if last_seen_ts:
                    last_seen = datetime.fromtimestamp(last_seen_ts)
                    if last_seen < active_threshold:
                        skipped_inactive += 1
                        continue

            role_bonus = sum(role_bonus_map.get(role.id, 0) for role in member.roles)
            total = base_amount + role_bonus

            await players_db.add_coins(
                guild_id=self.guild_id,
                eos_id=eos_id,
                amount=total,
                reason=f"Manual Payday" + (f" (+{role_bonus} role bonus)" if role_bonus else ""),
            )
            await economy_db.record_payday(
                guild_id=self.guild_id,
                discord_id=discord_id,
                eos_id=eos_id,
                base_amount=base_amount,
                role_bonus=role_bonus,
                total_amount=total,
            )
            paid_count += 1
            total_paid += total

        embed = discord.Embed(
            title=f"{icon} Payday Complete!",
            description=f"**{paid_count}** players received payday.\n**{total_paid:,}** {currency_name} distributed.",
            color=discord.Color.green(),
        )
        if skipped_no_role:
            embed.add_field(name="Skipped (no role)", value=str(skipped_no_role), inline=True)
        if skipped_inactive:
            embed.add_field(name="Skipped (inactive)", value=str(skipped_inactive), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Economy Roles View
# ---------------------------------------------------------------------------

class EconomyRolesView(View):
    """View for managing role-based payday bonuses with role selectors."""

    def __init__(self, guild_id: int, roles: list, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.roles = roles
        self.guild = guild

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎭 Role Payday Bonuses",
            description="Roles that receive bonus coins on each payday.",
            color=discord.Color.gold(),
        )
        if not self.roles:
            embed.description = "No role bonuses configured. Use **Add Role Bonus** to set one."
        else:
            lines = [f"<@&{r['role_id']}> — **+{r['bonus_amount']:,}** coins" for r in self.roles]
            embed.description = "\n".join(lines)
        return embed

    @discord.ui.button(label="➕ Add Role Bonus", style=discord.ButtonStyle.success)
    async def add_role(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(
            "Select a role to add a payday bonus:",
            view=AddRoleBonusSelect(self.guild_id, self),
            ephemeral=True,
        )

    @discord.ui.button(label="✏️ Edit Role Bonus", style=discord.ButtonStyle.primary)
    async def edit_role(self, interaction: discord.Interaction, button: Button):
        if not self.roles:
            await interaction.response.send_message("No role bonuses to edit. Use **Add Role Bonus** to create one.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Select a role to edit:",
            view=EditRoleBonusSelect(self.guild_id, self),
            ephemeral=True,
        )

    @discord.ui.button(label="🗑️ Remove Role Bonus", style=discord.ButtonStyle.danger)
    async def remove_role(self, interaction: discord.Interaction, button: Button):
        if not self.roles:
            await interaction.response.send_message("No role bonuses to remove.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Select a role to remove:",
            view=RemoveRoleBonusSelect(self.guild_id, self),
            ephemeral=True,
        )

    @discord.ui.button(label="◀ Back", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: Button):
        settings = await economy_db.get_economy_settings(self.guild_id)
        roles = await economy_db.get_economy_roles(self.guild_id)
        view = EconomyAdminPanel(self.guild_id, settings, roles)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class AddRoleBonusSelect(View):
    """View for selecting a role to add bonus."""

    def __init__(self, guild_id: int, parent: EconomyRolesView):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.parent = parent
        select = discord.ui.RoleSelect(placeholder="Select role to add bonus...")
        select.callback = self._select_callback
        self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        select = self.children[0]
        role = select.values[0]
        await interaction.response.send_modal(AddRoleBonusModal(self.guild_id, role, self.parent))


class RemoveRoleBonusSelect(View):
    """View for selecting a role to remove."""

    def __init__(self, guild_id: int, parent: EconomyRolesView):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.parent = parent
        select = discord.ui.RoleSelect(placeholder="Select role to remove...")
        select.callback = self._select_callback
        self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        select = self.children[0]
        role = select.values[0]
        await economy_db.remove_economy_role(self.guild_id, role.id)
        self.parent.roles = await economy_db.get_economy_roles(self.guild_id)
        embed = discord.Embed(
            title="✅ Role Bonus Removed",
            description=f"Removed bonus for {role.mention}.",
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=None)

        # Log to admin channel
        await _log_to_admin_channel(
            interaction.client, self.guild_id,
            f"[Economy] Removed role bonus for {role.name}"
        )


class EditRoleBonusSelect(View):
    """View for selecting a role to edit bonus."""

    def __init__(self, guild_id: int, parent: EconomyRolesView):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.parent = parent
        # Only show roles that already have bonuses
        existing_role_ids = [r["role_id"] for r in parent.roles]
        select = discord.ui.RoleSelect(
            placeholder="Select role to edit...",
            max_values=1,
        )
        # We need to filter to only show existing bonus roles
        # For now, just show all roles and validate
        select.callback = self._select_callback
        self.add_item(select)

    async def _select_callback(self, interaction: discord.Interaction):
        select = self.children[0]
        role = select.values[0]
        await interaction.response.send_modal(EditRoleBonusModal(self.guild_id, role, self.parent))


class EditRoleBonusModal(Modal, title="✏️ Edit Role Bonus"):
    bonus = TextInput(
        label="Bonus Amount (coins per payday)",
        placeholder="50",
        required=True,
        max_length=6,
    )

    def __init__(self, guild_id: int, role: discord.Role, parent: EconomyRolesView):
        super().__init__()
        self.guild_id = guild_id
        self.role = role
        self.parent = parent
        # Find existing values
        for r in parent.roles:
            if r["role_id"] == role.id:
                self.bonus.default = str(r.get("bonus_amount", 0))
                break

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bonus = int(self.bonus.value)
        except ValueError:
            await interaction.response.send_message("❌ Bonus must be a number.", ephemeral=True)
            return

        await economy_db.set_economy_role(
            self.guild_id,
            self.role.id,
            self.role.name,
            bonus,
        )

        self.parent.roles = await economy_db.get_economy_roles(self.guild_id)
        embed = discord.Embed(
            title="✅ Role Bonus Updated",
            description=f"Updated bonus for {self.role.mention}: {bonus:,} coins",
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=None)

        # Log to admin channel
        await _log_to_admin_channel(
            interaction.client, self.guild_id,
            f"[Economy] Updated role bonus for {self.role.name}: {bonus:,} coins"
        )


class AddRoleBonusModal(Modal, title="➕ Add Role Bonus"):
    bonus = TextInput(
        label="Bonus Amount (coins per payday)",
        placeholder="50",
        required=True,
        max_length=6,
    )

    def __init__(self, guild_id: int, role: discord.Role, parent: EconomyRolesView):
        super().__init__()
        self.guild_id = guild_id
        self.role = role
        self.parent = parent

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bonus = int(self.bonus.value.strip())
            if bonus <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Bonus must be a valid positive number.", ephemeral=True
            )
            return

        await economy_db.set_economy_role(self.guild_id, self.role.id, self.role.name, bonus)
        self.parent.roles = await economy_db.get_economy_roles(self.guild_id)
        
        embed = discord.Embed(
            title="✅ Role Bonus Added",
            description=f"{self.role.mention} will now receive **+{bonus:,}** bonus coins per payday.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Log to admin channel
        await _log_to_admin_channel(
            interaction.client, self.guild_id,
            f"[Economy] Added role bonus for {self.role.name}: {bonus:,} coins"
        )


# ---------------------------------------------------------------------------
# Economy Cog
# ---------------------------------------------------------------------------


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.payday_loop.start()

    def cog_unload(self):
        self.payday_loop.cancel()

    # ------------------------------------------------------------------
    # Payday Loop
    # ------------------------------------------------------------------

    @tasks.loop(hours=1.0)
    async def payday_loop(self):
        """Check each guild and run payday if the interval has elapsed."""
        for guild in self.bot.guilds:
            try:
                await self._run_payday_if_due(guild)
            except Exception as e:
                logger.error(f"Payday loop error for guild {guild.id}: {e}")

    @payday_loop.before_loop
    async def before_payday_loop(self):
        await self.bot.wait_until_ready()

    async def _run_payday_if_due(self, guild: discord.Guild):
        """Run payday for a guild if the schedule says it's time."""
        settings = await economy_db.get_economy_settings(guild.id)
        if not settings.get("payday_enabled", 1):
            return

        schedule_type = settings.get("payday_schedule_type", "daily")
        payday_time = settings.get("payday_time", "12:00")
        day_of_week = settings.get("payday_day_of_week", 0)

        now = datetime.utcnow()
        try:
            hour, minute = map(int, payday_time.split(":"))
        except ValueError:
            hour, minute = 12, 0

        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if schedule_type == "weekly":
            days_until_target = (day_of_week - now.weekday() + 1) % 7
            if days_until_target != 0 and (now - target_time).total_seconds() > 3600:
                return
        else:
            if abs((now - target_time).total_seconds()) > 3600:
                return

        async with aiosqlite.connect(Path(Config.DATABASE_PATH)) as db:
            cursor = await db.execute(
                "SELECT MAX(created_at) FROM payday_history WHERE guild_id = ?", (guild.id,)
            )
            row = await cursor.fetchone()
            last_run_str = row[0] if row else None

        if last_run_str:
            last_run = datetime.fromisoformat(last_run_str)
            if schedule_type == "daily" and (now - last_run) < timedelta(hours=23):
                return
            if schedule_type == "weekly" and (now - last_run) < timedelta(days=6):
                return

        await self._run_payday(guild, settings)

    async def _run_payday(self, guild: discord.Guild, settings: dict = None):
        """Execute payday for all linked players in a guild."""
        if settings is None:
            settings = await economy_db.get_economy_settings(guild.id)

        base_amount = settings.get("base_payday_amount", 100)
        currency_name = settings.get("currency_name", "Phoenix Coins")
        eligibility_role_id = settings.get("payday_eligibility_role_id")
        active_only = settings.get("payday_active_only", 0)
        role_bonuses = await economy_db.get_economy_roles(guild.id)
        role_bonus_map = {int(r["role_id"]): r["bonus_amount"] for r in role_bonuses}

        linked_players = await players_db.get_linked_players_for_guild(guild.id)
        if not linked_players:
            return

        now = datetime.utcnow()
        active_threshold = now - timedelta(days=7)

        paid_count = 0
        total_paid = 0
        skipped_no_role = 0
        skipped_inactive = 0

        for player in linked_players:
            discord_id = player.get("discord_user_id")
            eos_id = player.get("eos_id")
            if not discord_id or not eos_id:
                continue

            member = guild.get_member(discord_id)
            if member is None:
                continue

            if eligibility_role_id:
                role = guild.get_role(eligibility_role_id)
                if role and role not in member.roles:
                    skipped_no_role += 1
                    continue

            if active_only:
                last_seen_ts = player.get("last_seen_timestamp")
                if last_seen_ts:
                    last_seen = datetime.fromtimestamp(last_seen_ts)
                    if last_seen < active_threshold:
                        skipped_inactive += 1
                        continue

            role_bonus = sum(role_bonus_map.get(role.id, 0) for role in member.roles)
            total = base_amount + role_bonus

            await players_db.add_coins(
                guild_id=guild.id,
                eos_id=eos_id,
                amount=total,
                reason=f"Payday" + (f" (+{role_bonus} role bonus)" if role_bonus else ""),
            )
            await economy_db.record_payday(
                guild_id=guild.id,
                discord_id=discord_id,
                eos_id=eos_id,
                base_amount=base_amount,
                role_bonus=role_bonus,
                total_amount=total,
            )
            paid_count += 1
            total_paid += total

        if paid_count:
            logger.info(
                f"Payday complete for guild {guild.id}: {paid_count} players, "
                f"{total_paid:,} {currency_name} distributed"
            )

            server_config = await server_config_db.get_server_config(guild.id)
            log_channel_id = server_config.get("economy_channel_id") if server_config else None
            if log_channel_id:
                channel = guild.get_channel(log_channel_id)
                if channel:
                    icon = settings.get("currency_icon", "🪙")
                    embed = discord.Embed(
                        title=f"{icon} Payday Processed",
                        description=(
                            f"**{paid_count}** players received their payday.\n"
                            f"**{total_paid:,}** {currency_name} distributed."
                        ),
                        color=discord.Color.gold(),
                        timestamp=datetime.utcnow(),
                    )
                    embed.add_field(name="Base Amount", value=f"{base_amount:,}", inline=True)
                    if skipped_no_role:
                        embed.add_field(name="No Eligibility Role", value=str(skipped_no_role), inline=True)
                    if skipped_inactive:
                        embed.add_field(name="Inactive", value=str(skipped_inactive), inline=True)
                    await channel.send(embed=embed)

    # ------------------------------------------------------------------
    # Economy log helper
    # ------------------------------------------------------------------

    async def _log_economy_event(self, guild: discord.Guild, embed: discord.Embed):
        """Post an event embed to the configured economy log channel."""
        try:
            server_config = await server_config_db.get_server_config(guild.id)
            log_channel_id = server_config.get("economy_channel_id") if server_config else None
            if not log_channel_id:
                return
            channel = guild.get_channel(int(log_channel_id))
            if channel:
                await channel.send(embed=embed)
        except Exception as e:
            logger.warning(f"Failed to post economy log: {e}")

    # ------------------------------------------------------------------
    # User Commands
    # ------------------------------------------------------------------

    @commands.hybrid_command(name="balance", description="Check your Phoenix Coin balance.")
    async def balance(self, ctx: commands.Context):
        """Check your current Phoenix Coin balance."""
        await ctx.defer(ephemeral=True)
        balance, eos_id = await _require_linked(ctx, ctx.guild.id, ctx.author.id)
        if eos_id is None:
            return

        name, icon = await _get_currency(ctx.guild.id)
        embed = discord.Embed(
            description=f"{icon} **{balance:,}** {name}",
            color=discord.Color.gold(),
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="history", description="View your recent transaction history.")
    async def history(self, ctx: commands.Context):
        """View the last 10 transactions."""
        await ctx.defer(ephemeral=True)
        balance, eos_id = await _require_linked(ctx, ctx.guild.id, ctx.author.id)
        if eos_id is None:
            return

        history = await players_db.get_coin_history(guild_id=ctx.guild.id, eos_id=eos_id, limit=10)
        name, icon = await _get_currency(ctx.guild.id)

        if not history:
            await ctx.send("No transaction history found.", ephemeral=True)
            return

        embed = discord.Embed(title=f"{icon} Transaction History", color=discord.Color.blue())
        lines = []
        for tx in history:
            symbol = "+" if tx["transaction_type"] == "credit" else "-"
            amount = abs(tx["amount"])
            created = (tx.get("created_at") or "")[:10]
            lines.append(f"`{symbol}{amount:,}` {tx.get('reason', 'Unknown')} ({created})")

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Current balance: {balance:,} {name}")
        await ctx.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # Admin Commands
    # ------------------------------------------------------------------

    @commands.hybrid_command(name="addcoins", description="Admin: Add coins to a user.")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(user="The user to receive coins", amount="Amount to add", reason="Reason for the grant")
    async def add_coins(self, ctx: commands.Context, user: discord.Member, amount: int, reason: str = "Admin Grant"):
        await ctx.defer(ephemeral=True)
        if amount <= 0:
            await ctx.send("Amount must be positive.", ephemeral=True)
            return

        player = await players_db.get_player_by_discord_id(ctx.guild.id, user.id)
        if not player:
            await ctx.send(f"{user.mention} doesn't have a linked ARK account.", ephemeral=True)
            return

        name, icon = await _get_currency(ctx.guild.id)
        new_balance = await players_db.add_coins(
            guild_id=ctx.guild.id, eos_id=player["eos_id"],
            amount=amount, reason=reason, admin_id=ctx.author.id,
        )
        embed = discord.Embed(
            description=f"Added **{amount:,}** {icon} to {user.mention}.\nNew Balance: **{new_balance:,}**\nReason: *{reason}*",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed, ephemeral=True)
        log_embed = discord.Embed(
            title=f"➕ {icon} Coins Added",
            description=f"**{ctx.author.mention}** added **{amount:,}** {icon} to {user.mention}\nReason: *{reason}*\nNew balance: **{new_balance:,}**",
            color=discord.Color.green(),
            timestamp=datetime.utcnow(),
        )
        await self._log_economy_event(ctx.guild, log_embed)

    @commands.hybrid_command(name="removecoins", description="Admin: Remove coins from a user.")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(user="The user to deduct coins from", amount="Amount to remove", reason="Reason")
    async def remove_coins(self, ctx: commands.Context, user: discord.Member, amount: int, reason: str = "Admin Penalty"):
        await ctx.defer(ephemeral=True)
        if amount <= 0:
            await ctx.send("Amount must be positive.", ephemeral=True)
            return

        player = await players_db.get_player_by_discord_id(ctx.guild.id, user.id)
        if not player:
            await ctx.send(f"{user.mention} doesn't have a linked ARK account.", ephemeral=True)
            return

        name, icon = await _get_currency(ctx.guild.id)
        success = await players_db.deduct_coins(
            guild_id=ctx.guild.id, eos_id=player["eos_id"], amount=amount, reason=reason
        )
        if success:
            new_balance = await players_db.get_balance(ctx.guild.id, player["eos_id"])
            embed = discord.Embed(
                description=f"Removed **{amount:,}** {icon} from {user.mention}.\nNew Balance: **{new_balance:,}**\nReason: *{reason}*",
                color=discord.Color.red(),
            )
            await ctx.send(embed=embed, ephemeral=True)
            log_embed = discord.Embed(
                title=f"➖ {icon} Coins Removed",
                description=f"**{ctx.author.mention}** removed **{amount:,}** {icon} from {user.mention}\nReason: *{reason}*\nNew balance: **{new_balance:,}**",
                color=discord.Color.red(),
                timestamp=datetime.utcnow(),
            )
            await self._log_economy_event(ctx.guild, log_embed)
        else:
            await ctx.send(f"{user.mention} does not have enough coins.", ephemeral=True)

    @app_commands.command(name="economycfg", description="Admin: Open economy configuration panel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def economy_cfg(self, interaction: discord.Interaction):
        """Open the economy admin panel."""
        if not await check_feature(interaction, "economy"):
            return
        settings = await economy_db.get_economy_settings(interaction.guild_id)
        roles = await economy_db.get_economy_roles(interaction.guild_id)
        view = EconomyAdminPanel(interaction.guild_id, settings, roles)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    @app_commands.command(name="leaderboard", description="View the top players by game wins.")
    async def leaderboard(self, interaction: discord.Interaction):
        """Show the games leaderboard: wins, losses, win rate, and biggest win per game."""
        await interaction.response.defer(ephemeral=True)
        if not await check_feature(interaction, "games"):
            return

        settings = await economy_db.get_economy_settings(interaction.guild_id)
        icon = settings.get("currency_icon", "🪙")

        GAMES = ["Dino Jack", "ARK Dice", "Alpha Hunt", "Artifact Vault", "Ark Slots", "Crafting Race"]
        MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

        embed = discord.Embed(
            title="🏆 Games Leaderboard",
            description="Top players ranked by wins for each game.",
            color=discord.Color.gold(),
        )

        any_data = False
        for game_name in GAMES:
            rows = await games_db.get_game_leaderboard(interaction.guild_id, game_name, limit=5)
            if not rows:
                continue
            any_data = True
            lines = []
            for rank, row in enumerate(rows, 1):
                uid = row.get("user_id")
                wins = row.get("games_won", 0)
                played = row.get("games_played", 0)
                losses = played - wins
                win_pct = f"{wins / played * 100:.0f}%" if played > 0 else "0%"
                biggest = row.get("biggest_win", 0)
                member = interaction.guild.get_member(uid)
                name = member.display_name if member else f"<@{uid}>"
                medal = MEDALS.get(rank, f"#{rank}")
                lines.append(
                    f"{medal} **{name}** — {wins}W/{losses}L ({win_pct}) | Best: {icon}{biggest:,}"
                )
            embed.add_field(name=f"🎮 {game_name}", value="\n".join(lines), inline=False)

        if not any_data:
            embed.description = "No game stats yet — play some games first!"

        embed.set_footer(text="All-time stats · Use /games to play")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Economy(bot))
