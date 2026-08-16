"""
Import ARK core creatures from CSV to RAG database.
"""
import csv
import sqlite3

# Read the CSV
creatures = []
with open('/tmp/ark_dinos.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        creatures.append(row)

print(f"Read {len(creatures)} creatures from CSV")

# Database path
db_path = '/opt/phoenix-bot/data/phoenix_bot.db'

# Map creature ID patterns to likely maps
def guess_map_from_id(creature_id):
    id_lower = creature_id.lower()
    
    if any(x in id_lower for x in ['gen', 'megacave', 'nogl', 'basilosaurus', 'dinotrua', 'maewing']):
        return 'Genesis'
    if any(x in id_lower for x in ['basilisk', 'crab', 'lantern', 'nameless', 'rockwell', 'reaper', 'glow', 'xenomorph']):
        return 'Aberration'
    if any(x in id_lower for x in ['长沙', 'managarmr', 'ice', 'snow', 'forest', 'desert', 'ogs', 'megalodon', 'titanosaur']):
        return 'Extinction'
    if any(x in id_lower for x in ['manticore', 'jerboa', 'leech', 'morph', 'thorny', 'cave', 'wyvern', 'sand']):
        return 'ScorchedEarth'
    if any(x in id_lower for x in ['fjordur', 'bloodstalker', 'nimble', 'actinopt', 'maevulf']):
        return 'Fjordur'
    return 'TheIsland'

# Connect and insert
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

added = 0
skipped = 0

for row in creatures:
    name = row['Creature Name']
    creature_id = row['Creature ID']
    
    # Check if already exists
    cursor.execute("SELECT COUNT(*) FROM ark_ref_creatures WHERE class_string = ?", (creature_id,))
    if cursor.fetchone()[0] > 0:
        skipped += 1
        continue
    
    # Guess the map
    map_name = guess_map_from_id(creature_id)
    
    # Build path
    path_name = name.replace(' ', '').replace('(', '').replace(')', '')
    path = f"/Game/{map_name}/Dinos/{path_name}/{creature_id}.{creature_id}"
    
    cursor.execute("""
        INSERT INTO ark_ref_creatures (object_id, label, class_string, path, tags, stats, incubation_time, mature_time)
        VALUES (?, ?, ?, ?, 'object', NULL, NULL, NULL)
    """, (creature_id, name, creature_id, path))
    
    added += 1

conn.commit()

# Verify count
cursor.execute("SELECT COUNT(*) FROM ark_ref_creatures WHERE path LIKE '/Game/%' AND path NOT LIKE '/Game/Mods/%'")
core_count = cursor.fetchone()[0]

conn.close()

print(f"Added {added} new creatures")
print(f"Skipped {skipped} existing")
print(f"Total core creatures now: {core_count}")
print("Done!")
