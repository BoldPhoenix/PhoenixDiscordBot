"""
Starter kits cog for ARK servers.
Allows admins to create kits that players can claim.
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
import aiosqlite
from typing import Optional, List, Dict
from pathlib import Path
from datetime import datetime, timedelta

from bot.utils.config import Config
from bot.rcon.client import RCONManager
from bot.database import players_db
from bot.utils.permissions import require_verified_user
from bot.utils.player_linking import require_linked_player

logger = logging.getLogger("StarterKits")


class StarterKits(commands.Cog):
    """Starter kits system for new and returning players."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rcon_manager = RCONManager(Config.ARK_SERVERS)

    async def init_kits_db(self):
        """Initialize kits database tables."""
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS kits (
                    kit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    items TEXT NOT NULL,
                    cooldown_hours INTEGER DEFAULT 0,
                    max_claims INTEGER DEFAULT 0,
                    enabled BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS kit_claims (
                    claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kit_id INTEGER NOT NULL,
                    discord_id INTEGER NOT NULL,
                    server_name TEXT NOT NULL,
                    claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (kit_id) REFERENCES kits(kit_id)
                )
            """
            )

            await db.commit()
            logger.info("Kits tables initialized")

    async def can_claim_kit(self, discord_id: int, kit_id: int) -> tuple[bool, str]:
        """Check if user can claim a kit."""
        db_path = Path(Config.DATABASE_PATH)

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # Get kit info
            async with db.execute("SELECT * FROM kits WHERE kit_id = ?", (kit_id,)) as cursor:
                kit = await cursor.fetchone()

            if not kit or not kit["enabled"]:
                return False, "Kit not found or disabled"

            # Check max claims
            if kit["max_claims"] > 0:
                async with db.execute(
                    "SELECT COUNT(*) as count FROM kit_claims WHERE kit_id = ? AND discord_id = ?",
                    (kit_id, discord_id),
                ) as cursor:
                    result = await cursor.fetchone()
                    if result["count"] >= kit["max_claims"]:
                        return False, f"Maximum claims ({kit['max_claims']}) reached for this kit"

            # Check cooldown
            if kit["cooldown_hours"] > 0:
                async with db.execute(
                    "SELECT claimed_at FROM kit_claims WHERE kit_id = ? AND discord_id = ? ORDER BY claimed_at DESC LIMIT 1",
                    (kit_id, discord_id),
                ) as cursor:
                    last_claim = await cursor.fetchone()

                if last_claim:
                    last_claim_time = datetime.fromisoformat(last_claim["claimed_at"])
                    cooldown_end = last_claim_time + timedelta(hours=kit["cooldown_hours"])

                    if datetime.now() < cooldown_end:
                        time_left = cooldown_end - datetime.now()
                        hours = int(time_left.total_seconds() // 3600)
                        minutes = int((time_left.total_seconds() % 3600) // 60)
                        return False, f"Cooldown active. Try again in {hours}h {minutes}m"

            return True, "OK"

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize kits database on startup."""
        await self.init_kits_db()

    @app_commands.command(name="kit", description="Claim a starter kit")
    @app_commands.describe(
        kit_name="Name of the kit to claim", server="Server to deliver the kit on"
    )
    async def claim_kit(self, interaction: discord.Interaction, kit_name: str, server: str):
        """Claim a starter kit."""
        # Check if user is verified
        if not await require_verified_user(interaction):
            return

        # Check if player is linked (with helpful message)
        is_linked, player = await require_linked_player(interaction, defer=True)
        if not is_linked:
            return

        # Get kit
        db_path = Path(Config.DATABASE_PATH)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM kits WHERE name = ?", (kit_name,)) as cursor:
                kit = await cursor.fetchone()

        if not kit:
            await interaction.followup.send(f" Kit '{kit_name}' not found.")
            return

        # Check if can claim
        can_claim, message = await self.can_claim_kit(interaction.user.id, kit["kit_id"])
        if not can_claim:
            await interaction.followup.send(f" {message}")
            return

        # Get RCON client
        client = self.rcon_manager.get_client(server)
        if not client:
            await interaction.followup.send(f" Server '{server}' not found.")
            return

        # Try to deliver
        import json

        items = json.loads(kit["items"])

        player_id = await client.resolve_player_id_by_eos(player["eos_id"])

        if player_id:
            # Player online, deliver immediately
            success_count = 0
            for item in items:
                blueprint = item["blueprint"]
                quantity = item.get("quantity", 1)
                quality = item.get("quality", 0)

                if await client.give_item_to_player_by_eos(
                    player["eos_id"], blueprint, quantity, quality
                ):
                    success_count += 1

            if success_count > 0:
                # Record claim
                async with aiosqlite.connect(db_path) as db:
                    await db.execute(
                        "INSERT INTO kit_claims (kit_id, discord_id, server_name) VALUES (?, ?, ?)",
                        (kit["kit_id"], interaction.user.id, server),
                    )
                    await db.commit()

                await interaction.followup.send(
                    f" **{kit_name}** kit delivered!\n"
                    f"Delivered {success_count}/{len(items)} items to your inventory on **{server}**"
                )
            else:
                await interaction.followup.send(" Failed to deliver kit items.")
        else:
            # Queue all items
            for item in items:
                await players_db.queue_delivery(
                    interaction.user.id,
                    server,
                    item["blueprint"],
                    item.get("quantity", 1),
                    item.get("quality", 0),
                )

            await interaction.followup.send(
                f" You're offline.\n"
                f"**{kit_name}** kit has been queued for delivery when you join **{server}**"
            )

    @app_commands.command(name="listkits", description="List available starter kits")
    async def list_kits(self, interaction: discord.Interaction):
        """List all available kits."""
        db_path = Path(Config.DATABASE_PATH)

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM kits WHERE enabled = 1 ORDER BY name") as cursor:
                kits = await cursor.fetchall()

        if not kits:
            await interaction.response.send_message("No kits available.", ephemeral=True)
            return

        embed = discord.Embed(title=" Available Starter Kits", color=discord.Color.gold())

        for kit in kits:
            # Get user's claim info
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                    "SELECT COUNT(*) as count FROM kit_claims WHERE kit_id = ? AND discord_id = ?",
                    (kit["kit_id"], interaction.user.id),
                ) as cursor:
                    result = await cursor.fetchone()
                    claims = result[0] if result else 0

            value = f"{kit['description'] or 'No description'}\n"

            if kit["cooldown_hours"] > 0:
                value += f" Cooldown: {kit['cooldown_hours']} hours\n"

            if kit["max_claims"] > 0:
                value += f" Max claims: {kit['max_claims']} (You've claimed: {claims})\n"

            can_claim, msg = await self.can_claim_kit(interaction.user.id, kit["kit_id"])
            value += f"**Status:** {' Available' if can_claim else f' {msg}'}"

            embed.add_field(name=kit["name"], value=value, inline=False)

        embed.set_footer(text="Use /kit <kit_name> <server> to claim a kit")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="createkit", description="[ADMIN] Create a new starter kit")
    @app_commands.describe(
        name="Kit name",
        description="Kit description",
        items='JSON array of items [{"blueprint": "...", "quantity": 1, "quality": 0}]',
        cooldown_hours="Hours before kit can be claimed again (0 = unlimited)",
        max_claims="Maximum times kit can be claimed (0 = unlimited)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def create_kit(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str,
        items: str,
        cooldown_hours: int = 0,
        max_claims: int = 0,
    ):
        """Create a new starter kit."""
        # Validate JSON
        try:
            import json

            items_list = json.loads(items)
            if not isinstance(items_list, list):
                raise ValueError("Items must be a JSON array")
        except Exception as e:
            await interaction.response.send_message(f" Invalid items JSON: {e}", ephemeral=True)
            return

        db_path = Path(Config.DATABASE_PATH)

        try:
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    """
                    INSERT INTO kits (name, description, items, cooldown_hours, max_claims)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (name, description, items, cooldown_hours, max_claims),
                )
                await db.commit()

            await interaction.response.send_message(
                f" Created kit: **{name}**\n"
                f"Items: {len(items_list)}\n"
                f"Cooldown: {cooldown_hours}h\n"
                f"Max claims: {max_claims if max_claims > 0 else 'Unlimited'}",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f" Failed to create kit: {e}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(StarterKits(bot))
