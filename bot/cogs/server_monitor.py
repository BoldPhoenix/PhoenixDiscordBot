"""
Server monitoring cog for tracking server status and online players.
Creates voice channels for real-time server status display.
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
from typing import Optional, Dict, List, Set, Tuple
from datetime import datetime, timedelta
import subprocess

from bot.rcon.client import RCONManager
from bot.utils.validation import validate_service_name

# Steam Query disabled - ARK Ascended doesn't support A2S protocol reliably
# from bot.rcon.steam_query import SteamQueryManager
from bot.utils.system_monitor import SystemServerMonitor
from bot.utils.log_parser import parse_server_startup_info
from bot.utils.config import Config
from bot.database import server_config_db

logger = logging.getLogger("ServerMonitorCog")


class ServerMonitor(commands.Cog):
    """Commands for monitoring server status and players."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Multi-guild support: Per-guild state dictionaries
        self.guild_rcon_managers: Dict[int, RCONManager] = {}  # guild_id -> RCONManager
        self.guild_server_caches: Dict[int, Dict[str, dict]] = {}  # guild_id -> {server_name -> status}
        self.guild_voice_channels: Dict[int, Dict[int, int]] = {}  # guild_id -> {rcon_port -> channel_id}
        self.guild_status_messages: Dict[int, tuple] = {}  # guild_id -> (message_id, age)
        self.guild_status_categories: Dict[int, int] = {}  # guild_id -> category_id
        
        # Shared across all guilds
        self.system_monitor = SystemServerMonitor()  # Local filesystem/process monitoring
        self.log_paths_initialized = False
        self._consecutive_failures: Dict[int, int] = {}  # server_id -> failure count
        self._previous_players: Dict[int, Set[str]] = {}  # server_id -> eos_id set
        self.voice_rename_times: Dict[int, List[datetime]] = {}  # Track voice channel rename rate limits
        self.last_player_counts: Dict[int, int] = {}  # server_id -> player count
        self._player_consecutive_scans: Dict[Tuple[int, str], int] = {}  # (guild_id, eos_id) -> scan count
        # Start background loops
        self.purge_inactive_loop.start()
        self.monitor_loop.start()

    async def _initialize_log_paths(self):
        """Initialize log file paths for all servers and parse startup info."""
        if self.log_paths_initialized:
            return

        await asyncio.sleep(5)  # Wait for bot ready

        # Initialize for all guilds
        for guild in self.bot.guilds:
            guild_id = guild.id
            server_list = await self._get_server_list(guild_id)
            
            for server in server_list:
                server_name = server["name"]
                server_path = server.get("server_path", "")
                server_id = server.get("id")

                if server_path:
                    # Log path: <server_path>\ShooterGame\Saved\Logs\ShooterGame.log
                    log_path = f"{server_path}\\ShooterGame\\Saved\\Logs\\ShooterGame.log"
                    self.system_monitor.add_server(server_name, log_path)
                    logger.info(f"Monitoring log for {server_name}: {log_path}")

                    # Parse startup info from log file
                    try:
                        startup_info = parse_server_startup_info(log_path)
                        updates = {}

                        # Update max_players in DB if log differs (keep DB in sync)
                        if startup_info["max_players"] and startup_info["max_players"] != server.get(
                            "max_players"
                        ):
                            updates["max_players"] = startup_info["max_players"]

                        # Detect and cache ARK version from log on startup
                        from bot.utils.log_parser import extract_ark_version
                        detected_version = extract_ark_version(log_path)
                        if detected_version and detected_version != server.get("ark_version"):
                            updates["ark_version"] = detected_version
                            logger.info(f"{server_name}: Detected ARK version {detected_version}")

                        # Update cluster info in guild config if found
                        if startup_info["cluster_id"] or startup_info["cluster_folder_path"]:
                            if startup_info["cluster_id"]:
                                logger.info(
                                    f"{server_name}: Detected ClusterId={startup_info['cluster_id']}"
                                )
                            if startup_info["cluster_folder_path"]:
                                logger.info(
                                    f"{server_name}: Detected ClusterFolder={startup_info['cluster_folder_path']}"
                                )

                            # Update guild config with cluster info (always update if detected)
                            guild_config = await server_config_db.get_server_config(guild_id)
                            cluster_updates = {}

                            # Always update cluster info if detected from logs
                            if startup_info["cluster_id"]:
                                cluster_updates["cluster_id"] = startup_info["cluster_id"]
                            if startup_info["cluster_folder_path"]:
                                cluster_updates["cluster_folder_path"] = startup_info[
                                    "cluster_folder_path"
                                ]

                            if cluster_updates:
                                await server_config_db.create_or_update_server_config(
                                    guild_id,
                                    (
                                        self.bot.get_guild(guild_id).name
                                        if self.bot.get_guild(guild_id)
                                        else "Unknown"
                                    ),
                                    **cluster_updates,
                                )
                                logger.info(f"Updated guild cluster config: {cluster_updates}")

                        # Apply server updates if any
                        if updates and server_id:
                            await server_config_db.update_ark_server(server_id, **updates)
                            logger.info(f"Updated {server_name} config: {updates}")

                    except Exception as e:
                        logger.warning(f"Failed to parse startup info for {server_name}: {e}")
                else:
                    logger.warning(
                        f"No server_path configured for {server_name} - log monitoring disabled"
                    )

        self.log_paths_initialized = True

    async def _get_server_list(self, guild_id: int):
        """Get server list from database for a specific guild."""
        # Get servers from database for this guild
        servers = await server_config_db.get_ark_servers(guild_id)
        # Filter to only enabled servers
        servers = [s for s in servers if s.get("enabled", True)]
        
        if servers:
            logger.debug(f"Loaded {len(servers)} servers for guild {guild_id}")
        return servers

    async def _get_guild_config(self, guild_id: int):
        """Get configuration for a guild from database, fallback to .env."""
        # Try database first
        config = await server_config_db.get_server_config(guild_id)
        servers = await self._get_server_list(guild_id)

        if config:
            # Use database config
            return {
                "status_channel_id": config.get("status_channel_id"),
                "chat_channel_id": config.get("chat_channel_id"),
                "status_update_interval": config.get("status_update_interval", 60),
                "servers": servers,
            }
        else:
            # Fallback to .env config
            return {
                "status_channel_id": Config.STATUS_CHANNEL_ID,
                "chat_channel_id": Config.CHAT_CHANNEL_ID,
                "status_update_interval": Config.STATUS_UPDATE_INTERVAL,
                "servers": servers,
            }

    async def _get_status_channel_id(self, guild_id: int) -> Optional[int]:
        """Get status channel ID from database for a specific guild."""
        # Get from database
        config = await server_config_db.get_server_config(guild_id)
        if config and config.get("status_channel_id"):
            return config.get("status_channel_id")
        
        return None

    async def _refresh_server_status_cache(self, trigger_voice_update_on_change: bool = False):
        """Refresh the server status cache by parsing logs + validating with RCON.

        Args:
            trigger_voice_update_on_change: If True, immediately update voice channel
                                           when server status changes (online <-> offline)
        """
        if not self.rcon_manager:
            return

        # Ensure log paths are initialized
        if not self.log_paths_initialized:
            await self._initialize_log_paths()

        server_list = await self._get_server_list()

        for server_name, client in self.rcon_manager.clients.items():
            # Get server config by name
            server_config = next((s for s in server_list if s["name"] == server_name), None)
            max_players = server_config.get("max_players") if server_config else None
            rcon_port = server_config.get("rcon_port") if server_config else None
            service_name = server_config.get("service_name") if server_config else None

            # Store previous online status and player count to detect changes
            was_online = self.server_status_cache.get(server_name, {}).get("online", None)
            was_player_count = self.server_status_cache.get(server_name, {}).get(
                "player_count", None
            )

            # Initialize variables - assume offline until proven otherwise
            is_online = False
            player_count = 0
            player_list = []
            service_running = None
            rcon_connectivity = None

            # Check service status for informational purposes (not decision-making)
            if service_name and validate_service_name(service_name):
                try:
                    result = subprocess.run(
                        ["sc", "query", service_name], capture_output=True, text=True, timeout=5
                    )
                    out = (result.stdout or "").lower()
                    if "state" in out and "running" in out:
                        service_running = True
                    elif "state" in out:
                        service_running = False
                except Exception as se:
                    logger.debug(
                        f"Service status check failed for {server_name} ({service_name}): {se}"
                    )

            try:
                # Step 1: Parse new log entries for instant login detection
                new_logins = await self.system_monitor.parse_new_log_entries(server_name)
                if new_logins:
                    logger.info(f"{server_name}: Detected {len(new_logins)} new login(s) from log")

                # Step 2: Get player list from RCON (every 60s interval)
                # IMPORTANT: RCON connectivity is the SOURCE OF TRUTH for online status
                # Service status is only informational
                rcon_success = False
                logger.debug(f"Querying {server_name} player list via RCON")

                try:
                    rcon_players = await client.get_player_list()
                    
                    # If we got any response (empty list = no players, list = players), server is ONLINE
                    if rcon_players is not None:
                        rcon_success = True
                        is_online = True
                        player_list = rcon_players
                        player_count = len(rcon_players)
                        logger.info(f"RCON: {server_name} has {player_count} players")
                        
                        online_eos_ids = {p.get("eos_id") for p in rcon_players if p.get("eos_id")}
                        self.system_monitor.active_sessions[server_name] = online_eos_ids
                        self.system_monitor.last_rcon_validation[server_name] = datetime.now()
                    else:
                        # None = Keep Alive only (ambiguous) - treat as offline
                        rcon_success = False
                        is_online = False
                        player_count = 0
                        player_list = []
                        logger.warning(f"RCON: {server_name} returned Keep Alive only - OFFLINE")

                except Exception as rcon_err:
                    # Timeout, connection reset, etc = OFFLINE
                    logger.warning(f"RCON failed for {server_name}: {rcon_err}")
                    rcon_success = False
                    is_online = False
                    player_count = 0
                    player_list = []

                # Get version from server config (already fetched in _get_server_list)
                version = None
                if server_config:
                    version = server_config.get("ark_version")
                    if version:
                        logger.info(f"{server_name}: Using database version {version}")
                
                # No version in database — leave as None so voice channel omits it
                if not version:
                    logger.debug(f"{server_name}: No version in database, voice channel will omit it")

                # Update cache
                self.server_status_cache[server_name] = {
                    "online": is_online,
                    "player_count": player_count,
                    "players": player_list,
                    "max_players": max_players,
                    "version": version,
                    "last_successful_query": datetime.now() if is_online else None,
                }

                # DISABLED: Upsert players encountered into user DB cache
                # This was causing database corruption because discord_user_id is PRIMARY KEY (can't be NULL)
                # Use /lookupplayer and /adminlinkplayer instead to manually link players

                # ENABLED: Update last_seen for players we can identify by EOS ID
                try:
                    from bot.database import players_db

                    for p in player_list:
                        # Extract EOS ID
                        eos_id = (
                            (p.get("eos_id") if isinstance(p, dict) else None)
                            or (p.get("EOSID") if isinstance(p, dict) else None)
                            or (p.get("id") if isinstance(p, dict) else None)
                        )
                        char_name = (p.get("character_name") if isinstance(p, dict) else None) or (
                            p.get("name") if isinstance(p, dict) else None
                        )

                        if eos_id:
                            # Update last_seen for this player (sets both last_server and last_seen_server)
                            await players_db.update_player_last_seen(
                                eos_id=str(eos_id),
                                server_name=server_name,
                                character_name=char_name,
                            )
                except Exception as e:
                    logger.warning(f"Failed to update player last_seen: {e}")

                # Session tracking: detect joins and leaves
                try:
                    from bot.database import players_db

                    current_eos_ids: Set[str] = set()
                    player_data: Dict[str, Dict] = {}  # eos_id -> player data

                    for p in player_list:
                        eos_id = (
                            (p.get("eos_id") if isinstance(p, dict) else None)
                            or (p.get("EOSID") if isinstance(p, dict) else None)
                            or (p.get("id") if isinstance(p, dict) else None)
                        )
                        if eos_id:
                            eos_str = str(eos_id)
                            current_eos_ids.add(eos_str)
                            player_data[eos_str] = p

                    _sid = (server_config.get("id") if server_config else None) or 0
                    previous_eos_ids = self._previous_players.get(_sid, set())

                    # Detect joins (new players)
                    joined = current_eos_ids - previous_eos_ids
                    for eos_id in joined:
                        p = player_data.get(eos_id, {})
                        char_name = (p.get("character_name") if isinstance(p, dict) else None) or (
                            p.get("name") if isinstance(p, dict) else None
                        )
                        # Get discord_id if player is linked
                        player_info = await players_db.get_player_by_eos_id(eos_id)
                        discord_id = player_info.get("discord_user_id") if player_info else None
                        await players_db.start_player_session(
                            guild_id=server["guild_id"],
                            eos_id=eos_id,
                            discord_id=discord_id,
                            character_name=char_name,
                            server_name=server_name,
                        )

                    # Detect leaves (players who left)
                    left = previous_eos_ids - current_eos_ids
                    for eos_id in left:
                        await players_db.end_player_session(
                            guild_id=server["guild_id"],
                            eos_id=eos_id,
                            server_name=server_name,
                        )

                    # Update previous players for next scan
                    self._previous_players[_sid] = current_eos_ids

                    if joined or left:
                        logger.debug(
                            f"Session tracking for {server_name}: {len(joined)} joined, {len(left)} left, {len(current_eos_ids)} online"
                        )
                except Exception as e_session:
                    logger.warning(f"Failed to track sessions for {server_name}: {e_session}")
                # try:
                #     from bot.database import players_db
                #     for p in player_list:
                #         # Attempt to extract useful fields conservatively
                #         eos_id = (
                #             (p.get('eos_id') if isinstance(p, dict) else None)
                #             or (p.get('EOSID') if isinstance(p, dict) else None)
                #             or (p.get('id') if isinstance(p, dict) else None)
                #         )
                #         char_name = (p.get('character_name') if isinstance(p, dict) else None) or (p.get('name') if isinstance(p, dict) else None)
                #         player_name = (p.get('player_name') if isinstance(p, dict) else None)
                #         if eos_id:
                #             await players_db.upsert_player_seen(
                #                 eos_id=str(eos_id),
                #                 character_name=char_name,
                #                 player_name=player_name,
                #                 server_name=server_name,
                #                 seen_timestamp=None,
                #             )
                # except Exception as e_up:
                #     logger.warning(f"Failed to upsert seen players for {server_name}: {e_up}")

                # Auto-sync specimen IDs for online linked players
                try:
                    from bot.database import players_db

                    for p in player_list:
                        eos_id = (
                            (p.get("eos_id") if isinstance(p, dict) else None)
                            or (p.get("EOSID") if isinstance(p, dict) else None)
                            or (p.get("id") if isinstance(p, dict) else None)
                        )
                        if eos_id:
                            # Check if player is linked to Discord and missing specimen ID
                            player_info = await players_db.get_player_by_eos_id(str(eos_id))
                            if (
                                player_info
                                and player_info.get("discord_user_id")
                                and not player_info.get("specimen_id")
                            ):
                                # Attempt to fetch specimen ID via RCON
                                specimen_id = await players_db.sync_specimen_id_from_rcon(
                                    client, str(eos_id), player_info["discord_user_id"]
                                )
                                if specimen_id:
                                    logger.info(
                                        f"Auto-synced specimen ID {specimen_id} for EOS {eos_id}"
                                    )
                except Exception as e_spec:
                    logger.warning(f"Failed to auto-sync specimen IDs for {server_name}: {e_spec}")

            except Exception as e:
                # Any exception from player tracking - log but don't change online status
                # Online status was already determined by RCON check above
                logger.warning(f"Player tracking error for {server_name}: {e}")

            # If server went offline, end all sessions
            if not is_online and was_online:
                try:
                    from bot.database import players_db
                    ended = await players_db.end_all_server_sessions(
                        server["guild_id"], server_name
                    )
                    if ended > 0:
                        logger.info(f"Ended {ended} session(s) for {server_name} (server offline)")
                    self._previous_players.pop(_sid, None)
                except Exception as e_session:
                    logger.warning(f"Failed to end sessions for {server_name}: {e_session}")

            # Trigger immediate voice channel update if status CHANGED
            if trigger_voice_update_on_change and rcon_port and was_online is not None:
                try:
                    # Check for online/offline transition
                    if was_online != is_online:
                        status_change = "OFFLINE" if not is_online else "ONLINE"
                        logger.warning(
                            f"🚨 Server {server_name} went {status_change}! Triggering immediate voice update."
                        )
                        await self.update_voice_channel(
                            rcon_port, server_name, is_online, player_count, max_players,
                            self.server_status_cache.get(server_name, {}).get("version")
                        )
                    # Check for 0 ↔ non-zero player count transition (player joined/left)
                    elif was_player_count is not None:
                        became_empty = was_player_count > 0 and player_count == 0
                        became_occupied = was_player_count == 0 and player_count > 0
                        if became_empty or became_occupied:
                            transition = "EMPTY" if became_empty else "OCCUPIED"
                            logger.warning(
                                f"🚨 Server {server_name} became {transition} ({was_player_count}→{player_count})! Triggering immediate voice update."
                            )
                            await self.update_voice_channel(
                                rcon_port, server_name, is_online, player_count, max_players,
                                self.server_status_cache.get(server_name, {}).get("version")
                            )
                except Exception as voice_err:
                    logger.error(f"Failed to trigger voice update for {server_name}: {voice_err}", exc_info=True)

    def cog_unload(self):
        """Cleanup when cog is unloaded."""
        self.monitor_loop.cancel()
        self.purge_inactive_loop.cancel()

    async def _get_or_create_status_category(
        self, guild: discord.Guild
    ) -> Optional[discord.CategoryChannel]:
        """Get or create the Server Status category for voice channels."""
        guild_id = guild.id
        
        # Check if we have a configured category ID
        guild_config = await server_config_db.get_server_config(guild_id)
        if guild_config and guild_config.get("voice_category_id"):
            category = guild.get_channel(guild_config["voice_category_id"])
            if category and isinstance(category, discord.CategoryChannel):
                self.guild_status_categories[guild_id] = category.id
                logger.info(f"Using configured voice category: {category.name} ({category.id})")
                return category

        # Look for existing category by name
        for category in guild.categories:
            if category.name == "Server Status":
                self.guild_status_categories[guild_id] = category.id
                return category

        # Create new category
        try:
            category = await guild.create_category(
                name="Server Status", reason="ARK Bot - Server status monitoring"
            )
            self.guild_status_categories[guild_id] = category.id
            logger.info(f"Created Server Status category: {category.id}")
            return category
        except Exception as e:
            logger.error(f"Failed to create Server Status category: {e}")
            return None

    async def create_voice_channel_for_server(self, guild_id: int, server_config: dict) -> bool:
        """Create a voice channel for a server."""
        server_name = server_config["name"]
        rcon_port = server_config["rcon_port"]

        guild = self.bot.get_guild(guild_id)
        if not guild:
            logger.warning(f"Guild {guild_id} not found")
            return False
        
        # Initialize voice channels dict for this guild if needed
        if guild_id not in self.guild_voice_channels:
            self.guild_voice_channels[guild_id] = {}

        category = await self._get_or_create_status_category(guild)
        # Check DB for existing voice channel id to prevent duplicates
        try:
            channel_id = await server_config_db.get_voice_channel_id(
                guild_id, int(rcon_port)
            )
            if channel_id:
                ch = guild.get_channel(int(channel_id))
                if ch and isinstance(ch, discord.VoiceChannel):
                    self.guild_voice_channels[guild_id][rcon_port] = int(ch.id)
                    logger.info(
                        f"Linked existing channel by DB for {server_name} (port {rcon_port}): {ch.id}"
                    )
                    return True
                else:
                    # Channel doesn't exist anymore, clear from DB
                    logger.warning(
                        f"Stored channel {channel_id} for {server_name} not found, will create new one"
                    )
                    await server_config_db.clear_server_voice_channel_id(
                        guild_id, int(rcon_port)
                    )
        except Exception as e:
            logger.error(f"Error checking DB for existing voice channel for {server_name}: {e}")

        try:
            # Create voice channel with initial status (VoiceChannel has no 'topic' attribute)
            channel = await guild.create_voice_channel(
                name=f"🔴 {server_name} - 0/0",
                category=category,
                reason=f"ARK Bot - Monitoring for {server_name}",
            )

            # Lock the channel so users can't join
            await channel.set_permissions(guild.default_role, connect=False)

            self.guild_voice_channels[guild_id][rcon_port] = channel.id

            # Save channel ID to database for persistence across restarts
            try:
                await server_config_db.set_server_voice_channel_id(
                    guild_id, int(rcon_port), channel.id
                )
                logger.info(
                    f"Created voice channel for {server_name} (port {rcon_port}): {channel.id} (saved to DB)"
                )
            except Exception as db_err:
                logger.warning(
                    f"Created voice channel for {server_name} but failed to save to DB: {db_err}"
                )

            return True
        except Exception as e:
            logger.error(f"Failed to create voice channel for {server_name}: {e}")
            return False

    async def delete_voice_channel_for_server(
        self, guild_id: int, rcon_port: int, server_name: str = "Unknown"
    ) -> bool:
        """Delete a voice channel for a server."""
        voice_channels = self.guild_voice_channels.get(guild_id, {})
        channel_id = voice_channels.get(rcon_port)
        if not channel_id:
            logger.warning(f"No voice channel found for port {rcon_port} in guild {guild_id}")
            return False

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False

        channel = guild.get_channel(channel_id)
        if not channel:
            # Channel already deleted, clean up our tracking
            del voice_channels[rcon_port]
            return True

        try:
            await channel.delete(
                reason=f"ARK Bot - Server {server_name} (port {rcon_port}) removed from monitoring"
            )
            del voice_channels[rcon_port]

            # Clear from database as well
            try:
                await server_config_db.clear_server_voice_channel_id(
                    guild_id, int(rcon_port)
                )
                logger.info(
                    f"Deleted voice channel for {server_name} (port {rcon_port}) and cleared from DB"
                )
            except Exception as db_err:
                logger.warning(f"Deleted voice channel but failed to clear from DB: {db_err}")

            return True
        except Exception as e:
            logger.error(f"Failed to delete voice channel for {server_name}: {e}")
            return False

    def _can_rename_channel(self, rcon_port: int) -> bool:
        """Return True if fewer than 2 renames have occurred in the last 10 minutes."""
        cutoff = datetime.now() - timedelta(minutes=10)
        recent = [t for t in self.voice_rename_times.get(rcon_port, []) if t > cutoff]
        return len(recent) < 2

    def _record_rename(self, rcon_port: int):
        """Record a successful rename timestamp, keeping only the last 2 within 10 minutes."""
        now = datetime.now()
        cutoff = now - timedelta(minutes=10)
        recent = [t for t in self.voice_rename_times.get(rcon_port, []) if t > cutoff]
        recent.append(now)
        self.voice_rename_times[rcon_port] = recent[-2:]

    def _seconds_until_can_rename(self, rcon_port: int) -> float:
        """Return seconds until a rename is allowed (0 if allowed now)."""
        now = datetime.now()
        cutoff = now - timedelta(minutes=10)
        recent = sorted(t for t in self.voice_rename_times.get(rcon_port, []) if t > cutoff)
        if len(recent) < 2:
            return 0.0
        return max(0.0, (recent[0] + timedelta(minutes=10) - now).total_seconds())

    async def _retry_voice_update(self, guild_id: int, rcon_port: int, server_name: str, delay: float):
        """Retry a voice channel update after rate-limit delay, using fresh cache state."""
        await asyncio.sleep(delay + 2)
        cache = self.guild_server_caches.get(guild_id, {}).get(server_name)
        if cache is None:
            return
        server_list = await self._get_server_list(guild_id)
        srv_cfg = next((s for s in server_list if s.get("rcon_port") == rcon_port), None)
        if not srv_cfg:
            return
        await self.update_voice_channel(
            guild_id, rcon_port, server_name,
            cache.get("online", False),
            cache.get("player_count", 0),
            srv_cfg.get("max_players"),
            cache.get("version"),
        )

    async def update_voice_channel(
        self,
        guild_id: int,
        rcon_port: int,
        server_name: str,
        is_online: bool,
        player_count: int,
        max_players=None,
        version: str = None,
    ):
        """Update a voice channel with current server status."""
        # Get voice channels for this guild
        if guild_id not in self.guild_voice_channels:
            self.guild_voice_channels[guild_id] = {}
        
        voice_channels = self.guild_voice_channels[guild_id]
        channel_id = voice_channels.get(rcon_port)

        # If channel doesn't exist, create it
        if not channel_id:
            logger.info(f"No voice channel found for {server_name} (port {rcon_port}), creating one...")
            # Get server config to pass to create function
            try:
                servers = await server_config_db.get_ark_servers(guild_id)
                server_config = next((s for s in servers if s.get("rcon_port") == rcon_port), None)
                if server_config:
                    created = await self.create_voice_channel_for_server(guild_id, server_config)
                    if created:
                        logger.info(f"✅ Created voice channel for {server_name}")
                        # Get the newly created channel ID
                        channel_id = self.guild_voice_channels.get(guild_id, {}).get(rcon_port)
                        if not channel_id:
                            logger.error(f"Channel was created but not found in tracking dict")
                            return
                    else:
                        logger.error(f"Failed to create voice channel for {server_name}")
                        return
                else:
                    logger.error(f"Server config not found for port {rcon_port}")
                    return
            except Exception as e:
                logger.error(f"Error creating voice channel for {server_name}: {e}", exc_info=True)
                return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            # Channel was deleted, remove from tracking
            del voice_channels[rcon_port]
            return

        # Format status indicator and name with version if available
        status_emoji = "🟢" if is_online else "🔴"
        capacity = max_players if max_players is not None else "??"
        if version:
            new_name = f"{status_emoji} {server_name} (v{version}) - {player_count}/{capacity}"
        else:
            new_name = f"{status_emoji} {server_name} - {player_count}/{capacity}"

        # Log current vs new name for debugging
        logger.info(f"Voice channel update check for {server_name}:")
        logger.info(f"  Current: '{channel.name}'")
        logger.info(f"  New:     '{new_name}'")
        logger.info(f"  Match:   {channel.name == new_name}")

        # Only update if name changed (to avoid unnecessary renames)
        if channel.name != new_name:
            # Check sliding-window rate limit before calling Discord API
            if not self._can_rename_channel(rcon_port):
                wait = self._seconds_until_can_rename(rcon_port)
                logger.info(
                    f"Voice channel for {server_name}: rate limit reached, retrying in {wait:.0f}s"
                )
                asyncio.create_task(self._retry_voice_update(guild_id, rcon_port, server_name, wait))
                return
            try:
                # Add timeout to prevent hanging on Discord API calls
                await asyncio.wait_for(
                    channel.edit(name=new_name, reason="ARK Bot - Status update"),
                    timeout=10.0
                )
                self._record_rename(rcon_port)
                logger.info(f"✓ Updated voice channel for {server_name}: {new_name}")
            except asyncio.TimeoutError:
                logger.error(f"Timeout updating voice channel for {server_name} (10s limit exceeded)")
            except discord.HTTPException as e:
                if e.status == 429:  # Discord rate limited us anyway
                    retry_after = getattr(e, "retry_after", 60.0)
                    logger.warning(
                        f"Rate limited by Discord for {server_name}, retrying in {retry_after:.0f}s"
                    )
                    asyncio.create_task(self._retry_voice_update(guild_id, rcon_port, server_name, retry_after))
                else:
                    logger.error(f"Failed to update voice channel for {server_name}: {e}")
            except Exception as e:
                logger.error(f"Failed to update voice channel for {server_name}: {e}")
        else:
            logger.debug(f"Voice channel for {server_name} unchanged, skipping update")

    @tasks.loop(seconds=30.0)
    async def monitor_loop(self):
        """Single consolidated monitoring loop - multi-guild aware.
        
        Every 30 seconds:
        1. Check RCON for each server in each guild
        2. Update per-guild status cache
        3. Update voice channels if status changed
        4. Update status embed per guild
        5. Process pending deliveries for stable players
        """
        try:
            # Monitor servers for all guilds
            for guild in self.bot.guilds:
                guild_id = guild.id
                
                # Get RCON manager for this guild
                rcon_manager = self.guild_rcon_managers.get(guild_id)
                if not rcon_manager:
                    logger.debug(f"No RCON manager for guild {guild_id}, skipping")
                    continue
                
                # Get server list for this guild
                server_list = await self._get_server_list(guild_id)
                if not server_list:
                    continue
                
                # Initialize guild cache if needed
                if guild_id not in self.guild_server_caches:
                    self.guild_server_caches[guild_id] = {}
                
                server_cache = self.guild_server_caches[guild_id]

                # === STEP 1: Check each server via RCON ===
                for server_config in server_list:
                    server_name = server_config.get("name")
                    server_id = server_config.get("id")
                    rcon_port = server_config.get("rcon_port")
                    max_players = server_config.get("max_players")

                    if not server_name or not rcon_port or not server_id:
                        continue

                    # Get previous status for change detection
                    prev_cache = server_cache.get(server_name, {})
                    was_online = prev_cache.get("online", None)
                    was_player_count = prev_cache.get("player_count", None)
                    was_version = prev_cache.get("version")  # Capture BEFORE cache is updated

                    # Check RCON with timeout
                    is_online = False
                    player_count = 0
                    player_list = []
                    
                    try:
                        client = rcon_manager.get_client(server_name)
                        if client:
                            # 5 second timeout (increased from 3s for reliability)
                            players = await asyncio.wait_for(
                                client.get_player_list(),
                                timeout=5.0
                            )
                            # Any response (even empty list) = ONLINE
                            if players is not None:
                                is_online = True
                                player_list = players
                                player_count = len(players)
                                logger.info(f"RCON: {server_name} has {player_count} players - ONLINE")
                                # Reset failure counter on success
                                self._consecutive_failures[server_id] = 0
                            else:
                                # None response = Keep Alive only = ambiguous, treat as offline
                                is_online = False
                                logger.warning(f"RCON: {server_name} returned Keep Alive only - OFFLINE")
                    except asyncio.TimeoutError:
                        is_online = False
                        logger.warning(f"RCON: {server_name} timed out after 5s - OFFLINE")
                        # Force reconnect on timeout
                        self._consecutive_failures[server_id] = self._consecutive_failures.get(server_id, 0) + 1
                    except Exception as e:
                        is_online = False
                        logger.warning(f"RCON: {server_name} error: {e} - OFFLINE")
                        self._consecutive_failures[server_id] = self._consecutive_failures.get(server_id, 0) + 1

                    # Force reconnect after 3 consecutive failures
                    if self._consecutive_failures.get(server_id, 0) >= 3:
                        logger.warning(f"RCON: {server_name} failed 3+ times, forcing reconnect")
                        try:
                            client = rcon_manager.get_client(server_name)
                            if client:
                                await client.disconnect()
                        except Exception:
                            pass
                        self._consecutive_failures[server_id] = 0

                    # If server just came back online (e.g. after an update), re-read log
                    # to detect the new version and max_players.
                    if is_online and was_online is False:
                        try:
                            server_path = server_config.get("server_path")
                            if server_path and server_id:
                                from bot.utils.ark_version import detect_and_cache_server_version
                                new_ver = await detect_and_cache_server_version(server_id, server_path)
                                if new_ver:
                                    logger.info(f"🔄 {server_name} back online — detected version {new_ver}")
                        except Exception as e:
                            logger.warning(f"Failed to detect version for {server_name} on restart: {e}")
                    # Get version from database (may have just been refreshed above)
                    version = None
                    try:
                        servers = await server_config_db.get_ark_servers(guild_id)
                        for s in servers:
                            if s.get("name") == server_name and s.get("ark_version"):
                                version = s.get("ark_version")
                                break
                    except Exception:
                        pass

                    # === STEP 2: Update cache ===
                    server_cache[server_name] = {
                        "online": is_online,
                        "player_count": player_count,
                        "players": player_list,
                        "max_players": max_players,
                        "version": version,
                        "last_check": datetime.now(),
                    }

                    # === STEP 3: Update voice channel ONLY when data changed ===
                    # Compare current state with previous to detect changes (status, player count, version)
                    # was_version was captured from prev_cache BEFORE the cache was updated above.
                    version_changed = was_version != version

                    if was_online is not None:
                        data_changed = (
                            was_online != is_online or
                            was_player_count != player_count
                        )

                        if data_changed or version_changed:
                            if was_online != is_online:
                                status_change = "OFFLINE" if not is_online else "ONLINE"
                                logger.info(f"🚨 Server {server_name} went {status_change}!")
                            if version_changed:
                                logger.info(f"🔄 Server {server_name} version changed: {was_version} → {version}")
                            
                            if rcon_port:
                                try:
                                    await self.update_voice_channel(
                                        guild_id, rcon_port, server_name, is_online, player_count, max_players, version
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to update voice channel: {e}")
                    else:
                        # First run after bot start - always update voice channel to sync with current state
                        if version_changed:
                            logger.info(f"🔄 Server {server_name} version changed (first run): {was_version} → {version}")
                        if rcon_port:
                            try:
                                await self.update_voice_channel(
                                    guild_id, rcon_port, server_name, is_online, player_count, max_players, version
                                )
                            except Exception as e:
                                logger.error(f"Failed to update voice channel on first run: {e}")
                    
                    # End all sessions if server went offline
                    if not is_online:
                        try:
                            from bot.database import players_db
                            ended = await players_db.end_all_server_sessions(guild_id, server_name)
                            if ended > 0:
                                logger.info(f"Ended {ended} sessions for {server_name}")
                            self._previous_players.pop(server_id, None)
                        except Exception as e:
                            logger.warning(f"Failed to end sessions: {e}")

                    # Player session tracking
                    if is_online:
                        try:
                            await self._track_player_sessions(guild_id, server_id, server_name, player_list)
                        except Exception as e:
                            logger.warning(f"Session tracking error: {e}")

                # === STEP 4: Update status embed for this guild ===
                try:
                    await self._update_status_embed(guild_id)
                except Exception as e:
                    logger.error(f"Failed to update status embed for guild {guild_id}: {e}")

                # === STEP 5: Process pending deliveries for this guild ===
                try:
                    await self._process_pending_deliveries(guild_id)
                except Exception as e:
                    logger.error(f"Delivery processing error for guild {guild_id}: {e}")

        except Exception as e:
            logger.error(f"Error in monitor_loop: {e}", exc_info=True)

    async def _track_player_sessions(self, guild_id: int, server_id: int, server_name: str, player_list: list):
        """Track player sessions for join/leave detection."""
        from bot.database import players_db

        current_eos_ids: Set[str] = set()
        for p in player_list:
            eos_id = (p.get("eos_id") or p.get("EOSID") or p.get("id")) if isinstance(p, dict) else None
            if eos_id:
                current_eos_ids.add(str(eos_id))
                # Update last_seen
                char_name = p.get("character_name") or p.get("name")
                try:
                    await players_db.update_player_last_seen(
                        eos_id=str(eos_id),
                        server_name=server_name,
                        character_name=char_name,
                    )
                except Exception:
                    pass

        prev_eos_ids = self._previous_players.get(server_id, set())

        # Detect joins
        for eos_id in current_eos_ids - prev_eos_ids:
            try:
                await players_db.start_player_session(guild_id, None, eos_id, None, server_name)
                logger.debug(f"Player {eos_id[:12]} joined {server_name}")
            except Exception:
                pass

        # Detect leaves
        for eos_id in prev_eos_ids - current_eos_ids:
            try:
                await players_db.end_player_session(guild_id, None, eos_id, server_name)
                logger.debug(f"Player {eos_id[:12]} left {server_name}")
            except Exception:
                pass

        self._previous_players[server_id] = current_eos_ids

    async def _update_status_embed(self, guild_id: int):
        """Update the status embed in the configured channel for a specific guild."""
        status_channel_id = await self._get_status_channel_id(guild_id)
        if not status_channel_id:
            return

        channel = self.bot.get_channel(status_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        embed = await self._create_status_embed(guild_id)
        
        # Get or initialize status message tracking for this guild
        if guild_id not in self.guild_status_messages:
            self.guild_status_messages[guild_id] = (None, 0)  # (message_id, age)
        
        message_id, message_age = self.guild_status_messages[guild_id]

        # Every 5 updates, delete and resend to refresh timestamp
        if message_age >= 5:
            if message_id:
                try:
                    old_msg = await channel.fetch_message(message_id)
                    await old_msg.delete()
                    logger.debug(f"Deleted old status message for guild {guild_id} to refresh timestamp")
                except Exception:
                    pass

            new_msg = await channel.send(embed=embed)
            self.guild_status_messages[guild_id] = (new_msg.id, 0)
            logger.debug(f"Sent new status embed for guild {guild_id}")
        else:
            if message_id:
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(embed=embed)
                    self.guild_status_messages[guild_id] = (message_id, message_age + 1)
                    logger.debug(f"Updated status embed for guild {guild_id} (age: {message_age + 1})")
                except discord.NotFound:
                    # Message deleted, send new one
                    new_msg = await channel.send(embed=embed)
                    self.guild_status_messages[guild_id] = (new_msg.id, 0)
                except Exception as e:
                    logger.error(f"Failed to edit status message for guild {guild_id}: {e}")
            else:
                new_msg = await channel.send(embed=embed)
                self.guild_status_messages[guild_id] = (new_msg.id, 0)

    async def _process_pending_deliveries(self, guild_id: int):
        """Process pending deliveries for stable online players in a specific guild."""
        # Get server cache for this guild
        server_cache = self.guild_server_caches.get(guild_id, {})
        
        current_online: Dict[str, str] = {}
        for server_name, cache in server_cache.items():
            if cache.get("online") and cache.get("players"):
                for p in cache["players"]:
                    eos_id = (p.get("eos_id") or p.get("EOSID") or p.get("id")) if isinstance(p, dict) else None
                    if eos_id:
                        current_online[str(eos_id)] = server_name

        # Reset count for players no longer online in this guild
        for key in list(self._player_consecutive_scans.keys()):
            g_id, eos_id = key
            if g_id == guild_id and eos_id not in current_online:
                del self._player_consecutive_scans[key]

        # Increment count for currently online players in this guild
        for eos_id in current_online:
            self._player_consecutive_scans[(guild_id, eos_id)] = self._player_consecutive_scans.get((guild_id, eos_id), 0) + 1

        # Fire delivery only for players stable for 3+ consecutive scans
        shop_cog = self.bot.get_cog("ShopCog")
        if shop_cog and hasattr(shop_cog, "try_deliver_for_player"):
            for eos_id, server_name in current_online.items():
                if self._player_consecutive_scans.get((guild_id, eos_id), 0) >= 3:
                    try:
                        await shop_cog.try_deliver_for_player(eos_id, server_name)
                    except Exception as de:
                        logger.error(f"Delivery error for EOS {eos_id[:12]}: {de}")

    @tasks.loop(hours=12.0)
    async def purge_inactive_loop(self):
        """Purge players not seen in the last 90 days (unlinked only)."""
        try:
            from bot.database import players_db

            for guild in self.bot.guilds:
                deleted = await players_db.purge_inactive_players(guild.id, days=90)
                if deleted:
                    logger.debug(f"Purge inactive loop: deleted={deleted} in guild {guild.id}")
        except Exception as e:
            logger.warning(f"Purge inactive loop failed: {e}")

    @purge_inactive_loop.before_loop
    async def before_purge_inactive_loop(self):
        await self.bot.wait_until_ready()

    @monitor_loop.before_loop
    async def before_monitor_loop(self):
        """Wait for bot and initialize per-guild RCON managers."""
        logger.info("before_monitor_loop: Waiting for bot to be ready...")
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)
        logger.info("before_monitor_loop: Bot is ready, initializing per-guild RCON managers...")

        # Initialize RCON manager for each guild
        for guild in self.bot.guilds:
            guild_id = guild.id
            
            # Skip if already initialized
            if guild_id in self.guild_rcon_managers:
                logger.info(f"RCON manager already initialized for guild {guild_id} ({guild.name})")
                continue
            
            # Try to load servers for this guild
            server_list = None
            for attempt in range(10):
                server_list = await self._get_server_list(guild_id)
                if server_list:
                    break
                logger.debug(f"No servers for guild {guild_id} on attempt {attempt+1}/10, waiting...")
                await asyncio.sleep(0.5)
            
            if server_list:
                logger.info(f"Initializing RCON manager for guild {guild_id} ({guild.name}) with {len(server_list)} servers")
                self.guild_rcon_managers[guild_id] = RCONManager(server_list)
                logger.info(f"✓ RCON manager ready for guild {guild_id}")
            else:
                logger.info(f"No servers configured for guild {guild_id} ({guild.name})")

        # Load existing voice channels from database for all guilds
        await self._load_voice_channels()

    async def _load_voice_channels(self):
        """Load existing voice channels from database for all guilds."""
        for guild in self.bot.guilds:
            guild_id = guild.id
            
            # Initialize voice channels dict for this guild
            if guild_id not in self.guild_voice_channels:
                self.guild_voice_channels[guild_id] = {}
            
            server_list = await self._get_server_list(guild_id)
            if not server_list:
                continue

            for server_config in server_list:
                rcon_port = server_config["rcon_port"]
                server_name = server_config["name"]

                try:
                    channel_id = await server_config_db.get_voice_channel_id(
                        guild_id, int(rcon_port)
                    )
                    if channel_id:
                        ch = guild.get_channel(int(channel_id))
                        if ch and isinstance(ch, discord.VoiceChannel):
                            self.guild_voice_channels[guild_id][rcon_port] = int(channel_id)
                            logger.info(f"✓ Linked voice channel for {server_name} in guild {guild_id}: {channel_id}")
                        else:
                            await server_config_db.clear_server_voice_channel_id(
                                guild_id, int(rcon_port)
                            )
                except Exception as e:
                    logger.error(f"Error loading voice channel for {server_name} in guild {guild_id}: {e}")

            logger.info(f"Loaded {len(self.guild_voice_channels[guild_id])} voice channels for guild {guild_id}")

    async def _create_status_embed(self, guild_id: int) -> discord.Embed:
        """Create an embed with current server status using cached data - compact 3-column format."""
        from datetime import datetime, timezone, timedelta
        
        # Get RCON manager for this guild
        rcon_manager = self.guild_rcon_managers.get(guild_id)
        if not rcon_manager or not hasattr(rcon_manager, "clients"):
            embed = discord.Embed(
                title="🖥️ Cluster Status",
                color=discord.Color.blue(),
            )
            embed.add_field(
                name="⏳ Initializing...",
                value="Server monitoring is starting up. Please wait a moment.",
                inline=False,
            )
            return embed

        # Get server list for this guild
        server_list = await self._get_server_list(guild_id)
        
        # Get server cache for this guild
        server_cache = self.guild_server_caches.get(guild_id, {})
        
        # Count total online players and survivors
        total_players = 0
        total_servers = len(server_list)
        online_players_by_server = {}
        
        for server_config in server_list:
            server_name = server_config.get("name") or "Unknown"
            cache = server_cache.get(server_name)
            
            if cache and cache.get("online", False):
                player_count = cache.get("player_count", 0)
                players = cache.get("players", [])
                total_players += player_count
                if player_count > 0:
                    online_players_by_server[server_name] = players
        
        # Create embed with compact title
        embed = discord.Embed(
            title="🖥️ Cluster Status",
            description=f"**Total Online: {total_players} Survivors across {total_servers} Servers**",
            color=discord.Color.blue(),
        )
        
        # Add servers in 3-column grid format
        for server_config in server_list:
            server_name = server_config.get("name") or "Unknown"
            max_players = server_config.get("max_players")
            cache = server_cache.get(server_name)
            
            capacity = max_players if max_players is not None else "??"
            if cache and cache.get("online", False):
                player_count = cache.get("player_count", 0)
                status_emoji = "🟢"
                value = f"{player_count}/{capacity} Players"
            else:
                status_emoji = "🔴"
                value = f"0/{capacity} Players"
            
            embed.add_field(
                name=f"{status_emoji} {server_name}",
                value=value,
                inline=True,  # 3 columns
            )
        
        # Add online players section if any
        if online_players_by_server:
            player_lines = []
            for server_name, players in online_players_by_server.items():
                player_names = [p.get("name") if isinstance(p, dict) else str(p) for p in players]
                player_lines.append(f"**{server_name}:** {', '.join(player_names)}")
            
            embed.add_field(
                name="👥 Online Players",
                value="\n".join(player_lines),
                inline=False,
            )
        
        # Footer with update info - Discord will show timestamp in user's local timezone
        embed.set_footer(text=f"Total: {total_players} Online | Updates every 60s")
        timestamp = discord.utils.utcnow()
        logger.debug(f"Setting embed timestamp to: {timestamp} (ISO: {timestamp.isoformat()}, Unix: {timestamp.timestamp()})")
        embed.timestamp = timestamp
        
        return embed

    # REMOVED: /servers command - redundant with auto-updating health status embed

    @app_commands.command(name="listplayers", description="Show all online players across servers")
    async def list_players(self, interaction: discord.Interaction):
        """List all online players across all servers."""
        await interaction.response.defer()

        if not interaction.guild_id:
            await interaction.followup.send("This command must be used in a server.")
            return

        guild_id = interaction.guild_id
        servers = {}
        total_players = 0

        # Get this guild's server cache
        guild_cache = self.guild_server_caches.get(guild_id, {})
        for server_name, cache in guild_cache.items():
            if cache.get("online") and cache.get("player_count", 0) > 0:
                players = cache.get("players", [])
                if players:
                    servers[server_name] = players
                    total_players += len(players)

        if not servers or total_players == 0:
            await interaction.followup.send("No players are currently online.")
            return

        embed = discord.Embed(
            title="👥 Online Players",
            description=f"Total: {total_players} player(s)",
            color=discord.Color.green(),
        )

        for server, players in servers.items():
            # Format player names from dict structure
            player_list = "\n".join(
                [f"• {p.get('name', p) if isinstance(p, dict) else p}" for p in players[:15]]
            )
            if len(players) > 15:
                player_list += f"\n... and {len(players) - 15} more"

            embed.add_field(name=f"🖥️ {server} ({len(players)})", value=player_list, inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="findplayer", description="Find which server a player is on")
    @app_commands.describe(character_name="The character name to search for")
    async def find_player(self, interaction: discord.Interaction, character_name: str):
        """Find which server a specific player is on."""
        await interaction.response.defer()

        server_name = await self.rcon_manager.find_player_server(character_name)

        if server_name:
            await interaction.followup.send(
                f"✅ **{character_name}** is currently playing on **{server_name}**"
            )
        else:
            await interaction.followup.send(f"❌ **{character_name}** is not online on any server.")

    async def _reload_servers_internal(self):
        """Internal method to reload servers without interaction."""
        try:
            old_count = len(self.server_list_cache) if self.server_list_cache else 0
            self.server_list_cache = None  # Clear cache to force reload

            new_list = await self._get_server_list()
            new_count = len(new_list)

            # Reinitialize RCON manager
            if new_list:
                self.rcon_manager = RCONManager(new_list)
                self.server_list_cache = new_list

            logger.info(f"Server list reloaded internally: {old_count} -> {new_count} servers")
            return True
        except Exception as e:
            logger.error(f"Failed to reload servers internally: {e}")
            return False

    @app_commands.command(
        name="reloadservers", description="🔄 Reload server list from database (admin only)"
    )
    async def reload_servers(self, interaction: discord.Interaction):
        """Reload the server list from the database."""
        # Check if user has administrator permission
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need Administrator permission to use this command.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        old_count = len(self.server_list_cache) if self.server_list_cache else 0
        success = await self._reload_servers_internal()
        new_count = len(self.server_list_cache) if self.server_list_cache else 0

        if success:
            await interaction.followup.send(
                f"✅ **Server list reloaded!**\n"
                f"Before: {old_count} servers\n"
                f"After: {new_count} servers\n\n"
                f"Voice channels will update in the next monitoring cycle (~30s).",
                ephemeral=True,
            )
            logger.info(
                f"Server list manually reloaded by {interaction.user}: {old_count} -> {new_count} servers"
            )
        else:
            await interaction.followup.send(
                "❌ Failed to reload servers. Check logs for details.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(ServerMonitor(bot))
