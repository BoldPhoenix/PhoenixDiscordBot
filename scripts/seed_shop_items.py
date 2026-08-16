#!/usr/bin/env python3
"""Seed the shop with the bundled ARK item catalogue.

The bot ships with `data/seed/store_items.json` — 1,593 ARK: Survival Ascended items
(structures, saddles, skins, consumables, resources, chibis, mod items and event items), each
with its display name, description, cost and the `ark_command` blueprint path used to deliver it.
That catalogue is public game data; assembling it by hand is a long afternoon, so it is included
rather than left as an exercise.

The bot ships with NO database. One is created empty on first run, and shop items are scoped per
Discord server, so the catalogue has to be imported under YOUR guild id — which is what this
script does.

Usage:

    python scripts/seed_shop_items.py --guild-id 123456789012345678
    python scripts/seed_shop_items.py --guild-id 123... --db ark_bot.db
    python scripts/seed_shop_items.py --guild-id 123... --category mods --dry-run

Re-running is safe: an item already present for that guild (matched on `item_id`) is updated
rather than duplicated, so this doubles as a way to pull in catalogue updates.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED = ROOT / "data" / "seed" / "store_items.json"

COLUMNS = ["item_id", "name", "description", "cost", "ark_command", "category", "enabled",
           "purchase_limit", "supports_quality", "allow_blueprint_select", "max_stack_size",
           "is_pack", "pack_contents"]


def load_seed(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"Seed file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        items = json.load(fh)
    if not isinstance(items, list) or not items:
        sys.exit(f"Seed file is empty or malformed: {path}")
    return items


def ensure_table(con: sqlite3.Connection) -> None:
    """Create store_items if the bot has not been run yet, so seeding can come first."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS store_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            cost INTEGER NOT NULL DEFAULT 0,
            ark_command TEXT,
            category TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            purchase_limit INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            supports_quality INTEGER NOT NULL DEFAULT 0,
            allow_blueprint_select INTEGER NOT NULL DEFAULT 0,
            max_stack_size INTEGER NOT NULL DEFAULT 1,
            is_pack INTEGER NOT NULL DEFAULT 0,
            pack_contents TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS ix_store_items_guild ON store_items(guild_id)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed the shop catalogue for one Discord server.")
    ap.add_argument("--guild-id", required=True, type=int,
                    help="your Discord server (guild) id — right-click the server with Developer "
                         "Mode on and 'Copy Server ID'")
    ap.add_argument("--db", default=os.environ.get("DATABASE_PATH", "ark_bot.db"),
                    help="path to the bot database (default: $DATABASE_PATH or ark_bot.db)")
    ap.add_argument("--seed", default=str(DEFAULT_SEED), help="path to the seed JSON")
    ap.add_argument("--category", help="import only one category (e.g. mods, saddles, skins)")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = ap.parse_args()

    items = load_seed(Path(args.seed))
    if args.category:
        items = [i for i in items if (i.get("category") or "").lower() == args.category.lower()]
        if not items:
            sys.exit(f"No items in category {args.category!r}.")

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    try:
        ensure_table(con)
        existing = {r["item_id"] for r in
                    con.execute("SELECT item_id FROM store_items WHERE guild_id=?",
                                (args.guild_id,))}
        added = sum(1 for i in items if i["item_id"] not in existing)
        updated = len(items) - added

        if args.dry_run:
            print(f"[dry run] {args.db}: would add {added}, update {updated} "
                  f"for guild {args.guild_id}")
            return 0

        for i in items:
            values = [i.get(c) for c in COLUMNS]
            if i["item_id"] in existing:
                sets = ", ".join(f"{c}=?" for c in COLUMNS[1:])
                con.execute(f"UPDATE store_items SET {sets} WHERE guild_id=? AND item_id=?",
                            values[1:] + [args.guild_id, i["item_id"]])
            else:
                cols = ", ".join(["guild_id"] + COLUMNS)
                marks = ", ".join("?" * (len(COLUMNS) + 1))
                con.execute(f"INSERT INTO store_items({cols}) VALUES({marks})",
                            [args.guild_id] + values)
        con.commit()
    finally:
        con.close()

    print(f"Seeded {args.db}: {added} added, {updated} updated for guild {args.guild_id}.")
    print("Run the bot and try /shop to see them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
