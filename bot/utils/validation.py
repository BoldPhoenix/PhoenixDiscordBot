"""
Shared validation utilities for security boundaries.

All user-derived input that crosses a trust boundary (RCON commands,
service names for subprocess, SQL column names from kwargs) must be
validated through these functions.
"""

import re

_SAFE_RCON_INPUT = re.compile(r'^[a-zA-Z0-9_ .\-]+$')
_SAFE_SERVICE_NAME = re.compile(r'^[a-zA-Z0-9_\-]+$')


def validate_rcon_input(value: str) -> bool:
    """Validate that a value is safe to include in an RCON command."""
    return bool(value) and bool(_SAFE_RCON_INPUT.match(value)) and len(value) <= 100


def validate_service_name(value: str) -> bool:
    """Validate that a service name is safe for subprocess calls."""
    return bool(value) and bool(_SAFE_SERVICE_NAME.match(value)) and len(value) <= 256


def validate_sql_columns(kwargs: dict, allowed: set) -> dict:
    """Filter kwargs to only contain allowed column names.

    Args:
        kwargs: Dict of column_name -> value from caller
        allowed: Set of permitted column name strings

    Returns:
        Filtered dict containing only keys present in allowed set
    """
    return {k: v for k, v in kwargs.items() if k in allowed}
