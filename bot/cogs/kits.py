"""
Player Kit Commands Cog.
Provides /kit list and /kit claim commands for players.
"""

import logging
from typing import Optional, List
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from bot.database import kit_db, players_db, server_config_db, shop_db
from bot.utils.subscription_checker import check_feature

logger = logging.getLogger("KitsCog")

QUALITY_NAMES = {
    1: "Primitive",
    2: "Ramshackle",
    4: "Apprentice",
    6: "Journeyman",
    8: "Mastercraft",
    10: "Ascendant",
}


class KitsCog(commands.Cog):
    """Player kit commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------------------------
    # Kit List Command
    # ---------------------------------------------------------------------------

    @app_commands.command(name="kit", description="🎁 View and claim starter kits")
    async def kit_command(self, interaction: discord.Interaction):
        """Main kit command - shows available kits."""
        if not await check_feature(interaction, "kits"):
            return
        
        await interaction.response.defer(ephemeral=True)
        
        kits = await kit_db.get_all_kits(interaction.guild.id, enabled_only=True)
        
        if not kits:
            await interaction.followup.send(
                "📦 No kits are currently available on this server.",
                ephemeral=True,
            )
            return
        
        # Build kit list embed
        embed = await self._build_kit_list_embed(interaction, kits)
        view = KitListView(self, kits)
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def _build_kit_list_embed(
        self, interaction: discord.Interaction, kits: List[dict]
    ) -> discord.Embed:
        """Build embed showing available kits."""
        embed = discord.Embed(
            title="🎁 Available Kits",
            description="Select a kit below to view details and claim it.",
            color=discord.Color.green(),
        )
        
        # Get player data for requirement checks
        player_data = await players_db.get_player_by_discord_id(
            interaction.guild.id, interaction.user.id
        )
        
        for kit in kits[:10]:  # Show first 10
            # Check if player can claim
            can_claim, reason = await self._check_kit_requirements(
                interaction, kit, player_data
            )
            
            status = "✅" if can_claim else "❌"
            cooldown_text = (
                f"{kit['cooldown_hours']}h cooldown"
                if kit['cooldown_hours'] > 0
                else "One-time only"
            )
            
            requirements = []
            if kit['min_level'] > 0:
                requirements.append(f"Level {kit['min_level']}+")
            if kit['min_playtime_hours'] > 0:
                requirements.append(f"{kit['min_playtime_hours']}h playtime")
            if kit['required_role_id']:
                role = interaction.guild.get_role(kit['required_role_id'])
                if role:
                    requirements.append(f"Role: {role.name}")
            
            req_text = ", ".join(requirements) if requirements else "No requirements"
            
            field_value = f"{status} {kit['description'] or 'No description'}\n"
            field_value += f"**Cooldown:** {cooldown_text}\n"
            field_value += f"**Requirements:** {req_text}"
            
            if not can_claim and reason:
                field_value += f"\n⚠️ {reason}"
            
            embed.add_field(
                name=kit['kit_name'],
                value=field_value,
                inline=False,
            )
        
        embed.set_footer(text="Use the dropdown below to claim a kit")
        return embed

    async def _check_kit_requirements(
        self,
        interaction: discord.Interaction,
        kit: dict,
        player_data: Optional[dict],
    ) -> tuple[bool, Optional[str]]:
        """
        Check if player meets all requirements to claim a kit.
        Returns (can_claim, reason_if_not).
        
        Admins bypass cooldown restrictions for testing purposes.
        """
        # Check if player has linked account
        if not player_data or not player_data.get("specimen_id"):
            return False, "You must link your account first. Use `/link`"
        
        # Check if user is admin (bypass cooldowns for testing)
        is_admin = interaction.user.guild_permissions.administrator
        
        # Check cooldown (skip for admins)
        if not is_admin:
            can_claim_cooldown, next_claim_time = await kit_db.can_claim_kit(
                interaction.guild.id, kit['kit_id'], interaction.user.id
            )
            if not can_claim_cooldown:
                if next_claim_time:
                    next_time = datetime.fromisoformat(next_claim_time)
                    delta = next_time - datetime.utcnow()
                    hours = int(delta.total_seconds() / 3600)
                    return False, f"On cooldown. Available in {hours}h"
                else:
                    return False, "Already claimed (one-time kit)"
        
        # Check level requirement
        if kit['min_level'] > 0:
            player_level = player_data.get('level', 0)
            if player_level < kit['min_level']:
                return False, f"Requires level {kit['min_level']} (you are {player_level})"
        
        # Check playtime requirement
        if kit['min_playtime_hours'] > 0:
            # Calculate playtime from session history
            playtime_hours = await self._calculate_playtime(
                interaction.guild.id, interaction.user.id
            )
            if playtime_hours < kit['min_playtime_hours']:
                return False, f"Requires {kit['min_playtime_hours']}h playtime (you have {playtime_hours:.1f}h)"
        
        # Check role requirement
        if kit['required_role_id']:
            member = interaction.guild.get_member(interaction.user.id)
            if not member or kit['required_role_id'] not in [r.id for r in member.roles]:
                role = interaction.guild.get_role(kit['required_role_id'])
                role_name = role.name if role else "required role"
                return False, f"Requires {role_name}"
        
        return True, None

    async def _calculate_playtime(self, guild_id: int, user_id: int) -> float:
        """Calculate total playtime in hours from session history."""
        # Get player's EOS ID
        player_data = await players_db.get_player_by_discord_id(guild_id, user_id)
        if not player_data or not player_data.get("eos_id"):
            return 0.0
        
        eos_id = player_data["eos_id"]
        
        # Get all completed sessions for this player
        sessions = await players_db.get_player_session_history(guild_id, eos_id, limit=1000)
        
        total_seconds = 0.0
        for session in sessions:
            # Only count completed sessions (has leave_time)
            if session.get("leave_time") and session.get("join_time"):
                try:
                    join_time = datetime.fromisoformat(session["join_time"])
                    leave_time = datetime.fromisoformat(session["leave_time"])
                    duration = (leave_time - join_time).total_seconds()
                    if duration > 0:
                        total_seconds += duration
                except Exception as e:
                    logger.warning(f"Error calculating session duration: {e}")
                    continue
        
        # Convert to hours
        total_hours = total_seconds / 3600.0
        return total_hours

    async def _deliver_kit_items(
        self,
        interaction: discord.Interaction,
        items: List[dict],
        kit_name: str,
    ) -> tuple[bool, str]:
        """
        Queue kit items for delivery using shop's pending delivery system.
        If player is online, items deliver instantly via shop's delivery monitor.
        If offline, items queue until player comes online.
        Returns (success, message).
        """
        if not items:
            return False, "Kit has no items configured."
        
        # Get player data
        player_data = await players_db.get_player_by_discord_id(
            interaction.guild.id, interaction.user.id
        )
        if not player_data:
            return False, "❌ Your ARK account is not linked. Use `/link` first."
        
        eos_id = player_data.get("eos_id")
        if not eos_id:
            return False, "❌ No EOS ID found. Please re-link your account."
        
        # Get server - use last_seen_server or last_server as fallback
        server_name = player_data.get("last_seen_server") or player_data.get("last_server") or "unknown"
        
        # Queue all items for delivery
        queued_count = 0
        for item in items:
            try:
                await shop_db.add_pending_delivery(
                    guild_id=interaction.guild.id,
                    discord_user_id=interaction.user.id,
                    eos_id=eos_id,
                    server_name=server_name,
                    item_blueprint=item['item_blueprint'],
                    quantity=item['quantity'],
                    quality=item['quality'],
                    force_blueprint=False,
                )
                queued_count += 1
                logger.info(
                    "Queued kit item for %s: %s x%s Q%s",
                    eos_id[:12],
                    item['item_blueprint'],
                    item['quantity'],
                    item['quality'],
                )
            except Exception as e:
                logger.error("Failed to queue kit item: %s", e)
        
        if queued_count == 0:
            return False, "❌ Failed to queue items for delivery."
        
        # Return success - caller will handle messaging
        return True, server_name


# ---------------------------------------------------------------------------
# Kit List View
# ---------------------------------------------------------------------------

class KitListView(discord.ui.View):
    """View for selecting and claiming kits."""

    def __init__(self, cog: KitsCog, kits: List[dict]):
        super().__init__(timeout=300)
        self.cog = cog
        self.kits = kits
        
        # Add kit selection dropdown
        options = []
        for kit in kits[:25]:  # Discord limit
            cooldown = (
                f"{kit['cooldown_hours']}h"
                if kit['cooldown_hours'] > 0
                else "One-time"
            )
            options.append(
                discord.SelectOption(
                    label=kit['kit_name'],
                    description=f"{cooldown} - {kit['description'][:50] if kit['description'] else 'No description'}",
                    value=str(kit['kit_id']),
                )
            )
        
        select = discord.ui.Select(
            placeholder="Choose a kit to view/claim...",
            options=options,
            custom_id="kit_select",
        )
        select.callback = self.kit_selected
        self.add_item(select)

    async def kit_selected(self, interaction: discord.Interaction):
        """Handle kit selection."""
        kit_id = int(interaction.data["values"][0])
        kit = await kit_db.get_kit_by_id(kit_id)
        
        if not kit:
            await interaction.response.send_message(
                "❌ Kit not found.",
                ephemeral=True,
            )
            return
        
        # Get kit items
        items = await kit_db.get_kit_items(kit_id)
        
        # Build detailed embed
        embed = await self._build_kit_detail_embed(interaction, kit, items)
        
        # Check if player can claim
        player_data = await players_db.get_player_by_discord_id(
            interaction.guild.id, interaction.user.id
        )
        can_claim, reason = await self.cog._check_kit_requirements(
            interaction, kit, player_data
        )
        
        if can_claim:
            view = ClaimKitView(self.cog, kit, items)
            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )

    async def _build_kit_detail_embed(
        self, interaction: discord.Interaction, kit: dict, items: List[dict]
    ) -> discord.Embed:
        """Build detailed kit embed."""
        embed = discord.Embed(
            title=f"🎁 {kit['kit_name']}",
            description=kit['description'] or "No description",
            color=discord.Color.blue(),
        )
        
        # Cooldown info
        cooldown_text = (
            f"{kit['cooldown_hours']} hours"
            if kit['cooldown_hours'] > 0
            else "One-time only"
        )
        embed.add_field(name="Cooldown", value=cooldown_text, inline=True)
        
        # Requirements
        requirements = []
        if kit['min_level'] > 0:
            requirements.append(f"Level {kit['min_level']}+")
        if kit['min_playtime_hours'] > 0:
            requirements.append(f"{kit['min_playtime_hours']}h playtime")
        if kit['required_role_id']:
            role = interaction.guild.get_role(kit['required_role_id'])
            if role:
                requirements.append(f"Role: {role.name}")
        
        req_text = "\n".join(requirements) if requirements else "None"
        embed.add_field(name="Requirements", value=req_text, inline=True)
        
        # Items
        if items:
            item_list = []
            for item in items[:20]:  # Show first 20
                quality_name = QUALITY_NAMES.get(item['quality'], "Unknown")
                bp = item['item_blueprint']
                if "/" in bp:
                    bp = bp.split("/")[-1].replace("'", "")
                item_list.append(f"• **{bp}** x{item['quantity']} ({quality_name})")
            
            embed.add_field(
                name=f"Items ({len(items)})",
                value="\n".join(item_list),
                inline=False,
            )
        else:
            embed.add_field(
                name="Items",
                value="No items configured",
                inline=False,
            )
        
        return embed


# ---------------------------------------------------------------------------
# Claim Kit View
# ---------------------------------------------------------------------------

class ClaimKitView(discord.ui.View):
    """View for claiming a kit."""

    def __init__(self, cog: KitsCog, kit: dict, items: List[dict]):
        super().__init__(timeout=60)
        self.cog = cog
        self.kit = kit
        self.items = items

    @discord.ui.button(label="Claim Kit", style=discord.ButtonStyle.green, emoji="🎁")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Claim the kit."""
        await interaction.response.defer(ephemeral=True)
        
        # Double-check requirements
        player_data = await players_db.get_player_by_discord_id(
            interaction.guild.id, interaction.user.id
        )
        can_claim, reason = await self.cog._check_kit_requirements(
            interaction, self.kit, player_data
        )
        
        if not can_claim:
            await interaction.followup.send(
                f"❌ Cannot claim kit: {reason}",
                ephemeral=True,
            )
            return
        
        # Queue items for delivery
        success, server_name = await self.cog._deliver_kit_items(
            interaction, self.items, self.kit['kit_name']
        )
        
        if success:
            # Record claim
            await kit_db.record_claim(
                interaction.guild.id,
                self.kit['kit_id'],
                interaction.user.id,
                self.kit['cooldown_hours'],
            )
            
            # Log to admin channel
            await self._log_claim(interaction)
            
            # Build description based on item count
            if len(self.items) == 1:
                item = self.items[0]
                quality_name = QUALITY_NAMES.get(item['quality'], 'Primitive')
                # Shorten blueprint for display
                bp = item['item_blueprint']
                if "/" in bp:
                    bp = bp.split("/")[-1].replace("'", "")
                desc = (
                    f"**{self.kit['kit_name']}** claimed!\n"
                    f"{bp} x{item['quantity']} ({quality_name}) will be delivered next time you're online on an ARK server."
                )
            else:
                desc = (
                    f"**{self.kit['kit_name']}** claimed!\n"
                    f"All {len(self.items)} items will be delivered next time you're online on an ARK server."
                )
            
            # Send response embed
            embed = discord.Embed(
                title="🕐 Kit Queued for Delivery",
                description=desc,
                color=discord.Color.yellow(),
            )
            embed.set_footer(text="Auto-delivers ~2 min after login")
            await interaction.followup.send(embed=embed, ephemeral=True)
            
            # Send DM notification
            try:
                dm_embed = discord.Embed(
                    title="🕐 Kit Queued for Delivery",
                    description=desc,
                    color=discord.Color.yellow(),
                )
                dm_embed.set_footer(text="Auto-delivers ~2 min after login")
                await interaction.user.send(embed=dm_embed)
            except Exception:
                pass
        else:
            await interaction.followup.send(
                f"❌ Failed to claim kit: {server_name}",
                ephemeral=True,
            )

    async def _log_claim(self, interaction: discord.Interaction):
        """Log kit claim to admin channel."""
        try:
            config = await server_config_db.get_server_config(interaction.guild.id)
            if not config:
                return
            channel_id = config.get("admin_log_channel_id")
            if not channel_id:
                return
            channel = self.cog.bot.get_channel(int(channel_id))
            if not channel:
                return
            
            await channel.send(
                f"🎁 **Kit Claimed**: {self.kit['kit_name']} by {interaction.user.mention}"
            )
        except Exception as e:
            logger.error("Failed to log kit claim: %s", e)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel claiming."""
        await interaction.response.edit_message(
            content="❌ Claim cancelled.",
            view=None,
        )


async def setup(bot: commands.Bot):
    """Load the cog."""
    await bot.add_cog(KitsCog(bot))
