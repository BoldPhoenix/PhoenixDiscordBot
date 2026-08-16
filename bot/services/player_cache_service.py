"""
Player Cache Service - Background task to keep player database fresh.
Scans RCON and save files, caches player data, auto-links Discord accounts.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from bot.database import players_db, server_config_db
from bot.rcon.client import RCONManager
from bot.asa_parser_adapter import get_all_players_from_cluster
from bot.utils.config import Config

logger = logging.getLogger("PlayerCacheService")


class PlayerCacheService:
    """Service to maintain fresh player cache from RCON and save files."""

    def __init__(self, bot, rcon_manager: RCONManager = None):
        self.bot = bot
        self.rcon_manager = rcon_manager
        self.is_running = False
        self.scan_interval = 1800  # 30 minutes

    async def start(self):
        """Start the player cache background task."""
        if self.is_running:
            logger.warning("Player cache service already running")
            return

        self.is_running = True
        logger.info("Starting player cache service...")

        # Run initial scan after a short delay
        await asyncio.sleep(60)  # Wait 1 minute after bot startup

        while self.is_running:
            try:
                await self.scan_and_cache_players()
            except Exception as e:
                logger.error(f"Error in player cache scan: {e}", exc_info=True)

            # Wait for next scan interval
            await asyncio.sleep(self.scan_interval)

    def stop(self):
        """Stop the player cache background task."""
        self.is_running = False
        logger.info("Stopped player cache service")

    async def scan_and_cache_players(self):
        """Main scan logic: RCON + save files + auto-link + cleanup."""
        logger.info("Starting player cache scan...")
        start_time = datetime.utcnow()

        stats = {
            "rcon_players": 0,
            "save_players": 0,
            "cached_total": 0,
            "auto_linked": 0,
            "purged": 0,
        }

        try:
            # Step 1: Scan RCON for currently online players
            stats["rcon_players"] = await self._scan_rcon_players()

            # Step 2: Scan save files for all players in cluster
            stats["save_players"] = await self._scan_save_files()

            # Step 3: Auto-link players to Discord accounts
            stats["auto_linked"] = await self._auto_link_players()

            # Step 4: Purge old inactive players (90+ days)
            stats["purged"] = await players_db.purge_old_players(days_threshold=90)

            # Get total cached players
            cached = await players_db.get_cached_players(days_since_seen=90)
            stats["cached_total"] = len(cached)

            elapsed = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"Player cache scan completed in {elapsed:.1f}s: "
                f"{stats['rcon_players']} online, "
                f"{stats['save_players']} from saves, "
                f"{stats['auto_linked']} auto-linked, "
                f"{stats['purged']} purged, "
                f"{stats['cached_total']} total cached"
            )

        except Exception as e:
            logger.error(f"Error in scan_and_cache_players: {e}", exc_info=True)

    async def _scan_rcon_players(self) -> int:
        """Scan all servers via RCON for online players."""
        count = 0

        try:
            if not self.rcon_manager:
                logger.debug("No RCON manager available, skipping RCON scan")
                return 0

            # Get the main guild (first guild bot is in)
            if not self.bot.guilds:
                logger.debug("Bot not in any guilds, skipping RCON scan")
                return 0

            guild = self.bot.guilds[0]  # Use first guild

            # Get all configured servers for this guild
            all_servers = await server_config_db.get_ark_servers(guild.id)
            # Filter to only enabled servers
            servers = [s for s in all_servers if s.get("enabled", True)]

            for server in servers:
                try:
                    server_name = server.get("name")
                    if not server_name:
                        continue

                    # Get online players via RCON
                    client = self.rcon_manager.get_client(server_name)
                    if not client:
                        continue

                    players = await client.get_player_list()

                    for player in players:
                        # Cache player with available info from RCON
                        # Note: RCON doesn't give EOS ID directly, but ListPlayers
                        # format varies by server. We'll do our best.
                        player_name = player.get("name", "")

                        if player_name:
                            # Try to find this player in our cache by name
                            existing = await players_db.search_players_by_name(
                                player_name, days_since_seen=365
                            )

                            if existing:
                                # Update their last seen
                                for p in existing:
                                    if p.get("eos_id"):
                                        await players_db.cache_player(
                                            eos_id=p["eos_id"],
                                            character_name=player_name,
                                            last_server=server_name,
                                        )
                                        count += 1
                                        break

                except Exception as e:
                    logger.debug(f"Error scanning RCON for {server.get('name')}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in _scan_rcon_players: {e}")

        return count

    async def _scan_save_files(self) -> int:
        """Scan cluster save files for all players."""
        count = 0

        try:
            # Check if cluster root is configured
            cluster_root = getattr(Config, "CLUSTER_ROOT", None)
            if not cluster_root:
                logger.debug("CLUSTER_ROOT not configured, skipping save file scan")
                return 0

            cluster_path = Path(cluster_root)
            if not cluster_path.exists():
                logger.debug(f"Cluster path does not exist: {cluster_path}")
                return 0

            # Get all players from cluster save files
            players = await get_all_players_from_cluster(cluster_path)

            for player in players:
                if not player.eos_id:
                    continue

                # Cache this player
                await players_db.cache_player(
                    eos_id=player.eos_id,
                    character_name=player.character_name,
                    player_name=player.player_name,
                    level=player.level,
                    last_server=self._extract_server_name(player.file_path),
                )
                count += 1

        except Exception as e:
            logger.error(f"Error in _scan_save_files: {e}")

        return count

    async def _auto_link_players(self) -> int:
        """Auto-link players to Discord accounts based on name matching."""
        count = 0

        try:
            # Get the main guild (first guild bot is in)
            if not self.bot.guilds:
                logger.debug("Bot not in any guilds, skipping auto-link")
                return 0

            guild = self.bot.guilds[0]  # Use first guild

            # Auto-link players
            linked = await players_db.auto_link_by_name(guild, days_since_seen=90)
            count = len(linked)

        except Exception as e:
            logger.error(f"Error in _auto_link_players: {e}")

        return count

    @staticmethod
    def _extract_server_name(file_path: str) -> str:
        """Extract server name from file path."""
        try:
            path = Path(file_path)
            # Typically: /path/to/server_name/.../SavedArks/MapName_WP/...
            parts = path.parts
            for i, part in enumerate(parts):
                if "SavedArks" in part and i > 0:
                    return parts[i - 1]
            return path.parts[-3] if len(path.parts) >= 3 else "Unknown"
        except:
            return "Unknown"
