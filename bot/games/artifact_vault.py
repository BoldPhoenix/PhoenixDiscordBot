"""
Artifact Vault - Decode the hints of the Ancients.
Read the lore hint to identify which pedestal contains the hidden credits.
Free to play!
"""

import discord
import random
from bot.games.base import BaseGameView, GameResult, GameOutcome


class ArtifactVaultView(BaseGameView):
    NAME = "Artifact Vault"
    EMOJI = "🏺"
    DESCRIPTION = "Decode the hints of the Ancients!\nFree to play | Win 15 coins!"
    DEFAULT_WAGER = 0

    HINTS = [
        ("The artifact glows brightest in the darkness.", 2),
        ("The oldest pedestal holds the newest secret.", 1),
        ("What lies beneath is often forgotten.", 3),
        ("The center cannot hold forever.", 2),
        ("Left is right when shadows fall.", 1),
        ("The third time is the charm.", 3),
        ("Between two worlds lies the truth.", 2),
    ]

    def __init__(self, guild_id: int, user_id: int, wager: int = None):
        super().__init__(guild_id, user_id, wager, timeout=None)
        self._correct_pedestal = random.randint(1, 3)
        self._hint = random.choice(self.HINTS)
        # Remove inherited wager button since this is a free game
        self._remove_inherited_wager_button()
        # Add all games button for navigation
        self._add_all_games_button()

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

    def start_game(self):
        """Initialize game state when starting from GameIntroView"""
        return self._build_embed(), self

    def _build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=f"*{self._hint[0]}*\n\nChoose a pedestal!",
            color=discord.Color.blue()
        )
        return embed

    async def _choose_pedestal(self, interaction: discord.Interaction, choice: int):
        if self._resolved:
            return

        if choice == self._correct_pedestal:
            payout = 15
            await self.award_winnings(payout)
            
            outcome = GameOutcome(
                result=GameResult.WIN,
                wager=0,
                payout=payout,
                multiplier=0,
                message=f"Pedestal **{choice}** opens to reveal ancient treasures!\n\n**YOU WIN!**\nReceived: **{payout}** coins",
                color=discord.Color.gold()
            )
        else:
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=0,
                payout=0,
                multiplier=0,
                message=f"Pedestal **{choice}** is empty!\nThe treasure was in pedestal **{self._correct_pedestal}**.",
                color=discord.Color.red()
            )

        # Create custom embed with result
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=outcome.message,
            color=outcome.color
        )
        
        # Create new game instance for immediate play
        new_game = self.__class__(self.guild_id, self.user_id)
        
        await self.record_game(outcome)
        await interaction.response.edit_message(embed=embed, view=new_game)

    @discord.ui.button(label="Pedestal 1", style=discord.ButtonStyle.secondary, row=0)
    async def pedestal_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._choose_pedestal(interaction, 1)

    @discord.ui.button(label="Pedestal 2", style=discord.ButtonStyle.secondary, row=0)
    async def pedestal_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._choose_pedestal(interaction, 2)

    @discord.ui.button(label="Pedestal 3", style=discord.ButtonStyle.secondary, row=0)
    async def pedestal_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._choose_pedestal(interaction, 3)
