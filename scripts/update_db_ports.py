#!/usr/bin/env python3
"""
Update `server_ark_servers` in the bot database to match the new port mapping.
Run on the machine with the bot repository (it will detect `bot.db` or use DATABASE_PATH env/.env fallback).

This script backs up the DB to `bot.db.preports.bak` before making changes.
"""
import os
import re
import sqlite3
from pathlib import Path

# Determine DB path the same way the bot does
db_path = os.getenv('DATABASE_PATH')
if not db_path and Path('.env').exists():
    for line in Path('.env').read_text().splitlines():
        m = re.match(r"DATABASE_PATH\s*=\s*(.+)", line)
        if m:
            db_path = m.group(1).strip().strip('"').strip("'")
            break
if not db_path:
    db_path = 'bot.db'

db_file = Path(db_path)
if not db_file.exists():
    raise SystemExit(f"DB file not found: {db_file}")

backup = db_file.with_suffix('.preports.bak')
backup.write_bytes(db_file.read_bytes())
print(f"Backed up DB to {backup}")

# Ordered service list - must match the order used in the NSSM update script
services = [
    'asa_amissa',
    'asa_astraeos',
    'asa_center',
    'asa_extinction',
    'asa_island',
    'asa_ragvegas',
    'asa_ragnarok',
    'asa_scorched',
    'asa_valguero'
]

# Port mapping as specified
port_mapping = {
    'asa_amissa': (7777, 27000, 27050),
    'asa_astraeos': (7779, 27001, 27051),
    'asa_center': (7781, 27002, 27052),
    'asa_extinction': (7783, 27003, 27053),
    'asa_island': (7785, 27004, 27054),  # Note: User had 27051 but that conflicts with Astraeos
    'asa_ragnarok': (7787, 27005, 27055),
    'asa_ragvegas': (7789, 27006, 27056),
    'asa_scorched': (7791, 27007, 27057),
    'asa_valguero': (7793, 27008, 27058)
}

conn = sqlite3.connect(str(db_file))
cur = conn.cursor()

for svc, (game, query, rcon) in port_mapping.items():
    # Update rows where service_name matches
    cur.execute(
        "UPDATE server_ark_servers SET game_port = ?, query_port = ?, rcon_port = ? WHERE service_name = ?",
        (game, query, rcon, svc)
    )
    print(f"Updated {svc}: game={game} query={query} rcon={rcon} (rows changed: {cur.rowcount})")

conn.commit()
conn.close()
print('DB update complete. Verify with your bot or tools.')
