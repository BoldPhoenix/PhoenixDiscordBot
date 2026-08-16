"""
bot/cogs/arcade.py
The Complete Phoenix Arcade: Minigames for your ARK Community.
Includes: Slots, PVP Wager, Roulette, Coinflip, Blackjack, Racing, Hatchery, and Trivia.
"""

import discord
import random
import asyncio
import logging
from discord.ext import commands
from discord import app_commands
from bot.utils.subscription_checker import check_feature
from bot.utils.economy import (
    ensure_economy_table,
    get_balance,
    update_balance,
    log_item_win,
    can_claim_daily,
    update_daily_claim,
    get_stats,
)

logger = logging.getLogger("PhoenixArcade")

# --- DATA & CONFIG ---
TRIVIA_QUESTIONS = [
    {
        "q": "What allows you to breathe underwater in ARK?",
        "a": "Lazarus Chowder",
        "options": ["Lazarus Chowder", "Fria Curry", "Enduro Stew"],
    },
    {
        "q": "Which dino gathers berries the most efficiently?",
        "a": "Brontosaurus",
        "options": ["Trike", "Brontosaurus", "Stegosaurus"],
    },
    {
        "q": "What is the max level for wild dinos on official difficulty?",
        "a": "150",
        "options": ["120", "150", "180"],
    },
    {
        "q": "Which artifact is found in the Lower South Cave?",
        "a": "Hunter",
        "options": ["Hunter", "Massive", "Skylord"],
    },
    {
        "q": "What kibble does a Rex prefer?",
        "a": "Exceptional",
        "options": ["Superior", "Exceptional", "Regular"],
    },
    {
        "q": "What element is needed to craft Tek structures?",
        "a": "Element",
        "options": ["Crystal", "Element", "Metal Ingot"],
    },
    {
        "q": "Which map features the desert biome?",
        "a": "Scorched Earth",
        "options": ["The Island", "Scorched Earth", "Aberration"],
    },
    {
        "q": "What is the spawn command prefix in ARK?",
        "a": "cheat",
        "options": ["admin", "cheat", "spawn"],
    },
]


# --- VIEWS (BUTTONS) ---


class WagerView(discord.ui.View):
    """Accept/Deny view for PVP Wagers"""

    def __init__(self, challenger, opponent, amount):
        super().__init__(timeout=None)
        self.challenger = challenger
        self.opponent = opponent
        self.amount = amount
        self.accepted = False

    @discord.ui.button(label="Accept Wager", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message(
                "âŒ This wager isn't for you.", ephemeral=True
            )

        # Double check opponent funds (in case they spent it while waiting)
        bal = await get_balance(self.opponent.id)
        if bal < self.amount:
            return await interaction.response.send_message(
                "âŒ You don't have enough coins anymore!", ephemeral=True
            )

        self.accepted = True
        # Disable buttons
        for child in self.children:
            child.disabled = True

        # Execute Flip
        winner = random.choice([self.challenger, self.opponent])
        loser = self.opponent if winner == self.challenger else self.challenger

        # Deduct from opponent
        await update_balance(self.opponent.id, -self.amount)

        # Give pot to winner (Amount * 2)
        pot = self.amount * 2
        await update_balance(winner.id, pot, is_win=True)
        # Log loss for loser
        await update_balance(loser.id, 0, is_win=False)

        embed = discord.Embed(title="âš”ï¸ PVP Wager Result", color=discord.Color.gold())
        embed.description = (
            f"**{self.challenger.name}** vs **{self.opponent.name}**\nPot: **{pot}** Coins"
        )
        embed.add_field(
            name="Result", value=f"ðŸª™ The coin landed for... **{winner.name.upper()}**!"
        )

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id and interaction.user.id != self.challenger.id:
            return await interaction.response.send_message("âŒ Not your wager.", ephemeral=True)

        # Refund Challenger
        await update_balance(self.challenger.id, self.amount)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"âŒ Wager declined by {interaction.user.name}. Coins refunded.", view=self
        )
        self.stop()


class BlackjackView(discord.ui.View):
    """Interactive Buttons for Blackjack"""

    def __init__(self, user_id, bet, game_instance):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.bet = bet
        self.game = game_instance

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.success)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        await self.game.player_hit(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        await self.game.player_stand(interaction)
        self.stop()


class SupplyDropView(discord.ui.View):
    """Button for the Supply Drop Event"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="CLAIM DROP", style=discord.ButtonStyle.primary, emoji="ðŸŽ")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        button.label = f"Claimed by {interaction.user.name}"
        button.style = discord.ButtonStyle.secondary

        reward = random.randint(200, 500)
        await update_balance(interaction.user.id, reward, is_win=True)

        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"ðŸŽ‰ **{interaction.user.mention}** grabbed the Supply Drop and found **{reward}** Coins!",
            ephemeral=False,
        )
        self.stop()


# --- BLACKJACK LOGIC ---
class BlackjackGame:
    def __init__(self, user, bet):
        self.user = user
        self.bet = bet
        self.deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
        random.shuffle(self.deck)
        self.player_hand = [self.draw(), self.draw()]
        self.dealer_hand = [self.draw(), self.draw()]
        self.message = None

    def draw(self):
        return (
            self.deck.pop()
            if self.deck
            else random.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11])
        )

    def calculate(self, hand):
        score = sum(hand)
        aces = hand.count(11)
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    def get_embed(self, show_dealer=False):
        p_score = self.calculate(self.player_hand)
        d_hand_str = (
            f"{self.dealer_hand} (Score: {self.calculate(self.dealer_hand)})"
            if show_dealer
            else f"[{self.dealer_hand[0]}, ?]"
        )
        embed = discord.Embed(title="ðŸƒ Blackjack", color=discord.Color.dark_red())
        embed.add_field(
            name=f"{self.user.name}'s Hand",
            value=f"{self.player_hand}\nScore: **{p_score}**",
            inline=True,
        )
        embed.add_field(name="Dealer's Hand", value=d_hand_str, inline=True)
        return embed

    async def player_hit(self, interaction):
        self.player_hand.append(self.draw())
        if self.calculate(self.player_hand) > 21:
            await update_balance(self.user.id, 0, is_win=False)
            embed = self.get_embed(show_dealer=True)
            embed.description = "âŒ **BUST!** You went over 21."
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.edit_message(embed=self.get_embed(show_dealer=False))

    async def player_stand(self, interaction):
        while self.calculate(self.dealer_hand) < 17:
            self.dealer_hand.append(self.draw())
        p, d = self.calculate(self.player_hand), self.calculate(self.dealer_hand)
        embed = self.get_embed(show_dealer=True)

        if d > 21 or p > d:
            winnings = self.bet * 2
            await update_balance(self.user.id, winnings, is_win=True)
            embed.description = f"âœ… **YOU WIN!** You won {winnings} coins!"
        elif p == d:
            await update_balance(self.user.id, self.bet, is_win=None)
            embed.description = "âš–ï¸ **PUSH.** Money returned."
        else:
            await update_balance(self.user.id, 0, is_win=False)
            embed.description = "âŒ **DEALER WINS.**"
        await interaction.response.edit_message(embed=embed, view=None)


# --- MAIN COG ---


class PhoenixArcade(commands.Cog):
    """Phoenix Arcade - Community minigames and economy system"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        """Initialize arcade tables on cog load"""
        await ensure_economy_table()
        logger.info("ðŸŽ° Phoenix Arcade loaded & Database checked.")

    def create_embed(self, title, description, color=discord.Color.gold()):
        """Create a standardized arcade embed"""
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text="Phoenix Arcade ðŸŽ°")
        return embed

    # ==========================
    # ðŸ’° CORE ECONOMY
    # ==========================
    @app_commands.command(
        name="wallet", description="Check your Phoenix Coin balance and arcade stats"
    )
    async def wallet(self, interaction: discord.Interaction):
        """Check your coin balance and stats"""
        if not await check_feature(interaction, "games"):
            return
        coins = await get_balance(interaction.user.id)
        stats = await get_stats(interaction.user.id)

        embed = self.create_embed("ðŸ’° Your Wallet", f"Balance: **{coins:,}** Phoenix Coins")
        embed.add_field(
            name="ðŸ“Š Stats",
            value=f"Wins: **{stats['wins']}** | Losses: **{stats['losses']}**",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="daily", description="Claim your daily 100 coins")
    async def daily(self, interaction: discord.Interaction):
        """Claim daily coin reward"""
        if not await check_feature(interaction, "games"):
            return
        if not await can_claim_daily(interaction.user.id):
            return await interaction.response.send_message(
                "âŒ You already claimed your daily reward! Come back in 24 hours.", ephemeral=True
            )

        new_bal = await update_balance(interaction.user.id, 100, is_win=None)
        await update_daily_claim(interaction.user.id)
        embed = self.create_embed(
            "ðŸŒž Daily Reward", f"You claimed **100** coins!\nNew Balance: **{new_bal:,}**"
        )
        await interaction.response.send_message(embed=embed)

    # ==========================
    # ðŸŽ° GAME 1: DODO SLOTS
    # ==========================
    @app_commands.command(name="slots", description="Spin the Dodo Slots")
    @app_commands.describe(bet="Amount of coins to bet (default: 10)")
    async def slots(self, interaction: discord.Interaction, bet: int = 10):
        """Play the slot machine"""
        if not await check_feature(interaction, "games"):
            return
        user = interaction.user

        # Validation
        current_bal = await get_balance(user.id)
        if current_bal < bet:
            return await interaction.response.send_message(
                f"âŒ You need {bet} coins.", ephemeral=True
            )
        if bet <= 0:
            return await interaction.response.send_message(
                "âŒ Bet must be positive.", ephemeral=True
            )

        # Take money
        await update_balance(user.id, -bet, is_win=None)

        # Spin logic
        emojis = ["ðŸ¦•", "ðŸ¥š", "ðŸ¥©", "ðŸ’Ž", "ðŸ’©"]
        a, b, c = random.choices(emojis, k=3)

        # Animation
        await interaction.response.send_message(
            f"ðŸŽ° **{user.name}** bets **{bet}**...\n[ â“ | â“ | â“ ]"
        )
        msg = await interaction.original_response()
        await asyncio.sleep(0.5)
        await msg.edit(content=f"ðŸŽ° **{user.name}** bets **{bet}**...\n[ {a} | â“ | â“ ]")
        await asyncio.sleep(0.5)
        await msg.edit(content=f"ðŸŽ° **{user.name}** bets **{bet}**...\n[ {a} | {b} | â“ ]")
        await asyncio.sleep(0.5)

        # Payout
        result_text = f"[ {a} | {b} | {c} ]"

        if a == b == c:  # Jackpot
            if a == "ðŸ’Ž":
                multiplier = 50
            elif a == "ðŸ’©":
                multiplier = 0
            else:
                multiplier = 10

            winnings = bet * multiplier
            await update_balance(user.id, winnings, is_win=True)
            final_msg = (
                f"{result_text}\nðŸ’© **POOP JACKPOT!** You win nothing."
                if multiplier == 0
                else f"{result_text}\nðŸš¨ **JACKPOT!** You won **{winnings}** coins! ðŸš¨"
            )

        elif a == b or b == c or a == c:  # 2 Match
            winnings = int(bet * 1.5)
            await update_balance(user.id, winnings, is_win=True)
            final_msg = f"{result_text}\nâœ… **Nice!** Match 2. You won **{winnings}** coins."
        else:
            await update_balance(user.id, 0, is_win=False)
            final_msg = f"{result_text}\nâŒ **Bust.**"

        await msg.edit(content=final_msg)

    # ==========================
    # ðŸª™ GAME 2: COIN FLIP (VS BOT)
    # ==========================
    @app_commands.command(
        name="coinflip", description="Heads or Tails vs House (Double or Nothing)"
    )
    @app_commands.describe(choice="Choose heads or tails", bet="Amount to wager")
    async def coinflip(self, interaction: discord.Interaction, choice: str, bet: int):
        """Flip a coin against the house"""
        if not await check_feature(interaction, "games"):
            return
        user = interaction.user
        valid_choices = ["heads", "tails", "h", "t"]
        if choice.lower() not in valid_choices:
            return await interaction.response.send_message(
                "âŒ Pick 'heads' or 'tails'.", ephemeral=True
            )

        bal = await get_balance(user.id)
        if bal < bet:
            return await interaction.response.send_message("âŒ Insufficient funds.", ephemeral=True)
        if bet <= 0:
            return await interaction.response.send_message(
                "âŒ Bet must be positive.", ephemeral=True
            )

        await update_balance(user.id, -bet)

        result = random.choice(["heads", "tails"])
        user_pick = "heads" if choice.lower().startswith("h") else "tails"

        if user_pick == result:
            winnings = bet * 2
            await update_balance(user.id, winnings, is_win=True)
            await interaction.response.send_message(
                f"ðŸª™ It was **{result.upper()}**! You won **{winnings}** coins!"
            )
        else:
            await update_balance(user.id, 0, is_win=False)
            await interaction.response.send_message(
                f"ðŸª™ It was **{result.upper()}**. You lost **{bet}** coins."
            )

    # ==========================
    # âš”ï¸ GAME 3: PVP WAGER
    # ==========================
    @app_commands.command(
        name="wager", description="Challenge another player to a coin flip for coins"
    )
    @app_commands.describe(opponent="Player to challenge", amount="Amount to wager")
    async def wager(self, interaction: discord.Interaction, opponent: discord.Member, amount: int):
        """Challenge another player to a wager"""
        if not await check_feature(interaction, "games"):
            return
        challenger = interaction.user

        if opponent.bot or opponent.id == challenger.id:
            return await interaction.response.send_message(
                "âŒ You cannot wager against bots or yourself.", ephemeral=True
            )

        # Check Challenger Funds
        c_bal = await get_balance(challenger.id)
        if c_bal < amount:
            return await interaction.response.send_message(
                "âŒ You don't have enough coins.", ephemeral=True
            )

        # Check Opponent Funds (Initial check)
        o_bal = await get_balance(opponent.id)
        if o_bal < amount:
            return await interaction.response.send_message(
                f"âŒ {opponent.name} doesn't have enough coins.", ephemeral=True
            )

        # Deduct from Challenger NOW (Held in Escrow)
        await update_balance(challenger.id, -amount)

        embed = self.create_embed(
            "âš”ï¸ PVP Challenge",
            f"**{challenger.name}** challenges **{opponent.mention}** to a wager!\nAmount: **{amount}** Coins",
        )
        view = WagerView(challenger, opponent, amount)

        await interaction.response.send_message(content=opponent.mention, embed=embed, view=view)

    # ==========================
    # ðŸ”« GAME 4: RUSSIAN ROULETTE
    # ==========================
    @app_commands.command(name="roulette", description="Risk it all! 1/6 chance to lose BIG")
    @app_commands.describe(bet="Amount to risk")
    async def roulette(self, interaction: discord.Interaction, bet: int):
        """Play Russian Roulette - survive for a bonus, die to lose it all"""
        if not await check_feature(interaction, "games"):
            return
        user = interaction.user
        bal = await get_balance(user.id)
        if bal < bet:
            return await interaction.response.send_message("âŒ Insufficient funds.", ephemeral=True)

        # Check the chamber
        chamber = random.randint(1, 6)

        if chamber == 1:  # BANG
            await update_balance(user.id, -bet, is_win=False)
            await interaction.response.send_message(
                f"ðŸ”« **CLICK... BANG!** ðŸ’€\nYou died and lost **{bet}** coins."
            )
        else:  # Click
            winnings = int(bet * 0.2)
            await update_balance(user.id, winnings, is_win=True)
            await interaction.response.send_message(
                f"ðŸ”« **CLICK...** You survived! You take **{winnings}** coins from the pot."
            )

    # ==========================
    # ðŸ¦– GAME 5: DINO RACING
    # ==========================
    @app_commands.command(name="race", description="Bet on a Dino Race!")
    @app_commands.describe(dino_choice="Choose: raptor, trike, or dodo")
    async def race(self, interaction: discord.Interaction, dino_choice: str):
        """Bet on a dino race"""
        if not await check_feature(interaction, "games"):
            return
        bet = 50
        user = interaction.user
        valid_dinos = ["raptor", "trike", "dodo"]
        if dino_choice.lower() not in valid_dinos:
            return await interaction.response.send_message(
                "âŒ Choose: `Raptor`, `Trike`, or `Dodo`.", ephemeral=True
            )

        bal = await get_balance(user.id)
        if bal < bet:
            return await interaction.response.send_message("âŒ Insufficient funds.", ephemeral=True)

        await update_balance(user.id, -bet)

        racers = {"raptor": 0, "trike": 0, "dodo": 0}
        icons = {"raptor": "ðŸ¦–", "trike": "ðŸ¦•", "dodo": "ðŸ¦¤"}
        track_length = 20

        await interaction.response.send_message(
            f"ðŸ **The race begins!** You bet on **{dino_choice.title()}**."
        )
        msg = await interaction.original_response()

        winner = None
        for round_num in range(5):
            await asyncio.sleep(1.5)
            racers["raptor"] += random.randint(1, 6)
            racers["trike"] += random.randint(2, 4)
            racers["dodo"] += random.randint(0, 8)

            track_view = "**Race Update:**\n"
            for d, dist in racers.items():
                visible_dist = min(dist, track_length)
                line = "-" * visible_dist + icons[d] + " " * (track_length - visible_dist) + "ðŸ"
                track_view += f"`{d.upper()}`: {line}\n"
            await msg.edit(content=track_view)

            finished = [d for d, dist in racers.items() if dist >= track_length]
            if finished:
                winner = finished[0]
                break

        if not winner:
            winner = max(racers, key=racers.get)

        payout = 0
        if winner == dino_choice.lower():
            if winner == "raptor":
                payout = bet * 2
            if winner == "trike":
                payout = int(bet * 1.5)
            if winner == "dodo":
                payout = bet * 5
            await update_balance(user.id, payout, is_win=True)
            final_text = f"\nðŸ† **{winner.upper()} WINS!** You won **{payout}** coins!"
        else:
            final_text = f"\nâŒ **{winner.upper()} WINS!** You lost your bet."

        await msg.edit(content=msg.content + final_text)

    # ==========================
    # ðŸ¥š GAME 6: EGG HATCHERY
    # ==========================
    @app_commands.command(name="hatch", description="Buy and hatch a Mystery Egg (Cost: 500 coins)")
    async def hatch(self, interaction: discord.Interaction):
        """Hatch a mystery egg for a chance at rare rewards"""
        if not await check_feature(interaction, "games"):
            return
        cost = 500
        user = interaction.user
        bal = await get_balance(user.id)
        if bal < cost:
            return await interaction.response.send_message(
                f"âŒ You need {cost} coins.", ephemeral=True
            )

        await update_balance(user.id, -cost)

        await interaction.response.send_message("ðŸ¥š **Incubating Egg...**")
        msg = await interaction.original_response()
        await asyncio.sleep(2)

        roll = random.randint(1, 100)
        if roll <= 50:
            await msg.edit(content="ðŸ’¨ The egg was a dud. Just **Thatch**.")
        elif roll <= 85:
            refund = random.randint(300, 600)
            await update_balance(user.id, refund, is_win=True)
            await msg.edit(content=f"ðŸ¦– A baby Dodo popped out and gave you **{refund}** coins!")
        elif roll <= 98:
            prize = 2000
            await update_balance(user.id, prize, is_win=True)
            await msg.edit(content=f"ðŸ¦• **It's a Trike!** You sold it for **{prize}** coins!")
        else:
            item_name = "Ascendant Rex Saddle BP"
            await log_item_win(user.id, item_name)
            await msg.edit(
                content=f"ðŸš¨ **LEGENDARY HATCH!** ðŸš¨\nYou found: **{item_name}**!\nAn admin has been notified."
            )

    # ==========================
    # ðŸƒ GAME 7: BLACKJACK
    # ==========================
    @app_commands.command(name="blackjack", description="Play Blackjack against the bot")
    @app_commands.describe(bet="Amount to wager (minimum: 10)")
    async def blackjack(self, interaction: discord.Interaction, bet: int):
        """Play Blackjack"""
        if not await check_feature(interaction, "games"):
            return
        user = interaction.user
        bal = await get_balance(user.id)
        if bal < bet:
            return await interaction.response.send_message("âŒ Insufficient funds.", ephemeral=True)
        if bet < 10:
            return await interaction.response.send_message("âŒ Minimum bet is 10.", ephemeral=True)

        await update_balance(user.id, -bet)
        game = BlackjackGame(user, bet)
        view = BlackjackView(user.id, bet, game)
        embed = game.get_embed(show_dealer=False)
        await interaction.response.send_message(embed=embed, view=view)
        game.message = await interaction.original_response()

    # ==========================
    # ðŸŽ GAME 8: SUPPLY DROP (ADMIN)
    # ==========================
    @app_commands.command(name="spawn_drop", description="Admin: Spawns a loot crate")
    @app_commands.checks.has_permissions(administrator=True)
    async def spawn_drop(self, interaction: discord.Interaction):
        """Spawn a supply drop for users to claim"""
        if not await check_feature(interaction, "games"):
            return
        view = SupplyDropView()
        embed = self.create_embed(
            "ðŸš Incoming Supply Drop!",
            "A Red Loot Crate is descending...\n**First to click grabs the loot!**",
            color=discord.Color.red(),
        )
        embed.set_image(url="https://ark.wiki.gg/images/4/44/Red_Supply_Crate.png")

        await interaction.response.send_message("Drop incoming!", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)

    # ==========================
    # ðŸ§  GAME 9: TRIVIA
    # ==========================
    @app_commands.command(name="trivia", description="Answer an ARK question for coins")
    async def trivia(self, interaction: discord.Interaction):
        """Answer trivia for coins"""
        if not await check_feature(interaction, "games"):
            return
        q_data = random.choice(TRIVIA_QUESTIONS)
        question = q_data["q"]
        correct = q_data["a"]
        options = q_data["options"].copy()
        random.shuffle(options)

        class TriviaView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=None)

            @discord.ui.button(label=options[0], style=discord.ButtonStyle.primary)
            async def b1(self, i: discord.Interaction, b: discord.ui.Button):
                await self.check(i, options[0])

            @discord.ui.button(label=options[1], style=discord.ButtonStyle.primary)
            async def b2(self, i: discord.Interaction, b: discord.ui.Button):
                await self.check(i, options[1])

            @discord.ui.button(label=options[2], style=discord.ButtonStyle.primary)
            async def b3(self, i: discord.Interaction, b: discord.ui.Button):
                await self.check(i, options[2])

            async def check(self, i: discord.Interaction, guess: str):
                if i.user.id != interaction.user.id:
                    return
                self.stop()
                if guess == correct:
                    await update_balance(i.user.id, 50, is_win=True)
                    await i.response.edit_message(
                        content="✅ **Correct!** You won 50 coins.", view=None
                    )
                else:
                    await i.response.edit_message(
                        content=f"âŒ **Wrong!** The answer was **{correct}**.", view=None
                    )

        await interaction.response.send_message(f"ðŸ§  **TRIVIA:** {question}", view=TriviaView())


async def setup(bot):
    await bot.add_cog(PhoenixArcade(bot))
