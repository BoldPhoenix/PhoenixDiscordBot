"""
ARK Reference Data Schema

Tables to store ARK:SA game data for:
- Item/creature search in editors
- INI validation and descriptions
- Loot drop configuration
- Spawn point editing
"""

import aiosqlite
from pathlib import Path
import logging
import json

from bot.utils.config import Config

logger = logging.getLogger("ArkReferenceSchema")


async def init_ark_reference_tables(db_path: str):
    """Initialize ARK reference data tables."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ark_ref_items (
                object_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                alternate_label TEXT,
                class_string TEXT,
                path TEXT,
                stack_size INTEGER,
                required_level INTEGER,
                required_points INTEGER,
                tags TEXT,
                recipe TEXT,
                content_pack_id TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ark_ref_creatures (
                object_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                alternate_label TEXT,
                class_string TEXT,
                path TEXT,
                tags TEXT,
                stats TEXT,
                incubation_time REAL,
                mature_time REAL,
                mating_interval_min REAL,
                mating_interval_max REAL,
                content_pack_id TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ark_ref_engrams (
                object_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                alternate_label TEXT,
                class_string TEXT,
                path TEXT,
                required_level INTEGER,
                required_points INTEGER,
                stack_size INTEGER,
                item_id INTEGER,
                tags TEXT,
                recipe TEXT,
                entry_string TEXT,
                content_pack_id TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ark_ref_loot_sources (
                object_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                alternate_label TEXT,
                class_string TEXT,
                path TEXT,
                min_item_sets INTEGER DEFAULT 1,
                max_item_sets INTEGER DEFAULT 1,
                prevent_duplicates INTEGER DEFAULT 1,
                multiplier_min REAL,
                multiplier_max REAL,
                contents TEXT,
                tags TEXT,
                notes TEXT,
                experimental INTEGER DEFAULT 0,
                content_pack_id TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ark_ref_spawn_points (
                object_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                alternate_label TEXT,
                class_string TEXT,
                path TEXT,
                sets TEXT,
                limits TEXT,
                tags TEXT,
                content_pack_id TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ark_ref_ini_options (
                object_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                alternate_label TEXT,
                file TEXT,
                header TEXT,
                key TEXT,
                value_type TEXT,
                default_value TEXT,
                description TEXT,
                constraints TEXT,
                tags TEXT,
                content_pack_id TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ark_ref_content_packs (
                content_pack_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                marketplace TEXT,
                marketplace_id TEXT,
                console_safe INTEGER DEFAULT 0,
                default_enabled INTEGER DEFAULT 1,
                last_update INTEGER
            )
        """)
        
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ark_ref_items_label ON ark_ref_items(label)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ark_ref_items_class ON ark_ref_items(class_string)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ark_ref_creatures_label ON ark_ref_creatures(label)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ark_ref_creatures_class ON ark_ref_creatures(class_string)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ark_ref_engrams_label ON ark_ref_engrams(label)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ark_ref_engrams_class ON ark_ref_engrams(class_string)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ark_ref_loot_label ON ark_ref_loot_sources(label)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ark_ref_loot_class ON ark_ref_loot_sources(class_string)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ark_ref_spawn_label ON ark_ref_spawn_points(label)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ark_ref_ini_key ON ark_ref_ini_options(key)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_ark_ref_ini_header ON ark_ref_ini_options(header)")
        
        await db.commit()
        logger.info("ARK reference tables created")


async def import_ark_reference_data(json_path: str, db_path: str):
    """
    Import ARK reference data from JSON file.
    
    Args:
        json_path: Path to JSON data file
        db_path: Path to SQLite database
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    extracted = data.get('extracted_data', {})
    
    async with aiosqlite.connect(db_path) as db:
        items = extracted.get('items', [])
        if items:
            await _import_items(db, items)
        
        creatures = extracted.get('creatures', [])
        if creatures:
            await _import_creatures(db, creatures)
        
        engrams = extracted.get('engrams', [])
        if engrams:
            await _import_engrams(db, engrams)
        
        loot_sources = extracted.get('loot_sources', [])
        if loot_sources:
            await _import_loot_sources(db, loot_sources)
        
        spawn_points = extracted.get('spawn_points', [])
        if spawn_points:
            await _import_spawn_points(db, spawn_points)
        
        ini_options = extracted.get('configurations', [])
        if ini_options:
            await _import_ini_options(db, ini_options)
        
        await db.commit()
        logger.info("ARK reference data import complete")


async def _import_items(db, items: list):
    """Import items into database."""
    count = 0
    for item in items:
        try:
            await db.execute("""
                INSERT OR REPLACE INTO ark_ref_items (
                    object_id, label, alternate_label, class_string, path,
                    stack_size, required_level, required_points, tags, recipe, content_pack_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get('object_id'),
                item.get('label'),
                item.get('alternate_label'),
                item.get('class_string'),
                item.get('path'),
                item.get('stack_size'),
                item.get('required_level'),
                item.get('required_points'),
                json.dumps(item.get('tags', [])) if item.get('tags') else None,
                json.dumps(item.get('recipe', [])) if item.get('recipe') else None,
                item.get('content_pack_id'),
            ))
            count += 1
        except Exception as e:
            logger.warning(f"Failed to import item {item.get('object_id')}: {e}")
    
    logger.info(f"Imported {count} items")


async def _import_creatures(db, creatures: list):
    """Import creatures into database."""
    count = 0
    for creature in creatures:
        try:
            await db.execute("""
                INSERT OR REPLACE INTO ark_ref_creatures (
                    object_id, label, alternate_label, class_string, path,
                    tags, stats, incubation_time, mature_time,
                    mating_interval_min, mating_interval_max, content_pack_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                creature.get('object_id'),
                creature.get('label'),
                creature.get('alternate_label'),
                creature.get('class_string'),
                creature.get('path'),
                json.dumps(creature.get('tags', [])) if creature.get('tags') else None,
                json.dumps(creature.get('stats', {})) if creature.get('stats') else None,
                creature.get('incubation_time'),
                creature.get('mature_time'),
                creature.get('mating_interval_min'),
                creature.get('mating_interval_max'),
                creature.get('content_pack_id'),
            ))
            count += 1
        except Exception as e:
            logger.warning(f"Failed to import creature {creature.get('object_id')}: {e}")
    
    logger.info(f"Imported {count} creatures")


async def _import_engrams(db, engrams: list):
    """Import engrams into database."""
    count = 0
    for engram in engrams:
        try:
            await db.execute("""
                INSERT OR REPLACE INTO ark_ref_engrams (
                    object_id, label, alternate_label, class_string, path,
                    required_level, required_points, stack_size, item_id,
                    tags, recipe, entry_string, content_pack_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                engram.get('object_id'),
                engram.get('label'),
                engram.get('alternate_label'),
                engram.get('class_string'),
                engram.get('path'),
                engram.get('required_level'),
                engram.get('required_points'),
                engram.get('stack_size'),
                engram.get('item_id'),
                json.dumps(engram.get('tags', [])) if engram.get('tags') else None,
                json.dumps(engram.get('recipe', [])) if engram.get('recipe') else None,
                engram.get('entry_string'),
                engram.get('content_pack_id'),
            ))
            count += 1
        except Exception as e:
            logger.warning(f"Failed to import engram {engram.get('object_id')}: {e}")
    
    logger.info(f"Imported {count} engrams")


async def _import_loot_sources(db, loot_sources: list):
    """Import loot sources into database."""
    count = 0
    for loot in loot_sources:
        try:
            await db.execute("""
                INSERT OR REPLACE INTO ark_ref_loot_sources (
                    object_id, label, alternate_label, class_string, path,
                    min_item_sets, max_item_sets, prevent_duplicates,
                    multiplier_min, multiplier_max, contents, tags, notes, experimental, content_pack_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                loot.get('object_id'),
                loot.get('label'),
                loot.get('alternate_label'),
                loot.get('class_string'),
                loot.get('path'),
                loot.get('min_item_sets', 1),
                loot.get('max_item_sets', 1),
                1 if loot.get('prevent_duplicates', True) else 0,
                loot.get('multiplier_min'),
                loot.get('multiplier_max'),
                json.dumps(loot.get('contents', [])) if loot.get('contents') else None,
                json.dumps(loot.get('tags', [])) if loot.get('tags') else None,
                loot.get('notes'),
                1 if loot.get('experimental', False) else 0,
                loot.get('content_pack_id'),
            ))
            count += 1
        except Exception as e:
            logger.warning(f"Failed to import loot source {loot.get('object_id')}: {e}")
    
    logger.info(f"Imported {count} loot sources")


async def _import_spawn_points(db, spawn_points: list):
    """Import spawn points into database."""
    count = 0
    for spawn in spawn_points:
        try:
            await db.execute("""
                INSERT OR REPLACE INTO ark_ref_spawn_points (
                    object_id, label, alternate_label, class_string, path,
                    sets, limits, tags, content_pack_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                spawn.get('object_id'),
                spawn.get('label'),
                spawn.get('alternate_label'),
                spawn.get('class_string'),
                spawn.get('path'),
                json.dumps(spawn.get('sets', [])) if spawn.get('sets') else None,
                json.dumps(spawn.get('limits', {})) if spawn.get('limits') else None,
                json.dumps(spawn.get('tags', [])) if spawn.get('tags') else None,
                spawn.get('content_pack_id'),
            ))
            count += 1
        except Exception as e:
            logger.warning(f"Failed to import spawn point {spawn.get('object_id')}: {e}")
    
    logger.info(f"Imported {count} spawn points")


async def _import_ini_options(db, ini_options: list):
    """Import INI options into database."""
    count = 0
    for opt in ini_options:
        try:
            await db.execute("""
                INSERT OR REPLACE INTO ark_ref_ini_options (
                    object_id, label, alternate_label, file, header, key,
                    value_type, default_value, description, constraints, tags, content_pack_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                opt.get('object_id'),
                opt.get('label'),
                opt.get('alternate_label'),
                opt.get('file'),
                opt.get('header'),
                opt.get('key'),
                opt.get('value_type'),
                opt.get('default_value'),
                opt.get('description'),
                json.dumps(opt.get('constraints', {})) if opt.get('constraints') else None,
                json.dumps(opt.get('tags', [])) if opt.get('tags') else None,
                opt.get('content_pack_id'),
            ))
            count += 1
        except Exception as e:
            logger.warning(f"Failed to import INI option {opt.get('object_id')}: {e}")
    
    logger.info(f"Imported {count} INI options")


async def migrate_from_old_table_names(db_path: str):
    """
    Migrate data from beacon_* tables to ark_ref_* tables.
    Run this once on existing databases.
    """
    table_mappings = [
        ('beacon_items', 'ark_ref_items'),
        ('beacon_creatures', 'ark_ref_creatures'),
        ('beacon_engrams', 'ark_ref_engrams'),
        ('beacon_loot_sources', 'ark_ref_loot_sources'),
        ('beacon_spawn_points', 'ark_ref_spawn_points'),
        ('beacon_ini_options', 'ark_ref_ini_options'),
        ('beacon_content_packs', 'ark_ref_content_packs'),
    ]
    
    async with aiosqlite.connect(db_path) as db:
        for old_name, new_name in table_mappings:
            cursor = await db.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (old_name,)
            )
            if await cursor.fetchone():
                await db.execute(f"DROP TABLE IF EXISTS {new_name}")
                await db.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")
                logger.info(f"Migrated {old_name} -> {new_name}")
        
        await db.commit()
        logger.info("Table migration complete")
