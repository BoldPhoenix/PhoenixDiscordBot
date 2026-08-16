"""
Tests for bot/utils/report_generator.py

Covers:
- Each generate_X_report() returns a non-empty BytesIO
- Returned bytes start with PNG magic bytes (valid image)
- Empty data dict (all lists empty) produces placeholder chart — no crash
- No matplotlib figure state leak after generation (fig count stays constant)
"""

import io
import pytest
import matplotlib.pyplot as plt

from bot.utils import report_generator

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

_PNG_MAGIC = b"\x89PNG"

GUILD_NAME = "Test Phoenix Guild"
TIME_LABEL = "Last 7 days"

# Minimal non-empty data structures that exercise all chart paths
_PLAYER_DATA = {
    "daily_active":           [{"date": "2026-02-21", "count": 5},
                               {"date": "2026-02-22", "count": 8}],
    "sessions_by_server":     [{"server": "Island", "count": 20},
                               {"server": "Fjordur", "count": 15}],
    "avg_duration_by_server": [{"server": "Island", "avg_minutes": 45.5},
                               {"server": "Fjordur", "avg_minutes": 30.0}],
    "sessions_by_hour":       [{"hour": h, "count": max(1, 10 - abs(h - 18))}
                               for h in range(0, 24)],
}

_ECONOMY_DATA = {
    "payday_by_day":    [{"date": "2026-02-21", "total": 5000},
                         {"date": "2026-02-22", "total": 7500}],
    "type_breakdown":   [{"type": "payday", "count": 100},
                         {"type": "shop",   "count": 40},
                         {"type": "admin",  "count": 5}],
    "top_balances":     [{"name": f"Player{i}", "balance": 10000 - i * 500}
                         for i in range(10)],
    "cumulative_coins": [{"date": "2026-02-21", "running_total": 5000},
                         {"date": "2026-02-22", "running_total": 12500}],
}

_SHOP_DATA = {
    "purchases_by_day":  [{"date": "2026-02-21", "count": 12},
                          {"date": "2026-02-22", "count": 18}],
    "top_items":         [{"name": "Rocket Launcher", "count": 8},
                          {"name": "C4 Charge",       "count": 5},
                          {"name": "Tek Rifle",       "count": 3}],
    "spend_by_category": [{"category": "weapons", "total": 4000},
                          {"category": "ammo",    "total": 1500},
                          {"category": "armor",   "total": 800}],
    "coins_by_day":      [{"date": "2026-02-21", "total": 2000},
                          {"date": "2026-02-22", "total": 3500}],
}

_SERVER_DATA = {
    "sessions_by_server_day": [
        {"server": "Island",  "date": "2026-02-21", "count": 10},
        {"server": "Island",  "date": "2026-02-22", "count": 12},
        {"server": "Fjordur", "date": "2026-02-21", "count": 5},
        {"server": "Fjordur", "date": "2026-02-22", "count": 7},
    ],
    "total_by_server":    [{"server": "Island",  "count": 22},
                           {"server": "Fjordur", "count": 12}],
    "new_players_by_day": [{"date": "2026-02-21", "count": 3},
                           {"date": "2026-02-22", "count": 5}],
    "activity_by_hour":   [{"hour": h, "count": max(0, 8 - abs(h - 19))}
                           for h in range(0, 24)],
}

_EMPTY_DATA = {k: [] for k in list(_PLAYER_DATA) + list(_ECONOMY_DATA) +
               list(_SHOP_DATA) + list(_SERVER_DATA)}


# ---------------------------------------------------------------------------
# generate_player_report
# ---------------------------------------------------------------------------

class TestGeneratePlayerReport:

    def test_returns_bytesio(self):
        buf = report_generator.generate_player_report(_PLAYER_DATA, GUILD_NAME, TIME_LABEL)
        assert isinstance(buf, io.BytesIO)

    def test_non_empty(self):
        buf = report_generator.generate_player_report(_PLAYER_DATA, GUILD_NAME, TIME_LABEL)
        assert len(buf.getvalue()) > 0

    def test_valid_png_magic(self):
        buf = report_generator.generate_player_report(_PLAYER_DATA, GUILD_NAME, TIME_LABEL)
        assert buf.read(4) == _PNG_MAGIC

    def test_buffer_seeked_to_zero(self):
        buf = report_generator.generate_player_report(_PLAYER_DATA, GUILD_NAME, TIME_LABEL)
        assert buf.tell() == 0

    def test_empty_data_no_crash(self):
        """Empty data dicts produce a placeholder chart without raising."""
        empty = {k: [] for k in _PLAYER_DATA}
        buf = report_generator.generate_player_report(empty, GUILD_NAME, TIME_LABEL)
        assert buf.read(4) == _PNG_MAGIC

    def test_figure_closed_after_call(self):
        """matplotlib does not leak open figures."""
        before = plt.get_fignums()
        report_generator.generate_player_report(_PLAYER_DATA, GUILD_NAME, TIME_LABEL)
        after = plt.get_fignums()
        assert after == before


# ---------------------------------------------------------------------------
# generate_economy_report
# ---------------------------------------------------------------------------

class TestGenerateEconomyReport:

    def test_returns_bytesio(self):
        buf = report_generator.generate_economy_report(_ECONOMY_DATA, GUILD_NAME, TIME_LABEL)
        assert isinstance(buf, io.BytesIO)

    def test_valid_png_magic(self):
        buf = report_generator.generate_economy_report(_ECONOMY_DATA, GUILD_NAME, TIME_LABEL)
        assert buf.read(4) == _PNG_MAGIC

    def test_empty_data_no_crash(self):
        empty = {k: [] for k in _ECONOMY_DATA}
        buf = report_generator.generate_economy_report(empty, GUILD_NAME, TIME_LABEL)
        assert buf.read(4) == _PNG_MAGIC

    def test_figure_closed_after_call(self):
        before = plt.get_fignums()
        report_generator.generate_economy_report(_ECONOMY_DATA, GUILD_NAME, TIME_LABEL)
        after = plt.get_fignums()
        assert after == before

    def test_many_pie_slices_no_crash(self):
        """Pie chart with more slices than SERIES palette entries."""
        many_types = [{"type": f"type_{i}", "count": i + 1} for i in range(20)]
        data = {**_ECONOMY_DATA, "type_breakdown": many_types}
        buf = report_generator.generate_economy_report(data, GUILD_NAME, TIME_LABEL)
        assert buf.read(4) == _PNG_MAGIC


# ---------------------------------------------------------------------------
# generate_shop_report
# ---------------------------------------------------------------------------

class TestGenerateShopReport:

    def test_returns_bytesio(self):
        buf = report_generator.generate_shop_report(_SHOP_DATA, GUILD_NAME, TIME_LABEL)
        assert isinstance(buf, io.BytesIO)

    def test_valid_png_magic(self):
        buf = report_generator.generate_shop_report(_SHOP_DATA, GUILD_NAME, TIME_LABEL)
        assert buf.read(4) == _PNG_MAGIC

    def test_empty_data_no_crash(self):
        empty = {k: [] for k in _SHOP_DATA}
        buf = report_generator.generate_shop_report(empty, GUILD_NAME, TIME_LABEL)
        assert buf.read(4) == _PNG_MAGIC

    def test_figure_closed_after_call(self):
        before = plt.get_fignums()
        report_generator.generate_shop_report(_SHOP_DATA, GUILD_NAME, TIME_LABEL)
        after = plt.get_fignums()
        assert after == before

    def test_long_item_name_truncated(self):
        """Item names longer than 20 chars are truncated — no layout crash."""
        data = {
            **_SHOP_DATA,
            "top_items": [{"name": "A" * 50, "count": 99}],
        }
        buf = report_generator.generate_shop_report(data, GUILD_NAME, TIME_LABEL)
        assert buf.read(4) == _PNG_MAGIC


# ---------------------------------------------------------------------------
# generate_server_report
# ---------------------------------------------------------------------------

class TestGenerateServerReport:

    def test_returns_bytesio(self):
        buf = report_generator.generate_server_report(_SERVER_DATA, GUILD_NAME, TIME_LABEL)
        assert isinstance(buf, io.BytesIO)

    def test_valid_png_magic(self):
        buf = report_generator.generate_server_report(_SERVER_DATA, GUILD_NAME, TIME_LABEL)
        assert buf.read(4) == _PNG_MAGIC

    def test_empty_data_no_crash(self):
        empty = {k: [] for k in _SERVER_DATA}
        buf = report_generator.generate_server_report(empty, GUILD_NAME, TIME_LABEL)
        assert buf.read(4) == _PNG_MAGIC

    def test_figure_closed_after_call(self):
        before = plt.get_fignums()
        report_generator.generate_server_report(_SERVER_DATA, GUILD_NAME, TIME_LABEL)
        after = plt.get_fignums()
        assert after == before

    def test_multi_server_multi_line(self):
        """Multi-server panel renders multiple lines without crash."""
        data = {
            **_SERVER_DATA,
            "sessions_by_server_day": [
                {"server": f"Server{s}", "date": f"2026-02-{d:02d}", "count": s + d}
                for s in range(1, 6)
                for d in range(21, 28)
            ],
        }
        buf = report_generator.generate_server_report(data, GUILD_NAME, TIME_LABEL)
        assert buf.read(4) == _PNG_MAGIC


# ---------------------------------------------------------------------------
# Style constants sanity check
# ---------------------------------------------------------------------------

class TestStyleConstants:

    def test_bg_color_format(self):
        assert report_generator.BG.startswith("#")
        assert len(report_generator.BG) == 7

    def test_series_has_five_entries(self):
        assert len(report_generator.SERIES) == 5

    def test_figure_dimensions(self):
        assert report_generator.FIGURE_W == 12
        assert report_generator.FIGURE_H == 9
        assert report_generator.DPI == 100

    def test_four_axes_returned(self):
        """_create_figure returns a figure and exactly 4 axes."""
        fig, axes = report_generator._create_figure("Test", "Guild", "7d")
        assert len(axes) == 4
        plt.close(fig)

    def test_finalize_returns_seeked_buffer(self):
        """_finalize closes the figure and returns seeked BytesIO."""
        fig, _ = report_generator._create_figure("Test", "Guild", "7d")
        before = plt.get_fignums()
        buf = report_generator._finalize(fig)
        after = plt.get_fignums()
        assert buf.tell() == 0
        assert len(after) < len(before)  # figure was closed

    def test_create_figure_single_returns_single_axis(self):
        """_create_figure_single returns a figure and exactly one axis."""
        fig, ax = report_generator._create_figure_single("Test", "Guild", "7d")
        assert ax is not None
        assert not isinstance(ax, list)
        plt.close(fig)

    def test_figure_h_single_constant(self):
        assert report_generator.FIGURE_H_SINGLE == 7


# ---------------------------------------------------------------------------
# generate_player_chart — single-chart API
# ---------------------------------------------------------------------------

class TestGeneratePlayerChart:

    def test_valid_key_returns_png(self):
        buf = report_generator.generate_player_chart(
            "daily_active", _PLAYER_DATA, GUILD_NAME, TIME_LABEL
        )
        assert buf is not None
        assert buf.read(4) == _PNG_MAGIC

    def test_all_valid_keys_return_png(self):
        for key in ["daily_active", "sessions_by_server",
                    "avg_duration_by_server", "sessions_by_hour"]:
            buf = report_generator.generate_player_chart(
                key, _PLAYER_DATA, GUILD_NAME, TIME_LABEL
            )
            assert buf is not None, f"Expected PNG for key={key}"
            buf.seek(0)
            assert buf.read(4) == _PNG_MAGIC

    def test_empty_data_returns_none(self):
        empty = {k: [] for k in _PLAYER_DATA}
        buf = report_generator.generate_player_chart(
            "daily_active", empty, GUILD_NAME, TIME_LABEL
        )
        assert buf is None

    def test_unknown_key_returns_none(self):
        buf = report_generator.generate_player_chart(
            "nonexistent_key", _PLAYER_DATA, GUILD_NAME, TIME_LABEL
        )
        assert buf is None

    def test_figure_closed_after_call(self):
        before = plt.get_fignums()
        report_generator.generate_player_chart(
            "daily_active", _PLAYER_DATA, GUILD_NAME, TIME_LABEL
        )
        after = plt.get_fignums()
        assert after == before

    def test_buffer_seeked_to_zero(self):
        buf = report_generator.generate_player_chart(
            "sessions_by_hour", _PLAYER_DATA, GUILD_NAME, TIME_LABEL
        )
        assert buf is not None
        assert buf.tell() == 0


# ---------------------------------------------------------------------------
# generate_economy_chart — single-chart API
# ---------------------------------------------------------------------------

class TestGenerateEconomyChart:

    def test_all_valid_keys_return_png(self):
        for key in ["payday_by_day", "type_breakdown",
                    "top_balances", "cumulative_coins"]:
            buf = report_generator.generate_economy_chart(
                key, _ECONOMY_DATA, GUILD_NAME, TIME_LABEL
            )
            assert buf is not None, f"Expected PNG for key={key}"
            buf.seek(0)
            assert buf.read(4) == _PNG_MAGIC

    def test_empty_data_returns_none(self):
        empty = {k: [] for k in _ECONOMY_DATA}
        buf = report_generator.generate_economy_chart(
            "payday_by_day", empty, GUILD_NAME, TIME_LABEL
        )
        assert buf is None

    def test_unknown_key_returns_none(self):
        assert report_generator.generate_economy_chart(
            "bad_key", _ECONOMY_DATA, GUILD_NAME, TIME_LABEL
        ) is None

    def test_figure_closed_after_call(self):
        before = plt.get_fignums()
        report_generator.generate_economy_chart(
            "top_balances", _ECONOMY_DATA, GUILD_NAME, TIME_LABEL
        )
        after = plt.get_fignums()
        assert after == before


# ---------------------------------------------------------------------------
# generate_shop_chart — single-chart API
# ---------------------------------------------------------------------------

class TestGenerateShopChart:

    def test_all_valid_keys_return_png(self):
        for key in ["purchases_by_day", "top_items",
                    "spend_by_category", "coins_by_day"]:
            buf = report_generator.generate_shop_chart(
                key, _SHOP_DATA, GUILD_NAME, TIME_LABEL
            )
            assert buf is not None, f"Expected PNG for key={key}"
            buf.seek(0)
            assert buf.read(4) == _PNG_MAGIC

    def test_empty_data_returns_none(self):
        empty = {k: [] for k in _SHOP_DATA}
        buf = report_generator.generate_shop_chart(
            "top_items", empty, GUILD_NAME, TIME_LABEL
        )
        assert buf is None

    def test_unknown_key_returns_none(self):
        assert report_generator.generate_shop_chart(
            "bad_key", _SHOP_DATA, GUILD_NAME, TIME_LABEL
        ) is None

    def test_figure_closed_after_call(self):
        before = plt.get_fignums()
        report_generator.generate_shop_chart(
            "purchases_by_day", _SHOP_DATA, GUILD_NAME, TIME_LABEL
        )
        after = plt.get_fignums()
        assert after == before


# ---------------------------------------------------------------------------
# generate_server_chart — single-chart API
# ---------------------------------------------------------------------------

class TestGenerateServerChart:

    def test_all_valid_keys_return_png(self):
        for key in ["sessions_by_server_day", "total_by_server",
                    "new_players_by_day", "activity_by_hour"]:
            buf = report_generator.generate_server_chart(
                key, _SERVER_DATA, GUILD_NAME, TIME_LABEL
            )
            assert buf is not None, f"Expected PNG for key={key}"
            buf.seek(0)
            assert buf.read(4) == _PNG_MAGIC

    def test_empty_data_returns_none(self):
        empty = {k: [] for k in _SERVER_DATA}
        buf = report_generator.generate_server_chart(
            "total_by_server", empty, GUILD_NAME, TIME_LABEL
        )
        assert buf is None

    def test_unknown_key_returns_none(self):
        assert report_generator.generate_server_chart(
            "bad_key", _SERVER_DATA, GUILD_NAME, TIME_LABEL
        ) is None

    def test_multiline_chart_returns_png(self):
        """sessions_by_server_day uses special multi-line renderer — must not crash."""
        buf = report_generator.generate_server_chart(
            "sessions_by_server_day", _SERVER_DATA, GUILD_NAME, TIME_LABEL
        )
        assert buf is not None
        buf.seek(0)
        assert buf.read(4) == _PNG_MAGIC

    def test_figure_closed_after_call(self):
        before = plt.get_fignums()
        report_generator.generate_server_chart(
            "activity_by_hour", _SERVER_DATA, GUILD_NAME, TIME_LABEL
        )
        after = plt.get_fignums()
        assert after == before
