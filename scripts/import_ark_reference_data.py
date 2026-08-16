#!/usr/bin/env python3
"""
Import ARK reference data from JSON file.

Usage:
    python scripts/import_ark_reference_data.py [db_path] [json_path]

Arguments:
    db_path: Path to SQLite database (default: /opt/phoenix-bot/data/phoenix_bot.db)
    json_path: Path to JSON data file
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.database.ark_reference_schema import init_ark_reference_tables, import_ark_reference_data

DEFAULT_JSON = "data/seed/ark_reference_data.json"


async def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "ark_bot.db"
    json_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_JSON
    
    print(f"Database: {db_path}")
    print(f"JSON file: {json_path}")
    
    json_file = Path(json_path)
    if not json_file.exists():
        print(f"Error: JSON file not found: {json_path}")
        sys.exit(1)
    
    with open(json_file, 'r', encoding='utf-8') as f:
        import json
        data = json.load(f)
        print(f"Loaded JSON with keys: {list(data.keys())}")
    
    print("\nInitializing tables...")
    await init_ark_reference_tables(db_path)
    
    print("\nImporting data...")
    await import_ark_reference_data(json_path, db_path)
    
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
