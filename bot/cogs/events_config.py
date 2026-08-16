"""
Events Configuration Module
Centralized configuration and management for all bot events (Christmas, Easter, ARK anniversaries, etc.)
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import datetime
import json
from pathlib import Path

import logging

logger = logging.getLogger(__name__)


class EventsConfig(commands.Cog):
    """Manage seasonal and special events configuration"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_file = Path("events_config.json")
        self.events = self.load_config()

    def load_config(self) -> dict:
        """Load events configuration from file"""
        if self.config_file.exists():
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "christmas": {
                "enabled": True,
                "start_date": "2025-12-13",
                "end_date": "2025-12-25",
                "channel_id": None,
                "log_channel_id": None,
                "required_role_id": None,
                "debug_mode": False,
                "description": "12 Days of ARKmas - Daily gifts for the holiday season",
                "daily_message": "Wake up {role}! A new gift is here!",
                "announcement_time": "09:00",
            },
            "easter": {
                "enabled": False,
                "start_date": None,
                "end_date": None,
                "channel_id": None,
                "log_channel_id": None,
                "required_role_id": None,
                "debug_mode": False,
                "description": "Easter Egg Hunt - Special rewards",
                "daily_message": "🐰 New Easter event available!",
                "announcement_time": "09:00",
            },
            "ark_anniversary": {
                "enabled": False,
                "start_date": None,
                "end_date": None,
                "channel_id": None,
                "log_channel_id": None,
                "required_role_id": None,
                "debug_mode": False,
                "description": "ARK Anniversary Celebration",
                "daily_message": "🎉 ARK Anniversary event is live!",
                "announcement_time": "09:00",
            },
        }

    def save_config(self):
        """Save events configuration to file"""
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.events, f, indent=2)
        logger.info("Events configuration saved")

    @app_commands.command(name="eventcfg", description="⚙️ Configure seasonal and special events")
    @app_commands.describe(
        event="The event to configure",
        action="Simple action: view, enable, disable (leave other fields blank for these)",
        channel="Announcement channel (mention or ID)",
        log_channel="Log channel for tracking (mention or ID)",
        role="Required role to participate (mention or ID)",
        start_date="Start date (YYYY-MM-DD)",
        end_date="End date (YYYY-MM-DD)",
        daily_message="Daily announcement message (use {role} for mention)",
        announcement_time="Daily announcement time (HH:MM 24-hour)",
        debug="Debug mode (true/false)",
    )
    @app_commands.default_permissions(administrator=True)
    async def events_config_cmd(
        self,
        interaction: discord.Interaction,
        event: str,
        action: Optional[str] = None,
        channel: Optional[str] = None,
        log_channel: Optional[str] = None,
        role: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        daily_message: Optional[str] = None,
        announcement_time: Optional[str] = None,
        debug: Optional[str] = None,
    ):
        """Configure event settings - simple actions or detailed configuration"""
        await interaction.response.defer(ephemeral=True)

        if event not in self.events:
            await interaction.followup.send(
                f"❌ Unknown event: `{event}`\n" f"Available: {', '.join(self.events.keys())}",
                ephemeral=True,
            )
            return

        event_data = self.events[event]

        # Check if this is a simple action (view/enable/disable) or detailed config
        has_config_params = any(
            [
                channel,
                log_channel,
                role,
                start_date,
                end_date,
                daily_message,
                announcement_time,
                debug,
            ]
        )

        if action and not has_config_params:
            # Simple action mode
            if action == "view":
                embed = self.create_event_embed(event, event_data)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            elif action == "enable":
                event_data["enabled"] = True
                self.save_config()
                await interaction.followup.send(f"✅ Enabled **{event}** event", ephemeral=True)
                return

            elif action == "disable":
                event_data["enabled"] = False
                self.save_config()
                await interaction.followup.send(f"✅ Disabled **{event}** event", ephemeral=True)
                return

            else:
                await interaction.followup.send(
                    f"❌ Unknown action: `{action}`\n" f"Available: view, enable, disable",
                    ephemeral=True,
                )
                return

        # Detailed configuration mode - if any config parameters are provided
        if not has_config_params:
            # No action or config params provided
            await interaction.followup.send(
                f"❌ Please specify either:\n"
                f"• An **action** (view, enable, disable)\n"
                f"• Or **configuration parameters** (channel, role, dates, etc.)",
                ephemeral=True,
            )
            return

        changes = []

        # Channel configuration
        if channel:
            try:
                channel_id = int(channel.strip("<#>"))
                event_data["channel_id"] = channel_id
                changes.append(f"📢 Announcement channel: <#{channel_id}>")
            except ValueError:
                return await interaction.followup.send(
                    "❌ Invalid channel format\n\n"
                    "**Valid formats:**\n"
                    "• Mention: #arkmas-event\n"
                    "• ID: 555555555555555551",
                    ephemeral=True,
                )

        # Log channel configuration
        if log_channel:
            try:
                log_channel_id = int(log_channel.strip("<#>"))
                event_data["log_channel_id"] = log_channel_id
                changes.append(f"📝 Log channel: <#{log_channel_id}>")
            except ValueError:
                return await interaction.followup.send(
                    "❌ Invalid log channel format\n\n"
                    "**Valid formats:**\n"
                    "• Mention: #event-logs\n"
                    "• ID: 555555555555555552",
                    ephemeral=True,
                )

        # Role configuration
        if role:
            try:
                role_id = int(role.strip("<@&>"))
                event_data["required_role_id"] = role_id
                changes.append(f"🎭 Required role: <@&{role_id}>")
            except ValueError:
                return await interaction.followup.send(
                    "❌ Invalid role format\n\n"
                    "**Valid formats:**\n"
                    "• Mention: @VerifiedPlayer\n"
                    "• ID: 111111111111111111",
                    ephemeral=True,
                )

        # Date configurations
        if start_date:
            try:
                datetime.datetime.strptime(start_date, "%Y-%m-%d")
                event_data["start_date"] = start_date
                changes.append(f"📅 Start date: `{start_date}`")
            except ValueError:
                return await interaction.followup.send(
                    "❌ Invalid start date format\n\n"
                    "**Format:** YYYY-MM-DD\n"
                    "**Example:** 2025-12-13",
                    ephemeral=True,
                )

        if end_date:
            try:
                datetime.datetime.strptime(end_date, "%Y-%m-%d")
                event_data["end_date"] = end_date
                changes.append(f"📅 End date: `{end_date}`")
            except ValueError:
                return await interaction.followup.send(
                    "❌ Invalid end date format\n\n"
                    "**Format:** YYYY-MM-DD\n"
                    "**Example:** 2025-12-25",
                    ephemeral=True,
                )

        # Daily message
        if daily_message:
            event_data["daily_message"] = daily_message
            changes.append(f"💬 Daily message: `{daily_message}`")

        # Announcement time
        if announcement_time:
            try:
                parts = announcement_time.split(":")
                if len(parts) != 2:
                    raise ValueError
                hour = int(parts[0])
                minute = int(parts[1])
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
                event_data["announcement_time"] = announcement_time
                changes.append(f"⏰ Announcement time: `{announcement_time}`")
            except (ValueError, IndexError):
                return await interaction.followup.send(
                    "❌ Invalid time format\n\n"
                    "**Format:** HH:MM (24-hour)\n"
                    "**Example:** 09:00 or 14:30",
                    ephemeral=True,
                )

        # Debug mode
        if debug:
            if debug.lower() in ["true", "false"]:
                event_data["debug_mode"] = debug.lower() == "true"
                status = "enabled" if event_data["debug_mode"] else "disabled"
                changes.append(f"🐛 Debug mode: {status}")
            else:
                return await interaction.followup.send(
                    "❌ Invalid debug value\n\n" "**Valid values:** true, false", ephemeral=True
                )

        # Save and confirm
        if changes:
            self.save_config()
            embed = discord.Embed(
                title=f"✅ Updated {event.title()} Event",
                description="\n".join(changes),
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ No changes specified\n\n" "Provide at least one parameter to update.",
                ephemeral=True,
            )

    @events_config_cmd.autocomplete("event")
    async def event_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for event names"""
        return [
            app_commands.Choice(name=f"{name} - {data['description']}", value=name)
            for name, data in self.events.items()
            if current.lower() in name.lower()
        ]

    @events_config_cmd.autocomplete("action")
    async def action_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for actions"""
        actions = [
            ("view", "View current configuration"),
            ("enable", "Enable this event"),
            ("disable", "Disable this event"),
        ]
        return [
            app_commands.Choice(name=f"{name} - {desc}", value=name)
            for name, desc in actions
            if current.lower() in name.lower()
        ]

    @events_config_cmd.autocomplete("channel")
    async def channel_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for channels"""
        choices = []
        for channel in interaction.guild.text_channels:
            if current.lower() in channel.name.lower():
                choices.append(app_commands.Choice(name=f"#{channel.name}", value=str(channel.id)))
            if len(choices) >= 25:  # Discord limit
                break
        return choices

    @events_config_cmd.autocomplete("log_channel")
    async def log_channel_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for log channels"""
        choices = []
        for channel in interaction.guild.text_channels:
            if current.lower() in channel.name.lower():
                choices.append(app_commands.Choice(name=f"#{channel.name}", value=str(channel.id)))
            if len(choices) >= 25:  # Discord limit
                break
        return choices

    @events_config_cmd.autocomplete("role")
    async def role_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for roles"""
        choices = []
        for role in interaction.guild.roles:
            if role.name != "@everyone" and current.lower() in role.name.lower():
                choices.append(app_commands.Choice(name=f"@{role.name}", value=str(role.id)))
            if len(choices) >= 25:  # Discord limit
                break
        return choices

    @app_commands.command(name="eventlist", description="📅 List all configured events")
    async def events_list_cmd(self, interaction: discord.Interaction):
        """List all events and their status"""
        embed = discord.Embed(
            title="🎉 Events Configuration",
            description="All configured seasonal and special events",
            color=discord.Color.blue(),
        )

        for event_name, event_data in self.events.items():
            status = "✅ Enabled" if event_data["enabled"] else "❌ Disabled"
            debug = " 🐛 (Debug)" if event_data.get("debug_mode") else ""

            value = f"{status}{debug}\n"
            value += f"📅 {event_data['start_date']} to {event_data['end_date']}\n"

            if event_data.get("channel_id"):
                value += f"📢 <#{event_data['channel_id']}>\n"

            if event_data.get("log_channel_id"):
                value += f"📝 Log: <#{event_data['log_channel_id']}>\n"

            if event_data.get("required_role_id"):
                value += f"🎭 <@&{event_data['required_role_id']}>\n"

            if event_data.get("announcement_time"):
                value += f"⏰ {event_data['announcement_time']}\n"

            value += f"*{event_data['description']}*"

            embed.add_field(name=event_name.replace("_", " ").title(), value=value, inline=False)

        embed.set_footer(text="Use /eventcfg to modify settings")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def create_event_embed(self, event_name: str, event_data: dict) -> discord.Embed:
        """Create an embed showing event configuration"""
        status = "✅ Enabled" if event_data["enabled"] else "❌ Disabled"
        color = discord.Color.green() if event_data["enabled"] else discord.Color.red()

        embed = discord.Embed(
            title=f"🎉 {event_name.replace('_', ' ').title()} Configuration",
            description=event_data["description"],
            color=color,
        )

        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(
            name="Debug Mode",
            value="🐛 Enabled" if event_data.get("debug_mode") else "Disabled",
            inline=True,
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        embed.add_field(name="Start Date", value=event_data["start_date"] or "Not set", inline=True)
        embed.add_field(name="End Date", value=event_data["end_date"] or "Not set", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        embed.add_field(
            name="📢 Announcement Channel",
            value=f"<#{event_data['channel_id']}>" if event_data.get("channel_id") else "Not set",
            inline=True,
        )
        embed.add_field(
            name="📝 Log Channel",
            value=(
                f"<#{event_data['log_channel_id']}>"
                if event_data.get("log_channel_id")
                else "Not set"
            ),
            inline=True,
        )
        embed.add_field(
            name="🎭 Required Role",
            value=(
                f"<@&{event_data['required_role_id']}>"
                if event_data.get("required_role_id")
                else "None"
            ),
            inline=True,
        )

        # Daily message and time
        embed.add_field(
            name="💬 Daily Message",
            value=f"`{event_data.get('daily_message', 'Not set')}`",
            inline=False,
        )
        embed.add_field(
            name="⏰ Announcement Time",
            value=f"`{event_data.get('announcement_time', '09:00')}` (24-hour format)",
            inline=True,
        )

        return embed

    def get_event_config(self, event_name: str) -> Optional[dict]:
        """Get configuration for a specific event"""
        return self.events.get(event_name)

    def is_event_active(self, event_name: str) -> bool:
        """Check if an event is currently active"""
        event = self.events.get(event_name)
        if not event or not event["enabled"]:
            return False

        if not event["start_date"] or not event["end_date"]:
            return False

        today = datetime.date.today()
        start = datetime.datetime.strptime(event["start_date"], "%Y-%m-%d").date()
        end = datetime.datetime.strptime(event["end_date"], "%Y-%m-%d").date()

        return start <= today <= end


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsConfig(bot))
    logger.info("Events configuration cog loaded")
