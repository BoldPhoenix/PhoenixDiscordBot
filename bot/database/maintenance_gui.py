"""
Maintenance Configuration GUI Cog.
Provides GUI for backup schedules, maintenance settings, and job management.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button, Modal, TextInput

from bot.database import maintenance_db, server_config_db

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


class MaintenanceSettingsModal(Modal, title="⚙️ Maintenance Settings"):
    """Modal for configuring maintenance settings."""

    backup_enabled = TextInput(
        label="Enable Backups? (yes/no)",
        placeholder="yes",
        required=True,
        max_length=3,
    )
    backup_schedule = TextInput(
        label="Schedule (daily/weekly)",
        placeholder="daily",
        required=True,
        max_length=10,
    )
    backup_time = TextInput(
        label="Backup Time (HH:MM UTC)",
        placeholder="02:00",
        required=True,
        max_length=5,
    )
    retention_days = TextInput(
        label="Retention Days",
        placeholder="30",
        required=True,
        max_length=3,
    )
    backup_root = TextInput(
        label="Backup Root Path",
        placeholder="D:\\ARK\\Backups",
        required=False,
        max_length=200,
    )

    def __init__(self, settings: dict):
        super().__init__()
        self.guild_id = settings.get("guild_id")
        self.backup_enabled.default = "yes" if settings.get("backup_enabled") else "no"
        self.backup_schedule.default = settings.get("backup_schedule_type", "daily")
        self.backup_time.default = settings.get("backup_time", "02:00")
        self.retention_days.default = str(settings.get("backup_retention_days", 30))
        self.backup_root.default = settings.get("backup_root_path", "")

    async def on_submit(self, interaction: discord.Interaction):
        enabled = self.backup_enabled.value.strip().lower() in ("yes", "y", "true", "1")
        schedule = self.backup_schedule.value.strip().lower()
        if schedule not in ("daily", "weekly"):
            await interaction.response.send_message("❌ Schedule must be 'daily' or 'weekly'.", ephemeral=True)
            return

        time_str = self.backup_time.value.strip()
        try:
            parts = time_str.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except:
            await interaction.response.send_message("❌ Time must be HH:MM format.", ephemeral=True)
            return

        try:
            retention = int(self.retention_days.value.strip())
        except:
            await interaction.response.send_message("❌ Retention must be a number.", ephemeral=True)
            return

        await maintenance_db.update_maintenance_config(
            self.guild_id,
            backup_enabled=1 if enabled else 0,
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
        embed.add_field(name="Schedule", value=schedule, inline=True)
        embed.add_field(name="Time (UTC)", value=f"{hour:02d}:{minute:02d}", inline=True)
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

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🔧 Maintenance Configuration",
            description="Configure automated backups and updates for your ARK servers",
            color=discord.Color.blue(),
        )

        # Backup settings
        backup_enabled = self.settings.get("backup_enabled", 0)
        embed.add_field(
            name="💾 Backups",
            value="Enabled ✅" if backup_enabled else "Disabled ❌",
            inline=True,
        )
        if backup_enabled:
            schedule = self.settings.get("backup_schedule_type", "daily")
            time = self.settings.get("backup_time", "02:00")
            retention = self.settings.get("backup_retention_days", 30)
            embed.add_field(name="Schedule", value=f"{schedule} @ {time} UTC", inline=True)
            embed.add_field(name="Retention", value=f"{retention} days", inline=True)

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

    @discord.ui.button(label="⚙️ Backup Settings", style=discord.ButtonStyle.primary)
    async def backup_settings(self, interaction: discord.Interaction, button: Button):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        await interaction.response.send_modal(MaintenanceSettingsModal(self.settings))

    @discord.ui.button(label="🔄 Update Settings", style=discord.ButtonStyle.primary)
    async def update_settings(self, interaction: discord.Interaction, button: Button):
        if not await self.cog.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return
        await interaction.response.send_modal(UpdateSettingsModal(self.settings))

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
            lines.append(f"{status} {date} - {server}")

        embed.description = "\n".join(lines) or "No backups"
        await interaction.followup.send(embed=embed, ephemeral=True)

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


class MaintenanceCog(commands.Cog):
    """Maintenance configuration and management."""

    def __init__(self, bot):
        self.bot = bot
        self.backup_scheduler.start()

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

    @app_commands.command(name="maintcfg", description="[ADMIN] Configure maintenance settings")
    async def maintcfg(self, interaction: discord.Interaction):
        """Open maintenance configuration panel."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message("❌ Admin only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        settings = await maintenance_db.get_maintenance_config(interaction.guild_id)
        if not settings:
            settings = {"guild_id": interaction.guild_id}
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

        view = MaintenanceMainView(self, interaction.guild_id, settings)
        await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)

    @tasks.loop(minutes=1)
    async def backup_scheduler(self):
        """Background task to check and run scheduled backups."""
        now = datetime.utcnow()
        current_time = now.strftime("%H:%M")
        current_day = now.weekday()  # 0=Monday

        # Get all guilds with backup enabled
        # This is a simple implementation - in production you'd want more efficient querying
        for guild in self.bot.guilds:
            try:
                config = await maintenance_db.get_maintenance_config(guild.id)
                if not config or not config.get("backup_enabled"):
                    continue

                schedule = config.get("backup_schedule_type", "daily")
                backup_time = config.get("backup_time", "02:00")

                # Check if it's time to run backup
                if current_time != backup_time:
                    continue

                if schedule == "weekly":
                    config_day = config.get("backup_day_of_week", 0)
                    if current_day != config_day:
                        continue

                # TODO: Get servers for this guild and run backup via agent
                logger.info(f"Scheduled backup triggered for guild {guild.id}")

            except Exception as e:
                logger.error(f"Backup scheduler error for guild {guild.id}: {e}")


async def setup(bot):
    await bot.add_cog(MaintenanceCog(bot))
