"""
Tests for bot/utils/log_parser.py - NO MOCKS VERSION

Covers: parse_server_startup_info (legacy), _find_agent_for_server.
Minimal tests without I/O operations.
"""

import pytest
import pytest_asyncio
import asyncio


@pytest.mark.asyncio
async def test_find_agent_for_server_no_manager():
    """Test _find_agent_for_server returns None when no agent_manager provided."""
    from bot.utils.log_parser import _find_agent_for_server

    result = await _find_agent_for_server("TestServer", None)
    assert result is None


@pytest.mark.asyncio
async def test_parse_server_startup_info_legacy():
    """Test legacy parse_server_startup_info returns defaults."""
    from bot.utils.log_parser import parse_server_startup_info

    # Call with a dummy path - should return defaults
    result = parse_server_startup_info("dummy_path")
    assert result["max_players"] is None
    assert result["cluster_id"] is None
    assert result["cluster_folder_path"] is None
