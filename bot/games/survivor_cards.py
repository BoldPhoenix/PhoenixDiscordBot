"""
Survivor Cards - ARK-themed card game where you build the best survivor hand.
Draft cards to create the highest scoring survivor combination.
"""

import discord
import random
from bot.games.base import BaseGameView, GameResult, GameOutcome


class SurvivorCardsView(BaseGameView):
    NAME = "Survivor Cards"
    EMOJI = "🃏"
    DESCRIPTION = "Draft the best survivor hand! Higher score wins.\n🎯 Build combos: Tools + Weapons + Armor = Bonus points"
    DEFAULT_WAGER = 10

    # Card categories with ARK theme
    CARDS = {
        "tools": [
            {"name": "Stone Pick", "emoji": "⛏️", "value": 2},
            {"name": "Metal Hatchet", "emoji": "🪓", "value": 3},
            {"name": "Crossbow", "emoji": "🏹", "value": 4},
            {"name": "Fabricator", "emoji": "🔧", "value": 5},
            {"name": "Tek Rifle", "emoji": "🔫", "value": 6},
        ],
        "weapons": [
            {"name": "Spear", "emoji": "🔱", "value": 2},
            {"name": "Bow", "emoji": "🏹", "value": 3},
            {"name": "Pike", "emoji": "🔱", "value": 4},
            {"name": "Shotgun", "emoji": "🔫", "value": 5},
            {"name": "Rocket Launcher", "emoji": "🚀", "value": 6},
        ],
        "armor": [
            {"name": "Hide Shirt", "emoji": "👕", "value": 2},
            {"name": "Flame Helmet", "emoji": "🪖", "value": 3},
            {"name": "Chitin Chest", "emoji": "🦺", "value": 4},
            {"name": "Tek Boots", "emoji": "👢", "value": 5},
            {"name": "Master Crown", "emoji": "👑", "value": 6},
        ],
        "special": [
            {"name": "Medical Brew", "emoji": "🧪", "value": 3, "bonus": 2},
            {"name": "Cryo Sickness", "emoji": "❄️", "value": 1, "penalty": -2},
            {"name": "Imprinting", "emoji": "💝", "value": 4, "bonus": 3},
            {"name": "Alpha Call", "emoji": "🦖", "value": 5, "bonus": 4},
        ]
    }

    def __init__(self, guild_id: int, user_id: int, wager: int = None):
        super().__init__(guild_id, user_id, wager, timeout=None)
        self._player_hand = []
        self._dealer_hand = []
        self._draft_pool = []
        self._game_started = False
        self._drafts_remaining = 4  # Each player gets 4 cards
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
        # Add wager button (row 4, below card buttons)
        wager_btn = discord.ui.Button(label="💰 Wager", style=discord.ButtonStyle.primary, row=4)
        wager_btn.callback = self._wager_modal
        self.add_item(wager_btn)
        
        # Add all games button (row 4, below card buttons)
        games_btn = discord.ui.Button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=4)
        games_btn.callback = self._all_games
        self.add_item(games_btn)

    def _add_draft_buttons(self):
        """Add card selection buttons for the current draft pool"""
        # Clear existing card buttons
        items_to_remove = []
        for item in self.children[:]:
            if hasattr(item, 'custom_id') and item.custom_id and item.custom_id.startswith('card_'):
                items_to_remove.append(item)
        
        for item in items_to_remove:
            self.remove_item(item)
        
        # Add new card buttons
        if self._draft_pool and self._drafts_remaining > 0:
            for i, card in enumerate(self._draft_pool[:8]):  # Max 8 cards shown
                btn = discord.ui.Button(
                    label=f"{card['emoji']} {card['name']}",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"card_{i}",
                    row=i // 4 + 2  # Rows 2-3 for cards (0-3→row2, 4-7→row3)
                )
                # Use lambda with default arg to capture card index
                btn.callback = lambda interaction, idx=i: self._draft_card(interaction, idx)
                self.add_item(btn)

    async def _card_button_callback(self, interaction: discord.Interaction, card_idx: int):
        """Handle card button clicks"""
        await self._draft_card(interaction, card_idx)

    async def _wager_modal(self, interaction: discord.Interaction):
        """Open wager change modal"""
        await interaction.response.send_modal(SurvivorCardsWagerModal(self))

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
        self._game_started = True
        self._generate_draft_pool()
        self._add_draft_buttons()  # Add card selection buttons
        return self._build_game_embed(), self

    def _generate_draft_pool(self):
        """Create a pool of cards for drafting"""
        all_cards = []
        for category in self.CARDS.values():
            all_cards.extend(category.copy())
        
        # Create pool with 8 cards (4 for each player)
        self._draft_pool = random.sample(all_cards, min(8, len(all_cards)))

    def _build_game_embed(self) -> discord.Embed:
        if not self._game_started:
            embed = discord.Embed(
                title=f"{self.EMOJI} {self.NAME}",
                description="Draft the best survivor hand to beat the dealer!\n🎯 Build combos: Tools + Weapons + Armor = Bonus points",
                color=discord.Color.blue()
            )
            embed.add_field(name="How to Play", value="🃏 Draft 4 cards from the pool\n🏆 Higher total score wins 2x wager", inline=False)
            embed.add_field(name="Wager", value=f"🪙 {self.wager} coins", inline=True)
            embed.add_field(name="Balance", value=f"🪙 {self._current_balance:,} coins", inline=True)
            return embed

        # Show current game state
        lines = ["🎯 Build combos: Tools + Weapons + Armor = Bonus points"]
        
        # Player hand
        if self._player_hand:
            player_cards = []
            player_total = 0
            for card in self._player_hand:
                player_cards.append(f"{card['emoji']} {card['name']}")
                player_total += card['value']
                if 'bonus' in card:
                    player_total += card['bonus']
                elif 'penalty' in card:
                    player_total += card['penalty']
            
            lines.append(f"**Your Hand:** {player_total} points")
            lines.extend([f"  {card}" for card in player_cards])
        else:
            lines.append("**Your Hand:** Empty")
        
        lines.append("")
        
        # Draft pool
        if self._draft_pool:
            lines.append(f"**Draft Pool** (Cards remaining: {len(self._draft_pool)})")
            pool_display = []
            for i, card in enumerate(self._draft_pool):
                pool_display.append(f"{i+1}. {card['emoji']} {card['name']} ({card['value']}pts)")
            lines.extend(pool_display)
        
        lines.append(f"\n**Drafts remaining:** {self._drafts_remaining}")
        
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description="\n".join(lines),
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Wager", value=f"🪙 {self.wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {self._current_balance:,} coins", inline=True)
        embed.add_field(name="Payout", value="2x if you win!", inline=True)
        
        return embed

    async def _draft_card(self, interaction: discord.Interaction, card_idx: int):
        if self._drafts_remaining <= 0 or card_idx >= len(self._draft_pool):
            return await interaction.response.defer()
        
        # Player drafts card
        drafted_card = self._draft_pool.pop(card_idx)
        self._player_hand.append(drafted_card)
        self._drafts_remaining -= 1
        
        # Dealer automatically drafts a card (simple AI)
        if self._draft_pool:
            dealer_card = random.choice(self._draft_pool)
            self._draft_pool.remove(dealer_card)
            self._dealer_hand.append(dealer_card)
        
        # Check if drafting is complete
        if self._drafts_remaining <= 0:
            await self._complete_game(interaction)
        else:
            self._add_draft_buttons()  # Refresh card buttons
            await interaction.response.edit_message(
                embed=self._build_game_embed(),
                view=self
            )

    async def _complete_game(self, interaction: discord.Interaction):
        """Calculate scores and determine winner"""
        # Calculate player score
        player_total = 0
        for card in self._player_hand:
            player_total += card['value']
            if 'bonus' in card:
                player_total += card['bonus']
            elif 'penalty' in card:
                player_total += card['penalty']
        
        # Calculate dealer score
        dealer_total = 0
        for card in self._dealer_hand:
            dealer_total += card['value']
            if 'bonus' in card:
                dealer_total += card['bonus']
            elif 'penalty' in card:
                dealer_total += card['penalty']
        
        # Get current balance
        balance = await self.get_balance()
        
        # Determine winner
        if player_total > dealer_total:
            payout = self.wager * 2
            await self.award_winnings(payout)
            balance += payout  # Update balance after winning
            
            outcome = GameOutcome(
                result=GameResult.WIN,
                wager=self.wager,
                payout=payout,
                multiplier=2.0,
                message=f"Your score {player_total} beats dealer's {dealer_total}!",
                color=discord.Color.green()
            )
        elif player_total < dealer_total:
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=self.wager,
                payout=0,
                multiplier=0,
                message=f"Dealer's {dealer_total} beats your {player_total}",
                color=discord.Color.red()
            )
        else:
            # Tie
            await self.award_winnings(self.wager)
            
            outcome = GameOutcome(
                result=GameResult.PUSH,
                wager=self.wager,
                payout=self.wager,
                multiplier=1.0,
                message=f"Both scored {player_total}! It's a tie - wager returned.",
                color=discord.Color.orange()
            )
        
        # Create custom embed with result
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=outcome.message,
            color=outcome.color
        )
        
        # Player hand - inline=False so wager/balance appear below
        player_cards = [f"{card['emoji']} {card['name']}" for card in self._player_hand]
        embed.add_field(name=f"Your Hand ({player_total})", value="\n".join(player_cards), inline=False)
        
        # Dealer hand - inline=False so wager/balance appear below
        dealer_cards = [f"{card['emoji']} {card['name']}" for card in self._dealer_hand]
        embed.add_field(name=f"Dealer Hand ({dealer_total})", value="\n".join(dealer_cards), inline=False)
        
        # Wager and Balance in same row below hands
        embed.add_field(name="Wager", value=f"🪙 {self.wager}", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,}", inline=True)
        
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


class SurvivorCardsWagerModal(discord.ui.Modal, title="Change Wager"):
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
            description="Draft the best survivor hand to beat the dealer!",
            color=discord.Color.blue()
        )
        embed.add_field(name="How to Play", value="🃏 Draft 4 cards from the pool\n🎯 Build combos for bonus points\n🏆 Higher total score wins 2x", inline=False)
        embed.add_field(name="Wager", value=f"🪙 {wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,} coins", inline=True)
        
        await interaction.response.edit_message(embed=embed, view=self.game_view)
