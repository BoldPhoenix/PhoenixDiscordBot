"""
Explorer Trivia - Only the most studious survivors survive.
Test your ARK lore knowledge to earn rewards.
"""

import discord
import random
from bot.games.base import BaseGameView, GameResult, GameOutcome
from bot.games.static_trivia import get_static_question, get_question_count


class ExplorerTriviaView(BaseGameView):
    NAME = "Explorer Trivia"
    EMOJI = "📖"
    DESCRIPTION = "Test your ARK lore knowledge!\nFree to play | Win 20 coins for correct answer!"
    DEFAULT_WAGER = 0

    def __init__(self, guild_id: int, user_id: int, wager: int = 0):
        super().__init__(guild_id, user_id, wager, timeout=None)
        self._question = get_static_question()
        self._question_count = get_question_count()
        # Remove inherited wager button since this is a free game
        self._remove_inherited_wager_button()
        # Add all games button for navigation
        self._add_all_games_button()
    
    @property
    def total_questions(self) -> int:
        """Get total number of possible questions."""
        return self._question_count

    def _remove_inherited_wager_button(self):
        """Remove the inherited wager button from the view"""
        for item in self.children[:]:
            if hasattr(item, 'label') and ("Wager" in item.label or "wager" in item.label):
                self.remove_item(item)
                break

    def _add_all_games_button(self):
        """Add all games button for navigation"""
        games_btn = discord.ui.Button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=1)
        games_btn.callback = self._all_games
        self.add_item(games_btn)

    async def _all_games(self, interaction: discord.Interaction):
        """Return to game selection"""
        embed = discord.Embed(
            title="🎮 Phoenix ARK Games",
            description="Select a game to play!",
            color=discord.Color.blue()
        )
        embed.add_field(name="Free Game", value="This game is free to play!", inline=False)
        from bot.cogs.games import PhoenixGameHubView
        view = PhoenixGameHubView(self.guild_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)

    async def start_game(self, balance: int = None):
        """Initialize game state when starting from GameIntroView"""
        return self._build_embed(balance), self

    def _build_embed(self, balance: int = None) -> discord.Embed:
        opts = "\n".join(f"{chr(65+i)}) {opt}" for i, opt in enumerate(self._question["options"]))
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=f"**{self._question['q']}**\n\n{opts}",
            color=discord.Color.blue()
        )
        # Add balance display
        if balance is not None:
            balance_str = f"🪙 {balance:,}" if balance else "🪙 0"
        else:
            balance_str = "🪙 --"
        
        embed.add_field(name="Balance", value=balance_str, inline=True)
        return embed

    async def _answer(self, interaction: discord.Interaction, choice: int):
        if self._resolved:
            return

        correct = choice == self._question["answer"]
        
        if correct:
            payout = 20
            await self.award_winnings(payout)
            
            outcome = GameOutcome(
                result=GameResult.WIN,
                wager=0,
                payout=payout,
                multiplier=0,
                message=f"**CORRECT!**\n\nThe answer was: **{self._question['options'][self._question['answer']]}**\n\n"
                       f"**YOU WIN!**\nReceived: **{payout}** coins",
                color=discord.Color.green()
            )
        else:
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=0,
                payout=0,
                multiplier=0,
                message=f"**INCORRECT!**\n\nThe answer was: **{self._question['options'][self._question['answer']]}**\n\n"
                       f"Better study those notes!",
                color=discord.Color.red()
            )

        # Record the game result
        await self.record_game(outcome)
        
        # Get updated balance
        from bot.database import players_db
        new_balance, _ = await players_db.get_balance_by_discord_id(self.guild_id, self.user_id)
        balance_str = f"🪙 {new_balance:,}" if new_balance is not None else "🪙 0"
        
        # Create result view with Next Question and All Games buttons
        result_view = TriviaResultView(self.guild_id, self.user_id, outcome.message, outcome.color)
        
        # Build the result embed
        result_embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=outcome.message,
            color=outcome.color
        )
        result_embed.add_field(name="Balance", value=balance_str, inline=True)
        
        await interaction.response.edit_message(embed=result_embed, view=result_view)

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary, row=0)
    async def opt_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._answer(interaction, 0)

    @discord.ui.button(label="B", style=discord.ButtonStyle.primary, row=0)
    async def opt_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._answer(interaction, 1)

    @discord.ui.button(label="C", style=discord.ButtonStyle.primary, row=0)
    async def opt_c(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._answer(interaction, 2)

    @discord.ui.button(label="D", style=discord.ButtonStyle.primary, row=0)
    async def opt_d(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._answer(interaction, 3)

    @discord.ui.button(label="E", style=discord.ButtonStyle.primary, row=0)
    async def opt_e(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._answer(interaction, 4)


class TriviaResultView(discord.ui.View):
    """View shown after answering a trivia question"""
    timeout = None  # Disable timeout for ephemeral messages
    
    def __init__(self, guild_id: int, user_id: int, result_message: str, result_color: discord.Color):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.result_message = result_message
        self.result_color = result_color
        
        # Add Next Question button
        next_btn = discord.ui.Button(label="🔄 Next Question", style=discord.ButtonStyle.success, row=0)
        next_btn.callback = self._next_question
        self.add_item(next_btn)
        
        # Add All Games button
        games_btn = discord.ui.Button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=0)
        games_btn.callback = self._all_games
        self.add_item(games_btn)
    
    async def _next_question(self, interaction: discord.Interaction):
        """Start a new trivia question"""
        new_game = ExplorerTriviaView(self.guild_id, self.user_id)
        # Get balance for the new question
        from bot.database import players_db
        balance, _ = await players_db.get_balance_by_discord_id(self.guild_id, self.user_id)
        embed = new_game._build_embed(balance)
        await interaction.response.edit_message(embed=embed, view=new_game)
    
    async def _all_games(self, interaction: discord.Interaction):
        """Return to game selection"""
        embed = discord.Embed(
            title="🎮 Phoenix ARK Games",
            description="Select a game to play!",
            color=discord.Color.blue()
        )
        embed.add_field(name="Free Game", value="This game is free to play!", inline=False)
        from bot.cogs.games import PhoenixGameHubView
        view = PhoenixGameHubView(self.guild_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)
