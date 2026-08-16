#!/usr/bin/env python3
"""
CurseForge Mod Harvester

Background service that scrapes CurseForge API for ARK: Survival Ascended mods
and caches them in the local SQLite database for instant Discord bot lookups.

Usage:
    python scripts/harvester.py [--full-sweep] [--once]

Modes:
    --full-sweep: Fetch ALL mods (run once for initial population)
    --once: Run a single sync cycle then exit
    (default): Run forever, pulsing every SYNC_INTERVAL seconds
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

GAME_ID_ASA = 83374  # ARK: Survival Ascended (not 80191)
SYNC_INTERVAL_SECONDS = 1800
PAGE_SIZE = 50
RATE_LIMIT_SLEEP = 60
PAGE_DELAY_SECONDS = 2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Harvester")


class HarvesterConfig:
    CURSEFORGE_API_KEY: str = os.getenv("CURSEFORGE_API_KEY", "")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "bot.db")
    SYNC_INTERVAL: int = int(os.getenv("HARVESTER_INTERVAL", "1800"))

    @classmethod
    def validate(cls) -> bool:
        if not cls.CURSEFORGE_API_KEY:
            logger.error("CURSEFORGE_API_KEY not set in environment")
            return False
        return True


async def fetch_mods_page(
    session: aiohttp.ClientSession,
    index: int = 0,
    sort_field: int = 2,
) -> list[dict]:
    url = "https://api.curseforge.com/v1/mods/search"
    headers = {"x-api-key": HarvesterConfig.CURSEFORGE_API_KEY}
    params = {
        "gameId": GAME_ID_ASA,
        "sortField": sort_field,
        "sortOrder": "desc",
        "index": index,
        "pageSize": PAGE_SIZE,
    }

    try:
        async with session.get(url, headers=headers, params=params, timeout=15) as resp:
            if resp.status == 429:
                logger.warning("Rate limited, sleeping 60s")
                await asyncio.sleep(RATE_LIMIT_SLEEP)
                return await fetch_mods_page(session, index, sort_field)

            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", [])
    except aiohttp.ClientError as e:
        logger.error(f"HTTP error fetching mods: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching mods: {e}")
        return []


def parse_mod(mod: dict) -> dict:
    authors = mod.get("authors", [])
    author_name = authors[0].get("name", "Unknown") if authors else "Unknown"

    logo = mod.get("logo", {})
    thumbnail_url = logo.get("thumbnailUrl") if logo else None

    links = mod.get("links", {})

    return {
        "mod_id": mod.get("id"),
        "name": mod.get("name", ""),
        "summary": mod.get("summary"),
        "author": author_name,
        "download_count": mod.get("downloadCount", 0),
        "thumbnail_url": thumbnail_url,
        "date_modified": mod.get("dateModified"),
        "website_url": links.get("websiteUrl"),
        "wiki_url": links.get("wikiUrl"),
        "slug": mod.get("slug"),
    }


async def sync_page(
    session: aiohttp.ClientSession,
    index: int,
) -> int:
    from bot.database import curseforge_db

    mods = await fetch_mods_page(session, index)
    if not mods:
        return 0

    parsed = [parse_mod(m) for m in mods]
    count = await curseforge_db.upsert_mods_batch(parsed)
    logger.info(f"Synced {count} mods from index {index}")
    return len(mods)


async def run_sync(full_sweep: bool = False) -> int:
    from bot.database import curseforge_db

    async with aiohttp.ClientSession() as session:
        total = 0
        index = 0

        while True:
            count = await sync_page(session, index)
            total += count

            if count == 0:
                break

            if not full_sweep:
                break

            if count < PAGE_SIZE:
                break

            index += PAGE_SIZE
            await asyncio.sleep(PAGE_DELAY_SECONDS)

    return total


async def run_once(full_sweep: bool = False) -> None:
    logger.info(f"Starting {'full sweep' if full_sweep else 'pulse'} sync...")
    total = await run_sync(full_sweep)
    logger.info(f"Sync complete. Total mods processed: {total}")


async def run_forever() -> None:
    logger.info("Starting harvester in continuous mode...")
    logger.info(f"Sync interval: {HarvesterConfig.SYNC_INTERVAL}s")

    first_run = True

    while True:
        try:
            full_sweep = first_run
            logger.info(f"Pulse sync started at {datetime.now(timezone.utc).isoformat()}")
            total = await run_sync(full_sweep=full_sweep)
            logger.info(f"Sync complete. Mods processed: {total}")
            first_run = False

            await asyncio.sleep(HarvesterConfig.SYNC_INTERVAL)
        except Exception as e:
            logger.error(f"Error in sync cycle: {e}")
            await asyncio.sleep(60)


def main() -> int:
    parser = argparse.ArgumentParser(description="CurseForge Mod Harvester")
    parser.add_argument(
        "--full-sweep",
        action="store_true",
        help="Fetch all mods (not just first page)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single sync cycle then exit",
    )
    args = parser.parse_args()

    if not HarvesterConfig.validate():
        return 1

    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    if args.once:
        asyncio.run(run_once(full_sweep=args.full_sweep))
    else:
        if args.full_sweep:
            logger.info("Note: --full-sweep only affects first cycle in continuous mode")
        asyncio.run(run_forever())

    return 0


if __name__ == "__main__":
    sys.exit(main())
