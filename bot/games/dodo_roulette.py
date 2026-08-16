"""
Dodo Roulette - A classic Island pastime betting game.
Pick a color plate. If the Dodo waddles to your choice, you win!
Gold plates offer a rare 10x jackpot.
"""

import discord
import random
from bot.games.base import BaseGameView, GameResult, GameOutcome


class DodoRouletteView(BaseGameView):
    NAME = "Dodo Roulette"
    EMOJI = "🦤"
    DESCRIPTION = "Place your bets on the classic Island pastime!\n\n**Odds & Payouts:**\n🔴 Red: 1x (49%) - Most common, low payout\n🔵 Blue: 3x (28%) - Uncommon, medium payout\n🟢 Green: 5x (17%) - Rare, high payout\n✨ Gold: 10x (6%) - Ultra rare, jackpot!"
    DEFAULT_WAGER = 10

    OUTCOMES = ["Red", "Blue", "Green", "Gold"]
    WEIGHTS = [49, 28, 17, 6]
    MULTIPLIERS = {"Red": 1, "Blue": 3, "Green": 5, "Gold": 10}

    def __init__(self, guild_id: int, user_id: int, wager: int = None):
        super().__init__(guild_id, user_id, wager, timeout=None)
        self._winner = None
        self._current_balance = 0  # Set default balance
        self._add_control_buttons()
        # Remove the inherited wager button
        self._remove_inherited_wager_button()

    async def _initialize_balance(self):
        """Initialize balance when game starts"""
        self._current_balance = await self.get_balance()

    def start_game(self, balance: int = None):
        """Initialize game state when starting from GameIntroView"""
        if balance is not None:
            self._current_balance = balance
        return self._build_embed(), self

    def _remove_inherited_wager_button(self):
        """Remove the inherited wager button from the view"""
        for item in self.children[:]:
            if hasattr(item, 'label') and item.label == "💰 Wager":
                self.remove_item(item)
                break

    def _add_control_buttons(self):
        """Add wager and navigation buttons to the game"""
        # Add wager button
        wager_btn = discord.ui.Button(label="💰 Change Wager", style=discord.ButtonStyle.primary, row=1)
        wager_btn.callback = self._wager_modal
        self.add_item(wager_btn)
        
        # Add all games button
        games_btn = discord.ui.Button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=1)
        games_btn.callback = self._all_games
        self.add_item(games_btn)

    async def _wager_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(DodoRouletteWagerModal(self))

    async def _all_games(self, interaction: discord.Interaction):
        from bot.cogs.games import PhoenixGameHubView
        balance = await self.get_balance()
        embed = discord.Embed(title="🎮 Phoenix Game System", color=0xE74C3C)
        embed.add_field(name="Your Balance", value=f"🪙 {balance:,} coins", inline=False)
        view = PhoenixGameHubView(self.guild_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=self.DESCRIPTION,
            color=0xE74C3C
        )
        embed.add_field(name="Wager", value=f"🪙 {self.wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {self._current_balance:,} coins", inline=True)
        return embed

    async def _play(self, interaction: discord.Interaction, choice: str):
        if self._resolved:
            return

        has_balance = await self.ensure_balance(interaction)
        if not has_balance:
            return

        can_play, spent = await self._check_daily(interaction)
        if not can_play:
            return

        deducted = await self.deduct_wager()
        if not deducted:
            await interaction.response.send_message(
                "Failed to process wager. Please try again.",
                ephemeral=True
            )
            return

        self._winner = random.choices(self.OUTCOMES, weights=self.WEIGHTS)[0]
        multiplier = self.MULTIPLIERS[self._winner]

        if choice == self._winner:
            payout = self.wager * multiplier
            await self.award_winnings(payout)
            
            result = GameResult.JACKPOT if self._winner == "Gold" else GameResult.WIN
            outcome = GameOutcome(
                result=result,
                wager=self.wager,
                payout=payout,
                multiplier=multiplier,
                message=f"The Dodo waddled over to the **{self._winner}** plate!\n\n"
                        f"**YOU WIN!**\nReceived: **{payout}** coins",
                color=discord.Color.gold() if self._winner == "Gold" else discord.Color.green()
            )
        else:
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=self.wager,
                payout=0,
                multiplier=0,
                message=f"The Dodo waddled over to the **{self._winner}** plate.\n\n"
                        f"**YOU LOST!**\nBetter luck next time, Survivor.",
                color=discord.Color.red()
            )

        # Create custom result embed with game controls
        balance = await self.get_balance()
        stats = await self.get_stats()
        
        # Create custom embed
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=outcome.message,
            color=outcome.color
        )
        embed.add_field(name="Your Choice", value=choice, inline=True)
        embed.add_field(name="Winner", value=self._winner, inline=True)
        embed.add_field(name="Wager", value=f"🪙 {self.wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,} coins", inline=True)
        
        # Create new game instance for immediate play
        new_game = self.__class__(self.guild_id, self.user_id, self.wager)
        
        await self.record_game(outcome)
        await interaction.response.edit_message(embed=embed, view=new_game)

    async def _check_daily(self, interaction: discord.Interaction) -> tuple:
        from bot.database import games_db
        
        can_play, spent = await games_db.check_daily_limit(
            self.guild_id, self.user_id, self.wager
        )
        
        if not can_play:
            settings = await games_db.get_game_settings(self.guild_id)
            limit = settings.get("daily_limit", 5000)
            await interaction.response.send_message(
                f"You've reached your daily limit! Spent: {spent}/{limit} coins.",
                ephemeral=True
            )
            return False, spent
        return True, spent

    @discord.ui.button(label="Red", style=discord.ButtonStyle.danger, row=0)
    async def red_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "Red")

    @discord.ui.button(label="Blue", style=discord.ButtonStyle.primary, row=0)
    async def blue_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "Blue")

    @discord.ui.button(label="Green", style=discord.ButtonStyle.success, row=0)
    async def green_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "Green")

    @discord.ui.button(label="Gold", style=discord.ButtonStyle.secondary, emoji="✨", row=0)
    async def gold_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "Gold")


class DodoRouletteWagerModal(discord.ui.Modal, title="Change Wager"):
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
        
        # Get current balance
        balance = await self.game_view.get_balance()
        
        # Update the embed with new wager and balance (stay in current game)
        embed = discord.Embed(
            title=f"{self.game_view.EMOJI} {self.game_view.NAME}",
            description=self.game_view.DESCRIPTION,
            color=0xE74C3C
        )
        embed.add_field(name="Wager", value=f"🪙 {wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,} coins", inline=True)
        
        await interaction.response.edit_message(embed=embed, view=self.game_view)