"""
Loot Crate Parser - Parse ConfigOverrideSupplyCrateItems from Game.ini.

ARK uses a complex nested structure for loot crate overrides:
ConfigOverrideSupplyCrateItems=(
    SupplyCrateClassString="SupplyCrate_Level15_C",
    MinItemSets=1,
    MaxItemSets=1,
    bPreventDuplicates=True,
    ItemSets=(
        (
            MinNumItems=2,
            MaxNumItems=4,
            SetWeight=1.0,
            ItemEntries=(
                (
                    EntryWeight=1.0,
                    ItemClassStrings=("PrimalItem_WeaponStonePick_C"),
                    ItemsWeights=(1),
                    MinQuantity=1,
                    MaxQuantity=1,
                    MinQuality=0,
                    MaxQuality=0,
                    bForceBlueprint=False,
                    ChanceToBeBlueprintOverride=0.0
                )
            )
        )
    )
)
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("LootCrateParser")


def extract_crate_blocks(content: str) -> List[str]:
    """
    Extract all ConfigOverrideSupplyCrateItems blocks from INI content.
    
    Returns list of raw block strings (including the outer parentheses).
    """
    blocks = []
    pattern = r'ConfigOverrideSupplyCrateItems\s*=\s*\('
    
    for match in re.finditer(pattern, content):
        paren_start = match.end() - 1
        block = _extract_balanced_block(content[paren_start:])
        if block:
            blocks.append(block)
    
    return blocks


def _extract_balanced_block(content: str) -> Optional[str]:
    """Extract a balanced parentheses block starting from the first '('."""
    if not content or content[0] != '(':
        return None
    
    depth = 0
    in_string = False
    escape_next = False
    
    for i, char in enumerate(content):
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\' and in_string:
            escape_next = True
            continue
        
        if char == '"':
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth == 0:
                    return content[:i + 1]
    
    return None


def parse_crate_block(block: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single ConfigOverrideSupplyCrateItems block.
    
    Returns structured data:
    {
        'class_string': 'SupplyCrate_...',
        'min_item_sets': 1,
        'max_item_sets': 1,
        'prevent_duplicates': True,
        'item_sets': [
            {
                'min_items': 1,
                'max_items': 1,
                'weight': 1.0,
                'items': [...]
            }
        ]
    }
    """
    if not block:
        return None
    
    result = {
        'class_string': None,
        'min_item_sets': 1,
        'max_item_sets': 1,
        'prevent_duplicates': True,
        'item_sets': []
    }
    
    class_match = re.search(r'SupplyCrateClassString\s*=\s*"([^"]+)"', block)
    if class_match:
        result['class_string'] = class_match.group(1)
    
    min_sets_match = re.search(r'MinItemSets\s*=\s*(\d+)', block)
    if min_sets_match:
        result['min_item_sets'] = int(min_sets_match.group(1))
    
    max_sets_match = re.search(r'MaxItemSets\s*=\s*(\d+)', block)
    if max_sets_match:
        result['max_item_sets'] = int(max_sets_match.group(1))
    
    prevent_match = re.search(r'bPreventDuplicates\s*=\s*(True|False)', block, re.IGNORECASE)
    if prevent_match:
        result['prevent_duplicates'] = prevent_match.group(1).lower() == 'true'
    
    item_sets_match = re.search(r'ItemSets\s*=\s*\(', block)
    if item_sets_match:
        sets_start = item_sets_match.end() - 1
        sets_block = _extract_balanced_block(block[sets_start:])
        if sets_block:
            result['item_sets'] = _parse_item_sets(sets_block)
    
    return result if result['class_string'] else None


def _parse_item_sets(block: str) -> List[Dict[str, Any]]:
    """Parse ItemSets block into list of item sets."""
    item_sets = []
    
    inner = block[1:-1].strip()
    
    set_blocks = _split_top_level_tuples(inner)
    
    for set_block in set_blocks:
        item_set = _parse_single_item_set(set_block)
        if item_set:
            item_sets.append(item_set)
    
    return item_sets


def _split_top_level_tuples(content: str) -> List[str]:
    """Split content by top-level comma-separated tuples."""
    blocks = []
    current = []
    depth = 0
    in_string = False
    
    for char in content:
        if char == '"' and (not current or current[-1] != '\\'):
            in_string = not in_string
        
        if not in_string:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 0:
                block = ''.join(current).strip()
                if block:
                    blocks.append(block)
                current = []
                continue
        
        current.append(char)
    
    block = ''.join(current).strip()
    if block:
        blocks.append(block)
    
    return blocks


def _parse_single_item_set(block: str) -> Optional[Dict[str, Any]]:
    """Parse a single item set."""
    result = {
        'min_items': 1,
        'max_items': 1,
        'weight': 1.0,
        'items': []
    }
    
    if block.startswith('('):
        block = block[1:]
    if block.endswith(')'):
        block = block[:-1]
    
    min_match = re.search(r'MinNumItems\s*=\s*(\d+)', block)
    if min_match:
        result['min_items'] = int(min_match.group(1))
    
    max_match = re.search(r'MaxNumItems\s*=\s*(\d+)', block)
    if max_match:
        result['max_items'] = int(max_match.group(1))
    
    weight_match = re.search(r'SetWeight\s*=\s*([\d.]+)', block)
    if weight_match:
        result['weight'] = float(weight_match.group(1))
    
    entries_match = re.search(r'ItemEntries\s*=\s*\(', block)
    if entries_match:
        entries_start = entries_match.end() - 1
        entries_block = _extract_balanced_block(block[entries_start:])
        if entries_block:
            result['items'] = _parse_item_entries(entries_block)
    
    return result


def _parse_item_entries(block: str) -> List[Dict[str, Any]]:
    """Parse ItemEntries block into list of items."""
    items = []
    
    inner = block[1:-1].strip()
    entry_blocks = _split_top_level_tuples(inner)
    
    for entry_block in entry_blocks:
        item = _parse_single_item_entry(entry_block)
        if item:
            items.append(item)
    
    return items


def _parse_single_item_entry(block: str) -> Optional[Dict[str, Any]]:
    """Parse a single item entry."""
    result = {
        'class_string': None,
        'min_quantity': 1,
        'max_quantity': 1,
        'quality_min': 0,
        'quality_max': 0,
        'chance_to_be_blueprint': 0
    }
    
    if block.startswith('('):
        block = block[1:]
    if block.endswith(')'):
        block = block[:-1]
    
    class_match = re.search(r'ItemClassStrings\s*=\s*\(\s*"([^"]+)"', block)
    if class_match:
        result['class_string'] = class_match.group(1)
    else:
        return None
    
    min_qty_match = re.search(r'MinQuantity\s*=\s*(\d+)', block)
    if min_qty_match:
        result['min_quantity'] = int(min_qty_match.group(1))
    
    max_qty_match = re.search(r'MaxQuantity\s*=\s*(\d+)', block)
    if max_qty_match:
        result['max_quantity'] = int(max_qty_match.group(1))
    
    min_qual_match = re.search(r'MinQuality\s*=\s*([\d.]+)', block)
    if min_qual_match:
        result['quality_min'] = float(min_qual_match.group(1))
    
    max_qual_match = re.search(r'MaxQuality\s*=\s*([\d.]+)', block)
    if max_qual_match:
        result['quality_max'] = float(max_qual_match.group(1))
    
    blueprint_match = re.search(r'ChanceToBeBlueprintOverride\s*=\s*([\d.]+)', block)
    if blueprint_match:
        result['chance_to_be_blueprint'] = float(blueprint_match.group(1))
    
    return result


def parse_all_crates(content: str) -> List[Dict[str, Any]]:
    """
    Parse all loot crate configurations from INI content.
    
    Args:
        content: Raw INI file content
        
    Returns:
        List of parsed crate configurations
    """
    blocks = extract_crate_blocks(content)
    crates = []
    
    for block in blocks:
        crate = parse_crate_block(block)
        if crate:
            crates.append(crate)
    
    logger.info(f"Parsed {len(crates)} loot crate configurations")
    return crates


def find_crates_section(content: str) -> Tuple[str, str]:
    """
    Find the section containing loot crate configs.
    
    Returns:
        Tuple of (section_name, section_content) or (None, None)
    """
    section_pattern = re.compile(r'^\[([^\]]+)\]', re.MULTILINE)
    
    sections = list(section_pattern.finditer(content))
    
    for i, match in enumerate(sections):
        section_name = match.group(1)
        start = match.end()
        end = sections[i + 1].start() if i + 1 < len(sections) else len(content)
        section_content = content[start:end]
        
        if 'ConfigOverrideSupplyCrateItems' in section_content:
            return section_name, section_content
    
    return None, None
