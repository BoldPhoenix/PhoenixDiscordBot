"""
Mutation Slots - ARK-themed slot machine using Pillow images.
Optimized for Raspberry Pi 5 / NVMe performance.
"""

import discord
import random
import os
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from bot.games.base import BaseGameView, GameResult, GameOutcome

# Ensure these assets exist in your path
SLOT_IMAGES_PATH = "/opt/phoenix-bot/images/slots"
SYMBOL_SIZE = 160  # Larger symbols for better visibility (was 80)
CABINET_PADDING = 60  # Increased padding for larger symbols

# ARK-Specific Symbol Map
SYMBOL_MAP = {
    "🧬": "dino",         # Jackpot
    "💎": "diamond",      # High
    "🥚": "egg",          # Mid  
    "🥩": "meat",         # Low
    "🫐": "berry",        # Low
    "🔥": "fire",         # Mid
    "⭐": "star",         # Low
    "💀": "skull",        # Low
    "W": "wild",          # Wild - substitutes for any symbol
    "S": "freespin",      # Free Spin - scatter (3+ triggers bonus)
}

class MutationSlotsView(BaseGameView):
    NAME = "Ark Slots"
    EMOJI = "🎰"
    DESCRIPTION = "Match 3 symbols to win! Wild substitutes for any symbol."
    DEFAULT_WAGER = 10
    WAGER_BUTTON_ROW = 1  # Place wager button on row 1 with All Games

    SYMBOLS = list(SYMBOL_MAP.keys())
    # Weights adjusted - S (free spins) now much rarer
    # Total ~97, S weighted low for rare free spin trigger
    WEIGHTS = [15, 12, 10, 8, 8, 10, 8, 8, 8, 5]  # 🧬💎🥚🥩🫐🔥⭐💀WS - S is now 5 (was 35)
    
    # Standard symbols (excluding wild and scatter)
    STANDARD_SYMBOLS = ["🧬", "💎", "🥚", "🥩", "🫐", "🔥", "⭐", "💀"]
    WILD = "W"
    SCATTER = "S"
    
    # Paytable: (multiplier, color)
    PAYOUTS = {
        # Jackpot: 3 identical - 10000 coins regardless of wager (5% odds)
        ("🧬", "🧬", "🧬"): (10000, discord.Color.from_rgb(0, 255, 255)),
        ("💎", "💎", "💎"): (5000, discord.Color.blue()),
        ("🥚", "🥚", "🥚"): (2500, discord.Color.orange()),
        ("🔥", "🔥", "🔥"): (1000, discord.Color.red()),
        ("⭐", "⭐", "⭐"): (500, discord.Color.yellow()),
        # 2 identical + wild (10% odds) - pays based on the pair
        (WILD, WILD, "🧬"): (500, discord.Color.from_rgb(255, 215, 0)),
        (WILD, WILD, "💎"): (250, discord.Color.from_rgb(255, 215, 0)),
        (WILD, WILD, "🥚"): (100, discord.Color.from_rgb(255, 215, 0)),
        (WILD, WILD, "🔥"): (50, discord.Color.from_rgb(255, 215, 0)),
        (WILD, WILD, "⭐"): (25, discord.Color.from_rgb(255, 215, 0)),
        ("🧬", WILD, WILD): (500, discord.Color.from_rgb(255, 215, 0)),
        ("💎", WILD, WILD): (250, discord.Color.from_rgb(255, 215, 0)),
        ("🥚", WILD, WILD): (100, discord.Color.from_rgb(255, 215, 0)),
        ("🔥", WILD, WILD): (50, discord.Color.from_rgb(255, 215, 0)),
        ("⭐", WILD, WILD): (25, discord.Color.from_rgb(255, 215, 0)),
        # Any pair (20% odds) - 2x payout
    }

    _symbol_images = None
    _cabinet_overlay = None

    def __init__(self, guild_id: int, user_id: int, wager: int = 10):
        super().__init__(guild_id, user_id, wager, timeout=None)
        self._reels = [None, None, None]
        self._payout = 0
        self._won = False
        self._free_spins = 0
        self._total_wager = wager
        self._load_images()
        self._create_buttons()

    @classmethod
    def _load_images(cls):
        if cls._symbol_images is not None:
            return
        
        cls._symbol_images = {}
        for emoji, name in SYMBOL_MAP.items():
            filepath = os.path.join(SLOT_IMAGES_PATH, f"{name}.png")
            if os.path.exists(filepath):
                # Pre-resize and keep in RAM for Pi 5 performance
                img = Image.open(filepath).convert("RGBA")
                cls._symbol_images[emoji] = img.resize((SYMBOL_SIZE, SYMBOL_SIZE), Image.Resampling.LANCZOS)
        
        cabinet_path = os.path.join(SLOT_IMAGES_PATH, "cabinet.png")
        if os.path.exists(cabinet_path):
            cls._cabinet_overlay = Image.open(cabinet_path).convert("RGBA")

    def _create_buttons(self):
        # Spin buttons with multipliers - different colors
        spin_x1 = discord.ui.Button(label="SPIN 1x", style=discord.ButtonStyle.success, row=0)
        spin_x1.callback = self._spin_x1
        self.add_item(spin_x1)
        
        spin_x5 = discord.ui.Button(label="SPIN 5x", style=discord.ButtonStyle.primary, row=0)
        spin_x5.callback = self._spin_x5
        self.add_item(spin_x5)
        
        spin_x10 = discord.ui.Button(label="SPIN 10x", style=discord.ButtonStyle.danger, row=0)
        spin_x10.callback = self._spin_x10
        self.add_item(spin_x10)
        
        # Second row: All Games only (wager button provided by base class on row 1)
        games_btn = discord.ui.Button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=1)
        games_btn.callback = self._all_games
        self.add_item(games_btn)

    async def _change_wager(self, interaction: discord.Interaction):
        from bot.games.base import WagerModal
        modal = WagerModal(self)
        await interaction.response.send_modal(modal)

    async def _all_games(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎮 Phoenix ARK Games",
            description="Select a game to play!",
            color=discord.Color.blue()
        )
        from bot.cogs.games import PhoenixGameHubView
        view = PhoenixGameHubView(self.guild_id, self.user_id)
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])

    def _create_slots_image(self, reels, show_win=False, spinning=False):
        """High-fidelity image generation with motion blur and layering."""
        # Target canvas size - use full resolution cabinet
        target_width = 1215
        target_height = 450
        
        # Scale cabinet to target size
        if self._cabinet_overlay:
            cabinet = self._cabinet_overlay.resize((target_width, target_height), Image.Resampling.LANCZOS)
            canvas = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
            canvas.paste(cabinet, (0, 0))
        else:
            canvas = Image.new('RGBA', (target_width, target_height), (20, 20, 30, 255))
        
        # Scale icons to 180px (slightly larger) and position evenly across window
        # Window is ~847px wide (188 to 1035), use even spacing
        icon_size = 180
        x_positions = [265, 522, 779]  # Evenly spaced across ~847px window
        y_offset = 135  # Center vertically (132 + small adjustment)

        for i, emoji in enumerate(reels):
            x = x_positions[i]
            # During spin - show blurred Phoenix icon for all reels
            if spinning:
                if self._symbol_images and "W" in self._symbol_images:
                    symbol_img = self._symbol_images["W"].copy()
                    symbol_img = symbol_img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
                    symbol_img = symbol_img.filter(ImageFilter.GaussianBlur(radius=8))
                    canvas.paste(symbol_img, (x, y_offset), symbol_img)
            elif emoji and emoji in self._symbol_images:
                symbol_img = self._symbol_images[emoji].copy()
                symbol_img = symbol_img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
                canvas.paste(symbol_img, (x, y_offset), symbol_img)

        # Winner Highlights
        if show_win:
            overlay = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.rectangle([15, 15, target_width-15, target_height-15], outline=(0, 255, 255, 200), width=8)
            canvas = Image.alpha_composite(canvas, overlay)

        buffer = BytesIO()
        canvas.save(buffer, format='PNG', optimize=True)
        buffer.seek(0)
        return buffer

    async def _spin_x1(self, interaction: discord.Interaction):
        await self._spin(interaction, 1)
    
    async def _spin_x5(self, interaction: discord.Interaction):
        await self._spin(interaction, 5)
    
    async def _spin_x10(self, interaction: discord.Interaction):
        await self._spin(interaction, 10)
    
    async def _spin(self, interaction: discord.Interaction, multiplier: int = 1):
        # STEP 1: Balance check - use multiplied wager
        self._total_wager = self.wager * multiplier
        
        # Check balance with multiplied wager
        balance = await self.get_balance()
        if balance < self._total_wager:
            await interaction.response.send_message(
                f"Need {self._total_wager} coins for a spin. Balance: {balance}",
                ephemeral=True
            )
            return
        
        # Deduct wager
        from bot.database import players_db
        if self._eos_id is None:
            _, self._eos_id = await players_db.get_balance_by_discord_id(self.guild_id, self.user_id)
        
        success = await players_db.deduct_coins(
            self.guild_id,
            self._eos_id,
            self._total_wager,
            reason=f"Slots wager: {self.game_name}",
            discord_id=self.user_id
        )
        if not success:
            await interaction.response.send_message("Failed to process wager.", ephemeral=True)
            return

        # STEP 2: DEFER (Crucial for Fiber/API stability)
        await interaction.response.defer()

        # STEP 3: Show "Spinning" Frame
        spinning_buffer = self._create_slots_image([None, None, None], spinning=True)
        spinning_file = discord.File(spinning_buffer, filename="slots.png")
        
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description="🔄 *Spinning...*",
            color=discord.Color.blue()
        )
        embed.set_image(url="attachment://slots.png")
        await interaction.edit_original_response(embed=embed, attachments=[spinning_file])

        # STEP 3: Wait for "The Spin" (Visual pacing) - reduced from 1.2s
        await asyncio.sleep(0.8)
        
        # STEP 4: Calculate Results
        reels = tuple(random.choices(self.SYMBOLS, weights=self.WEIGHTS)[0] for _ in range(3))
        self._reels = list(reels)
        
        # Check for scatter wins (free spins) - 3 S triggers free spins (rare)
        scatter_count = reels.count(self.SCATTER)
        free_spins_awarded = 0
        if scatter_count >= 3:
            free_spins_awarded = 1  # Just 1 free spin (was scatter_count * 3)
            # Scatter wins always pay back wager (push) + 1 free spin
            self._payout = self._total_wager  # Return wager
            self._won = True
            win_type = f"FREE SPINS!"
        
        # Check for wins (including wild substitutions)
        # Only check if we didn't already win from scatters
        if scatter_count < 2:
            self._won = False
            win_type = ""
            
            # Check exact match first
            if reels in self.PAYOUTS:
                mult, color = self.PAYOUTS[reels]
                self._payout = self._total_wager * mult
                self._won = True
                win_type = "JACKPOT!"
            else:
                # Check wild substitutions for 3-of-a-kind
                reels_list = list(reels)
                for i in range(3):
                    if reels_list[i] == self.WILD:
                        for sym in self.STANDARD_SYMBOLS:
                            test_reels = reels_list.copy()
                            test_reels[i] = sym
                            test_tuple = tuple(test_reels)
                            if test_tuple in self.PAYOUTS:
                                mult, color = self.PAYOUTS[test_tuple]
                                self._payout = self._total_wager * mult
                                self._won = True
                                win_type = f"WILD {sym} WIN!"
                                break
                        if self._won:
                            break
                
                # Check for any pair (2 matching symbols) - 2x payout
                if not self._won:
                    from collections import Counter
                    symbol_counts = Counter(reels_list)
                    for sym, count in symbol_counts.items():
                        if count >= 2 and sym != self.WILD and sym != self.SCATTER:
                            self._payout = self._total_wager * 2
                            self._won = True
                            win_type = f"PAIR {sym}{sym} WIN!"
                            break
                    # Also check for pair with wild
                    if not self._won:
                        wild_count = reels_list.count(self.WILD)
                        if wild_count >= 1:
                            for sym in self.STANDARD_SYMBOLS:
                                if reels_list.count(sym) >= 1:
                                    self._payout = self._total_wager * 2
                                    self._won = True
                                    win_type = f"WILD PAIR WIN!"
                                    break
        
        if self._won:
            await self.award_winnings(self._payout)
        
        # Store free spins info for display
        self._free_spins = free_spins_awarded
        
        # STEP 5: Record the game result BEFORE building embed (so stats update)
        if self._won:
            await self.record_game(GameOutcome(
                result=GameResult.WIN,
                wager=self._total_wager,
                payout=self._payout,
                multiplier=self._payout // self._total_wager if self._total_wager > 0 else 0,
                message=f"**WIN!** +{self._payout} coins!",
                color=discord.Color.from_rgb(0, 255, 255)
            ))
        else:
            await self.record_game(GameOutcome(
                result=GameResult.LOSS,
                wager=self._total_wager,
                payout=0,
                multiplier=0,
                message="No match",
                color=discord.Color.dark_grey()
            ))
        
        # STEP 6: Final Update
        embed, file = await self._build_embed()
        await interaction.edit_original_response(embed=embed, attachments=[file])

    async def _build_embed(self):
        balance = await self.get_balance()
        result_text = "🔄 Spin to win!"
        
        if self._reels[0] is not None:
            if self._won:
                if self._free_spins > 0:
                    result_text = f"🎉 **WIN!** +{self._payout} coins! +{self._free_spins} FREE SPINS!"
                else:
                    result_text = f"**WIN!** +{self._payout} coins!"
            else:
                result_text = "No match"

        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description=result_text,
            color=discord.Color.from_rgb(0, 255, 255) if self._won else discord.Color.dark_grey()
        )
        
        slots_file = discord.File(self._create_slots_image(self._reels, self._won), filename="slots.png")
        embed.set_image(url="attachment://slots.png")
        embed.add_field(name="Wager", value=f"🪙 {self.wager}", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,}", inline=True)
        
        stats = await self.get_stats()
        embed.add_field(name="Record", value=f"✅ {stats.get('won', 0)} | ❌ {stats.get('lost', 0)}", inline=True)
        
        return embed, slots_file

    async def start_game(self, balance: int = None):
        embed, file = await self._build_embed()
        return embed, file, self