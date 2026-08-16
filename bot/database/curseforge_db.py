"""
CurseForge mod cache database operations.
Provides fast local lookup of mod metadata for the Discord bot.
"""

import aiosqlite
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from bot.utils.config import Config

logger = logging.getLogger("CurseForgeDB")


def _db_path() -> str:
    return Config.DATABASE_PATH


async def get_mod_by_id(mod_id: int) -> Optional[Dict[str, Any]]:
    """Get a single mod by its CurseForge ID."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM curseforge_mods WHERE mod_id = ?", (mod_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def search_mods(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Search for mods by name, author, ID, or description."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT mod_id, name, author, download_count, thumbnail_url, website_url, summary, date_modified
            FROM curseforge_mods
            WHERE is_available = 1
              AND (
                  name LIKE ? 
                  OR author LIKE ? 
                  OR CAST(mod_id AS TEXT) LIKE ? 
                  OR summary LIKE ?
              )
            LIMIT ?
            """,
            (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_all_mods(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Get all mods with pagination."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM curseforge_mods
            WHERE is_available = 1
            ORDER BY name COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_mod_count() -> int:
    """Get total count of cached mods."""
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM curseforge_mods WHERE is_available = 1"
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def upsert_mod(
    mod_id: int,
    name: str,
    summary: Optional[str] = None,
    author: Optional[str] = None,
    download_count: int = 0,
    thumbnail_url: Optional[str] = None,
    date_modified: Optional[str] = None,
    website_url: Optional[str] = None,
    wiki_url: Optional[str] = None,
    slug: Optional[str] = None,
    raw_json: Optional[str] = None,
) -> bool:
    """Insert or update a mod in the cache."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                """
                INSERT INTO curseforge_mods (
                    mod_id, name, summary, author, download_count,
                    thumbnail_url, date_modified, website_url, wiki_url, slug, raw_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mod_id) DO UPDATE SET
                    name = excluded.name,
                    summary = excluded.summary,
                    author = excluded.author,
                    download_count = excluded.download_count,
                    thumbnail_url = excluded.thumbnail_url,
                    date_modified = excluded.date_modified,
                    website_url = excluded.website_url,
                    wiki_url = excluded.wiki_url,
                    slug = excluded.slug,
                    raw_json = excluded.raw_json,
                    updated_at = excluded.updated_at
                """,
                (
                    mod_id,
                    name,
                    summary,
                    author,
                    download_count,
                    thumbnail_url,
                    date_modified,
                    website_url,
                    wiki_url,
                    slug,
                    raw_json,
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to upsert mod {mod_id}: {e}")
        return False


async def upsert_mods_batch(mods: List[Dict[str, Any]]) -> int:
    """Batch insert/update multiple mods. Returns count of successfully upserted mods."""
    success_count = 0
    async with aiosqlite.connect(_db_path()) as db:
        for mod in mods:
            try:
                await db.execute(
                    """
                    INSERT INTO curseforge_mods (
                        mod_id, name, summary, author, download_count,
                        thumbnail_url, date_modified, website_url, wiki_url, slug, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(mod_id) DO UPDATE SET
                        name = excluded.name,
                        summary = excluded.summary,
                        author = excluded.author,
                        download_count = excluded.download_count,
                        thumbnail_url = excluded.thumbnail_url,
                        date_modified = excluded.date_modified,
                        website_url = excluded.website_url,
                        wiki_url = excluded.wiki_url,
                        slug = excluded.slug,
                        updated_at = excluded.updated_at
                    """,
                    (
                        mod.get("id") or mod.get("mod_id"),
                        mod.get("name"),
                        mod.get("summary"),
                        mod.get("author"),
                        mod.get("download_count", 0),
                        mod.get("thumbnail_url"),
                        mod.get("date_modified"),
                        mod.get("website_url"),
                        mod.get("wiki_url"),
                        mod.get("slug"),
                        datetime.utcnow().isoformat(),
                    ),
                )
                success_count += 1
            except Exception as e:
                logger.warning(f"Failed to upsert mod {mod.get('id')}: {e}")
        await db.commit()
    return success_count


async def mark_mod_unavailable(mod_id: int) -> bool:
    """Mark a mod as no longer available (deleted from CurseForge)."""
    try:
        async with aiosqlite.connect(_db_path()) as db:
            await db.execute(
                "UPDATE curseforge_mods SET is_available = 0 WHERE mod_id = ?", (mod_id,)
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Failed to mark mod {mod_id} unavailable: {e}")
        return False


async def get_recently_updated(limit: int = 50) -> List[Dict[str, Any]]:
    """Get mods sorted by most recent update on CurseForge."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT mod_id, name, author, download_count, date_modified, website_url
            FROM curseforge_mods
            WHERE is_available = 1 AND date_modified IS NOT NULL
            ORDER BY date_modified DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_top_downloaded(limit: int = 50) -> List[Dict[str, Any]]:
    """Get mods sorted by download count."""
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT mod_id, name, author, download_count, thumbnail_url, website_url
            FROM curseforge_mods
            WHERE is_available = 1
            ORDER BY download_count DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
