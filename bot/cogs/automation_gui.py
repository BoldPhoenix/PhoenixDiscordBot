"""
Automation GUI - Interactive interface for managing scheduled commands.
Provides visual tools for creating, editing, and managing scheduled tasks.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button, Modal, TextInput
from typing import Optional, List
import logging

from bot.database import server_config_db
from bot.utils.config import Config

logger = logging.getLogger("AutomationGUI")


class AutomationView(View):
    """Main automation management interface."""

    def __init__(self, guild_id: int, user: discord.User, bot: commands.Bot, timeout: int = 300):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user = user
        self.bot = bot
        self.tasks = {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This management panel is not for you!", ephemeral=True
            )
            return False
        return True

    def load_tasks(self):
        """Load scheduled tasks from ScheduledCommands cog."""
        cog = self.bot.get_cog("ScheduledCommands")
        if cog:
            self.tasks = cog.scheduled_tasks.copy()
        else:
            self.tasks = {}

    def create_main_embed(self) -> discord.Embed:
        """Create the main automation embed."""
        embed = discord.Embed(
            title="⏰ Automation & Scheduled Commands",
            description=(
                "Manage automated tasks and scheduled RCON commands.\n\n"
                f"**Active Tasks:** {len([t for t in self.tasks.values() if t.get('enabled', True)])}\n"
                f"**Total Tasks:** {len(self.tasks)}"
            ),
            color=discord.Color.blue(),
        )

        if self.tasks:
            for task_id, task in list(self.tasks.items())[:5]:
                status = "✅" if task.get("enabled", True) else "⏸️"
                embed.add_field(
                    name=f"{status} {task['name']}",
                    value=(
                        f"🕐 {task['time']} | 🖥️ {task['server']}\n`{task['command'][:40]}...`"
                        if len(task["command"]) > 40
                        else f"🕐 {task['time']} | 🖥️ {task['server']}\n`{task['command']}`"
                    ),
                    inline=False,
                )

            if len(self.tasks) > 5:
                embed.add_field(
                    name="", value=f"*...and {len(self.tasks) - 5} more tasks*", inline=False
                )
        else:
            embed.add_field(
                name="No Tasks",
                value="No scheduled tasks configured. Create one to automate server management!",
                inline=False,
            )

        embed.add_field(
            name="💡 Common Uses",
            value=(
                "• Scheduled restarts\n"
                "• Automatic broadcasts\n"
                "• Periodic world saves\n"
                "• Wild dino wipes"
            ),
            inline=True,
        )

        embed.set_footer(text="💡 Use the buttons below to manage tasks")
        return embed


class AutomationMainView(AutomationView):
    """Main automation view with action buttons."""

    def __init__(self, guild_id: int, user: discord.User, bot: commands.Bot):
        super().__init__(guild_id, user, bot)

        self.add_item(AutomationActionButton("Create Task", "➕", "create"))
        self.add_item(AutomationActionButton("View Tasks", "📋", "view"))
        self.add_item(AutomationActionButton("Edit Task", "✏️", "edit"))
        self.add_item(AutomationActionButton("Delete Task", "🗑️", "delete"))
        self.add_item(AutomationActionButton("Toggle Task", "🔄", "toggle"))


class AutomationActionButton(Button):
    """Button for automation actions."""

    def __init__(self, label: str, emoji: str, action: str):
        super().__init__(
            style=discord.ButtonStyle.primary, label=label, emoji=emoji, custom_id=f"auto_{action}"
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        view: AutomationMainView = self.view

        if self.action == "create":
            # Get available servers
            servers = await server_config_db.get_ark_servers(view.guild_id)
            if not servers:
                servers = Config.ARK_SERVERS

            if not servers:
                await interaction.response.send_message(
                    "❌ No servers configured! Add servers first using `/setupgui` or `/addserver`.",
                    ephemeral=True,
                )
                return

            modal = CreateTaskModal(servers)
            await interaction.response.send_modal(modal)

        elif self.action == "view":
            tasks_view = TasksListView(view.guild_id, view.user, view.bot)
            tasks_view.load_tasks()
            embed = tasks_view.create_list_embed()
            await interaction.response.send_message(embed=embed, view=tasks_view, ephemeral=True)

        elif self.action == "edit":
            if not view.tasks:
                await interaction.response.send_message("❌ No tasks to edit!", ephemeral=True)
                return

            edit_view = EditTaskSelectView(view.guild_id, view.user, view.bot)
            edit_view.load_tasks()
            embed = edit_view.create_select_embed()
            await interaction.response.send_message(embed=embed, view=edit_view, ephemeral=True)

        elif self.action == "delete":
            if not view.tasks:
                await interaction.response.send_message("❌ No tasks to delete!", ephemeral=True)
                return

            delete_view = DeleteTaskSelectView(view.guild_id, view.user, view.bot)
            delete_view.load_tasks()
            embed = delete_view.create_select_embed()
            await interaction.response.send_message(embed=embed, view=delete_view, ephemeral=True)

        elif self.action == "toggle":
            if not view.tasks:
                await interaction.response.send_message("❌ No tasks to toggle!", ephemeral=True)
                return

            toggle_view = ToggleTaskSelectView(view.guild_id, view.user, view.bot)
            toggle_view.load_tasks()
            embed = toggle_view.create_select_embed()
            await interaction.response.send_message(embed=embed, view=toggle_view, ephemeral=True)


class CreateTaskModal(Modal):
    """Modal for creating a new scheduled task."""

    def __init__(self, servers: List[dict]):
        super().__init__(title="➕ Create Scheduled Task")
        self.servers = servers

        self.task_name = TextInput(
            label="Task Name",
            placeholder="e.g., Morning Restart, Hourly Save",
            required=True,
            max_length=50,
        )
        self.add_item(self.task_name)

        # Server selection (comma-separated list of available servers)
        server_names = ", ".join([s["name"] for s in servers[:10]])
        self.server = TextInput(
            label=(
                f"Server ({server_names[:40]}...)"
                if len(server_names) > 40
                else f"Server ({server_names})"
            ),
            placeholder="Enter server name exactly",
            required=True,
            max_length=50,
        )
        self.add_item(self.server)

        self.time = TextInput(
            label="Time (24-hour format HH:MM)",
            placeholder="e.g., 06:00, 18:30",
            required=True,
            max_length=5,
        )
        self.add_item(self.time)

        self.command = TextInput(
            label="RCON Command",
            placeholder="e.g., SaveWorld, ServerChat Hello, DoExit",
            required=True,
            max_length=500,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.command)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate time format
        from datetime import datetime

        try:
            datetime.strptime(self.time.value, "%H:%M")
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid time format! Use HH:MM (24-hour format).\nExamples: 06:00, 14:30, 22:00",
                ephemeral=True,
            )
            return

        # Check if server exists
        server_name = self.server.value.strip()
        if not any(s["name"].lower() == server_name.lower() for s in self.servers):
            await interaction.response.send_message(
                f"❌ Server '{server_name}' not found!\n"
                f"Available servers: {', '.join(s['name'] for s in self.servers)}",
                ephemeral=True,
            )
            return

        # Get ScheduledCommands cog
        cog = interaction.client.get_cog("ScheduledCommands")
        if not cog:
            await interaction.response.send_message(
                "❌ ScheduledCommands cog not loaded!", ephemeral=True
            )
            return

        # Create task ID
        task_id = f"{server_name}_{self.task_name.value}_{self.time.value}".replace(" ", "_")

        # Add task
        cog.scheduled_tasks[task_id] = {
            "name": self.task_name.value,
            "server": server_name,
            "command": self.command.value,
            "time": self.time.value,
            "enabled": True,
            "created_by": interaction.user.id,
        }

        embed = discord.Embed(
            title="✅ Task Created",
            description=f"**{self.task_name.value}** has been scheduled!",
            color=discord.Color.green(),
        )
        embed.add_field(name="Server", value=server_name, inline=True)
        embed.add_field(name="Time", value=self.time.value, inline=True)
        embed.add_field(name="Command", value=f"`{self.command.value}`", inline=False)
        embed.set_footer(text=f"Task ID: {task_id[:50]}")

        await interaction.response.send_message(embed=embed, ephemeral=True)


class TasksListView(AutomationView):
    """View for listing all scheduled tasks."""

    def __init__(self, guild_id: int, user: discord.User, bot: commands.Bot):
        super().__init__(guild_id, user, bot)
        self.current_page = 0
        self.items_per_page = 5

        self.add_item(PaginationButton("◀️ Previous", "prev"))
        self.add_item(PaginationButton("Next ▶️", "next"))


    def create_list_embed(self) -> discord.Embed:
        """Create task list embed."""
        task_list = list(self.tasks.items())
        total_pages = max(1, (len(task_list) + self.items_per_page - 1) // self.items_per_page)
        self.current_page = min(self.current_page, total_pages - 1)

        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        page_tasks = task_list[start:end]

        embed = discord.Embed(
            title="📋 Scheduled Tasks",
            description=f"Showing {len(page_tasks)} of {len(task_list)} tasks",
            color=discord.Color.blue(),
        )

        for task_id, task in page_tasks:
            status = "✅ Enabled" if task.get("enabled", True) else "⏸️ Paused"

            value = f"**Status:** {status}\n"
            value += f"**Server:** {task['server']}\n"
            value += f"**Time:** {task['time']}\n"
            value += (
                f"**Command:** `{task['command'][:50]}{'...' if len(task['command']) > 50 else ''}`"
            )

            embed.add_field(name=f"⏰ {task['name']}", value=value, inline=False)

        if not page_tasks:
            embed.add_field(name="No Tasks", value="No scheduled tasks found", inline=False)

        embed.set_footer(text=f"Page {self.current_page + 1}/{total_pages}")
        return embed


class PaginationButton(Button):
    """Button for pagination."""

    def __init__(self, label: str, direction: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=label)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: TasksListView = self.view

        if self.direction == "prev" and view.current_page > 0:
            view.current_page -= 1
        elif self.direction == "next":
            total_pages = max(1, (len(view.tasks) + view.items_per_page - 1) // view.items_per_page)
            if view.current_page < total_pages - 1:
                view.current_page += 1

        embed = view.create_list_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class EditTaskSelectView(AutomationView):
    """View for selecting a task to edit."""

    def __init__(self, guild_id: int, user: discord.User, bot: commands.Bot):
        super().__init__(guild_id, user, bot)


    def load_tasks(self):
        """Load tasks and add select menu."""
        super().load_tasks()

        if self.tasks:
            options = []
            for task_id, task in list(self.tasks.items())[:25]:
                status = "✅" if task.get("enabled", True) else "⏸️"
                options.append(
                    discord.SelectOption(
                        label=f"{status} {task['name'][:40]}",
                        description=f"{task['time']} | {task['server']}",
                        value=task_id[:100],
                    )
                )

            select = Select(
                placeholder="Select a task to edit...",
                options=options,
                custom_id="edit_task_select",
            )
            select.callback = self.task_selected
            self.add_item(select)

    async def task_selected(self, interaction: discord.Interaction):
        """Handle task selection for editing."""
        task_id = interaction.data["values"][0]
        task = self.tasks.get(task_id)

        if task:
            modal = EditTaskModal(task_id, task)
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message("❌ Task not found!", ephemeral=True)

    def create_select_embed(self) -> discord.Embed:
        """Create task selection embed."""
        embed = discord.Embed(
            title="✏️ Edit Task",
            description="Select a task from the dropdown to edit it.",
            color=discord.Color.blue(),
        )
        return embed


class EditTaskModal(Modal):
    """Modal for editing an existing task."""

    def __init__(self, task_id: str, task: dict):
        super().__init__(title=f"✏️ Edit: {task['name'][:30]}")
        self.task_id = task_id

        self.task_name = TextInput(
            label="Task Name", default=task["name"], required=True, max_length=50
        )
        self.add_item(self.task_name)

        self.time = TextInput(
            label="Time (24-hour format HH:MM)", default=task["time"], required=True, max_length=5
        )
        self.add_item(self.time)

        self.command = TextInput(
            label="RCON Command",
            default=task["command"],
            required=True,
            max_length=500,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.command)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate time format
        from datetime import datetime

        try:
            datetime.strptime(self.time.value, "%H:%M")
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid time format! Use HH:MM (24-hour format).", ephemeral=True
            )
            return

        # Get ScheduledCommands cog
        cog = interaction.client.get_cog("ScheduledCommands")
        if not cog or self.task_id not in cog.scheduled_tasks:
            await interaction.response.send_message("❌ Task not found!", ephemeral=True)
            return

        # Update task
        cog.scheduled_tasks[self.task_id]["name"] = self.task_name.value
        cog.scheduled_tasks[self.task_id]["time"] = self.time.value
        cog.scheduled_tasks[self.task_id]["command"] = self.command.value

        embed = discord.Embed(
            title="✅ Task Updated",
            description=f"**{self.task_name.value}** has been updated!",
            color=discord.Color.green(),
        )
        embed.add_field(name="Time", value=self.time.value, inline=True)
        embed.add_field(name="Command", value=f"`{self.command.value}`", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


class DeleteTaskSelectView(AutomationView):
    """View for selecting a task to delete."""

    def __init__(self, guild_id: int, user: discord.User, bot: commands.Bot):
        super().__init__(guild_id, user, bot)


    def load_tasks(self):
        """Load tasks and add select menu."""
        super().load_tasks()

        if self.tasks:
            options = []
            for task_id, task in list(self.tasks.items())[:25]:
                options.append(
                    discord.SelectOption(
                        label=task["name"][:50],
                        description=f"{task['time']} | {task['server']}",
                        value=task_id[:100],
                    )
                )

            select = Select(
                placeholder="Select a task to delete...",
                options=options,
                custom_id="delete_task_select",
            )
            select.callback = self.task_selected
            self.add_item(select)

    async def task_selected(self, interaction: discord.Interaction):
        """Handle task selection for deletion."""
        task_id = interaction.data["values"][0]
        task = self.tasks.get(task_id)

        if task:
            confirm_view = ConfirmDeleteTaskView(task_id, task, self.bot)
            embed = discord.Embed(
                title="⚠️ Confirm Deletion",
                description=f"Are you sure you want to delete **{task['name']}**?",
                color=discord.Color.red(),
            )
            embed.add_field(name="Server", value=task["server"], inline=True)
            embed.add_field(name="Time", value=task["time"], inline=True)
            embed.add_field(name="Command", value=f"`{task['command']}`", inline=False)
            await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
        else:
            await interaction.response.send_message("❌ Task not found!", ephemeral=True)

    def create_select_embed(self) -> discord.Embed:
        """Create task deletion selection embed."""
        embed = discord.Embed(
            title="🗑️ Delete Task",
            description="Select a task from the dropdown to delete it.",
            color=discord.Color.red(),
        )
        return embed


class ConfirmDeleteTaskView(View):
    """Confirmation view for task deletion."""

    def __init__(self, task_id: str, task: dict, bot: commands.Bot):
        super().__init__(timeout=None)
        self.task_id = task_id
        self.task = task
        self.bot = bot

    @discord.ui.button(label="Yes, Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: Button):
        cog = self.bot.get_cog("ScheduledCommands")
        if cog and self.task_id in cog.scheduled_tasks:
            del cog.scheduled_tasks[self.task_id]

            embed = discord.Embed(
                title="✅ Task Deleted",
                description=f"**{self.task['name']}** has been deleted.",
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title="❌ Error",
                description="Task not found or already deleted.",
                color=discord.Color.red(),
            )

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            content="❌ Deletion cancelled.", embed=None, view=None
        )


class ToggleTaskSelectView(AutomationView):
    """View for toggling task enabled status."""

    def __init__(self, guild_id: int, user: discord.User, bot: commands.Bot):
        super().__init__(guild_id, user, bot)


    def load_tasks(self):
        """Load tasks and add select menu."""
        super().load_tasks()

        if self.tasks:
            options = []
            for task_id, task in list(self.tasks.items())[:25]:
                status = "✅" if task.get("enabled", True) else "⏸️"
                options.append(
                    discord.SelectOption(
                        label=f"{status} {task['name'][:40]}",
                        description="Click to toggle",
                        value=task_id[:100],
                    )
                )

            select = Select(
                placeholder="Select a task to toggle...",
                options=options,
                custom_id="toggle_task_select",
            )
            select.callback = self.task_selected
            self.add_item(select)

    async def task_selected(self, interaction: discord.Interaction):
        """Handle task selection for toggling."""
        task_id = interaction.data["values"][0]

        cog = self.bot.get_cog("ScheduledCommands")
        if cog and task_id in cog.scheduled_tasks:
            task = cog.scheduled_tasks[task_id]
            task["enabled"] = not task.get("enabled", True)
            new_status = task["enabled"]

            embed = discord.Embed(
                title="✅ Task Toggled",
                description=f"**{task['name']}** is now {'✅ Enabled' if new_status else '⏸️ Paused'}",
                color=discord.Color.green(),
            )
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.send_message("❌ Task not found!", ephemeral=True)

    def create_select_embed(self) -> discord.Embed:
        """Create toggle selection embed."""
        embed = discord.Embed(
            title="🔄 Toggle Task",
            description="Select a task to enable/pause it.",
            color=discord.Color.blue(),
        )
        return embed


class AutomationGUI(commands.Cog):
    """Interactive automation and scheduled commands GUI."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user is admin."""
        if interaction.user.guild_permissions.administrator:
            return True

        config = await server_config_db.get_server_config(interaction.guild_id)
        if config and config.get("admin_role_id"):
            admin_role = interaction.guild.get_role(config["admin_role_id"])
            if admin_role and admin_role in interaction.user.roles:
                return True

        return False

    @app_commands.command(
        name="automationcfg", description="⏰ Interactive automation management (admin only)"
    )
    async def automation_cfg(self, interaction: discord.Interaction):
        """Open the interactive automation management GUI."""
        if not await self.is_admin(interaction):
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        view = AutomationMainView(interaction.guild_id, interaction.user, self.bot)
        view.load_tasks()
        embed = view.create_main_embed()

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(AutomationGUI(bot))
