"""
Chat relay cog for bidirectional communication between Discord and ARK servers.
Uses RCON GetChat command to poll for in-game chat messages and relay to Discord.
"""

import discord
from discord.ext import commands, tasks
import logging
import asyncio
import re
from pathlib import Path
from typing import Dict, Optional, List, Set
import aiofiles

from bot.rcon.client import RCONManager, ArkRCONClient
from bot.utils.config import Config
from bot.database import server_config_db
from bot.database import chat_history_db


logger = logging.getLogger("ChatRelayCog")


class RCONChatMonitor:
    """Monitors ARK server chat via RCON GetChat command."""

    def __init__(self, server_name: str, rcon_client: ArkRCONClient):
        self.server_name = server_name
        self.rcon_client = rcon_client
        self.last_messages: Set[str] = set()  # Track seen messages to prevent duplicates
        self.max_cache_size = 200  # Maximum messages to cache

        # ARK ASA chat patterns from GetChat response
        # Common formats:
        # "PlayerName: message"
        # "[GLOBAL] PlayerName: message"
        # "SERVER: message" (admin broadcasts - we should skip these)
        self.chat_patterns = [
            # Global chat: "[GLOBAL] PlayerName: message" or "PlayerName: message"
            re.compile(
                r"^\[?(?:GLOBAL|LOCAL|TRIBE|ALLIANCE)?\]?\s*([^:\[\]]+?):\s+(.+)$", re.IGNORECASE
            ),
        ]

        # Patterns for messages to SKIP (system messages, bot echoes)
        self.skip_patterns = [
            re.compile(r"^\[Discord\]", re.IGNORECASE),  # Our own Discord relay
            re.compile(r"^SERVER:", re.IGNORECASE),  # Server broadcasts
            re.compile(r"^Admin\s*Message", re.IGNORECASE),  # Admin messages
            re.compile(r"Server received, But no response", re.IGNORECASE),  # Empty response
        ]

    async def get_new_messages(self) -> List[dict]:
        """Poll RCON GetChat for new chat messages."""
        messages = []

        try:
            # Get chat via RCON
            response = await self.rcon_client.get_chat()

            if not response:
                return []

            for line in response:
                line = line.strip()
                if not line:
                    continue

                # Skip system messages and bot echoes
                should_skip = False
                for skip_pattern in self.skip_patterns:
                    if skip_pattern.search(line):
                        should_skip = True
                        break

                if should_skip:
                    continue

                # Try to parse chat message
                for pattern in self.chat_patterns:
                    match = pattern.match(line)
                    if match:
                        player_name = match.group(1).strip()
                        message_text = match.group(2).strip()

                        # Skip commands and empty messages
                        if not player_name or not message_text or message_text.startswith("/"):
                            continue

                        # Create unique key to prevent duplicates
                        msg_key = f"{player_name}:{message_text}"

                        if msg_key not in self.last_messages:
                            self.last_messages.add(msg_key)
                            messages.append(
                                {
                                    "player": player_name,
                                    "message": message_text,
                                    "server": self.server_name,
                                }
                            )

                            # Prevent memory bloat
                            if len(self.last_messages) > self.max_cache_size:
                                # Remove oldest half
                                to_remove = list(self.last_messages)[: self.max_cache_size // 2]
                                for key in to_remove:
                                    self.last_messages.discard(key)
                        break

        except Exception as e:
            logger.error(f"Error getting chat from {self.server_name}: {e}")

        return messages


class LogMonitor:
    """Monitors ARK server log files for chat messages (fallback for non-ASA servers)."""

    def __init__(self, log_path: str, server_name: str):
        self.log_path = Path(log_path)
        self.server_name = server_name
        self.position = 0
        self.last_messages: Set[str] = set()  # Prevent duplicate messages

        # ARK chat patterns
        # ASA format: "[timestamp] PlayerName: message"
        self.chat_patterns = [
            re.compile(r"\[[\d:\.]+\]\s+(.+?):\s+(.+)"),  # Standard chat
            re.compile(r"<(.+?)>\s+(.+)"),  # Alternative format
        ]

    async def get_new_messages(self) -> list:
        """Read new chat messages from log file."""
        if not self.log_path.exists():
            return []

        messages = []

        try:
            async with aiofiles.open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                await f.seek(self.position)
                new_lines = await f.readlines()
                self.position = await f.tell()

                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Try each pattern
                    for pattern in self.chat_patterns:
                        match = pattern.search(line)
                        if match:
                            player_name = match.group(1).strip()
                            message = match.group(2).strip()

                            # Filter out system messages and commands
                            if player_name and message and not message.startswith("/"):
                                # Create unique key to prevent duplicates
                                msg_key = f"{player_name}:{message}"
                                if msg_key not in self.last_messages:
                                    self.last_messages.add(msg_key)
                                    messages.append(
                                        {
                                            "player": player_name,
                                            "message": message,
                                            "server": self.server_name,
                                        }
                                    )

                                    # Keep last_messages set from growing too large
                                    if len(self.last_messages) > 100:
                                        self.last_messages.clear()
                            break
        except Exception as e:
            logger.error(f"Error reading log file {self.log_path}: {e}")

        return messages


class ChatRelay(commands.Cog):
    """Cross-chat relay between Discord and ARK servers.

    Uses RCON GetChat command to poll for in-game chat messages.
    Discord → ARK: Uses RCON ServerChat command.
    ARK → Discord: Uses RCON GetChat command polling.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Multi-tenant: Use server_id as key (unique across all guilds)
        self.log_monitors: Dict[int, LogMonitor] = {}  # server_id -> LogMonitor
        self.rcon_chat_monitors: Dict[int, RCONChatMonitor] = {}  # server_id -> RCONChatMonitor
        self.rcon_clients: Dict[int, ArkRCONClient] = {}  # server_id -> ArkRCONClient
        # Multi-tenant: Store config per guild
        self.guild_configs: Dict[int, dict] = {}  # guild_id -> {chat_channel_id, admin_log_channel_id, servers}
        self._initialized = False
        
        self._admin_patterns = [
            re.compile(r"^SERVER:", re.IGNORECASE),
            re.compile(r"^Admin\s*Message", re.IGNORECASE),
            re.compile(r"^\[SERVER\]", re.IGNORECASE),
        ]

    async def cog_load(self):
        """Called when the cog is loaded."""
        # Initialize chat history database table
        await chat_history_db.init_chat_history_table()
        
        # Start cleanup task
        self.cleanup_old_chat_messages.start()
        
        # Schedule initialization for after bot is ready (don't block setup_hook)
        self.bot.loop.create_task(self._delayed_init())

    async def _delayed_init(self):
        """Initialize after bot is ready."""
        await self.bot.wait_until_ready()
        await self._initialize_from_database()
        self.chat_relay_loop.start()

    async def _initialize_from_database(self):
        """Load configuration from database for ALL guilds (multi-tenant)."""
        try:
            # Multi-tenant: Load config for ALL guilds
            for guild in self.bot.guilds:
                guild_id = guild.id
                
                # Get server config from database
                config = await server_config_db.get_server_config(guild_id)
                if not config:
                    logger.warning(f"No server config found for guild {guild.name} ({guild_id})")
                    continue
                
                chat_channel_id = config.get("chat_channel_id")
                admin_log_channel_id = config.get("admin_log_channel_id")
                
                if not chat_channel_id:
                    logger.warning(f"chat_channel_id not configured for guild {guild.name} ({guild_id})")
                    continue
                
                # Get ARK servers for this guild
                all_servers = await server_config_db.get_ark_servers(guild_id)
                enabled_servers = [s for s in all_servers if s.get("enabled", True)]
                
                if not enabled_servers:
                    logger.warning(f"No enabled servers for guild {guild.name} ({guild_id})")
                    continue
                
                # Store guild config
                self.guild_configs[guild_id] = {
                    "chat_channel_id": chat_channel_id,
                    "admin_log_channel_id": admin_log_channel_id,
                    "servers": enabled_servers
                }
                
                logger.info(f"Chat relay loaded for guild {guild.name} ({guild_id}): {len(enabled_servers)} servers, chat channel {chat_channel_id}")
            
            if not self.guild_configs:
                logger.warning("No guilds configured for chat relay")
                return
            
            # Initialize RCON clients for all servers across all guilds
            await self._initialize_rcon_clients()
            
            # Initialize log monitors
            self._initialize_log_monitors()
            
            self._initialized = True
            logger.info(f"Chat relay initialized for {len(self.guild_configs)} guild(s)")

        except Exception as e:
            logger.error(f"Error initializing chat relay from database: {e}")

    async def _initialize_rcon_clients(self):
        """Set up RCON clients for each server with chat enabled across all guilds."""
        for guild_id, guild_config in self.guild_configs.items():
            for server in guild_config["servers"]:
                if server.get("chat_enabled", False) and server.get("enabled", True):
                    server_id = server["id"]
                    try:
                        client = ArkRCONClient(
                            host=server["host"],
                            port=server["rcon_port"],
                            password=server["rcon_password"],
                            server_name=server["name"],
                        )

                        # Connect the RCON client
                        if await client.connect():
                            self.rcon_clients[server_id] = client
                            logger.info(f"Connected RCON client for chat: {server['name']} (ID: {server_id})")

                            # Create RCON chat monitor for ARK→Discord (ASA servers)
                            self.rcon_chat_monitors[server_id] = RCONChatMonitor(
                                server_name=server["name"], rcon_client=client
                            )
                            logger.info(f"Initialized RCON chat monitor for {server['name']} (ID: {server_id})")
                        else:
                            logger.warning(f"Failed to connect RCON for chat: {server['name']} (ID: {server_id})")

                    except Exception as e:
                        logger.error(f"Error creating RCON client for {server['name']} (ID: {server_id}): {e}")

    def _initialize_log_monitors(self):
        """Set up log monitors for each server with log paths (Self-Hosted Only) across all guilds."""
        for guild_id, guild_config in self.guild_configs.items():
            for server in guild_config["servers"]:
                if server.get("chat_enabled", False) and server.get("enabled", True):
                    server_id = server["id"]
                    log_path = server.get("log_path")
                    if log_path:
                        self.log_monitors[server_id] = LogMonitor(log_path, server["name"])
                        logger.info(f"Initialized log monitor for {server['name']} (ID: {server_id}): {log_path}")
                    else:
                        logger.debug(
                            f"Server {server['name']} (ID: {server_id}) has no log_path - ARK→Discord chat disabled for this server"
                        )

    def cog_unload(self):
        """Cleanup when cog is unloaded."""
        self.chat_relay_loop.cancel()

    async def refresh_config(self):
        """Refresh configuration from database (for hot-reload)."""
        await self._initialize_from_database()
        logger.info("Chat relay configuration refreshed")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Forward Discord messages to ARK servers."""
        # Debug: Log ALL messages to see if event is firing
        logger.debug(f"on_message triggered: author={message.author}, channel={message.channel.id}, bot={message.author.bot}")
        
        # Ignore bot messages
        if message.author.bot:
            logger.debug(f"Ignoring bot message from {message.author}")
            return

        # Check if initialized
        if not self._initialized:
            logger.warning("Chat relay not initialized")
            return
        
        # Multi-tenant: Get guild from message
        if not message.guild:
            logger.debug("Ignoring DM message")
            return
        
        guild_id = message.guild.id
        guild_config = self.guild_configs.get(guild_id)
        
        if not guild_config:
            logger.debug(f"No chat relay config for guild {guild_id}")
            return
        
        # Only relay from the designated chat channel for this guild
        if message.channel.id != guild_config["chat_channel_id"]:
            logger.debug(f"Ignoring message from channel {message.channel.id} (expected {guild_config['chat_channel_id']})")
            return

        logger.info(f"Processing chat message from {message.author} in guild {message.guild.name}: {message.clean_content}")

        # Format message for ARK
        formatted_message = f"[Discord] {message.author.display_name}: {message.clean_content}"

        # Get ServerMonitor's RCONManager for this guild
        server_monitor = self.bot.get_cog("ServerMonitor")
        if not server_monitor:
            logger.error("ServerMonitor not available for chat relay")
            return
        
        rcon_manager = server_monitor.guild_rcon_managers.get(guild_id)
        if not rcon_manager:
            logger.error(f"No RCONManager found for guild {guild_id}")
            return

        # Broadcast to all servers in this guild with chat enabled
        success_count = 0
        for server in guild_config["servers"]:
            if server.get("chat_enabled", False) and server.get("enabled", True):
                try:
                    success, response = await rcon_manager.execute_command(server["name"], f"ServerChat {formatted_message}")
                    if success:
                        success_count += 1
                        logger.debug(f"Sent Discord message to {server['name']}")
                    else:
                        logger.warning(f"Failed to send to {server['name']}: {response}")
                except Exception as e:
                    logger.error(f"Error broadcasting to {server['name']}: {e}")

        if success_count > 0:
            # Add reaction to confirm message was sent
            try:
                await message.add_reaction("✅")
            except:
                pass
            logger.info(
                f"Relayed Discord message from {message.author} to {success_count} server(s)"
            )
        else:
            logger.warning(
                f"Failed to relay Discord message from {message.author} - no servers available"
            )

    @tasks.loop(seconds=3.0)
    async def chat_relay_loop(self):
        """Poll ARK servers for new chat messages and relay cross-server (multi-tenant)."""
        if not self._initialized:
            return
        
        # Multi-tenant: Process each guild separately
        for guild_id, guild_config in self.guild_configs.items():
            chat_channel_id = guild_config["chat_channel_id"]
            admin_log_channel_id = guild_config.get("admin_log_channel_id")
            
            channel = self.bot.get_channel(chat_channel_id)
            if not channel:
                logger.debug(f"Chat channel {chat_channel_id} not found for guild {guild_id}")
                continue
            
            admin_channel = None
            if admin_log_channel_id:
                admin_channel = self.bot.get_channel(admin_log_channel_id)
            
            await self._process_guild_chat(guild_id, guild_config, channel, admin_channel)
    
    async def _process_guild_chat(self, guild_id: int, guild_config: dict, channel, admin_channel):
        """Process chat for a single guild."""
        # Get server IDs for this guild
        guild_server_ids = {s["id"] for s in guild_config["servers"]}
        
        # Poll RCON chat monitors (primary method for ASA servers) - only for this guild's servers
        for server_id, monitor in self.rcon_chat_monitors.items():
            if server_id not in guild_server_ids:
                continue
            try:
                messages = await monitor.get_new_messages()

                for msg in messages:
                    # Check if this is an admin message
                    is_admin_msg = self._is_admin_message(msg["player"], msg["message"])
                    
                    # Store message in database
                    await chat_history_db.store_chat_message(
                        guild_id, msg["server"], msg["player"], msg["message"]
                    )

                    # Route admin messages to admin log channel, regular messages to chat channel
                    target_channel = admin_channel if is_admin_msg else channel
                    if not target_channel:
                        target_channel = channel
                    
                    embed_color = discord.Color.orange() if is_admin_msg else discord.Color.green()
                    
                    # Format message for Discord
                    embed = discord.Embed(description=msg["message"], color=embed_color)
                    embed.set_author(name=f"[{msg['server']}] {msg['player']}")

                    try:
                        await target_channel.send(embed=embed)
                        logger.info(
                            f"Relayed {'admin ' if is_admin_msg else ''}message from {msg['player']} on {msg['server']} to Discord"
                        )
                    except Exception as e:
                        logger.error(f"Error sending message to Discord: {e}")

                    # Cross-server relay: broadcast to ALL OTHER servers in this guild (skip admin messages)
                    if not is_admin_msg:
                        await self._relay_to_other_servers(msg, msg["server"], guild_id, guild_config)

            except Exception as e:
                logger.error(f"Error in RCON chat relay loop for server ID {server_id}: {e}")

        # Also check log monitors (fallback for legacy/non-ASA servers) - only for this guild's servers
        for server_id, monitor in self.log_monitors.items():
            if server_id not in guild_server_ids:
                continue
            try:
                messages = await monitor.get_new_messages()

                for msg in messages:
                    # Check if this is an admin message
                    is_admin_msg = self._is_admin_message(msg["player"], msg["message"])
                    
                    # Store message in database
                    await chat_history_db.store_chat_message(
                        guild_id, msg["server"], msg["player"], msg["message"]
                    )

                    # Route admin messages to admin log channel, regular messages to chat channel
                    target_channel = admin_channel if is_admin_msg else channel
                    if not target_channel:
                        target_channel = channel
                    
                    embed_color = discord.Color.orange() if is_admin_msg else discord.Color.blue()
                    
                    # Format message for Discord
                    embed = discord.Embed(description=msg["message"], color=embed_color)
                    embed.set_author(name=f"[{msg['server']}] {msg['player']}")

                    try:
                        await target_channel.send(embed=embed)
                        logger.debug(
                            f"Relayed {'admin ' if is_admin_msg else ''}message from {msg['player']} on {msg['server']}"
                        )
                    except Exception as e:
                        logger.error(f"Error sending message to Discord: {e}")

                    # Cross-server relay: broadcast to ALL OTHER servers in this guild (skip admin messages)
                    if not is_admin_msg:
                        await self._relay_to_other_servers(msg, msg["server"], guild_id, guild_config)

            except Exception as e:
                logger.error(f"Error in log chat relay loop for server ID {server_id}: {e}")

    def _is_admin_message(self, player: str, message: str) -> bool:
        """Check if a message is an admin/server broadcast."""
        combined = f"{player}: {message}"
        for pattern in self._admin_patterns:
            if pattern.search(combined):
                return True
        return False

    async def _relay_to_other_servers(self, msg: dict, source_server: str, guild_id: int, guild_config: dict):
        """Relay a message from one ARK server to all other ARK servers in the same guild."""
        # Format message for cross-server broadcast
        formatted_message = f"[{msg['server']}] {msg['player']}: {msg['message']}"

        # Get ServerMonitor's RCONManager for this guild
        server_monitor = self.bot.get_cog("ServerMonitor")
        if not server_monitor:
            logger.error("ServerMonitor not available for cross-server relay")
            return
        
        rcon_manager = server_monitor.guild_rcon_managers.get(guild_id)
        if not rcon_manager:
            logger.error(f"No RCONManager found for guild {guild_id} in cross-server relay")
            return

        relay_count = 0
        for server in guild_config["servers"]:
            # Skip the source server - don't echo back
            if server["name"] == source_server:
                continue

            # Only relay to servers with chat enabled
            if not server.get("chat_enabled", False) or not server.get("enabled", True):
                continue

            try:
                success, response = await rcon_manager.execute_command(server["name"], f"ServerChat {formatted_message}")
                if success:
                    relay_count += 1
                else:
                    logger.warning(f"Failed cross-server relay to {server['name']}: {response}")
            except Exception as e:
                logger.error(f"Error relaying cross-server chat to {server['name']}: {e}")

        if relay_count > 0:
            logger.debug(
                f"Cross-server relayed message from {source_server} to {relay_count} other server(s) in guild {guild_id}"
            )

    @chat_relay_loop.before_loop
    async def before_chat_relay(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24.0)
    async def cleanup_old_chat_messages(self):
        """Daily cleanup of old chat messages (30+ days old)."""
        try:
            for guild_id in list(self.guild_configs):
                deleted = await chat_history_db.cleanup_old_messages(guild_id, days=30)
                if deleted > 0:
                    logger.info(f"Chat history cleanup guild {guild_id}: deleted {deleted} old messages")
        except Exception as e:
            logger.error(f"Error during chat history cleanup: {e}")

    @cleanup_old_chat_messages.before_loop
    async def before_cleanup(self):
        """Wait until the bot is ready before starting cleanup task."""
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(ChatRelay(bot))
