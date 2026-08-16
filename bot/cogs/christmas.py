"""
bot/cogs/christmas.py
The '12 Days of ARKmas' Event Module (Final Winter Edition).
Features: Level 450 Tamed Dinos + Saddles, Mod Items, and Full Sets.
"""

import discord
import asyncio
import aiosqlite
import logging
import datetime
from discord.ext import commands, tasks
from discord import app_commands
from pathlib import Path

from bot.utils.economy import update_balance
from bot.database import players_db


# ===========================
# ðŸ“ CUSTOM MOD PATHS
# ===========================
# PASTE YOUR MOD PATHS HERE:
PHOENIX_TRANQ_BP = "Blueprint'/RiseofPhoenix/Weapons/Tranq/PrimalItemstruct_PhoenixDart.PrimalItemstruct_PhoenixDart'"
PHOENIX_SHOTGUN_BP = "Blueprint'/Game/PrimalEarth/CoreBlueprints/Weapons/PrimalItem_WeaponMachinedShotgun.PrimalItem_WeaponMachinedShotgun'"
PHOENIX_SHOTGUN_SHELLS_BP = "Blueprint'/RiseofPhoenix/Weapons/Shotgun/Shell/PrimalItemstruct_FireShell.PrimalItemstruct_FireShell'"
PHOENIX_LONGNECK_BP = (
    "Blueprint'/RiseofPhoenix/Weapons/Longneck/PrimalItemstruct_LONGNECK.PrimalItemstruct_LONGNECK'"
)
PHOENIX_ELEMENT_BP = "Blueprint'/RiseofPhoenix/Items/Element/PrimalItemResource_ElementTransfers_Child.PrimalItemResource_ElementTransfers_Child'"
PHOENIX_ARMOR_BPS = [
    "Blueprint'/Game/Mods/Phoenix/PrimalItemArmor_PhoenixHelmet.PrimalItemArmor_PhoenixHelmet'",
    "Blueprint'/Game/Mods/Phoenix/PrimalItemArmor_PhoenixShirt.PrimalItemArmor_PhoenixShirt'",
    "Blueprint'/Game/Mods/Phoenix/PrimalItemArmor_PhoenixPants.PrimalItemArmor_PhoenixPants'",
    "Blueprint'/Game/Mods/Phoenix/PrimalItemArmor_PhoenixBoots.PrimalItemArmor_PhoenixBoots'",
    "Blueprint'/Game/Mods/Phoenix/PrimalItemArmor_PhoenixGloves.PrimalItemArmor_PhoenixGloves'",
]  # <--- REPLACE THESE

# ===========================
# 🎄 EVENT CONFIGURATION 🎄
# ===========================
# NOTE: Configuration is now managed via /events_config command
# These fallback values are used if events_config.json doesn't exist

EVENT_START_DATE = datetime.date(2025, 12, 13)  # Fallback: Production default
EVENT_CHANNEL_ID = None  # Set via /events_config
VERIFIED_ROLE_ID = 111111111111111111  # Fallback: Production role

# DEBUG MODE: Set via /events_config command
DEBUG_MODE = False  # Fallback: Production mode

DB_PATH = Path("bot_database.sqlite")

# RCON COMMAND TEMPLATES
# ASA-compatible: GiveItemToPlayer with Specimen Implant ID (numeric - NO quotes)
CMD_GIVE_ITEM = 'GiveItemToPlayer {specimen_id} "{blueprint}" {quantity} {quality} 0'
# ASA-compatible: GMSummon (spawns tamed dino at origin - not ideal but works)
CMD_SPAWN_DINO = 'GMSummon "{blueprint}_C" {level}'

REWARDS = {
    # DAY 1: Snow Owl Currency (Universal Coin)
    1: {
        "name": "Universal Coin (Snow Owl Voucher)",
        "type": "item",
        "qty": 1,
        "quality": 0,
        "bp": "Blueprint'/AdminsArsenal/Items/Coins/PrimalItem_UniversalCoin.PrimalItem_UniversalCoin'",
        "desc": "Trade this at the Christmas Shop for a Snow Owl (Lvl 600) with Ascendant Saddle!",
    },
    # DAY 2: 2x Universal Coins
    2: {
        "name": "2x Universal Coins",
        "type": "item",
        "qty": 2,
        "quality": 0,
        "bp": "Blueprint'/AdminsArsenal/Items/Coins/PrimalItem_UniversalCoin.PrimalItem_UniversalCoin'",
        "desc": "Rare currency for special trades!",
    },
    # DAY 3: 30 Fria Curry
    3: {
        "name": "30x Fria Curry",
        "type": "item",
        "qty": 30,
        "quality": 0,
        "bp": "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Consumables/PrimalItemConsumable_Soup_FriaCurry.PrimalItemConsumable_Soup_FriaCurry'",
        "desc": "Stay warm out there!",
    },
    # DAY 4: Phoenix Armor Set (5 Pieces)
    4: {
        "name": "Phoenix Armor Set",
        "type": "item_list",
        "qty": 1,
        "quality": 1200,
        "bps": PHOENIX_ARMOR_BPS,
        "desc": "Complete Phoenix armor set (Helmet, Chest, Legs, Boots, Gloves) - Maximum Quality!",
    },
    # DAY 5: 500 Phoenix Coins
    5: {
        "name": "500 Phoenix Coins",
        "type": "coin",
        "qty": 500,
        "desc": "Currency to spend in the shop!",
    },
    # DAY 6: 60 Phoenix Tranq Darts (Custom Mod)
    6: {
        "name": "60x Phoenix Tranq Darts",
        "type": "item",
        "qty": 60,
        "quality": 0,
        "bp": PHOENIX_TRANQ_BP,
        "desc": "Knock 'em out in style.",
    },
    # DAY 7: 70 Phoenix Shotgun Shells
    7: {
        "name": "70x Phoenix Shotgun Shells",
        "type": "item",
        "qty": 70,
        "quality": 0,
        "bp": PHOENIX_SHOTGUN_SHELLS_BP,
        "desc": "Ammunition for your Phoenix shotgun!",
    },
    # DAY 8: Phoenix Longneck (Max Level)
    8: {
        "name": "Phoenix Longneck (Max Level)",
        "type": "item",
        "qty": 1,
        "quality": 1200,
        "bp": PHOENIX_LONGNECK_BP,
        "desc": "High-powered Phoenix longneck rifle - Maximum Quality!",
    },
    # DAY 9: Yutyrannus Currency (2x Universal Coins)
    9: {
        "name": "2x Universal Coins (Yutyrannus Voucher)",
        "type": "item",
        "qty": 2,
        "quality": 0,
        "bp": "Blueprint'/AdminsArsenal/Items/Coins/PrimalItem_UniversalCoin.PrimalItem_UniversalCoin'",
        "desc": "Trade these at the Christmas Shop for a Mating Pair of Yutyrannus (Lvl 600) with Ascendant Saddles!",
    },
    # DAY 10: 1000 Phoenix Element
    10: {
        "name": "1000x Phoenix Element",
        "type": "item",
        "qty": 1000,
        "quality": 0,
        "bp": PHOENIX_ELEMENT_BP,
        "desc": "Power for your Tek gear.",
    },
    # DAY 11: Phoenix Shotgun (Custom Mod)
    11: {
        "name": "Phoenix Shotgun",
        "type": "item",
        "qty": 1,
        "quality": 1200,
        "bp": PHOENIX_SHOTGUN_BP,
        "desc": "Special event firepower - Maximum Quality!",
    },
    # DAY 12: Managarmr Currency (Universal Coin)
    12: {
        "name": "Universal Coin (Managarmr Voucher)",
        "type": "item",
        "qty": 1,
        "quality": 0,
        "bp": "Blueprint'/AdminsArsenal/Items/Coins/PrimalItem_UniversalCoin.PrimalItem_UniversalCoin'",
        "desc": "Trade this at the Christmas Shop for a Managarmr (Lvl 600) with Ascendant Saddle!",
    },
}

# ===========================
# âš™ï¸ THE CODE
# ===========================


class ChristmasEvent(commands.Cog):
    """12 Days of ARKmas Event - Daily gift claiming with RCON delivery"""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("ChristmasEvent")

        # Runtime config (loaded from events_config cog)
        self.config = {
            "start_date": EVENT_START_DATE,
            "channel_id": EVENT_CHANNEL_ID,
            "role_id": VERIFIED_ROLE_ID,
            "debug_mode": DEBUG_MODE,
        }

    def load_event_config(self):
        """Load configuration from events_config cog if available"""
        events_cog = self.bot.get_cog("EventsConfig")
        if events_cog:
            event_config = events_cog.get_event_config("christmas")
            if event_config:
                self.logger.info("Loading Christmas config from events_config cog")

                # Update runtime config
                if event_config.get("start_date"):
                    self.config["start_date"] = datetime.datetime.strptime(
                        event_config["start_date"], "%Y-%m-%d"
                    ).date()

                if event_config.get("end_date"):
                    self.config["end_date"] = datetime.datetime.strptime(
                        event_config["end_date"], "%Y-%m-%d"
                    ).date()

                if event_config.get("channel_id"):
                    self.config["channel_id"] = event_config["channel_id"]

                if event_config.get("required_role_id"):
                    self.config["role_id"] = event_config["required_role_id"]

                self.config["debug_mode"] = event_config.get("debug_mode", False)

                self.logger.info(f"Christmas config loaded: {self.config}")
        else:
            self.logger.info("EventsConfig cog not found, using fallback values")

    async def cog_load(self):
        """Initialize database table for claims"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS christmas_claims (
                    user_id INTEGER,
                    day INTEGER,
                    year INTEGER,
                    claimed_at TEXT,
                    PRIMARY KEY (user_id, day, year)
                )
            """
            )
            await db.commit()
        self.logger.info("🎄 Christmas Event Module Loaded!")

        # Load configuration from events_config cog
        self.load_event_config()

        # Register persistent views for all possible days (1-12)
        for day in range(1, 13):
            view = ClaimView(self, day)
            self.bot.add_view(view)

        # Start the daily announcement task
        self.daily_task.start()
        self.logger.info("Christmas: Daily task started and persistent views registered")

    async def cog_unload(self):
        """Stop the daily task when cog is unloaded"""
        self.daily_task.cancel()

    async def log_event(self, title: str, description: str, color: discord.Color = None):
        """Log an event to the configured events channel"""
        log_channel_id = self.config.get("events_channel_id")
        if not log_channel_id:
            self.logger.warning("events_channel_id not configured for events")
            return

        log_channel = self.bot.get_channel(log_channel_id)
        if not log_channel:
            self.logger.warning(f"Events channel {log_channel_id} not found!")
            return

        log_channel = self.bot.get_channel(log_channel_id)
        if not log_channel:
            self.logger.warning(f"Events channel {log_channel_id} not found!")
            return

        embed = discord.Embed(
            title=f"🎄 {title}",
            description=description,
            color=color or discord.Color.blue(),
            timestamp=datetime.datetime.now(),
        )

        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Failed to send log message: {e}")

    def get_current_day(self) -> int:
        """Returns the current day of the event (1-12) or None if not active."""
        today = datetime.date.today()

        # Calculate days since start
        delta = (today - self.config["start_date"]).days + 1

        # Check if within event date range
        if self.config.get("end_date"):
            end_date = self.config["end_date"]
            if isinstance(end_date, str):
                end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()
            total_days = (end_date - self.config["start_date"]).days + 1
        else:
            total_days = 12  # Default to 12 days

        self.logger.info(
            f"Christmas: Date check - Today: {today}, Start: {self.config['start_date']}, Delta: {delta}, Total days: {total_days}"
        )

        if 1 <= delta <= total_days:
            self.logger.info(f"Christmas: Event is active, returning day {delta}")
            return delta

        self.logger.warning(
            f"Christmas: Event not active - delta {delta} not in range 1-{total_days}"
        )
        return None

    async def has_claimed(self, user_id: int, day: int) -> bool:
        """Checks if user already claimed this day's gift."""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT * FROM christmas_claims WHERE user_id=? AND day=? AND year=?",
                (user_id, day, datetime.date.today().year),
            )
            return await cursor.fetchone() is not None

    async def mark_claimed(self, user_id: int, day: int):
        """Mark a day's gift as claimed for a user"""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO christmas_claims (user_id, day, year, claimed_at) VALUES (?, ?, ?, ?)",
                (user_id, day, datetime.date.today().year, datetime.datetime.now().isoformat()),
            )
            await db.commit()

    async def get_player_info(self, discord_id: int) -> dict:
        """
        Get player's Specimen ID and online status.
        Uses the existing players_db to lookup linked accounts.
        Returns dict with 'specimen_id', 'online', 'server_name'
        """
        # Get linked player from database
        player = await players_db.get_player_by_discord_id(discord_id)

        self.logger.info(
            f"Christmas: get_player_info for Discord ID {discord_id} - Player data: {player}"
        )

        if not player:
            self.logger.warning(f"Christmas: No player found for Discord ID {discord_id}")
            return {"specimen_id": None, "online": False, "server_name": None}

        specimen_id = player.get("specimen_id")

        self.logger.info(f"Christmas: Extracted specimen_id: {specimen_id} from player: {player}")

        if not specimen_id:
            self.logger.warning(f"Christmas: No specimen_id found for Discord ID {discord_id}")
            return {"specimen_id": None, "online": False, "server_name": None}

        # Check if player is online using EOS ID (login detection still uses EOS)
        eos_id = player.get("steam_id") or player.get("eos_id")
        if not eos_id:
            self.logger.warning(
                f"Christmas: No EOS ID found for online check for Discord ID {discord_id}"
            )
            return {"specimen_id": specimen_id, "online": False, "server_name": None}

        # Check if player is currently online on any server
        # Use the server monitor cog to check online status
        monitor_cog = self.bot.get_cog("ServerMonitor")
        if monitor_cog:
            # guild_server_caches: {guild_id: {server_name: status_dict}}
            all_servers = {
                sn: sd
                for guild_cache in monitor_cog.guild_server_caches.values()
                for sn, sd in guild_cache.items()
            }
            self.logger.info(
                f"Christmas: Checking {len(all_servers)} servers for online player {eos_id}"
            )
            for server_name, server_data in all_servers.items():
                players_list = server_data.get("players", [])
                self.logger.info(
                    f"Christmas: Server {server_name} has {len(players_list)} online players"
                )
                for online_player in players_list:
                    player_steam = online_player.get("steam_id")
                    player_eos = online_player.get("eos_id")
                    self.logger.info(
                        f"Christmas: Comparing online player - Steam: {player_steam}, EOS: {player_eos} vs looking for: {eos_id}"
                    )
                    if player_steam == eos_id or player_eos == eos_id:
                        self.logger.info(f"Christmas: MATCH FOUND! Player online on {server_name}")
                        return {
                            "specimen_id": specimen_id,
                            "online": True,
                            "server_name": server_name,
                        }
            self.logger.warning(
                f"Christmas: Player {eos_id} not found in any server's guild_server_caches"
            )
        else:
            self.logger.error("Christmas: ServerMonitorCog not found!")

        return {"specimen_id": specimen_id, "online": False, "server_name": None}

    async def send_rcon_command(self, server_name: str, command: str) -> bool:
        """
        Send RCON command to the specified server with retry logic for 'Keep Alive' responses.
        Returns True if successful, False otherwise.
        """
        try:
            # Use ServerMonitor's RCON manager - access client directly
            monitor_cog = self.bot.get_cog("ServerMonitor")
            if not monitor_cog or not monitor_cog.rcon_manager:
                self.logger.error("Christmas: ServerMonitor cog or RCON manager not found!")
                return False

            # Get the specific RCON client for this server
            if server_name not in monitor_cog.rcon_manager.clients:
                self.logger.error(f"Christmas: No RCON client found for server {server_name}")
                return False

            client = monitor_cog.rcon_manager.clients[server_name]

            # Log the command we're sending
            self.logger.info(f"Christmas: Sending RCON to {server_name}: {command}")

            # Execute command with retry logic for 'Keep Alive' responses
            max_attempts = 3
            for attempt in range(max_attempts):
                result = await client.execute_command(command)

                # Log the result
                self.logger.info(
                    f"Christmas: RCON result from {server_name} (attempt {attempt + 1}/{max_attempts}): {result}"
                )

                # If we got a valid response (not None, not empty, not 'Keep Alive'), return success
                if result and result.strip() != "Keep Alive":
                    return True

                # If we got 'Keep Alive', retry after short delay (except on last attempt)
                if result and result.strip() == "Keep Alive":
                    if attempt < max_attempts - 1:
                        self.logger.debug(f"Christmas: Got 'Keep Alive', retrying in 0.3s...")
                        await asyncio.sleep(0.3)
                        continue
                    else:
                        self.logger.warning(
                            f"Christmas: All {max_attempts} attempts returned 'Keep Alive'"
                        )
                        # Return True anyway since server is responding, just busy
                        return True

                # If we got None or empty, that's a connection failure
                if result is None:
                    self.logger.error(f"Christmas: Connection failure on attempt {attempt + 1}")
                    return False

            return False

        except Exception as e:
            self.logger.error(f"Christmas: RCON command failed: {e}")
            return False

    @tasks.loop(time=datetime.time(hour=9, minute=0))  # Run at 9:00 AM server time
    async def daily_task(self):
        """Daily announcement task - posts the day's gift at 9 AM"""
        day = self.get_current_day()
        if not day:
            return

        channel = self.bot.get_channel(self.config["channel_id"])
        if not channel:
            self.logger.warning(f"Event channel {self.config['channel_id']} not found!")
            return

        reward = REWARDS.get(day)
        if not reward:
            return

        # Prepare mention using config
        mention = "@everyone"
        if self.config.get("role_id"):
            role = channel.guild.get_role(self.config["role_id"])
            mention = role.mention if role else "@everyone"

        # Get daily message from config
        daily_message = self.config.get("daily_message", "Wake up {role}! A new gift is here!")
        daily_message = daily_message.replace("{role}", mention)

        embed = discord.Embed(
            title=f"🎄 Day {day} of ARKmas!", color=discord.Color.from_rgb(200, 230, 255)
        )
        embed.description = (
            f"**On the {day}{self.get_ordinal(day)} day of Christmas, the ARK gave to me...**\n\n"
            f"🎁 **{reward['name']}**\n*{reward['desc']}*"
        )
        embed.set_image(url="https://ark.wiki.gg/images/1/1a/Christmas_Tree.png")
        embed.set_footer(
            text="Click the button below to claim! Items require you to be online in-game."
        )

        view = ClaimView(self, day)
        await channel.send(content=daily_message, embed=embed, view=view)

        # Log to log channel if configured
        await self.log_event(
            f"Day {day} announcement posted", f"Posted daily gift announcement for Day {day}"
        )

    @daily_task.before_loop
    async def before_daily_task(self):
        """Wait until bot is ready before starting the daily task"""
        await self.bot.wait_until_ready()

    def get_ordinal(self, n: int) -> str:
        """Convert number to ordinal string (1st, 2nd, 3rd, etc.)"""
        if 11 <= n <= 13:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

    @app_commands.command(
        name="xmas_announce",
        description="🎅 [ADMIN] Manually trigger today's Christmas announcement",
    )
    @app_commands.default_permissions(administrator=True)
    async def xmas_announce(self, interaction: discord.Interaction):
        """Manually trigger the daily announcement for testing"""
        await interaction.response.defer(ephemeral=True)

        day = self.get_current_day()
        if not day:
            return await interaction.followup.send("❌ Event not active today!", ephemeral=True)

        channel = self.bot.get_channel(self.config["channel_id"])
        if not channel:
            return await interaction.followup.send(
                f"❌ Channel {self.config['channel_id']} not found!", ephemeral=True
            )

        reward = REWARDS.get(day)
        if not reward:
            return await interaction.followup.send(
                f"❌ No reward configured for day {day}!", ephemeral=True
            )

        # Prepare mention using config
        mention = "@everyone"
        if self.config.get("role_id"):
            role = channel.guild.get_role(self.config["role_id"])
            mention = role.mention if role else "@everyone"

        # Get daily message from config
        daily_message = self.config.get("daily_message", "Wake up {role}! A new gift is here!")
        daily_message = daily_message.replace("{role}", mention)

        embed = discord.Embed(
            title=f"🎄 Day {day} of ARKmas!", color=discord.Color.from_rgb(200, 230, 255)
        )
        embed.description = (
            f"**On the {day}{self.get_ordinal(day)} day of Christmas, the ARK gave to me...**\n\n"
            f"🎁 **{reward['name']}**\n*{reward['desc']}*"
        )
        embed.set_image(url="https://ark.wiki.gg/images/1/1a/Christmas_Tree.png")
        embed.set_footer(
            text="Click the button below to claim! Items require you to be online in-game."
        )

        view = ClaimView(self, day)
        await channel.send(content=daily_message, embed=embed, view=view)

        # Log manual announcement
        await self.log_event(
            f"Manual Announcement - Day {day}",
            f"Admin {interaction.user.mention} manually triggered Day {day} announcement",
            discord.Color.gold(),
        )

        await interaction.followup.send(
            f"✅ Posted Day {day} announcement to <#{self.config['channel_id']}>!", ephemeral=True
        )

    @app_commands.command(
        name="register_specimen",
        description="🔗 Register your Specimen Implant ID for item delivery",
    )
    @app_commands.describe(
        specimen_id="Your Specimen Implant ID (numeric, visible in your implant inventory)"
    )
    async def register_specimen(self, interaction: discord.Interaction, specimen_id: str):
        """Allow users to register their Specimen Implant ID"""
        await interaction.response.defer(ephemeral=True)

        # Verify user has linked account
        player = await players_db.get_player_by_discord_id(interaction.user.id)
        if not player:
            return await interaction.followup.send(
                "❌ You must link your account first! Use `/link` to connect your EOS ID.",
                ephemeral=True,
            )

        # Validate specimen_id format (should be numeric)
        if not specimen_id.isdigit():
            return await interaction.followup.send(
                "❌ Invalid Specimen ID! Your Specimen ID should be a number (e.g., 3744359).\n"
                "You can find it in your inventory by looking at your Specimen Implant.",
                ephemeral=True,
            )

        # Update specimen_id in database
        success = await players_db.update_specimen_id(interaction.user.id, specimen_id)

        if success:
            await interaction.followup.send(
                f"✅ Successfully registered Specimen ID: **{specimen_id}**\n"
                f"You can now receive items via RCON commands (like Christmas rewards)!",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "❌ Failed to register Specimen ID. Please try again or contact an admin.",
                ephemeral=True,
            )

    @app_commands.command(name="christmas", description="🎄 Claim your daily ARKmas gift!")
    async def christmas(self, interaction: discord.Interaction):
        """Manual claim command for daily gifts"""
        try:
            self.logger.info(f"Christmas: Command invoked by {interaction.user.name}")

            # Defer IMMEDIATELY to avoid timeout
            await interaction.response.defer(ephemeral=True)

            day = self.get_current_day()
            if not day:
                return await interaction.followup.send(
                    "❌ The Christmas event is not active right now! Check back December 13-24! 🎄",
                    ephemeral=True,
                )

            self.logger.info(f"Christmas: Current day calculated as {day}")

            await self.process_claim(interaction, day)
        except Exception as e:
            self.logger.error(f"Christmas: Error in christmas command: {e}", exc_info=True)

    async def process_claim(self, interaction: discord.Interaction, day: int):
        """Process a gift claim request"""
        try:
            # Ensure the interaction is acknowledged to avoid Unknown interaction errors
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)

            user = interaction.user
            self.logger.info(f"Christmas: Processing claim for {user.name}, day {day}")

            # Reload config to get latest settings (including debug_mode)
            self.load_event_config()

            # 1. Check Role (if required, skip in debug mode)
            if self.config.get("role_id") and not self.config["debug_mode"]:
                if self.config["role_id"] not in [r.id for r in user.roles]:
                    # Also allow administrators
                    if not user.guild_permissions.administrator:
                        return await interaction.followup.send(
                            "❌ You must be a Verified Player to participate!", ephemeral=True
                        )

            # 2. Check Previous Claim (skip in debug mode)
            if not self.config["debug_mode"]:
                if await self.has_claimed(user.id, day):
                    return await interaction.followup.send(
                        f"❌ You already claimed the **Day {day}** gift!", ephemeral=True
                    )
            else:
                self.logger.info(f"Christmas: DEBUG MODE - Skipping claim check for {user.name}")

            reward = REWARDS[day]

            # 3. Handle Coin Rewards (No Login Needed)
            if reward["type"] == "coin":
                await update_balance(user.id, reward["qty"], is_win=True)
                if not cog.config["debug_mode"]:
                    await cog.mark_claimed(user_id, day)
                return await interaction.followup.send(
                    f"🎁 **MERRY CHRISTMAS!**\nAdded **{reward['qty']}** Phoenix Coins to your wallet!",
                    ephemeral=True,
                )

            # 4. Get player info for item/dino delivery
            player_info = await self.get_player_info(user.id)

            if not player_info["specimen_id"]:
                return await interaction.followup.send(
                    "⚠️ **Specimen ID Not Registered**\n\n"
                    "Your Specimen Implant ID is required for item delivery.\n\n"
                    "**How to register:**\n"
                    "1️⃣ Open your inventory in-game\n"
                    "2️⃣ Look at your **Specimen Implant** item\n"
                    "3️⃣ Note the numeric ID shown (e.g., 3744359)\n"
                    "4️⃣ Use `/register_specimen <your_id>` in Discord\n\n"
                    "💡 Tip: Use `/mylink` to check your registration status!",
                    ephemeral=True,
                )

            if not player_info["online"]:
                return await interaction.followup.send(
                    "⚠️ **Delivery Failed:** You must be **Online** in the server to claim this item!\n\n"
                    "**Steps:**\n"
                    "1. Log into the ARK Server\n"
                    "2. Wait 2 minutes for the server to register you\n"
                    "3. Run `/christmas` again\n\n"
                    "*Items cannot be delivered to offline players as they would disappear.*",
                    ephemeral=True,
                )

            success = False

            # --- TYPE: ITEMS ---
            if reward["type"] == "item":
                cmd = CMD_GIVE_ITEM.format(
                    specimen_id=player_info["specimen_id"],
                    blueprint=reward["bp"],
                    quantity=reward["qty"],
                    quality=reward.get("quality", 0),
                )
                success = await self.send_rcon_command(player_info["server_name"], cmd)

            # --- TYPE: ITEM SETS (Day 4 - Armor Set) ---
            elif reward["type"] == "item_list":
                all_sent = True
                for bp in reward["bps"]:
                    cmd = CMD_GIVE_ITEM.format(
                        specimen_id=player_info["specimen_id"],
                        blueprint=bp,
                        quantity=1,
                        quality=reward.get("quality", 0),
                    )
                    result = await self.send_rcon_command(player_info["server_name"], cmd)
                    if not result:
                        all_sent = False
                success = all_sent

            if success:
                # Mark as claimed (skip in debug mode to allow re-testing)
                if not self.config["debug_mode"]:
                    await self.mark_claimed(user.id, day)
                else:
                    self.logger.info(
                        f"Christmas: DEBUG MODE - Skipping mark_claimed for {user.name}"
                    )

                # Log the claim
                await self.log_event(
                    f"Gift Claimed - Day {day}",
                    f"{user.mention} claimed **{reward['name']}**\n"
                    f"Server: {player_info['server_name']}\n"
                    f"Specimen ID: {player_info['specimen_id']}",
                    discord.Color.green(),
                )

                await interaction.followup.send(
                    f"🎁 **DELIVERED!**\nCheck your inventory for your **{reward['name']}**!\n*Delivered to {player_info['server_name']}*",
                    ephemeral=True,
                )
                self.logger.info(
                    f"Christmas Day {day} delivered to {user.name} ({user.id}) on {player_info['server_name']}"
                )
            else:
                await interaction.followup.send(
                    "❌ Error connecting to server or delivering item. Please try again later.",
                    ephemeral=True,
                )

        except Exception as e:
            self.logger.error(f"Christmas: Error in process_claim: {e}", exc_info=True)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        f"❌ An error occurred: {str(e)}", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"❌ An error occurred: {str(e)}", ephemeral=True
                    )
            except:
                pass


class ClaimView(discord.ui.View):
    """Persistent button view for claiming Christmas gifts"""

    def __init__(self, cog: ChristmasEvent, day: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.day = day
        # Add button with dynamic custom_id
        self.add_item(ClaimButton(day))


class ClaimButton(discord.ui.Button):
    """Button for claiming Christmas gifts"""

    def __init__(self, day: int):
        super().__init__(
            label="🎁 CLAIM GIFT",
            style=discord.ButtonStyle.success,
            custom_id=f"xmas_claim_day_{day}",
        )
        self.claim_day = day

    async def callback(self, interaction: discord.Interaction):
        """Handle button click for claiming gifts"""
        # Get the cog and process the claim
        cog = interaction.client.get_cog("ChristmasEvent")
        if cog:
            await cog.process_claim(interaction, self.claim_day)
        else:
            await interaction.response.send_message(
                "❌ Christmas event system is not available!", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(ChristmasEvent(bot))
