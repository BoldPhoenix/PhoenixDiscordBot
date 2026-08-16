"""
Cryo Gamble - What's frozen inside the pod?
The ultimate mystery box. Open a pod for random rewards.
"""

import discord
import random
from bot.games.base import BaseGameView, GameResult, GameOutcome


class CryoGambleView(BaseGameView):
    NAME = "Cryo Gamble"
    EMOJI = "❄️"
    DESCRIPTION = "What's frozen inside the pod?\n0.5x-10x multiplier based on creature rarity"
    DEFAULT_WAGER = 10

    CREATURES = [
        ("Phiomia", 0.5, 0.30, discord.Color.light_gray()),
        ("Parasaur", 1.0, 0.30, discord.Color.green()),
        ("Raptor", 1.5, 0.20, discord.Color.blue()),
        ("Carno", 2.0, 0.10, discord.Color.purple()),
        ("Rex", 4.0, 0.07, discord.Color.gold()),
        ("Giganotosaurus", 10.0, 0.03, discord.Color.red()),
    ]

    def __init__(self, guild_id: int, user_id: int, wager: int = None):
        super().__init__(guild_id, user_id, wager, timeout=None)
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
        await interaction.response.send_modal(CryoGambleWagerModal(self))

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
            description=self.DESCRIPTION,
            color=discord.Color.blue()
        )
        embed.add_field(name="Wager", value=f"🪙 {self.wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {self._current_balance:,} coins", inline=True)
        return embed

    async def _open_cryo(self, interaction: discord.Interaction):
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

        creature, multiplier, weight, color = random.choices(
            self.CREATURES, weights=[c[2] for c in self.CREATURES]
        )[0]

        payout = int(self.wager * multiplier)
        
        # Get current balance
        balance = await self.get_balance()
        
        if payout > 0:
            await self.award_winnings(payout)
            balance += payout  # Update balance after winning
            
            result = GameResult.JACKPOT if multiplier >= 5 else GameResult.WIN
            outcome = GameOutcome(
                result=result,
                wager=self.wager,
                payout=payout,
                multiplier=multiplier,
                message=f"The cryopod opens to reveal...\n\n"
                       f"**{creature}**!\n\n"
                       f"{'🎉 LEGENDARY! 🎉' if multiplier >= 5 else 'YOU WIN!'}\n"
                       f"Received: **{payout}** coins ({multiplier}x)",
                color=color
            )
        else:
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=self.wager,
                payout=0,
                multiplier=0,
                message=f"The cryopod opens to reveal...\n\n"
                       f"A dead **{creature}**!\n\n**YOU LOST!**",
                color=discord.Color.dark_gray()
            )

        # Create custom embed with result
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=outcome.message,
            color=outcome.color
        )
        embed.add_field(name="Creature", value=creature, inline=True)
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

    @discord.ui.button(label="Open Cryopod", style=discord.ButtonStyle.primary, emoji="❄️", row=0)
    async def open_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_cryo(interaction)


class CryoGambleWagerModal(discord.ui.Modal, title="Change Wager"):
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
            description=self.game_view.DESCRIPTION,
            color=discord.Color.blue()
        )
        embed.add_field(name="Wager", value=f"🪙 {wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,} coins", inline=True)
        
        await interaction.response.edit_message(embed=embed, view=self.game_view)
