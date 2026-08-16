"""
System-level monitoring for ARK servers using Windows services and log file parsing.
More reliable than RCON/query protocols for local servers.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta
import subprocess

logger = logging.getLogger("SystemMonitor")


class SystemServerMonitor:
    """Monitor ARK servers using log parsing + RCON validation."""

    def __init__(self, agent_manager=None):
        self.log_paths = {}  # Map server name -> log file path
        self.log_positions = {}  # Track file position for each server
        self.active_sessions = {}  # Map server name -> set of EOS IDs currently online
        self.last_rcon_validation = {}  # Map server name -> timestamp of last RCON check
        self.agent_manager = agent_manager

    def set_agent_manager(self, agent_manager):
        """Set or update the agent manager."""
        self.agent_manager = agent_manager

    def add_server(self, server_name: str, log_path: str):
        """Register a server's log file for monitoring."""
        self.log_paths[server_name] = Path(log_path)
        self.log_positions[server_name] = 0
        self.active_sessions[server_name] = set()

    async def parse_new_log_entries(self, server_name: str) -> List[Dict]:
        """
        Parse new log entries since last check.
        Returns list of login events: [{'eos_id': str, 'ip': str, 'timestamp': datetime}, ...]
        """
        if server_name not in self.log_paths:
            return []

        log_file = self.log_paths[server_name]
        if not log_file.exists():
            logger.warning(f"Log file does not exist: {log_file}")
            return []

        try:
            current_pos = self.log_positions.get(server_name, 0)

            # Read file in a thread to avoid blocking the event loop
            new_lines, new_pos = await asyncio.to_thread(
                self._read_log_from_position, log_file, current_pos
            )
            self.log_positions[server_name] = new_pos

            # Parse login events
            logins = []
            login_pattern = re.compile(r"IP for incoming account ([0-9a-f]+) - IP ([\d.]+)")

            for line in new_lines:
                match = login_pattern.search(line)
                if match:
                    eos_id = match.group(1)
                    ip_addr = match.group(2)

                    # Extract timestamp from log line
                    # Format: [2025.12.03-18.01.52:439]
                    timestamp_match = re.match(
                        r"\[(\d{4})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2})", line
                    )
                    if timestamp_match:
                        y, m, d, h, min_val, s = map(int, timestamp_match.groups())
                        timestamp = datetime(y, m, d, h, min_val, s)
                    else:
                        timestamp = datetime.now()

                    logins.append(
                        {
                            "eos_id": eos_id,
                            "ip": ip_addr,
                            "timestamp": timestamp,
                            "server": server_name,
                        }
                    )

                    # Add to active sessions
                    self.active_sessions[server_name].add(eos_id)
                    logger.info(f"{server_name}: Player {eos_id} logged in from {ip_addr}")

            return logins

        except Exception as e:
            logger.error(f"Failed to parse log for {server_name}: {e}")
            return []

    @staticmethod
    def _read_log_from_position(log_file: Path, position: int) -> Tuple[List[str], int]:
        """Synchronous helper to read new lines from a log file. Runs in a thread."""
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(position)
            lines = f.readlines()
            new_position = f.tell()
        return lines, new_position

    async def validate_sessions_with_rcon(
        self, server_name: str, rcon_client, use_targeted_queries: bool = True
    ) -> Set[str]:
        """
        Validate active sessions using RCON.

        Args:
            server_name: Server to validate
            rcon_client: RCON client instance to use for queries
            use_targeted_queries: Ignored (kept for compatibility) - always uses ListPlayers

        Returns:
            Set of EOS IDs that are confirmed online
        """
        if server_name not in self.active_sessions:
            return set()

        current_sessions = self.active_sessions[server_name].copy()

        if not current_sessions:
            # No sessions to validate
            return set()

        # GetPlayerIDForEOSID doesn't exist in ARK Ascended - use ListPlayers only
        try:
            players = await rcon_client.get_player_list()

            if players is None:
                # All attempts returned "Keep Alive" - don't remove players
                # Trust log data since RCON is unreliable
                logger.debug(
                    f"{server_name}: RCON validation skipped (Keep Alive), keeping {len(current_sessions)} sessions"
                )
                return current_sessions

            # Extract EOS IDs from ListPlayers response
            online_eos_ids = {p["eos_id"] for p in players if "eos_id" in p}

            # Debug logging for Valguero
            if server_name == "Valguero":
                logger.info(f"🔍 Valguero validation - Current sessions: {current_sessions}")
                logger.info(f"🔍 Valguero validation - Online EOS IDs: {online_eos_ids}")
                logger.info(f"🔍 Valguero validation - Players data: {players}")

            # Remove players who are no longer online according to RCON
            for eos_id in current_sessions:
                if eos_id not in online_eos_ids:
                    self.active_sessions[server_name].discard(eos_id)
                    logger.info(
                        f"{server_name}: Player {eos_id[:8]} logged out (confirmed via ListPlayers)"
                    )

            self.last_rcon_validation[server_name] = datetime.now()
            return online_eos_ids

        except Exception as e:
            logger.error(f"{server_name}: RCON validation error: {e}")
            # On error, keep sessions to avoid false logouts
            return current_sessions

    def get_active_player_count(self, server_name: str) -> int:
        """Get current player count from active sessions."""
        if server_name not in self.active_sessions:
            return 0
        return len(self.active_sessions[server_name])

    def get_active_players(self, server_name: str) -> List[str]:
        """Get list of active EOS IDs."""
        if server_name not in self.active_sessions:
            return []
        return list(self.active_sessions[server_name])

    def should_validate_with_rcon(self, server_name: str, interval_seconds: int = 60) -> bool:
        """Check if enough time has passed since last RCON validation."""
        if server_name not in self.last_rcon_validation:
            return True

        elapsed = (datetime.now() - self.last_rcon_validation[server_name]).total_seconds()
        return elapsed >= interval_seconds
