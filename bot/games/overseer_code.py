"""
Overseer Code Breaker - Crack the Overseer's color code.
A Mastermind-style logic puzzle. Guess the 4-color pattern.
"""

import discord
from bot.games.base import BaseGameView, GameResult, GameOutcome


class OverseerCodeView(BaseGameView):
    NAME = "Overseer Code Breaker"
    EMOJI = "💻"
    DESCRIPTION = "Crack the code to win coins! Free to play!\n4 colors (no repeats), 6 options, 9 guesses | 10-100 coins"
    DEFAULT_WAGER = 0

    COLORS = {
        "red": {"emoji": "🔴", "name": "Red"},
        "orange": {"emoji": "🟠", "name": "Orange"},
        "yellow": {"emoji": "🟡", "name": "Yellow"},
        "green": {"emoji": "🟢", "name": "Green"},
        "blue": {"emoji": "🔵", "name": "Blue"},
        "purple": {"emoji": "🟣", "name": "Purple"},
    }
    COLOR_ORDER = ["red", "orange", "yellow", "green", "blue", "purple"]

    def __init__(self, guild_id: int, user_id: int, wager: int = None):
        import random
        super().__init__(guild_id, user_id, wager or 0, timeout=None)
        self._secret_code = random.sample(list(self.COLORS.keys()), 4)
        self._current_guess = [None, None, None, None]
        self._current_slot = 0  # Initialize current slot
        self._guesses = []
        self._resolved = False
        self._max_attempts = 9
        # Add all games button
        self._add_all_games_button()
        # Remove inherited wager button since this is a free game
        self._remove_inherited_wager_button()

    def _add_all_games_button(self):
        """Add all games button for navigation"""
        games_btn = discord.ui.Button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=2)
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

    def _remove_inherited_wager_button(self):
        """Remove the inherited wager button from the view"""
        items_to_remove = []
        for item in self.children[:]:
            if hasattr(item, 'label') and ("Wager" in item.label or "wager" in item.label or "💰" in item.label):
                items_to_remove.append(item)
        
        for item in items_to_remove:
            self.remove_item(item)

    def start_game(self):
        """Initialize game state when starting from GameIntroView"""
        return self._build_embed(), self

    def _build_embed(self):
        lines = ["**Break the 4-color code!** (no repeated colors)"]
        lines.append("")
        
        current_slot = next((i for i, c in enumerate(self._current_guess) if c is None), 4)
        code_display = " ".join(
            self.COLORS[c]["emoji"] if c else "⚫" for c in self._current_guess
        )
        lines.append(f"Your guess: {code_display}  (Slot {current_slot + 1}/4)")
        
        if self._guesses:
            lines.append("")
            lines.append("__Previous Guesses__")
            lines.append("⚫ = Correct color & position  |  🟤 = Correct color, wrong position  |  ⚪ = Wrong color")
            lines.append("")
            for guess, correct_pos, correct_color in self._guesses:
                guess_emoji = " ".join(self.COLORS[c]["emoji"] for c in guess)
                wrong_pos = correct_color - correct_pos
                
                result = "⚫" * correct_pos + "🟤" * wrong_pos
                result = result.ljust(4, "⚪")
                
                lines.append(f"{guess_emoji}  →  {result}")
        
        lines.append("")
        lines.append(f"Attempt {len(self._guesses) + 1}/{self._max_attempts}")
        
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description="\n".join(lines),
            color=discord.Color.blue()
        )
        return embed

    async def _press_color(self, interaction: discord.Interaction, color: str):
        if self._resolved:
            return

        if color in self._current_guess:
            await interaction.response.send_message(
                "Each color can only be used once per guess!", ephemeral=True
            )
            return

        if self._current_slot < 4:
            self._current_guess[self._current_slot] = color
            self._current_slot += 1
            
            if self._current_slot == 4:
                await self._check_guess(interaction)
            else:
                await interaction.response.edit_message(embed=self._build_embed(), view=self)
        else:
            await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def _check_guess(self, interaction: discord.Interaction):
        guess = self._current_guess.copy()
        
        correct_pos = sum(a == b for a, b in zip(guess, self._secret_code))
        
        secret_counts = {}
        for c in self._secret_code:
            secret_counts[c] = secret_counts.get(c, 0) + 1
        
        guess_counts = {}
        for c in guess:
            guess_counts[c] = guess_counts.get(c, 0) + 1
        
        correct_color = sum(
            min(guess_counts.get(c, 0), secret_counts.get(c, 0)) 
            for c in secret_counts
        )
        
        self._guesses.append((guess, correct_pos, correct_color))
        
        if correct_pos == 4:
            attempts = len(self._guesses)
            if attempts <= 3:
                payout = 100
            elif attempts <= 6:
                payout = 50
            else:
                payout = 10
            await self.award_winnings(payout)
            code_emoji = " ".join(self.COLORS[c]["emoji"] for c in self._secret_code)
            outcome = GameOutcome(
                result=GameResult.JACKPOT if payout >= 50 else GameResult.WIN,
                wager=0,
                payout=payout,
                multiplier=0,
                message=f"**CODE CRACKED!**\n\nThe code was: {code_emoji}\nAttempts: {attempts}/{self._max_attempts}\n\n{'🎉 BRILLIANT! 🎉' if payout == 100 else 'Great job!'}\nReceived: **{payout}** coins",
                color=discord.Color.gold() if payout >= 50 else discord.Color.green()
            )
            await self.resolve_game(interaction, outcome)
            return
        
        if len(self._guesses) >= self._max_attempts:
            code_emoji = " ".join(self.COLORS[c]["emoji"] for c in self._secret_code)
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=0,
                payout=0,
                multiplier=0,
                message=f"**SYSTEM LOCKOUT!**\n\nThe code was: {code_emoji}\n\nBetter luck next time, Survivor.",
                color=discord.Color.red()
            )
            await self.resolve_game(interaction, outcome)
            return
        
        self._current_guess = [None, None, None, None]
        self._current_slot = 0
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def _clear(self, interaction: discord.Interaction):
        if self._resolved:
            return
        self._current_guess = [None, None, None, None]
        self._current_slot = 0
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    async def _check_daily(self, interaction: discord.Interaction) -> tuple:
        from bot.database import games_db
        
        can_play, spent = await games_db.check_daily_limit(
            self.guild_id, self.user_id, self.wager
        )
        
        if not can_play:
            settings = await games_db.get_game_settings(self.guild_id)
            limit = settings.get("daily_limit", 5000)
            await interaction.response.send_message(
                f"Daily limit reached! Spent: {spent}/{limit} coins.",
                ephemeral=True
            )
            return False, spent
        return True, spent

    @discord.ui.button(label="🔴", style=discord.ButtonStyle.secondary, row=0)
    async def btn_red(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._press_color(interaction, "red")

    @discord.ui.button(label="🟠", style=discord.ButtonStyle.secondary, row=0)
    async def btn_orange(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._press_color(interaction, "orange")

    @discord.ui.button(label="🟡", style=discord.ButtonStyle.secondary, row=0)
    async def btn_yellow(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._press_color(interaction, "yellow")

    @discord.ui.button(label="🟢", style=discord.ButtonStyle.secondary, row=1)
    async def btn_green(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._press_color(interaction, "green")

    @discord.ui.button(label="🔵", style=discord.ButtonStyle.secondary, row=1)
    async def btn_blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._press_color(interaction, "blue")

    @discord.ui.button(label="🟣", style=discord.ButtonStyle.secondary, row=1)
    async def btn_purple(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._press_color(interaction, "purple")

    @discord.ui.button(label="Clear", style=discord.ButtonStyle.danger, row=2)
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._clear(interaction)
