"""
Tests for bot/utils/player_linking.py — require_linked_player,
create_link_success_embed, create_eos_id_help_embed.

Tests use real discord.py objects and a real SQLite database (no mocks).
Fake interactions are constructed with SimpleNamespace.

All async tests use pytest.mark.asyncio.
"""

import pytest
import discord
from types import SimpleNamespace
from unittest.mock import AsyncMock

# Test constants
GUILD_ID = 999888777


# ---------------------------------------------------------------------------
# Interaction factory helper
# ---------------------------------------------------------------------------

def make_interaction(user_id: int = 111222333, guild_id: int = GUILD_ID) -> SimpleNamespace:
    """Create a minimal fake Discord interaction for player linking tests."""
    interaction = SimpleNamespace()
    interaction.user = SimpleNamespace(id=user_id)
    interaction.guild_id = guild_id
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


# ---------------------------------------------------------------------------
# Tests for create_link_success_embed()
# ---------------------------------------------------------------------------

class TestCreateLinkSuccessEmbed:
    def test_returns_discord_embed(self):
        from bot.utils.player_linking import create_link_success_embed
        embed = create_link_success_embed("0002abc123def456")
        assert isinstance(embed, discord.Embed)

    def test_embed_has_green_color(self):
        from bot.utils.player_linking import create_link_success_embed
        embed = create_link_success_embed("0002abc123def456")
        assert embed.color == discord.Color.green()

    def test_embed_description_contains_eos_id(self):
        from bot.utils.player_linking import create_link_success_embed
        eos_id = "0002abc123def456"
        embed = create_link_success_embed(eos_id)
        assert eos_id in embed.description

    def test_embed_title_contains_linked_successfully(self):
        from bot.utils.player_linking import create_link_success_embed
        embed = create_link_success_embed("0002abc123def456")
        assert "Linked Successfully" in embed.title or "Account Linked" in embed.title

    def test_embed_with_different_eos_id(self):
        from bot.utils.player_linking import create_link_success_embed
        eos_id = "0001zxcvbnmlkjhg"
        embed = create_link_success_embed(eos_id)
        assert eos_id in embed.description

    def test_embed_has_at_least_one_field(self):
        from bot.utils.player_linking import create_link_success_embed
        embed = create_link_success_embed("0002abc123def456")
        assert len(embed.fields) >= 1


# ---------------------------------------------------------------------------
# Tests for create_eos_id_help_embed()
# ---------------------------------------------------------------------------

class TestCreateEosIdHelpEmbed:
    def test_returns_discord_embed(self):
        from bot.utils.player_linking import create_eos_id_help_embed
        embed = create_eos_id_help_embed()
        assert isinstance(embed, discord.Embed)

    def test_embed_has_blue_color(self):
        from bot.utils.player_linking import create_eos_id_help_embed
        embed = create_eos_id_help_embed()
        assert embed.color == discord.Color.blue()

    def test_embed_has_exactly_4_fields(self):
        """Embed must have exactly 4 fields: Method 1, Method 2, What Does It Look Like, Once You Have It."""
        from bot.utils.player_linking import create_eos_id_help_embed
        embed = create_eos_id_help_embed()
        assert len(embed.fields) == 4

    def test_embed_title_contains_eos_id(self):
        from bot.utils.player_linking import create_eos_id_help_embed
        embed = create_eos_id_help_embed()
        assert "EOS ID" in embed.title or "How to Find" in embed.title

    def test_embed_field_names_cover_required_topics(self):
        """All four required topics must be present as field names."""
        from bot.utils.player_linking import create_eos_id_help_embed
        embed = create_eos_id_help_embed()
        field_names = [f.name for f in embed.fields]
        combined = " ".join(field_names)

        # Must have Method 1 and Method 2
        assert any("Method 1" in name for name in field_names)
        assert any("Method 2" in name for name in field_names)

        # Must have "What Does It Look Like" topic
        assert any("Look Like" in name or "What Does" in name for name in field_names)

        # Must have "Once You Have It" topic
        assert any("Once You Have" in name for name in field_names)

    def test_embed_description_mentions_ark(self):
        from bot.utils.player_linking import create_eos_id_help_embed
        embed = create_eos_id_help_embed()
        assert "ARK" in embed.description or "Epic" in embed.description

    def test_embed_field_method1_mentions_console(self):
        """Method 1 should describe using the in-game console."""
        from bot.utils.player_linking import create_eos_id_help_embed
        embed = create_eos_id_help_embed()
        method1 = next((f for f in embed.fields if "Method 1" in f.name), None)
        assert method1 is not None
        assert "Tab" in method1.value or "console" in method1.value.lower() or "ShowMyAdminManager" in method1.value

    def test_embed_example_eos_id_format(self):
        """At least one field should show the 16-char EOS ID format."""
        from bot.utils.player_linking import create_eos_id_help_embed
        embed = create_eos_id_help_embed()
        all_text = " ".join(f.value for f in embed.fields)
        # Should mention the 16-character format like "0002abc123def456"
        assert "0002" in all_text or "16 character" in all_text.lower() or "16)" in all_text


# ---------------------------------------------------------------------------
# Tests for require_linked_player() — happy path
# ---------------------------------------------------------------------------

class TestRequireLinkedPlayerLinked:
    @pytest.mark.asyncio
    async def test_returns_true_and_player_when_linked(self, full_db):
        """When player is linked, require_linked_player returns (True, player_dict)."""
        from bot.utils.player_linking import require_linked_player
        from bot.database.players_db import link_player

        user_id = 123456789
        eos_id = "0002abc123def456"
        await link_player(GUILD_ID, user_id, eos_id, "TestUser")

        interaction = make_interaction(user_id=user_id)
        result, player = await require_linked_player(interaction)

        assert result is True
        assert player is not None
        assert isinstance(player, dict)

    @pytest.mark.asyncio
    async def test_player_dict_contains_eos_id(self, full_db):
        """The returned player dict includes the eos_id."""
        from bot.utils.player_linking import require_linked_player
        from bot.database.players_db import link_player

        user_id = 234567890
        eos_id = "0002xyz789ghi012"
        await link_player(GUILD_ID, user_id, eos_id, "AnotherUser")

        interaction = make_interaction(user_id=user_id)
        result, player = await require_linked_player(interaction)

        assert result is True
        assert player["eos_id"] == eos_id

    @pytest.mark.asyncio
    async def test_does_not_send_message_when_linked(self, full_db):
        """When player is linked, no error embed is sent."""
        from bot.utils.player_linking import require_linked_player
        from bot.database.players_db import link_player

        user_id = 345678901
        eos_id = "0002def456abc789"
        await link_player(GUILD_ID, user_id, eos_id, "User3")

        interaction = make_interaction(user_id=user_id)
        await require_linked_player(interaction)

        interaction.response.send_message.assert_not_called()
        interaction.followup.send.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for require_linked_player() — not linked path
# ---------------------------------------------------------------------------

class TestRequireLinkedPlayerNotLinked:
    @pytest.mark.asyncio
    async def test_returns_false_and_none_when_not_linked(self, full_db):
        """When player is not linked, require_linked_player returns (False, None)."""
        from bot.utils.player_linking import require_linked_player

        # user_id that has NOT been linked
        interaction = make_interaction(user_id=999111222)
        result, player = await require_linked_player(interaction)

        assert result is False
        assert player is None

    @pytest.mark.asyncio
    async def test_sends_embed_when_not_linked(self, full_db):
        """When player is not linked, response.send_message is called with an embed."""
        from bot.utils.player_linking import require_linked_player

        interaction = make_interaction(user_id=888111222)
        await require_linked_player(interaction)

        interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_sends_ephemeral_embed_when_not_linked(self, full_db):
        """The embed sent to unlinked users must be ephemeral."""
        from bot.utils.player_linking import require_linked_player

        interaction = make_interaction(user_id=777111222)
        await require_linked_player(interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        assert call_kwargs.get("ephemeral") is True

    @pytest.mark.asyncio
    async def test_embed_has_blue_color_when_not_linked(self, full_db):
        """The help embed sent to unlinked users should have blue color."""
        from bot.utils.player_linking import require_linked_player

        interaction = make_interaction(user_id=666111222)
        await require_linked_player(interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert embed.color == discord.Color.blue()

    @pytest.mark.asyncio
    async def test_embed_has_link_account_title_when_not_linked(self, full_db):
        """The help embed title instructs user to link their account."""
        from bot.utils.player_linking import require_linked_player

        interaction = make_interaction(user_id=555111222)
        await require_linked_player(interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert "Link" in embed.title or "Account" in embed.title

    @pytest.mark.asyncio
    async def test_embed_has_multiple_fields_when_not_linked(self, full_db):
        """The help embed should have multiple fields guiding the user."""
        from bot.utils.player_linking import require_linked_player

        interaction = make_interaction(user_id=444111222)
        await require_linked_player(interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed = call_kwargs.get("embed")
        assert embed is not None
        assert len(embed.fields) >= 2


# ---------------------------------------------------------------------------
# Tests for require_linked_player() — defer=True path
# ---------------------------------------------------------------------------

class TestRequireLinkedPlayerDeferred:
    @pytest.mark.asyncio
    async def test_deferred_not_linked_uses_followup(self, full_db):
        """With defer=True and unlinked player, followup.send is used instead of response.send_message."""
        from bot.utils.player_linking import require_linked_player

        interaction = make_interaction(user_id=333111222)
        result, player = await require_linked_player(interaction, defer=True)

        assert result is False
        assert player is None
        interaction.followup.send.assert_called_once()
        interaction.response.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_deferred_calls_response_defer(self, full_db):
        """With defer=True, response.defer() is called before the DB lookup."""
        from bot.utils.player_linking import require_linked_player

        interaction = make_interaction(user_id=222111333)
        await require_linked_player(interaction, defer=True)

        interaction.response.defer.assert_called_once()

    @pytest.mark.asyncio
    async def test_deferred_linked_player_does_not_use_followup(self, full_db):
        """With defer=True and a linked player, followup.send is NOT called."""
        from bot.utils.player_linking import require_linked_player
        from bot.database.players_db import link_player

        user_id = 111333444
        eos_id = "0002linkeddeferred"
        await link_player(GUILD_ID, user_id, eos_id, "DeferUser")

        interaction = make_interaction(user_id=user_id)
        result, player = await require_linked_player(interaction, defer=True)

        assert result is True
        assert player is not None
        interaction.followup.send.assert_not_called()


# ---------------------------------------------------------------------------
# Import sanity check
# ---------------------------------------------------------------------------

class TestPlayerLinkingImports:
    def test_require_linked_player_is_importable(self):
        from bot.utils.player_linking import require_linked_player
        assert callable(require_linked_player)

    def test_create_link_success_embed_is_importable(self):
        from bot.utils.player_linking import create_link_success_embed
        assert callable(create_link_success_embed)

    def test_create_eos_id_help_embed_is_importable(self):
        from bot.utils.player_linking import create_eos_id_help_embed
        assert callable(create_eos_id_help_embed)
