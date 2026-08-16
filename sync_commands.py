"""
Sync Discord slash commands manually.
Run this after making changes to commands or when commands need to be updated in Discord.
"""

import asyncio
import discord
from discord.ext import commands
import logging

from bot.utils.config import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("CommandSync")


class SyncBot(commands.Bot):
    """Minimal bot for command syncing."""
    
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.synced = False
        
    async def setup_hook(self):
        """Load all cogs to register commands."""
        logger.info("Loading cogs to register commands...")
        
        # Load all active cogs (needed to register commands)
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
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
                # ANTI-RATE LIMIT: Small pause to let event loop breathe
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")
        
        logger.info(f"All cogs loaded. Total commands: {len(self.tree.get_commands())}")
        
    async def on_ready(self):
        """Sync commands when ready."""
        if not self.synced:
            logger.info(f"Logged in as {self.user}")
            logger.info("Starting command sync...")
            
            try:
                if Config.DISCORD_GUILD_ID:
                    guild = discord.Object(id=Config.DISCORD_GUILD_ID)

                    # Step 1: Sync guild-scoped commands
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    logger.info(f"✅ Synced {len(synced)} commands to guild {Config.DISCORD_GUILD_ID}")

                    # Step 2: Clear stale global commands (fixes duplicate command issue)
                    self.tree.clear_commands(guild=None)
                    await self.tree.sync()
                    logger.info("✅ Cleared global commands (removes duplicates visible globally)")
                else:
                    # Sync globally (takes up to 1 hour to propagate)
                    synced = await self.tree.sync()
                    logger.info(f"✅ Synced {len(synced)} commands globally")
                
                self.synced = True
                logger.info("Command sync complete! Bot can now respond to slash commands.")
                
            except discord.HTTPException as e:
                if e.status == 429:
                    logger.error(f"❌ Rate limited! Retry after {e.response.headers.get('Retry-After', 'unknown')} seconds")
                else:
                    logger.error(f"❌ HTTP error during sync: {e}")
            except Exception as e:
                logger.error(f"❌ Failed to sync commands: {e}")
            finally:
                # Close after syncing
                await asyncio.sleep(2)
                await self.close()


async def main():
    """Main sync function."""
    logger.info("=" * 60)
    logger.info("Discord Command Sync Tool")
    logger.info("=" * 60)
    
    bot = SyncBot()
    
    try:
        await bot.start(Config.DISCORD_BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Sync cancelled by user")
    except Exception as e:
        logger.error(f"Error during sync: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
