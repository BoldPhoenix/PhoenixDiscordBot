"""
Alpha Hunt - Stare down a predator and live to tell the tale.
Combat standoff. Choose your weapon to beat the Alpha's health roll.
"""

import discord
import random
from bot.games.base import BaseGameView, GameResult, GameOutcome


class AlphaHuntView(BaseGameView):
    NAME = "Alpha Hunt"
    EMOJI = "🦖"
    DESCRIPTION = "Stare down a predator and live to tell the tale!\nPike: 2x (safer) | Longneck: 4x (riskier)"
    DEFAULT_WAGER = 10

    ALPHAS = [
        {"name": "Alpha Raptor", "hp_range": (2000, 4000)},
        {"name": "Alpha Carno", "hp_range": (4000, 6000)},
        {"name": "Alpha Rex", "hp_range": (6000, 9000)},
    ]

    WEAPONS = {
        "pike": {"damage_range": (1500, 3500), "multiplier": 2.0, "emoji": "🔱"},
        "longneck": {"damage_range": (1000, 5000), "multiplier": 4.0, "emoji": "🔫"},
    }

    def __init__(self, guild_id: int, user_id: int, wager: int = None):
        super().__init__(guild_id, user_id, wager, timeout=None)
        self._alpha = random.choice(self.ALPHAS)
        self._alpha_hp = random.randint(*self._alpha["hp_range"])
        self._current_balance = 0  # Initialize balance
        self._add_control_buttons()
        # Remove inherited wager button
        self._remove_inherited_wager_button()

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
        """Open wager change modal"""
        await interaction.response.send_modal(AlphaHuntWagerModal(self))

    async def _all_games(self, interaction: discord.Interaction):
        """Return to game selection"""
        balance = await self.get_balance()
        embed = discord.Embed(
            title="🎮 Phoenix ARK Games",
            description="Select a game to play!",
            color=discord.Color.blue()
        )
        embed.add_field(name="Your Balance", value=f"🪙 {balance:,} coins", inline=False)
        from bot.cogs.games import PhoenixGameHubView
        view = PhoenixGameHubView(self.guild_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view)

    def start_game(self, balance: int = None):
        """Initialize game state when starting from GameIntroView"""
        if balance is not None:
            self._current_balance = balance
        return self._build_embed(), self

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=f"{self.DESCRIPTION}\n\nYou encounter a **{self._alpha['name']}** (HP: {self._alpha_hp})!",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="Wager", value=f"🪙 {self.wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {self._current_balance:,} coins", inline=True)
        return embed

    async def _attack(self, interaction: discord.Interaction, weapon: str):
        if self._resolved:
            return

        has_balance = await self.ensure_balance(interaction)
        if not has_balance:
            return

        can_play, _ = await self._check_daily(interaction)
        if not can_play:
            return

        deducted = await self.deduct_wager()
        if not deducted:
            await interaction.response.send_message(
                "Failed to process wager.", ephemeral=True
            )
            return

        wp = self.WEAPONS[weapon]
        damage = random.randint(*wp["damage_range"])
        
        # Get current balance
        balance = await self.get_balance()

        if damage >= self._alpha_hp:
            payout = int(self.wager * wp["multiplier"])
            await self.award_winnings(payout)
            balance += payout  # Update balance after winning
            
            outcome = GameOutcome(
                result=GameResult.WIN,
                wager=self.wager,
                payout=payout,
                multiplier=wp["multiplier"],
                message=f"You encountered a **{self._alpha['name']}** (HP: {self._alpha_hp})!\n\n"
                       f"{wp['emoji']} {weapon.title()} deals **{damage}** damage!\n\n"
                       f"**VICTORY!**\nReceived: **{payout}** coins",
                color=discord.Color.green()
            )
        else:
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=self.wager,
                payout=0,
                multiplier=0,
                message=f"You encountered a **{self._alpha['name']}** (HP: {self._alpha_hp})!\n\n"
                       f"{wp['emoji']} {weapon.title()} deals **{damage}** damage!\n\n"
                       f"**DEFEATED!**\nThe Alpha survived your attack.",
                color=discord.Color.red()
            )

        # Create custom embed with result
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=outcome.message,
            color=outcome.color
        )
        embed.add_field(name="Weapon", value=f"{wp['emoji']} {weapon.title()}", inline=True)
        embed.add_field(name="Wager", value=f"🪙 {self.wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,} coins", inline=True)
        
        # Create new game instance for immediate play
        new_game = self.__class__(self.guild_id, self.user_id, self.wager)
        new_game._current_balance = balance
        
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
                f"Daily limit reached! Spent: {spent}/{limit} coins.",
                ephemeral=True
            )
            return False, spent
        return True, spent

    @discord.ui.button(label="Pike (2x / Safe)", style=discord.ButtonStyle.success, row=0)
    async def pike_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._attack(interaction, "pike")

    @discord.ui.button(label="Longneck (4x / Risky)", style=discord.ButtonStyle.danger, row=0)
    async def longneck_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._attack(interaction, "longneck")


class AlphaHuntWagerModal(discord.ui.Modal, title="Change Wager"):
    wager_input = discord.ui.TextInput(
        label="Wager Amount",
        placeholder="Enter wager amount",
        min_length=1,
        max_length=6
    )

    def __init__(self, game_view):
        super().__init__()
        self.game_view = game_view
        # Set current wager as default value
        self.wager_input.default = str(game_view.wager)

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
            description=f"{self.game_view.DESCRIPTION}\n\nYou encounter a **{self.game_view._alpha['name']}** (HP: {self.game_view._alpha_hp})!",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="Wager", value=f"🪙 {wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,} coins", inline=True)
        
        await interaction.response.edit_message(embed=embed, view=self.game_view)
