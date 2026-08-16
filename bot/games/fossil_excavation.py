"""
Fossil Excavation - Unearth ancient ARK fossils!
Excavate grid layers to find hidden fossils before tool durability runs out.
"""

import discord
import random
from bot.games.base import BaseGameView, GameResult, GameOutcome

class FossilExcavationView(BaseGameView):
    NAME = "Fossil Excavation"
    EMOJI = "🦴"
    DESCRIPTION = "Excavate fossils from rock layers!\nFind all fossils before tools break!"
    DEFAULT_WAGER = 10

    GRID_SIZE = 16  # 4x4 grid
    TOOL_DURABILITY = 8
    FOSSIL_COUNT = 3
    
    LAYERS = {
        0: {"emoji": "🟫", "name": "Topsoil", "color": discord.Color.yellow()},
        1: {"emoji": "🟨", "name": "Clay", "color": discord.Color.orange()},
        2: {"emoji": "🟪", "name": "Shale", "color": discord.Color.purple()},
        3: {"emoji": "⚫", "name": "Bedrock", "color": discord.Color.dark_grey()}
    }
    
    def __init__(self, guild_id: int, user_id: int, wager: int = None):
        super().__init__(guild_id, user_id, wager, timeout=None)
        self._grid = self._generate_grid()
        self._tool_durability = self.TOOL_DURABILITY
        self._fossils_found = 0
        self._score = 0
        self._selected = []
        self._game_started = False
        self._current_balance = 0  # Initialize balance
        # Remove inherited wager button - we'll add it dynamically
        self._remove_inherited_wager_button()

    def _generate_grid(self):
        grid = []
        for _ in range(self.GRID_SIZE):
            layer = random.choices([0, 1, 2, 3], weights=[0.4, 0.3, 0.2, 0.1])[0]
            grid.append({"layer": layer, "excavated": False, "fossil": False})
        
        # Place fossils randomly
        fossil_positions = random.sample(range(self.GRID_SIZE), self.FOSSIL_COUNT)
        for pos in fossil_positions:
            grid[pos]["fossil"] = True
        
        return grid

    def _build_game_embed(self) -> discord.Embed:
        """Game-specific embed shown when game is actively being played"""
        embed = discord.Embed(
            title=f"{self.EMOJI} {self.NAME}",
            description="Excavate the grid to find hidden fossils!",
            color=discord.Color.dark_grey()
        )
        
        embed.add_field(name="Tool Durability", value=f"⛏️ {self._tool_durability}/{self.TOOL_DURABILITY}", inline=True)
        embed.add_field(name="Fossils Found", value=f"🦴 {self._fossils_found}/{self.FOSSIL_COUNT}", inline=True)
        embed.add_field(name="Current Score", value=f"🪙 {self._score}", inline=True)
        embed.add_field(name="Wager", value=f"🪙 {self.wager} coins", inline=True)
        embed.add_field(name="Balance", value=f"🪙 {self._current_balance:,} coins", inline=True)
        
        if self._game_started:
            progress = (self._fossils_found / self.FOSSIL_COUNT) * 100
            embed.add_field(name="Progress", value=f"{progress:.0f}% complete", inline=False)
        
        return embed

    def _remove_inherited_wager_button(self):
        """Remove the inherited wager button from the view"""
        for item in self.children[:]:
            if hasattr(item, 'label') and item.label == "💰 Wager":
                self.remove_item(item)
                break
    
    def _add_grid_buttons(self):
        """Add grid buttons to this view"""
        for i, tile in enumerate(self._grid):
            if tile["excavated"]:
                if tile["fossil"]:
                    label = "🦴"
                    style = discord.ButtonStyle.success
                else:
                    label = "🟨"
                    style = discord.ButtonStyle.secondary
            else:
                label = "❓"
                style = discord.ButtonStyle.secondary
            btn = discord.ui.Button(label=label, style=style, row=i // 4, custom_id=f"grid_{i}")
            btn.callback = lambda interaction, idx=i: self._excavate_tile(interaction, idx)
            self.add_item(btn)
        
        # Add control buttons below grid (row 4)
        wager_btn = discord.ui.Button(label="💰 Wager", style=discord.ButtonStyle.primary, row=4)
        wager_btn.callback = self._wager_modal
        self.add_item(wager_btn)
        
        all_games_btn = discord.ui.Button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=4)
        all_games_btn.callback = self._all_games
        self.add_item(all_games_btn)
    
    async def _wager_modal(self, interaction: discord.Interaction):
        """Open wager change modal"""
        from bot.games.base import WagerModal
        await interaction.response.send_modal(WagerModal(self))
    
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
        self._add_grid_buttons()
        return self._build_game_embed(), self

    async def _excavate_tile(self, interaction: discord.Interaction, tile_idx: int):
        if not self._game_started or self._grid[tile_idx]["excavated"]:
            return await interaction.response.defer()
        
        # Check if game should end before allowing excavation
        if self._tool_durability <= 0 or all(tile["excavated"] for tile in self._grid):
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=self.wager,
                payout=0,
                multiplier=0,
                message=f"Tools broke! You only found {self._fossils_found}/{self.FOSSIL_COUNT} fossils.",
                color=discord.Color.red()
            )
            await self.resolve_game(interaction, outcome)
            return
        
        # Excavate the tile
        self._grid[tile_idx]["excavated"] = True
        self._tool_durability -= 1
        self._selected.append(tile_idx)
        
        # Check for fossil
        if self._grid[tile_idx]["fossil"]:
            self._fossils_found += 1
            self._score += 20
        
        # Check for pattern matches (3+ adjacent same layer)
        matches = self._find_pattern_matches(tile_idx)
        if matches:
            self._score += len(matches) * 5
        
        # Check win condition
        if self._fossils_found == self.FOSSIL_COUNT:
            total_payout = self.wager + self._score
            outcome = GameOutcome(
                result=GameResult.WIN,
                wager=self.wager,
                payout=total_payout,
                multiplier=total_payout / self.wager if self.wager > 0 else 0,
                message=f"Excavation complete! You found all {self.FOSSIL_COUNT} fossils and earned {self._score} bonus coins!",
                color=discord.Color.gold()
            )
            await self.award_winnings(total_payout)
            await self.resolve_game(interaction, outcome)
            return
        
        # Check lose condition (after this excavation)
        if self._tool_durability <= 0 or all(tile["excavated"] for tile in self._grid):
            outcome = GameOutcome(
                result=GameResult.LOSS,
                wager=self.wager,
                payout=0,
                multiplier=0,
                message=f"Tools broke! You only found {self._fossils_found}/{self.FOSSIL_COUNT} fossils.",
                color=discord.Color.red()
            )
            await self.resolve_game(interaction, outcome)
            return
        
        # Update the display for next turn
        self._refresh_grid_buttons()
        await interaction.response.edit_message(
            embed=self._build_game_embed(),
            view=self
        )

    def _find_pattern_matches(self, last_tile: int) -> list:
        """Find adjacent tiles with same layer for bonus points"""
        matches = []
        row, col = last_tile // 4, last_tile % 4
        layer = self._grid[last_tile]["layer"]
        
        # Check all 4 directions
        for dr, dc in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
            r, c = row + dr, col + dc
            if 0 <= r < 4 and 0 <= c < 4:
                neighbor_idx = r * 4 + c
                if (self._grid[neighbor_idx]["excavated"] and 
                    self._grid[neighbor_idx]["layer"] == layer):
                    matches.append(neighbor_idx)
        
        return matches if len(matches) >= 2 else []

    def _refresh_grid_buttons(self):
        """Refresh grid button labels after excavation"""
        for i, tile in enumerate(self._grid):
            for item in self.children:
                if hasattr(item, 'custom_id') and item.custom_id == f"grid_{i}":
                    if tile["excavated"]:
                        if tile["fossil"]:
                            item.label = "🦴"
                            item.style = discord.ButtonStyle.success
                        else:
                            item.label = "🟨"
                            item.style = discord.ButtonStyle.secondary
                    break
    
    async def _check_daily(self, interaction: discord.Interaction) -> tuple:
        from bot.database import games_db
        can_play, spent = await games_db.check_daily_limit(self.guild_id, self.user_id, self.wager)
        if not can_play:
            settings = await games_db.get_game_settings(self.guild_id)
            limit = settings.get("daily_limit", 5000)
            await interaction.response.send_message(f"Daily limit reached! {spent}/{limit}", ephemeral=True)
            return False, spent
        return True, spent
