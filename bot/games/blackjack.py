"""
Dino Jack - ARK-themed Blackjack card game.
Get closer to 21 than the dealer without going over!
Uses Pillow to generate card images in-memory.
"""

import discord
import random
import os
from io import BytesIO
from PIL import Image, ImageDraw
from bot.games.base import BaseGameView, GameResult, GameOutcome

CARD_IMAGES_PATH = "/opt/phoenix-bot/images/cards"
CARD_WIDTH = 128  # Larger cards for better visibility
CARD_HEIGHT = 192
GREEN_FELT = (0, 100, 0)  # Dark green casino felt


class BlackjackView(BaseGameView):
    NAME = "Dino Jack"
    EMOJI = "🃏"
    DESCRIPTION = "Classic 21! Get closer to 21 than the dealer.\nWager coins | Win 2.5x on blackjack, 1x on beat dealer"
    DEFAULT_WAGER = 10
    WAGER_BUTTON_ROW = 0

    def __init__(self, guild_id: int, user_id: int, wager: int = 10):
        super().__init__(guild_id, user_id, wager, timeout=None)
        self._deck = []
        self._player_hand = []
        self._dealer_hand = []
        self._game_over = False
        self._player_stood = False
        self._blackjack = False
        self._create_buttons()
    
    def _create_buttons(self):
        hit_btn = discord.ui.Button(label="Hit", style=discord.ButtonStyle.success, row=0)
        hit_btn.callback = self._hit
        self.add_item(hit_btn)
        
        stand_btn = discord.ui.Button(label="Stand", style=discord.ButtonStyle.danger, row=0)
        stand_btn.callback = self._stand
        self.add_item(stand_btn)
        
        # Wager button provided by base class on row 1
        self._add_all_games_button()
    
    def _add_all_games_button(self):
        games_btn = discord.ui.Button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=0)
        games_btn.callback = self._all_games
        self.add_item(games_btn)
    
    def _create_game_over_buttons(self):
        self.clear_items()
        
        deal_btn = discord.ui.Button(label="🔄 Deal Again", style=discord.ButtonStyle.success, row=0)
        deal_btn.callback = self._deal_again
        self.add_item(deal_btn)
        
        wager_btn = discord.ui.Button(label="Change Wager", style=discord.ButtonStyle.secondary, row=0)
        wager_btn.callback = self._change_wager
        self.add_item(wager_btn)
        
        games_btn = discord.ui.Button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=0)
        games_btn.callback = self._all_games
        self.add_item(games_btn)

    async def _all_games(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎮 Phoenix ARK Games",
            description="Select a game to play!",
            color=discord.Color.blue()
        )
        from bot.cogs.games import PhoenixGameHubView
        view = PhoenixGameHubView(self.guild_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])
    
    def _add_wager_button(self):
        wager_btn = discord.ui.Button(label=f"Wager: {self.wager}", style=discord.ButtonStyle.secondary, row=0)
        wager_btn.callback = self._change_wager
        self.add_item(wager_btn)
    
    async def _change_wager(self, interaction: discord.Interaction):
        from bot.games.base import WagerModal
        modal = WagerModal(self)
        await interaction.response.send_modal(modal)
    
    def _get_card_image_filename(self, card: str) -> str:
        rank_map = {
            'A': 'A', '2': '2', '3': '3', '4': '4', '5': '5',
            '6': '6', '7': '7', '8': '8', '9': '9', '10': '10',
            'J': 'J', 'Q': 'Q', 'K': 'K'
        }
        suit_map = {'♠': 'S', '♥': 'H', '♦': 'D', '♣': 'C'}
        
        if not card or len(card) < 2:
            return "back.png"
        
        rank = rank_map.get(card[:-1], 'A')
        suit = suit_map.get(card[-1], 'S')
        
        return f"{rank}{suit}.png"
    
    def _create_hand_image(self, cards: list, hide_first: bool = False) -> BytesIO:
        if not cards:
            return self._create_empty_hand_image()
        
        num_cards = len(cards) - 1 if hide_first else len(cards)
        width = num_cards * (CARD_WIDTH - 10) + 20
        height = CARD_HEIGHT + 30
        
        canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        
        x_offset = 10
        for i, card in enumerate(cards):
            if hide_first and i == 0:
                back_path = os.path.join(CARD_IMAGES_PATH, "back.png")
                if os.path.exists(back_path):
                    card_img = Image.open(back_path).convert('RGBA')
                    card_img = card_img.resize((CARD_WIDTH, CARD_HEIGHT))
                    canvas.paste(card_img, (x_offset, 10), card_img)
                x_offset += CARD_WIDTH - 10
                continue
            
            filename = self._get_card_image_filename(card)
            filepath = os.path.join(CARD_IMAGES_PATH, filename)
            
            if os.path.exists(filepath):
                card_img = Image.open(filepath).convert('RGBA')
                card_img = card_img.resize((CARD_WIDTH, CARD_HEIGHT))
                canvas.paste(card_img, (x_offset, 10), card_img)
            x_offset += CARD_WIDTH - 10
        
        buffer = BytesIO()
        canvas.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer
    
    def _create_empty_hand_image(self) -> BytesIO:
        width = CARD_WIDTH + 20
        height = CARD_HEIGHT + 30
        
        canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        
        buffer = BytesIO()
        canvas.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer
    
    def _create_table_image(self, result_text: str = None, result_color: tuple = None, result_subtext: str = None) -> BytesIO:
        """Create a combined table image with green felt and both hands."""
        from PIL import ImageFont
        card_spacing = CARD_WIDTH + 5  # Space between cards

        # Calculate width based on max cards in either hand
        max_cards = max(len(self._player_hand), len(self._dealer_hand))
        width = max(max_cards * card_spacing + 40, 200)

        # Calculate height: two rows of cards with gap in middle
        height = CARD_HEIGHT * 2 + 80  # Two card heights + gap + padding

        # Green felt background
        canvas = Image.new('RGBA', (width, height), (*GREEN_FELT, 255))
        draw = ImageDraw.Draw(canvas)

        # Draw table border (darker green)
        draw.rectangle([0, 0, width-1, height-1], outline=(20, 80, 20), width=3)

        # Draw dealer's hand at top
        dealer_y = 15
        dealer_x = (width - (len(self._dealer_hand) * card_spacing)) // 2
        hide_first = not self._player_stood and not self._game_over

        for i, card in enumerate(self._dealer_hand):
            x_pos = dealer_x + i * card_spacing
            if hide_first and i == 0:
                back_path = os.path.join(CARD_IMAGES_PATH, "back.png")
                if os.path.exists(back_path):
                    card_img = Image.open(back_path).convert('RGBA')
                    card_img = card_img.resize((CARD_WIDTH, CARD_HEIGHT))
                    canvas.paste(card_img, (x_pos, dealer_y), card_img)
            else:
                filename = self._get_card_image_filename(card)
                filepath = os.path.join(CARD_IMAGES_PATH, filename)
                if os.path.exists(filepath):
                    card_img = Image.open(filepath).convert('RGBA')
                    card_img = card_img.resize((CARD_WIDTH, CARD_HEIGHT))
                    canvas.paste(card_img, (x_pos, dealer_y), card_img)

        # Draw player's hand at bottom
        player_y = height - CARD_HEIGHT - 15
        player_x = (width - (len(self._player_hand) * card_spacing)) // 2

        for i, card in enumerate(self._player_hand):
            x_pos = player_x + i * card_spacing
            filename = self._get_card_image_filename(card)
            filepath = os.path.join(CARD_IMAGES_PATH, filename)
            if os.path.exists(filepath):
                card_img = Image.open(filepath).convert('RGBA')
                card_img = card_img.resize((CARD_WIDTH, CARD_HEIGHT))
                canvas.paste(card_img, (x_pos, player_y), card_img)

        # Draw casino-style result banner centered between the two hands
        if result_text:
            color = result_color or (255, 215, 0)
            cx = width // 2
            cy = height // 2

            # Load bold font
            font_main = None
            font_sub = None
            for font_path in [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            ]:
                if os.path.exists(font_path):
                    font_main = ImageFont.truetype(font_path, 52)
                    font_sub = ImageFont.truetype(font_path, 26)
                    break
            if font_main is None:
                font_main = ImageFont.load_default()

            # Semi-transparent dark banner spanning the full width
            banner_h = 90 if result_subtext else 66
            overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle(
                [0, cy - banner_h // 2, width, cy + banner_h // 2],
                fill=(0, 0, 0, 170)
            )
            canvas = Image.alpha_composite(canvas, overlay)
            draw = ImageDraw.Draw(canvas)

            # Main result text — offset up slightly if subtext present
            text_y = cy - 14 if result_subtext else cy
            for dx, dy in [(-2,-2),(-2,0),(-2,2),(0,-2),(0,2),(2,-2),(2,0),(2,2)]:
                draw.text((cx + dx, text_y + dy), result_text, fill=(0, 0, 0), font=font_main, anchor="mm")
            draw.text((cx, text_y), result_text, fill=color, font=font_main, anchor="mm")

            # Subtext (payout info) below main text
            if result_subtext and font_sub:
                sub_y = cy + 26
                draw.text((cx, sub_y), result_subtext, fill=(210, 210, 210), font=font_sub, anchor="mm")

        buffer = BytesIO()
        canvas.save(buffer, format='PNG', optimize=True)
        buffer.seek(0)
        return buffer
    
    async def _hit(self, interaction: discord.Interaction):
        if self._game_over:
            return
        
        card = self._draw_card()
        self._player_hand.append(card)
        
        player_total = self._calculate_total(self._player_hand)
        
        # 5-card Charlie: 5 cards without busting = automatic win + 50 coin bonus
        if len(self._player_hand) >= 5 and player_total <= 21:
            self._game_over = True
            payout = int(self.wager * 2) + 50
            await self.award_winnings(payout)
            outcome = GameOutcome(
                result=GameResult.WIN,
                wager=self.wager,
                payout=payout,
                multiplier=2,
                message=f"**5-CARD CHARLIE!**\n\nYou win +{payout} coins! (+50 bonus)",
                color=discord.Color.green()
            )
            await self._finish_game(interaction, outcome)
            return
        elif player_total > 21:
            self._game_over = True
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=self.wager,
                payout=0,
                multiplier=0,
                message=f"**BUSTED!**\n\nYou went over 21!",
                color=discord.Color.red()
            )
            await self._finish_game(interaction, outcome)
        elif player_total == 21:
            await self._stand(interaction)
        else:
            embed, file = await self._build_embed()
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)
    
    async def _stand(self, interaction: discord.Interaction):
        if self._game_over:
            return
        
        self._player_stood = True
        self._game_over = True
        
        while self._calculate_total(self._dealer_hand) < 17:
            self._dealer_hand.append(self._draw_card())
        
        player_total = self._calculate_total(self._player_hand)
        dealer_total = self._calculate_total(self._dealer_hand)
        
        if dealer_total > 21:
            payout = self.wager * 2
            await self.award_winnings(payout)
            outcome = GameOutcome(
                result=GameResult.WIN,
                wager=self.wager,
                payout=payout,
                multiplier=2,
                message=f"**DEALER BUSTS!**\n\n**YOU WIN {payout} coins!**",
                color=discord.Color.green()
            )
        elif player_total > dealer_total:
            payout = self.wager
            await self.award_winnings(payout)
            outcome = GameOutcome(
                result=GameResult.WIN,
                wager=self.wager,
                payout=payout,
                multiplier=1,
                message=f"**YOU WIN!**\n\n**YOU WIN {payout} coins!**",
                color=discord.Color.green()
            )
        elif player_total < dealer_total:
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=self.wager,
                payout=0,
                multiplier=0,
                message=f"**DEALER WINS!**",
                color=discord.Color.red()
            )
        else:
            await self.award_winnings(self.wager)
            outcome = GameOutcome(
                result=GameResult.PUSH,
                wager=self.wager,
                payout=self.wager,
                multiplier=1,
                message=f"**PUSH!**\n\nYour wager has been returned.",
                color=discord.Color.yellow()
            )
        
        await self._finish_game(interaction, outcome)
    
    async def _deal_again(self, interaction: discord.Interaction):
        """Start a new hand with the same wager."""
        new_game = BlackjackView(self.guild_id, self.user_id, self.wager)
        
        new_game._deck = new_game._create_deck()
        new_game._player_hand = [new_game._draw_card(), new_game._draw_card()]
        new_game._dealer_hand = [new_game._draw_card(), new_game._draw_card()]
        new_game._game_over = False
        new_game._player_stood = False
        
        player_total = new_game._calculate_total(new_game._player_hand)
        
        if player_total == 21:
            new_game._blackjack = True
            new_game._game_over = True
            payout = int(new_game.wager * 2.5)
            await new_game.award_winnings(payout)
            
            outcome = GameOutcome(
                result=GameResult.WIN,
                wager=new_game.wager,
                payout=payout,
                multiplier=2.5,
                message=f"**BLACKJACK!**\n\n**YOU WIN {payout} coins!**",
                color=discord.Color.green()
            )
            await new_game._finish_with_outcome(interaction, outcome)
        else:
            embed, file = await new_game._build_embed()
            await interaction.response.edit_message(embed=embed, attachments=[file], view=new_game)
    
    async def _finish_game(self, interaction: discord.Interaction, outcome: GameOutcome):
        await self._finish_with_outcome(interaction, outcome)
    
    async def _finish_with_outcome(self, interaction: discord.Interaction, outcome: GameOutcome):
        balance = await self.get_balance()

        # Map outcome message to casino-style overlay text + subtext
        msg = outcome.message
        if outcome.result == GameResult.WIN:
            embed_color = discord.Color.green()
            overlay_color = (255, 215, 0)   # Gold
            if "BLACKJACK" in msg:
                overlay_text = "BLACKJACK!"
                overlay_subtext = f"+{outcome.payout} coins  (2.5×)"
            elif "5-CARD CHARLIE" in msg:
                overlay_text = "5-CARD CHARLIE!"
                overlay_subtext = f"+{outcome.payout} coins  (+50 bonus)"
            elif "DEALER BUSTS" in msg:
                overlay_text = "DEALER BUSTS!"
                overlay_subtext = f"+{outcome.payout} coins"
            else:
                overlay_text = "YOU WIN!"
                overlay_subtext = f"+{outcome.payout} coins"
        elif outcome.result == GameResult.LOSS:
            embed_color = discord.Color.red()
            overlay_color = (220, 50, 50)   # Red
            if "BUST" in msg:
                overlay_text = "BUSTED!"
            else:
                overlay_text = "DEALER WINS"
            overlay_subtext = None
        else:
            embed_color = discord.Color.yellow()
            overlay_text = "PUSH!"
            overlay_color = (255, 165, 0)   # Orange
            overlay_subtext = "Wager returned"

        result_embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            color=embed_color
        )

        result_embed.add_field(name="Wager", value=f"{self.wager}", inline=True)
        result_embed.add_field(name="Balance", value=f"🪙 {balance:,}", inline=True)

        await self.record_game(outcome)
        stats = await self.get_stats()
        result_embed.add_field(name="Record", value=f"✅ {stats.get('won', 0)}W  ❌ {stats.get('lost', 0)}L", inline=True)

        new_game = BlackjackView(self.guild_id, self.user_id, self.wager)
        new_game._game_over = True
        new_game._player_hand = self._player_hand.copy()
        new_game._dealer_hand = self._dealer_hand.copy()
        new_game._player_stood = True
        new_game._create_game_over_buttons()

        # Result text rendered directly onto the table image between the hands
        table_buffer = new_game._create_table_image(result_text=overlay_text, result_color=overlay_color, result_subtext=overlay_subtext)
        table_file = discord.File(table_buffer, filename="table.png")
        result_embed.set_image(url="attachment://table.png")

        await interaction.response.edit_message(embed=result_embed, attachments=[table_file], view=new_game)
    
    async def _build_embed(self):
        player_total = self._calculate_total(self._player_hand)
        
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=f"Get closer to 21 than the dealer!",
            color=discord.Color.blurple()
        )
        
        if self._player_stood or self._game_over:
            dealer_total = self._calculate_total(self._dealer_hand)
            dealer_name = f"Dealer ({dealer_total})"
        else:
            dealer_name = "Dealer"
        
        # All in one row
        embed.add_field(name=f"Your Hand", value=f"**{player_total}**", inline=True)
        embed.add_field(name=dealer_name, value="​", inline=True)
        embed.add_field(name="Wager", value=f"{self.wager}", inline=True)
        
        # Use combined table image with green felt
        table_buffer = self._create_table_image()
        table_file = discord.File(table_buffer, filename="table.png")
        
        embed.set_image(url="attachment://table.png")
        
        return embed, table_file
    
    def _calculate_total(self, hand: list) -> int:
        total = 0
        aces = 0
        
        for card in hand:
            rank = card[:-1]
            if rank in ["J", "Q", "K"]:
                total += 10
            elif rank == "A":
                aces += 1
                total += 11
            else:
                total += int(rank)
        
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        
        return total
    
    def _draw_card(self) -> str:
        if not self._deck:
            self._deck = self._create_deck()
        return self._deck.pop()
    
    def _create_deck(self) -> list:
        suits = ["♠", "♥", "♦", "♣"]
        ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        deck = [f"{rank}{suit}" for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck
    
    async def start_game(self, balance: int = None):
        self._deck = self._create_deck()
        self._player_hand = [self._draw_card(), self._draw_card()]
        self._dealer_hand = [self._draw_card(), self._draw_card()]
        self._game_over = False
        self._player_stood = False
        
        player_total = self._calculate_total(self._player_hand)
        
        if player_total == 21:
            self._blackjack = True
            self._game_over = True
            payout = int(self.wager * 2.5)
            await self.award_winnings(payout)
            # Continue to show game with game over buttons instead of early return
        
        embed, file = await self._build_embed()
        return embed, file, self
