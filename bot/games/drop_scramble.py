import discord
import random
import asyncio
from bot.games.base import BaseGameView, GameResult, GameOutcome

class DropScrambleView(BaseGameView):
    NAME = "Drop Scramble"
    EMOJI = "📦"
    DESCRIPTION = "Fastest hands in the ARK!\nClick Claim within 2 seconds to win!"
    DEFAULT_WAGER = 10

    LOOT_TIERS = [
        ("Common", 5, 0.45, discord.Color.light_gray()),
        ("Uncommon", 15, 0.30, discord.Color.green()),
        ("Rare", 30, 0.18, discord.Color.blue()),
        ("Legendary", 75, 0.07, discord.Color.gold()),
    ]

    def __init__(self, guild_id: int, user_id: int, wager: int = None):
        super().__init__(guild_id, user_id, wager, timeout=None)
        self._claimed = False
        self._loot = None
        self._started = False
        self._message = None

    @discord.ui.button(label="Start Drop", style=discord.ButtonStyle.success, row=0)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._resolved or self._started:
            return await interaction.response.defer()

        if not await self.ensure_balance(interaction) or not (await self._check_daily(interaction))[0]:
            return
            
        if not await self.deduct_wager():
            return await interaction.response.send_message("Failed to process wager.", ephemeral=True)

        self._started = True
        self._loot = random.choices(self.LOOT_TIERS, weights=[t[2] for t in self.LOOT_TIERS])[0]

        button.disabled = True
        embed = discord.Embed(title=f"{self.EMOJI} {self.NAME}", description="**GET READY!**", color=discord.Color.orange())
        
        await interaction.response.edit_message(embed=embed, view=self)
        self._message = await interaction.original_response()

        await asyncio.sleep(random.uniform(1.5, 4.0))
        
        if self._resolved:
            return

        self.claim_btn.disabled = False
        embed.description = "**DROP INCOMING!**\nClick **Claim** now!"
        embed.color = discord.Color.gold()
        await self._message.edit(embed=embed, view=self)

        await asyncio.sleep(2.0)
        if not self._claimed and not self._resolved:
            self._resolved = True
            self.claim_btn.disabled = True
            await self._message.edit(content="Too slow! The drop vanished.", embed=None, view=self)

    @discord.ui.button(label="Claim!", style=discord.ButtonStyle.success, emoji="📦", row=0, disabled=True)
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This isn't your drop!", ephemeral=True)
        
        if self._resolved or self._claimed:
            return await interaction.response.defer()

        self._claimed = self._resolved = True
        
        tier_name, payout_bonus, _, color = self._loot
        total = self.wager + payout_bonus
        await self.award_winnings(total)

        outcome = GameOutcome(
            result=GameResult.WIN, wager=self.wager, payout=total,
            multiplier=total / self.wager if self.wager > 0 else 0,
            message=f"You snagged a **{tier_name}** drop!", color=color
        )
        await self.resolve_game(interaction, outcome)

    async def _check_daily(self, interaction: discord.Interaction) -> tuple:
        from bot.database import games_db
        can_play, spent = await games_db.check_daily_limit(self.guild_id, self.user_id, self.wager)
        if not can_play:
            settings = await games_db.get_game_settings(self.guild_id)
            limit = settings.get("daily_limit", 5000)
            await interaction.response.send_message(f"Daily limit reached! {spent}/{limit}", ephemeral=True)
            return False, spent
        return True, spent