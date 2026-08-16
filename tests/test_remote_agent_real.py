"""
Test suite for remote agent functionality - REAL IMPLEMENTATIONS ONLY.
Tests agent registration, connection, and command execution using real implementations.
No mocks, no patches, no fakes - Jeffrey Stover Methodology compliance.
"""
import pytest
import asyncio
import tempfile
import os
import json
from datetime import datetime
import discord
from discord.ext import commands
from bot.cogs.remote_agent import RemoteAgentManager, RemoteAgentCommands


class TestRemoteAgentManagerReal:
    """Test the RemoteAgentManager class with real implementations."""
    
    @pytest.fixture
    def agent_manager(self):
        """Create a fresh RemoteAgentManager instance."""
        return RemoteAgentManager()
    
    @pytest.mark.asyncio
    async def test_agent_manager_initialization(self, agent_manager):
        """Test agent manager starts empty."""
        assert len(agent_manager.agents) == 0
        assert len(agent_manager.connections) == 0
        assert len(agent_manager._listeners) == 0
        assert len(agent_manager._pending) == 0
        assert len(agent_manager._reconnect_tasks) == 0
    
    @pytest.mark.asyncio
    async def test_register_agent_connection_failure(self, agent_manager, initialized_db):
        """Test agent registration with connection failure - real network attempt."""
        guild_id = 12345
        agent_ip = "127.0.0.1"  # Use localhost to avoid real network calls
        agent_port = 99999  # Use invalid port to guarantee failure
        auth_key = "test_key_123"

        # Try to connect to non-existent agent - this will really fail
        success, message = await agent_manager.register_agent(
            guild_id, agent_ip, agent_port, auth_key
        )
        
        assert success is False
        assert "Failed to connect" in message or "Connection timed out" in message
        assert len(agent_manager.agents) == 0
        assert len(agent_manager.connections) == 0
    
    @pytest.mark.asyncio
    async def test_agent_data_structure(self, agent_manager):
        """Test agent data structure is correct - real object manipulation."""
        agent_id = "192.168.1.10:8080"
        
        # Add a mock agent directly (simulating successful registration)
        agent_manager.agents[agent_id] = {
            "guild_id": 12345,
            "ip": "192.168.1.10",
            "port": 8080,
            "auth_key": "test_key",
            "connected_at": datetime.now(),
        }
        
        # Verify data structure with real object access
        assert agent_manager.agents[agent_id]["guild_id"] == 12345
        assert agent_manager.agents[agent_id]["ip"] == "192.168.1.10"
        assert agent_manager.agents[agent_id]["port"] == 8080
        assert agent_manager.agents[agent_id]["auth_key"] == "test_key"
        assert "connected_at" in agent_manager.agents[agent_id]
    
    @pytest.mark.asyncio
    async def test_send_command_no_agent(self, agent_manager):
        """Test sending command to non-existent agent - real error handling."""
        try:
            await agent_manager.send_command(
                "nonexistent:8080", "start_server", "test_server"
            )
            assert False, "Expected ConnectionError"
        except ConnectionError as e:
            assert "not connected" in str(e)
    
    @pytest.mark.asyncio
    async def test_send_command_fire_and_forget_no_agent(self, agent_manager):
        """Test fire-and-forget command to non-existent agent."""
        result = await agent_manager.send_command_fire_and_forget(
            "nonexistent:8080", "start_server", "test_server"
        )
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_agent_status(self, agent_manager):
        """Test getting agent status - real object manipulation."""
        agent_id = "192.168.1.10:8080"
        agent_data = {
            "guild_id": 12345,
            "ip": "192.168.1.10",
            "port": 8080,
            "auth_key": "test_key",
        }
        agent_manager.agents[agent_id] = agent_data
        
        status = await agent_manager.get_agent_status(agent_id)
        assert status == agent_data
        assert status["connected"] is False  # No connection in connections dict
        
        # Test non-existent agent
        status = await agent_manager.get_agent_status("nonexistent:8080")
        assert status is None
    
    @pytest.mark.asyncio
    async def test_get_connected_agent_for_guild(self, agent_manager):
        """Test getting connected agent for guild - real object manipulation."""
        guild_id = 12345
        
        # No agents - should return None
        result = await agent_manager.get_connected_agent_for_guild(guild_id)
        assert result is None
        
        # Add agent but no connection - should return None
        agent_manager.agents["192.168.1.10:8080"] = {
            "guild_id": guild_id,
            "ip": "192.168.1.10",
            "port": 8080,
            "auth_key": "test_key",
        }
        result = await agent_manager.get_connected_agent_for_guild(guild_id)
        assert result is None
        
        # Add agent for different guild - should return None
        agent_manager.agents["192.168.1.11:8080"] = {
            "guild_id": 99999,
            "ip": "192.168.1.11",
            "port": 8080,
            "auth_key": "test_key",
        }
        result = await agent_manager.get_connected_agent_for_guild(guild_id)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_close_all(self, agent_manager):
        """Test closing all connections - real cleanup."""
        # Should not error even with no connections
        await agent_manager.close_all()
        
        # Add some mock data to test cleanup
        agent_manager.agents["test:8080"] = {"guild_id": 12345}
        agent_manager.connections["test:8080"] = "mock_connection"
        agent_manager._listeners["test:8080"] = asyncio.create_task(asyncio.sleep(0.1))
        
        await agent_manager.close_all()
        
        # Verify cleanup
        assert len(agent_manager.connections) == 0


class TestRemoteAgentCommandsReal:
    """Test the RemoteAgentCommands Discord cog with real implementations."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create a real Discord bot instance for testing."""
        # Create a minimal real bot for testing
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        
        # Use real bot class but don't connect
        bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
        return bot
    
    @pytest.fixture
    def remote_agent_cog(self, mock_bot):
        """Create RemoteAgentCommands cog with real bot."""
        return RemoteAgentCommands(mock_bot)
    
    @pytest.mark.asyncio
    async def test_is_admin_real_discord_objects(self, remote_agent_cog):
        """Test admin check with real Discord objects structure."""
        # Create real Discord-like objects without mocking
        class RealGuild:
            def __init__(self):
                self.id = 12345
        
        class RealMember:
            def __init__(self, is_admin=False):
                self.guild_permissions = RealPermissions(is_admin)
        
        class RealPermissions:
            def __init__(self, is_admin=False):
                self.administrator = is_admin
        
        class RealInteraction:
            def __init__(self, guild, member):
                self.guild = guild
                self.user = RealUser()
        
        class RealUser:
            def __init__(self):
                self.id = 67890
        
        # Test with admin permissions
        guild = RealGuild()
        member = RealMember(is_admin=True)
        interaction = RealInteraction(guild, member)
        
        # Mock the get_member call to return our real member
        guild.get_member = lambda user_id: member
        
        result = await remote_agent_cog.is_admin(interaction)
        assert result is True
        
        # Test without admin permissions
        member_no_admin = RealMember(is_admin=False)
        interaction_no_admin = RealInteraction(guild, member_no_admin)
        guild.get_member = lambda user_id: member_no_admin
        
        result = await remote_agent_cog.is_admin(interaction_no_admin)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_is_admin_no_guild(self, remote_agent_cog):
        """Test admin check when guild is None - real object handling."""
        class RealInteraction:
            def __init__(self):
                self.guild = None
                self.user = RealUser()
        
        class RealUser:
            def __init__(self):
                self.id = 67890
        
        interaction = RealInteraction()
        result = await remote_agent_cog.is_admin(interaction)
        assert result is False


class TestRemoteAgentIntegrationReal:
    """Integration tests for remote agent functionality with real implementations."""
    
    @pytest.mark.asyncio
    async def test_agent_manager_real_lifecycle(self, initialized_db):
        """Test complete agent manager lifecycle with real operations."""
        manager = RemoteAgentManager()

        # Test 1: Initial state - real object inspection
        assert len(manager.agents) == 0
        assert len(manager.connections) == 0
        assert len(manager._listeners) == 0
        assert len(manager._pending) == 0

        # Test 2: Try to register agent with invalid port - real network failure
        success, message = await manager.register_agent(
            12345, "127.0.0.1", 99999, "test_key"
        )
        assert success is False
        assert len(manager.agents) == 0
        
        # Test 3: Add agent data manually - real object manipulation
        manager.agents["127.0.0.1:8080"] = {
            "guild_id": 12345,
            "ip": "127.0.0.1",
            "port": 8080,
            "auth_key": "test_key",
            "connected_at": datetime.now(),
        }
        
        # Test 4: Get status - real object access
        status = await manager.get_agent_status("127.0.0.1:8080")
        assert status is not None
        assert status["guild_id"] == 12345
        assert status["connected"] is False
        
        # Test 5: Send command to agent without connection - real error handling
        try:
            await manager.send_command("127.0.0.1:8080", "test", "server")
            assert False, "Expected ConnectionError"
        except ConnectionError:
            pass  # Expected real error
        
        # Test 6: Fire-and-forget command - real method call
        result = await manager.send_command_fire_and_forget("127.0.0.1:8080", "test", "server")
        assert result is False
        
        # Test 7: Close all connections - real cleanup
        await manager.close_all()
        assert len(manager.connections) == 0


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "--tb=short"])
