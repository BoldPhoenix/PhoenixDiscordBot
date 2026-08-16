"""
RCON client for communicating with ARK servers.
Handles server commands, player queries, and item delivery.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from bot.rcon.simple_client import SimpleRCONClient


logger = logging.getLogger("RCONClient")


class ArkRCONClient:
    """RCON client for ARK Survival Ascended servers."""

    def __init__(self, host: str, port: int, password: str, server_name: str):
        self.host = host
        self.port = port
        self.password = password
        self.server_name = server_name
        self._client: Optional[SimpleRCONClient] = None

    async def connect(self) -> bool:
        """Establish RCON connection."""
        try:
            self._client = SimpleRCONClient(self.host, self.port, self.password, timeout=10.0)
            if await self._client.connect():
                logger.info(f"Connected to {self.server_name} ({self.host}:{self.port})")
                return True
            else:
                self._client = None
                return False
        except Exception as e:
            logger.error(f"Failed to connect to {self.server_name}: {e}")
            self._client = None
            return False

    async def disconnect(self) -> None:
        """Close RCON connection."""
        if self._client:
            try:
                await self._client.disconnect()
                logger.info(f"Disconnected from {self.server_name}")
            except Exception as e:
                logger.error(f"Error disconnecting from {self.server_name}: {e}")
            finally:
                self._client = None

    async def execute_command(self, command: str) -> Optional[str]:
        """Execute a command on the ARK server."""
        if not self._client:
            if not await self.connect():
                return None

        try:
            response = await self._client.execute(command)
            logger.debug(f"Command '{command}' response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error executing command on {self.server_name}: {e}")
            # Disconnect broken connection so next attempt will reconnect
            await self.disconnect()
            return None

    async def check_player_online(self, eos_id: str) -> bool:
        """
        Check if a specific player is online using their EOS ID.
        More reliable than ListPlayers for validation since it doesn't return 'Keep Alive'.

        Args:
            eos_id: Epic Online Services ID of the player

        Returns:
            True if player is online, False if offline or error
        """
        try:
            # GetPlayerIDForEOSID returns numeric player ID if online, error message if offline
            response = await self.execute_command(f"GetPlayerIDForEOSID {eos_id}")

            if not response:
                return False

            # Response will be a number if player is online, or error message if not
            # Example success: "12345"
            # Example failure: "Player not found" or similar
            response = response.strip()

            # If response is numeric, player is online
            if response.isdigit():
                logger.debug(
                    f"{self.server_name}: Player {eos_id[:8]} is online (player_id={response})"
                )
                return True
            else:
                logger.debug(
                    f"{self.server_name}: Player {eos_id[:8]} offline or not found: {response}"
                )
                return False

        except Exception as e:
            logger.error(f"Error checking player {eos_id[:8]} on {self.server_name}: {e}")
            await self.disconnect()
            return False

    async def get_player_list(self) -> Optional[List[Dict[str, str]]]:
        """Get list of online players with retry logic for 'Keep Alive' responses.

        Returns:
            List of players if successful
            Empty list if server confirms no players online
            None if all attempts returned 'Keep Alive' (validation should be skipped)
        """
        max_attempts = 3
        responses = []

        for attempt in range(max_attempts):
            response = await self.execute_command("ListPlayers")
            if not response:
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.3)
                    continue
                raise ConnectionError(f"Failed to connect to {self.server_name}")

            # Skip "Keep Alive" responses but continue trying
            if response.strip() == "Keep Alive":
                logger.debug(
                    f"{self.server_name}: Got 'Keep Alive' on attempt {attempt + 1}/{max_attempts}"
                )
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.3)
                    continue
                else:
                    # All attempts returned Keep Alive - return None to signal validation should be skipped
                    logger.warning(
                        f"{self.server_name}: All {max_attempts} attempts returned 'Keep Alive' - skipping validation"
                    )
                    return None

            # Got valid response
            responses.append(response)
            break

        # Use the first valid (non-Keep Alive) response
        if not responses:
            return []

        response = responses[0]

        # Debug logging for Aberration and Valguero
        if self.server_name in ["Aberration", "Valguero"]:
            logger.info(
                f"🔍 {self.server_name} ListPlayers RAW response: '{response}' (length={len(response)})"
            )

        players = []
        lines = response.strip().split("\n")

        for line in lines:
            if "," in line:
                try:
                    # Format: "0. PlayerName, EOSID" where 0 is the specimen ID
                    parts = line.split(",")
                    if len(parts) >= 2:
                        # Extract specimen ID and player name from "0. PlayerName"
                        player_name_raw = parts[0].strip()
                        specimen_id = None

                        if ". " in player_name_raw:
                            # Split "0. BoldPhoenix" into specimen_id=0 and name="BoldPhoenix"
                            id_part, player_name = player_name_raw.split(". ", 1)
                            try:
                                specimen_id = id_part.strip()
                            except ValueError:
                                player_name = player_name_raw
                        else:
                            player_name = player_name_raw

                        eos_id = parts[1].strip()
                        player_dict = {
                            "name": player_name,
                            "steam_id": eos_id,
                            "eos_id": eos_id,
                            "server": self.server_name,
                        }
                        if specimen_id:
                            player_dict["specimen_id"] = specimen_id
                        players.append(player_dict)
                except Exception as e:
                    logger.warning(f"Failed to parse player line '{line}': {e}")

        return players

    async def get_player_id_by_steam_id(self, steam_id: str) -> Optional[int]:
        """Get player's in-game ID from Steam ID."""
        players = await self.get_player_list()
        if not players:
            return None
        for idx, player in enumerate(players):
            if player.get("steam_id") == steam_id:
                return idx  # In ARK, player ID is often the list index
        return None

    async def get_player_id_by_name(self, player_name: str) -> Optional[int]:
        """Get player's in-game ID from character name."""
        players = await self.get_player_list()
        if not players:
            return None
        for idx, player in enumerate(players):
            if (player.get("name") or "").lower() == player_name.lower():
                return idx
        return None

    async def give_item_to_player(
        self, player_identifier: str, ark_command: str
    ) -> tuple[bool, str]:
        """
        Give an item to a player.

        Args:
            player_identifier: Steam ID or character name
            ark_command: ARK console command with {player_id} placeholder

        Returns:
            Tuple of (success, message)
        """
        # Try to find player by Steam ID first, then by name
        player_id = None
        if player_identifier.isdigit():
            player_id = await self.get_player_id_by_steam_id(player_identifier)

        if player_id is None:
            player_id = await self.get_player_id_by_name(player_identifier)

        if player_id is None:
            return (
                False,
                f"Player '{player_identifier}' not found on {self.server_name}. Make sure they are online.",
            )

        # Replace placeholder with actual player ID
        command = ark_command.replace("{player_id}", str(player_id))

        # Execute the command
        response = await self.execute_command(command)

        if response is not None:
            return True, f"Item delivered to player on {self.server_name}"
        else:
            return False, f"Failed to deliver item on {self.server_name}"

    async def broadcast_message(self, message: str) -> bool:
        """Broadcast a message to all players on the server."""
        command = f"ServerChat {message}"
        response = await self.execute_command(command)
        return response is not None

    async def get_chat(self) -> List[str]:
        """Get recent chat messages (if supported by server)."""
        response = await self.execute_command("GetChat")
        if response:
            return response.strip().split("\n")
        return []

    async def save_world(self) -> bool:
        """Force a world save."""
        response = await self.execute_command("SaveWorld")
        return response is not None

    async def get_server_info(self) -> Dict[str, Any]:
        """Get basic server information."""
        players = await self.get_player_list()
        return {
            "name": self.server_name,
            "host": self.host,
            "port": self.port,
            "online": self._client is not None,
            "player_count": len(players),
            "players": players,
        }


class RCONManager:
    """Manages multiple RCON connections to ARK servers."""

    def __init__(self, server_configs: List[Dict[str, Any]]):
        self.clients: Dict[str, ArkRCONClient] = {}

        for config in server_configs:
            name = config.get("name")
            host = config.get("rcon_host") or config.get(
                "host"
            )  # Try rcon_host first, fallback to host
            port = config.get("rcon_port")
            password = config.get("rcon_password")

            if all([name, host, port, password]):
                self.clients[name] = ArkRCONClient(host, port, password, name)
                logger.debug(f"RCONManager: Created RCON client for {name}")
            else:
                logger.warning(f"Invalid server config: {name or 'unknown'} - "
                              f"name={name}, host={host}, port={port}, password={'***' if password else 'MISSING'}")
        
        logger.info(f"RCONManager initialized with {len(self.clients)} RCON clients: {list(self.clients.keys())}")

    def get_client(self, server_name: str) -> Optional[ArkRCONClient]:
        """Get RCON client for a specific server."""
        return self.clients.get(server_name)

    async def get_all_players(self) -> List[Dict[str, str]]:
        """Get players from all servers."""
        all_players = []

        for server_name, client in self.clients.items():
            try:
                players = await client.get_player_list()
                all_players.extend(players)
            except Exception as e:
                logger.error(f"Error getting players from {server_name}: {e}")

        return all_players

    async def broadcast_to_all(self, message: str) -> int:
        """Broadcast message to all servers. Returns number of successful broadcasts."""
        success_count = 0

        for server_name, client in self.clients.items():
            try:
                if await client.broadcast_message(message):
                    success_count += 1
            except Exception as e:
                logger.error(f"Error broadcasting to {server_name}: {e}")

        return success_count

    async def find_player_server(self, player_identifier: str) -> Optional[str]:
        """Find which server a player is on by name or Steam ID."""
        for server_name, client in self.clients.items():
            try:
                players = await client.get_player_list()
                for player in players:
                    if (
                        player.get("name", "").lower() == player_identifier.lower()
                        or player.get("steam_id") == player_identifier
                    ):
                        return server_name
            except Exception as e:
                logger.debug(f"Error checking {server_name} for player: {e}")

        return None

    async def execute_command(self, server_name: str, command: str) -> tuple:
        """Execute a command on a specific server.

        Args:
            server_name: Name of the server to execute on
            command: RCON command to execute

        Returns:
            Tuple of (success: bool, response: str)
        """
        client = self.get_client(server_name)
        if not client:
            return (False, f"Server '{server_name}' not found")

        try:
            response = await client.execute_command(command)
            # None means connection failure, empty string is valid success
            if response is None:
                return (False, "Failed to connect to server")
            else:
                # Return success with response (even if empty string)
                return (True, response if response else "Command executed successfully")
        except Exception as e:
            logger.error(f"Error executing command on {server_name}: {e}")
            return (False, str(e))
