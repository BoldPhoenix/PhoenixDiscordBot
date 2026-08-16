"""
Phase 16: ARK Server Service Management

Discord commands for creating, updating, and deleting ARK server Windows services
via the remote agent. This replaces NSSM with a native Phoenix ARK solution.
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional

logger = logging.getLogger("ServerService")

MAP_CHOICES = [
    app_commands.Choice(name="The Island", value="TheIsland"),
    app_commands.Choice(name="Scorched Earth", value="ScorchedEarth_P"),
    app_commands.Choice(name="The Center", value="TheCenter"),
    app_commands.Choice(name="Aberration", value="Aberration_P"),
    app_commands.Choice(name="Extinction", value="Extinction"),
    app_commands.Choice(name="Valguero", value="Valguero_P"),
    app_commands.Choice(name="Genesis: Part 1", value="Genesis"),
    app_commands.Choice(name="Genesis: Part 2", value="Gen2"),
    app_commands.Choice(name="Crystal Isles", value="CrystalIsles"),
    app_commands.Choice(name="Lost Island", value="LostIsland"),
    app_commands.Choice(name="Fjordur", value="Fjordur"),
]


class CreateServerServiceModal(discord.ui.Modal, title="Create ARK Server Service"):
    server_name = discord.ui.TextInput(
        label="Server Name",
        placeholder="e.g., TheIsland, Aberration",
        required=True,
        max_length=50,
    )
    display_name = discord.ui.TextInput(
        label="Display Name",
        placeholder="e.g., The Island, Aberration PvP",
        required=True,
        max_length=100,
    )
    game_port = discord.ui.TextInput(
        label="Game Port",
        placeholder="7777",
        default="7777",
        required=True,
        max_length=5,
    )
    query_port = discord.ui.TextInput(
        label="Query Port",
        placeholder="27015",
        default="27015",
        required=True,
        max_length=5,
    )
    rcon_port = discord.ui.TextInput(
        label="RCON Port",
        placeholder="27020",
        default="27020",
        required=True,
        max_length=5,
    )

    def __init__(self, cog, agent_id: str, map_name: str, server_path: str, steamcmd_path: str, max_players: int, rcon_password: str):
        super().__init__()
        self.cog = cog
        self.agent_id = agent_id
        self.map_name = map_name
        self.server_path = server_path
        self.steamcmd_path = steamcmd_path
        self.max_players = max_players
        self.rcon_password = rcon_password

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            agent_manager = self.cog.agent_manager

            result = await agent_manager.create_server_service(
                agent_id=self.agent_id,
                server_name=str(self.server_name),
                display_name=str(self.display_name),
                map_name=self.map_name,
                game_port=int(str(self.game_port)),
                query_port=int(str(self.query_port)),
                rcon_port=int(str(self.rcon_port)),
                rcon_password=self.rcon_password,
                max_players=self.max_players,
                server_path=self.server_path,
                steamcmd_path=self.steamcmd_path,
            )

            if result.get("error"):
                await interaction.followup.send(
                    f"❌ Failed to create service: {result['error']}", ephemeral=True
                )
                return

            service_name = result.get("data", {}).get("service_name", "Unknown")
            await interaction.followup.send(
                f"✅ ARK server service created!\n"
                f"**Server:** {self.server_name}\n"
                f"**Service:** {service_name}\n"
                f"**Map:** {self.map_name}\n\n"
                f"Use `/startservice {service_name}` to start the server.",
                ephemeral=True,
            )

        except ValueError as e:
            await interaction.followup.send(f"❌ Invalid input: {e}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating server service: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class UpdateServerConfigModal(discord.ui.Modal, title="Update Server Configuration"):
    display_name = discord.ui.TextInput(
        label="Display Name",
        placeholder="Leave blank to keep current",
        required=False,
        max_length=100,
    )
    max_players = discord.ui.TextInput(
        label="Max Players",
        placeholder="Leave blank to keep current",
        required=False,
        max_length=4,
    )
    mods = discord.ui.TextInput(
        label="Mods (comma-separated IDs)",
        placeholder="Leave blank to keep current",
        required=False,
        max_length=500,
    )
    cluster_id = discord.ui.TextInput(
        label="Cluster ID",
        placeholder="Leave blank to keep current",
        required=False,
        max_length=100,
    )

    def __init__(self, cog, agent_id: str, server_name: str, current_config: dict):
        super().__init__()
        self.cog = cog
        self.agent_id = agent_id
        self.server_name = server_name
        self.current_config = current_config

        self.display_name.default = current_config.get("display_name", "")
        self.max_players.default = str(current_config.get("max_players", ""))
        self.mods.default = current_config.get("mods", "")
        self.cluster_id.default = current_config.get("cluster_id", "")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        updates = {}
        if str(self.display_name):
            updates["display_name"] = str(self.display_name)
        if str(self.max_players):
            try:
                updates["max_players"] = int(str(self.max_players))
            except ValueError:
                await interaction.followup.send("❌ Max Players must be a number", ephemeral=True)
                return
        if str(self.mods):
            updates["mods"] = str(self.mods)
        if str(self.cluster_id):
            updates["cluster_id"] = str(self.cluster_id)

        if not updates:
            await interaction.followup.send("No changes provided.", ephemeral=True)
            return

        try:
            agent_manager = self.cog.agent_manager
            result = await agent_manager.update_server_config(
                agent_id=self.agent_id,
                server_name=self.server_name,
                **updates,
            )

            if result.get("error"):
                await interaction.followup.send(
                    f"❌ Failed to update config: {result['error']}", ephemeral=True
                )
                return

            await interaction.followup.send(
                f"✅ Configuration updated for **{self.server_name}**\n"
                f"Changes: {', '.join(updates.keys())}",
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"Error updating server config: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


class DeleteServerConfirmView(discord.ui.View):
    def __init__(self, cog, agent_id: str, server_name: str, service_name: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.agent_id = agent_id
        self.server_name = server_name
        self.service_name = service_name

    @discord.ui.button(label="Delete Service", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        try:
            agent_manager = self.cog.agent_manager
            result = await agent_manager.delete_server_service(
                agent_id=self.agent_id,
                server_name=self.server_name,
                service_name=self.service_name,
            )

            if result.get("error"):
                await interaction.followup.send(
                    f"❌ Failed to delete service: {result['error']}", ephemeral=True
                )
                return

            await interaction.followup.send(
                f"✅ Service **{self.service_name}** deleted successfully.",
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"Error deleting server service: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Deletion cancelled.", view=None
        )


class ServerServiceCog(commands.Cog):
    """Discord commands for ARK server service management (Phase 16)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.agent_manager = getattr(bot, "agent_manager", None)
        logger.info("ServerService cog initialized")

    @property
    def agent_manager(self):
        return getattr(self.bot, "agent_manager", None)

    @agent_manager.setter
    def agent_manager(self, value):
        self.bot.agent_manager = value

    async def get_agent_for_guild(self, guild_id: int) -> Optional[str]:
        """Get connected agent_id for a guild."""
        if not self.agent_manager:
            return None
        return await self.agent_manager.get_connected_agent_for_guild(guild_id)

    @app_commands.command(
        name="createservice",
        description="Create a new ARK server Windows service (Phase 16)"
    )
    @app_commands.describe(
        map_name="Select the ARK map",
        server_path="Full path to server directory (e.g., D:\\ARK\\Servers\\Island)",
        steamcmd_path="Full path to SteamCMD directory (e.g., D:\\SteamCMD)",
        rcon_password="RCON password for the server",
        max_players="Maximum player count (default: 70)",
    )
    @app_commands.choices(map_name=MAP_CHOICES)
    @app_commands.checks.has_permissions(administrator=True)
    async def create_service(
        self,
        interaction: discord.Interaction,
        map_name: str,
        server_path: str,
        steamcmd_path: str,
        rcon_password: str,
        max_players: app_commands.Range[int, 1, 255] = 70,
    ):
        """Create a new ARK server Windows service."""
        agent_id = await self.get_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.response.send_message(
                "❌ No remote agent connected. Use `/register_agent` first.",
                ephemeral=True,
            )
            return

        modal = CreateServerServiceModal(
            cog=self,
            agent_id=agent_id,
            map_name=map_name,
            server_path=server_path,
            steamcmd_path=steamcmd_path,
            max_players=max_players,
            rcon_password=rcon_password,
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="updateservice",
        description="Update an ARK server service configuration"
    )
    @app_commands.describe(server_name="Server name to update")
    @app_commands.checks.has_permissions(administrator=True)
    async def update_service(self, interaction: discord.Interaction, server_name: str):
        """Update an existing ARK server configuration."""
        agent_id = await self.get_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.response.send_message(
                "❌ No remote agent connected.", ephemeral=True
            )
            return

        modal = UpdateServerConfigModal(
            cog=self,
            agent_id=agent_id,
            server_name=server_name,
            current_config={},
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="deleteservice",
        description="Delete an ARK server Windows service"
    )
    @app_commands.describe(server_name="Server name to delete")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_service(self, interaction: discord.Interaction, server_name: str):
        """Delete an ARK server service and its configuration."""
        await interaction.response.defer(ephemeral=True)

        agent_id = await self.get_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send(
                "❌ No remote agent connected.", ephemeral=True
            )
            return

        service_name = f"PhoenixARK_{server_name}"

        embed = discord.Embed(
            title="⚠️ Confirm Server Deletion",
            description=f"You are about to delete:\n"
            f"**Server:** {server_name}\n"
            f"**Service:** {service_name}\n\n"
            f"This will remove the Windows service and registry configuration.\n"
            f"The server files will NOT be deleted.",
            color=discord.Color.orange(),
        )

        view = DeleteServerConfirmView(
            cog=self,
            agent_id=agent_id,
            server_name=server_name,
            service_name=service_name,
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="serviceconfig",
        description="View ARK server service configuration from registry"
    )
    @app_commands.describe(server_name="Server name to view")
    @app_commands.checks.has_permissions(administrator=True)
    async def view_service_config(self, interaction: discord.Interaction, server_name: str):
        """View an ARK server's registry configuration."""
        await interaction.response.defer(ephemeral=True)

        agent_id = await self.get_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send(
                "❌ No remote agent connected.", ephemeral=True
            )
            return

        try:
            result = await self.agent_manager.read_server_config(agent_id, server_name)

            if result.get("error"):
                await interaction.followup.send(
                    f"❌ Server not found: {server_name}", ephemeral=True
                )
                return

            config = result.get("data", {})

            embed = discord.Embed(
                title=f"📋 Server Configuration: {server_name}",
                color=discord.Color.blue(),
            )

            embed.add_field(name="Display Name", value=config.get("display_name", "N/A"), inline=True)
            embed.add_field(name="Map", value=config.get("map_name", "N/A"), inline=True)
            embed.add_field(name="Max Players", value=config.get("max_players", "N/A"), inline=True)

            embed.add_field(name="Game Port", value=config.get("game_port", "N/A"), inline=True)
            embed.add_field(name="Query Port", value=config.get("query_port", "N/A"), inline=True)
            embed.add_field(name="RCON Port", value=config.get("rcon_port", "N/A"), inline=True)

            embed.add_field(name="Server Path", value=config.get("server_path", "N/A"), inline=False)
            embed.add_field(name="SteamCMD Path", value=config.get("steamcmd_path", "N/A"), inline=False)

            mods = config.get("mods", "")
            embed.add_field(name="Mods", value=mods if mods else "None", inline=False)

            cluster_id = config.get("cluster_id", "")
            if cluster_id:
                embed.add_field(name="Cluster ID", value=cluster_id, inline=True)
                embed.add_field(name="Cluster Path", value=config.get("cluster_path", "N/A"), inline=True)

            embed.set_footer(text=f"Service: {config.get('service_name', 'N/A')}")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error reading server config: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(
        name="listservices",
        description="List all ARK server services on the remote agent"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def list_services(self, interaction: discord.Interaction):
        """List all PhoenixARK server services."""
        await interaction.response.defer(ephemeral=True)

        agent_id = await self.get_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send(
                "❌ No remote agent connected.", ephemeral=True
            )
            return

        try:
            result = await self.agent_manager.list_server_services(agent_id)

            if result.get("error"):
                await interaction.followup.send(
                    f"❌ Error: {result['error']}", ephemeral=True
                )
                return

            services = result.get("data", [])

            if not services:
                await interaction.followup.send(
                    "No ARK server services found.", ephemeral=True
                )
                return

            embed = discord.Embed(
                title="🖥️ ARK Server Services",
                description=f"Found {len(services)} service(s)",
                color=discord.Color.blue(),
            )

            for svc in services[:10]:
                name = svc.get("server_name", "Unknown")
                service = svc.get("service_name", "Unknown")
                status = svc.get("status", "Unknown")
                status_emoji = "🟢" if status == "Running" else "🔴"
                embed.add_field(
                    name=f"{status_emoji} {name}",
                    value=f"Service: `{service}`\nStatus: {status}",
                    inline=False,
                )

            if len(services) > 10:
                embed.set_footer(text=f"Showing 10 of {len(services)} services")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing services: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(
        name="startservice",
        description="Start an ARK server service"
    )
    @app_commands.describe(service_name="Service name (e.g., PhoenixARK_TheIsland)")
    @app_commands.checks.has_permissions(administrator=True)
    async def start_service(self, interaction: discord.Interaction, service_name: str):
        """Start an ARK server service."""
        await interaction.response.defer(ephemeral=True)

        agent_id = await self.get_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send(
                "❌ No remote agent connected.", ephemeral=True
            )
            return

        try:
            result = await self.agent_manager.start_ark_service(agent_id, service_name)

            if result.get("error"):
                await interaction.followup.send(
                    f"❌ Failed to start service: {result['error']}", ephemeral=True
                )
                return

            await interaction.followup.send(
                f"✅ Service **{service_name}** started successfully.",
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"Error starting service: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(
        name="stopservice",
        description="Stop an ARK server service"
    )
    @app_commands.describe(service_name="Service name (e.g., PhoenixARK_TheIsland)")
    @app_commands.checks.has_permissions(administrator=True)
    async def stop_service(self, interaction: discord.Interaction, service_name: str):
        """Stop an ARK server service."""
        await interaction.response.defer(ephemeral=True)

        agent_id = await self.get_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send(
                "❌ No remote agent connected.", ephemeral=True
            )
            return

        try:
            result = await self.agent_manager.stop_ark_service(agent_id, service_name)

            if result.get("error"):
                await interaction.followup.send(
                    f"❌ Failed to stop service: {result['error']}", ephemeral=True
                )
                return

            await interaction.followup.send(
                f"✅ Service **{service_name}** stopped successfully.",
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"Error stopping service: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(
        name="restartservice",
        description="Restart an ARK server service"
    )
    @app_commands.describe(service_name="Service name (e.g., PhoenixARK_TheIsland)")
    @app_commands.checks.has_permissions(administrator=True)
    async def restart_service(self, interaction: discord.Interaction, service_name: str):
        """Restart an ARK server service."""
        await interaction.response.defer(ephemeral=True)

        agent_id = await self.get_agent_for_guild(interaction.guild_id)
        if not agent_id:
            await interaction.followup.send(
                "❌ No remote agent connected.", ephemeral=True
            )
            return

        try:
            result = await self.agent_manager.restart_ark_service(agent_id, service_name)

            if result.get("error"):
                await interaction.followup.send(
                    f"❌ Failed to restart service: {result['error']}", ephemeral=True
                )
                return

            await interaction.followup.send(
                f"✅ Service **{service_name}** restarted successfully.",
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"Error restarting service: {e}")
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerServiceCog(bot))
