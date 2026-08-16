"""
Steam Query (A2S) client for reliable player list retrieval.
More reliable than RCON ListPlayers command.
"""

import a2s
import asyncio
import logging
from typing import List, Dict, Optional

logger = logging.getLogger("SteamQuery")


class SteamQueryClient:
    """Wrapper for Steam A2S queries to ARK servers."""

    def __init__(self, host: str, query_port: int, server_name: str):
        """
        Initialize Steam Query client.

        Args:
            host: Server IP address
            query_port: Steam query port (usually game_port + 1)
            server_name: Friendly server name for logging
        """
        self.host = host
        self.query_port = query_port
        self.server_name = server_name
        self.address = (host, query_port)

    async def get_players(self, timeout: float = 3.0) -> List[Dict[str, any]]:
        """
        Query server for player list using Steam A2S_PLAYER protocol.

        Returns:
            List of dicts with 'name', 'score', 'duration' keys
            Empty list if query fails or no players online
        """
        try:
            # A2S queries are blocking, run in executor
            loop = asyncio.get_event_loop()
            players_raw = await loop.run_in_executor(
                None, lambda: a2s.players(self.address, timeout=timeout)
            )

            # Convert to our standard format
            players = []
            for p in players_raw:
                players.append(
                    {
                        "name": p.name,
                        "score": p.score,
                        "duration": p.duration,  # seconds online
                        "server": self.server_name,
                    }
                )

            logger.debug(f"{self.server_name} Steam Query: {len(players)} players")
            return players

        except asyncio.TimeoutError:
            logger.warning(f"{self.server_name}: Steam query timeout")
            return []
        except Exception as e:
            logger.error(f"{self.server_name}: Steam query error: {e}")
            return []

    async def get_info(self, timeout: float = 3.0) -> Optional[Dict[str, any]]:
        """
        Query server info (name, map, player count, max players).

        Returns:
            Dict with server info or None if query fails
        """
        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, lambda: a2s.info(self.address, timeout=timeout))

            return {
                "server_name": info.server_name,
                "map": info.map_name,
                "players": info.player_count,
                "max_players": info.max_players,
                "server_type": info.server_type,
                "platform": info.platform,
            }

        except Exception as e:
            logger.error(f"{self.server_name}: Steam info query error: {e}")
            return None


class SteamQueryManager:
    """Manages Steam Query clients for multiple servers."""

    def __init__(self):
        self.clients: Dict[str, SteamQueryClient] = {}

    def add_server(self, server_name: str, host: str, query_port: int):
        """Register a server for Steam queries."""
        self.clients[server_name] = SteamQueryClient(host, query_port, server_name)
        logger.info(f"Registered Steam Query for {server_name} at {host}:{query_port}")

    async def get_all_players(self) -> Dict[str, List[Dict[str, any]]]:
        """
        Query all registered servers for players.

        Returns:
            Dict mapping server_name -> list of player dicts
        """
        results = {}
        tasks = []
        server_names = []

        for server_name, client in self.clients.items():
            tasks.append(client.get_players())
            server_names.append(server_name)

        if tasks:
            player_lists = await asyncio.gather(*tasks, return_exceptions=True)

            for server_name, players in zip(server_names, player_lists):
                if isinstance(players, Exception):
                    logger.error(f"{server_name}: Steam query exception: {players}")
                    results[server_name] = []
                else:
                    results[server_name] = players

        return results

    async def get_total_players(self) -> int:
        """Get total player count across all servers."""
        all_players = await self.get_all_players()
        return sum(len(players) for players in all_players.values())
