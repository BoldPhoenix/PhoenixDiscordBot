"""
Scheduled commands cog for automating RCON tasks.
Allows admins to schedule periodic server commands (restarts, broadcasts, saves, etc.).
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
from typing import Dict, List
from datetime import datetime, time as dt_time
import json

from bot.utils.config import Config
from bot.rcon.client import RCONManager

logger = logging.getLogger("ScheduledCommands")


class ScheduledCommands(commands.Cog):
    """Scheduled RCON commands for server automation."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rcon_manager = RCONManager(Config.ARK_SERVERS)
        self.scheduled_tasks: Dict[str, dict] = {}
        self.task_check.start()

    def cog_unload(self):
        self.task_check.cancel()

    @tasks.loop(minutes=1)
    async def task_check(self):
        """Check and execute scheduled tasks."""
        now = datetime.now()
        current_time = now.strftime("%H:%M")

        for task_id, task in list(self.scheduled_tasks.items()):
            if task["time"] == current_time and task["enabled"]:
                await self._execute_scheduled_task(task)

    @task_check.before_loop
    async def before_task_check(self):
        await self.bot.wait_until_ready()

    async def _execute_scheduled_task(self, task: dict):
        """Execute a scheduled task."""
        try:
            server = task["server"]
            command = task["command"]

            client = self.rcon_manager.get_client(server)
            if client:
                response = await client.execute_command(command)
                logger.info(f"Executed scheduled task: {task['name']} on {server}")

                if task.get("notify_channel"):
                    channel = self.bot.get_channel(task["notify_channel"])
                    if channel:
                        await channel.send(
                            f" Scheduled task **{task['name']}** executed on **{server}**"
                        )
        except Exception as e:
            logger.error(f"Error executing scheduled task {task['name']}: {e}")

    @app_commands.command(name="schedule", description="[ADMIN] Schedule a recurring RCON command")
    @app_commands.describe(
        name="Task name",
        server="Server to run command on",
        command="RCON command to execute",
        time="Time to run (HH:MM format, 24-hour)",
        notify_channel="Channel to notify when task runs (optional)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def schedule_command(
        self,
        interaction: discord.Interaction,
        name: str,
        server: str,
        command: str,
        time: str,
        notify_channel: discord.TextChannel = None,
    ):
        """Schedule a recurring RCON command."""
        # Validate time format
        try:
            datetime.strptime(time, "%H:%M")
        except ValueError:
            await interaction.response.send_message(
                " Invalid time format. Use HH:MM (24-hour format).", ephemeral=True
            )
            return

        # Check if server exists
        if not self.rcon_manager.get_client(server):
            await interaction.response.send_message(
                f" Server '{server}' not found.", ephemeral=True
            )
            return

        task_id = f"{server}_{name}_{time}".replace(" ", "_")

        self.scheduled_tasks[task_id] = {
            "name": name,
            "server": server,
            "command": command,
            "time": time,
            "enabled": True,
            "notify_channel": notify_channel.id if notify_channel else None,
            "created_by": interaction.user.id,
        }

        embed = discord.Embed(title=" Scheduled Task Created", color=discord.Color.green())
        embed.add_field(name="Task Name", value=name, inline=True)
        embed.add_field(name="Server", value=server, inline=True)
        embed.add_field(name="Time", value=time, inline=True)
        embed.add_field(name="Command", value=f"{command}", inline=False)
        if notify_channel:
            embed.add_field(name="Notifications", value=notify_channel.mention, inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="listschedules", description="[ADMIN] List all scheduled tasks")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_schedules(self, interaction: discord.Interaction):
        """List all scheduled tasks."""
        if not self.scheduled_tasks:
            await interaction.response.send_message(
                "No scheduled tasks configured.", ephemeral=True
            )
            return

        embed = discord.Embed(title=" Scheduled Tasks", color=discord.Color.blue())

        for task_id, task in self.scheduled_tasks.items():
            status = " Enabled" if task["enabled"] else " Disabled"
            value = (
                f"**Server:** {task['server']}\n"
                f"**Time:** {task['time']}\n"
                f"**Command:** {task['command']}\n"
                f"**Status:** {status}"
            )
            embed.add_field(name=task["name"], value=value, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="removeschedule", description="[ADMIN] Remove a scheduled task")
    @app_commands.describe(name="Name of the task to remove")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_schedule(self, interaction: discord.Interaction, name: str):
        """Remove a scheduled task."""
        # Find task by name
        task_id = None
        for tid, task in self.scheduled_tasks.items():
            if task["name"] == name:
                task_id = tid
                break

        if not task_id:
            await interaction.response.send_message(f" Task '{name}' not found.", ephemeral=True)
            return

        del self.scheduled_tasks[task_id]
        await interaction.response.send_message(
            f" Removed scheduled task: **{name}**", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ScheduledCommands(bot))
