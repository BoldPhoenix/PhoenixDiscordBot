"""
ARK Dice - Roll against the house with ARK-themed dice.
Beat the dealer's roll to win! Higher roll wins, ties are a push.
"""

import discord
import random
from bot.games.base import BaseGameView, GameResult, GameOutcome


class ArkDiceView(BaseGameView):
    NAME = "ARK Dice"
    EMOJI = "🎲"
    DESCRIPTION = "Roll against the house! Higher roll wins.\n🎯 Beat dealer to win 2x, tie = push (wager returned)"
    DEFAULT_WAGER = 10

    DICE_FACES = ["[1]", "[2]", "[3]", "[4]", "[5]", "[6]"]

    def __init__(self, guild_id: int, user_id: int, wager: int = None):
        super().__init__(guild_id, user_id, wager, timeout=None)
        self._player_roll = None
        self._dealer_roll = None
        self._game_started = False
        self._current_balance = None
        self._add_control_buttons()
        # Remove the inherited wager button
        self._remove_inherited_wager_button()

    def _remove_inherited_wager_button(self):
        """Remove the inherited wager button from the view"""
        for item in self.children[:]:
            if hasattr(item, 'label') and item.label == "💰 Wager":
                self.remove_item(item)
                break

    def _add_control_buttons(self):
        """Add roll dice, wager and navigation buttons to the game"""
        # Add roll dice button
        roll_btn = discord.ui.Button(label="🎲 Roll Dice", style=discord.ButtonStyle.success, row=0)
        roll_btn.callback = self._roll_dice
        self.add_item(roll_btn)
        
        # Add wager button
        wager_btn = discord.ui.Button(label="💰 Change Wager", style=discord.ButtonStyle.primary, row=1)
        wager_btn.callback = self._wager_modal
        self.add_item(wager_btn)
        
        # Add all games button
        games_btn = discord.ui.Button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=1)
        games_btn.callback = self._all_games
        self.add_item(games_btn)

    async def _wager_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ArkDiceWagerModal(self))

    async def _all_games(self, interaction: discord.Interaction):
        from bot.cogs.games import PhoenixGameHubView
        balance = await self.get_balance()
        embed = discord.Embed(title="🎮 Phoenix Game System", color=0xE74C3C)
        embed.add_field(name="Your Balance", value=f"🪙 {balance:,} coins", inline=False)
        view = PhoenixGameHubView(self.guild_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)

    def start_game(self, balance: int = None):
        """Initialize game state when starting from GameIntroView"""
        self._game_started = True
        # Use passed balance or get it if not provided
        if balance is not None:
            self._current_balance = balance
        else:
            # Fallback: try to get balance synchronously
            self._current_balance = 0
        return self._build_game_embed(), self

    def _build_game_embed(self) -> discord.Embed:
        if not self._game_started:
            embed = discord.Embed(
                title=f"{self.EMOJI} {self.NAME}",
                description="Click **Roll Dice** to play against the dealer!",
                color=discord.Color.blue()
            )
            embed.add_field(name="How to Play", value="🎲 Roll your dice vs dealer\n🏆 Higher roll wins 2x wager\n🤝 Tie = push (wager returned)", inline=False)
            return embed

        if self._player_roll is None:
            embed = discord.Embed(
                title=f"{self.EMOJI} {self.NAME}",
                description="Click **Roll Dice** to play against the dealer!",
                color=discord.Color.blue()
            )
            embed.add_field(name="Wager", value=f"🪙 {self.wager} coins", inline=True)
            embed.add_field(name="Balance", value=f"🪙 {self._current_balance:,} coins", inline=True)
            embed.add_field(name="Payout", value="2x if you win!", inline=True)
        else:
            # Game completed
            if self._player_roll > self._dealer_roll:
                result_text = "🎉 **YOU WIN!**"
                color = discord.Color.green()
            elif self._player_roll < self._dealer_roll:
                result_text = "😔 **DEALER WINS**"
                color = discord.Color.red()
            else:
                result_text = "🤝 **TIE - PUSH**"
                color = discord.Color.orange()
            
            embed = discord.Embed(
                title=f"{self.EMOJI} {self.NAME}",
                description=f"{result_text}\n\n🎲 **Your Roll:** {self.DICE_FACES[self._player_roll - 1]} ({self._player_roll})\n🎲 **Dealer Roll:** {self.DICE_FACES[self._dealer_roll - 1]} ({self._dealer_roll})",
                color=color
            )
            embed.add_field(name="Result", value=f"{self._player_roll} vs {self._dealer_roll}", inline=True)
        
        return embed

    async def _roll_dice(self, interaction: discord.Interaction):
        if self._player_roll is not None:
            return await interaction.response.defer()
        
        # Get current balance for display
        self._current_balance = await self.get_balance()
        
        # Roll the dice
        self._player_roll = random.randint(1, 6)
        self._dealer_roll = random.randint(1, 6)
        
        # Determine outcome and handle winnings
        if self._player_roll > self._dealer_roll:
            # Player wins
            payout = self.wager * 2
            await self.award_winnings(payout)
            result_text = "🎉 **YOU WIN!**"
            color = discord.Color.green()
        elif self._player_roll < self._dealer_roll:
            # Player loses
            result_text = "😔 **DEALER WINS**"
            color = discord.Color.red()
        else:
            # Tie - push
            await self.award_winnings(self.wager)
            result_text = "🤝 **TIE - PUSH**"
            color = discord.Color.orange()
        
        # Create custom result embed with game controls
        balance = await self.get_balance()
        
        # Create outcome for stats
        if self._player_roll > self._dealer_roll:
            outcome = GameOutcome(
                result=GameResult.WIN,
                wager=self.wager,
                payout=payout,
                multiplier=2.0,
                message=f"You rolled {self._player_roll} and beat the dealer's {self._dealer_roll}!",
                color=color
            )
        elif self._player_roll < self._dealer_roll:
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=self.wager,
                payout=0,
                multiplier=0,
                message=f"Dealer's {self._dealer_roll} beats your {self._player_roll}",
                color=color
            )
        else:
            outcome = GameOutcome(
                result=GameResult.PUSH,
                wager=self.wager,
                payout=self.wager,
                multiplier=1.0,
                message=f"Both rolled {self._player_roll}! It's a tie - wager returned.",
                color=color
            )
        
        # Create custom embed
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=f"{result_text}\n\n🎲 **Your Roll:** {self._player_roll}\n🎲 **Dealer Roll:** {self._dealer_roll}",
            color=color
        )
        embed.add_field(name="Wager", value=f"🪙 {self.wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,} coins", inline=True)
        embed.add_field(name="Result", value=f"{self._player_roll} vs {self._dealer_roll}", inline=True)
        
        # Create new game instance for immediate play
        new_game = self.__class__(self.guild_id, self.user_id, self.wager)
        new_game._current_balance = balance
        
        await self.record_game(outcome)
        await interaction.response.edit_message(embed=embed, view=new_game)

    async def _check_daily(self, interaction: discord.Interaction) -> tuple:
        from bot.database import games_db
        can_play, spent = await games_db.check_daily_limit(self.guild_id, self.user_id, self.wager)
        if not can_play:
            settings = await games_db.get_game_settings(self.guild_id)
            limit = settings.get("daily_limit", 5000)
            await interaction.response.send_message(f"Daily limit reached! {spent}/{limit}", ephemeral=True)
            return False, spent
        return True, spent


class ArkDiceResultView(discord.ui.View):
    """Custom result view for ARK Dice with Roll Again and Wager buttons"""
    
    def __init__(self, guild_id: int, user_id: int, game_class, wager: int, balance: int, stats: dict):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.game_class = game_class
        self.wager = wager
        self.balance = balance
        self.stats = stats

    @discord.ui.button(label="🎲 Roll Again", style=discord.ButtonStyle.success, row=0)
    async def roll_again_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Create new game instance with same wager
        new_game = self.game_class(self.guild_id, self.user_id, self.wager)
        
        # Check balance and deduct wager
        if not await new_game.ensure_balance(interaction):
            return
            
        if not await new_game.deduct_wager():
            return await interaction.response.send_message("Failed to process wager.", ephemeral=True)
        
        # Get updated balance
        new_game._current_balance = await new_game.get_balance()
        
        # Roll the dice directly
        await new_game._roll_dice(interaction)

    @discord.ui.button(label="💰 Change Wager", style=discord.ButtonStyle.primary, row=0)
    async def wager_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ArkDiceWagerModal(self))

    @discord.ui.button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=0)
    async def all_games_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from bot.cogs.games import PhoenixGameHubView
        embed = discord.Embed(title="🎮 Phoenix Game System", color=0xE74C3C)
        embed.add_field(name="Your Balance", value=f"🪙 {self.balance:,} coins", inline=False)
        view = PhoenixGameHubView(self.guild_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)


class ArkDiceWagerModal(discord.ui.Modal, title="Change Wager"):
    wager_input = discord.ui.TextInput(
        label="Wager Amount",
        placeholder="Enter wager amount",
        min_length=1,
        max_length=6
    )

    def __init__(self, game_view):
        super().__init__()
        self.game_view = game_view
        self.wager_input.default = str(int(game_view.wager))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            wager = int(self.wager_input.value)
            if wager < self.game_view.DEFAULT_WAGER:
                await interaction.response.send_message(
                    f"Minimum wager is {self.game_view.DEFAULT_WAGER} coins.",
                    ephemeral=True
                )
                return
            if wager > self.game_view.MAX_WAGER:
                await interaction.response.send_message(
                    f"Maximum wager is {self.game_view.MAX_WAGER} coins.",
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)
            return

        # Update the wager
        self.game_view.wager = wager
        
        # Update the embed with new wager and balance (stay in current game)
        embed = discord.Embed(
            title=f"{self.game_view.EMOJI} {self.game_view.NAME}",
            description="Click **Roll Dice** to play against the dealer!",
            color=discord.Color.blue()
        )
        embed.add_field(name="How to Play", value="🎲 Roll your dice vs dealer\n🏆 Higher roll wins 2x wager\n🤝 Tie = push (wager returned)", inline=False)
        embed.add_field(name="Wager", value=f"🪙 {wager} coins", inline=True)
        embed.add_field(name="Payout", value="2x if you win!", inline=True)
        
        await interaction.response.edit_message(embed=embed, view=self.game_view)
