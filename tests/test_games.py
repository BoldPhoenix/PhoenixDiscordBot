"""
Tests for Phoenix Gaming Terminal - games module.
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
import discord

from bot.games.base import BaseGameView, GameResult, GameOutcome
from bot.games.dodo_roulette import DodoRouletteView
from bot.database import games_db, players_db, init_db
from bot.utils.config import Config


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        old_path = Config.DATABASE_PATH
        Config.DATABASE_PATH = str(Path(tmpdir) / "test.db")
        yield Config.DATABASE_PATH
        Config.DATABASE_PATH = old_path


@pytest.fixture
def db_setup(temp_db):
    asyncio.get_event_loop().run_until_complete(init_db.initialize_database())
    asyncio.get_event_loop().run_until_complete(players_db.init_players_tables())
    asyncio.get_event_loop().run_until_complete(games_db.init_games_tables())
    return temp_db


class TestGameOutcome:
    def test_win_outcome(self):
        outcome = GameOutcome(
            result=GameResult.WIN,
            wager=100,
            payout=200,
            multiplier=2.0,
            message="You win!",
            color=discord.Color.green()
        )
        assert outcome.result == GameResult.WIN
        assert outcome.wager == 100
        assert outcome.payout == 200
        assert outcome.multiplier == 2.0

    def test_loss_outcome(self):
        outcome = GameOutcome(
            result=GameResult.LOSS,
            wager=100,
            payout=0,
            multiplier=0,
            message="You lose!",
            color=discord.Color.red()
        )
        assert outcome.result == GameResult.LOSS
        assert outcome.payout == 0

    def test_jackpot_outcome(self):
        outcome = GameOutcome(
            result=GameResult.JACKPOT,
            wager=100,
            payout=1000,
            multiplier=10.0,
            message="JACKPOT!",
            color=discord.Color.gold()
        )
        assert outcome.result == GameResult.JACKPOT
        assert outcome.multiplier == 10.0


class TestGameResult:
    def test_result_values(self):
        assert GameResult.WIN.value == "win"
        assert GameResult.LOSS.value == "loss"
        assert GameResult.JACKPOT.value == "jackpot"
        assert GameResult.PUSH.value == "push"


class TestDodoRouletteView:
    def test_view_initialization(self):
        view = DodoRouletteView(guild_id=123, user_id=456, wager=100)
        assert view.guild_id == 123
        assert view.user_id == 456
        assert view.wager == 100
        assert view._resolved is False
        assert view.game_name == "Dodo Roulette"

    def test_view_default_wager(self):
        view = DodoRouletteView(guild_id=123, user_id=456)
        assert view.wager == 10  # DodoRouletteView has DEFAULT_WAGER = 10

    def test_outcomes_weights_sum(self):
        assert sum(DodoRouletteView.WEIGHTS) == 100

    def test_multipliers_defined(self):
        assert "Red" in DodoRouletteView.MULTIPLIERS
        assert "Blue" in DodoRouletteView.MULTIPLIERS
        assert "Green" in DodoRouletteView.MULTIPLIERS
        assert "Gold" in DodoRouletteView.MULTIPLIERS
        assert DodoRouletteView.MULTIPLIERS["Gold"] == 10


class TestGamesDatabase:
    @pytest.mark.asyncio
    async def test_init_games_tables(self, temp_db):
        await games_db.init_games_tables()
        
        import aiosqlite
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='game_settings'"
            )
            assert await cursor.fetchone() is not None
            
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='game_stats'"
            )
            assert await cursor.fetchone() is not None
            
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='game_leaderboard'"
            )
            assert await cursor.fetchone() is not None

    @pytest.mark.asyncio
    async def test_get_game_settings_defaults(self, temp_db):
        await games_db.init_games_tables()
        settings = await games_db.get_game_settings(guild_id=123)
        
        assert settings["games_enabled"] == 1
        assert settings["house_edge_percent"] == 10
        assert settings["min_wager"] == 10
        assert settings["max_wager"] == 1000
        assert settings["daily_limit"] == 999999999

    @pytest.mark.asyncio
    async def test_update_game_settings(self, temp_db):
        await games_db.init_games_tables()
        await games_db.update_game_settings(
            guild_id=123,
            games_enabled=0,
            min_wager=50,
            max_wager=5000
        )
        
        settings = await games_db.get_game_settings(guild_id=123)
        assert settings["games_enabled"] == 0
        assert settings["min_wager"] == 50
        assert settings["max_wager"] == 5000

    @pytest.mark.asyncio
    async def test_record_game_win(self, temp_db):
        await games_db.init_games_tables()
        result = await games_db.record_game(
            guild_id=123,
            user_id=456,
            game_name="Dodo Roulette",
            wager=100,
            won=True,
            payout=200
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_record_game_loss(self, temp_db):
        await games_db.init_games_tables()
        result = await games_db.record_game(
            guild_id=123,
            user_id=456,
            game_name="Dodo Roulette",
            wager=100,
            won=False,
            payout=0
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_get_user_stats_no_data(self, temp_db):
        await games_db.init_games_tables()
        stats = await games_db.get_user_stats(guild_id=123, user_id=999, game_name="Dodo Roulette")
        assert stats is None

    @pytest.mark.asyncio
    async def test_get_user_stats_after_games(self, temp_db):
        await games_db.init_games_tables()
        await games_db.record_game(123, 456, "Dodo Roulette", 100, True, 200)
        await games_db.record_game(123, 456, "Dodo Roulette", 100, False, 0)
        await games_db.record_game(123, 456, "Dodo Roulette", 50, True, 100)
        
        stats = await games_db.get_user_stats(123, 456, "Dodo Roulette")
        
        assert stats is not None
        assert stats["games_played"] == 3
        assert stats["games_won"] == 2
        assert stats["total_wagered"] == 250
        assert stats["total_won"] == 300
        assert stats["biggest_win"] == 200

    @pytest.mark.asyncio
    async def test_game_leaderboard(self, temp_db):
        await games_db.init_games_tables()
        await games_db.record_game(123, 100, "Dodo Roulette", 100, True, 500)
        await games_db.record_game(123, 200, "Dodo Roulette", 100, True, 300)
        await games_db.record_game(123, 300, "Dodo Roulette", 100, True, 100)
        
        leaderboard = await games_db.get_game_leaderboard(123, "Dodo Roulette", limit=10)
        
        assert len(leaderboard) == 3
        assert leaderboard[0]["user_id"] == 100
        assert leaderboard[0]["total_won"] == 500

    @pytest.mark.asyncio
    async def test_daily_limit_check(self, temp_db):
        await games_db.init_games_tables()
        await games_db.update_game_settings(123, daily_limit=1000)
        
        can_play, spent = await games_db.check_daily_limit(123, 456, 500)
        assert can_play is True
        assert spent == 0

    @pytest.mark.asyncio
    async def test_daily_limit_enforcement(self, temp_db):
        await games_db.init_games_tables()
        await games_db.update_game_settings(123, daily_limit=100)
        
        await games_db.record_game(123, 456, "Dodo Roulette", 80, True, 100)
        
        can_play, spent = await games_db.check_daily_limit(123, 456, 50)
        assert can_play is False
        assert spent == 80

    @pytest.mark.asyncio
    async def test_overall_leaderboard(self, temp_db):
        await games_db.init_games_tables()
        await games_db.record_game(123, 100, "Dodo Roulette", 100, True, 200)
        await games_db.record_game(123, 100, "Mutation Slot", 50, True, 150)
        await games_db.record_game(123, 200, "Dodo Roulette", 100, True, 300)
        
        leaderboard = await games_db.get_overall_leaderboard(123, limit=10)
        
        assert len(leaderboard) == 2
        total_won_100 = next(r["total_won"] for r in leaderboard if r["user_id"] == 100)
        total_won_200 = next(r["total_won"] for r in leaderboard if r["user_id"] == 200)
        
        assert total_won_100 == 350
        assert total_won_200 == 300


class TestBaseGameView:
    def test_game_name_property(self):
        view = BaseGameView(guild_id=123, user_id=456)
        assert view.game_name == "Base Game"

    def test_default_wager(self):
        view = BaseGameView(guild_id=123, user_id=456)
        assert view.wager == 10  # All games now have DEFAULT_WAGER = 10

    def test_custom_wager(self):
        view = BaseGameView(guild_id=123, user_id=456, wager=500)
        assert view.wager == 500

    def test_resolved_flag(self):
        view = BaseGameView(guild_id=123, user_id=456)
        assert view._resolved is False


class TestAllGameViews:
    def test_dodo_roulette_constants(self):
        assert DodoRouletteView.NAME == "Dodo Roulette"
        assert DodoRouletteView.EMOJI == "🦤"
        assert len(DodoRouletteView.OUTCOMES) == 4
        assert len(DodoRouletteView.WEIGHTS) == 4

    def test_all_games_have_required_attributes(self):
        from bot.games import (
            DodoRouletteView,
            OverseerCodeView,
            FossilExcavationView,
            TamingRiskView,
            ArtifactVaultView,
            CraftingRaceView,
            MutationSlotsView,
            AlphaHuntView,
            BlackjackView,
            CryoGambleView,
        )
        
        games = [
            DodoRouletteView,
            OverseerCodeView,
            FossilExcavationView,
            TamingRiskView,
            ArtifactVaultView,
            CraftingRaceView,
            MutationSlotsView,
            AlphaHuntView,
            BlackjackView,
            CryoGambleView,
        ]
        
        for game in games:
            assert hasattr(game, "NAME"), f"{game} missing NAME"
            assert hasattr(game, "EMOJI"), f"{game} missing EMOJI"
            assert hasattr(game, "DESCRIPTION"), f"{game} missing DESCRIPTION"
            assert hasattr(game, "DEFAULT_WAGER"), f"{game} missing DEFAULT_WAGER"

    def test_games_cog_can_be_imported(self):
        """Verify the games cog can be imported without errors.
        
        This catches issues like missing game exports that would cause
        the /games command to fail in Discord.
        """
        from bot.cogs import games as games_cog
        assert games_cog is not None


# ---------------------------------------------------------------------------
# 13. Verify all game exports are valid (catches missing/disabled games)
# ---------------------------------------------------------------------------

class TestGameExportsValid:
    """Test that all games exported from bot.games can be imported."""
    
    def test_all_exported_games_are_importable(self):
        """Every game in bot.games.__all__ that is a View should be importable and have required attributes."""
        from bot import games as games_module
        from bot.games.base import BaseGameView
        
        for game_name in games_module.__all__:
            # Get the actual class
            game_class = getattr(games_module, game_name)
            
            # Only test View classes (skip BaseGameView, GameResult, GameOutcome)
            if game_name in ("BaseGameView", "GameResult", "GameOutcome"):
                continue
                
            # Should be a View class (subclass of BaseGameView)
            assert issubclass(game_class, BaseGameView), f"{game_name} is not a View class"
            
            # Should have required attributes
            assert hasattr(game_class, "NAME"), f"{game_name} missing NAME attribute"
            assert hasattr(game_class, "EMOJI"), f"{game_name} missing EMOJI attribute"
