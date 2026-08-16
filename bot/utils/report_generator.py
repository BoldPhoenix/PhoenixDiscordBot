"""
Report generator — creates dark-themed PNG charts using matplotlib.
All rendering is in-memory (BytesIO). No disk I/O.

Uses the non-interactive Agg backend so it is safe to call from async code.
"""

import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — must be set before importing pyplot
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.figure import Figure

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------
BG      = "#1a1a2e"   # deep navy background
PANEL   = "#16213e"   # subplot face colour
ACCENT  = "#e94560"   # phoenix red — primary series
GRID    = "#2d2d44"   # subtle grid lines
TEXT    = "#eaeaea"   # all labels and titles
SERIES  = ["#e94560", "#0f3460", "#533483", "#05c46b", "#f0a500"]  # multi-series palette

FIGURE_W = 12   # inches @ 100 DPI → 1200 px
FIGURE_H = 9    # inches @ 100 DPI → 900 px
FIGURE_H_SINGLE = 7   # single-chart height → 1200×700 px
DPI      = 100


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _create_figure(title: str, guild_name: str, time_label: str):
    """
    Create a 1200×900 dark figure with a header strip and 2×2 subplot grid.

    Returns (fig, [ax0, ax1, ax2, ax3]).
    """
    fig = plt.figure(figsize=(FIGURE_W, FIGURE_H), facecolor=BG, dpi=DPI)

    # Header strip — report title + guild + time range + timestamp
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    header = f"{title}  ·  {guild_name}  ·  {time_label}  ·  {timestamp}"
    fig.text(
        0.5, 0.97, header,
        ha="center", va="top",
        color=TEXT, fontsize=11, fontweight="bold",
    )

    # Footer strip
    fig.text(
        0.5, 0.01, "Phoenix ARK Bot Analytics",
        ha="center", va="bottom",
        color=GRID, fontsize=9, style="italic",
    )

    # 2×2 grid — leave room for header (top) and footer (bottom)
    axes = fig.subplots(2, 2)
    axes_flat = [axes[0][0], axes[0][1], axes[1][0], axes[1][1]]

    for ax in axes_flat:
        ax.set_facecolor(PANEL)
        ax.tick_params(colors=TEXT, labelsize=8)
        ax.xaxis.label.set_color(TEXT)
        ax.yaxis.label.set_color(TEXT)
        ax.title.set_color(TEXT)
        for spine in ax.spines.values():
            spine.set_edgecolor(GRID)
        ax.grid(color=GRID, linewidth=0.5, linestyle="--", alpha=0.7)

    fig.subplots_adjust(
        top=0.93, bottom=0.07,
        left=0.08, right=0.97,
        hspace=0.40, wspace=0.35,
    )

    return fig, axes_flat


def _finalize(fig: Figure) -> io.BytesIO:
    """Save figure to BytesIO buffer, close figure, return buffer seeked to 0."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf


def _no_data_panel(ax, label: str):
    """Render a centred 'No data available' message on an axis."""
    ax.set_title(label, fontsize=9, color=TEXT, pad=6)
    ax.text(
        0.5, 0.5, "No data available",
        ha="center", va="center",
        transform=ax.transAxes,
        color=GRID, fontsize=10,
    )
    ax.set_xticks([])
    ax.set_yticks([])


def _line_chart(ax, rows, x_key: str, y_key: str, title: str, color=ACCENT):
    """Draw a simple line chart from a list of dicts."""
    ax.set_title(title, fontsize=9, color=TEXT, pad=6)
    if not rows:
        _no_data_panel(ax, title)
        return
    xs = [r[x_key] for r in rows]
    ys = [r[y_key] or 0 for r in rows]
    ax.plot(xs, ys, color=color, linewidth=1.5, marker="o", markersize=3)
    ax.fill_between(range(len(xs)), ys, alpha=0.15, color=color)
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs, rotation=45, ha="right", fontsize=7)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))


def _hbar_chart(ax, rows, label_key: str, value_key: str, title: str, color=ACCENT):
    """Draw a horizontal bar chart from a list of dicts."""
    ax.set_title(title, fontsize=9, color=TEXT, pad=6)
    if not rows:
        _no_data_panel(ax, title)
        return
    labels = [str(r[label_key])[:20] for r in rows]
    values = [r[value_key] or 0 for r in rows]
    y_pos = range(len(labels))
    ax.barh(y_pos, values, color=color, height=0.6)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))


def _bar_chart(ax, rows, x_key: str, y_key: str, title: str, color=ACCENT):
    """Draw a vertical bar chart from a list of dicts."""
    ax.set_title(title, fontsize=9, color=TEXT, pad=6)
    if not rows:
        _no_data_panel(ax, title)
        return
    xs = [str(r[x_key]) for r in rows]
    ys = [r[y_key] or 0 for r in rows]
    ax.bar(range(len(xs)), ys, color=color, width=0.6)
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(xs, rotation=45, ha="right", fontsize=7)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))


def _pie_chart(ax, rows, label_key: str, value_key: str, title: str):
    """Draw a pie chart from a list of dicts."""
    ax.set_title(title, fontsize=9, color=TEXT, pad=6)
    if not rows:
        _no_data_panel(ax, title)
        return
    labels = [str(r[label_key])[:16] for r in rows]
    values = [r[value_key] or 0 for r in rows]
    colours = (SERIES * ((len(labels) // len(SERIES)) + 1))[: len(labels)]
    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels,
        colors=colours,
        autopct="%1.0f%%",
        startangle=90,
        textprops={"color": TEXT, "fontsize": 7},
    )
    for at in autotexts:
        at.set_fontsize(7)
        at.set_color(BG)


# ---------------------------------------------------------------------------
# Public API — 4-panel reports (kept for backwards compatibility)
# ---------------------------------------------------------------------------

def generate_player_report(data: dict, guild_name: str, time_label: str) -> io.BytesIO:
    """Generate the 'Players' report PNG and return a BytesIO buffer."""
    fig, (ax0, ax1, ax2, ax3) = _create_figure(
        "Player Activity Report", guild_name, time_label
    )

    _line_chart(ax0, data.get("daily_active", []), "date", "count",
                "Daily Active Players")

    _hbar_chart(ax1, data.get("sessions_by_server", []), "server", "count",
                "Sessions per Server")

    _hbar_chart(ax2, data.get("avg_duration_by_server", []), "server", "avg_minutes",
                "Avg Session Duration (min)")

    _bar_chart(ax3, data.get("sessions_by_hour", []), "hour", "count",
               "Sessions by Hour of Day")

    return _finalize(fig)


def generate_economy_report(data: dict, guild_name: str, time_label: str) -> io.BytesIO:
    """Generate the 'Economy' report PNG and return a BytesIO buffer."""
    fig, (ax0, ax1, ax2, ax3) = _create_figure(
        "Economy Report", guild_name, time_label
    )

    _line_chart(ax0, data.get("payday_by_day", []), "date", "total",
                "Coins Distributed per Day (Payday)")

    _pie_chart(ax1, data.get("type_breakdown", []), "type", "count",
               "Transaction Type Breakdown")

    _hbar_chart(ax2, data.get("top_balances", []), "name", "balance",
                "Top 10 Player Balances")

    _line_chart(ax3, data.get("cumulative_coins", []), "date", "running_total",
                "Cumulative Coins in Circulation", color=SERIES[2])

    return _finalize(fig)


def generate_shop_report(data: dict, guild_name: str, time_label: str) -> io.BytesIO:
    """Generate the 'Shop' report PNG and return a BytesIO buffer."""
    fig, (ax0, ax1, ax2, ax3) = _create_figure(
        "Shop Report", guild_name, time_label
    )

    _line_chart(ax0, data.get("purchases_by_day", []), "date", "count",
                "Purchases per Day")

    _hbar_chart(ax1, data.get("top_items", []), "name", "count",
                "Top 10 Items Purchased")

    _pie_chart(ax2, data.get("spend_by_category", []), "category", "total",
               "Spend by Category")

    _line_chart(ax3, data.get("coins_by_day", []), "date", "total",
                "Coins Spent per Day", color=SERIES[3])

    return _finalize(fig)


def generate_server_report(data: dict, guild_name: str, time_label: str) -> io.BytesIO:
    """Generate the 'Servers' report PNG and return a BytesIO buffer."""
    fig, (ax0, ax1, ax2, ax3) = _create_figure(
        "Server Activity Report", guild_name, time_label
    )

    # Panel 1: Multi-line — sessions per server per day
    ax0.set_title("Sessions per Server Over Time", fontsize=9, color=TEXT, pad=6)
    server_day_rows = data.get("sessions_by_server_day", [])
    if server_day_rows:
        # Group by server
        servers: dict = {}
        all_dates: list = []
        for r in server_day_rows:
            srv = r["server"]
            dt  = r["date"]
            if dt not in all_dates:
                all_dates.append(dt)
            servers.setdefault(srv, {})[dt] = r["count"]

        all_dates.sort()
        for idx, (srv, date_map) in enumerate(servers.items()):
            ys = [date_map.get(d, 0) for d in all_dates]
            colour = SERIES[idx % len(SERIES)]
            ax0.plot(
                range(len(all_dates)), ys,
                color=colour, linewidth=1.5, marker="o", markersize=3,
                label=srv[:12],
            )
        ax0.set_xticks(range(len(all_dates)))
        ax0.set_xticklabels(all_dates, rotation=45, ha="right", fontsize=7)
        ax0.legend(fontsize=7, facecolor=PANEL, labelcolor=TEXT, framealpha=0.5)
        ax0.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    else:
        _no_data_panel(ax0, "Sessions per Server Over Time")

    _bar_chart(ax1, data.get("total_by_server", []), "server", "count",
               "Total Sessions per Server")

    _line_chart(ax2, data.get("new_players_by_day", []), "date", "count",
                "New Players per Day", color=SERIES[3])

    _bar_chart(ax3, data.get("activity_by_hour", []), "hour", "count",
               "Activity by Hour of Day", color=SERIES[2])

    return _finalize(fig)


# ---------------------------------------------------------------------------
# Single-chart API — used by the /report dropdown UX
# ---------------------------------------------------------------------------

def _create_figure_single(title: str, guild_name: str, time_label: str):
    """
    Create a 1200×700 single-panel dark figure with header and footer strips.

    Returns (fig, ax).
    """
    fig = plt.figure(figsize=(FIGURE_W, FIGURE_H_SINGLE), facecolor=BG, dpi=DPI)

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    header = f"{title}  ·  {guild_name}  ·  {time_label}  ·  {timestamp}"
    fig.text(
        0.5, 0.97, header,
        ha="center", va="top",
        color=TEXT, fontsize=11, fontweight="bold",
    )
    fig.text(
        0.5, 0.01, "Phoenix ARK Bot Analytics",
        ha="center", va="bottom",
        color=GRID, fontsize=9, style="italic",
    )

    ax = fig.add_subplot(1, 1, 1)
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=TEXT, labelsize=9)
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)
    ax.title.set_color(TEXT)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.grid(color=GRID, linewidth=0.5, linestyle="--", alpha=0.7)

    fig.subplots_adjust(top=0.90, bottom=0.13, left=0.11, right=0.96)
    return fig, ax


def _draw_server_day_multiline(ax, rows: list) -> None:
    """Render 'sessions per server per day' as overlapping lines on a single axis."""
    servers: dict = {}
    all_dates: list = []
    for r in rows:
        srv = r["server"]
        dt = r["date"]
        if dt not in all_dates:
            all_dates.append(dt)
        servers.setdefault(srv, {})[dt] = r["count"]
    all_dates.sort()
    for idx, (srv, date_map) in enumerate(servers.items()):
        ys = [date_map.get(d, 0) for d in all_dates]
        colour = SERIES[idx % len(SERIES)]
        ax.plot(
            range(len(all_dates)), ys,
            color=colour, linewidth=1.5, marker="o", markersize=4,
            label=srv[:12],
        )
    ax.set_xticks(range(len(all_dates)))
    ax.set_xticklabels(all_dates, rotation=45, ha="right", fontsize=8)
    ax.legend(fontsize=8, facecolor=PANEL, labelcolor=TEXT, framealpha=0.5)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))


def _render_single(title: str, draw_fn, data: dict, key: str,
                   guild_name: str, time_label: str) -> "io.BytesIO | None":
    """Common helper: check data presence, create single figure, draw, finalize."""
    if not data.get(key):
        return None
    fig, ax = _create_figure_single(title, guild_name, time_label)
    draw_fn(ax)
    ax.set_title(title, fontsize=12, color=TEXT, pad=8)
    return _finalize(fig)


def generate_player_chart(chart_key: str, data: dict,
                           guild_name: str, time_label: str) -> "io.BytesIO | None":
    """
    Generate one player-activity chart by key.  Returns None when data is empty.

    Valid keys: daily_active, sessions_by_server, avg_duration_by_server, sessions_by_hour
    """
    _DRAWS = {
        "daily_active": (
            "Daily Active Players",
            lambda ax: _line_chart(ax, data.get("daily_active", []),
                                   "date", "count", "Daily Active Players"),
        ),
        "sessions_by_server": (
            "Sessions per Server",
            lambda ax: _hbar_chart(ax, data.get("sessions_by_server", []),
                                   "server", "count", "Sessions per Server"),
        ),
        "avg_duration_by_server": (
            "Avg Session Duration (min)",
            lambda ax: _hbar_chart(ax, data.get("avg_duration_by_server", []),
                                   "server", "avg_minutes", "Avg Session Duration (min)"),
        ),
        "sessions_by_hour": (
            "Sessions by Hour of Day",
            lambda ax: _bar_chart(ax, data.get("sessions_by_hour", []),
                                  "hour", "count", "Sessions by Hour of Day"),
        ),
    }
    if chart_key not in _DRAWS:
        return None
    title, draw = _DRAWS[chart_key]
    return _render_single(title, draw, data, chart_key, guild_name, time_label)


def generate_economy_chart(chart_key: str, data: dict,
                            guild_name: str, time_label: str) -> "io.BytesIO | None":
    """
    Generate one economy chart by key.  Returns None when data is empty.

    Valid keys: payday_by_day, type_breakdown, top_balances, cumulative_coins
    """
    _DRAWS = {
        "payday_by_day": (
            "Coins Distributed per Day",
            lambda ax: _line_chart(ax, data.get("payday_by_day", []),
                                   "date", "total", "Coins Distributed per Day"),
        ),
        "type_breakdown": (
            "Transaction Type Breakdown",
            lambda ax: _pie_chart(ax, data.get("type_breakdown", []),
                                  "type", "count", "Transaction Type Breakdown"),
        ),
        "top_balances": (
            "Top 10 Player Balances",
            lambda ax: _hbar_chart(ax, data.get("top_balances", []),
                                   "name", "balance", "Top 10 Player Balances"),
        ),
        "cumulative_coins": (
            "Cumulative Coins in Circulation",
            lambda ax: _line_chart(ax, data.get("cumulative_coins", []),
                                   "date", "running_total",
                                   "Cumulative Coins in Circulation", color=SERIES[2]),
        ),
    }
    if chart_key not in _DRAWS:
        return None
    title, draw = _DRAWS[chart_key]
    return _render_single(title, draw, data, chart_key, guild_name, time_label)


def generate_shop_chart(chart_key: str, data: dict,
                         guild_name: str, time_label: str) -> "io.BytesIO | None":
    """
    Generate one shop chart by key.  Returns None when data is empty.

    Valid keys: purchases_by_day, top_items, spend_by_category, coins_by_day
    """
    _DRAWS = {
        "purchases_by_day": (
            "Purchases per Day",
            lambda ax: _line_chart(ax, data.get("purchases_by_day", []),
                                   "date", "count", "Purchases per Day"),
        ),
        "top_items": (
            "Top 10 Items Purchased",
            lambda ax: _hbar_chart(ax, data.get("top_items", []),
                                   "name", "count", "Top 10 Items Purchased"),
        ),
        "spend_by_category": (
            "Spend by Category",
            lambda ax: _pie_chart(ax, data.get("spend_by_category", []),
                                  "category", "total", "Spend by Category"),
        ),
        "coins_by_day": (
            "Coins Spent per Day",
            lambda ax: _line_chart(ax, data.get("coins_by_day", []),
                                   "date", "total",
                                   "Coins Spent per Day", color=SERIES[3]),
        ),
    }
    if chart_key not in _DRAWS:
        return None
    title, draw = _DRAWS[chart_key]
    return _render_single(title, draw, data, chart_key, guild_name, time_label)


def generate_server_chart(chart_key: str, data: dict,
                           guild_name: str, time_label: str) -> "io.BytesIO | None":
    """
    Generate one server-activity chart by key.  Returns None when data is empty.

    Valid keys: sessions_by_server_day, total_by_server, new_players_by_day, activity_by_hour
    """
    _TITLES = {
        "sessions_by_server_day": "Sessions per Server Over Time",
        "total_by_server":        "Total Sessions per Server",
        "new_players_by_day":     "New Players per Day",
        "activity_by_hour":       "Activity by Hour of Day",
    }
    if chart_key not in _TITLES or not data.get(chart_key):
        return None
    title = _TITLES[chart_key]
    fig, ax = _create_figure_single(title, guild_name, time_label)
    if chart_key == "sessions_by_server_day":
        _draw_server_day_multiline(ax, data["sessions_by_server_day"])
    elif chart_key == "total_by_server":
        _bar_chart(ax, data.get("total_by_server", []), "server", "count", title)
    elif chart_key == "new_players_by_day":
        _line_chart(ax, data.get("new_players_by_day", []), "date", "count",
                    title, color=SERIES[3])
    elif chart_key == "activity_by_hour":
        _bar_chart(ax, data.get("activity_by_hour", []), "hour", "count",
                   title, color=SERIES[2])
    ax.set_title(title, fontsize=12, color=TEXT, pad=8)
    return _finalize(fig)
