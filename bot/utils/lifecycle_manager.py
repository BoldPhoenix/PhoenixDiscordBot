"""
Server Lifecycle Manager - Centralized server stop/start/restart with hooks.

All server lifecycle operations flow through this manager to ensure
consistent behavior for:
- Pending INI changes (applied on stop)
- SaveWorld before stop
- Backups before maintenance
- Notifications
- Future extensibility
"""

import asyncio
import logging
from typing import Callable, List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("LifecycleManager")


HookCallback = Callable[[int, str, str], Any]


class ServerLifecycleManager:
    """
    Centralized handler for all server stop/start sequences.
    
    Usage:
        lifecycle = ServerLifecycleManager(agent_manager)
        lifecycle.register_post_stop_hook(apply_pending_ini_changes)
        
        # All restart paths use same flow
        await lifecycle.restart_server(guild_id, server_name, "manual")
    """
    
    def __init__(self, agent_manager):
        self.agent_manager = agent_manager
        self._pre_stop_hooks: List[HookCallback] = []
        self._post_stop_hooks: List[HookCallback] = []
        self._pre_start_hooks: List[HookCallback] = []
        self._post_start_hooks: List[HookCallback] = []
        self._operation_locks: Dict[str, asyncio.Lock] = {}
    
    def _get_lock(self, server_name: str) -> asyncio.Lock:
        """Get or create a lock for a specific server to prevent concurrent operations."""
        if server_name not in self._operation_locks:
            self._operation_locks[server_name] = asyncio.Lock()
        return self._operation_locks[server_name]
    
    def register_pre_stop_hook(self, callback: HookCallback):
        """Register a hook to run before server stops."""
        self._pre_stop_hooks.append(callback)
        logger.debug(f"Registered pre_stop hook: {callback.__name__}")
    
    def register_post_stop_hook(self, callback: HookCallback):
        """Register a hook to run after server stops."""
        self._post_stop_hooks.append(callback)
        logger.debug(f"Registered post_stop hook: {callback.__name__}")
    
    def register_pre_start_hook(self, callback: HookCallback):
        """Register a hook to run before server starts."""
        self._pre_start_hooks.append(callback)
        logger.debug(f"Registered pre_start hook: {callback.__name__}")
    
    def register_post_start_hook(self, callback: HookCallback):
        """Register a hook to run after server starts."""
        self._post_start_hooks.append(callback)
        logger.debug(f"Registered post_start hook: {callback.__name__}")
    
    async def _run_hooks(self, hooks: List[HookCallback], guild_id: int, server_name: str, reason: str):
        """Run a list of hooks, catching and logging any errors."""
        for hook in hooks:
            try:
                result = hook(guild_id, server_name, reason)
                if asyncio.iscoroutine(result):
                    await result
                logger.debug(f"Hook {hook.__name__} completed for {server_name}")
            except Exception as e:
                logger.error(f"Hook {hook.__name__} failed for {server_name}: {e}")
    
    async def stop_server(
        self,
        guild_id: int,
        server_name: str,
        agent_id: str,
        reason: str = "manual",
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """
        Stop a server with lifecycle hooks.
        
        Flow:
        1. Pre-stop hooks (SaveWorld, etc.)
        2. Stop command to agent
        3. Post-stop hooks (Apply pending INI changes, etc.)
        
        Args:
            guild_id: Discord guild ID
            server_name: ARK server name
            agent_id: Connected agent ID
            reason: Reason for stop (manual, maintenance, update, etc.)
            timeout: Timeout for stop command
            
        Returns:
            Dict with 'success' bool and 'message' str
        """
        lock = self._get_lock(server_name)
        async with lock:
            logger.info(f"Stopping server {server_name} (reason: {reason})")
            
            await self._run_hooks(self._pre_stop_hooks, guild_id, server_name, reason)
            
            try:
                result = await self.agent_manager.send_command(
                    agent_id, "stop_server", server_name, timeout=timeout
                )
                
                if result.get("type") == "complete":
                    await self._run_hooks(self._post_stop_hooks, guild_id, server_name, reason)
                    logger.info(f"Server {server_name} stopped successfully")
                    return {"success": True, "message": f"Server {server_name} stopped"}
                else:
                    error = result.get("error", "Unknown error")
                    logger.error(f"Failed to stop {server_name}: {error}")
                    return {"success": False, "message": f"Failed to stop: {error}"}
                    
            except asyncio.TimeoutError:
                logger.error(f"Timeout stopping {server_name}")
                return {"success": False, "message": "Stop command timed out"}
            except Exception as e:
                logger.error(f"Error stopping {server_name}: {e}")
                return {"success": False, "message": str(e)}
    
    async def start_server(
        self,
        guild_id: int,
        server_name: str,
        agent_id: str,
        reason: str = "manual",
        timeout: float = 120.0
    ) -> Dict[str, Any]:
        """
        Start a server with lifecycle hooks.
        
        Flow:
        1. Pre-start hooks
        2. Start command to agent
        3. Post-start hooks
        
        Args:
            guild_id: Discord guild ID
            server_name: ARK server name
            agent_id: Connected agent ID
            reason: Reason for start (manual, maintenance, update, etc.)
            timeout: Timeout for start command
            
        Returns:
            Dict with 'success' bool and 'message' str
        """
        lock = self._get_lock(server_name)
        async with lock:
            logger.info(f"Starting server {server_name} (reason: {reason})")
            
            await self._run_hooks(self._pre_start_hooks, guild_id, server_name, reason)
            
            try:
                result = await self.agent_manager.send_command(
                    agent_id, "start_server", server_name, timeout=timeout
                )
                
                if result.get("type") == "complete":
                    await self._run_hooks(self._post_start_hooks, guild_id, server_name, reason)
                    logger.info(f"Server {server_name} started successfully")
                    return {"success": True, "message": f"Server {server_name} started"}
                else:
                    error = result.get("error", "Unknown error")
                    logger.error(f"Failed to start {server_name}: {error}")
                    return {"success": False, "message": f"Failed to start: {error}"}
                    
            except asyncio.TimeoutError:
                logger.error(f"Timeout starting {server_name}")
                return {"success": False, "message": "Start command timed out"}
            except Exception as e:
                logger.error(f"Error starting {server_name}: {e}")
                return {"success": False, "message": str(e)}
    
    async def restart_server(
        self,
        guild_id: int,
        server_name: str,
        agent_id: str,
        reason: str = "manual",
        stop_timeout: float = 60.0,
        start_timeout: float = 120.0
    ) -> Dict[str, Any]:
        """
        Restart a server with lifecycle hooks.
        
        Flow:
        1. Stop with hooks
        2. Start with hooks
        
        Args:
            guild_id: Discord guild ID
            server_name: ARK server name
            agent_id: Connected agent ID
            reason: Reason for restart (manual, maintenance, update, etc.)
            stop_timeout: Timeout for stop command
            start_timeout: Timeout for start command
            
        Returns:
            Dict with 'success' bool and 'message' str
        """
        logger.info(f"Restarting server {server_name} (reason: {reason})")
        
        stop_result = await self.stop_server(
            guild_id, server_name, agent_id, reason, stop_timeout
        )
        
        if not stop_result["success"]:
            return stop_result
        
        start_result = await self.start_server(
            guild_id, server_name, agent_id, reason, start_timeout
        )
        
        return start_result
    
    async def update_server(
        self,
        guild_id: int,
        server_name: str,
        agent_id: str,
        reason: str = "update",
        timeout: float = 300.0
    ) -> Dict[str, Any]:
        """
        Update a server with lifecycle hooks.
        
        Flow:
        1. Stop with hooks (applies pending INI changes)
        2. Update command to agent
        3. Start with hooks
        
        Args:
            guild_id: Discord guild ID
            server_name: ARK server name
            agent_id: Connected agent ID
            reason: Reason for update
            timeout: Timeout for update command
            
        Returns:
            Dict with 'success' bool and 'message' str
        """
        lock = self._get_lock(server_name)
        async with lock:
            logger.info(f"Updating server {server_name} (reason: {reason})")
            
            stop_result = await self.stop_server(
                guild_id, server_name, agent_id, reason
            )
            
            if not stop_result["success"]:
                return stop_result
            
            try:
                result = await self.agent_manager.send_command(
                    agent_id, "update_server", server_name, timeout=timeout
                )
                
                if result.get("type") == "complete":
                    logger.info(f"Server {server_name} updated successfully")
                else:
                    error = result.get("error", "Unknown error")
                    logger.error(f"Update failed for {server_name}: {error}")
                    
            except Exception as e:
                logger.error(f"Error updating {server_name}: {e}")
            
            start_result = await self.start_server(
                guild_id, server_name, agent_id, reason
            )
            
            return start_result


async def apply_pending_ini_changes(guild_id: int, server_name: str, agent_manager) -> int:
    """
    Apply pending INI changes after server stops.
    
    Called as a post-stop hook by the lifecycle manager.
    
    Args:
        guild_id: Discord guild ID
        server_name: ARK server name
        agent_manager: The agent manager instance
        
    Returns:
        Number of changes applied
    """
    from bot.database import ini_settings_db
    
    pending = await ini_settings_db.get_pending_changes(guild_id, server_name)
    if not pending:
        logger.debug(f"No pending INI changes for {server_name}")
        return 0
    
    agent_id = await agent_manager.get_connected_agent_for_guild(guild_id)
    if not agent_id:
        logger.warning(f"Cannot apply pending changes - no agent connected for guild {guild_id}")
        return 0
    
    applied = 0
    for change in pending:
        change_id = change.get("id")
        if not change_id:
            continue
            
        file_name = change.get("file_name")
        section = change.get("section_name")
        key = change.get("key_name")
        value = change.get("new_value")
        
        logger.info(f"Applying INI change: {file_name} -> [{section}] {key} = {value}")
        
        try:
            result = await agent_manager.update_ini_setting(
                agent_id, server_name, file_name, section, key, value
            )
            
            if result.get("type") == "complete":
                await ini_settings_db.mark_change_applied(change_id)
                applied += 1
                logger.info(f"Applied pending change: {section}.{key} = {value}")
            else:
                logger.error(f"Failed to apply change {change_id}: {result.get('error')}")
        except Exception as e:
            logger.error(f"Error applying change {change_id}: {e}")
    
    logger.info(f"Applied {applied}/{len(pending)} pending INI changes for {server_name}")
    return applied


lifecycle_manager: Optional[ServerLifecycleManager] = None


def init_lifecycle_manager(agent_manager) -> ServerLifecycleManager:
    """Initialize the global lifecycle manager."""
    global lifecycle_manager
    lifecycle_manager = ServerLifecycleManager(agent_manager)
    return lifecycle_manager


def get_lifecycle_manager() -> Optional[ServerLifecycleManager]:
    """Get the global lifecycle manager."""
    return lifecycle_manager
