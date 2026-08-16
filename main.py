"""
ARK Survival Ascended Discord Bot
Main entry point for the bot application.
"""

import asyncio
import platform
import logging
import os
import sys
from pathlib import Path
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Windows Event Loop Policy fix
try:
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
except Exception:
    pass

from bot.utils.config import Config
from bot.database.init_db import initialize_database

# We import these but we WON'T use them in main() anymore
from bot.utils.arkids_api import get_arkids_client, cleanup_arkids_client
from bot.utils.phoenix_ai import cleanup_phoenix_ai


def setup_logging() -> None:
    """Configure logging for the bot."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    # Parse log level safely; fall back to INFO on invalid values
    log_level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    log_level = logging._nameToLevel.get(log_level_name, logging.INFO)
    log_file = os.getenv("LOG_FILE", "logs/bot.log")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    stream_handler = logging.StreamHandler(sys.stdout)

    if platform.system() == "Windows":
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        stream_handler = logging.StreamHandler(sys.stdout)

    if log_level_name not in logging._nameToLevel:
        # Use a direct print to avoid relying on logging before it's configured
        print(f"[WARN] Invalid LOG_LEVEL '{log_level_name}' - defaulting to INFO", file=sys.stderr)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[file_handler, stream_handler],
    )


class ArkBot(commands.Bot):
    """Custom bot class for ARK Discord Bot."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True

        # Optimize HTTP connector for faster API responses
        import aiohttp
        connector = aiohttp.TCPConnector(
            limit=100,  # Connection pool size
            ttl_dns_cache=300,  # DNS cache TTL
            force_close=False,  # Keep connections alive
            enable_cleanup_closed=True
        )

        super().__init__(
            command_prefix=Config.BOT_PREFIX, 
            intents=intents, 
            help_command=None,
            connector=connector  # Use optimized connector
        )
        self.config = Config
        self.logger = logging.getLogger("ArkBot")

    async def setup_hook(self) -> None:
        """Load cogs and setup the bot."""
        self.logger.info("Loading cogs...")

        # --- CRITICAL FIX: Background Task for Cache ---
        # We start this task immediately, but it runs in the background
        # so it does not block the bot from logging in.
        self.loop.create_task(self.load_cache_background())

        # ANTI-RATE LIMIT FIX: Load all cogs with 0.1s delay between each
        # This prevents API hammering during startup
        cogs = [
            "bot.cogs.setup_gui",
            "bot.cogs.server_monitor",
            "bot.cogs.chat_relay",
            "bot.cogs.help_commands",
            "bot.cogs.server_management",
            "bot.cogs.rcon_admin",
            "bot.cogs.log_viewer",
            "bot.cogs.player_management",
            "bot.cogs.economy",
            "bot.cogs.shop",
            "bot.cogs.bot_control",
            "bot.cogs.remote_agent",    # CRITICAL: Load before remote_agent_gui
            "bot.cogs.remote_agent_gui",
            "bot.cogs.mod_management",
            "bot.cogs.ini_management",
            "bot.cogs.ask_phoenix",
            "bot.cogs.games",
            "bot.cogs.shopcfg_gui",
            "bot.cogs.maintenance_gui",
            "bot.cogs.subscription",
            "bot.cogs.kit_management",
            "bot.cogs.kits",
            "bot.cogs.analytics_dashboard",
            "bot.cogs.server_service",  # Phase 16: ARK server service management
            # "bot.cogs.loot_crate_editor",  # DISABLED: Deferred until spreadsheet approach implemented
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                self.logger.info(f"Loaded cog: {cog}")
                # ANTI-RATE LIMIT: Small pause to let event loop breathe
                await asyncio.sleep(0.1)
            except Exception as e:
                self.logger.error(f"Failed to load cog {cog}: {e}")

        # Command syncing - enabled for multi-guild support
        if os.path.exists(".sync_commands"):
            self.logger.info("Found .sync_commands file - will sync commands on startup")
            self.loop.create_task(self._sync_commands())

    async def load_cache_background(self):
        """Loads heavy API data in background without stopping startup."""
        await self.wait_until_ready()  # Wait until we are logged into Discord
        self.logger.info("⏳ Starting background load of ArkIDs cache...")
        try:
            client = get_arkids_client()
            await client.load_items_cache()
            self.logger.info("✅ ArkIDs cache loaded successfully!")
        except Exception as e:
            self.logger.error(f"❌ Failed to load ArkIDs cache (Bot is still online): {e}")

    async def _sync_commands(self):
        try:
            await self.wait_until_ready()
            
            # Multi-guild support: Copy global commands to each guild, then sync
            synced_count = 0
            for guild in self.guilds:
                try:
                    guild_obj = discord.Object(id=guild.id)
                    # Copy global commands to this guild
                    self.tree.copy_global_to(guild=guild_obj)
                    # Sync commands to this guild
                    synced = await self.tree.sync(guild=guild_obj)
                    synced_count += len(synced)
                    self.logger.info(f"✅ Synced {len(synced)} commands to guild {guild.name} ({guild.id})")
                except Exception as e:
                    self.logger.error(f"❌ Failed to sync commands to guild {guild.name} ({guild.id}): {e}")
            
            self.logger.info(f"✅ Command sync complete! Synced to {len(self.guilds)} guilds ({synced_count} total commands)")

            if os.path.exists(".sync_commands"):
                os.remove(".sync_commands")
        except Exception as e:
            self.logger.error(f"Failed to sync commands: {e}")

    async def on_ready(self) -> None:
        self.logger.info(f"Bot is ready! Logged in as {self.user}")
        activity = discord.Activity(type=discord.ActivityType.watching, name="ARK Servers | /help")
        await self.change_presence(activity=activity)

    async def on_message(self, message: discord.Message) -> None:
        """Process messages and dispatch to cog listeners."""
        # Process commands first (for prefix commands if any)
        await self.process_commands(message)
        # Event will automatically propagate to cog listeners

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Automatically sync commands when bot joins a new guild."""
        self.logger.info(f"Joined new guild: {guild.name} ({guild.id})")
        try:
            # Copy global commands to the new guild and sync
            guild_obj = discord.Object(id=guild.id)
            self.tree.copy_global_to(guild=guild_obj)
            synced = await self.tree.sync(guild=guild_obj)
            self.logger.info(f"✅ Synced {len(synced)} commands to new guild {guild.name}")
            # Note: Guild initialization (trial subscription, database entry) is handled by subscription cog
        except Exception as e:
            self.logger.error(f"❌ Failed to sync commands to new guild {guild.name}: {e}")

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: {error.param.name}")
        else:
            self.logger.error(f"Command error: {error}", exc_info=error)


async def main():
    load_dotenv()
    setup_logging()
    logger = logging.getLogger("Main")

    if not Config.DISCORD_BOT_TOKEN:
        logger.error("DISCORD_BOT_TOKEN not found!")
        sys.exit(1)

    logger.info("Initializing database...")
    await initialize_database()

    # --- MOVED: Cache loading is now in ArkBot.setup_hook ---

    bot = ArkBot()
    try:
        logger.info("Starting bot...")
        await bot.start(Config.DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=e)
    finally:
        await cleanup_arkids_client()
        await cleanup_phoenix_ai()
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot shutdown complete.")
