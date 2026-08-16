"""
AskPhoenix Discord Cog
Provides /askphoenix command for ARK: Survival Ascended Q&A.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.phoenix_ai import get_phoenix_ai, PhoenixAI
from bot.database import server_config_db
from bot.utils.subscription_checker import check_feature

logger = logging.getLogger(__name__)


class AskPhoenix(commands.Cog):
    """Discord cog for PhoenixAI Q&A system."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def _is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has the configured admin role."""
        if not interaction.guild:
            return False
        
        guild_id = interaction.guild_id
        user = interaction.user
        
        # Get configured admin role
        config = await server_config_db.get_server_config(guild_id)
        if not config:
            return False
        
        admin_role_id = config.get('admin_role_id')
        if not admin_role_id:
            return False
        
        # Check if user has the admin role
        if isinstance(user, discord.Member):
            for role in user.roles:
                if role.id == admin_role_id:
                    return True
        
        return False
    
    @app_commands.command(
        name="askphoenix",
        description="Ask PhoenixAI a question about ARK: Survival Ascended"
    )
    @app_commands.describe(
        question="Your question about ARK: Survival Ascended"
    )
    async def askphoenix(
        self,
        interaction: discord.Interaction,
        question: str
    ):
        if not await check_feature(interaction, "ask_phoenix"):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        user_id = str(interaction.user.id)
        username = interaction.user.display_name
        
        phoenix_ai = get_phoenix_ai()
        
        if not phoenix_ai.is_available():
            await interaction.followup.send(
                "PhoenixAI is currently unavailable. Please try again later.",
                ephemeral=True
            )
            return
        
        can_proceed, remaining = phoenix_ai.check_cooldown(user_id)
        if not can_proceed:
            await interaction.followup.send(
                f"Please wait {remaining} more second(s) before asking another question.",
                ephemeral=True
            )
            return
        
        logger.info(f"AskPhoenix from {username}: {question[:100]}...")
        
        guild_id = interaction.guild_id
        is_admin = await self._is_admin(interaction)
        
        try:
            response = await phoenix_ai.ask(question, guild_id=guild_id, is_admin=is_admin)
            
            header = f"**PhoenixAI**\n> {question}\n\n"
            footer = "\n\n*Powered by PhoenixArkAI*"
            max_msg_len = 2000
            max_first_chunk = max_msg_len - len(header) - len(footer)
            max_continuation = max_msg_len - len(footer)
            
            if len(response) <= max_first_chunk:
                message = f"{header}{response}{footer}"
                await interaction.followup.send(message, ephemeral=True)
            else:
                remaining_text = response
                is_first = True
                
                while remaining_text:
                    chunk_max = max_first_chunk if is_first else max_continuation
                    
                    if len(remaining_text) <= chunk_max:
                        chunk = remaining_text
                        remaining_text = ''
                    else:
                        break_at = remaining_text.rfind('\n', 0, chunk_max)
                        if break_at < chunk_max * 0.5:
                            break_at = remaining_text.rfind(' ', 0, chunk_max)
                        if break_at < 100:
                            break_at = chunk_max
                        
                        chunk = remaining_text[:break_at]
                        remaining_text = remaining_text[break_at:].lstrip()
                    
                    if is_first:
                        msg = f"{header}{chunk}"
                        is_first = False
                    else:
                        msg = chunk
                    
                    if not remaining_text:
                        msg += footer
                    
                    await interaction.followup.send(msg, ephemeral=True)
            
            logger.info(f"AskPhoenix responded to {username} ({len(response)} chars)")
            
        except Exception as e:
            logger.error(f"AskPhoenix error: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while processing your question. Please try again.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AskPhoenix(bot))
