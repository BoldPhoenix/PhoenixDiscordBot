"""
Tests for /report command group in AnalyticsDashboard cog.

Covers:
- /report players|economy|shop|activity defers ephemerally, queries DB
- With data → followup sends ephemeral embed + Select view (no chart at command time)
- No data → followup sends ephemeral "no data" embed (no view)
- Free-tier guild is blocked by check_feature (no defer, no followup)
- timerange defaults to "7d" when not supplied
- TIME_RANGE_DAYS and TIME_RANGE_LABELS module-level constants are correct
- All four report subcommands exist on the cog
- PLAYER_CHARTS / ECONOMY_CHARTS / SHOP_CHARTS / SERVER_CHARTS dicts are present
- _has_data() helper works correctly
- ReportChartSelect.callback generates and sends a chart file
"""

import asyncio
import inspect
import io
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from bot.cogs.analytics_dashboard import (
    AnalyticsDashboard,
    TIME_RANGE_DAYS,
    TIME_RANGE_LABELS,
    PLAYER_CHARTS,
    ECONOMY_CHARTS,
    SHOP_CHARTS,
    SERVER_CHARTS,
    ReportChartSelect,
    ReportChartSelectView,
    _has_data,
)

# Patch path for check_feature as imported by analytics_dashboard
CHECK_FEATURE_PATH = "bot.cogs.analytics_dashboard.check_feature"


# ---------------------------------------------------------------------------
# Minimal bot stand-in
# ---------------------------------------------------------------------------

class _FakeBot:
    def __init__(self):
        self.guilds = []

    async def wait_until_ready(self):
        pass

    def get_cog(self, name):
        return None


def _make_cog():
    return AnalyticsDashboard(_FakeBot())


# ---------------------------------------------------------------------------
# Fake interaction factory
# ---------------------------------------------------------------------------

def _make_interaction(guild_id: int = 123456, guild_name: str = "Test Guild"):
    guild = SimpleNamespace(id=guild_id, name=guild_name)
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.guild_id = guild_id
    interaction.user = SimpleNamespace(id=999)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

_EMPTY_PLAYER   = {"daily_active": [], "sessions_by_server": [],
                    "avg_duration_by_server": [], "sessions_by_hour": []}
_EMPTY_ECONOMY  = {"payday_by_day": [], "type_breakdown": [],
                    "top_balances": [], "cumulative_coins": []}
_EMPTY_SHOP     = {"purchases_by_day": [], "top_items": [],
                    "spend_by_category": [], "coins_by_day": []}
_EMPTY_SERVER   = {"sessions_by_server_day": [], "total_by_server": [],
                    "new_players_by_day": [], "activity_by_hour": []}

# Minimal non-empty datasets (one key has data)
_HAS_PLAYER  = {**_EMPTY_PLAYER,  "daily_active": [{"date": "2026-01-01", "count": 3}]}
_HAS_ECONOMY = {**_EMPTY_ECONOMY, "payday_by_day": [{"date": "2026-01-01", "total": 500}]}
_HAS_SHOP    = {**_EMPTY_SHOP,    "purchases_by_day": [{"date": "2026-01-01", "count": 2}]}
_HAS_SERVER  = {**_EMPTY_SERVER,  "total_by_server": [{"server": "Island", "count": 10}]}

_FAKE_BUF = io.BytesIO(b"\x89PNG" + b"\x00" * 100)


# ---------------------------------------------------------------------------
# TIME_RANGE_DAYS / TIME_RANGE_LABELS constants
# ---------------------------------------------------------------------------

class TestTimeRangeConstants:

    def test_days_all_keys_present(self):
        assert set(TIME_RANGE_DAYS.keys()) == {"1d", "7d", "30d", "6m", "1y"}

    def test_days_values(self):
        assert TIME_RANGE_DAYS["1d"] == 1
        assert TIME_RANGE_DAYS["7d"] == 7
        assert TIME_RANGE_DAYS["30d"] == 30
        assert TIME_RANGE_DAYS["6m"] == 180
        assert TIME_RANGE_DAYS["1y"] == 365

    def test_labels_all_keys_present(self):
        assert set(TIME_RANGE_LABELS.keys()) == {"1d", "7d", "30d", "6m", "1y"}

    def test_labels_are_strings(self):
        for v in TIME_RANGE_LABELS.values():
            assert isinstance(v, str) and len(v) > 0


# ---------------------------------------------------------------------------
# Chart dicts
# ---------------------------------------------------------------------------

class TestChartDicts:

    def test_player_charts_has_four_entries(self):
        assert len(PLAYER_CHARTS) == 4

    def test_player_charts_keys(self):
        assert set(PLAYER_CHARTS) == {
            "daily_active", "sessions_by_server",
            "avg_duration_by_server", "sessions_by_hour",
        }

    def test_economy_charts_has_four_entries(self):
        assert len(ECONOMY_CHARTS) == 4

    def test_shop_charts_has_four_entries(self):
        assert len(SHOP_CHARTS) == 4

    def test_server_charts_has_four_entries(self):
        assert len(SERVER_CHARTS) == 4

    def test_all_labels_are_non_empty_strings(self):
        for d in [PLAYER_CHARTS, ECONOMY_CHARTS, SHOP_CHARTS, SERVER_CHARTS]:
            for v in d.values():
                assert isinstance(v, str) and len(v) > 0


# ---------------------------------------------------------------------------
# _has_data helper
# ---------------------------------------------------------------------------

class TestHasData:

    def test_all_empty_returns_false(self):
        assert _has_data({"a": [], "b": [], "c": []}) is False

    def test_one_non_empty_returns_true(self):
        assert _has_data({"a": [], "b": [1], "c": []}) is True

    def test_all_non_empty_returns_true(self):
        assert _has_data({"a": [1], "b": [2]}) is True

    def test_empty_dict_returns_false(self):
        assert _has_data({}) is False


# ---------------------------------------------------------------------------
# Cog structure — report subcommands exist
# ---------------------------------------------------------------------------

class TestCogStructure:

    def test_report_group_exists(self):
        cog = _make_cog()
        assert hasattr(cog, "report")
        assert isinstance(cog.report, discord.app_commands.Group)

    def test_report_players_command_exists(self):
        cog = _make_cog()
        names = [cmd.name for cmd in cog.report.commands]
        assert "players" in names

    def test_report_economy_command_exists(self):
        cog = _make_cog()
        names = [cmd.name for cmd in cog.report.commands]
        assert "economy" in names

    def test_report_shop_command_exists(self):
        cog = _make_cog()
        names = [cmd.name for cmd in cog.report.commands]
        assert "shop" in names

    def test_report_activity_command_exists(self):
        cog = _make_cog()
        names = [cmd.name for cmd in cog.report.commands]
        assert "activity" in names

    def test_report_group_has_four_commands(self):
        cog = _make_cog()
        assert len(cog.report.commands) == 4


# ---------------------------------------------------------------------------
# /report players
# ---------------------------------------------------------------------------

class TestReportPlayersCommand:

    @pytest.mark.asyncio
    async def test_defers_ephemerally(self):
        cog = _make_cog()
        interaction = _make_interaction()

        with (
            patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=True)),
            patch("bot.cogs.analytics_dashboard.analytics_db.get_player_report_data",
                  new=AsyncMock(return_value=_HAS_PLAYER)),
        ):
            await cog.report_players.callback(cog, interaction, timerange="7d")

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    @pytest.mark.asyncio
    async def test_blocked_on_free_tier(self):
        """check_feature returns False → no defer, no followup."""
        cog = _make_cog()
        interaction = _make_interaction()

        with patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=False)):
            await cog.report_players.callback(cog, interaction, timerange="7d")

        interaction.response.defer.assert_not_awaited()
        interaction.followup.send.assert_not_called()

    def test_default_timerange_is_7d(self):
        cog = _make_cog()
        sig = inspect.signature(cog.report_players.callback)
        param = sig.parameters.get("timerange")
        assert param is not None
        assert param.default == "7d"

    @pytest.mark.asyncio
    async def test_with_data_sends_embed_and_view(self):
        """With non-empty data → followup.send gets embed + view (ephemeral)."""
        cog = _make_cog()
        interaction = _make_interaction()

        with (
            patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=True)),
            patch("bot.cogs.analytics_dashboard.analytics_db.get_player_report_data",
                  new=AsyncMock(return_value=_HAS_PLAYER)),
        ):
            await cog.report_players.callback(cog, interaction, timerange="7d")

        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.call_args.kwargs
        assert "embed" in kwargs
        assert "view" in kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_no_data_sends_embed_without_view(self):
        """With all-empty data → followup.send gets embed only, no view."""
        cog = _make_cog()
        interaction = _make_interaction()

        with (
            patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=True)),
            patch("bot.cogs.analytics_dashboard.analytics_db.get_player_report_data",
                  new=AsyncMock(return_value=_EMPTY_PLAYER)),
        ):
            await cog.report_players.callback(cog, interaction, timerange="7d")

        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.call_args.kwargs
        assert "embed" in kwargs
        assert kwargs.get("view") is None or "view" not in kwargs
        assert kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# /report economy
# ---------------------------------------------------------------------------

class TestReportEconomyCommand:

    @pytest.mark.asyncio
    async def test_defers_ephemerally(self):
        cog = _make_cog()
        interaction = _make_interaction()

        with (
            patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=True)),
            patch("bot.cogs.analytics_dashboard.analytics_db.get_economy_report_data",
                  new=AsyncMock(return_value=_HAS_ECONOMY)),
        ):
            await cog.report_economy.callback(cog, interaction, timerange="30d")

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    @pytest.mark.asyncio
    async def test_blocked_on_free_tier(self):
        cog = _make_cog()
        interaction = _make_interaction()

        with patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=False)):
            await cog.report_economy.callback(cog, interaction, timerange="7d")

        interaction.followup.send.assert_not_called()

    def test_default_timerange_is_7d(self):
        cog = _make_cog()
        sig = inspect.signature(cog.report_economy.callback)
        assert sig.parameters["timerange"].default == "7d"

    @pytest.mark.asyncio
    async def test_no_data_sends_no_data_embed(self):
        cog = _make_cog()
        interaction = _make_interaction()

        with (
            patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=True)),
            patch("bot.cogs.analytics_dashboard.analytics_db.get_economy_report_data",
                  new=AsyncMock(return_value=_EMPTY_ECONOMY)),
        ):
            await cog.report_economy.callback(cog, interaction, timerange="7d")

        kwargs = interaction.followup.send.call_args.kwargs
        assert "embed" in kwargs
        assert kwargs.get("ephemeral") is True


# ---------------------------------------------------------------------------
# /report shop
# ---------------------------------------------------------------------------

class TestReportShopCommand:

    @pytest.mark.asyncio
    async def test_defers_ephemerally(self):
        cog = _make_cog()
        interaction = _make_interaction()

        with (
            patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=True)),
            patch("bot.cogs.analytics_dashboard.analytics_db.get_shop_report_data",
                  new=AsyncMock(return_value=_HAS_SHOP)),
        ):
            await cog.report_shop.callback(cog, interaction, timerange="7d")

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    @pytest.mark.asyncio
    async def test_blocked_on_free_tier(self):
        cog = _make_cog()
        interaction = _make_interaction()

        with patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=False)):
            await cog.report_shop.callback(cog, interaction, timerange="7d")

        interaction.followup.send.assert_not_called()

    def test_default_timerange_is_7d(self):
        cog = _make_cog()
        sig = inspect.signature(cog.report_shop.callback)
        assert sig.parameters["timerange"].default == "7d"

    @pytest.mark.asyncio
    async def test_with_data_sends_view(self):
        cog = _make_cog()
        interaction = _make_interaction()

        with (
            patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=True)),
            patch("bot.cogs.analytics_dashboard.analytics_db.get_shop_report_data",
                  new=AsyncMock(return_value=_HAS_SHOP)),
        ):
            await cog.report_shop.callback(cog, interaction, timerange="7d")

        kwargs = interaction.followup.send.call_args.kwargs
        assert "view" in kwargs
        assert isinstance(kwargs["view"], ReportChartSelectView)


# ---------------------------------------------------------------------------
# /report activity
# ---------------------------------------------------------------------------

class TestReportActivityCommand:

    @pytest.mark.asyncio
    async def test_defers_ephemerally(self):
        cog = _make_cog()
        interaction = _make_interaction()

        with (
            patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=True)),
            patch("bot.cogs.analytics_dashboard.analytics_db.get_server_report_data",
                  new=AsyncMock(return_value=_HAS_SERVER)),
        ):
            await cog.report_activity.callback(cog, interaction, timerange="6m")

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    @pytest.mark.asyncio
    async def test_blocked_on_free_tier(self):
        cog = _make_cog()
        interaction = _make_interaction()

        with patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=False)):
            await cog.report_activity.callback(cog, interaction, timerange="7d")

        interaction.followup.send.assert_not_called()

    def test_default_timerange_is_7d(self):
        cog = _make_cog()
        sig = inspect.signature(cog.report_activity.callback)
        assert sig.parameters["timerange"].default == "7d"

    @pytest.mark.asyncio
    async def test_1y_timerange_accepted(self):
        """Timerange '1y' → 365 days window — no crash."""
        cog = _make_cog()
        interaction = _make_interaction()

        with (
            patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=True)),
            patch("bot.cogs.analytics_dashboard.analytics_db.get_server_report_data",
                  new=AsyncMock(return_value=_EMPTY_SERVER)),
        ):
            await cog.report_activity.callback(cog, interaction, timerange="1y")

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)

    @pytest.mark.asyncio
    async def test_no_data_sends_no_data_embed(self):
        cog = _make_cog()
        interaction = _make_interaction()

        with (
            patch(CHECK_FEATURE_PATH, new=AsyncMock(return_value=True)),
            patch("bot.cogs.analytics_dashboard.analytics_db.get_server_report_data",
                  new=AsyncMock(return_value=_EMPTY_SERVER)),
        ):
            await cog.report_activity.callback(cog, interaction, timerange="7d")

        kwargs = interaction.followup.send.call_args.kwargs
        assert "embed" in kwargs
        assert "view" not in kwargs or kwargs.get("view") is None


# ---------------------------------------------------------------------------
# ReportChartSelect callback
# ---------------------------------------------------------------------------

class TestReportChartSelectCallback:

    @pytest.mark.asyncio
    async def test_sends_file_on_data(self):
        """Select callback generates chart and sends ephemeral file."""
        fake_buf = io.BytesIO(b"\x89PNG" + b"\x00" * 50)

        select = ReportChartSelect(
            PLAYER_CHARTS,
            _HAS_PLAYER,
            "Test Guild",
            "Last 7 days",
            MagicMock(return_value=fake_buf),
        )
        select._values = ["daily_active"]  # discord.ui.Select has no values setter

        interaction = _make_interaction()

        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(return_value=fake_buf)

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            await select.callback(interaction)

        interaction.response.defer.assert_awaited_once()
        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.call_args.kwargs
        assert "file" in kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_sends_no_data_message_when_generate_returns_none(self):
        """Select callback sends 'no data' text when generate_fn returns None."""
        select = ReportChartSelect(
            PLAYER_CHARTS,
            _HAS_PLAYER,
            "Test Guild",
            "Last 7 days",
            MagicMock(return_value=None),
        )
        select._values = ["daily_active"]

        interaction = _make_interaction()

        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(return_value=None)

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            await select.callback(interaction)

        interaction.followup.send.assert_awaited_once()
        kwargs = interaction.followup.send.call_args.kwargs
        assert "file" not in kwargs
        assert kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_select_has_correct_options(self):
        """Select options match PLAYER_CHARTS dict."""
        select = ReportChartSelect(
            PLAYER_CHARTS, _HAS_PLAYER, "Test Guild", "Last 7 days", MagicMock()
        )
        option_values = {opt.value for opt in select.options}
        assert option_values == set(PLAYER_CHARTS.keys())

    @pytest.mark.asyncio
    async def test_select_view_adds_select_item(self):
        """ReportChartSelectView contains exactly one Select item."""
        view = ReportChartSelectView(
            PLAYER_CHARTS, _HAS_PLAYER, "Test Guild", "Last 7 days", MagicMock()
        )
        select_items = [c for c in view.children
                        if isinstance(c, discord.ui.Select)]
        assert len(select_items) == 1
