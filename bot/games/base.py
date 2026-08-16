"""
Base classes and utilities for Phoenix Gaming Terminal.
Provides shared functionality for all mini-games.
"""

import discord
import asyncio
import logging
from dataclasses import dataclass
from discord.ext import commands
from discord import app_commands
from typing import Dict, Any
from enum import Enum

from bot.database import games_db

logger = logging.getLogger("PhoenixGames")


class GameResult(Enum):
    WIN = "win"
    LOSS = "loss"
    JACKPOT = "jackpot"
    PUSH = "push"


@dataclass
class GameOutcome:
    result: GameResult
    wager: int
    payout: int
    multiplier: float
    message: str
    color: discord.Color


class GameIntroView(discord.ui.View):
    """Intro screen shown before starting a game."""

    def __init__(self, guild_id: int, user_id: int, game_view_class, balance: int, stats: Dict[str, int]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.game_view_class = game_view_class
        self.wager = game_view_class.DEFAULT_WAGER
        self.balance = balance
        self.stats = stats
        
        # Only add wager button for paid games
        if game_view_class.DEFAULT_WAGER > 0:
            wager_btn = discord.ui.Button(label="💰 Wager", style=discord.ButtonStyle.primary, row=0)
            wager_btn.callback = self._wager_callback
            self.add_item(wager_btn)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.game_view_class.EMOJI} {self.game_view_class.NAME}",
            description=self.game_view_class.DESCRIPTION,
            color=0xE74C3C
        )
        
        # Only show wager info for paid games
        if self.game_view_class.DEFAULT_WAGER > 0:
            embed.add_field(name="Wager", value=f"🪙 {self.wager} coins", inline=True)
            embed.add_field(name="Balance", value=f"🪙 {self.balance:,} coins", inline=True)
        else:
            embed.add_field(name="Game Type", value="🆓 **Free to Play**", inline=True)
            embed.add_field(name="Balance", value=f"🪙 {self.balance:,} coins", inline=True)
        
        embed.add_field(name="Record", value=f"✅ {self.stats['won']} | ❌ {self.stats['lost']}", inline=True)
        return embed
    
    async def _wager_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IntroWagerModal(self))

    @discord.ui.button(label="▶️ Play", style=discord.ButtonStyle.success, row=0)
    async def play_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        game_view = self.game_view_class(self.guild_id, self.user_id, self.wager)
        
        # Check balance and deduct wager
        if not await game_view.ensure_balance(interaction):
            return
            
        if not await game_view.deduct_wager():
            return await interaction.response.send_message("Failed to process wager.", ephemeral=True)
        
        # Get updated balance after wager deduction
        updated_balance = await game_view.get_balance()
        
        # Start the game
        if hasattr(game_view, 'start_game'):
            if asyncio.iscoroutinefunction(game_view.start_game):
                result = await game_view.start_game(updated_balance)
            else:
                try:
                    result = game_view.start_game(updated_balance)
                except TypeError:
                    result = game_view.start_game()
            
            # Handle both 2-value (embed, view) and 3-value (embed, file, view) returns
            if len(result) == 3:
                embed, file, view = result
                await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=view)
                return
            else:
                embed, view = result
        else:
            embed = game_view._build_embed() if hasattr(game_view, '_build_embed') else self.build_embed()
            view = game_view
        
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=0)
    async def all_games_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from bot.cogs.games import PhoenixGameHubView
        embed = discord.Embed(title="🎮 Phoenix Game System", color=0xE74C3C)
        embed.add_field(name="Your Balance", value=f"🪙 {self.balance:,} coins", inline=False)
        view = PhoenixGameHubView(self.guild_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)


class IntroWagerModal(discord.ui.Modal, title="Change Wager"):
    wager_input = discord.ui.TextInput(
        label="Wager Amount",
        placeholder="Enter wager amount",
        min_length=1,
        max_length=6
    )

    def __init__(self, intro_view: GameIntroView):
        super().__init__()
        self.intro_view = intro_view
        self.wager_input.default = str(intro_view.wager)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            wager = int(self.wager_input.value)
            if wager < self.intro_view.game_view_class.MIN_WAGER:
                await interaction.response.send_message(
                    f"Minimum wager is {self.intro_view.game_view_class.MIN_WAGER} coins.",
                    ephemeral=True
                )
                return
            if wager > self.intro_view.game_view_class.MAX_WAGER:
                await interaction.response.send_message(
                    f"Maximum wager is {self.intro_view.game_view_class.MAX_WAGER} coins.",
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)
            return

        self.intro_view.wager = wager
        await interaction.response.edit_message(embed=self.intro_view.build_embed(), view=self.intro_view)


class BaseGameView(discord.ui.View):
    NAME: str = "Base Game"
    EMOJI: str = "🎮"
    DESCRIPTION: str = "Base game class"
    DEFAULT_WAGER: int = 10
    MIN_WAGER: int = 1
    MAX_WAGER: int = 1000
    WAGER_BUTTON_ROW: int = 4  # Override in subclass to place button on different row

    def __init__(
        self,
        guild_id: int,
        user_id: int,
        wager: int = None,
        timeout: float = None,
    ):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.user_id = user_id
        self.wager = wager or self.DEFAULT_WAGER
        self._resolved = False
        self._eos_id: str = None
        
        # Add wager button on configured row
        wager_btn = discord.ui.Button(label="💰 Wager", style=discord.ButtonStyle.secondary, row=self.WAGER_BUTTON_ROW)
        wager_btn.callback = self._change_wager
        self.add_item(wager_btn)

    @property
    def game_name(self) -> str:
        return self.NAME

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This game belongs to another player!",
                ephemeral=True
            )
            return False
        return True

    async def ensure_balance(self, interaction: discord.Interaction) -> bool:
        from bot.database import players_db
        
        balance, eos_id = await players_db.get_balance_by_discord_id(self.guild_id, self.user_id)
        if eos_id is None:
            await interaction.response.send_message(
                "You need to link your account first! Use `/player link`.",
                ephemeral=True
            )
            return False
        
        self._eos_id = eos_id
        
        if balance < self.wager:
            await interaction.response.send_message(
                f"You need at least {self.wager} coins to play! Your balance: {balance}",
                ephemeral=True
            )
            return False
        return True

    async def deduct_wager(self) -> bool:
        from bot.database import players_db
        
        success = await players_db.deduct_coins(
            self.guild_id,
            self._eos_id,
            self.wager,
            reason=f"Game wager: {self.game_name}",
            discord_id=self.user_id
        )
        return success

    async def award_winnings(self, amount: int) -> int:
        from bot.database import players_db
        
        new_balance = await players_db.add_coins(
            self.guild_id,
            self._eos_id,
            amount,
            reason=f"Game winnings: {self.game_name}",
            discord_id=self.user_id
        )
        return new_balance

    async def record_game(self, outcome: GameOutcome):
        await games_db.record_game(
            guild_id=self.guild_id,
            user_id=self.user_id,
            game_name=self.game_name,
            wager=self.wager,
            won=outcome.result in (GameResult.WIN, GameResult.JACKPOT),
            payout=outcome.payout,
        )

    async def get_balance(self) -> int:
        from bot.database import players_db
        balance, _ = await players_db.get_balance_by_discord_id(self.guild_id, self.user_id)
        return balance if balance else 0

    async def get_stats(self) -> Dict[str, int]:
        stats = await games_db.get_user_stats(self.guild_id, self.user_id, self.game_name)
        if stats:
            return {
                "played": stats.get("games_played", 0),
                "won": stats.get("games_won", 0),
                "lost": stats.get("games_played", 0) - stats.get("games_won", 0),
            }
        return {"played": 0, "won": 0, "lost": 0}

    def build_embed(self, outcome: GameOutcome, balance: int, stats: Dict[str, int]) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.game_name}",
            description=outcome.message,
            color=outcome.color
        )
        
        embed.add_field(name="Wager", value=f"{self.wager} coins", inline=True)
        
        if outcome.payout > 0:
            embed.add_field(
                name="Payout",
                value=f"{outcome.payout} coins ({outcome.multiplier:.1f}x)",
                inline=True
            )
        else:
            embed.add_field(name="Result", value="No payout", inline=True)
        
        embed.add_field(name="Balance · Record", value=f"🪙 {balance:,}  ·  ✅{stats['won']} ❌{stats['lost']}", inline=True)

        return embed

    async def resolve_game(
        self,
        interaction: discord.Interaction,
        outcome: GameOutcome,
    ):
        if self._resolved:
            return
        self._resolved = True

        await self.record_game(outcome)
        
        balance = await self.get_balance()
        stats = await self.get_stats()
        
        embed = self.build_embed(outcome, balance, stats)
        view = GameResultButtons(self.guild_id, self.user_id, self.__class__, self.wager, balance, stats)

        await interaction.response.edit_message(embed=embed, view=view)

    async def _change_wager(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WagerModal(self))


class WagerModal(discord.ui.Modal):
    def __init__(self, game_view: BaseGameView):
        super().__init__(title=f"Change Wager")
        self.game_view = game_view

        self.wager_input = discord.ui.TextInput(
            label="Wager Amount",
            placeholder=f"Enter amount ({game_view.MIN_WAGER} - {game_view.MAX_WAGER})",
            default=str(game_view.wager),
            min_length=1,
            max_length=6
        )
        self.add_item(self.wager_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            wager = int(self.wager_input.value)
            if wager < self.game_view.MIN_WAGER or wager > self.game_view.MAX_WAGER:
                await interaction.response.send_message(
                    f"Wager must be between {self.game_view.MIN_WAGER} and {self.game_view.MAX_WAGER} coins.",
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)
            return

        self.game_view.wager = wager
        
        # Check if game view has custom embed building (for games with images)
        if hasattr(self.game_view, '_build_embed'):
            import asyncio
            if asyncio.iscoroutinefunction(self.game_view._build_embed):
                result = await self.game_view._build_embed()
            else:
                result = self.game_view._build_embed()
            if isinstance(result, tuple) and len(result) == 2:
                embed, file = result
                await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=self.game_view)
                return
        
        balance = await self.game_view.get_balance()
        stats = await self.game_view.get_stats()
        
        embed = discord.Embed(
            title=f"{self.game_view.EMOJI} {self.game_view.NAME}",
            description=self.game_view.DESCRIPTION,
            color=0xE74C3C
        )
        embed.add_field(name="Wager", value=f"{wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,} coins", inline=True)
        embed.add_field(name="Record", value=f"✅ {stats['won']} | ❌ {stats['lost']}", inline=True)
        
        await interaction.response.edit_message(embed=embed, view=self.game_view)


class GameResultButtons(discord.ui.View):
    """Post-game buttons: Play Again, All Games."""

    def __init__(self, guild_id: int, user_id: int, game_view_class, wager: int, balance: int, stats: Dict[str, int]):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.game_view_class = game_view_class
        self.wager = wager
        self.balance = balance
        self.stats = stats

    @discord.ui.button(label="Play Again", style=discord.ButtonStyle.green, emoji="🔄")
    async def play_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Create new game instance and start directly
        game_view = self.game_view_class(self.guild_id, self.user_id, self.wager)
        
        # Check balance and deduct wager
        if not await game_view.ensure_balance(interaction):
            return
            
        if not await game_view.deduct_wager():
            await interaction.response.send_message("Failed to process wager.", ephemeral=True)
            return
        
        # Get updated balance
        updated_balance = await game_view.get_balance()
        
        # Start the game directly
        if hasattr(game_view, 'start_game'):
            import asyncio
            if asyncio.iscoroutinefunction(game_view.start_game):
                result = await game_view.start_game(updated_balance)
            else:
                try:
                    result = game_view.start_game(updated_balance)
                except TypeError:
                    result = game_view.start_game()
            
            # Handle both 2-value and 3-value returns
            if len(result) == 3:
                embed, file, view = result
                await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=view)
                return
            else:
                embed, view = result
        else:
            embed = game_view._build_embed() if hasattr(game_view, '_build_embed') else None
            view = game_view
        
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="All Games", style=discord.ButtonStyle.secondary, emoji="🎮")
    async def return_to_games(self, interaction: discord.Interaction, button: discord.ui.Button):
        from bot.cogs.games import PhoenixGameHubView
        embed = discord.Embed(title="🎮 Phoenix Game System", color=0xE74C3C)
        embed.add_field(name="Your Balance", value=f"🪙 {self.balance:,} coins", inline=False)
        view = PhoenixGameHubView(self.guild_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)
