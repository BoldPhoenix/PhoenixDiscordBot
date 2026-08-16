"""
Phoenix Game System - Discord cog for mini-games.
Provides /games command to access all game types.
"""

import discord
import logging
import random
from discord.ext import commands
from discord import app_commands

from bot.utils.subscription_checker import check_feature
from bot.games import (
    DodoRouletteView,
    OverseerCodeView,
    FossilExcavationView,
    TamingRiskView,
    ArtifactVaultView,
    CraftingRaceView,
    MutationSlotsView,
    AlphaHuntView,
    CryoGambleView,
    ArkDiceView,
    SurvivorCardsView,
    BlackjackView,
)

logger = logging.getLogger("PhoenixGames")


class PhoenixGamesCog(commands.Cog):
    """Phoenix Game System - Mini-games for ARK communities."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="games",
        description="Open the Phoenix Game System"
    )
    async def games(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await check_feature(interaction, "games"):
            return
        balance = await self._get_balance(interaction.guild_id, interaction.user.id)
        
        embed = discord.Embed(
            title="🎮 Phoenix Game System",
            color=0xE74C3C
        )
        embed.add_field(name="Your Balance", value=f"🪙 {balance:,} coins", inline=False)
        
        view = PhoenixGameHubView(interaction.guild_id, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    
    async def _get_balance(self, guild_id: int, user_id: int) -> int:
        from bot.database import players_db
        balance, _ = await players_db.get_balance_by_discord_id(guild_id, user_id)
        return balance if balance else 0


class PhoenixGameHubView(discord.ui.View):
    """Main menu for all games with randomized button colors."""

    GAMES = [
        ("Dino Jack", "🃏", BlackjackView),
        ("Dodo Roulette", "🦤", DodoRouletteView),
        ("Overseer Code", "💻", OverseerCodeView),
        ("Fossil Excavation", "🦴", FossilExcavationView),
        ("ARK Dice", "🎲", ArkDiceView),
        ("Survivor Cards", "🃏", SurvivorCardsView),
        ("Taming Risk", "🥩", TamingRiskView),
        ("Artifact Vault", "🏺", ArtifactVaultView),
        ("Crafting Race", "⚒️", CraftingRaceView),
        ("Ark Slots", "🎰", MutationSlotsView),
        ("Alpha Hunt", "🦖", AlphaHuntView),
        ("Cryo Gamble", "❄️", CryoGambleView),
    ]

    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id

        for i, (name, emoji, view_class) in enumerate(self.GAMES):
            row = i // 3
            style = discord.ButtonStyle.primary  # Standard blue color for all buttons
            btn = discord.ui.Button(
                label=name,
                style=style,
                emoji=emoji,
                row=row
            )
            btn.callback = self._make_callback(view_class)
            self.add_item(btn)

    def _make_callback(self, view_class):
        async def callback(interaction: discord.Interaction):
            from bot.database import players_db, games_db
            from bot.games.base import GameIntroView
            
            balance, _ = await players_db.get_balance_by_discord_id(self.guild_id, self.user_id)
            balance = balance if balance else 0
            
            stats = await games_db.get_user_stats(self.guild_id, self.user_id, view_class.NAME)
            if stats:
                stats_dict = {"played": stats.get("games_played", 0), "won": stats.get("games_won", 0), "lost": stats.get("games_played", 0) - stats.get("games_won", 0)}
            else:
                stats_dict = {"played": 0, "won": 0, "lost": 0}
            
            intro_view = GameIntroView(self.guild_id, self.user_id, view_class, balance, stats_dict)
            await interaction.response.edit_message(embed=intro_view.build_embed(), view=intro_view)
        return callback


async def setup(bot):
    await bot.add_cog(PhoenixGamesCog(bot))
