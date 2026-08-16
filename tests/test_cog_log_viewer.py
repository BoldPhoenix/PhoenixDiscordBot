"""
Tests for log_viewer.py - LogViewer cog and LogViewerView pagination.

Tests cover:
- LogViewer cog instantiation
- LogViewerView initialization attributes
- total_pages calculation (standard and edge cases)
- get_current_page() slicing
- update_buttons() state for first/last page
- Button presence on the view
- _analyze_logs() level counting
- _analyze_logs() common pattern counting
- _analyze_logs() empty input
- Expected commands on LogViewer
- get_agent_manager() behaviour with no agent_manager on bot

Uses real discord.py objects. All View/Embed tests are async.
"""

import pytest
from types import SimpleNamespace
import inspect


def _make_bot(agent_manager=None):
    """Minimal fake bot object."""
    bot = SimpleNamespace()
    if agent_manager is not None:
        bot.agent_manager = agent_manager
    return bot


# ---------------------------------------------------------------------------
# LogViewer cog tests
# ---------------------------------------------------------------------------

class TestLogViewerCogInit:
    def test_cog_instantiation(self):
        """LogViewer can be instantiated with a fake bot."""
        from bot.cogs.log_viewer import LogViewer
        bot = _make_bot()
        cog = LogViewer(bot)
        assert cog is not None
        assert cog.bot is bot

    def test_cog_has_agent_manager_none_by_default(self):
        """LogViewer starts with agent_manager = None."""
        from bot.cogs.log_viewer import LogViewer
        bot = _make_bot()
        cog = LogViewer(bot)
        assert cog.agent_manager is None

    def test_get_agent_manager_returns_none_when_bot_has_no_attribute(self):
        """get_agent_manager() returns None when bot has no agent_manager attribute."""
        from bot.cogs.log_viewer import LogViewer
        bot = SimpleNamespace()  # No agent_manager attribute at all
        cog = LogViewer(bot)
        result = cog.get_agent_manager()
        assert result is None

    def test_get_agent_manager_returns_manager_when_present(self):
        """get_agent_manager() returns the agent_manager if bot has it set."""
        from bot.cogs.log_viewer import LogViewer
        fake_manager = object()
        bot = _make_bot(agent_manager=fake_manager)
        cog = LogViewer(bot)
        assert cog.get_agent_manager() is fake_manager


class TestLogViewerCommands:
    def test_has_serverlogs_command(self):
        """LogViewer has a serverlogs command."""
        from bot.cogs.log_viewer import LogViewer
        assert hasattr(LogViewer, "server_logs")

    def test_has_searchlogs_command(self):
        """LogViewer has a searchlogs command."""
        from bot.cogs.log_viewer import LogViewer
        assert hasattr(LogViewer, "search_logs")

    def test_has_logstats_command(self):
        """LogViewer has a logstats command."""
        from bot.cogs.log_viewer import LogViewer
        assert hasattr(LogViewer, "log_stats")

    def test_setup_function_exists(self):
        """Module-level setup() function exists in log_viewer."""
        import bot.cogs.log_viewer as module
        assert hasattr(module, "setup")
        assert inspect.iscoroutinefunction(module.setup)


# ---------------------------------------------------------------------------
# LogViewerView tests (async — discord.py Views need an event loop)
# ---------------------------------------------------------------------------

class TestLogViewerViewInit:
    @pytest.mark.asyncio
    async def test_view_initialises_with_correct_attributes(self):
        """LogViewerView stores logs, server_name, lines_per_page, and starts on page 0."""
        from bot.cogs.log_viewer import LogViewerView
        logs = [f"log line {i}" for i in range(40)]
        view = LogViewerView(logs, "TestServer", 20, None, None, 123)
        assert view.logs is logs
        assert view.server_name == "TestServer"
        assert view.lines_per_page == 20
        assert view.current_page == 0
        assert view.user_id == 123

    @pytest.mark.asyncio
    async def test_total_pages_100_logs_20_per_page(self):
        """100 logs / 20 per page = exactly 5 pages."""
        from bot.cogs.log_viewer import LogViewerView
        logs = [f"line {i}" for i in range(100)]
        view = LogViewerView(logs, "Server", 20, None, None, 1)
        assert view.total_pages == 5

    @pytest.mark.asyncio
    async def test_total_pages_1_log_20_per_page(self):
        """1 log line / 20 per page = 1 page (edge case, no zero pages)."""
        from bot.cogs.log_viewer import LogViewerView
        view = LogViewerView(["single line"], "Server", 20, None, None, 1)
        assert view.total_pages == 1

    @pytest.mark.asyncio
    async def test_total_pages_21_logs_20_per_page(self):
        """21 logs / 20 per page = 2 pages (ceiling division)."""
        from bot.cogs.log_viewer import LogViewerView
        logs = [f"line {i}" for i in range(21)]
        view = LogViewerView(logs, "Server", 20, None, None, 1)
        assert view.total_pages == 2

    @pytest.mark.asyncio
    async def test_total_pages_empty_logs(self):
        """Empty log list still gives at least 1 page."""
        from bot.cogs.log_viewer import LogViewerView
        view = LogViewerView([], "Server", 20, None, None, 1)
        assert view.total_pages >= 1

    @pytest.mark.asyncio
    async def test_view_has_prev_button(self):
        """LogViewerView creates a prev_button attribute."""
        from bot.cogs.log_viewer import LogViewerView
        view = LogViewerView(["line"], "Server", 20, None, None, 1)
        assert hasattr(view, "prev_button")
        assert view.prev_button is not None

    @pytest.mark.asyncio
    async def test_view_has_next_button(self):
        """LogViewerView creates a next_button attribute."""
        from bot.cogs.log_viewer import LogViewerView
        view = LogViewerView(["line"], "Server", 20, None, None, 1)
        assert hasattr(view, "next_button")
        assert view.next_button is not None

    @pytest.mark.asyncio
    async def test_both_buttons_added_to_children(self):
        """Both prev and next buttons are added to the view's children list."""
        import discord
        from bot.cogs.log_viewer import LogViewerView
        view = LogViewerView(["line1", "line2"], "Server", 20, None, None, 1)
        buttons = [c for c in view.children if isinstance(c, discord.ui.Button)]
        assert len(buttons) == 2


class TestLogViewerViewGetCurrentPage:
    @pytest.mark.asyncio
    async def test_get_current_page_returns_first_slice(self):
        """get_current_page() returns lines 0..lines_per_page on page 0."""
        from bot.cogs.log_viewer import LogViewerView
        logs = [f"line {i}" for i in range(50)]
        view = LogViewerView(logs, "Server", 10, None, None, 1)
        page_text = view.get_current_page()
        assert "line 0" in page_text
        assert "line 9" in page_text
        assert "line 10" not in page_text

    @pytest.mark.asyncio
    async def test_get_current_page_second_page(self):
        """get_current_page() returns lines 10..19 after advancing to page 1."""
        from bot.cogs.log_viewer import LogViewerView
        logs = [f"line {i}" for i in range(50)]
        view = LogViewerView(logs, "Server", 10, None, None, 1)
        view.current_page = 1
        page_text = view.get_current_page()
        assert "line 10" in page_text
        assert "line 19" in page_text
        assert "line 9" not in page_text

    @pytest.mark.asyncio
    async def test_get_current_page_last_page_partial(self):
        """get_current_page() handles a partial final page correctly."""
        from bot.cogs.log_viewer import LogViewerView
        logs = [f"line {i}" for i in range(25)]
        view = LogViewerView(logs, "Server", 10, None, None, 1)
        view.current_page = 2  # page 3: lines 20-24
        page_text = view.get_current_page()
        assert "line 20" in page_text
        assert "line 24" in page_text


class TestLogViewerViewUpdateButtons:
    @pytest.mark.asyncio
    async def test_prev_disabled_on_first_page(self):
        """prev_button is disabled when current_page == 0."""
        from bot.cogs.log_viewer import LogViewerView
        logs = [f"line {i}" for i in range(40)]
        view = LogViewerView(logs, "Server", 10, None, None, 1)
        # page 0 (initial)
        view.update_buttons()
        assert view.prev_button.disabled is True

    @pytest.mark.asyncio
    async def test_next_disabled_on_last_page(self):
        """next_button is disabled when current_page is the last page."""
        from bot.cogs.log_viewer import LogViewerView
        logs = [f"line {i}" for i in range(40)]
        view = LogViewerView(logs, "Server", 10, None, None, 1)
        view.current_page = view.total_pages - 1
        view.update_buttons()
        assert view.next_button.disabled is True

    @pytest.mark.asyncio
    async def test_both_enabled_on_middle_page(self):
        """Both buttons are enabled on a middle page."""
        from bot.cogs.log_viewer import LogViewerView
        logs = [f"line {i}" for i in range(50)]
        view = LogViewerView(logs, "Server", 10, None, None, 1)
        view.current_page = 2  # middle page out of 5
        view.update_buttons()
        assert view.prev_button.disabled is False
        assert view.next_button.disabled is False

    @pytest.mark.asyncio
    async def test_single_page_both_disabled(self):
        """When there is only 1 page, both prev and next are disabled."""
        from bot.cogs.log_viewer import LogViewerView
        view = LogViewerView(["only line"], "Server", 20, None, None, 1)
        # update_buttons is called in __init__, verify state
        assert view.prev_button.disabled is True
        assert view.next_button.disabled is True


# ---------------------------------------------------------------------------
# LogViewer._analyze_logs tests (pure logic, synchronous)
# ---------------------------------------------------------------------------

class TestAnalyzeLogs:
    def _get_cog(self):
        from bot.cogs.log_viewer import LogViewer
        bot = SimpleNamespace()
        return LogViewer(bot)

    def test_counts_errors(self):
        """_analyze_logs counts [ERROR] lines correctly."""
        cog = self._get_cog()
        logs = ["`[ERROR] something went wrong`", "`[INFO] normal line`", "`[ERROR] another error`"]
        stats = cog._analyze_logs(logs)
        assert stats["errors"] == 2

    def test_counts_warnings_warn(self):
        """_analyze_logs counts [WARN] lines correctly."""
        cog = self._get_cog()
        logs = ["`[WARN] disk space low`", "`[WARNING] memory high`"]
        stats = cog._analyze_logs(logs)
        assert stats["warnings"] == 2

    def test_counts_info(self):
        """_analyze_logs counts [INFO] lines."""
        cog = self._get_cog()
        logs = ["`[INFO] server started`", "`[INFO] loading map`"]
        stats = cog._analyze_logs(logs)
        assert stats["info"] == 2

    def test_counts_debug(self):
        """_analyze_logs counts [DEBUG] lines."""
        cog = self._get_cog()
        logs = ["`[DEBUG] trace output here`"]
        stats = cog._analyze_logs(logs)
        assert stats["debug"] == 1

    def test_empty_logs_returns_zero_counts(self):
        """_analyze_logs returns zeros for all counters when given empty list."""
        cog = self._get_cog()
        stats = cog._analyze_logs([])
        assert stats["errors"] == 0
        assert stats["warnings"] == 0
        assert stats["info"] == 0
        assert stats["debug"] == 0
        assert stats["common_patterns"] == {}

    def test_common_pattern_player(self):
        """_analyze_logs counts PLAYER occurrences in common_patterns."""
        cog = self._get_cog()
        logs = [
            "`PLAYER joined the game`",
            "`PLAYER left the game`",
            "`tribe raid started`",
        ]
        stats = cog._analyze_logs(logs)
        assert stats["common_patterns"].get("PLAYER", 0) == 2

    def test_common_pattern_tribe(self):
        """_analyze_logs counts TRIBE occurrences."""
        cog = self._get_cog()
        logs = ["`TRIBE destroyed enemy base`", "`[INFO] server tick`"]
        stats = cog._analyze_logs(logs)
        assert stats["common_patterns"].get("TRIBE", 0) == 1

    def test_common_pattern_multiple(self):
        """_analyze_logs picks up multiple common patterns from a single line."""
        cog = self._get_cog()
        logs = ["`PLAYER killed a DINO`"]
        stats = cog._analyze_logs(logs)
        assert stats["common_patterns"].get("PLAYER", 0) >= 1
        assert stats["common_patterns"].get("DINO", 0) >= 1

    def test_common_patterns_sorted_by_frequency(self):
        """_analyze_logs sorts common_patterns by frequency descending."""
        cog = self._get_cog()
        logs = (
            ["`PLAYER event`"] * 5
            + ["`TRIBE event`"] * 3
            + ["`DINO event`"] * 1
        )
        stats = cog._analyze_logs(logs)
        keys = list(stats["common_patterns"].keys())
        # PLAYER (5) should appear before TRIBE (3) which before DINO (1)
        assert keys.index("PLAYER") < keys.index("TRIBE")
        assert keys.index("TRIBE") < keys.index("DINO")

    def test_mixed_levels_only_first_match_counted(self):
        """A line matching [ERROR] is not also counted as [WARN] or [INFO]."""
        cog = self._get_cog()
        logs = ["`[ERROR] something`"]
        stats = cog._analyze_logs(logs)
        assert stats["errors"] == 1
        assert stats["warnings"] == 0
        assert stats["info"] == 0
        assert stats["debug"] == 0
