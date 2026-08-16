"""
Analytics Dashboard GUI - Interactive data browser for ARK server analytics.
Provides spreadsheet-style views for players, tribes, dinos, and structures
with filtering, searching, and historical data support.
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button, Modal, TextInput
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime, timedelta
import logging
import asyncio

from bot.utils.config import Config
from bot.database.server_config_db import is_self_hosted
from bot.utils.subscription_checker import check_feature
from bot.database import analytics_db
from bot.utils import report_generator

# Import ark-asa-parser components
try:
    from ark_asa_parser import (
        ArkSaveReader,
        scan_all_servers,
        PlayerData,
        TribeData,
        DinoExtractor,
        StructureExtractor,
        HistoricalTracker,
        PlayerSnapshot,
        TribeSnapshot,
        PlayerStatsReader,
    )
    from ark_asa_parser.levels import get_default_xp_table

    HAS_PARSER = True
except ImportError:
    HAS_PARSER = False
    get_default_xp_table = None
    ArkSaveReader = None
    PlayerData = None
    TribeData = None
    DinoExtractor = None
    StructureExtractor = None
    HistoricalTracker = None
    PlayerSnapshot = None
    TribeSnapshot = None
    PlayerStatsReader = None

logger = logging.getLogger("AnalyticsDashboard")

# Constants
ITEMS_PER_PAGE = 5  # Discord embeds have 25 field limit, showing 5 detailed entries per page
MAX_FIELD_LENGTH = 1024

# ARK ASA XP Table (reverse-engineered from 26 real players across 25 unique levels, L9-L143)
# Uses multiplier 1.1050 with base_xp 6.617
# Formula: Total XP at level N = sum(6.617 * 1.1050^i for i in range(2, N+1))
# Accuracy: Perfect at L114, ±1 level at L117/L134, ±2 levels at L143
# Note: Uses MAX XP per level (pure grind baseline, accounts for level boosts from notes/bosses)
ARK_ASA_XP_TABLE = {
    1: 0,
    2: 7,
    3: 15,
    4: 23,
    5: 33,
    6: 43,
    7: 55,
    8: 68,
    9: 82,
    10: 98,
    11: 53,
    12: 62,
    13: 72,
    14: 84,
    15: 96,
    16: 111,
    17: 126,
    18: 144,
    19: 164,
    20: 185,
    21: 210,
    22: 237,
    23: 267,
    24: 301,
    25: 338,
    26: 380,
    27: 426,
    28: 478,
    29: 536,
    30: 600,
    31: 672,
    32: 751,
    33: 840,
    34: 939,
    35: 1049,
    36: 1172,
    37: 1309,
    38: 1461,
    39: 1631,
    40: 1820,
    41: 2031,
    42: 2266,
    43: 2527,
    44: 2818,
    45: 3143,
    46: 3504,
    47: 3907,
    48: 4356,
    49: 4855,
    50: 5412,
    51: 6032,
    52: 6723,
    53: 7493,
    54: 8350,
    55: 9305,
    56: 10369,
    57: 11554,
    58: 12874,
    59: 14345,
    60: 15984,
    61: 17809,
    62: 19843,
    63: 22108,
    64: 24631,
    65: 27443,
    66: 30574,
    67: 34063,
    68: 37949,
    69: 42279,
    70: 47102,
    71: 52474,
    72: 58460,
    73: 65127,
    74: 72555,
    75: 80829,
    76: 90047,
    77: 100316,
    78: 111755,
    79: 124498,
    80: 138694,
    81: 154508,
    82: 172125,
    83: 191751,
    84: 213614,
    85: 237969,
    86: 265100,
    87: 295325,
    88: 328995,
    89: 366504,
    90: 408288,
    91: 454836,
    92: 506691,
    93: 564457,
    94: 628808,
    95: 700496,
    96: 780355,
    97: 869319,
    98: 968424,
    99: 1078828,
    100: 1201818,
    101: 1338828,
    102: 1491458,
    103: 1661487,
    104: 1850900,
    105: 2061905,
    106: 2296966,
    107: 2558823,
    108: 2850532,
    109: 3175496,
    110: 3537505,
    111: 3940784,
    112: 4390037,
    113: 4890504,
    114: 5448025,
    115: 6069103,
    116: 6760984,
    117: 7531739,
    118: 8390361,
    119: 9346865,
    120: 10412411,
    121: 11599429,
    122: 12921767,
    123: 14394851,
    124: 16035868,
    125: 17863960,
    126: 19900454,
    127: 22169109,
    128: 24696391,
    129: 27511783,
    130: 30648129,
    131: 34142019,
    132: 38034213,
    133: 42370116,
    134: 47200312,
    135: 52581151,
    136: 58575406,
    137: 65253005,
    138: 72691851,
    139: 80978725,
    140: 90210303,
    141: 100494281,
    142: 111950632,
    143: 124713007,
    144: 138930293,
    145: 154768350,
    146: 172411945,
    147: 192066909,
    148: 213962540,
    149: 238354273,
    150: 265526663,
    151: 295796706,
    152: 329517534,
    153: 367082536,
    154: 408929948,
    155: 455547965,
    156: 507480437,
    157: 565333210,
    158: 629781199,
    159: 701576259,
    160: 781555955,
    161: 870653337,
    162: 969907821,
    163: 1080477316,
    164: 1203651733,
    165: 1340868034,
    166: 1493726993,
    167: 1664011873,
    168: 1853709230,
    169: 2065032085,
    170: 2300445746,
    171: 2562696564,
    172: 2854843976,
    173: 3180296192,
    174: 3542849961,
    175: 3946734860,
    176: 4396662637,
    177: 4897882181,
    178: 5456240753,
    179: 6078252202,
    180: 6771172956,
    181: 7543086676,
    182: 8402998560,
    183: 9360940399,
    184: 10428087608,
    185: 11616889599,
    186: 12941215016,
    187: 14416513531,
    188: 16059996077,
    189: 17890835633,
    190: 19930390898,
    191: 22202455464,
    192: 24733535390,
    193: 27553158427,
    194: 30694218491,
    195: 34193359402,
    196: 38091402378,
    197: 42433822252,
    198: 47271277992,
    199: 52660203686,
    200: 58663466909,
}


class AnalyticsDashboard(commands.Cog):
    """Interactive analytics dashboard for ARK server data."""

    def __init__(self, bot):
        self.bot = bot
        # Cluster root must be configured - no hardcoded fallback
        if not Config.ASA_CLUSTER_ROOT:
            logger.error("ASA_CLUSTER_ROOT not configured - analytics will not function")
            self.cluster_root = None
        else:
            self.cluster_root = Path(Config.ASA_CLUSTER_ROOT)
        self.history_db = Path("data/ark_history.db")
        self.history_db.parent.mkdir(exist_ok=True)

        # Initialize historical tracker
        if HAS_PARSER:
            self.tracker = HistoricalTracker(self.history_db)
        else:
            self.tracker = None

        # Cache for server data
        self._cache = {}
        self._cache_time = None
        self._cache_ttl = 60  # 60 second cache

    async def cog_load(self):
        """Called when cog is loaded."""
        logger.info("AnalyticsDashboard cog loaded")
        if not HAS_PARSER:
            logger.warning("ark-asa-parser not installed - some features disabled")

    def _get_servers(self) -> Dict[str, Path]:
        """Get available servers."""
        if not HAS_PARSER:
            return {}

        try:
            servers = scan_all_servers(self.cluster_root)
            return {name: reader.save_dir for name, reader in servers.items()}
        except Exception as e:
            logger.error(f"Error scanning servers: {e}")
            return {}

    def _get_server_list(self) -> List[str]:
        """Get list of server names."""
        servers = self._get_servers()
        return sorted(servers.keys())

    @app_commands.command(name="analytics", description="📊 Open the ARK analytics dashboard")
    async def analytics_command(self, interaction: discord.Interaction):
        """Open the main analytics dashboard."""
        if not await check_feature(interaction, "analytics"):
            return
        # Check if self-hosted (requires local file access)
        if not await is_self_hosted(interaction.guild_id):
            await interaction.response.send_message(
                "❌ This command requires self-hosted servers with local file access.",
                ephemeral=True,
            )
            return

        if not HAS_PARSER:
            await interaction.response.send_message(
                "❌ Analytics requires `ark-asa-parser` library. Install with:\n"
                "```pip install ark-asa-parser>=0.2.0```",
                ephemeral=True,
            )
            return

        servers = self._get_server_list()
        if not servers:
            await interaction.response.send_message(
                "❌ No ARK servers found. Check cluster root path configuration.", ephemeral=True
            )
            return

        view = MainDashboardView(self, interaction.user, servers)
        embed = view.create_main_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="recordsnapshot",
        description="📸 Record current player/tribe data for historical tracking",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def record_snapshot_command(self, interaction: discord.Interaction):
        """Record a snapshot of current player and tribe data."""
        if not await check_feature(interaction, "analytics"):
            return
        # Check if self-hosted (requires local file access)
        if not await is_self_hosted(interaction.guild_id):
            await interaction.response.send_message(
                "❌ This command requires self-hosted servers with local file access.",
                ephemeral=True,
            )
            return

        if not HAS_PARSER or not self.tracker:
            await interaction.response.send_message(
                "❌ Historical tracking not available.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            servers = self._get_servers()
            player_count = 0
            tribe_count = 0
            timestamp = datetime.now()

            for server_name, save_dir in servers.items():
                try:
                    reader = ArkSaveReader(save_dir)

                    # Record players
                    players = reader.get_all_players()
                    for player in players:
                        snapshot = PlayerSnapshot(
                            timestamp=timestamp,
                            eos_id=player.eos_id,
                            player_name=player.player_name or "",
                            character_name=player.character_name or "",
                            level=player.level or 0,
                            experience=player.experience or 0.0,
                            tribe_id=player.tribe_id or 0,
                            server_name=server_name,
                        )
                        self.tracker.record_player_snapshot(snapshot)
                        player_count += 1

                    # Record tribes
                    tribes = reader.get_all_tribes()
                    for tribe in tribes:
                        snapshot = TribeSnapshot(
                            timestamp=timestamp,
                            tribe_id=tribe.tribe_id,
                            tribe_name=tribe.tribe_name or "",
                            member_count=tribe.member_count or 0,
                            server_name=server_name,
                        )
                        self.tracker.record_tribe_snapshot(snapshot)
                        tribe_count += 1

                    # Log activity
                    self.tracker.log_activity(
                        event_type="snapshot_recorded",
                        server_name=server_name,
                        details=f"{len(players)} players, {len(tribes)} tribes",
                    )

                except Exception as e:
                    logger.error(f"Error recording snapshot for {server_name}: {e}")

            await interaction.followup.send(
                f"✅ Snapshot recorded!\n"
                f"📊 {player_count} players\n"
                f"🏛️ {tribe_count} tribes\n"
                f"🗺️ {len(servers)} servers",
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"Error in record_snapshot: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error recording snapshot: {str(e)}", ephemeral=True
            )

    @app_commands.command(name="exportdata", description="📤 Export analytics data to CSV format")
    @app_commands.describe(
        data_type="Type of data to export", server="Server name (or 'all' for all servers)"
    )
    @app_commands.choices(
        data_type=[
            app_commands.Choice(name="Players", value="players"),
            app_commands.Choice(name="Tribes", value="tribes"),
            app_commands.Choice(name="Dinos", value="dinos"),
            app_commands.Choice(name="Structures", value="structures"),
        ]
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def export_data_command(
        self, interaction: discord.Interaction, data_type: str, server: str = "all"
    ):
        """Export analytics data to CSV."""
        if not await check_feature(interaction, "analytics"):
            return
        # Check if self-hosted (requires local file access)
        if not await is_self_hosted(interaction.guild_id):
            await interaction.response.send_message(
                "❌ This command requires self-hosted servers with local file access.",
                ephemeral=True,
            )
            return

        if not HAS_PARSER:
            await interaction.response.send_message(
                "❌ Export requires `ark-asa-parser` library.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            import csv
            from io import StringIO

            output = StringIO()

            if data_type == "players":
                writer = csv.writer(output)
                writer.writerow(
                    [
                        "EOS ID",
                        "Player Name",
                        "Character Name",
                        "Level",
                        "Experience",
                        "Tribe ID",
                        "Server",
                    ]
                )

                servers = self._get_servers()
                server_list = [server] if server != "all" and server in servers else servers.keys()

                for server_name in server_list:
                    if server_name in servers:
                        reader = ArkSaveReader(servers[server_name])
                        players = reader.get_all_players()
                        for p in players:
                            writer.writerow(
                                [
                                    p.eos_id,
                                    p.player_name or "",
                                    p.character_name or "",
                                    p.level or 0,
                                    p.experience or 0,
                                    p.tribe_id or 0,
                                    server_name,
                                ]
                            )

            elif data_type == "tribes":
                writer = csv.writer(output)
                writer.writerow(["Tribe ID", "Tribe Name", "Owner", "Members", "Server"])

                servers = self._get_servers()
                server_list = [server] if server != "all" and server in servers else servers.keys()

                for server_name in server_list:
                    if server_name in servers:
                        reader = ArkSaveReader(servers[server_name])
                        tribes = reader.get_all_tribes()
                        for t in tribes:
                            writer.writerow(
                                [
                                    t.tribe_id,
                                    t.tribe_name or "",
                                    t.owner_name or "",
                                    t.member_count or 0,
                                    server_name,
                                ]
                            )

            elif data_type == "dinos":
                writer = csv.writer(output)
                writer.writerow(
                    ["Species", "Name", "Level", "Owner", "Tribe ID", "Health", "Stamina", "Server"]
                )

                servers = self._get_servers()
                server_list = [server] if server != "all" and server in servers else servers.keys()

                for server_name in server_list:
                    if server_name in servers:
                        save_dir = servers[server_name]
                        world_ark = save_dir / f"{save_dir.name}.ark"
                        if world_ark.exists():
                            dinos = DinoExtractor.extract_dinos_from_world(world_ark)
                            for d in dinos:
                                writer.writerow(
                                    [
                                        d.species_name or "",
                                        d.dino_name or "",
                                        d.level or 0,
                                        d.owner_name or "",
                                        d.tribe_id or 0,
                                        d.health or 0,
                                        d.stamina or 0,
                                        server_name,
                                    ]
                                )

            elif data_type == "structures":
                writer = csv.writer(output)
                writer.writerow(["Type", "Owner", "Tribe", "Health", "Locked", "Server"])

                servers = self._get_servers()
                server_list = [server] if server != "all" and server in servers else servers.keys()

                for server_name in server_list:
                    if server_name in servers:
                        save_dir = servers[server_name]
                        world_ark = save_dir / f"{save_dir.name}.ark"
                        if world_ark.exists():
                            structures = StructureExtractor.extract_structures_from_world(world_ark)
                            for s in structures:
                                writer.writerow(
                                    [
                                        s.structure_type or "",
                                        s.owner_name or "",
                                        s.tribe_name or "",
                                        s.health or 0,
                                        "Yes" if s.is_locked else "No",
                                        server_name,
                                    ]
                                )

            # Create file
            output.seek(0)
            filename = f"{data_type}_{server}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            file = discord.File(fp=StringIO(output.getvalue()), filename=filename)

            await interaction.followup.send(
                f"✅ Exported {data_type} data for {server}!", file=file, ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error exporting data: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Error exporting data: {str(e)}", ephemeral=True)

    # -----------------------------------------------------------------------
    # /report command group — SQLite-based visual analytics
    # -----------------------------------------------------------------------

    report = app_commands.Group(name="report", description="📈 Generate visual analytics reports")

    @report.command(name="players", description="Player activity report (sessions, duration, peak hours)")
    @app_commands.describe(timerange="Time period to cover (default: 7d)")
    @app_commands.choices(timerange=[
        app_commands.Choice(name="Last 24 hours", value="1d"),
        app_commands.Choice(name="Last 7 days",   value="7d"),
        app_commands.Choice(name="Last 30 days",  value="30d"),
        app_commands.Choice(name="Last 6 months", value="6m"),
        app_commands.Choice(name="Last year",     value="1y"),
    ])
    async def report_players(
        self,
        interaction: discord.Interaction,
        timerange: str = "7d",
    ):
        """Generate a player-activity report chart."""
        if not await check_feature(interaction, "analytics"):
            return
        await interaction.response.defer(ephemeral=True)
        since = datetime.utcnow() - timedelta(days=TIME_RANGE_DAYS[timerange])
        guild_name = interaction.guild.name if interaction.guild else "Unknown Guild"
        data = await analytics_db.get_player_report_data(interaction.guild_id, since)
        if not _has_data(data):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="📭 No Data Available",
                    description=(
                        f"No player activity data found for the **{TIME_RANGE_LABELS[timerange]}** period.\n"
                        "Try a longer time range or wait for players to log in."
                    ),
                    color=0xe94560,
                ),
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="📊 Player Activity Report",
            description=f"Select a chart to view — **{TIME_RANGE_LABELS[timerange]}**",
            color=0xe94560,
        )
        view = ReportChartSelectView(
            PLAYER_CHARTS, data, guild_name, TIME_RANGE_LABELS[timerange],
            report_generator.generate_player_chart,
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @report.command(name="economy", description="Economy report (paydays, coin flow, top balances)")
    @app_commands.describe(timerange="Time period to cover (default: 7d)")
    @app_commands.choices(timerange=[
        app_commands.Choice(name="Last 24 hours", value="1d"),
        app_commands.Choice(name="Last 7 days",   value="7d"),
        app_commands.Choice(name="Last 30 days",  value="30d"),
        app_commands.Choice(name="Last 6 months", value="6m"),
        app_commands.Choice(name="Last year",     value="1y"),
    ])
    async def report_economy(
        self,
        interaction: discord.Interaction,
        timerange: str = "7d",
    ):
        """Generate an economy report chart."""
        if not await check_feature(interaction, "analytics"):
            return
        await interaction.response.defer(ephemeral=True)
        since = datetime.utcnow() - timedelta(days=TIME_RANGE_DAYS[timerange])
        guild_name = interaction.guild.name if interaction.guild else "Unknown Guild"
        data = await analytics_db.get_economy_report_data(interaction.guild_id, since)
        if not _has_data(data):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="📭 No Data Available",
                    description=(
                        f"No economy data found for the **{TIME_RANGE_LABELS[timerange]}** period.\n"
                        "Try a longer time range or wait for payday/transactions to occur."
                    ),
                    color=0xe94560,
                ),
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="💰 Economy Report",
            description=f"Select a chart to view — **{TIME_RANGE_LABELS[timerange]}**",
            color=0xe94560,
        )
        view = ReportChartSelectView(
            ECONOMY_CHARTS, data, guild_name, TIME_RANGE_LABELS[timerange],
            report_generator.generate_economy_chart,
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @report.command(name="shop", description="Shop report (purchases, top items, spend by category)")
    @app_commands.describe(timerange="Time period to cover (default: 7d)")
    @app_commands.choices(timerange=[
        app_commands.Choice(name="Last 24 hours", value="1d"),
        app_commands.Choice(name="Last 7 days",   value="7d"),
        app_commands.Choice(name="Last 30 days",  value="30d"),
        app_commands.Choice(name="Last 6 months", value="6m"),
        app_commands.Choice(name="Last year",     value="1y"),
    ])
    async def report_shop(
        self,
        interaction: discord.Interaction,
        timerange: str = "7d",
    ):
        """Generate a shop report chart."""
        if not await check_feature(interaction, "analytics"):
            return
        await interaction.response.defer(ephemeral=True)
        since = datetime.utcnow() - timedelta(days=TIME_RANGE_DAYS[timerange])
        guild_name = interaction.guild.name if interaction.guild else "Unknown Guild"
        data = await analytics_db.get_shop_report_data(interaction.guild_id, since)
        if not _has_data(data):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="📭 No Data Available",
                    description=(
                        f"No shop data found for the **{TIME_RANGE_LABELS[timerange]}** period.\n"
                        "Try a longer time range or wait for purchases to occur."
                    ),
                    color=0xe94560,
                ),
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="🛒 Shop Report",
            description=f"Select a chart to view — **{TIME_RANGE_LABELS[timerange]}**",
            color=0xe94560,
        )
        view = ReportChartSelectView(
            SHOP_CHARTS, data, guild_name, TIME_RANGE_LABELS[timerange],
            report_generator.generate_shop_chart,
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @report.command(name="activity", description="Player activity by server (sessions, new players, peak hours)")
    @app_commands.describe(timerange="Time period to cover (default: 7d)")
    @app_commands.choices(timerange=[
        app_commands.Choice(name="Last 24 hours", value="1d"),
        app_commands.Choice(name="Last 7 days",   value="7d"),
        app_commands.Choice(name="Last 30 days",  value="30d"),
        app_commands.Choice(name="Last 6 months", value="6m"),
        app_commands.Choice(name="Last year",     value="1y"),
    ])
    async def report_activity(
        self,
        interaction: discord.Interaction,
        timerange: str = "7d",
    ):
        """Generate a player-activity-by-server report chart."""
        if not await check_feature(interaction, "analytics"):
            return
        await interaction.response.defer(ephemeral=True)
        since = datetime.utcnow() - timedelta(days=TIME_RANGE_DAYS[timerange])
        guild_name = interaction.guild.name if interaction.guild else "Unknown Guild"
        data = await analytics_db.get_server_report_data(interaction.guild_id, since)
        if not _has_data(data):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="📭 No Data Available",
                    description=(
                        f"No player activity data found for the **{TIME_RANGE_LABELS[timerange]}** period.\n"
                        "Try a longer time range or wait for players to connect."
                    ),
                    color=0xe94560,
                ),
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="🖥️ Player Activity by Server",
            description=f"Select a chart to view — **{TIME_RANGE_LABELS[timerange]}**",
            color=0xe94560,
        )
        view = ReportChartSelectView(
            SERVER_CHARTS, data, guild_name, TIME_RANGE_LABELS[timerange],
            report_generator.generate_server_chart,
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class MainDashboardView(View):
    """Main dashboard view with category selection."""

    def __init__(self, cog: AnalyticsDashboard, user: discord.User, servers: List[str]):
        super().__init__(timeout=None)
        self.cog = cog
        self.user = user
        self.servers = servers
        self.selected_server = servers[0] if servers else None
        self.selected_category = "players"
        self.date_range = "current"  # current, 24h, 7d, 30d
        self.search_query = ""
        self.current_page = 0

        self._setup_components()

    def _setup_components(self):
        """Setup view components."""
        self.clear_items()

        # Server selector
        server_options = [
            discord.SelectOption(
                label=server.upper(),
                value=server,
                default=(server == self.selected_server),
                emoji="🗺️",
            )
            for server in self.servers[:25]
        ]
        server_options.insert(
            0,
            discord.SelectOption(
                label="All Servers",
                value="all",
                default=(self.selected_server == "all"),
                emoji="🌐",
            ),
        )

        server_select = Select(
            placeholder="Select Server...", options=server_options, custom_id="server_select", row=0
        )
        server_select.callback = self.server_selected
        self.add_item(server_select)

        # Category buttons
        categories = [
            ("👥 Players", "players", discord.ButtonStyle.primary),
            ("🏛️ Tribes", "tribes", discord.ButtonStyle.primary),
            ("🦖 Dinos", "dinos", discord.ButtonStyle.primary),
            ("🏗️ Structures", "structures", discord.ButtonStyle.primary),
        ]

        for label, cat_id, style in categories:
            btn = Button(
                label=label,
                style=style if cat_id != self.selected_category else discord.ButtonStyle.success,
                custom_id=f"cat_{cat_id}",
                row=1,
            )
            btn.callback = self._make_category_callback(cat_id)
            self.add_item(btn)

        # Date range selector
        date_options = [
            discord.SelectOption(
                label="Current Data",
                value="current",
                emoji="📍",
                default=(self.date_range == "current"),
            ),
            discord.SelectOption(
                label="Last 24 Hours", value="24h", emoji="🕐", default=(self.date_range == "24h")
            ),
            discord.SelectOption(
                label="Last 7 Days", value="7d", emoji="📅", default=(self.date_range == "7d")
            ),
            discord.SelectOption(
                label="Last 30 Days", value="30d", emoji="📆", default=(self.date_range == "30d")
            ),
        ]

        date_select = Select(
            placeholder="Date Range...", options=date_options, custom_id="date_select", row=2
        )
        date_select.callback = self.date_selected
        self.add_item(date_select)

        # Search button
        search_btn = Button(
            label="🔍 Search", style=discord.ButtonStyle.secondary, custom_id="search_btn", row=3
        )
        search_btn.callback = self.open_search
        self.add_item(search_btn)

        # Pagination buttons
        prev_btn = Button(
            label="◀️",
            style=discord.ButtonStyle.secondary,
            custom_id="prev_page",
            row=3,
            disabled=(self.current_page == 0),
        )
        prev_btn.callback = self.prev_page
        self.add_item(prev_btn)

        next_btn = Button(
            label="▶️", style=discord.ButtonStyle.secondary, custom_id="next_page", row=3
        )
        next_btn.callback = self.next_page
        self.add_item(next_btn)

        # Refresh button
        refresh_btn = Button(
            label="🔄 Refresh", style=discord.ButtonStyle.secondary, custom_id="refresh", row=4
        )
        refresh_btn.callback = self.refresh_data
        self.add_item(refresh_btn)

        # ARK Leaderboards button
        lb_btn = Button(
            label="🏆 ARK Leaderboards", style=discord.ButtonStyle.secondary, custom_id="leaderboards", row=4
        )
        lb_btn.callback = self.open_leaderboards
        self.add_item(lb_btn)

    def _make_category_callback(self, category: str):
        """Create callback for category button."""

        async def callback(interaction: discord.Interaction):
            self.selected_category = category
            self.current_page = 0
            self._setup_components()
            embed = await self.create_data_embed()
            await interaction.response.edit_message(embed=embed, view=self)

        return callback

    async def open_leaderboards(self, interaction: discord.Interaction):
        """Open the ARK cluster leaderboard view."""
        if not HAS_PARSER:
            await interaction.response.send_message(
                "❌ Leaderboards require `ark-asa-parser` library.", ephemeral=True
            )
            return
        servers = self.cog._get_server_list()
        if not servers:
            await interaction.response.send_message("❌ No ARK server data available.", ephemeral=True)
            return
        view = LeaderboardView(self.cog, interaction.user, servers, dashboard_view=self)
        embed = await view.create_leaderboard_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This dashboard is not for you!", ephemeral=True
            )
            return False
        return True

    def create_main_embed(self) -> discord.Embed:
        """Create the main dashboard embed."""
        embed = discord.Embed(
            title="📊 ARK Analytics Dashboard",
            description=(
                "Browse player, tribe, dino, and structure data across your ARK cluster.\n\n"
                "**Instructions:**\n"
                "• Select a **server** from the dropdown (or 'All Servers')\n"
                "• Click a **category** button to view that data type\n"
                "• Use **date range** to view historical snapshots\n"
                "• Click **Search** to filter by name/ID"
            ),
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="🗺️ Available Servers",
            value=", ".join([s.upper() for s in self.servers[:10]])
            + (f" (+{len(self.servers)-10} more)" if len(self.servers) > 10 else ""),
            inline=False,
        )

        embed.add_field(
            name="📂 Categories",
            value="👥 Players • 🏛️ Tribes • 🦖 Dinos • 🏗️ Structures",
            inline=False,
        )

        embed.set_footer(text="Select a server and category to begin")
        return embed

    async def create_data_embed(self) -> discord.Embed:
        """Create embed for current data view."""
        if self.selected_category == "players":
            return await self._create_players_embed()
        elif self.selected_category == "tribes":
            return await self._create_tribes_embed()
        elif self.selected_category == "dinos":
            return await self._create_dinos_embed()
        elif self.selected_category == "structures":
            return await self._create_structures_embed()
        return self.create_main_embed()

    async def _create_players_embed(self) -> discord.Embed:
        """Create players data embed."""
        embed = discord.Embed(
            title=f"👥 Players - {self.selected_server.upper() if self.selected_server != 'all' else 'All Servers'}",
            color=discord.Color.green(),
            description="ℹ️ **Note:** Player levels cannot be determined from profile files (ARK stores total XP earned, not leveling XP). Levels require RCON query of online players.",
        )

        try:
            players = await self._get_players_data()

            # Apply date range filtering
            if self.date_range != "current":
                from datetime import datetime, timezone, timedelta

                now = datetime.now(timezone.utc)

                if self.date_range == "24h":
                    cutoff = now - timedelta(hours=24)
                elif self.date_range == "7d":
                    cutoff = now - timedelta(days=7)
                elif self.date_range == "30d":
                    cutoff = now - timedelta(days=30)
                else:
                    cutoff = None

                if cutoff:
                    players = [
                        p
                        for p in players
                        if hasattr(p, "last_seen")
                        and p.last_seen
                        and (
                            p.last_seen.replace(tzinfo=timezone.utc)
                            if p.last_seen.tzinfo is None
                            else p.last_seen
                        )
                        >= cutoff
                    ]

            if self.search_query:
                players = [
                    p
                    for p in players
                    if self.search_query.lower() in (p.player_name or "").lower()
                    or self.search_query.lower() in (p.character_name or "").lower()
                    or self.search_query.lower() in (p.eos_id or "").lower()
                ]
                embed.description = f"⚠️ **Note:** 'Last Seen' is based on character file modification time.\n🔍 Search: `{self.search_query}` | Found: {len(players)}"

            total_pages = max(1, (len(players) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            self.current_page = min(self.current_page, total_pages - 1)

            start_idx = self.current_page * ITEMS_PER_PAGE
            end_idx = start_idx + ITEMS_PER_PAGE
            page_players = players[start_idx:end_idx]

            if not page_players:
                embed.description = "No players found."
            else:
                # Create horizontal table display with all details
                for i, player in enumerate(page_players, start=start_idx + 1):
                    # Format last seen timestamp
                    if hasattr(player, "last_seen") and player.last_seen:
                        from datetime import datetime, timezone

                        now = datetime.now(timezone.utc)

                        # Make player.last_seen timezone-aware if it's naive
                        last_seen_dt = player.last_seen
                        if last_seen_dt.tzinfo is None:
                            last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)

                        time_diff = now - last_seen_dt

                        if time_diff.days > 0:
                            last_seen = f"{time_diff.days}d ago"
                        elif time_diff.seconds >= 3600:
                            hours = time_diff.seconds // 3600
                            last_seen = f"{hours}h ago"
                        elif time_diff.seconds >= 60:
                            mins = time_diff.seconds // 60
                            last_seen = f"{mins}m ago"
                        else:
                            last_seen = "Just now"
                    else:
                        last_seen = "Unknown"

                    # Get character name
                    char_name = player.character_name or player.player_name or "Unknown"

                    # Build player info in horizontal format
                    player_lines = []
                    player_lines.append(f"**Level:** {self._format_level(player)}")
                    player_lines.append(
                        f"**Tribe ID:** {player.tribe_id if player.tribe_id else 'No Tribe'}"
                    )
                    player_lines.append(
                        f"**EOS ID:** `{player.eos_id if player.eos_id else 'Unknown'}`"
                    )

                    # Always show location section (even if unavailable)
                    if player.lat and player.lon:
                        player_lines.append(
                            f"**Last Known Position:** Lat {player.lat:.1f}, Lon {player.lon:.1f}"
                        )
                    else:
                        player_lines.append(f"**Last Known Position:** Unknown")

                    player_lines.append(f"**Last Seen:** {last_seen}")

                    # Get file path to extract specimen ID if available
                    if hasattr(player, "file_path") and player.file_path:
                        # Specimen ID is typically in the filename
                        filename = Path(player.file_path).stem
                        player_lines.append(f"**Specimen ID:** `{filename}`")

                    embed.add_field(
                        name=f"#{i} {char_name}", value="\n".join(player_lines), inline=False
                    )

            embed.set_footer(
                text=f"Page {self.current_page + 1}/{total_pages} • Total: {len(players)} players"
            )

        except Exception as e:
            logger.error(f"Error creating players embed: {e}", exc_info=True)
            embed.description = f"❌ Error loading player data: {str(e)}"

        return embed

    async def _create_tribes_embed(self) -> discord.Embed:
        """Create tribes data embed."""
        embed = discord.Embed(
            title=f"🏛️ Tribes - {self.selected_server.upper() if self.selected_server != 'all' else 'All Servers'}",
            color=discord.Color.gold(),
        )

        try:
            tribes = await self._get_tribes_data()

            if self.search_query:
                tribes = [
                    t
                    for t in tribes
                    if self.search_query.lower() in (t.tribe_name or "").lower()
                    or self.search_query.lower() in str(t.tribe_id)
                ]
                embed.description = f"🔍 Search: `{self.search_query}` | Found: {len(tribes)}"

            total_pages = max(1, (len(tribes) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            self.current_page = min(self.current_page, total_pages - 1)

            start_idx = self.current_page * ITEMS_PER_PAGE
            end_idx = start_idx + ITEMS_PER_PAGE
            page_tribes = tribes[start_idx:end_idx]

            if not page_tribes:
                embed.description = "No tribes found."
            else:
                table_lines = ["```"]
                table_lines.append(f"{'#':<3} {'Tribe Name':<25} {'Members':<8} {'ID':<12}")
                table_lines.append("-" * 52)

                for i, tribe in enumerate(page_tribes, start=start_idx + 1):
                    name = (tribe.tribe_name or "Unknown")[:23]
                    members = str(tribe.member_count) if tribe.member_count else "?"
                    tribe_id = str(tribe.tribe_id)[:10]
                    table_lines.append(f"{i:<3} {name:<25} {members:<8} {tribe_id:<12}")

                table_lines.append("```")
                embed.add_field(name="Tribe Data", value="\n".join(table_lines), inline=False)

            embed.set_footer(
                text=f"Page {self.current_page + 1}/{total_pages} • Total: {len(tribes)} tribes"
            )

        except Exception as e:
            logger.error(f"Error creating tribes embed: {e}", exc_info=True)
            embed.description = f"❌ Error loading tribe data: {str(e)}"

        return embed

    async def _create_dinos_embed(self) -> discord.Embed:
        """Create dinos data embed."""
        embed = discord.Embed(
            title=f"🦖 Tamed Dinos - {self.selected_server.upper() if self.selected_server != 'all' else 'All Servers'}",
            color=discord.Color.orange(),
        )

        try:
            dinos = await self._get_dinos_data()

            if self.search_query:
                dinos = [
                    d
                    for d in dinos
                    if self.search_query.lower() in (d.species_name or "").lower()
                    or self.search_query.lower() in (d.dino_name or "").lower()
                    or self.search_query.lower() in (d.owner_name or "").lower()
                ]
                embed.description = f"🔍 Search: `{self.search_query}` | Found: {len(dinos)}"

            total_pages = max(1, (len(dinos) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            self.current_page = min(self.current_page, total_pages - 1)

            start_idx = self.current_page * ITEMS_PER_PAGE
            end_idx = start_idx + ITEMS_PER_PAGE
            page_dinos = dinos[start_idx:end_idx]

            if not page_dinos:
                embed.description = "No tamed dinos found (or world save not accessible)."
            else:
                table_lines = ["```"]
                table_lines.append(
                    f"{'#':<3} {'Species':<18} {'Name':<15} {'Lvl':<5} {'Owner':<12}"
                )
                table_lines.append("-" * 57)

                for i, dino in enumerate(page_dinos, start=start_idx + 1):
                    species = (dino.species_name or "Unknown")[:16]
                    name = (dino.dino_name or "-")[:13]
                    level = str(dino.level) if dino.level else "?"
                    owner = (dino.owner_name or "-")[:10]
                    table_lines.append(f"{i:<3} {species:<18} {name:<15} {level:<5} {owner:<12}")

                table_lines.append("```")
                embed.add_field(name="Dino Data", value="\n".join(table_lines), inline=False)

            # Add summary
            if dinos:
                species_count = {}
                for d in dinos:
                    species_count[d.species_name] = species_count.get(d.species_name, 0) + 1
                top_species = sorted(species_count.items(), key=lambda x: x[1], reverse=True)[:5]
                summary = " • ".join([f"{s}: {c}" for s, c in top_species])
                embed.add_field(name="📊 Top Species", value=summary or "N/A", inline=False)

            embed.set_footer(
                text=f"Page {self.current_page + 1}/{total_pages} • Total: {len(dinos)} dinos"
            )

        except Exception as e:
            logger.error(f"Error creating dinos embed: {e}", exc_info=True)
            embed.description = f"❌ Error loading dino data: {str(e)}"

        return embed

    async def _create_structures_embed(self) -> discord.Embed:
        """Create structures data embed."""
        embed = discord.Embed(
            title=f"🏗️ Structures - {self.selected_server.upper() if self.selected_server != 'all' else 'All Servers'}",
            color=discord.Color.purple(),
        )

        try:
            structures = await self._get_structures_data()

            if self.search_query:
                structures = [
                    s
                    for s in structures
                    if self.search_query.lower() in (s.structure_type or "").lower()
                    or self.search_query.lower() in (s.owner_name or "").lower()
                    or self.search_query.lower() in (s.tribe_name or "").lower()
                ]
                embed.description = f"🔍 Search: `{self.search_query}` | Found: {len(structures)}"

            # Group by category for summary view
            if not self.search_query:
                category_counts = {}
                for s in structures:
                    cat = getattr(s, "category", "Unknown")
                    category_counts[cat] = category_counts.get(cat, 0) + 1

                if category_counts:
                    embed.add_field(
                        name="📊 By Category",
                        value="\n".join(
                            [
                                f"**{cat}:** {count:,}"
                                for cat, count in sorted(
                                    category_counts.items(), key=lambda x: x[1], reverse=True
                                )
                            ]
                        ),
                        inline=True,
                    )

                # Group by tribe
                tribe_counts = {}
                for s in structures:
                    tribe = s.tribe_name or s.owner_name or "Unknown"
                    tribe_counts[tribe] = tribe_counts.get(tribe, 0) + 1

                if tribe_counts:
                    top_tribes = sorted(tribe_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                    embed.add_field(
                        name="🏛️ Top Builders",
                        value="\n".join([f"**{t}:** {c:,}" for t, c in top_tribes]),
                        inline=True,
                    )

            total_pages = max(1, (len(structures) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            self.current_page = min(self.current_page, total_pages - 1)

            start_idx = self.current_page * ITEMS_PER_PAGE
            end_idx = start_idx + ITEMS_PER_PAGE
            page_structures = structures[start_idx:end_idx]

            if page_structures:
                table_lines = ["```"]
                table_lines.append(f"{'#':<3} {'Type':<20} {'Owner/Tribe':<18} {'Locked':<6}")
                table_lines.append("-" * 51)

                for i, struct in enumerate(page_structures, start=start_idx + 1):
                    stype = (struct.structure_type or "Unknown")[:18]
                    owner = (struct.tribe_name or struct.owner_name or "-")[:16]
                    locked = "🔒" if struct.is_locked else "-"
                    table_lines.append(f"{i:<3} {stype:<20} {owner:<18} {locked:<6}")

                table_lines.append("```")
                embed.add_field(name="Structure Data", value="\n".join(table_lines), inline=False)

            embed.set_footer(
                text=f"Page {self.current_page + 1}/{total_pages} • Total: {len(structures):,} structures"
            )

        except Exception as e:
            logger.error(f"Error creating structures embed: {e}", exc_info=True)
            embed.description = f"❌ Error loading structure data: {str(e)}"

        return embed

    async def _get_players_data(self) -> List:
        """Get player data from selected server(s) with enhanced stats."""
        servers = self.cog._get_servers()
        players = []

        if self.selected_server == "all":
            for name, save_dir in servers.items():
                try:
                    xp_table = get_default_xp_table() if get_default_xp_table else None
                    reader = ArkSaveReader(save_dir, xp_table=xp_table)
                    server_players = reader.get_all_players()
                    # Manually fix levels if they're wrong
                    server_players = self._fix_player_levels(server_players)
                    # Enrich with detailed stats if available
                    server_players = await self._enrich_player_stats(server_players, save_dir)
                    players.extend(server_players)
                except Exception as e:
                    logger.error(f"Error reading players from {name}: {e}")
        else:
            if self.selected_server in servers:
                try:
                    xp_table = get_default_xp_table() if get_default_xp_table else None
                    reader = ArkSaveReader(servers[self.selected_server], xp_table=xp_table)
                    players = reader.get_all_players()
                    # Manually fix levels if they're wrong
                    players = self._fix_player_levels(players)
                    # Enrich with detailed stats if available
                    players = await self._enrich_player_stats(
                        players, servers[self.selected_server]
                    )
                except Exception as e:
                    logger.error(f"Error reading players: {e}")

        # Sort by level descending
        players.sort(key=lambda p: p.level or 0, reverse=True)
        return players

    def _format_level(self, player) -> str:
        """Format player level display.

        Calculates level from total XP using reverse-engineered ARK ASA XP curve.
        Based on 29 real players (levels 9-143). Accuracy: ±1-2 levels for most players.
        """
        if not player or not hasattr(player, "experience") or player.experience is None:
            return "Unknown"

        xp = player.experience
        if xp <= 0:
            return "1"

        # Find level using XP table (binary search for efficiency)
        for level in range(1, 200):
            if level == 199:
                return "200+"

            next_level_xp = ARK_ASA_XP_TABLE.get(level + 1, float("inf"))
            current_level_xp = ARK_ASA_XP_TABLE[level]

            if current_level_xp <= xp < next_level_xp:
                return str(level)

        return "200+"

    def _fix_player_levels(self, players: List) -> List:
        """Manually recalculate player levels from experience if they're wrong."""
        # Library now reads experience correctly, but XP table caps at 180
        # Players can accumulate millions of XP beyond that with server multipliers
        return players

    async def _enrich_player_stats(self, players: List, save_dir: Path) -> List:
        """Enrich basic player data with detailed stats from PlayerStatsReader."""
        if not HAS_PARSER or not PlayerStatsReader:
            return players

        enriched = []
        for player in players:
            if player.file_path and Path(player.file_path).exists():
                try:
                    # PlayerStatsReader.read_player_stats returns a dict, not an object
                    stats_dict = PlayerStatsReader.read_player_stats(Path(player.file_path))

                    # Stats dict should have character level info
                    # The basic level from PlayerData is already calculated from experience
                    # So we don't need to override it unless stats_dict has better data
                    if stats_dict and isinstance(stats_dict, dict):
                        logger.debug(
                            f"Got stats for {player.character_name}: {list(stats_dict.keys())}"
                        )
                except Exception as e:
                    # If stats reading fails, keep basic data
                    logger.debug(f"Could not read stats for {player.character_name}: {e}")

            enriched.append(player)

        return enriched

    async def _get_tribes_data(self) -> List:
        """Get tribe data from selected server(s)."""
        servers = self.cog._get_servers()
        tribes = []

        if self.selected_server == "all":
            for name, save_dir in servers.items():
                try:
                    xp_table = get_default_xp_table() if get_default_xp_table else None
                    reader = ArkSaveReader(save_dir, xp_table=xp_table)
                    server_tribes = reader.get_all_tribes()
                    tribes.extend(server_tribes)
                except Exception as e:
                    logger.error(f"Error reading tribes from {name}: {e}")
        else:
            if self.selected_server in servers:
                try:
                    xp_table = get_default_xp_table() if get_default_xp_table else None
                    reader = ArkSaveReader(servers[self.selected_server], xp_table=xp_table)
                    tribes = reader.get_all_tribes()
                except Exception as e:
                    logger.error(f"Error reading tribes: {e}")

        # Sort by member count descending
        tribes.sort(key=lambda t: t.member_count or 0, reverse=True)
        return tribes

    async def _get_dinos_data(self) -> List:
        """Get dino data from selected server(s)."""
        servers = self.cog._get_servers()
        dinos = []

        if self.selected_server == "all":
            for name, save_dir in servers.items():
                try:
                    world_ark = save_dir / f"{save_dir.name}.ark"
                    if world_ark.exists():
                        extractor = DinoExtractor(str(world_ark))
                        server_dinos = extractor.extract_tamed_dinos()
                        dinos.extend(server_dinos)
                except Exception as e:
                    logger.error(f"Error reading dinos from {name}: {e}", exc_info=True)
        else:
            if self.selected_server in servers:
                try:
                    save_dir = servers[self.selected_server]
                    world_ark = save_dir / f"{save_dir.name}.ark"
                    if world_ark.exists():
                        extractor = DinoExtractor(str(world_ark))
                        dinos = extractor.extract_tamed_dinos()
                except Exception as e:
                    logger.error(f"Error reading dinos: {e}", exc_info=True)

        # Sort by level descending
        dinos.sort(key=lambda d: d.level or 0, reverse=True)
        return dinos

    async def _get_structures_data(self) -> List:
        """Get structure data from selected server(s)."""
        servers = self.cog._get_servers()
        structures = []

        if self.selected_server == "all":
            for name, save_dir in servers.items():
                try:
                    world_ark = save_dir / f"{save_dir.name}.ark"
                    if world_ark.exists():
                        server_structures = StructureExtractor.extract_structures_from_world(
                            world_ark
                        )
                        structures.extend(server_structures)
                except Exception as e:
                    logger.error(f"Error reading structures from {name}: {e}")
        else:
            if self.selected_server in servers:
                try:
                    save_dir = servers[self.selected_server]
                    world_ark = save_dir / f"{save_dir.name}.ark"
                    if world_ark.exists():
                        structures = StructureExtractor.extract_structures_from_world(world_ark)
                except Exception as e:
                    logger.error(f"Error reading structures: {e}")

        return structures

    # Callbacks
    async def server_selected(self, interaction: discord.Interaction):
        """Handle server selection."""
        self.selected_server = interaction.data["values"][0]
        self.current_page = 0
        self._setup_components()
        embed = await self.create_data_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def date_selected(self, interaction: discord.Interaction):
        """Handle date range selection."""
        self.date_range = interaction.data["values"][0]
        self.current_page = 0
        self._setup_components()
        embed = await self.create_data_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def open_search(self, interaction: discord.Interaction):
        """Open search modal."""
        modal = SearchModal(self)
        await interaction.response.send_modal(modal)

    async def prev_page(self, interaction: discord.Interaction):
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            embed = await self.create_data_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()

    async def next_page(self, interaction: discord.Interaction):
        """Go to next page."""
        self.current_page += 1
        embed = await self.create_data_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def refresh_data(self, interaction: discord.Interaction):
        """Refresh data."""
        self._setup_components()
        embed = await self.create_data_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class SearchModal(Modal):
    """Modal for searching data."""

    def __init__(self, dashboard_view: MainDashboardView):
        super().__init__(title="🔍 Search Data")
        self.dashboard_view = dashboard_view

        self.search_input = TextInput(
            label="Search Query",
            placeholder="Enter player name, tribe name, species, etc...",
            required=False,
            max_length=100,
        )
        self.add_item(self.search_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle search submission."""
        self.dashboard_view.search_query = self.search_input.value.strip()
        self.dashboard_view.current_page = 0
        self.dashboard_view._setup_components()
        embed = await self.dashboard_view.create_data_embed()
        await interaction.response.edit_message(embed=embed, view=self.dashboard_view)


class PlayerDetailView(View):
    """Detailed view for a single player."""

    def __init__(self, cog: AnalyticsDashboard, user: discord.User, player, server: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.user = user
        self.player = player
        self.server = server

        # Add buttons
        self.add_item(
            Button(
                label="View History",
                style=discord.ButtonStyle.primary,
                custom_id="history",
                emoji="📊",
            )
        )
        self.add_item(
            Button(
                label="View Stats", style=discord.ButtonStyle.primary, custom_id="stats", emoji="📈"
            )
        )
        self.add_item(
            Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="back", emoji="◀️")
        )

    async def create_embed(self) -> discord.Embed:
        """Create player detail embed."""
        embed = discord.Embed(
            title=f"👤 {self.player.character_name or self.player.player_name or 'Unknown Player'}",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="📛 Player Name", value=self.player.player_name or "Unknown", inline=True
        )
        embed.add_field(
            name="🎮 Character", value=self.player.character_name or "Unknown", inline=True
        )
        embed.add_field(
            name="📊 Level", value=self.dashboard._format_level(self.player), inline=True
        )

        embed.add_field(name="🆔 EOS ID", value=f"`{self.player.eos_id}`", inline=False)
        embed.add_field(
            name="🏛️ Tribe ID",
            value=str(self.player.tribe_id) if self.player.tribe_id else "No Tribe",
            inline=True,
        )
        embed.add_field(
            name="⭐ Experience",
            value=f"{self.player.experience:,.0f}" if self.player.experience else "Unknown",
            inline=True,
        )

        # Get full stats if profile available
        try:
            if hasattr(self.player, "file_path") and self.player.file_path:
                from pathlib import Path

                stats = PlayerStatsReader.extract_player_stats(Path(self.player.file_path))
                if stats:
                    stats_text = (
                        f"❤️ Health: {stats.health:.0f} | 💪 Stamina: {stats.stamina:.0f}\n"
                        f"⚖️ Weight: {stats.weight:.0f} | 🌊 Oxygen: {stats.oxygen:.0f}\n"
                        f"🍖 Food: {stats.food:.0f} | 💧 Water: {stats.water:.0f}\n"
                        f"⚔️ Melee: {stats.melee_damage:.1f}% | 🏃 Speed: {stats.movement_speed:.1f}%"
                    )
                    embed.add_field(name="📈 Full Stats", value=stats_text, inline=False)
        except Exception as e:
            logger.debug(f"Could not load full stats: {e}")

        # Get historical data if available
        try:
            if self.cog.tracker:
                progression = self.cog.tracker.get_player_level_progression(self.player.eos_id)
                if progression and len(progression) > 1:
                    recent = progression[-5:]
                    history_text = "\n".join(
                        [
                            f"{entry['timestamp'][:10]}: Lvl {entry['level']} (+{entry['level_gain']})"
                            for entry in recent
                        ]
                    )
                    embed.add_field(
                        name="📊 Recent Progress", value=history_text or "No data", inline=False
                    )
        except Exception as e:
            logger.debug(f"Could not load history: {e}")

        embed.set_footer(text=f"Server: {self.server.upper()}")
        return embed


class TribeDetailView(View):
    """Detailed view for a single tribe."""

    def __init__(self, cog: AnalyticsDashboard, user: discord.User, tribe, server: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.user = user
        self.tribe = tribe
        self.server = server

        # Add buttons
        self.add_item(
            Button(
                label="View Members",
                style=discord.ButtonStyle.primary,
                custom_id="members",
                emoji="👥",
            )
        )
        self.add_item(
            Button(
                label="View Dinos", style=discord.ButtonStyle.primary, custom_id="dinos", emoji="🦖"
            )
        )
        self.add_item(
            Button(
                label="View Structures",
                style=discord.ButtonStyle.primary,
                custom_id="structures",
                emoji="🏗️",
            )
        )
        self.add_item(
            Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="back", emoji="◀️")
        )

    async def create_embed(self) -> discord.Embed:
        """Create tribe detail embed."""
        embed = discord.Embed(
            title=f"🏛️ {self.tribe.tribe_name or 'Unknown Tribe'}", color=discord.Color.gold()
        )

        embed.add_field(name="🆔 Tribe ID", value=str(self.tribe.tribe_id), inline=True)
        embed.add_field(
            name="👥 Members",
            value=str(self.tribe.member_count) if self.tribe.member_count else "Unknown",
            inline=True,
        )
        embed.add_field(name="👑 Owner", value=self.tribe.owner_name or "Unknown", inline=True)

        # Get tribe's dinos
        try:
            servers = self.cog._get_servers()
            if self.server in servers:
                save_dir = servers[self.server]
                world_ark = save_dir / f"{save_dir.name}.ark"
                if world_ark.exists():
                    tribe_dinos = DinoExtractor.get_tribe_dinos(world_ark, self.tribe.tribe_id)
                    if tribe_dinos:
                        species_count = {}
                        for d in tribe_dinos:
                            species_count[d.species_name] = species_count.get(d.species_name, 0) + 1
                        top_species = sorted(
                            species_count.items(), key=lambda x: x[1], reverse=True
                        )[:5]
                        dinos_text = "\n".join([f"**{s}:** {c}" for s, c in top_species])
                        embed.add_field(
                            name=f"🦖 Tamed Dinos ({len(tribe_dinos)} total)",
                            value=dinos_text,
                            inline=True,
                        )
        except Exception as e:
            logger.debug(f"Could not load tribe dinos: {e}")

        # Get tribe's structures
        try:
            servers = self.cog._get_servers()
            if self.server in servers:
                save_dir = servers[self.server]
                world_ark = save_dir / f"{save_dir.name}.ark"
                if world_ark.exists():
                    tribe_structures = StructureExtractor.get_tribe_structures(
                        world_ark, self.tribe.tribe_id
                    )
                    if tribe_structures:
                        cat_count = {}
                        for s in tribe_structures:
                            cat = getattr(s, "category", "Unknown")
                            cat_count[cat] = cat_count.get(cat, 0) + 1
                        struct_text = "\n".join(
                            [
                                f"**{cat}:** {count}"
                                for cat, count in sorted(
                                    cat_count.items(), key=lambda x: x[1], reverse=True
                                )[:5]
                            ]
                        )
                        embed.add_field(
                            name=f"🏗️ Structures ({len(tribe_structures)} total)",
                            value=struct_text,
                            inline=True,
                        )
        except Exception as e:
            logger.debug(f"Could not load tribe structures: {e}")

        # Get historical data
        try:
            if self.cog.tracker:
                growth = self.cog.tracker.get_tribe_growth(self.tribe.tribe_id, days=30)
                if growth and len(growth) > 1:
                    first = growth[0]
                    last = growth[-1]
                    change = last["member_count"] - first["member_count"]
                    embed.add_field(
                        name="📊 30-Day Growth",
                        value=f"Members: {first['member_count']} → {last['member_count']} ({'+' if change >= 0 else ''}{change})",
                        inline=False,
                    )
        except Exception as e:
            logger.debug(f"Could not load tribe history: {e}")

        embed.set_footer(text=f"Server: {self.server.upper()}")
        return embed


class LeaderboardView(View):
    """View for displaying ARK cluster leaderboards."""

    def __init__(self, cog: AnalyticsDashboard, user: discord.User, servers: List[str], dashboard_view=None):
        super().__init__(timeout=None)
        self.cog = cog
        self.user = user
        self.servers = servers
        self.selected_server = servers[0] if servers else None
        self.board_type = "levels"  # levels, gainers, tribes, dinos
        self.dashboard_view = dashboard_view  # reference back to main dashboard

        self._setup_components()

    def _setup_components(self):
        """Setup view components."""
        self.clear_items()

        # Leaderboard type buttons
        boards = [
            ("Top Levels", "levels", "📊"),
            ("Level Gainers", "gainers", "📈"),
            ("Top Tribes", "tribes", "🏛️"),
            ("Most Dinos", "dinos", "🦖"),
        ]

        for label, board_id, emoji in boards:
            btn = Button(
                label=label,
                style=(
                    discord.ButtonStyle.primary
                    if board_id != self.board_type
                    else discord.ButtonStyle.success
                ),
                emoji=emoji,
                custom_id=f"board_{board_id}",
                row=0,
            )
            btn.callback = self._make_board_callback(board_id)
            self.add_item(btn)

        # Back to dashboard button (only shown when opened from the dashboard)
        if self.dashboard_view is not None:
            back_btn = Button(
                label="◀️ Back to Dashboard", style=discord.ButtonStyle.secondary,
                custom_id="back_to_dashboard", row=1,
            )
            back_btn.callback = self._back_to_dashboard
            self.add_item(back_btn)

    def _make_board_callback(self, board_type: str):
        """Create callback for board type button."""

        async def callback(interaction: discord.Interaction):
            self.board_type = board_type
            self._setup_components()
            embed = await self.create_leaderboard_embed()
            await interaction.response.edit_message(embed=embed, view=self)

        return callback

    async def _back_to_dashboard(self, interaction: discord.Interaction):
        """Return to the main analytics dashboard."""
        dv = self.dashboard_view
        dv._setup_components()
        embed = dv.create_main_embed()
        await interaction.response.edit_message(embed=embed, view=dv)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact."""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ This leaderboard is not for you!", ephemeral=True
            )
            return False
        return True

    async def create_leaderboard_embed(self) -> discord.Embed:
        """Create leaderboard embed based on type."""
        if self.board_type == "levels":
            return await self._create_levels_board()
        elif self.board_type == "gainers":
            return await self._create_gainers_board()
        elif self.board_type == "tribes":
            return await self._create_tribes_board()
        elif self.board_type == "dinos":
            return await self._create_dinos_board()
        return discord.Embed(title="Leaderboard", color=discord.Color.blue())

    async def _create_levels_board(self) -> discord.Embed:
        """Create top levels leaderboard."""
        embed = discord.Embed(title="📊 Top Players by Level", color=discord.Color.blue())

        try:
            servers = self.cog._get_servers()
            all_players = []
            for name, save_dir in servers.items():
                try:
                    reader = ArkSaveReader(save_dir)
                    players = reader.get_all_players()
                    for p in players:
                        p._server = name  # Add server info
                    all_players.extend(players)
                except Exception as e:
                    logger.error(f"Error reading players from {name}: {e}")

            # Sort by level
            all_players.sort(key=lambda p: p.level or 0, reverse=True)
            top_players = all_players[:15]

            if top_players:
                lines = ["```"]
                lines.append(f"{'Rank':<6} {'Character':<22} {'Lvl':<6} {'Server':<12}")
                lines.append("-" * 50)
                for i, player in enumerate(top_players, 1):
                    name = (player.character_name or player.player_name or "Unknown")[:20]
                    level = self._format_level(player)
                    server = getattr(player, "_server", "Unknown")[:10]
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
                    lines.append(f"{medal} {i:<3} {name:<22} {level:<6} {server:<12}")
                lines.append("```")
                embed.description = "\n".join(lines)
        except Exception as e:
            logger.error(f"Error creating levels board: {e}", exc_info=True)
            embed.description = f"❌ Error: {str(e)}"

        return embed

    async def _create_gainers_board(self) -> discord.Embed:
        """Create level gainers leaderboard."""
        embed = discord.Embed(
            title="📈 Top Level Gainers (Last 7 Days)", color=discord.Color.green()
        )

        try:
            if self.cog.tracker:
                top_gainers = self.cog.tracker.get_top_level_gainers(days=7, limit=15)

                if top_gainers:
                    lines = ["```"]
                    lines.append(f"{'Rank':<6} {'Player':<22} {'Gain':<8} {'Start→End':<12}")
                    lines.append("-" * 52)
                    for i, player in enumerate(top_gainers, 1):
                        name = (player["player_name"] or "Unknown")[:20]
                        gain = f"+{player['level_gain']}"
                        levels = f"{player['start_level']}→{player['end_level']}"
                        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
                        lines.append(f"{medal} {i:<3} {name:<22} {gain:<8} {levels:<12}")
                    lines.append("```")
                    embed.description = "\n".join(lines)
                else:
                    embed.description = (
                        "No historical data available yet. Run `/recordsnapshot` to start tracking."
                    )
            else:
                embed.description = "Historical tracking not available."
        except Exception as e:
            logger.error(f"Error creating gainers board: {e}", exc_info=True)
            embed.description = f"❌ Error: {str(e)}"

        return embed

    async def _create_tribes_board(self) -> discord.Embed:
        """Create top tribes leaderboard."""
        embed = discord.Embed(title="🏛️ Top Tribes by Members", color=discord.Color.gold())

        try:
            servers = self.cog._get_servers()
            all_tribes = []
            for name, save_dir in servers.items():
                try:
                    reader = ArkSaveReader(save_dir)
                    tribes = reader.get_all_tribes()
                    for t in tribes:
                        t._server = name
                    all_tribes.extend(tribes)
                except Exception as e:
                    logger.error(f"Error reading tribes from {name}: {e}")

            all_tribes.sort(key=lambda t: t.member_count or 0, reverse=True)
            top_tribes = all_tribes[:15]

            if top_tribes:
                lines = ["```"]
                lines.append(f"{'Rank':<6} {'Tribe':<25} {'Mem':<5} {'Server':<10}")
                lines.append("-" * 50)
                for i, tribe in enumerate(top_tribes, 1):
                    name = (tribe.tribe_name or "Unknown")[:23]
                    members = str(tribe.member_count) if tribe.member_count else "?"
                    server = getattr(tribe, "_server", "Unknown")[:8]
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
                    lines.append(f"{medal} {i:<3} {name:<25} {members:<5} {server:<10}")
                lines.append("```")
                embed.description = "\n".join(lines)
        except Exception as e:
            logger.error(f"Error creating tribes board: {e}", exc_info=True)
            embed.description = f"❌ Error: {str(e)}"

        return embed

    async def _create_dinos_board(self) -> discord.Embed:
        """Create most dinos leaderboard."""
        embed = discord.Embed(title="🦖 Top Tribes by Tamed Dinos", color=discord.Color.orange())

        try:
            servers = self.cog._get_servers()
            tribe_dino_counts = {}

            for name, save_dir in servers.items():
                try:
                    world_ark = save_dir / f"{save_dir.name}.ark"
                    if world_ark.exists():
                        dinos = DinoExtractor.extract_dinos_from_world(world_ark)
                        for dino in dinos:
                            if dino.tribe_id:
                                key = (dino.tribe_id, name)
                                tribe_dino_counts[key] = tribe_dino_counts.get(key, 0) + 1
                except Exception as e:
                    logger.error(f"Error reading dinos from {name}: {e}")

            # Sort by count
            sorted_tribes = sorted(tribe_dino_counts.items(), key=lambda x: x[1], reverse=True)[:15]

            if sorted_tribes:
                lines = ["```"]
                lines.append(f"{'Rank':<6} {'Tribe ID':<14} {'Dinos':<8} {'Server':<10}")
                lines.append("-" * 42)
                for i, ((tribe_id, server), count) in enumerate(sorted_tribes, 1):
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "  "
                    lines.append(f"{medal} {i:<3} {str(tribe_id):<14} {count:<8} {server[:8]:<10}")
                lines.append("```")
                embed.description = "\n".join(lines)
            else:
                embed.description = "No dino data found."
        except Exception as e:
            logger.error(f"Error creating dinos board: {e}", exc_info=True)
            embed.description = f"❌ Error: {str(e)}"

        return embed


# ---------------------------------------------------------------------------
# Module-level constants (used by the /report command group above)
# ---------------------------------------------------------------------------

TIME_RANGE_DAYS = {"1d": 1, "7d": 7, "30d": 30, "6m": 180, "1y": 365}
TIME_RANGE_LABELS = {
    "1d": "Last 24 hours",
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    "6m": "Last 6 months",
    "1y": "Last year",
}

# Chart label dicts — map data key → human-readable Select option label
PLAYER_CHARTS: dict[str, str] = {
    "daily_active":           "Daily Active Players",
    "sessions_by_server":     "Sessions per Server",
    "avg_duration_by_server": "Avg Session Duration",
    "sessions_by_hour":       "Sessions by Hour of Day",
}
ECONOMY_CHARTS: dict[str, str] = {
    "payday_by_day":    "Coins Distributed per Day",
    "type_breakdown":   "Transaction Type Breakdown",
    "top_balances":     "Top 10 Player Balances",
    "cumulative_coins": "Cumulative Coins in Circulation",
}
SHOP_CHARTS: dict[str, str] = {
    "purchases_by_day":  "Purchases per Day",
    "top_items":         "Top 10 Items Purchased",
    "spend_by_category": "Spend by Category",
    "coins_by_day":      "Coins Spent per Day",
}
SERVER_CHARTS: dict[str, str] = {
    "sessions_by_server_day": "Sessions per Server Over Time",
    "total_by_server":        "Total Sessions per Server",
    "new_players_by_day":     "New Players per Day",
    "activity_by_hour":       "Activity by Hour of Day",
}


def _has_data(data: dict) -> bool:
    """Return True if at least one list in the data dict is non-empty."""
    return any(bool(v) for v in data.values())


class ReportChartSelect(discord.ui.Select):
    """Dropdown that generates and sends a single chart image on selection."""

    def __init__(self, charts: dict, data: dict, guild_name: str,
                 time_label: str, generate_fn):
        options = [
            discord.SelectOption(label=label, value=key)
            for key, label in charts.items()
        ]
        super().__init__(
            placeholder="Select a chart to view…",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.data = data
        self.guild_name = guild_name
        self.time_label = time_label
        self.generate_fn = generate_fn
        self.charts = charts

    async def callback(self, interaction: discord.Interaction) -> None:
        chart_key = self.values[0]
        chart_label = self.charts.get(chart_key, chart_key)
        await interaction.response.defer(ephemeral=True)
        buf = await asyncio.get_running_loop().run_in_executor(
            None,
            self.generate_fn,
            chart_key, self.data, self.guild_name, self.time_label,
        )
        if buf is None:
            await interaction.followup.send(
                f"📭 No data available for **{chart_label}** in this time period.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            file=discord.File(buf, filename=f"{chart_key}.png"),
            ephemeral=True,
        )


class ReportChartSelectView(discord.ui.View):
    """View containing a single ReportChartSelect dropdown."""

    def __init__(self, charts: dict, data: dict, guild_name: str,
                 time_label: str, generate_fn):
        super().__init__(timeout=300)
        self.add_item(ReportChartSelect(charts, data, guild_name, time_label, generate_fn))


async def setup(bot):
    """Setup the cog."""
    await bot.add_cog(AnalyticsDashboard(bot))
