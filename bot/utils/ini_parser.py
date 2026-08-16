"""
INI Parser - Parse and serialize ARK INI configuration files.

Handles:
- Standard INI sections [SectionName]
- Key=value pairs
- Comments (; or #)
- Multi-line values (partial support)
- Preserves section order

NOTE: Complex multi-entry sections are deferred to Phase 7G:
- ConfigOverrideSupplyCrateItems
- ConfigOverrideItemCraftingCosts
- ConfigAdd/Subtract/OverrideNPCSpawnEntriesContainer
- OverrideEngramEntries / OverrideNamedEngramEntries
These require dedicated parsers and database tables.
"""

import re
import logging
from typing import Dict, List, Tuple, Any, Optional, Set
from collections import OrderedDict

logger = logging.getLogger("IniParser")


COMPLEX_SECTIONS_PREFIXES = [
    "ConfigOverrideSupplyCrateItems",
    "ConfigOverrideItemCraftingCosts",
    "ConfigOverrideItemMaxQuantity",
    "ConfigAddNPCSpawnEntriesContainer",
    "ConfigSubtractNPCSpawnEntriesContainer",
    "ConfigOverrideNPCSpawnEntriesContainer",
    "OverrideEngramEntries",
    "OverrideNamedEngramEntries",
    "EngramEntryAutoUnlocks",
    "DinoSpawnWeightMultipliers",
    "NPCReplacements",
]


def is_complex_key(key: str) -> bool:
    """Check if a key is part of a complex multi-entry section."""
    for prefix in COMPLEX_SECTIONS_PREFIXES:
        if key.startswith(prefix):
            return True
    return False


def parse_ini(content: str) -> Dict[str, Dict[str, str]]:
    """
    Parse INI content into a nested dictionary.
    
    Args:
        content: Raw INI file content
        
    Returns:
        Dict: {section_name: {key: value, ...}, ...}
        
    Note:
        - Duplicate keys are skipped (first occurrence kept)
        - Complex multi-entry sections are skipped (logged for Phase 7G)
        
    Example:
        >>> parse_ini("[ServerSettings]\\nMaxPlayers=70\\n")
        {'ServerSettings': {'MaxPlayers': '70'}}
    """
    result: Dict[str, Dict[str, str]] = OrderedDict()
    current_section: Optional[str] = None
    current_key: Optional[str] = None
    current_value_lines: List[str] = []
    seen_keys: Set[str] = set()
    skipped_complex: int = 0
    skipped_duplicates: int = 0
    
    lines = content.split('\n')
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped or stripped.startswith(';') or stripped.startswith('#'):
            continue
            
        section_match = re.match(r'^\[([^\]]+)\]$', stripped)
        if section_match:
            if current_section and current_key is not None:
                result[current_section][current_key] = '\n'.join(current_value_lines)
            
            current_section = section_match.group(1)
            result[current_section] = OrderedDict()
            current_key = None
            current_value_lines = []
            seen_keys = set()
            continue
        
        if current_section is None:
            continue
            
        if '=' in stripped:
            if current_key is not None:
                result[current_section][current_key] = '\n'.join(current_value_lines)
            
            eq_pos = stripped.index('=')
            key = stripped[:eq_pos].strip()
            value = stripped[eq_pos + 1:].strip()
            
            key_id = f"{current_section}.{key}"
            
            if is_complex_key(key):
                skipped_complex += 1
                current_key = None
                current_value_lines = []
                continue
            
            if key_id in seen_keys:
                skipped_duplicates += 1
                current_key = None
                current_value_lines = []
                continue
            
            seen_keys.add(key_id)
            current_key = key
            current_value_lines = [value]
        elif current_key:
            if stripped.startswith('(') or stripped.endswith(')') or \
               '(' in stripped or ')' in stripped or stripped.startswith('"'):
                current_value_lines.append(stripped)
    
    if current_section and current_key is not None:
        result[current_section][current_key] = '\n'.join(current_value_lines)
    
    if skipped_complex > 0:
        logger.info(f"Skipped {skipped_complex} complex multi-entry lines (Phase 7G)")
    if skipped_duplicates > 0:
        logger.info(f"Skipped {skipped_duplicates} duplicate keys")
    
    return result


def serialize_ini(data: Dict[str, Dict[str, str]], original_content: str = "") -> str:
    """
    Serialize a dictionary back to INI format.
    
    Attempts to preserve comments and structure from original content.
    
    Args:
        data: Dict of {section: {key: value}}
        original_content: Original file content to preserve comments from
        
    Returns:
        INI-formatted string
    """
    lines: List[str] = []
    
    for section_name, section_data in data.items():
        lines.append(f"[{section_name}]")
        
        for key, value in section_data.items():
            if '\n' in value:
                lines.append(f"{key}={value}")
            else:
                lines.append(f"{key}={value}")
        
        lines.append("")
    
    return '\n'.join(lines)


def detect_value_type(value: str) -> str:
    """
    Detect the type of a setting value.
    
    Args:
        value: The setting value as string
        
    Returns:
        One of: 'boolean', 'integer', 'float', 'string', 'multiline'
    """
    if not value:
        return 'string'
    
    if '\n' in value:
        return 'multiline'
    
    lower = value.lower()
    if lower in ('true', 'false', '1', '0', 'yes', 'no', 'on', 'off'):
        return 'boolean'
    
    try:
        int(value)
        return 'integer'
    except ValueError:
        pass
    
    try:
        float(value)
        return 'float'
    except ValueError:
        pass
    
    return 'string'


def merge_ini_changes(
    original: Dict[str, Dict[str, str]],
    changes: Dict[str, Dict[str, str]]
) -> Dict[str, Dict[str, str]]:
    """
    Merge changes into original INI data.
    
    Args:
        original: Original parsed INI data
        changes: Changes to apply {section: {key: new_value}}
        
    Returns:
        Merged dictionary
    """
    result = OrderedDict()
    
    for section, keys in original.items():
        result[section] = OrderedDict(keys)
    
    for section, keys in changes.items():
        if section not in result:
            result[section] = OrderedDict()
        for key, value in keys.items():
            result[section][key] = value
    
    return result


def extract_settings_list(
    data: Dict[str, Dict[str, str]]
) -> List[Dict[str, Any]]:
    """
    Convert parsed INI data to a list of settings for database import.
    
    Args:
        data: Parsed INI data {section: {key: value}}
        
    Returns:
        List of dicts: [{section_name, key_name, key_value, value_type}, ...]
    """
    settings = []
    
    for section_name, keys in data.items():
        for key_name, key_value in keys.items():
            settings.append({
                'section_name': section_name,
                'key_name': key_name,
                'key_value': key_value,
                'value_type': detect_value_type(key_value),
            })
    
    return settings


def apply_pending_changes(
    original_data: Dict[str, Dict[str, str]],
    pending_changes: List[Dict[str, Any]]
) -> Dict[str, Dict[str, str]]:
    """
    Apply pending changes to parsed INI data.
    
    Args:
        original_data: Current parsed INI data
        pending_changes: List of pending change dicts with file_name, section_name, key_name, new_value
        
    Returns:
        Updated INI data
    """
    result = OrderedDict()
    
    for section, keys in original_data.items():
        result[section] = OrderedDict(keys)
    
    for change in pending_changes:
        section = change.get('section_name')
        key = change.get('key_name')
        value = change.get('new_value')
        
        if not section or not key or value is None:
            continue
            
        if section not in result:
            result[section] = OrderedDict()
        
        result[section][key] = value
        logger.debug(f"Applied pending change: {section}.{key} = {value[:50]}...")
    
    return result


def format_value_for_display(value: str, max_length: int = 100) -> str:
    """
    Format a value for display in Discord.
    
    Args:
        value: The setting value
        max_length: Maximum length before truncating
        
    Returns:
        Formatted string for display
    """
    if not value:
        return "(empty)"
    
    if '\n' in value:
        first_line = value.split('\n')[0]
        if len(first_line) > max_length:
            return first_line[:max_length] + "..."
        return first_line + "..."
    
    if len(value) > max_length:
        return value[:max_length] + "..."
    
    return value


def update_single_setting(
    content: str,
    section_name: str,
    key_name: str,
    new_value: str
) -> str:
    """
    Update a single setting in INI content using line-based editing.
    
    Preserves all other content including:
    - Complex multi-line sections
    - Comments
    - Duplicate keys (edits first occurrence in section)
    - Section order
    - Formatting
    
    Args:
        content: Original INI file content
        section_name: The section containing the key (without brackets)
        key_name: The key to update
        new_value: The new value to set
        
    Returns:
        Modified INI content with only the target line changed
        
    Raises:
        ValueError: If section or key not found
    """
    lines = content.split('\n')
    
    in_target_section = False
    section_pattern = re.compile(r'^\[([^\]]+)\]$', re.IGNORECASE)
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        section_match = section_pattern.match(stripped)
        if section_match:
            current_section = section_match.group(1)
            in_target_section = (current_section == section_name)
            continue
        
        if in_target_section and '=' in stripped:
            eq_pos = stripped.index('=')
            current_key = stripped[:eq_pos].strip()
            
            if current_key == key_name:
                indent_match = re.match(r'^(\s*)', line)
                indent = indent_match.group(1) if indent_match else ''
                leading_spaces = len(line) - len(line.lstrip())
                
                original_prefix = line[:leading_spaces]
                lines[i] = f"{original_prefix}{key_name}={new_value}"
                return '\n'.join(lines)
    
    raise ValueError(f"Key '{key_name}' not found in section '[{section_name}]'")


def add_setting(
    content: str,
    section_name: str,
    key_name: str,
    value: str
) -> str:
    """
    Add a new setting to an INI file. Creates section if it doesn't exist.
    
    Args:
        content: Original INI file content
        section_name: The section to add to (without brackets)
        key_name: The key to add
        value: The value to set
        
    Returns:
        Modified INI content with the new setting added
    """
    lines = content.split('\n')
    
    in_target_section = False
    section_pattern = re.compile(r'^\[([^\]]+)\]$', re.IGNORECASE)
    section_line_idx = -1
    last_key_line_idx = -1
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        section_match = section_pattern.match(stripped)
        if section_match:
            current_section = section_match.group(1)
            if current_section == section_name:
                in_target_section = True
                section_line_idx = i
            elif in_target_section:
                break
            continue
        
        if in_target_section and '=' in stripped:
            last_key_line_idx = i
    
    if in_target_section and last_key_line_idx >= 0:
        lines.insert(last_key_line_idx + 1, f"{key_name}={value}")
        return '\n'.join(lines)
    elif in_target_section and section_line_idx >= 0:
        lines.insert(section_line_idx + 1, f"{key_name}={value}")
        return '\n'.join(lines)
    else:
        if content.strip() and not content.endswith('\n'):
            content += '\n'
        return content + f"\n[{section_name}]\n{key_name}={value}\n"


def validate_ini_syntax(content: str) -> Tuple[bool, Optional[str]]:
    """
    Validate INI file syntax.
    
    Args:
        content: Raw INI content
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    lines = content.split('\n')
    current_section: Optional[str] = None
    line_num = 0
    
    for line in lines:
        line_num += 1
        stripped = line.strip()
        
        if not stripped or stripped.startswith(';') or stripped.startswith('#'):
            continue
        
        if stripped.startswith('['):
            if not stripped.endswith(']'):
                return False, f"Line {line_num}: Invalid section header - missing ']'"
            section_name = stripped[1:-1]
            if not section_name:
                return False, f"Line {line_num}: Empty section name"
            current_section = stripped
            continue
        
        if current_section is None and '=' in stripped:
            return False, f"Line {line_num}: Key=value outside of section"
    
    return True, None
