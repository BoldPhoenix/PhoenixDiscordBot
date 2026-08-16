"""
Clear all Discord slash commands and force a fresh sync.
This will remove old command names from Discord's cache.
"""

import asyncio
import logging
import os
from dotenv import load_dotenv
import discord
from discord.ext import commands

# Load environment
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CommandCleaner")

async def clear_commands():
    """Clear all guild commands and resync."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    guild_id = os.getenv("DISCORD_GUILD_ID")
    
    if not token:
        logger.error("DISCORD_BOT_TOKEN not found!")
        return
    
    if not guild_id:
        logger.error("DISCORD_GUILD_ID not found!")
        return
    
    # Create bot instance
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    
    @bot.event
    async def on_ready():
        logger.info(f"Logged in as {bot.user}")
        
        # Get guild
        guild = discord.Object(id=int(guild_id))
        
        # Clear all commands from guild
        logger.info("Clearing all guild commands...")
        bot.tree.clear_commands(guild=guild)
        await bot.tree.sync(guild=guild)
        logger.info("✓ Guild commands cleared")
        
        # Also clear global commands just in case
        logger.info("Clearing all global commands...")
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync(guild=None)
        logger.info("✓ Global commands cleared")
        
        logger.info("\n✓ All commands cleared! Now restart the bot to register fresh commands.")
        
        await bot.close()
    
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(clear_commands())
