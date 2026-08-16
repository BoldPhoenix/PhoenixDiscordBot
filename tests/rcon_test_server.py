"""
Real RCON test server for integration testing.
Implements actual RCON protocol with TCP server for no-mock testing.
"""

import os
import asyncio
import struct
import logging
from typing import Tuple, Optional

logger = logging.getLogger("RCONTestServer")


class RCONTestServer:
    """Real RCON server implementation for testing."""
    
    def __init__(self):
        self.server = None
        self.port = None
        self.authenticated = False
        self.password = "test_password"
        self.responses = {
            "listplayers": "Player_1,Player_2,Player_3",
            "info": "Server Info Response",
            "status": "Online",
            "invalid": "Unknown command"
        }
    
    async def start_server(self) -> Tuple[str, int]:
        """Start RCON server on localhost:0 (OS-assigned port)."""
        self.server = await asyncio.start_server(
            self.handle_client, 
            "127.0.0.1", 
            0
        )
        
        # Get the assigned port
        socket = self.server.sockets[0]
        self.port = socket.getsockname()[1]
        
        logger.info(f"RCON test server started on 127.0.0.1:{self.port}")
        return ("127.0.0.1", self.port)
    
    async def stop_server(self):
        """Stop the RCON server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("RCON test server stopped")
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle RCON client connection."""
        try:
            self.authenticated = False
            
            while True:
                # Read RCON packet header (12 bytes: size + id + type)
                header_data = await reader.readexactly(12)
                if not header_data:
                    break
                
                # Parse header: size (4), id (4), type (4)
                size, packet_id, packet_type = struct.unpack('<iii', header_data)
                
                # Read packet body
                if size > 12:
                    body = await reader.readexactly(size - 12)
                    body = body.rstrip(b'\x00')  # Remove null terminator
                else:
                    body = b''
                
                # Process packet
                response_id, response_type, response_body = await self.process_packet(
                    packet_id, packet_type, body
                )
                
                # Send response
                await self.send_response(writer, response_id, response_type, response_body)
                
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass  # Client disconnected
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def process_packet(self, packet_id: int, packet_type: int, body: bytes) -> Tuple[int, int, bytes]:
        """Process incoming RCON packet."""
        body_str = body.decode('utf-8', errors='ignore')
        
        # Handle authentication
        if packet_type == 3:  # SERVERDATA_AUTH
            if body_str == self.password:
                self.authenticated = True
                return packet_id, 2, b''  # SERVERDATA_AUTH_RESPONSE
            else:
                return -1, 2, b''  # Authentication failed
        
        # Handle commands
        elif packet_type == 2:  # SERVERDATA_EXECCOMMAND
            if not self.authenticated:
                return -1, 2, b'Not authenticated'
            
            # Return predefined response for test commands
            response = self.responses.get(body_str.lower(), self.responses["invalid"])
            return packet_id, 0, response.encode('utf-8')
        
        # Handle other packet types
        else:
            return packet_id, 0, b'Unknown packet type'
    
    async def send_response(self, writer: asyncio.StreamWriter, response_id: int, response_type: int, body: bytes):
        """Send RCON response packet."""
        body_with_null = body + b'\x00'
        size = 12 + len(body_with_null)
        
        # Pack header
        header = struct.pack('<iii', size, response_id, response_type)
        
        # Send packet
        writer.write(header + body_with_null)
        await writer.drain()
        
        # Clean up any null files created during test
        try:
            if os.path.exists("nul"):
                os.remove("nul")
        except Exception as e:
            logger.debug(f"Failed to remove nul file: {e}")


# Fixture for pytest
async def get_rcon_test_server():
    """Create and start RCON test server for testing."""
    server = RCONTestServer()
    host, port = await server.start_server()
    
    try:
        yield server, host, port
    finally:
        await server.stop_server()
