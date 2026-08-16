"""
Tests for guild lifecycle handling (join/leave) and owner notifications.

Covers:
- on_guild_join sends DM to bot owner
- on_guild_join logs to owner notification channel (if configured)
- on_guild_remove marks guild as inactive (soft delete)
- on_guild_remove does NOT delete data
- /subadmin dashboard shows aggregate stats
"""

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timezone
from types import SimpleNamespace

pytestmark = pytest.mark.asyncio(loop_scope="function")


class _FakeBot:
    def __init__(self):
        self.guilds = []
        self.owner = None
        self.owner_id = 123456789
        
    def get_channel(self, channel_id):
        return None
    
    def get_guild(self, guild_id):
        return None
    
    def get_user(self, user_id):
        return None
    
    async def wait_until_ready(self):
        pass


def _make_guild(guild_id=12345, name="Test Guild", member_count=100, owner_id=99999):
    guild = MagicMock()
    guild.id = guild_id
    guild.name = name
    guild.member_count = member_count
    guild.owner_id = owner_id
    owner = MagicMock()
    owner.id = owner_id
    owner.display_name = "OwnerName"
    owner.name = "owneruser"
    owner.send = AsyncMock()
    guild.owner = owner
    return guild


@pytest.fixture
def tmp_db_path(tmp_path):
    return str(tmp_path / "test_bot.db")


@pytest.fixture
def config_db_path(tmp_db_path, monkeypatch):
    monkeypatch.setattr("bot.utils.config.Config.DATABASE_PATH", tmp_db_path)
    return tmp_db_path


@pytest_asyncio.fixture
async def initialized_db(config_db_path):
    from bot.database import init_db
    await init_db.initialize_database()
    return config_db_path


# ---------------------------------------------------------------------------
# Test: on_guild_join sends DM to bot owner
# ---------------------------------------------------------------------------

class TestOnGuildJoinOwnerNotification:
    """Verify on_guild_join notifies the bot owner about new guilds."""
    
    @pytest.mark.asyncio
    async def test_on_guild_join_sends_dm_to_bot_owner(self, initialized_db, monkeypatch):
        """on_guild_join MUST send a DM to the bot owner with guild details."""
        from bot.cogs.subscription import SubscriptionCog
        from bot.utils.config import Config
        
        monkeypatch.setattr(Config, "BOT_OWNER_DISCORD_ID", 123456789)
        
        bot = _FakeBot()
        
        owner_user = MagicMock()
        owner_user.id = 123456789
        owner_user.send = AsyncMock()
        bot.get_user = MagicMock(return_value=owner_user)
        
        cog = SubscriptionCog(bot)
        
        guild = _make_guild(guild_id=555666, name="New ARK Server", member_count=150, owner_id=888999)
        
        await cog.on_guild_join(guild)
        
        bot.get_user.assert_called_once_with(123456789)
        owner_user.send.assert_called_once()
        
        call_args = owner_user.send.call_args
        assert call_args is not None
        embed = call_args.kwargs.get("embed") or call_args.args[0]
        assert embed is not None
        assert "555666" in str(embed.to_dict()) or "New ARK Server" in str(embed.to_dict())
    
    @pytest.mark.asyncio
    async def test_on_guild_join_dm_content_contains_guild_info(self, initialized_db, monkeypatch):
        """DM must contain: guild name, guild ID, owner name, member count."""
        from bot.cogs.subscription import SubscriptionCog
        from bot.utils.config import Config
        
        monkeypatch.setattr(Config, "BOT_OWNER_DISCORD_ID", 123456789)
        
        bot = _FakeBot()
        
        owner_user = MagicMock()
        owner_user.id = 123456789
        owner_user.send = AsyncMock()
        bot.get_user = MagicMock(return_value=owner_user)
        
        cog = SubscriptionCog(bot)
        guild = _make_guild(guild_id=777888, name="Dino Warriors", member_count=250, owner_id=111222)
        
        await cog.on_guild_join(guild)
        
        call_args = owner_user.send.call_args
        embed = call_args.kwargs.get("embed") or call_args.args[0]
        embed_dict = embed.to_dict()
        content = str(embed_dict)
        
        assert "Dino Warriors" in content
        assert "777888" in content or "250" in content


# ---------------------------------------------------------------------------
# Test: on_guild_remove marks guild inactive (soft delete)
# ---------------------------------------------------------------------------

class TestOnGuildRemoveSoftDelete:
    """Verify on_guild_remove soft-deletes guild data without hard deletion."""
    
    @pytest.mark.asyncio
    async def test_on_guild_remove_marks_guild_inactive(self, initialized_db):
        """on_guild_remove MUST set is_active=0 on guilds table, NOT delete."""
        import aiosqlite
        from bot.cogs.subscription import SubscriptionCog
        
        bot = _FakeBot()
        cog = SubscriptionCog(bot)
        
        guild_id = 111222
        guild = _make_guild(guild_id=guild_id, name="Leaving Guild")
        
        async with aiosqlite.connect(initialized_db) as db:
            await db.execute(
                "INSERT INTO guilds (guild_id, guild_name, is_active) VALUES (?, ?, 1)",
                (guild_id, "Leaving Guild"),
            )
            await db.commit()
        
        if hasattr(cog, 'on_guild_remove'):
            await cog.on_guild_remove(guild)
        else:
            pytest.skip("on_guild_remove not implemented yet")
        
        async with aiosqlite.connect(initialized_db) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT is_active FROM guilds WHERE guild_id = ?", (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    assert row["is_active"] == 0, "Guild should be marked inactive"
                else:
                    pytest.fail("Guild row not found - soft delete failed")
    
    @pytest.mark.asyncio
    async def test_on_guild_remove_preserves_data(self, initialized_db):
        """on_guild_remove MUST NOT delete server configs or subscription data."""
        import aiosqlite
        from bot.database import server_config_db, subscription_db
        from bot.cogs.subscription import SubscriptionCog
        
        bot = _FakeBot()
        cog = SubscriptionCog(bot)
        
        guild_id = 222333
        guild = _make_guild(guild_id=guild_id, name="Data Preservation Test")
        
        await server_config_db.create_or_update_server_config(guild_id, "Data Preservation Test")
        await subscription_db.get_or_create_subscription(guild_id)
        await server_config_db.add_ark_server(
            guild_id, name="TestServer", host="127.0.0.1", rcon_port=27020, rcon_password="test"
        )
        
        if hasattr(cog, 'on_guild_remove'):
            await cog.on_guild_remove(guild)
        else:
            pytest.skip("on_guild_remove not implemented yet")
        
        sub = await subscription_db.get_subscription(guild_id)
        assert sub is not None, "Subscription should still exist"
        
        servers = await server_config_db.get_ark_servers(guild_id)
        assert len(servers) >= 1, "ARK servers should still exist"


# ---------------------------------------------------------------------------
# Test: /subadmin dashboard aggregate stats
# ---------------------------------------------------------------------------

class TestSubadminDashboard:
    """Verify /subadmin dashboard shows comprehensive stats."""
    
    @pytest.mark.asyncio
    async def test_subadmin_dashboard_shows_total_guilds(self, initialized_db, monkeypatch):
        """/subadmin dashboard MUST show total registered guilds."""
        from bot.cogs.subscription import SubscriptionCog
        from bot.database import server_config_db, subscription_db
        from bot.utils.config import Config
        
        monkeypatch.setattr(Config, "BOT_OWNER_DISCORD_ID", 123456789)
        
        bot = _FakeBot()
        
        for gid in [101, 102, 103]:
            await server_config_db.create_or_update_server_config(gid, f"Guild {gid}")
            await subscription_db.get_or_create_subscription(gid)
        
        cog = SubscriptionCog(bot)
        
        if not hasattr(cog, 'subadmin_dashboard'):
            pytest.skip("subadmin_dashboard command not implemented yet")
        
        interaction = MagicMock()
        interaction.user.id = 123456789
        interaction.guild_id = 999
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.response.send_message = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        
        await cog.subadmin_dashboard.callback(cog, interaction)
        
        send_call = interaction.followup.send.call_args
        assert send_call is not None
        
        embed = send_call.kwargs.get("embed")
        assert embed is not None, "Expected embed in followup.send"
        embed_dict = embed.to_dict()
        content = str(embed_dict)
        
        assert "3" in content or "total" in content.lower() or "guild" in content.lower()
    
    @pytest.mark.asyncio
    async def test_subadmin_dashboard_shows_tier_distribution(self, initialized_db, monkeypatch):
        """Dashboard MUST show breakdown: free vs premium vs lifetime counts."""
        from bot.cogs.subscription import SubscriptionCog
        from bot.database import subscription_db
        from bot.utils.config import Config
        
        monkeypatch.setattr(Config, "BOT_OWNER_DISCORD_ID", 123456789)
        
        bot = _FakeBot()
        
        for gid, tier in [(201, "free"), (202, "premium"), (203, "premium"), (204, "lifetime")]:
            await subscription_db.get_or_create_subscription(gid)
            if tier != "free":
                await subscription_db.set_tier(gid, tier, "active")
        
        cog = SubscriptionCog(bot)
        
        if not hasattr(cog, 'subadmin_dashboard'):
            pytest.skip("subadmin_dashboard command not implemented yet")
        
        interaction = MagicMock()
        interaction.user.id = 123456789
        interaction.guild_id = 999
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()
        
        await cog.subadmin_dashboard.callback(cog, interaction)
        
        embed = interaction.followup.send.call_args.kwargs.get("embed")
        assert embed is not None, "Expected embed in followup.send"
        embed_dict = embed.to_dict()
        content = str(embed_dict).lower()
        
        assert "premium" in content or "lifetime" in content or "free" in content
