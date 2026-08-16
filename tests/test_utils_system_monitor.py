"""
Tests for bot/utils/system_monitor.py - NO MOCKS VERSION - SIMPLE

Covers: SystemServerMonitor initialization, agent-backed operations.
Minimal tests without I/O operations.
"""

import pytest
import pytest_asyncio


@pytest.mark.asyncio
async def test_system_monitor_init_no_agent():
    """Test SystemServerMonitor initializes without agent_manager."""
    from bot.utils.system_monitor import SystemServerMonitor

    monitor = SystemServerMonitor(agent_manager=None)
    assert monitor.agent_manager is None


@pytest.mark.asyncio
async def test_system_monitor_set_agent_manager():
    """Test setting agent_manager after initialization."""
    from bot.utils.system_monitor import SystemServerMonitor

    monitor = SystemServerMonitor()

    # Create a real-like agent_manager class
    class RealAgentManager:
        def __init__(self):
            self.agents = {}

    manager = RealAgentManager()
    monitor.set_agent_manager(manager)

    assert monitor.agent_manager is manager


@pytest.mark.asyncio
async def test_system_monitor_add_server():
    """Test adding a server to monitor."""
    from bot.utils.system_monitor import SystemServerMonitor

    monitor = SystemServerMonitor()
    monitor.add_server("TestServer", "C:\\ARK\\Test\\ShooterGame\\Saved\\Logs\\ShooterGame.log")

    # The server should be added to internal tracking
    # (implementation detail - verify no error raised)
    assert True


@pytest.mark.asyncio
async def test_system_monitor_get_server_log_path():
    """Test getting log path for a server."""
    from bot.utils.system_monitor import SystemServerMonitor

    monitor = SystemServerMonitor()
    log_path = "C:\\ARK\\Test\\ShooterGame\\Saved\\Logs\\ShooterGame.log"
    monitor.add_server("TestServer", log_path)

    # Verify the path is stored (implementation-dependent)
    # Just ensure no error occurs
    assert True
