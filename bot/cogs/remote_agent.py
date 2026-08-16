"""
Remote Agent Manager - Manages WebSocket connections to ARK server agents.

Provides:
- WebSocket connection management with auto-reconnect
- Request-response correlation (send command, await result)
- Background response listener
- Shared instance accessible via bot.agent_manager
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import json
import websockets
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime
from bot.database import remote_agent_db

logger = logging.getLogger("RemoteAgent")


class RemoteAgentManager:
    """Manages connections to remote ARK server agents with response handling."""

    def __init__(self):
        self.agents: Dict[str, Dict] = {}  # agent_id -> agent_info
        self.connections: Dict[str, Any] = {}  # agent_id -> websocket
        self._listeners: Dict[str, asyncio.Task] = {}  # agent_id -> recv task
        self._pending: Dict[str, asyncio.Future] = {}  # request_id -> future
        self._reconnect_tasks: Dict[str, asyncio.Task] = {}
        self.bot = None  # Set by set_bot() for progress logging

    @staticmethod
    def _log_task_exception(task: asyncio.Task) -> None:
        """Done-callback that logs unhandled exceptions from fire-and-forget tasks."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(f"Unhandled exception in background task {task.get_name()}: {exc}")

    def set_bot(self, bot):
        """Set bot reference for progress logging to Discord channels."""
        self.bot = bot

    async def _log_progress_to_channel(self, agent_id: str, progress: int, status: str):
        """Log progress message to the guild's server log channel."""
        if not self.bot:
            logger.warning("Cannot log progress - bot reference not set")
            return
        try:
            agent_info = self.agents.get(agent_id)
            if not agent_info:
                logger.debug(f"Cannot log progress - no agent info for {agent_id}")
                return
            guild_id = agent_info.get("guild_id")
            if not guild_id:
                logger.debug(f"Cannot log progress - no guild_id for agent {agent_id}")
                return
            
            # Get log channel from config
            from bot.database import server_config_db
            config = await server_config_db.get_server_config(guild_id)
            if not config:
                logger.debug(f"Cannot log progress - no config for guild {guild_id}")
                return
            channel_id = config.get("server_log_channel_id")
            if not channel_id:
                logger.debug(f"Cannot log progress - no server_log_channel_id for guild {guild_id}")
                return
            
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await channel.send(f"📋 {progress}% — {status}")
                logger.info(f"Logged progress to channel {channel_id}: {progress}% - {status}")
            else:
                logger.warning(f"Cannot log progress - channel {channel_id} not found")
        except Exception as e:
            logger.warning(f"Could not log progress to channel: {e}")

    async def register_agent(self, guild_id: int, agent_ip: str, agent_port: int, auth_key: str):
        """Register and connect to a remote agent."""
        agent_id = f"{agent_ip}:{agent_port}"

        # Check subscription tier and enforce limits
        from bot.database import subscription_db
        
        sub = await subscription_db.get_or_create_subscription(guild_id)
        tier = subscription_db.get_effective_tier(sub)
        
        # Free tier: limit to 1 agent
        if tier == "free":
            existing_agents = await remote_agent_db.get_remote_agents(guild_id)
            if len(existing_agents) >= 1:
                logger.warning(f"Free tier agent limit reached for guild {guild_id}")
                return False, "❌ **Free tier limit:** You can only register **1 remote agent**.\n\n💎 Upgrade to **Premium** for unlimited agents and servers!\nUse `/subscribe` to upgrade."
        
        # Check if auth_key is already bound to a different guild
        is_bound, bound_guild_id = await remote_agent_db.check_auth_key_guild_binding(auth_key)
        if is_bound and bound_guild_id != guild_id:
            logger.warning(f"Auth key already bound to guild {bound_guild_id}, rejecting registration for guild {guild_id}")
            return False, f"❌ This remote agent is already registered to another Discord server. Each agent can only be used by one server."

        try:
            uri = f"ws://{agent_ip}:{agent_port}/ws?auth_key={auth_key}"
            logger.info(f"Connecting to agent: ws://{agent_ip}:{agent_port}/ws (guild {guild_id}, tier: {tier})")
            websocket = await asyncio.wait_for(
                websockets.connect(uri, ping_interval=30, ping_timeout=10),
                timeout=10,
            )
            logger.info(f"WebSocket connected to {agent_id}")

            # Save to database (binds auth_key to this guild permanently)
            db_success = await remote_agent_db.create_remote_agent(guild_id, agent_id, agent_ip, agent_port, auth_key)
            if not db_success:
                return False, "Failed to save agent to database"

            self.agents[agent_id] = {
                "guild_id": guild_id,
                "ip": agent_ip,
                "port": agent_port,
                "auth_key": auth_key,
                "connected_at": datetime.now(),
            }
            self.connections[agent_id] = websocket

            await remote_agent_db.update_agent_connection(agent_id, connected=True)

            # Start background listener for this connection
            self._start_listener(agent_id)
            
            # Auto-import INI files for all servers on this agent
            task = asyncio.create_task(self._auto_import_ini_files(agent_id, guild_id))
            task.add_done_callback(self._log_task_exception)

            return True, f"Agent {agent_id} connected successfully"

        except asyncio.TimeoutError:
            logger.error(f"Connection timeout to agent {agent_id}")
            return False, "Connection timed out (10s)"
        except Exception as e:
            logger.error(f"Failed to connect to agent {agent_id}: {e}")
            return False, f"Failed to connect: {str(e)}"

    def _start_listener(self, agent_id: str):
        """Start a background task to listen for responses from the agent."""
        # Cancel existing listener if any
        if agent_id in self._listeners and not self._listeners[agent_id].done():
            self._listeners[agent_id].cancel()
        task = asyncio.create_task(self._recv_loop(agent_id))
        task.add_done_callback(self._log_task_exception)
        self._listeners[agent_id] = task

    async def _recv_loop(self, agent_id: str):
        """Background loop that receives and dispatches agent responses."""
        ws = self.connections.get(agent_id)
        if not ws:
            return

        try:
            async for message in ws:
                try:
                    data = json.loads(message)
                    resp_type = data.get("type", "")
                    request_id = data.get("request_id", "")

                    logger.debug(f"Agent {agent_id} -> type={resp_type} req={request_id}")

                    # Resolve pending future if one exists for this request_id
                    if request_id and request_id in self._pending:
                        future = self._pending[request_id]
                        if not future.done():
                            # List of response types that resolve futures
                            valid_response_types = (
                                "complete", "status", "servers", "logs", "error",
                                "list_server_services", "create_server_service",
                                "update_server_config", "read_server_config",
                                "delete_server_service", "start_ark_service",
                                "stop_ark_service", "restart_ark_service",
                                "get_ark_service_status"
                            )
                            if resp_type in valid_response_types:
                                future.set_result(data)
                                del self._pending[request_id]
                                # Side-effect: auto-update map_name from discover/status
                                if resp_type in ("servers", "status"):
                                    t = asyncio.create_task(
                                        self._auto_update_map_names(agent_id, resp_type, data)
                                    )
                                    t.add_done_callback(self._log_task_exception)
                            elif resp_type == "progress":
                                # Don't resolve yet — progress is intermediate
                                status = data.get('status', '')
                                progress_pct = data.get('progress', 0)
                                logger.info(f"Progress {progress_pct}%: {status}")
                                # Log to Discord channel if bot is available
                                await self._log_progress_to_channel(agent_id, progress_pct, status)
                    elif resp_type == "connected":
                        logger.info(f"Agent {agent_id} confirmed connection: {data.get('data')}")
                    elif resp_type == "ark_version_update":
                        # Handle ARK version update from agent
                        await self._handle_ark_version_update(data)
                    elif resp_type == "server_config_request":
                        # Handle server configuration request from agent
                        await self._handle_server_config_request(agent_id, data)

                except json.JSONDecodeError:
                    logger.warning(f"Non-JSON message from {agent_id}: {message[:100]}")
                except Exception as e:
                    logger.error(f"Error processing message from {agent_id}: {e}")

        except websockets.ConnectionClosed as e:
            logger.warning(f"Agent {agent_id} connection closed: {e}")
        except Exception as e:
            logger.error(f"Agent {agent_id} recv loop error: {e}")
        finally:
            # Connection lost — mark disconnected and schedule reconnect
            logger.info(f"Agent {agent_id} recv loop ended, scheduling reconnect")
            self.connections.pop(agent_id, None)
            # Update DB so the GUI shows the correct disconnected state
            try:
                await remote_agent_db.update_agent_connection(agent_id, connected=False)
            except Exception:
                pass
            # Fail any pending futures and clear the dict to prevent leak
            for req_id, future in list(self._pending.items()):
                if not future.done():
                    future.set_exception(ConnectionError(f"Agent {agent_id} disconnected"))
            self._pending.clear()
            self._schedule_reconnect(agent_id)

    def _schedule_reconnect(self, agent_id: str):
        """Schedule an auto-reconnect attempt."""
        if agent_id in self._reconnect_tasks and not self._reconnect_tasks[agent_id].done():
            return  # Already reconnecting
        if agent_id not in self.agents:
            return  # Agent was removed, don't reconnect
        task = asyncio.create_task(self._reconnect_loop(agent_id))
        task.add_done_callback(self._log_task_exception)
        self._reconnect_tasks[agent_id] = task

    async def _handle_ark_version_update(self, data: dict):
        """Handle ARK version update from remote agent."""
        try:
            server_name = data.get("data", {}).get("server_name")
            ark_version = data.get("data", {}).get("ark_version")

            if not server_name or not ark_version:
                logger.warning(f"Invalid ARK version update data: {data}")
                return

            logger.info(f"Received ARK version update for {server_name}: {ark_version}")

            # Update database with new version - need to find server across all guilds
            from bot.database import server_config_db

            # Get all guilds and search for the server
            guild_ids = await server_config_db.get_all_guild_ids()

            for guild_id in guild_ids:
                servers = await server_config_db.get_ark_servers(guild_id)
                for server in servers:
                    if server.get("name") == server_name:
                        await server_config_db.update_ark_server(
                            server["id"],
                            ark_version=ark_version
                        )
                        logger.info(f"Updated ARK version in database for {server_name} (guild {guild_id}): {ark_version}")
                        
                        # Trigger immediate voice channel update with new version
                        server_monitor = self.bot.get_cog("ServerMonitor")
                        if server_monitor:
                            cache = server_monitor.guild_server_caches.get(guild_id, {}).get(server_name, {})
                            is_online = cache.get("online", False)
                            player_count = cache.get("player_count", 0)
                            max_players = server.get("max_players", 70)
                            rcon_port = server.get("rcon_port")

                            if rcon_port:
                                await server_monitor.update_voice_channel(
                                    guild_id, rcon_port, server_name, is_online, player_count, max_players, ark_version
                                )
                                logger.info(f"Triggered voice channel update for {server_name} with version {ark_version}")
                        return

            logger.warning(f"Server {server_name} not found in any guild database")

        except Exception as e:
            logger.error(f"Error handling ARK version update: {e}")

    async def push_server_config(self, guild_id: int):
        """Push the guild's current server list to every CONNECTED agent of that guild.

        Called after ark-server add/edit/remove: the agent only refreshed its
        in-memory server list on connect/startup, so servers added while it was
        connected were invisible to maintain_server ("Server 'X' not found in
        config" — field bug 2026-07-03, new Genesis map server).
        """
        pushed = 0
        for agent_id, info in list(self.agents.items()):
            if info.get("guild_id") != guild_id:
                continue
            if agent_id not in self.connections:
                continue
            await self._handle_server_config_request(agent_id, {})
            pushed += 1
        logger.info(f"push_server_config: pushed to {pushed} agent(s) for guild {guild_id}")

    async def _handle_server_config_request(self, agent_id: str, data: dict):
        """Handle server configuration request from remote agent."""
        try:
            logger.info(f"Agent {agent_id} requesting server configuration")

            # Get the guild_id from the agent's stored info
            agent_info = self.agents.get(agent_id)
            if not agent_info:
                logger.warning(f"No agent info found for {agent_id}, trying database lookup")
                # Try to look up from database
                from bot.database import remote_agent_db
                agents = await remote_agent_db.get_all_remote_agents()
                for agent in agents:
                    if agent.get("agent_id") == agent_id:
                        guild_id = agent.get("guild_id")
                        if guild_id:
                            self.agents[agent_id] = {"guild_id": guild_id}
                            break
                agent_info = self.agents.get(agent_id)
                if not agent_info:
                    logger.warning(f"No agent info found for {agent_id} in database either")
                    return

            guild_id = agent_info.get("guild_id")
            if not guild_id:
                logger.warning(f"No guild_id for agent {agent_id}")
                return

            # Get servers from database for this guild
            from bot.database import server_config_db
            servers = await server_config_db.get_ark_servers(guild_id)
            
            # Convert server data to agent format
            agent_servers = []
            for server in servers:
                agent_server = {
                    "name": server.get("name"),
                    "service_name": server.get("service_name"),
                    "install_path": server.get("server_path"),
                    "steamcmd_path": server.get("steamcmd_path"),
                    "rcon_port": server.get("rcon_port"),
                    "rcon_password": server.get("rcon_password"),
                    "log_path": server.get("log_path")
                }
                agent_servers.append(agent_server)
            
            # Send configure_servers command to agent
            command = {
                "type": "configure_servers",
                "params": agent_servers,
                "request_id": f"config_{int(time.time())}"
            }
            
            # Send command to agent
            ws = self.connections.get(agent_id)
            if ws:
                await ws.send(json.dumps(command))
                logger.info(f"Sent server configuration to agent {agent_id}: {len(agent_servers)} servers")
            else:
                logger.warning(f"No WebSocket connection for agent {agent_id}")
                
        except Exception as e:
            logger.error(f"Error handling server config request: {e}")

    async def _auto_update_map_names(self, agent_id: str, resp_type: str, data: dict):
        """Auto-update map_name in DB when discover_servers or get_status returns it."""
        try:
            agent_info = self.agents.get(agent_id)
            if not agent_info:
                return
            guild_id = agent_info.get("guild_id")
            if not guild_id:
                return

            from bot.database import server_config_db

            if resp_type == "servers":
                # discover_servers response: data["data"] is a list of server dicts
                servers_list = data.get("data", [])
                if not isinstance(servers_list, list):
                    return
                for srv in servers_list:
                    if not isinstance(srv, dict):
                        continue
                    map_name = srv.get("map_name")
                    rcon_port = srv.get("rcon_port")
                    if map_name and rcon_port:
                        await server_config_db.update_ark_server_by_port(
                            guild_id, rcon_port, map_name=map_name
                        )
                        logger.info(f"Auto-updated map_name={map_name} for port {rcon_port} (guild {guild_id})")

            elif resp_type == "status":
                # get_status response: data["data"] is a single server status dict
                status_data = data.get("data", {})
                if not isinstance(status_data, dict):
                    return
                map_name = status_data.get("map_name")
                rcon_port = status_data.get("rcon_port")
                if map_name and rcon_port:
                    await server_config_db.update_ark_server_by_port(
                        guild_id, rcon_port, map_name=map_name
                    )
                    logger.info(f"Auto-updated map_name={map_name} for port {rcon_port} (guild {guild_id})")

        except Exception as e:
            logger.error(f"Error auto-updating map_names: {e}")

    async def _reconnect_loop(self, agent_id: str):
        """Try to reconnect to an agent with exponential backoff."""
        delay = 5
        max_delay = 300  # 5 minutes max

        logger.info(f"Starting reconnect loop for {agent_id}")
        
        while agent_id in self.agents and agent_id not in self.connections:
            logger.info(f"Reconnecting to {agent_id} in {delay}s...")
            await asyncio.sleep(delay)

            info = self.agents.get(agent_id)
            if not info:
                logger.warning(f"No agent info found for {agent_id}, breaking reconnect loop")
                break

            try:
                uri = f"ws://{info['ip']}:{info['port']}/ws?auth_key={info['auth_key']}"
                logger.info(f"Attempting connection to ws://{info['ip']}:{info['port']}/ws")
                ws = await asyncio.wait_for(
                    websockets.connect(uri, ping_interval=30, ping_timeout=10),
                    timeout=10,
                )
                self.connections[agent_id] = ws
                self._start_listener(agent_id)
                await remote_agent_db.update_agent_connection(agent_id, connected=True)
                logger.info(f"✅ Successfully reconnected to agent {agent_id}")

                # Auto-import INI files
                guild_id = info.get("guild_id")
                if guild_id:
                    t = asyncio.create_task(self._auto_import_ini_files(agent_id, guild_id))
                    t.add_done_callback(self._log_task_exception)

                # Proactively push server config to agent on connect
                try:
                    await self._handle_server_config_request(agent_id, {})
                except Exception as e:
                    logger.warning(f"Failed to push server config to {agent_id}: {e}")
                break  # Exit loop on successful connection

            except Exception as e:
                logger.error(f"Failed to connect to {agent_id}: {e}")
                delay = min(delay * 2, max_delay)  # Exponential backoff

    async def send_command(
        self,
        agent_id: str,
        command_type: str,
        server_name: str = "",
        params: Dict = None,
        timeout: float = 120.0,
    ) -> Dict[str, Any]:
        """Send a command and wait for the response.

        Returns the response dict from the agent, or raises on error/timeout.
        """
        if agent_id not in self.connections:
            raise ConnectionError(f"Agent {agent_id} not connected")

        # Free tier can now use their 1 allowed remote agent
        # No tier restrictions on agent commands
        
        ws = self.connections[agent_id]
        request_id = f"{command_type}_{datetime.now().timestamp()}"

        command = {
            "type": command_type,
            "request_id": request_id,
            "server": server_name,
            "params": params or {},
        }

        # Create a future for the response
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending[request_id] = future

        try:
            await ws.send(json.dumps(command))
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise TimeoutError(f"Command {command_type} timed out after {timeout}s")
        except Exception:
            self._pending.pop(request_id, None)
            raise

    async def send_command_fire_and_forget(
        self, agent_id: str, command_type: str, server_name: str, params: Dict = None
    ) -> bool:
        """Send a command without waiting for response. Returns True if sent."""
        if agent_id not in self.connections:
            return False

        ws = self.connections[agent_id]
        command = {
            "type": command_type,
            "request_id": f"{command_type}_{datetime.now().timestamp()}",
            "server": server_name,
            "params": params or {},
        }

        try:
            await ws.send(json.dumps(command))
            return True
        except Exception as e:
            logger.error(f"Failed to send command to {agent_id}: {e}")
            return False

    async def get_agent_status(self, agent_id: str) -> Optional[Dict]:
        """Get in-memory agent info."""
        info = self.agents.get(agent_id)
        if info:
            info["connected"] = agent_id in self.connections
        return info

    async def get_connected_agent_for_guild(self, guild_id: int) -> Optional[str]:
        """Get the first connected agent_id for a guild."""
        target = int(guild_id)
        for agent_id, info in self.agents.items():
            stored = info.get("guild_id")
            if stored is not None and int(stored) == target and agent_id in self.connections:
                return agent_id
        return None

    async def get_mods(self, agent_id: str, server_name: str) -> Dict[str, Any]:
        """Get active mod IDs for a server from the remote agent."""
        return await self.send_command(agent_id, "get_mods", server_name)

    async def set_mods(self, agent_id: str, server_name: str, mod_ids: list) -> Dict[str, Any]:
        """Set active mod IDs for a server via the remote agent."""
        return await self.send_command(agent_id, "set_mods", server_name, {"mod_ids": mod_ids})

    async def read_ini(self, agent_id: str, server_name: str, file_name: str = "GameUserSettings.ini") -> Dict[str, Any]:
        """Read an INI file from the remote agent."""
        return await self.send_command(agent_id, "read_ini", server_name, {"file_name": file_name})

    async def write_ini(self, agent_id: str, server_name: str, file_name: str, content: str) -> Dict[str, Any]:
        """Write an INI file via the remote agent."""
        return await self.send_command(agent_id, "write_ini", server_name, {"file_name": file_name, "content": content})

    async def update_ini_setting(self, agent_id: str, server_name: str, file_name: str, section: str, key: str, value: str) -> Dict[str, Any]:
        """Update a single INI setting via the remote agent (line-based editing)."""
        return await self.send_command(agent_id, "update_ini_setting", server_name, {
            "file_name": file_name,
            "section": section,
            "key": key,
            "value": value,
        })

    async def _auto_import_ini_files(self, agent_id: str, guild_id: int):
        """Auto-import INI files for all servers when agent connects."""
        try:
            await asyncio.sleep(2)
            
            from bot.database import server_config_db, ini_settings_db
            from bot.utils.ini_parser import parse_ini, extract_settings_list
            
            servers = await server_config_db.get_ark_servers(guild_id)
            if not servers:
                logger.debug(f"No servers found for guild {guild_id}, skipping INI import")
                return
            
            logger.info(f"Auto-importing INI files for {len(servers)} servers...")
            
            for server in servers:
                server_name = server.get("name")
                if not server_name:
                    continue
                
                for file_name in ["GameUserSettings.ini", "Game.ini"]:
                    try:
                        result = await self.read_ini(agent_id, server_name, file_name)
                        
                        if result.get("type") == "complete":
                            content = result.get("data", {}).get("content", "")
                            if content:
                                parsed = parse_ini(content)
                                settings = extract_settings_list(parsed)
                                
                                count = await ini_settings_db.import_ini_settings(
                                    guild_id, server_name, file_name, settings
                                )
                                logger.info(f"Auto-imported {count} settings from {server_name}/{file_name}")
                        else:
                            error = result.get("error", "Unknown error")
                            logger.debug(f"Could not read {file_name} for {server_name}: {error}")
                            
                    except Exception as e:
                        logger.debug(f"Error importing {file_name} for {server_name}: {e}")
                        
        except Exception as e:
            logger.error(f"Error in auto-import INI files: {e}")

    async def load_agents_from_db(self, guild_id: int = None):
        """Load and reconnect agents from database."""
        logger.info(f"Loading agents from DB - guild_id: {guild_id}")
        
        if guild_id:
            agents = await remote_agent_db.get_remote_agents(guild_id)
        else:
            # Load all agents
            agents = await remote_agent_db.get_all_remote_agents()
        
        logger.info(f"Found {len(agents)} agents in database")
        
        for agent in agents:
            agent_id = agent["agent_id"]
            logger.info(f"Processing agent from database: {agent_id}")
            
            if agent_id not in self.agents:
                logger.info(f"Adding new agent to memory: {agent_id}")
                self.agents[agent_id] = {
                    "guild_id": agent.get("guild_id"),
                    "ip": agent.get("agent_ip") or agent.get("ip"),
                    "port": agent.get("agent_port") or agent.get("port"),
                    "auth_key": agent["auth_key"],
                    "connected_at": None,
                }
                safe_info = {k: v for k, v in self.agents[agent_id].items() if k != 'auth_key'}
                logger.info(f"Agent info: {safe_info}")
                
                if agent_id not in self.connections:
                    logger.info(f"Agent {agent_id} not in connections, scheduling reconnect")
                    self._schedule_reconnect(agent_id)
                else:
                    logger.info(f"Agent {agent_id} already in connections")
            else:
                logger.info(f"Agent {agent_id} already in agents")

    async def close_all(self):
        """Close all connections gracefully."""
        for agent_id, ws in list(self.connections.items()):
            try:
                await ws.close()
            except Exception:
                pass
        self.connections.clear()
        for task in self._listeners.values():
            task.cancel()
        for task in self._reconnect_tasks.values():
            task.cancel()

    # ========================================================================
    # Phase 16: ARK Server Service Management
    # ========================================================================

    async def create_server_service(
        self,
        agent_id: str,
        server_name: str,
        display_name: str,
        map_name: str,
        game_port: int = 7777,
        query_port: int = 27015,
        rcon_port: int = 27020,
        rcon_password: str = "",
        server_password: str = "",
        admin_password: str = "",
        max_players: int = 70,
        server_path: str = "",
        steamcmd_path: str = "",
        mods: str = "",
        cluster_id: str = "",
        cluster_path: str = "",
        battleye_enabled: bool = True,
        active_event: str = "",
    ) -> Dict[str, Any]:
        """Create a new ARK server Windows service via the remote agent."""
        params = {
            "server_name": server_name,
            "display_name": display_name,
            "map_name": map_name,
            "game_port": game_port,
            "query_port": query_port,
            "rcon_port": rcon_port,
            "rcon_password": rcon_password,
            "server_password": server_password,
            "admin_password": admin_password,
            "max_players": max_players,
            "server_path": server_path,
            "steamcmd_path": steamcmd_path,
            "mods": mods,
            "cluster_id": cluster_id,
            "cluster_path": cluster_path,
            "battleye_enabled": battleye_enabled,
            "active_event": active_event,
        }
        return await self.send_command(agent_id, "create_server_service", params=params)

    async def update_server_config(
        self,
        agent_id: str,
        server_name: str,
        **updates,
    ) -> Dict[str, Any]:
        """Update an existing ARK server configuration in the registry."""
        params = {"server_name": server_name}
        params.update(updates)
        return await self.send_command(agent_id, "update_server_config", params=params)

    async def read_server_config(self, agent_id: str, server_name: str) -> Dict[str, Any]:
        """Read an ARK server configuration from the registry."""
        return await self.send_command(agent_id, "read_server_config", server_name)

    async def delete_server_service(
        self, agent_id: str, server_name: str, service_name: str = ""
    ) -> Dict[str, Any]:
        """Delete an ARK server service and its registry configuration."""
        params = {"server_name": server_name}
        if service_name:
            params["service_name"] = service_name
        return await self.send_command(agent_id, "delete_server_service", params=params)

    async def list_server_services(self, agent_id: str) -> Dict[str, Any]:
        """List all PhoenixARK server services on the remote agent."""
        logger.info(f"list_server_services: Sending command to agent {agent_id}")
        result = await self.send_command(agent_id, "list_server_services")
        logger.info(f"list_server_services: Got result from agent: {result}")
        return result

    async def start_ark_service(self, agent_id: str, service_name: str) -> Dict[str, Any]:
        """Start an ARK server service."""
        return await self.send_command(agent_id, "start_ark_service", service_name)

    async def stop_ark_service(self, agent_id: str, service_name: str) -> Dict[str, Any]:
        """Stop an ARK server service."""
        return await self.send_command(agent_id, "stop_ark_service", service_name)

    async def restart_ark_service(self, agent_id: str, service_name: str) -> Dict[str, Any]:
        """Restart an ARK server service."""
        return await self.send_command(agent_id, "restart_ark_service", service_name)

    async def get_ark_service_status(self, agent_id: str, service_name: str) -> Dict[str, Any]:
        """Get the status of an ARK server service."""
        return await self.send_command(agent_id, "get_ark_service_status", service_name)


class RemoteAgentCommands(commands.Cog):
    """Discord commands for managing remote ARK server agents."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("RemoteAgent cog __init__ called - creating agent manager")
        
        # Use shared agent_manager from bot object, or create one
        if not hasattr(bot, "agent_manager") or bot.agent_manager is None:
            bot.agent_manager = RemoteAgentManager()
            logger.info("Created new RemoteAgentManager instance")
        else:
            logger.info("Using existing RemoteAgentManager instance")
        
        # Always set bot reference (needed for progress logging)
        bot.agent_manager.set_bot(bot)
        self.agent_manager = bot.agent_manager

    async def cog_load(self):
        """Reconnect agents from DB on cog load."""
        logger.info("RemoteAgent cog_load called - scheduling delayed agent loading")
        # Don't load agents immediately - defer to background task
        # This prevents blocking during cog loading
        task = asyncio.create_task(self._load_agents_delayed())
        task.add_done_callback(
            lambda t: logger.error(f"Delayed agent loading failed: {t.exception()}")
            if not t.cancelled() and t.exception() else None
        )

    async def _load_agents_delayed(self):
        """Load agents after bot is fully ready."""
        try:
            logger.info("Starting delayed agent loading task")
            # Wait for bot to be ready
            await self.bot.wait_until_ready()
            logger.info("Bot is ready, waiting 2 seconds before loading agents")
            await asyncio.sleep(2)  # Small delay after ready

            # Test database connection
            try:
                from bot.database import remote_agent_db
                test_agents = await remote_agent_db.get_all_remote_agents()
                logger.info(f"Database test: Found {len(test_agents)} agents in database")
            except Exception as e:
                logger.error(f"Database connection test failed: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return

            # Load agents for all guilds the bot is in
            logger.info(f"Bot is in {len(self.bot.guilds)} guilds")
            for guild in self.bot.guilds:
                try:
                    logger.info(f"Loading agents for guild {guild.id}")
                    await self.agent_manager.load_agents_from_db(guild.id)
                    logger.info(f"Loaded agents for guild {guild.id}")
                except Exception as e:
                    logger.error(f"Failed to load agents for guild {guild.id}: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
        except Exception as e:
            logger.error(f"Failed in delayed agent loading: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

    async def is_admin(self, interaction: discord.Interaction) -> bool:
        """Check if user has admin permissions."""
        if not interaction.guild:
            return False
        if hasattr(interaction.user, "guild_permissions"):
            return interaction.user.guild_permissions.administrator
        member = interaction.guild.get_member(interaction.user.id)
        if hasattr(member, "guild_permissions"):
            return member.guild_permissions.administrator
        return False


async def setup(bot: commands.Bot):
    """Setup the remote agent commands cog."""
    # Ensure shared agent_manager exists on bot
    if not hasattr(bot, "agent_manager") or bot.agent_manager is None:
        bot.agent_manager = RemoteAgentManager()
    await bot.add_cog(RemoteAgentCommands(bot))
