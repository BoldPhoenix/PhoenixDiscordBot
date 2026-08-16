"""
Crafting Race - Multi-tier ARK recipe knowledge game.

Select ALL correct ingredients before time runs out.
Three difficulty tiers with increasing ingredient count and time pressure.

Ban logic (two rules):
  1. Forward ban  — if a correct ingredient is itself craftable, ban its
     sub-components as decoys (e.g. Tranq Arrow needs Stone Arrow → ban Flint+Fiber).
  2. Inverse ban  — if ALL sub-components of a crafted item are present in the
     correct list, ban that crafted item as a decoy (e.g. Campfire needs
     Flint+Stone → ban Sparkpowder so it never appears as an option).
"""

import discord
import random

from bot.games.base import BaseGameView


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — registered in games.py / PhoenixGameHubView
# ─────────────────────────────────────────────────────────────────────────────

class CraftingRaceView(BaseGameView):
    """
    Thin entry point that satisfies the GameIntroView / BaseGameView contract.
    start_game() transitions immediately to the tier-selection screen.
    """
    NAME = "Crafting Race"
    EMOJI = "⚒️"
    DESCRIPTION = (
        "Select **all** correct ingredients before time runs out!\n"
        "🟢 Easy: 2 ingredients, 30s  |  🟡 Medium: 3, 20s  |  🔴 Hard: 4, 15s"
    )
    DEFAULT_WAGER = 0

    def start_game(self, balance: int = None):
        tier_view = CraftingRaceTierView(
            self.guild_id, self.user_id, balance or 0, self._eos_id
        )
        return tier_view.build_embed(), tier_view


# ─────────────────────────────────────────────────────────────────────────────
# Tier selection
# ─────────────────────────────────────────────────────────────────────────────

class CraftingRaceTierView(discord.ui.View):
    """Difficulty selection shown between GameIntroView and the actual game."""

    def __init__(self, guild_id: int, user_id: int, balance: int, eos_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.balance = balance
        self.eos_id = eos_id

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="⚒️ Crafting Race — Choose Difficulty",
            description="Pick your tier. Select **all** correct ingredients before time runs out!",
            color=0xE74C3C,
        )
        embed.add_field(name="🟢 Easy",   value="2 ingredients\n⏱️ 30 seconds\n🪙 10 coins",  inline=True)
        embed.add_field(name="🟡 Medium", value="3 ingredients\n⏱️ 20 seconds\n🪙 20 coins",  inline=True)
        embed.add_field(name="🔴 Hard",   value="4 ingredients\n⏱️ 15 seconds\n🪙 35 coins",  inline=True)
        embed.add_field(name="Balance",   value=f"🪙 {self.balance:,} coins",                  inline=False)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This game belongs to another player!", ephemeral=True)
            return False
        return True

    async def _launch(self, interaction: discord.Interaction, tier: str):
        game = CraftingRaceGameView(self.guild_id, self.user_id, self.eos_id, tier)
        await interaction.response.edit_message(embed=game.build_embed(), view=game)

    @discord.ui.button(label="🟢 Easy",      style=discord.ButtonStyle.success,   row=0)
    async def easy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._launch(interaction, "easy")

    @discord.ui.button(label="🟡 Medium",    style=discord.ButtonStyle.primary,   row=0)
    async def medium_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._launch(interaction, "medium")

    @discord.ui.button(label="🔴 Hard",      style=discord.ButtonStyle.danger,    row=0)
    async def hard_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._launch(interaction, "hard")

    @discord.ui.button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=1)
    async def all_games_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from bot.cogs.games import PhoenixGameHubView
        embed = discord.Embed(title="🎮 Phoenix Game System", color=0xE74C3C)
        embed.add_field(name="Your Balance", value=f"🪙 {self.balance:,} coins", inline=False)
        await interaction.response.edit_message(embed=embed, view=PhoenixGameHubView(self.guild_id, self.user_id))


# ─────────────────────────────────────────────────────────────────────────────
# The timed game
# ─────────────────────────────────────────────────────────────────────────────

class CraftingRaceGameView(discord.ui.View):
    """
    Dynamic timed game view.
    - Ingredient buttons toggle green/grey when clicked.
    - Confirm button submits the selection.
    - View timeout = tier time limit; on_timeout resolves as a loss.
    """

    TIERS = {
        "easy":   {"coins": 10,  "timeout": 30, "num_options": 5, "num_correct": 2, "label": "🟢 Easy"},
        "medium": {"coins": 20,  "timeout": 20, "num_options": 6, "num_correct": 3, "label": "🟡 Medium"},
        "hard":   {"coins": 35,  "timeout": 15, "num_options": 7, "num_correct": 4, "label": "🔴 Hard"},
    }

    BLUEPRINTS = {
        # ── EASY: 2 correct ingredients ──────────────────────────────────────
        "easy": [
            {"name": "Sparkpowder",       "ingredients": ["Flint",        "Stone"]},
            {"name": "Narcotic",          "ingredients": ["Narcoberry",   "Spoiled Meat"]},
            {"name": "Cementing Paste",   "ingredients": ["Chitin",       "Stone"]},
            {"name": "Gasoline",          "ingredients": ["Oil",          "Hide"]},
            {"name": "Re-Fertilizer",     "ingredients": ["Thatch",       "Poop"]},
            {"name": "Cooked Meat",       "ingredients": ["Raw Meat",     "Wood"]},
            {"name": "Cooked Fish Meat",  "ingredients": ["Raw Fish Meat","Wood"]},
            {"name": "Bug Repellant",     "ingredients": ["Poop",         "Charcoal"]},
            {"name": "Preserving Salt",   "ingredients": ["Sulfur",       "Crystal"]},
            {"name": "Water Jar",         "ingredients": ["Stone",        "Hide"]},
            {"name": "Mortar and Pestle", "ingredients": ["Stone",        "Thatch"]},
            {"name": "Stone Arrow",       "ingredients": ["Flint",        "Fiber"]},
            {"name": "Spear",             "ingredients": ["Wood",         "Flint"]},
            {"name": "Bow",               "ingredients": ["Wood",         "Fiber"]},
            {"name": "Torch",             "ingredients": ["Flint",        "Thatch"]},
            {"name": "Hide Chestpiece",   "ingredients": ["Hide",         "Fiber"]},
            {"name": "Chitin Chestpiece", "ingredients": ["Chitin",       "Hide"]},
            {"name": "Fur Chestpiece",    "ingredients": ["Pelt",         "Fiber"]},
            {"name": "Flak Chestpiece",   "ingredients": ["Metal Ingot",  "Hide"]},
            {"name": "Thatch Foundation", "ingredients": ["Thatch",       "Wood"]},
            {"name": "Red Dye",           "ingredients": ["Charcoal",     "Tintoberry"]},
            {"name": "Blue Dye",          "ingredients": ["Charcoal",     "Azulberry"]},
            {"name": "Yellow Dye",        "ingredients": ["Charcoal",     "Amarberry"]},
            {"name": "Simple Bed",        "ingredients": ["Fiber",        "Thatch"]},
            {"name": "Parasaur Saddle",   "ingredients": ["Hide",         "Wood"]},
            {"name": "Gunpowder",         "ingredients": ["Charcoal",     "Sparkpowder"]},
            {"name": "Stimulant",         "ingredients": ["Azulberry",    "Sparkpowder"]},
            {"name": "Medical Brew",      "ingredients": ["Tintoberry",   "Narcotic"]},
            {"name": "Polymer",           "ingredients": ["Obsidian",     "Cementing Paste"]},
            {"name": "Electronics",       "ingredients": ["Metal Ingot",  "Silica Pearls"]},
            {"name": "Tranq Arrow",       "ingredients": ["Stone Arrow",  "Narcotic"]},
            {"name": "Metal Arrow",       "ingredients": ["Metal Ingot",  "Fiber"]},
            {"name": "Simple Bullet",     "ingredients": ["Metal Ingot",  "Gunpowder"]},
            {"name": "Pike",              "ingredients": ["Wood",         "Metal Ingot"]},
            {"name": "Sword",             "ingredients": ["Metal Ingot",  "Crystal"]},
            {"name": "Fabricated Pistol", "ingredients": ["Metal Ingot",  "Polymer"]},
        ],

        # ── MEDIUM: 3 correct ingredients ────────────────────────────────────
        "medium": [
            {"name": "Bola",               "ingredients": ["Fiber",       "Raw Meat",    "Wood"]},
            {"name": "Campfire",           "ingredients": ["Flint",       "Stone",       "Wood"]},
            {"name": "Ghillie Chestpiece", "ingredients": ["Fiber",       "Pelt",        "Crystal"]},
            {"name": "Air Conditioner",    "ingredients": ["Metal Ingot", "Crystal",     "Fiber"]},
            {"name": "Grappling Hook",     "ingredients": ["Metal Ingot", "Fiber",       "Hide"]},
            {"name": "Crossbow",           "ingredients": ["Metal Ingot", "Wood",        "Fiber"]},
            {"name": "Longneck Rifle",     "ingredients": ["Metal Ingot", "Wood",        "Crystal"]},
            {"name": "Stone Foundation",   "ingredients": ["Stone",       "Wood",        "Fiber"]},
            {"name": "Compass",            "ingredients": ["Metal Ingot", "Crystal",     "Hide"]},
            {"name": "Metal Hatchet",      "ingredients": ["Metal Ingot", "Stone",       "Wood"]},
            {"name": "Cactus Broth",       "ingredients": ["Cactus Sap",  "Mejoberry",   "Sparkpowder"]},
            {"name": "Wood Foundation",    "ingredients": ["Wood",        "Fiber",       "Thatch"]},
        ],

        # ── HARD: 4 correct ingredients ──────────────────────────────────────
        "hard": [
            {"name": "Simple Kibble",   "ingredients": ["Small Egg",  "Cooked Meat",      "Rockarrot", "Mejoberry"]},
            {"name": "Basic Kibble",    "ingredients": ["Small Egg",  "Fiber",            "Amarberry", "Mejoberry"]},
            {"name": "Regular Kibble",  "ingredients": ["Medium Egg", "Cooked Meat Jerky","Longrass",  "Savoroot"]},
            {"name": "Superior Kibble", "ingredients": ["Large Egg",  "Prime Meat Jerky", "Citronal",  "Savoroot"]},
            {"name": "C4 Charge",       "ingredients": ["Sparkpowder","Fiber",            "Crystal",   "Polymer"]},
            {"name": "Chemistry Bench", "ingredients": ["Crystal",    "Metal Ingot",      "Obsidian",  "Polymer"]},
            {"name": "Focal Chili",     "ingredients": ["Citronal",   "Rockarrot",        "Longrass",  "Savoroot"]},
        ],
    }

    # Crafted item → its direct sub-components.
    # Drives both ban rules (see module docstring).
    CRAFTED_INGREDIENTS = {
        "Sparkpowder":       ["Flint",          "Stone"],
        "Narcotic":          ["Narcoberry",      "Spoiled Meat"],
        "Cementing Paste":   ["Chitin",          "Stone"],
        "Gunpowder":         ["Charcoal",        "Sparkpowder"],
        "Metal Ingot":       ["Metal Ore"],
        "Polymer":           ["Obsidian",        "Cementing Paste"],
        "Cooked Meat":       ["Raw Meat",        "Wood"],
        "Gasoline":          ["Oil",             "Hide"],
        "Stone Arrow":       ["Flint",           "Fiber"],
        "Cooked Meat Jerky": ["Cooked Meat",     "Oil"],
        "Prime Meat Jerky":  ["Raw Prime Meat",  "Oil"],
    }

    # Full decoy pool — raw resources + crafted items that may appear as decoys
    ALL_INGREDIENTS = [
        # Raw
        "Flint", "Stone", "Narcoberry", "Spoiled Meat", "Chitin",
        "Charcoal", "Metal Ore", "Wood", "Obsidian", "Fiber",
        "Rockarrot", "Raw Meat", "Crystal", "Silica Pearls", "Oil",
        "Hide", "Thatch", "Poop", "Azulberry", "Tintoberry", "Amarberry",
        "Pelt", "Raw Fish Meat", "Raw Prime Meat", "Longrass", "Savoroot",
        "Citronal", "Mejoberry", "Sulfur", "Cactus Sap",
        "Small Egg", "Medium Egg", "Large Egg",
        # Crafted (valid decoys for higher-tier recipes)
        "Sparkpowder", "Narcotic", "Cementing Paste", "Gunpowder",
        "Metal Ingot", "Polymer", "Cooked Meat", "Gasoline", "Stone Arrow",
        "Cooked Meat Jerky", "Prime Meat Jerky",
    ]

    def __init__(self, guild_id: int, user_id: int, eos_id: str, tier: str):
        cfg = self.TIERS[tier]
        super().__init__(timeout=cfg["timeout"])
        self.guild_id = guild_id
        self.user_id = user_id
        self.eos_id = eos_id
        self.tier = tier
        self._cfg = cfg
        self._blueprint = random.choice(self.BLUEPRINTS[tier])
        self._selected: set = set()
        self._resolved = False
        self._message = None
        self._ingredient_buttons: dict = {}
        self._build_buttons()

    # ── ban logic ─────────────────────────────────────────────────────────────

    def _get_banned_decoys(self) -> set:
        correct = set(self._blueprint["ingredients"])
        banned = set()

        # Rule 1: ban sub-components of any crafted correct ingredient
        for ingredient in correct:
            if ingredient in self.CRAFTED_INGREDIENTS:
                banned.update(self.CRAFTED_INGREDIENTS[ingredient])

        # Rule 2: ban crafted items whose FULL recipe is a subset of correct
        for crafted_item, subs in self.CRAFTED_INGREDIENTS.items():
            if crafted_item not in correct and all(s in correct for s in subs):
                banned.add(crafted_item)

        return banned

    # ── button construction ───────────────────────────────────────────────────

    def _build_buttons(self):
        correct = self._blueprint["ingredients"]
        banned = self._get_banned_decoys()
        num_decoys = self._cfg["num_options"] - len(correct)

        decoy_pool = [
            i for i in self.ALL_INGREDIENTS
            if i not in correct and i not in banned
        ]
        decoys = random.sample(decoy_pool, num_decoys)

        options = list(correct) + decoys
        random.shuffle(options)

        for i, ingredient in enumerate(options):
            row = i // 3
            btn = discord.ui.Button(
                label=ingredient,
                style=discord.ButtonStyle.secondary,
                row=row,
            )
            btn.callback = self._make_ingredient_callback(ingredient)
            self._ingredient_buttons[ingredient] = btn
            self.add_item(btn)

        # Confirm on the row after the last ingredient row
        confirm_row = ((self._cfg["num_options"] - 1) // 3) + 1
        confirm_btn = discord.ui.Button(
            label=f"✅ Confirm  ({self._cfg['num_correct']} needed)",
            style=discord.ButtonStyle.success,
            row=confirm_row,
        )
        confirm_btn.callback = self._confirm
        self.add_item(confirm_btn)

    def _make_ingredient_callback(self, ingredient: str):
        async def callback(interaction: discord.Interaction):
            self._message = interaction.message
            if self._resolved:
                return await interaction.response.defer()
            if ingredient in self._selected:
                self._selected.discard(ingredient)
                self._ingredient_buttons[ingredient].style = discord.ButtonStyle.secondary
            else:
                self._selected.add(ingredient)
                self._ingredient_buttons[ingredient].style = discord.ButtonStyle.primary
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
        return callback

    async def _confirm(self, interaction: discord.Interaction):
        self._message = interaction.message
        if self._resolved:
            return await interaction.response.defer()
        needed = self._cfg["num_correct"]
        if len(self._selected) != needed:
            await interaction.response.send_message(
                f"Select exactly **{needed}** ingredients! (You have {len(self._selected)} selected)",
                ephemeral=True,
            )
            return
        await self._resolve(interaction)

    # ── resolution ────────────────────────────────────────────────────────────

    async def _resolve(self, interaction: discord.Interaction):
        if self._resolved:
            return
        self._resolved = True
        for item in self.children:
            item.disabled = True

        correct_set = set(self._blueprint["ingredients"])
        won = self._selected == correct_set

        if won:
            payout = self._cfg["coins"]
            await self._award_coins(payout)
            embed = discord.Embed(
                title="⚒️ Crafting Race",
                description=(
                    f"✅ **CORRECT!** You crafted **{self._blueprint['name']}**!\n\n"
                    f"**+{payout} coins**"
                ),
                color=discord.Color.green(),
            )
        else:
            payout = 0
            wrong = self._selected - correct_set
            missing = correct_set - self._selected
            parts = []
            if wrong:
                parts.append(f"Wrong: {', '.join(wrong)}")
            if missing:
                parts.append(f"Missing: {', '.join(missing)}")
            embed = discord.Embed(
                title="⚒️ Crafting Race",
                description=(
                    f"❌ **Wrong!** {' | '.join(parts)}\n"
                    f"Needed: **{', '.join(self._blueprint['ingredients'])}**"
                ),
                color=discord.Color.red(),
            )

        await self._record_result(won, payout)
        balance = await self._get_balance()
        embed.add_field(name="Tier",    value=self._cfg["label"],      inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,} coins", inline=True)

        result_view = CraftingRaceResultView(self.guild_id, self.user_id, balance, self.eos_id)
        await interaction.response.edit_message(embed=embed, view=result_view)

    async def on_timeout(self):
        if self._resolved:
            return
        self._resolved = True
        for item in self.children:
            item.disabled = True

        await self._record_result(False, 0)
        balance = await self._get_balance()

        embed = discord.Embed(
            title="⚒️ Crafting Race",
            description=(
                f"⏱️ **TIME'S UP!**\n"
                f"Needed: **{', '.join(self._blueprint['ingredients'])}**"
            ),
            color=discord.Color.red(),
        )
        embed.add_field(name="Tier",    value=self._cfg["label"],      inline=True)
        embed.add_field(name="Balance", value=f"🪙 {balance:,} coins", inline=True)

        result_view = CraftingRaceResultView(self.guild_id, self.user_id, balance, self.eos_id)
        if self._message:
            try:
                await self._message.edit(embed=embed, view=result_view)
            except Exception:
                pass

    # ── embed ────────────────────────────────────────────────────────────────

    def build_embed(self) -> discord.Embed:
        needed = self._cfg["num_correct"]
        selected_count = len(self._selected)
        embed = discord.Embed(
            title=f"⚒️ Crafting Race — {self._cfg['label']}",
            description=(
                f"**Craft: {self._blueprint['name']}**\n\n"
                f"Select **{needed}** ingredients  •  ⏱️ {self._cfg['timeout']}s to answer!"
            ),
            color=discord.Color.blue(),
        )
        if self._selected:
            embed.add_field(
                name=f"Selected ({selected_count}/{needed})",
                value=", ".join(sorted(self._selected)),
                inline=False,
            )
        embed.add_field(name="Reward", value=f"🪙 {self._cfg['coins']} coins", inline=True)
        return embed

    # ── interaction guard ────────────────────────────────────────────────────

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This game belongs to another player!", ephemeral=True)
            return False
        return True

    # ── DB helpers ───────────────────────────────────────────────────────────

    async def _award_coins(self, amount: int):
        from bot.database import players_db
        if self.eos_id:
            await players_db.add_coins(
                self.guild_id, self.eos_id, amount,
                reason="Game winnings: Crafting Race", discord_id=self.user_id,
            )

    async def _record_result(self, won: bool, payout: int):
        from bot.database import games_db
        await games_db.record_game(
            guild_id=self.guild_id, user_id=self.user_id,
            game_name="Crafting Race", wager=0, won=won, payout=payout,
        )

    async def _get_balance(self) -> int:
        from bot.database import players_db
        balance, _ = await players_db.get_balance_by_discord_id(self.guild_id, self.user_id)
        return balance if balance else 0


# ─────────────────────────────────────────────────────────────────────────────
# Post-game buttons
# ─────────────────────────────────────────────────────────────────────────────

class CraftingRaceResultView(discord.ui.View):
    """Play Again and All Games buttons shown after resolution."""

    def __init__(self, guild_id: int, user_id: int, balance: int, eos_id: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.balance = balance
        self.eos_id = eos_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This game belongs to another player!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔄 Play Again", style=discord.ButtonStyle.success,   row=0)
    async def play_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        from bot.database import players_db
        balance, eos_id = await players_db.get_balance_by_discord_id(self.guild_id, self.user_id)
        tier_view = CraftingRaceTierView(
            self.guild_id, self.user_id, balance or 0, eos_id or self.eos_id
        )
        await interaction.response.edit_message(embed=tier_view.build_embed(), view=tier_view)

    @discord.ui.button(label="🎮 All Games", style=discord.ButtonStyle.secondary, row=0)
    async def all_games(self, interaction: discord.Interaction, button: discord.ui.Button):
        from bot.cogs.games import PhoenixGameHubView
        embed = discord.Embed(title="🎮 Phoenix Game System", color=0xE74C3C)
        embed.add_field(name="Your Balance", value=f"🪙 {self.balance:,} coins", inline=False)
        await interaction.response.edit_message(embed=embed, view=PhoenixGameHubView(self.guild_id, self.user_id))
