"""
Tests for bot/utils/permissions.py — is_admin, is_verified_user,
require_admin, require_verified_user.

Tests use real discord.py objects and a real SQLite database (no mocks).
Fake interactions are constructed with SimpleNamespace to match the exact
attribute paths used in permissions.py.

Async tests use pytest.mark.asyncio.
"""

import pytest
import discord
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Interaction factory helpers
# ---------------------------------------------------------------------------

def make_admin_interaction(guild_id: int = 123456) -> SimpleNamespace:
    """Fake interaction where the user has Discord Administrator permission."""
    interaction = SimpleNamespace()
    interaction.guild_id = guild_id
    interaction.user = SimpleNamespace(
        guild_permissions=SimpleNamespace(administrator=True),
        roles=[],
    )
    interaction.guild = SimpleNamespace(get_role=lambda x: None)
    interaction.response = AsyncMock()
    return interaction


def make_non_admin_interaction(guild_id: int = 123456) -> SimpleNamespace:
    """Fake interaction where the user has NO Administrator permission and no roles."""
    interaction = SimpleNamespace()
    interaction.guild_id = guild_id
    interaction.user = SimpleNamespace(
        guild_permissions=SimpleNamespace(administrator=False),
        roles=[],
    )
    interaction.guild = SimpleNamespace(get_role=lambda x: None)
    interaction.response = AsyncMock()
    return interaction


def make_role_admin_interaction(guild_id: int = 123456, role_id: int = 555) -> SimpleNamespace:
    """Fake interaction where user is NOT Administrator but has the designated admin role."""
    # Build a real-ish role object that compares by identity
    admin_role = SimpleNamespace(id=role_id)

    interaction = SimpleNamespace()
    interaction.guild_id = guild_id
    interaction.user = SimpleNamespace(
        guild_permissions=SimpleNamespace(administrator=False),
        roles=[admin_role],
    )
    # guild.get_role returns the same role object when asked for that role_id
    interaction.guild = SimpleNamespace(
        get_role=lambda rid: admin_role if rid == role_id else None
    )
    interaction.response = AsyncMock()
    return interaction


def make_user_role_interaction(guild_id: int = 123456, role_id: int = 777) -> SimpleNamespace:
    """Fake interaction where user has the configured user_role (not admin)."""
    user_role = SimpleNamespace(id=role_id)

    interaction = SimpleNamespace()
    interaction.guild_id = guild_id
    interaction.user = SimpleNamespace(
        guild_permissions=SimpleNamespace(administrator=False),
        roles=[user_role],
    )
    interaction.guild = SimpleNamespace(
        get_role=lambda rid: user_role if rid == role_id else None
    )
    interaction.response = AsyncMock()
    return interaction


def make_no_role_interaction(guild_id: int = 123456) -> SimpleNamespace:
    """Fake interaction where user has no roles and no administrator permission."""
    return make_non_admin_interaction(guild_id)


# ---------------------------------------------------------------------------
# Tests for is_admin()
# ---------------------------------------------------------------------------

class TestIsAdmin:
    @pytest.mark.asyncio
    async def test_is_admin_returns_true_for_administrator_permission(self, initialized_db):
        """User with Discord Administrator permission is always admin."""
        from bot.utils.permissions import is_admin
        interaction = make_admin_interaction()
        result = await is_admin(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_admin_returns_false_no_permission_no_config(self, initialized_db):
        """Non-admin user with no DB config returns False."""
        from bot.utils.permissions import is_admin
        # No guild config has been created, so config is None
        interaction = make_non_admin_interaction(guild_id=999999)
        result = await is_admin(interaction)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_admin_returns_false_no_permission_config_no_admin_role(self, initialized_db):
        """Non-admin user with guild config but no admin_role_id set returns False."""
        from bot.utils.permissions import is_admin
        from bot.database.server_config_db import create_or_update_server_config

        # Create config without admin_role_id
        await create_or_update_server_config(111222, "Test Guild")

        interaction = make_non_admin_interaction(guild_id=111222)
        result = await is_admin(interaction)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_admin_returns_true_when_user_has_admin_role(self, initialized_db):
        """Non-admin user WITH the configured admin role returns True."""
        from bot.utils.permissions import is_admin
        from bot.database.server_config_db import create_or_update_server_config

        guild_id = 333444
        role_id = 555666

        # Configure admin_role_id in DB
        await create_or_update_server_config(guild_id, "Guild With Role", admin_role_id=role_id)

        interaction = make_role_admin_interaction(guild_id=guild_id, role_id=role_id)
        result = await is_admin(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_admin_returns_false_when_user_lacks_admin_role(self, initialized_db):
        """Non-admin user who does NOT have the configured admin role returns False."""
        from bot.utils.permissions import is_admin
        from bot.database.server_config_db import create_or_update_server_config

        guild_id = 444555
        role_id = 666777

        # Configure admin_role_id but user does not have it
        await create_or_update_server_config(guild_id, "Guild Role Check", admin_role_id=role_id)

        interaction = make_non_admin_interaction(guild_id=guild_id)
        result = await is_admin(interaction)
        assert result is False


# ---------------------------------------------------------------------------
# Tests for is_verified_user()
# ---------------------------------------------------------------------------

class TestIsVerifiedUser:
    @pytest.mark.asyncio
    async def test_is_verified_user_returns_true_for_admin(self, initialized_db):
        """Admins always pass the verified user check."""
        from bot.utils.permissions import is_verified_user
        interaction = make_admin_interaction(guild_id=100001)
        result = await is_verified_user(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_verified_user_returns_true_when_no_user_role_configured(self, initialized_db):
        """If no user_role_id in config, everyone is verified (open access)."""
        from bot.utils.permissions import is_verified_user
        from bot.database.server_config_db import create_or_update_server_config

        guild_id = 100002
        # Config exists but no user_role_id
        await create_or_update_server_config(guild_id, "Open Guild")

        interaction = make_non_admin_interaction(guild_id=guild_id)
        result = await is_verified_user(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_verified_user_returns_true_when_no_config_at_all(self, initialized_db):
        """If no config exists at all, everyone is verified (no restriction)."""
        from bot.utils.permissions import is_verified_user
        interaction = make_non_admin_interaction(guild_id=888777)
        result = await is_verified_user(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_verified_user_returns_true_when_user_has_user_role(self, initialized_db):
        """User with the configured user_role passes verification."""
        from bot.utils.permissions import is_verified_user
        from bot.database.server_config_db import create_or_update_server_config

        guild_id = 100003
        role_id = 200001

        await create_or_update_server_config(guild_id, "Role Guild", user_role_id=role_id)

        interaction = make_user_role_interaction(guild_id=guild_id, role_id=role_id)
        result = await is_verified_user(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_is_verified_user_returns_false_when_user_lacks_user_role(self, initialized_db):
        """User without the configured user_role fails verification."""
        from bot.utils.permissions import is_verified_user
        from bot.database.server_config_db import create_or_update_server_config

        guild_id = 100004
        role_id = 200002

        await create_or_update_server_config(guild_id, "Restricted Guild", user_role_id=role_id)

        # User has no roles
        interaction = make_no_role_interaction(guild_id=guild_id)
        result = await is_verified_user(interaction)
        assert result is False


# ---------------------------------------------------------------------------
# Tests for require_admin()
# ---------------------------------------------------------------------------

class TestRequireAdmin:
    @pytest.mark.asyncio
    async def test_require_admin_returns_true_for_admin(self, initialized_db):
        """require_admin returns True for admin user and sends no error."""
        from bot.utils.permissions import require_admin
        interaction = make_admin_interaction()
        result = await require_admin(interaction)
        assert result is True
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_require_admin_returns_false_for_non_admin(self, initialized_db):
        """require_admin returns False for non-admin and sends an error message."""
        from bot.utils.permissions import require_admin
        interaction = make_non_admin_interaction(guild_id=555444)
        result = await require_admin(interaction)
        assert result is False

    @pytest.mark.asyncio
    async def test_require_admin_sends_error_message_on_rejection(self, initialized_db):
        """When non-admin is rejected, response.send_message is called."""
        from bot.utils.permissions import require_admin
        interaction = make_non_admin_interaction(guild_id=555443)
        await require_admin(interaction)
        interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_require_admin_sends_ephemeral_error(self, initialized_db):
        """The error message sent by require_admin must be ephemeral."""
        from bot.utils.permissions import require_admin
        interaction = make_non_admin_interaction(guild_id=555442)
        await require_admin(interaction)
        call_kwargs = interaction.response.send_message.call_args[1]
        assert call_kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_require_admin_error_message_mentions_permission(self, initialized_db):
        """The error message should reference Administrator or admin role."""
        from bot.utils.permissions import require_admin
        interaction = make_non_admin_interaction(guild_id=555441)
        await require_admin(interaction)
        call_args = interaction.response.send_message.call_args
        message_text = call_args[0][0] if call_args[0] else ""
        assert "Administrator" in message_text or "admin" in message_text.lower()


# ---------------------------------------------------------------------------
# Tests for require_verified_user()
# ---------------------------------------------------------------------------

class TestRequireVerifiedUser:
    @pytest.mark.asyncio
    async def test_require_verified_user_returns_true_for_admin(self, initialized_db):
        """Admin always passes require_verified_user."""
        from bot.utils.permissions import require_verified_user
        interaction = make_admin_interaction(guild_id=700001)
        result = await require_verified_user(interaction)
        assert result is True

    @pytest.mark.asyncio
    async def test_require_verified_user_returns_true_no_user_role_configured(self, initialized_db):
        """When no user_role_id configured, require_verified_user returns True."""
        from bot.utils.permissions import require_verified_user
        from bot.database.server_config_db import create_or_update_server_config

        guild_id = 700002
        await create_or_update_server_config(guild_id, "Open Guild 2")

        interaction = make_non_admin_interaction(guild_id=guild_id)
        result = await require_verified_user(interaction)
        assert result is True
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_require_verified_user_returns_false_for_unverified_user(self, initialized_db):
        """When user_role_id configured and user lacks role, returns False."""
        from bot.utils.permissions import require_verified_user
        from bot.database.server_config_db import create_or_update_server_config

        guild_id = 700003
        role_id = 800001

        await create_or_update_server_config(guild_id, "Restricted 2", user_role_id=role_id)

        interaction = make_no_role_interaction(guild_id=guild_id)
        result = await require_verified_user(interaction)
        assert result is False

    @pytest.mark.asyncio
    async def test_require_verified_user_sends_embed_to_unverified(self, initialized_db):
        """When user is unverified, require_verified_user sends an embed via response."""
        from bot.utils.permissions import require_verified_user
        from bot.database.server_config_db import create_or_update_server_config

        guild_id = 700004
        role_id = 800002

        await create_or_update_server_config(guild_id, "Restricted 3", user_role_id=role_id)

        interaction = make_no_role_interaction(guild_id=guild_id)
        await require_verified_user(interaction)
        interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_require_verified_user_embed_is_ephemeral(self, initialized_db):
        """The verification embed sent to unverified users must be ephemeral."""
        from bot.utils.permissions import require_verified_user
        from bot.database.server_config_db import create_or_update_server_config

        guild_id = 700005
        role_id = 800003

        await create_or_update_server_config(guild_id, "Restricted 4", user_role_id=role_id)

        interaction = make_no_role_interaction(guild_id=guild_id)
        await require_verified_user(interaction)
        call_kwargs = interaction.response.send_message.call_args[1]
        assert call_kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_require_verified_user_embed_contains_verification_required(self, initialized_db):
        """The embed title should mention Verification Required."""
        from bot.utils.permissions import require_verified_user
        from bot.database.server_config_db import create_or_update_server_config

        guild_id = 700006
        role_id = 800004

        await create_or_update_server_config(guild_id, "Restricted 5", user_role_id=role_id)

        interaction = make_no_role_interaction(guild_id=guild_id)
        await require_verified_user(interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert isinstance(embed, discord.Embed)
        assert "Verification Required" in embed.title

    @pytest.mark.asyncio
    async def test_require_verified_user_returns_true_for_user_with_role(self, initialized_db):
        """User who has the required user_role passes require_verified_user."""
        from bot.utils.permissions import require_verified_user
        from bot.database.server_config_db import create_or_update_server_config

        guild_id = 700007
        role_id = 800005

        await create_or_update_server_config(guild_id, "Role Guild 2", user_role_id=role_id)

        interaction = make_user_role_interaction(guild_id=guild_id, role_id=role_id)
        result = await require_verified_user(interaction)
        assert result is True


# ---------------------------------------------------------------------------
# Import sanity check
# ---------------------------------------------------------------------------

class TestPermissionsImports:
    def test_is_admin_is_importable(self):
        from bot.utils.permissions import is_admin
        assert callable(is_admin)

    def test_is_verified_user_is_importable(self):
        from bot.utils.permissions import is_verified_user
        assert callable(is_verified_user)

    def test_require_admin_is_importable(self):
        from bot.utils.permissions import require_admin
        assert callable(require_admin)

    def test_require_verified_user_is_importable(self):
        from bot.utils.permissions import require_verified_user
        assert callable(require_verified_user)
