"""
Simple async RCON client for Source engine servers (ARK).
Uses asyncio.open_connection for Windows compatibility.
"""

import asyncio
import struct
import logging
from typing import Optional

logger = logging.getLogger("SimpleRCON")


class SimpleRCONClient:
    """Lightweight async RCON client using asyncio streams."""

    SERVERDATA_AUTH = 3
    SERVERDATA_AUTH_RESPONSE = 2
    SERVERDATA_EXECCOMMAND = 2
    SERVERDATA_RESPONSE_VALUE = 0

    def __init__(self, host: str, port: int, password: str, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._request_id = 0
        self._lock = asyncio.Lock()  # Prevent concurrent use of same connection

    def _get_request_id(self) -> int:
        """Get next request ID."""
        self._request_id = (self._request_id + 1) % 10000
        return self._request_id

    def _encode_packet(self, packet_type: int, body: str) -> bytes:
        """Encode RCON packet."""
        request_id = self._get_request_id()
        body_bytes = body.encode("utf-8")
        # Size, ID, Type, Body, Two null terminators
        packet = struct.pack("<ii", request_id, packet_type)
        packet += body_bytes + b"\x00\x00"
        return struct.pack("<i", len(packet)) + packet

    async def _read_packet(self) -> tuple[int, int, bytes]:
        """Read and decode RCON packet."""
        if not self._reader:
            raise RuntimeError("Not connected")

        # Read size
        size_data = await asyncio.wait_for(self._reader.readexactly(4), timeout=self.timeout)
        size = struct.unpack("<i", size_data)[0]

        # Read packet
        packet_data = await asyncio.wait_for(self._reader.readexactly(size), timeout=self.timeout)

        request_id, packet_type = struct.unpack("<ii", packet_data[:8])
        body = packet_data[8:-2]  # Remove two null terminators

        return request_id, packet_type, body

    async def connect(self) -> bool:
        """Connect and authenticate."""
        async with self._lock:  # Protect connection establishment
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=self.timeout
                )

                # Send auth packet
                auth_packet = self._encode_packet(self.SERVERDATA_AUTH, self.password)
                self._writer.write(auth_packet)
                await self._writer.drain()

                # Read auth response
                _, response_type, _ = await self._read_packet()

                if response_type == self.SERVERDATA_AUTH_RESPONSE:
                    logger.debug(f"Connected to {self.host}:{self.port}")
                    return True
                else:
                    logger.error(
                        f"Auth failed for {self.host}:{self.port} - response type: {response_type}"
                    )
                    await self.disconnect()
                    return False

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError) as e:
                logger.debug(
                    f"Connection failed to {self.host}:{self.port}: {type(e).__name__} - {e}"
                )
                return False
            except Exception as e:
                logger.error(
                    f"Unexpected error connecting to {self.host}:{self.port}: {type(e).__name__} - {e}"
                )
                return False

    async def disconnect(self):
        """Close connection."""
        async with self._lock:  # Protect disconnect
            if self._writer:
                try:
                    self._writer.close()
                    await self._writer.wait_closed()
                except Exception:
                    pass
                finally:
                    self._writer = None
                    self._reader = None

    async def execute(self, command: str) -> Optional[str]:
        """Execute command and return response."""
        async with self._lock:  # Ensure only one operation at a time
            if not self._writer or not self._reader:
                return None

            try:
                # Drain any unsolicited packets buffered by ARK (e.g. periodic "Keep Alive" pings).
                # These arrive independently of commands and corrupt subsequent reads if not cleared.
                drained = 0
                while True:
                    try:
                        # Check for a buffered size header (4 bytes) with a very short timeout.
                        size_data = await asyncio.wait_for(
                            self._reader.readexactly(4), timeout=0.02
                        )
                        size = struct.unpack("<i", size_data)[0]
                        # Commit to reading the full body now that we have the size.
                        await asyncio.wait_for(self._reader.readexactly(size), timeout=5.0)
                        drained += 1
                    except asyncio.TimeoutError:
                        break  # No more buffered data — safe to proceed
                if drained:
                    logger.debug(f"Drained {drained} buffered RCON packet(s) before '{command[:40]}'")

                # Send command
                cmd_packet = self._encode_packet(self.SERVERDATA_EXECCOMMAND, command)
                self._writer.write(cmd_packet)
                await self._writer.drain()

                # Read response
                _, response_type, body = await self._read_packet()

                if response_type == self.SERVERDATA_RESPONSE_VALUE:
                    return body.decode("utf-8", errors="ignore")
                else:
                    logger.warning(f"Unexpected response type: {response_type}")
                    return None

            except asyncio.TimeoutError:
                logger.debug(f"Command timeout on {self.host}:{self.port}")
                await self.disconnect()
                return None
            except Exception as e:
                logger.error(f"Error executing command on {self.host}:{self.port}: {e}")
                await self.disconnect()
                return None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
