"""Server change event system for notifying views of updates."""

import asyncio
import inspect
from typing import Set, Dict, Any
from logging import getLogger

logger = getLogger(__name__)


class ServerEventSystem:
    """Simple event system to notify views when servers change."""
    
    def __init__(self):
        self._subscribers: Dict[int, Set] = {}  # guild_id -> set of view callbacks
    
    def subscribe(self, guild_id: int, view_callback):
        """Subscribe a view to server changes for a guild."""
        if guild_id not in self._subscribers:
            self._subscribers[guild_id] = set()
        self._subscribers[guild_id].add(view_callback)
    
    def unsubscribe(self, guild_id: int, view_callback):
        """Unsubscribe a view from server changes."""
        if guild_id in self._subscribers:
            self._subscribers[guild_id].discard(view_callback)
            if not self._subscribers[guild_id]:
                del self._subscribers[guild_id]
    
    async def notify_servers_changed(self, guild_id: int):
        """Notify all subscribers that servers changed."""
        if guild_id not in self._subscribers:
            return
        
        logger.debug(f"Notifying {len(self._subscribers[guild_id])} subscribers of server change for guild {guild_id}")
        
        # Create a copy to avoid issues if subscribers modify during iteration
        callbacks = list(self._subscribers[guild_id])
        
        for callback in callbacks:
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error notifying subscriber of server change: {e}")
                # Remove failing subscriber
                self._subscribers[guild_id].discard(callback)


# Global instance
server_events = ServerEventSystem()
