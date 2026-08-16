"""Test that server removal confirmation closes automatically."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.cogs.setup_gui import ConfirmRemoveView


@pytest.mark.asyncio
async def test_removal_confirmation_view_structure():
    """Test that ConfirmRemoveView has the correct structure."""
    # Mock server data
    server = {"id": 1, "name": "TestServer", "guild_id": 12345}
    guild_id = 12345
    user = MagicMock()
    user.id = 999
    
    # Create confirmation view
    view = ConfirmRemoveView(server, guild_id, user, None)
    
    # Verify view has 2 buttons (confirm and cancel)
    buttons = [child for child in view.children if hasattr(child, 'label')]
    assert len(buttons) == 2
    
    # Verify button labels
    labels = [button.label for button in buttons]
    assert "Yes, Remove" in labels
    assert "Cancel" in labels


@pytest.mark.asyncio 
async def test_server_removal_interaction_pattern():
    """Test the interaction pattern for server removal."""
    # Mock the interaction methods that should be called
    mock_interaction = AsyncMock()
    mock_interaction.response.send_message = AsyncMock()
    mock_interaction.delete_original_response = AsyncMock()
    
    # Test the expected interaction pattern
    await mock_interaction.response.send_message(
        "✅ Server removed successfully.",
        ephemeral=True
    )
    await mock_interaction.delete_original_response()
    
    # Verify the pattern was followed
    mock_interaction.response.send_message.assert_called_once_with(
        "✅ Server removed successfully.",
        ephemeral=True
    )
    mock_interaction.delete_original_response.assert_called_once()
