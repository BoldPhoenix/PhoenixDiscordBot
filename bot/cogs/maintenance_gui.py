"""
Maintenance Configuration GUI Cog.
Provides GUI for backup schedules, maintenance settings, and job management.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput

from bot.database import maintenance_db, server_config_db
from bot.rcon.simple_client import SimpleRCONClient
from bot.utils.subscription_checker import check_feature

ASA_APP_ID = 2430930

logger = logging.getLogger("MaintenanceGUI")


async def _log_to_channel(bot, guild_id: int, message: str):
    """Send a message to the guild's configured server log channel."""
    try:
        config = await server_config_db.get_server_config(guild_id)
        if not config:
            return
        channel_id = config.get("server_log_channel_id")
        if not channel_id:
            return
        channel = bot.get_channel(int(channel_id))
        if not channel:
            return
        await channel.send(message)
    except Exception as e:
        logger.error(f"Failed to send to log channel: {e}")


def _extract_server_name(backup_path: str) -> str:
    """Extract server name from a backup filename.

    Backup files follow the pattern:
        {ServerName}_backup_{YYYYMMDD}_{HHMMSS}_{type}.zip
    Returns empty string if the format is unrecognised.
    """
    filename = backup_path.replace("\\", "/").split("/")[-1]
    parts = filename.split("_backup_")
    return parts[0] if len(parts) > 1 else ""


class MaintenanceSettingsModal(Modal, title="⚙️ Maintenance Settings"):
    """Modal for configuring maintenance settings."""

    backup_enabled = TextInput(
        label="Enable Backups? (yes/no)",
        placeholder="yes",
        required=True,
        max_length=3,
    )
    backup_type = TextInput(
        label="Backup Type (essentials/full)",
        placeholder="essentials",
        required=True,
        max_length=10,
    )
    backup_schedule = TextInput(
        label="Schedule (e.g., daily@02:00 or weekly@03:00)",
        placeholder="daily@02:00",
        required=True,
        max_length=20,
    )
    retention_days = TextInput(
        label="Retention Days",
        placeholder="30",
        required=True,
        max_length=3,
    )
    backup_root = TextInput(
        label="Backup Root Path (optional)",
        placeholder="D:\\ARK\\Backups",
        required=False,
        max_length=200,
    )

    def __init__(self, settings: dict):
        super().__init__()
        self.guild_id = settings.get("guild_id")
        self.backup_enabled.default = "yes" if settings.get("backup_enabled") else "no"
        self.backup_type.default = settings.get("backup_type", "essentials")
        schedule = settings.get("backup_schedule_type", "daily")
        time = settings.get("backup_time", "02:00")
        self.backup_schedule.default = f"{schedule}@{time}"
        self.retention_days.default = str(settings.get("backup_retention_days", 30))
        self.backup_root.default = settings.get("backup_root_path") or ""

    async def on_submit(self, interaction: discord.Interaction):
        enabled = self.backup_enabled.value.strip().lower() in ("yes", "y", "true", "1")
        
        backup_type = self.backup_type.value.strip().lower()
        if backup_type not in ("essentials", "full"):
            await interaction.response.send_message("❌ Backup type must be 'essentials' or 'full'.", ephemeral=True)
            return
        
        schedule_str = self.backup_schedule.value.strip().lower()
        try:
            if "@" in schedule_str:
                schedule, time_str = schedule_str.split("@")
            else:
                schedule = schedule_str
                time_str = "02:00"
            schedule = schedule.strip()
            if schedule not in ("daily", "weekly"):
                raise ValueError("Invalid schedule")
            parts = time_str.strip().split(":")
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time")
        except:
            await interaction.response.send_message("❌ Schedule must be 'daily@HH:MM' or 'weekly@HH:MM' format.", ephemeral=True)
            return

        try:
            retention = int(self.retention_days.value.strip())
        except:
            await interaction.response.send_message("❌ Retention must be a number.", ephemeral=True)
            return

        await maintenance_db.update_maintenance_config(
            self.guild_id,
            backup_enabled=1 if enabled else 0,
            backup_type=backup_type,
            backup_schedule_type=schedule,
            backup_time=f"{hour:02d}:{minute:02d}",
            backup_retention_days=retention,
            backup_root_path=self.backup_root.value.strip() or None,
        )

        embed = discord.Embed(
            title="✅ Maintenance Settings Updated",
            color=discord.Color.green(),
        )
        embed.add_field(name="Backups", value="Enabled ✅" if enabled else "Disabled ❌", inline=True)
        embed.add_field(name="Backup Type", value=backup_type, inline=True)
        embed.add_field(name="Schedule", value=f"{schedule} @ {hour:02d}:{minute:02d} UTC", inline=True)
        embed.add_field(name="Retention", value=f"{retention} days", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Log to server channel
        await _log_to_channel(
            interaction.client, self.guild_id,
            f"[Maintenance] Settings updated: Backups {'enabled' if enabled else 'disabled'}, {schedule} at {hour:02d}:{minute:02d} UTC"
        )


class UpdateSettingsModal(Modal, title="🔄 Update Settings"):
    """Modal for configuring update settings."""

    update_enabled = TextInput(
        label="Enable Auto-Updates? (yes/no)",
        placeholder="no",
        required=True,
        max_length=3,
    )
    update_schedule = TextInput(
        label="Schedule (daily/weekly)",
        placeholder="weekly",
        required=True,
        max_length=10,
    )
    update_time = TextInput(
        label="Update Time (HH:MM UTC)",
        placeholder="03:00",
        required=True,
        max_length=5,
    )
    pre_update_backup = TextInput(
        label="Backup Before Update? (yes/no)",
        placeholder="yes",
        required=True,
        max_length=3,
    )
    saveworld = TextInput(
        label="SaveWorld Before? (yes/no)",
        placeholder="yes",
        required=True,
        max_length=3,
    )

    def __init__(self, settings: dict):
        super().__init__()
        self.guild_id = settings.get("guild_id")
        self.update_enabled.default = "yes" if settings.get("update_enabled") else "no"
        self.update_schedule.default = settings.get("update_schedule_type", "weekly")
        self.update_time.default = settings.get("update_time", "03:00")
        self.pre_update_backup.default = "yes" if settings.get("enable_pre_update_backup") else "no"
        self.saveworld.default = "yes" if settings.get("enable_saveworld") else "no"

    async def on_submit(self, interaction: discord.Interaction):
        enabled = self.update_enabled.value.strip().lower() in ("yes", "y", "true", "1")
        schedule = self.update_schedule.value.strip().lower()
        if schedule not in ("daily", "weekly"):
            await interaction.response.send_message("❌ Schedule must be 'daily' or 'weekly'.", ephemeral=True)
            return

        time_str = self.update_time.value.strip()
        try:
            parts = time_str.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except:
            await interaction.response.send_message("❌ Time must be HH:MM format.", ephemeral=True)
            return

        pre_backup = self.pre_update_backup.value.strip().lower() in ("yes", "y", "true", "1")
        saveworld = self.saveworld.value.strip().lower() in ("yes", "y", "true", "1")

        await maintenance_db.update_maintenance_config(
            self.guild_id,
            update_enabled=1 if enabled else 0,
            update_schedule_type=schedule,
            update_time=f"{hour:02d}:{minute:02d}",
            enable_pre_update_backup=1 if pre_backup else 0,
            enable_saveworld=1 if saveworld else 0,
        )

        embed = discord.Embed(
            title="✅ Update Settings Updated",
            color=discord.Color.green(),
        )
        embed.add_field(name="Auto-Update", value="Enabled ✅" if enabled else "Disabled ❌", inline=True)
        embed.add_field(name="Schedule", value=schedule, inline=True)
        embed.add_field(name="Time (UTC)", value=f"{hour:02d}:{minute:02d}", inline=True)
        embed.add_field(name="Pre-Update Backup", value="Yes ✅" if pre_backup else "No ❌", inline=True)
        embed.add_field(name="SaveWorld", value="Yes ✅" if saveworld else "No ❌", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

        await _log_to_channel(
            interaction.client, self.guild_id,
            f"[Maintenance] Update settings updated: {'Enabled' if enabled else 'Disabled'}, {schedule} at {hour:02d}:{minute:02d} UTC"
        )


class MaintenanceMainView(View):
    """Main maintenance configuration panel."""

    def __init__(self, cog, guild_id: int, settings: dict):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.settings = settings

    def build_embed(self, schedule_count: int = 0) -> discord.Embed:
        embed = discord.Embed(
            title="🔧 Maintenance Configuration",
            description="Configure automated backups and updates for your ARK servers",
            color=discord.Color.blue(),
        )

        # Backup schedules summary
        embed.add_field(
            name="💾 Backups",
            value=f"{schedule_count} schedule{'s' if schedule_count != 1 else ''} active" if schedule_count else "No schedules configured",
            inline=True,
        )

        # Update settings
        update_enabled = self.settings.get("update_enabled", 0)
        embed.add_field(
            name="🔄 Auto-Updates",
            value="Enabled ✅" if update_enabled else "Disabled ❌",
            inline=True,
        )
        if update_enabled:
            schedule = self.settings.get("update_schedule_type", "weekly")
            time = self.settings.get("update_time", "03:00")
            embed.add_field(name="Schedule", value=f"{schedule} @ {time} UTC", inline=True)

        return embed

    @discord.ui.button(label="📅 Backup Schedules", style=discord.ButtonStyle.primary)
    async def backup_schedules(self, interaction: discord.Interaction, button: Button):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        schedules = await maintenance_db.get_backup_schedules(self.guild_id)
        view = BackupSchedulesView(self.cog, self.guild_id, schedules)
        await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)

    @discord.ui.button(label="🔄 Update Settings", style=discord.ButtonStyle.primary)
    async def update_settings(self, interaction: discord.Interaction, button: Button):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        # Re-fetch from DB so the modal always shows the latest saved values
        fresh_settings = await maintenance_db.get_maintenance_config(self.guild_id) or {}
        fresh_settings.setdefault("guild_id", self.guild_id)
        await interaction.response.send_modal(UpdateSettingsModal(fresh_settings))

    @discord.ui.button(label="📋 Backup History", style=discord.ButtonStyle.secondary)
    async def backup_history(self, interaction: discord.Interaction, button: Button):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        history = await maintenance_db.get_backup_history(self.guild_id, limit=10)
        if not history:
            await interaction.followup.send("No backup history found.", ephemeral=True)
            return

        embed = discord.Embed(title="💾 Backup History", color=discord.Color.blue())
        lines = []
        for h in history:
            status = "✅" if h.get("status") == "success" else "❌"
            date = (h.get("created_at") or "")[:16]
            server = h.get("server_name", "Unknown")
            btype = h.get("backup_type", "essentials")
            lines.append(f"{status} {date} - {server} ({btype})")

        embed.description = "\n".join(lines) or "No backups"
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🚀 Backup Now", style=discord.ButtonStyle.success)
    async def backup_now(self, interaction: discord.Interaction, button: Button):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        
        # Show server selection for backup
        await interaction.response.defer(ephemeral=True)
        
        servers = await server_config_db.get_ark_servers(self.guild_id)
        if not servers:
            await interaction.followup.send("No servers configured.", ephemeral=True)
            return
        
        # Create select menu for servers — prepend "All Servers" option
        options = [
            discord.SelectOption(
                label="All Servers",
                value="__ALL__",
                description="Back up every configured server",
            )
        ]
        for s in servers:
            options.append(discord.SelectOption(
                label=s.get("name", "Unknown"),
                value=s.get("name", "")
            ))

        view = ImmediateBackupView(self.cog, self.guild_id, options)
        await interaction.followup.send("Select a server to backup:", view=view, ephemeral=True)

    @discord.ui.button(label="♻️ Restore Backup", style=discord.ButtonStyle.danger)
    async def restore_backup(self, interaction: discord.Interaction, button: Button):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        
        # Show backup history for restore
        await interaction.response.defer(ephemeral=True)
        
        history = await maintenance_db.get_backup_history(self.guild_id, limit=20)
        if not history:
            await interaction.followup.send("No backups available to restore.", ephemeral=True)
            return
        
        # Create options for restore
        options = []
        for h in history:
            if h.get("status") != "success":
                continue
            date = (h.get("created_at") or "")[:16]
            server = h.get("server_name", "Unknown")
            btype = h.get("backup_type", "essentials")
            path = h.get("backup_path", "")
            options.append(discord.SelectOption(
                label=f"{server} - {date} ({btype})",
                value=path
            ))
        
        if not options:
            await interaction.followup.send("No successful backups available.", ephemeral=True)
            return
        
        view = RestoreBackupView(self.cog, self.guild_id, options)
        await interaction.followup.send("Select a backup to restore:", view=view, ephemeral=True)

    @discord.ui.button(label="📜 Job History", style=discord.ButtonStyle.secondary)
    async def job_history(self, interaction: discord.Interaction, button: Button):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        jobs = await maintenance_db.get_maintenance_jobs(self.guild_id, limit=10)
        if not jobs:
            await interaction.followup.send("No maintenance jobs found.", ephemeral=True)
            return

        embed = discord.Embed(title="📜 Maintenance Job History", color=discord.Color.blue())
        lines = []
        for j in jobs:
            status = "✅" if j.get("status") == "completed" else "❌" if j.get("status") == "failed" else "⏳"
            date = (j.get("created_at") or "")[:16]
            job_type = j.get("job_type", "unknown")
            server = j.get("server_name", "Unknown")
            lines.append(f"{status} {date} - {job_type} ({server})")

        embed.description = "\n".join(lines) or "No jobs"
        await interaction.followup.send(embed=embed, ephemeral=True)


class BackupSchedulesView(View):
    """View listing all backup schedules for a guild with Add/Edit/Delete actions."""

    def __init__(self, cog, guild_id: int, schedules: list):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.schedules = schedules
        self._build_select()

    def _build_select(self):
        """Add or refresh the schedule select menu."""
        # Remove any existing select
        for item in list(self.children):
            if isinstance(item, discord.ui.Select):
                self.remove_item(item)

        if not self.schedules:
            return

        options = []
        for s in self.schedules[:25]:  # Discord limit
            status = "✅" if s.get("enabled") else "❌"
            label = f"{status} {s['name']}"[:100]
            desc = f"{s['backup_type']} — {s['schedule_type']} @ {s['backup_time']} UTC"
            options.append(discord.SelectOption(label=label, value=str(s["id"]), description=desc[:100]))

        select = discord.ui.Select(placeholder="Select a schedule to edit or delete", options=options)
        select.callback = self.on_select
        self.add_item(select)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="📅 Backup Schedules",
            description="Manage automated backup schedules. Each schedule applies to all servers.",
            color=discord.Color.blue(),
        )
        if not self.schedules:
            embed.description = "No backup schedules configured. Click **➕ Add Schedule** to create one."
            return embed

        for s in self.schedules:
            status = "✅ Enabled" if s.get("enabled") else "❌ Disabled"
            sched = f"{s['schedule_type']} @ {s['backup_time']} UTC"
            if s["schedule_type"] == "weekly":
                days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                sched += f" ({days[s.get('day_of_week', 0)]})"
            target = s.get("target_directory")
            target_line = f"\n📁 `{target}`" if target else ""
            embed.add_field(
                name=s["name"],
                value=f"Type: {s['backup_type']}\nSchedule: {sched}\nStatus: {status}{target_line}",
                inline=True,
            )
        return embed

    def _selected_id(self) -> Optional[int]:
        """Return the schedule id currently selected in the dropdown, or None."""
        for item in self.children:
            if isinstance(item, discord.ui.Select) and item.values:
                try:
                    return int(item.values[0])
                except (ValueError, IndexError):
                    pass
        return None

    async def on_select(self, interaction: discord.Interaction):
        # Just acknowledge so the selection is registered; buttons will act on it
        await interaction.response.defer()

    @discord.ui.button(label="➕ Add Schedule", style=discord.ButtonStyle.success, row=1)
    async def add_schedule(self, interaction: discord.Interaction, button: Button):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        await interaction.response.send_modal(AddScheduleModal(self.cog, self.guild_id))

    @discord.ui.button(label="✏️ Edit", style=discord.ButtonStyle.primary, row=1)
    async def edit_schedule(self, interaction: discord.Interaction, button: Button):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        schedule_id = self._selected_id()
        if not schedule_id:
            await interaction.response.send_message("Select a schedule first.", ephemeral=True)
            return
        # Always re-fetch from DB so the modal shows the latest saved values
        # (avoids stale in-memory schedules missing recently-set target_directory)
        fresh_schedules = await maintenance_db.get_backup_schedules(self.guild_id)
        self.schedules = fresh_schedules  # keep in-memory state current too
        schedule = next((s for s in fresh_schedules if s["id"] == schedule_id), None)
        if not schedule:
            await interaction.response.send_message("Schedule not found.", ephemeral=True)
            return
        await interaction.response.send_modal(AddScheduleModal(self.cog, self.guild_id, schedule=schedule))

    @discord.ui.button(label="🗑️ Delete", style=discord.ButtonStyle.danger, row=1)
    async def delete_schedule(self, interaction: discord.Interaction, button: Button):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        schedule_id = self._selected_id()
        if not schedule_id:
            await interaction.response.send_message("Select a schedule first.", ephemeral=True)
            return
        await maintenance_db.delete_backup_schedule(schedule_id, self.guild_id)
        self.schedules = await maintenance_db.get_backup_schedules(self.guild_id)
        self._build_select()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        self.schedules = await maintenance_db.get_backup_schedules(self.guild_id)
        self._build_select()
        await interaction.edit_original_response(embed=self.build_embed(), view=self)


class AddScheduleModal(Modal, title="📅 Backup Schedule"):
    """Modal for creating or editing a backup schedule."""

    sched_name = TextInput(
        label="Schedule Name",
        placeholder="Daily Essentials",
        required=True,
        max_length=50,
    )
    backup_type = TextInput(
        label="Backup Type (essentials / full)",
        placeholder="essentials",
        default="essentials",
        required=True,
        max_length=10,
    )
    schedule = TextInput(
        label="Schedule (daily@HH:MM or weekly@Mon@HH:MM)",
        placeholder="daily@02:00",
        required=True,
        max_length=30,
    )
    enabled = TextInput(
        label="Enabled? (yes / no)",
        placeholder="yes",
        default="yes",
        required=True,
        max_length=3,
    )
    target_directory = TextInput(
        label="Backup Target Directory (optional)",
        placeholder="e.g. D:\\ARK\\Backups  (empty = <ServerInstallPath>\\Backups)",
        required=False,
        max_length=200,
    )

    def __init__(self, cog, guild_id: int, schedule: Optional[dict] = None):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.editing_id: Optional[int] = None

        if schedule:
            self.editing_id = schedule["id"]
            self.sched_name.default = schedule.get("name", "")
            self.backup_type.default = schedule.get("backup_type", "essentials")
            stype = schedule.get("schedule_type", "daily")
            btime = schedule.get("backup_time", "02:00")
            if stype == "weekly":
                days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                day = days[schedule.get("day_of_week", 0)]
                self.schedule.default = f"weekly@{day}@{btime}"
            else:
                self.schedule.default = f"daily@{btime}"
            self.enabled.default = "yes" if schedule.get("enabled", 1) else "no"
            self.target_directory.default = schedule.get("target_directory") or ""

    async def on_submit(self, interaction: discord.Interaction):
        # Validate backup_type
        btype = self.backup_type.value.strip().lower()
        if btype not in ("essentials", "full"):
            await interaction.response.send_message("❌ Backup type must be 'essentials' or 'full'.", ephemeral=True)
            return

        # Parse schedule string
        parts = [p.strip() for p in self.schedule.value.strip().lower().split("@")]
        schedule_type = parts[0] if parts else "daily"
        if schedule_type not in ("daily", "weekly"):
            await interaction.response.send_message("❌ Schedule must start with 'daily' or 'weekly'.", ephemeral=True)
            return

        day_of_week = 0
        try:
            if schedule_type == "weekly":
                if len(parts) < 3:
                    raise ValueError("weekly requires day and time")
                day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                day_of_week = day_names.index(parts[1])
                time_str = parts[2]
            else:
                time_str = parts[1] if len(parts) > 1 else "02:00"
            h, m = int(time_str.split(":")[0]), int(time_str.split(":")[1])
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError("Invalid time")
        except (ValueError, IndexError):
            await interaction.response.send_message(
                "❌ Invalid format. Use `daily@HH:MM` or `weekly@Mon@HH:MM`.", ephemeral=True
            )
            return

        backup_time = f"{h:02d}:{m:02d}"
        is_enabled = 1 if self.enabled.value.strip().lower() in ("yes", "y", "true", "1") else 0
        name = self.sched_name.value.strip()
        target_dir = (self.target_directory.value or "").strip() or None

        if self.editing_id:
            await maintenance_db.update_backup_schedule(
                self.editing_id,
                name=name,
                backup_type=btype,
                schedule_type=schedule_type,
                backup_time=backup_time,
                day_of_week=day_of_week,
                enabled=is_enabled,
                target_directory=target_dir,
            )
            msg = f"✅ Schedule **{name}** updated."
        else:
            new_id = await maintenance_db.add_backup_schedule(
                guild_id=self.guild_id,
                name=name,
                backup_type=btype,
                schedule_type=schedule_type,
                backup_time=backup_time,
                day_of_week=day_of_week,
                enabled=is_enabled,
                target_directory=target_dir,
            )
            msg = f"✅ Schedule **{name}** created (id={new_id})."

        await interaction.response.send_message(msg, ephemeral=True)


class ImmediateBackupView(View):
    """View for immediate backup selection."""

    def __init__(self, cog, guild_id: int, server_options: list):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id

        select = discord.ui.Select(
            placeholder="Select a server to backup",
            options=server_options,
        )
        select.callback = self.select_server
        self.add_item(select)

    async def select_server(self, interaction: discord.Interaction):
        server_name = interaction.data["values"][0]
        # Show modal for backup options
        await interaction.response.send_modal(ImmediateBackupModal(self.cog, self.guild_id, server_name))


class ImmediateBackupModal(Modal, title="🚀 Immediate Backup"):
    """Modal for immediate backup options."""

    backup_type = TextInput(
        label="Backup Type (essentials/full)",
        placeholder="essentials",
        default="essentials",
        required=True,
        max_length=10,
    )
    target_path = TextInput(
        label="Backup Save Path (optional)",
        placeholder="e.g. D:\\ARK\\Backups  (empty = <ServerInstallPath>\\Backups)",
        required=False,
        max_length=200,
    )

    def __init__(self, cog, guild_id: int, server_name: str):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.server_name = server_name

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Check for agent
        if not hasattr(self.cog.bot, 'agent_manager') or not self.cog.bot.agent_manager:
            await interaction.followup.send("❌ Agent not connected.", ephemeral=True)
            return

        # Use the manager's helper — handles int/str guild_id type mismatch safely
        agent_id = await self.cog.bot.agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            await interaction.followup.send(
                "❌ No connected agent found for this server. Check that the agent is online.", ephemeral=True
            )
            return

        # Get backup options
        backup_type = self.backup_type.value.strip().lower()
        if backup_type not in ("essentials", "full"):
            await interaction.followup.send("❌ Backup type must be 'essentials' or 'full'.", ephemeral=True)
            return

        essentials_only = (backup_type == "essentials")
        target_path = self.target_path.value.strip()

        # Build params - send backup path to agent if user specified one
        params: Dict = {"essentials_only": essentials_only}
        if target_path:
            params["backup_path"] = target_path

        # Run backup as background task to avoid blocking the bot
        asyncio.create_task(self._run_backup_task(interaction, agent_id, backup_type, params))
        
        # Acknowledge immediately
        await interaction.followup.send(
            f"🚀 Backup started in background for **{self.server_name}**.\n\nThe bot will remain responsive to other commands.",
            ephemeral=True
        )

    async def _run_backup_task(self, interaction: discord.Interaction, agent_id: str, backup_type: str, params: Dict):
        """Run the actual backup process as a background task."""
        # --- All Servers branch ---
        if self.server_name == "__ALL__":
            servers = await server_config_db.get_ark_servers(self.guild_id)
            if not servers:
                await interaction.followup.send("❌ No servers configured.", ephemeral=True)
                return

            await interaction.edit_original_response(
                content=f"🚀 Starting **{backup_type}** backup for **all {len(servers)} servers**..."
            )

            results_summary = []
            for server in servers:
                sname = server.get("name", "")
                if not sname:
                    continue
                try:
                    result = await self.cog.bot.agent_manager.send_command(
                        agent_id, "backup_server", sname, params=params, timeout=300
                    )
                    if result.get("data"):
                        data = result["data"]
                        backup_file = data.get("backup_file", "")
                        size_mb = data.get("size_mb", "0")
                        btype = data.get("backup_type", backup_type)
                        file_count = data.get("file_count", 0)
                        size_bytes = 0
                        try:
                            size_bytes = int(float(size_mb) * 1024 * 1024)
                        except Exception:
                            pass
                        await maintenance_db.add_backup_history(
                            guild_id=self.guild_id,
                            server_name=sname,
                            backup_path=backup_file,
                            backup_size_bytes=size_bytes,
                            status="success",
                            backup_type=btype,
                        )
                        results_summary.append(f"✅ **{sname}** — {size_mb} MB, {file_count} files")
                        await _log_to_channel(
                            interaction.client, self.guild_id,
                            f"💾 Manual backup completed for **{sname}**\n📁 `{backup_file}`\n💾 {size_mb} MB ({btype})"
                        )
                    else:
                        results_summary.append(f"❌ **{sname}** — no data returned")
                except Exception as e:
                    await maintenance_db.add_backup_history(
                        guild_id=self.guild_id, server_name=sname, backup_path="",
                        backup_size_bytes=0, status="failed", error_message=str(e)
                    )
                    results_summary.append(f"❌ **{sname}** — {e}")

            embed = discord.Embed(
                title="💾 All-Server Backup Complete",
                description="\n".join(results_summary) or "No servers backed up.",
                color=discord.Color.green(),
            )
            embed.add_field(name="Type", value=backup_type, inline=True)
            await interaction.edit_original_response(content=None, embed=embed, view=None)
            return

        # --- Single server branch ---
        try:
            # Show "Starting" in the deferred slot first so it appears ABOVE the result
            await interaction.edit_original_response(
                content=f"🚀 Starting **{backup_type}** backup for **{self.server_name}**..."
            )

            result = await self.cog.bot.agent_manager.send_command(
                agent_id,
                "backup_server",
                self.server_name,
                params=params,
                timeout=300  # 5 minutes
            )

            if result.get("data"):
                data = result["data"]
                backup_file = data.get("backup_file", "")
                size_mb = data.get("size_mb", "0")
                btype = data.get("backup_type", backup_type)
                file_count = data.get("file_count", 0)

                # Record in history
                size_bytes = 0
                try:
                    size_bytes = int(float(size_mb) * 1024 * 1024)
                except Exception:
                    pass

                await maintenance_db.add_backup_history(
                    guild_id=self.guild_id,
                    server_name=self.server_name,
                    backup_path=backup_file,
                    backup_size_bytes=size_bytes,
                    status="success",
                    backup_type=btype
                )

                embed = discord.Embed(
                    title="✅ Backup Complete",
                    description=f"Server **{self.server_name}** backed up successfully",
                    color=discord.Color.green()
                )
                embed.add_field(name="📁 Location", value=f"`{backup_file}`", inline=False)
                embed.add_field(name="💾 Size", value=f"{size_mb} MB", inline=True)
                embed.add_field(name="📂 Files", value=str(file_count), inline=True)
                embed.add_field(name="🔒 Type", value=btype, inline=True)
                await interaction.edit_original_response(content=None, embed=embed, view=None)

                # Log completion to server log channel
                await _log_to_channel(
                    interaction.client, self.guild_id,
                    f"💾 Manual backup completed for **{self.server_name}**\n"
                    f"📁 `{backup_file}`\n"
                    f"💾 Size: {size_mb} MB ({btype})"
                )
            else:
                await interaction.edit_original_response(content="❌ Backup failed — no data returned", view=None)

        except Exception as e:
            await maintenance_db.add_backup_history(
                guild_id=self.guild_id,
                server_name=self.server_name,
                backup_path="",
                backup_size_bytes=0,
                status="failed",
                error_message=str(e)
            )
            await interaction.edit_original_response(content=f"❌ Backup failed: {e}", view=None)


class RestoreBackupView(View):
    """View for restore backup selection."""

    def __init__(self, cog, guild_id: int, backup_options: list):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id

        select = discord.ui.Select(
            placeholder="Select a backup to restore",
            options=backup_options,
        )
        select.callback = self.select_backup
        self.add_item(select)

    async def select_backup(self, interaction: discord.Interaction):
        backup_path = interaction.data["values"][0]
        await interaction.response.defer(ephemeral=True)

        # Verify the backup file still exists before offering restore
        if hasattr(self.cog.bot, "agent_manager") and self.cog.bot.agent_manager:
            agent_id = await self.cog.bot.agent_manager.get_connected_agent_for_guild(self.guild_id)
            if agent_id:
                try:
                    result = await self.cog.bot.agent_manager.send_command(
                        agent_id,
                        "verify_backup",
                        "",
                        params={"backup_path": backup_path},
                        timeout=30,
                    )
                    data = result.get("data", {})
                    if not data.get("exists", True):
                        await interaction.followup.send(
                            f"❌ Backup file no longer found at:\n`{backup_path}`\n\nIt may have been deleted or moved.",
                            ephemeral=True,
                        )
                        return
                except Exception as e:
                    logger.warning(f"verify_backup failed (proceeding anyway): {e}")

        # Show confirmation
        confirm_view = RestoreConfirmView(self.cog, self.guild_id, backup_path)
        await interaction.followup.send(
            f"⚠️ Restore from `{backup_path}`?\n\nThis will overwrite current server data!",
            view=confirm_view,
            ephemeral=True,
        )


class RestoreConfirmView(View):
    """Confirmation for restore operation."""

    def __init__(self, cog, guild_id: int, backup_path: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id
        self.backup_path = backup_path

    @discord.ui.button(label="✅ Confirm Restore", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        view = RestoreTargetView(self.cog, self.guild_id, self.backup_path)
        await interaction.followup.send(
            content=(
                f"♻️ Choose restore target for:\n`{self.backup_path}`\n\n"
                f"**📦 Staging** — restore to an alternate directory (server can stay running)\n"
                f"**⚠️ Production** — restore to the live `Saved/` directory (server must be stopped)"
            ),
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Restore cancelled.", ephemeral=True)


class RestoreModal(Modal, title="♻️ Restore Backup"):
    """Modal for specifying restore target path."""

    target_path = TextInput(
        label="Target Directory (leave empty for Saved)",
        placeholder="D:\\ARK\\Servers\\Aberration\\ShooterGame\\Saved",
        required=False,
        max_length=200,
    )

    def __init__(self, cog, guild_id: int, backup_path: str):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.backup_path = backup_path

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Check for agent
        if not hasattr(self.cog.bot, 'agent_manager') or not self.cog.bot.agent_manager:
            await interaction.followup.send("❌ Agent not connected.", ephemeral=True)
            return

        # Use the manager's helper — handles int/str guild_id type mismatch safely
        agent_id = await self.cog.bot.agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            await interaction.followup.send(
                "❌ No connected agent found for this server. Check that the agent is online.", ephemeral=True
            )
            return

        target = self.target_path.value.strip()

        try:
            # Show "Starting" in the deferred slot first so it appears ABOVE the result
            await interaction.edit_original_response(content="♻️ Starting restore from backup...")

            result = await self.cog.bot.agent_manager.send_command(
                agent_id,
                "restore_server",
                "",  # server name not needed — extracted from backup filename
                params={
                    "backup_path": self.backup_path,
                    "target_path": target
                },
                timeout=300  # 5 minutes for large restores
            )

            if result.get("data"):
                data = result["data"]
                server_name = data.get("server_name", "Unknown")
                files_restored = data.get("files_restored", 0)

                embed = discord.Embed(
                    title="✅ Restore Complete",
                    description=f"Restored from `{self.backup_path}`",
                    color=discord.Color.green()
                )
                embed.add_field(name="Server", value=server_name, inline=True)
                embed.add_field(name="Files Restored", value=str(files_restored), inline=True)
                if target:
                    embed.add_field(name="Target", value=f"`{target}`", inline=False)
                else:
                    embed.add_field(name="Target", value="Saved directory (default)", inline=False)
                await interaction.edit_original_response(content=None, embed=embed, view=None)
            else:
                await interaction.edit_original_response(content="❌ Restore failed — no data returned", view=None)

        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Restore failed: {e}", view=None)


class RestoreTargetView(View):
    """Choose between staging or production restore target."""

    def __init__(self, cog, guild_id: int, backup_path: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id
        self.backup_path = backup_path

    @discord.ui.button(label="📦 Staging Directory", style=discord.ButtonStyle.primary)
    async def staging(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(
            RestoreStagingModal(self.cog, self.guild_id, self.backup_path)
        )

    @discord.ui.button(label="⚠️ Production Directory", style=discord.ButtonStyle.danger)
    async def production(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)

        if not hasattr(self.cog.bot, "agent_manager") or not self.cog.bot.agent_manager:
            await interaction.followup.send("❌ Agent not connected.", ephemeral=True)
            return

        agent_id = await self.cog.bot.agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            await interaction.followup.send(
                "❌ No connected agent found. Check that the agent is online.", ephemeral=True
            )
            return

        server_name = _extract_server_name(self.backup_path)

        try:
            result = await self.cog.bot.agent_manager.send_command(
                agent_id, "get_status", server_name
            )
            online = result.get("data", {}).get("online", False)
        except Exception as e:
            await interaction.followup.send(f"❌ Could not check server status: {e}", ephemeral=True)
            return

        if online:
            view = ProductionRestoreWarningView(
                self.cog, self.guild_id, agent_id, server_name, self.backup_path
            )
            await interaction.followup.send(
                content=(
                    f"⚠️ **Server is currently Running!**\n\n"
                    f"You must stop the server before restoring to the production `Saved/` directory. "
                    f"Click **Stop & Restore** to stop the server and then restore, or **Cancel** to abort."
                ),
                view=view,
                ephemeral=True,
            )
        else:
            view = ProductionRestoreReadyView(
                self.cog, self.guild_id, agent_id, server_name, self.backup_path
            )
            await interaction.followup.send(
                content=(
                    f"✅ **Server is stopped** — safe to restore.\n\n"
                    f"Click **Restore to Production** to overwrite the live `Saved/` directory, "
                    f"or **Cancel** to abort."
                ),
                view=view,
                ephemeral=True,
            )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Restore cancelled.", view=None)


class RestoreStagingModal(Modal, title="📦 Restore to Staging"):
    """Restore a backup to a custom staging directory."""

    staging_path = TextInput(
        label="Staging Directory Path",
        placeholder="D:\\Staging\\ServerName\\ShooterGame\\Saved",
        required=True,
        max_length=200,
    )

    def __init__(self, cog, guild_id: int, backup_path: str):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.backup_path = backup_path

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not hasattr(self.cog.bot, "agent_manager") or not self.cog.bot.agent_manager:
            await interaction.followup.send("❌ Agent not connected.", ephemeral=True)
            return

        agent_id = await self.cog.bot.agent_manager.get_connected_agent_for_guild(self.guild_id)
        if not agent_id:
            await interaction.followup.send(
                "❌ No connected agent found. Check that the agent is online.", ephemeral=True
            )
            return

        target = self.staging_path.value.strip()

        try:
            await interaction.edit_original_response(
                content=f"📦 Restoring to staging directory `{target}`..."
            )

            result = await self.cog.bot.agent_manager.send_command(
                agent_id,
                "restore_server",
                "",
                params={"backup_path": self.backup_path, "target_path": target},
                timeout=300,
            )

            if result.get("data"):
                data = result["data"]
                server_name = data.get("server_name", "Unknown")
                files_restored = data.get("files_restored", 0)

                embed = discord.Embed(
                    title="✅ Staging Restore Complete",
                    description=f"Restored from `{self.backup_path}`",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Server", value=server_name, inline=True)
                embed.add_field(name="Files Restored", value=str(files_restored), inline=True)
                embed.add_field(name="📦 Staging Target", value=f"`{target}`", inline=False)
                await interaction.edit_original_response(content=None, embed=embed, view=None)
            else:
                await interaction.edit_original_response(
                    content="❌ Restore failed — no data returned", view=None
                )

        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Restore failed: {e}", view=None)


class ProductionRestoreWarningView(View):
    """Confirm stop-and-restore when server is currently running."""

    def __init__(self, cog, guild_id: int, agent_id: str, server_name: str, backup_path: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.agent_id = agent_id
        self.server_name = server_name
        self.backup_path = backup_path

    @discord.ui.button(label="🛑 Stop & Restore", style=discord.ButtonStyle.danger)
    async def stop_and_restore(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.edit_original_response(
                content=f"🛑 Stopping server **{self.server_name}**..."
            )
            await self.cog.bot.agent_manager.send_command(
                self.agent_id, "stop_server", self.server_name, timeout=90
            )
        except Exception as e:
            await interaction.edit_original_response(
                content=f"❌ Failed to stop server: {e}", view=None
            )
            return

        try:
            await interaction.edit_original_response(
                content=f"♻️ Restoring **{self.server_name}** from backup..."
            )
            result = await self.cog.bot.agent_manager.send_command(
                self.agent_id,
                "restore_server",
                "",
                params={"backup_path": self.backup_path, "target_path": ""},
                timeout=300,
            )

            if result.get("data"):
                data = result["data"]
                server_name = data.get("server_name", self.server_name)
                files_restored = data.get("files_restored", 0)

                embed = discord.Embed(
                    title="✅ Production Restore Complete",
                    description=f"Restored from `{self.backup_path}`",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Server", value=server_name, inline=True)
                embed.add_field(name="Files Restored", value=str(files_restored), inline=True)
                embed.add_field(
                    name="Target", value="Production `Saved/` directory", inline=False
                )
                await interaction.edit_original_response(content=None, embed=embed, view=None)
            else:
                await interaction.edit_original_response(
                    content="❌ Restore failed — no data returned", view=None
                )

        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Restore failed: {e}", view=None)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Restore cancelled.", view=None)


class ProductionRestoreReadyView(View):
    """Confirm restore when server is already stopped."""

    def __init__(self, cog, guild_id: int, agent_id: str, server_name: str, backup_path: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.agent_id = agent_id
        self.server_name = server_name
        self.backup_path = backup_path

    @discord.ui.button(label="✅ Restore to Production", style=discord.ButtonStyle.danger)
    async def restore(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)

        try:
            await interaction.edit_original_response(
                content=f"♻️ Restoring **{self.server_name}** to production `Saved/`..."
            )
            result = await self.cog.bot.agent_manager.send_command(
                self.agent_id,
                "restore_server",
                "",
                params={"backup_path": self.backup_path, "target_path": ""},
                timeout=300,
            )

            if result.get("data"):
                data = result["data"]
                server_name = data.get("server_name", self.server_name)
                files_restored = data.get("files_restored", 0)

                embed = discord.Embed(
                    title="✅ Production Restore Complete",
                    description=f"Restored from `{self.backup_path}`",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Server", value=server_name, inline=True)
                embed.add_field(name="Files Restored", value=str(files_restored), inline=True)
                embed.add_field(
                    name="Target", value="Production `Saved/` directory", inline=False
                )
                await interaction.edit_original_response(content=None, embed=embed, view=None)
            else:
                await interaction.edit_original_response(
                    content="❌ Restore failed — no data returned", view=None
                )

        except Exception as e:
            await interaction.edit_original_response(content=f"❌ Restore failed: {e}", view=None)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Restore cancelled.", view=None)


class MaintenanceCog(commands.Cog):
    """Maintenance configuration and management."""

    def __init__(self, bot):
        self.bot = bot
        self._already_run: set = set()  # tracks (guild_id, schedule_id, date, time) to prevent double-runs
        self._update_already_run: set = set()  # tracks (guild_id, "update", date, time) to prevent double-runs
        self.backup_scheduler.start()
        self.update_scheduler.start()

    async def is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions."""
        if interaction.user.guild_permissions.administrator:
            return True
        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_role_id"):
            role = interaction.guild.get_role(config["admin_role_id"])
            if role and role in interaction.user.roles:
                return True
        return False

    @app_commands.command(name="maintenance", description="[ADMIN] Configure maintenance, backups and schedules")
    async def maintenance(self, interaction: discord.Interaction):
        """Open maintenance configuration panel."""
        if not await check_feature(interaction, "maintenance"):
            return
        try:
            if not await self.is_admin(interaction):
                await interaction.response.send_message("❌ Admin only.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            settings = await maintenance_db.get_maintenance_config(interaction.guild_id)
            if not settings:
                await maintenance_db.update_maintenance_config(
                    interaction.guild_id,
                    backup_enabled=0,
                    backup_schedule_type="daily",
                    backup_time="02:00",
                    backup_retention_days=30,
                    update_enabled=0,
                    update_schedule_type="weekly",
                    update_time="03:00",
                )
                settings = await maintenance_db.get_maintenance_config(interaction.guild_id)

            # Fallback if still None
            if not settings:
                settings = {"guild_id": interaction.guild_id, "backup_enabled": 0, "backup_time": "02:00"}

            schedules = await maintenance_db.get_backup_schedules(interaction.guild_id)
            active_count = sum(1 for s in schedules if s.get("enabled", 1))
            view = MaintenanceMainView(self, interaction.guild_id, settings)
            await interaction.followup.send(embed=view.build_embed(schedule_count=active_count), view=view, ephemeral=True)
        except Exception as e:
            logger.error(f"maintenance error: {e}", exc_info=True)
            try:
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            except:
                pass

    @tasks.loop(minutes=1)
    async def backup_scheduler(self, _now=None):
        """Background task to check and run scheduled backups from backup_schedules table."""
        now = _now if _now is not None else datetime.utcnow()
        current_time = now.strftime("%H:%M")
        current_day = now.weekday()  # 0=Monday
        today_date = now.strftime("%Y-%m-%d")

        try:
            all_schedules = await maintenance_db.get_all_enabled_backup_schedules()
        except Exception as e:
            logger.error(f"backup_scheduler: failed to fetch schedules: {e}")
            return

        for sched in all_schedules:
            guild_id = sched.get("guild_id")
            schedule_id = sched.get("id")
            try:
                # Skip if not the right time
                if current_time != sched.get("backup_time", "02:00"):
                    continue

                schedule_type = sched.get("schedule_type", "daily")
                if schedule_type == "weekly":
                    if current_day != sched.get("day_of_week", 0):
                        continue

                # Prevent double-run within the same minute for this schedule
                run_key = (guild_id, schedule_id, today_date, current_time)
                if run_key in self._already_run:
                    continue
                self._already_run.add(run_key)

                backup_type = sched.get("backup_type", "essentials")
                essentials_only = (backup_type == "essentials")
                target_dir = sched.get("target_directory") or None

                servers = await server_config_db.get_ark_servers(guild_id)
                if not servers:
                    logger.info(f"No servers found for guild {guild_id}, skipping schedule {schedule_id}")
                    continue

                if not hasattr(self.bot, "agent_manager") or not self.bot.agent_manager:
                    logger.warning(f"No agent_manager for guild {guild_id}")
                    continue

                for server in servers:
                    server_name = server.get("name")
                    if not server_name:
                        continue

                    agent_id = await self.bot.agent_manager.get_connected_agent_for_guild(guild_id)
                    if not agent_id:
                        logger.warning(f"No connected agent for {server_name} (guild {guild_id})")
                        continue

                    params: Dict = {"essentials_only": essentials_only}
                    if target_dir:
                        params["backup_path"] = target_dir

                    try:
                        result = await self.bot.agent_manager.send_command(
                            agent_id,
                            "backup_server",
                            server_name,
                            params=params,
                            timeout=120,
                        )

                        if result.get("data"):
                            data = result["data"]
                            backup_file = data.get("backup_file", "")
                            size_mb = data.get("size_mb", "0")
                            btype = data.get("backup_type", backup_type)

                            size_bytes = 0
                            try:
                                size_bytes = int(float(size_mb) * 1024 * 1024)
                            except Exception:
                                pass

                            await maintenance_db.add_backup_history(
                                guild_id=guild_id,
                                server_name=server_name,
                                backup_path=backup_file,
                                backup_size_bytes=size_bytes,
                                status="success",
                                backup_type=btype,
                            )

                            logger.info(f"Scheduled backup done: {server_name} → {backup_file} ({size_mb} MB)")
                            await _log_to_channel(
                                self.bot, guild_id,
                                f"💾 Scheduled backup completed for **{server_name}** (schedule: {sched['name']})\n"
                                f"📁 `{backup_file}`\n"
                                f"💾 Size: {size_mb} MB ({btype})",
                            )

                    except Exception as e:
                        logger.error(f"Scheduled backup failed for {server_name}: {e}")
                        await maintenance_db.add_backup_history(
                            guild_id=guild_id,
                            server_name=server_name,
                            backup_path="",
                            backup_size_bytes=0,
                            status="failed",
                            error_message=str(e),
                        )

            except Exception as e:
                logger.error(f"backup_scheduler error for schedule {schedule_id} guild {guild_id}: {e}", exc_info=True)

    @tasks.loop(minutes=1)
    async def update_scheduler(self, _now=None, _stop_delay: int = 15):
        """Background task to check and run scheduled server updates."""
        now = _now if _now is not None else datetime.utcnow()
        current_time = now.strftime("%H:%M")
        current_day = now.weekday()  # 0=Monday
        today_date = now.strftime("%Y-%m-%d")

        try:
            all_configs = await maintenance_db.get_all_enabled_update_configs()
        except Exception as e:
            logger.error(f"update_scheduler: failed to fetch configs: {e}")
            return

        for config in all_configs:
            guild_id = config.get("guild_id")
            try:
                # Skip if not the right time
                if current_time != config.get("update_time", "03:00"):
                    continue

                schedule_type = config.get("update_schedule_type", "weekly")
                if schedule_type == "weekly":
                    if current_day != config.get("update_day_of_week", 0):
                        continue

                # Prevent double-run within the same minute
                run_key = (guild_id, "update", today_date, current_time)
                if run_key in self._update_already_run:
                    continue
                self._update_already_run.add(run_key)

                enable_saveworld = config.get("enable_saveworld", 1)
                enable_pre_update_backup = config.get("enable_pre_update_backup", 1)

                servers = await server_config_db.get_ark_servers(guild_id)
                if not servers:
                    logger.info(f"No servers found for guild {guild_id}, skipping update schedule")
                    continue

                if not hasattr(self.bot, "agent_manager") or not self.bot.agent_manager:
                    logger.warning(f"No agent_manager for guild {guild_id}")
                    continue

                await _log_to_channel(
                    self.bot, guild_id,
                    f"🔄 **Scheduled server update starting** — {len(servers)} server(s)",
                )

                for server in servers:
                    server_name = server.get("name")
                    if not server_name:
                        continue

                    agent_id = await self.bot.agent_manager.get_connected_agent_for_guild(guild_id)
                    if not agent_id:
                        logger.warning(f"No connected agent for {server_name} (guild {guild_id})")
                        await _log_to_channel(self.bot, guild_id, f"⚠️ No connected agent for **{server_name}** — skipping")
                        continue

                    try:
                        await _log_to_channel(self.bot, guild_id, f"🔄 Starting scheduled update for **{server_name}**")

                        # Optional pre-update backup
                        if enable_pre_update_backup:
                            await _log_to_channel(self.bot, guild_id, f"💾 Running pre-update backup for **{server_name}**...")
                            try:
                                await self.bot.agent_manager.send_command(
                                    agent_id, "backup_server", server_name,
                                    params={"essentials_only": True},
                                    timeout=120,
                                )
                            except Exception as e:
                                logger.warning(f"Pre-update backup failed for {server_name}: {e}")

                        # Save world via RCON
                        if enable_saveworld:
                            try:
                                async with SimpleRCONClient(
                                    host=server["host"], port=server["rcon_port"],
                                    password=server["rcon_password"], timeout=10.0,
                                ) as rcon:
                                    await rcon.execute("saveworld")
                                await _log_to_channel(self.bot, guild_id, f"💾 Saveworld sent to **{server_name}**")
                            except Exception as e:
                                logger.warning(f"Saveworld failed for {server_name}: {e}")

                        # Stop server
                        await _log_to_channel(self.bot, guild_id, f"🛑 Stopping **{server_name}** for update...")
                        try:
                            await self.bot.agent_manager.send_command(
                                agent_id, "stop_server", server_name, timeout=60
                            )
                        except Exception as e:
                            logger.warning(f"Stop server failed for {server_name}: {e}")
                        await asyncio.sleep(_stop_delay)

                        # Run SteamCMD update
                        await _log_to_channel(self.bot, guild_id, f"📦 Running SteamCMD update for **{server_name}**...")
                        update_result = await self.bot.agent_manager.send_command(
                            agent_id, "update_server", server_name,
                            params={
                                "steamcmd_path": server.get("steamcmd_path", ""),
                                "server_path": server.get("server_path", ""),
                                "ark_appid": ASA_APP_ID,
                                "validate": False,
                                "use_custom_script": True,
                            },
                            timeout=1800,
                        )

                        if isinstance(update_result, dict) and update_result.get("type") == "error":
                            err = update_result.get("error", "Unknown error")
                            await _log_to_channel(self.bot, guild_id, f"❌ Update failed for **{server_name}**: {err}")
                            continue

                        # Start server
                        await _log_to_channel(self.bot, guild_id, f"▶️ Starting **{server_name}** after update...")
                        try:
                            await self.bot.agent_manager.send_command(
                                agent_id, "start_server", server_name, timeout=120
                            )
                        except Exception as e:
                            logger.warning(f"Start server failed for {server_name}: {e}")

                        await _log_to_channel(self.bot, guild_id, f"✅ Scheduled update complete for **{server_name}**")

                    except Exception as e:
                        logger.error(f"Scheduled update failed for {server_name}: {e}", exc_info=True)
                        await _log_to_channel(self.bot, guild_id, f"❌ Scheduled update error for **{server_name}**: {e}")

            except Exception as e:
                logger.error(f"update_scheduler error for guild {guild_id}: {e}", exc_info=True)

    async def _cleanup_old_backups(self, guild_id: int, retention_days: int):
        """Remove backup history records older than retention period."""
        try:
            # This would need the agent to delete actual backup files
            # For now, we just log that cleanup would happen
            logger.info(f"Retention cleanup for guild {guild_id}: would keep last {retention_days} days")
        except Exception as e:
            logger.error(f"Cleanup error for guild {guild_id}: {e}")


async def setup(bot):
    await bot.add_cog(MaintenanceCog(bot))
