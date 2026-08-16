"""
Loot Crate Database - Store per-server loot crate configurations.

Tables:
- loot_crate_configs: Per-server crate overrides
- loot_item_sets: Item sets within each crate
- loot_set_items: Individual items within each set
"""

import aiosqlite
import json
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger("LootCrateDB")


async def init_loot_crate_tables(db_path: str):
    """Initialize loot crate configuration tables."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS loot_crate_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                class_string TEXT NOT NULL,
                label TEXT,
                min_item_sets INTEGER DEFAULT 1,
                max_item_sets INTEGER DEFAULT 1,
                prevent_duplicates INTEGER DEFAULT 1,
                is_enabled INTEGER DEFAULT 1,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                updated_at INTEGER DEFAULT (strftime('%s', 'now')),
                UNIQUE(guild_id, server_name, class_string)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS loot_item_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                crate_config_id INTEGER NOT NULL,
                set_name TEXT DEFAULT 'ItemSet',
                min_items INTEGER DEFAULT 1,
                max_items INTEGER DEFAULT 1,
                weight REAL DEFAULT 1.0,
                set_order INTEGER DEFAULT 0,
                FOREIGN KEY (crate_config_id) REFERENCES loot_crate_configs(id) ON DELETE CASCADE
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS loot_set_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_set_id INTEGER NOT NULL,
                class_string TEXT NOT NULL,
                label TEXT,
                min_quantity INTEGER DEFAULT 1,
                max_quantity INTEGER DEFAULT 1,
                quality_min REAL DEFAULT 0,
                quality_max REAL DEFAULT 0,
                chance_to_be_blueprint REAL DEFAULT 0,
                item_order INTEGER DEFAULT 0,
                FOREIGN KEY (item_set_id) REFERENCES loot_item_sets(id) ON DELETE CASCADE
            )
        """)
        
        await db.execute("CREATE INDEX IF NOT EXISTS idx_loot_crate_guild ON loot_crate_configs(guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_loot_crate_server ON loot_crate_configs(guild_id, server_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_loot_item_sets_crate ON loot_item_sets(crate_config_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_loot_set_items_set ON loot_set_items(item_set_id)")
        
        await db.commit()
        logger.info("Loot crate tables initialized")


async def get_crate_configs(guild_id: int, server_name: str, db_path: str) -> List[Dict[str, Any]]:
    """Get all crate configs for a server."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM loot_crate_configs
            WHERE guild_id = ? AND server_name = ?
            ORDER BY label, class_string
        """, (guild_id, server_name))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_crate_config(guild_id: int, server_name: str, class_string: str, db_path: str) -> Optional[Dict[str, Any]]:
    """Get a specific crate config."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM loot_crate_configs
            WHERE guild_id = ? AND server_name = ? AND class_string = ?
        """, (guild_id, server_name, class_string))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_crate_with_sets(crate_config_id: int, db_path: str) -> Dict[str, Any]:
    """Get a crate config with all its item sets and items."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        
        cursor = await db.execute(
            "SELECT * FROM loot_crate_configs WHERE id = ?",
            (crate_config_id,)
        )
        crate_row = await cursor.fetchone()
        if not crate_row:
            return None
        
        crate = dict(crate_row)
        
        cursor = await db.execute("""
            SELECT * FROM loot_item_sets
            WHERE crate_config_id = ?
            ORDER BY set_order, id
        """, (crate_config_id,))
        set_rows = await cursor.fetchall()
        
        item_sets = []
        for set_row in set_rows:
            item_set = dict(set_row)
            
            cursor = await db.execute("""
                SELECT * FROM loot_set_items
                WHERE item_set_id = ?
                ORDER BY item_order, id
            """, (item_set['id'],))
            item_rows = await cursor.fetchall()
            item_set['items'] = [dict(row) for row in item_rows]
            item_sets.append(item_set)
        
        crate['item_sets'] = item_sets
        return crate


async def create_crate_config(
    guild_id: int,
    server_name: str,
    class_string: str,
    label: Optional[str] = None,
    min_item_sets: int = 1,
    max_item_sets: int = 1,
    prevent_duplicates: bool = True,
    db_path: str = None
) -> int:
    """Create a new crate config. Returns the ID."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("""
            INSERT INTO loot_crate_configs (
                guild_id, server_name, class_string, label,
                min_item_sets, max_item_sets, prevent_duplicates
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            guild_id, server_name, class_string, label,
            min_item_sets, max_item_sets, 1 if prevent_duplicates else 0
        ))
        await db.commit()
        return cursor.lastrowid


async def update_crate_config(crate_config_id: int, db_path: str, **updates) -> bool:
    """Update a crate config."""
    if not updates:
        return False
    
    allowed = {'label', 'min_item_sets', 'max_item_sets', 'prevent_duplicates', 'is_enabled'}
    updates = {k: v for k, v in updates.items() if k in allowed}
    
    if not updates:
        return False
    
    updates['updated_at'] = int(__import__('time').time())
    
    set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [crate_config_id]
    
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"UPDATE loot_crate_configs SET {set_clause} WHERE id = ?",
            values
        )
        await db.commit()
        return True


async def delete_crate_config(crate_config_id: int, db_path: str) -> bool:
    """Delete a crate config and all its item sets/items."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM loot_crate_configs WHERE id = ?", (crate_config_id,))
        await db.commit()
        return True


async def create_item_set(
    crate_config_id: int,
    set_name: str = "ItemSet",
    min_items: int = 1,
    max_items: int = 1,
    weight: float = 1.0,
    db_path: str = None
) -> int:
    """Create a new item set. Returns the ID."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("""
            SELECT COALESCE(MAX(set_order), -1) + 1 FROM loot_item_sets WHERE crate_config_id = ?
        """, (crate_config_id,))
        row = await cursor.fetchone()
        next_order = row[0] if row else 0
        
        cursor = await db.execute("""
            INSERT INTO loot_item_sets (
                crate_config_id, set_name, min_items, max_items, weight, set_order
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (crate_config_id, set_name, min_items, max_items, weight, next_order))
        await db.commit()
        return cursor.lastrowid


async def update_item_set(item_set_id: int, db_path: str, **updates) -> bool:
    """Update an item set."""
    if not updates:
        return False
    
    allowed = {'set_name', 'min_items', 'max_items', 'weight', 'set_order'}
    updates = {k: v for k, v in updates.items() if k in allowed}
    
    if not updates:
        return False
    
    set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [item_set_id]
    
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"UPDATE loot_item_sets SET {set_clause} WHERE id = ?",
            values
        )
        await db.commit()
        return True


async def delete_item_set(item_set_id: int, db_path: str) -> bool:
    """Delete an item set and all its items."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM loot_item_sets WHERE id = ?", (item_set_id,))
        await db.commit()
        return True


async def create_set_item(
    item_set_id: int,
    class_string: str,
    label: Optional[str] = None,
    min_quantity: int = 1,
    max_quantity: int = 1,
    quality_min: float = 0,
    quality_max: float = 0,
    chance_to_be_blueprint: float = 0,
    db_path: str = None
) -> int:
    """Create a new item in a set. Returns the ID."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("""
            SELECT COALESCE(MAX(item_order), -1) + 1 FROM loot_set_items WHERE item_set_id = ?
        """, (item_set_id,))
        row = await cursor.fetchone()
        next_order = row[0] if row else 0
        
        cursor = await db.execute("""
            INSERT INTO loot_set_items (
                item_set_id, class_string, label, min_quantity, max_quantity,
                quality_min, quality_max, chance_to_be_blueprint, item_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_set_id, class_string, label, min_quantity, max_quantity,
            quality_min, quality_max, chance_to_be_blueprint, next_order
        ))
        await db.commit()
        return cursor.lastrowid


async def update_set_item(item_id: int, db_path: str, **updates) -> bool:
    """Update an item."""
    if not updates:
        return False
    
    allowed = {'class_string', 'label', 'min_quantity', 'max_quantity', 
               'quality_min', 'quality_max', 'chance_to_be_blueprint', 'item_order'}
    updates = {k: v for k, v in updates.items() if k in allowed}
    
    if not updates:
        return False
    
    set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [item_id]
    
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"UPDATE loot_set_items SET {set_clause} WHERE id = ?",
            values
        )
        await db.commit()
        return True


async def delete_set_item(item_id: int, db_path: str) -> bool:
    """Delete an item."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM loot_set_items WHERE id = ?", (item_id,))
        await db.commit()
        return True


async def import_crate_from_ini(
    guild_id: int,
    server_name: str,
    class_string: str,
    crate_data: Dict[str, Any],
    db_path: str
) -> int:
    """
    Import a crate configuration from parsed INI data.
    
    crate_data format:
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
                'items': [
                    {
                        'class_string': 'PrimalItem_...',
                        'min_quantity': 1,
                        'max_quantity': 2,
                        'quality_min': 0,
                        'quality_max': 0,
                        'chance_to_be_blueprint': 0.5
                    },
                    ...
                ]
            },
            ...
        ]
    }
    """
    crate_id = await create_crate_config(
        guild_id=guild_id,
        server_name=server_name,
        class_string=class_string,
        min_item_sets=crate_data.get('min_item_sets', 1),
        max_item_sets=crate_data.get('max_item_sets', 1),
        prevent_duplicates=crate_data.get('prevent_duplicates', True),
        db_path=db_path
    )
    
    for set_data in crate_data.get('item_sets', []):
        set_id = await create_item_set(
            crate_config_id=crate_id,
            min_items=set_data.get('min_items', 1),
            max_items=set_data.get('max_items', 1),
            weight=set_data.get('weight', 1.0),
            db_path=db_path
        )
        
        for item_data in set_data.get('items', []):
            await create_set_item(
                item_set_id=set_id,
                class_string=item_data['class_string'],
                min_quantity=item_data.get('min_quantity', 1),
                max_quantity=item_data.get('max_quantity', 1),
                quality_min=item_data.get('quality_min', 0),
                quality_max=item_data.get('quality_max', 0),
                chance_to_be_blueprint=item_data.get('chance_to_be_blueprint', 0),
                db_path=db_path
            )
    
    return crate_id


async def export_crate_to_ini(crate_config_id: int, db_path: str) -> str:
    """
    Export a crate configuration to INI format.
    
    Returns the ConfigOverrideSupplyCrateItems line(s).
    """
    crate = await get_crate_with_sets(crate_config_id, db_path)
    if not crate:
        return ""
    
    lines = []
    lines.append(f"ConfigOverrideSupplyCrateItems=(")
    lines.append(f"    SupplyCrateClassString=\"{crate['class_string']}\",")
    lines.append(f"    MinItemSets={crate['min_item_sets']},")
    lines.append(f"    MaxItemSets={crate['max_item_sets']},")
    lines.append(f"    bPreventDuplicates={'True' if crate['prevent_duplicates'] else 'False'},")
    
    item_sets = crate.get('item_sets', [])
    if item_sets:
        lines.append("    ItemSets=(")
    
    for i, item_set in enumerate(item_sets):
        set_prefix = "        (" if i == 0 else "        ,("
        lines.append(f"{set_prefix}")
        lines.append(f"            MinNumItems={item_set['min_items']},")
        lines.append(f"            MaxNumItems={item_set['max_items']},")
        lines.append(f"            SetWeight={item_set['weight']},")
        
        items = item_set.get('items', [])
        if items:
            lines.append("            ItemEntries=(")
            
            for j, item in enumerate(items):
                item_prefix = "                (" if j == 0 else "                ,("
                lines.append(f"{item_prefix}")
                lines.append(f"                    EntryWeight=1.0,")
                lines.append(f"                    ItemClassStrings=(\"{item['class_string']}\"),")
                lines.append(f"                    ItemsWeights=(1),")
                lines.append(f"                    MinQuantity={item['min_quantity']},")
                lines.append(f"                    MaxQuantity={item['max_quantity']},")
                lines.append(f"                    MinQuality={item['quality_min']},")
                lines.append(f"                    MaxQuality={item['quality_max']},")
                lines.append(f"                    bForceBlueprint={'True' if item.get('chance_to_be_blueprint', 0) >= 1 else 'False'},")
                lines.append(f"                    ChanceToBeBlueprintOverride={item.get('chance_to_be_blueprint', 0)}")
                lines.append("                )")
            
            lines.append("            )")
        
        lines.append("        )")
    
    if item_sets:
        lines.append("    )")
    
    lines.append(")")
    
    return '\n'.join(lines)
