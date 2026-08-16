# Player Stats Feature - Implementation Notes

## New Commands

### `/mystats` - Comprehensive Player Statistics
Shows detailed player information including:
- Character name
- Level
- Last seen server
- Last seen timestamp (relative time format)
- Specimen ID (for item delivery)
- EOS ID

**Usage:** `/mystats`
**Visibility:** Ephemeral (only visible to you)

### `/whereami` - Quick Last Seen Location
Quick command to show just your last known server location.

**Usage:** `/whereami`
**Visibility:** Ephemeral (only visible to you)

## How It Works

1. **Player Cache Service** (`player_cache.py` + `player_cache_service.py`):
   - Runs every 30 minutes
   - Scans RCON for currently online players
   - Parses cluster save files for all players
   - Updates `last_server` and `last_seen_timestamp` for each player

2. **Database Tracking** (`players` table):
   - `last_server`: Name of server where player was last seen
   - `last_seen_timestamp`: Unix timestamp of last activity
   - `character_name`: In-game character name
   - `level`: Character level
   - `specimen_id`: For item delivery

3. **Real-time Updates**:
   - Players are tracked when they join/leave servers
   - Voice channel integration shows current online status
   - `/servers` command shows current server population

## Data Population

To populate player data:

1. **Automatic** (Recommended):
   ```
   - Ensure servers are running and RCON is accessible
   - Player cache service runs automatically every 30 minutes
   - Players will be cached as they play
   ```

2. **Manual Trigger** (Admin):
   ```
   /playercache action:Scan Now
   ```

3. **From Save Files** (if CLUSTER_ROOT configured):
   ```
   - Set CLUSTER_ROOT in .env to your cluster directory
   - Service will parse save files for all player data
   - Example: CLUSTER_ROOT=C:/ARK\Servers
   ```

## Configuration

In `.env`:
```ini
# Required for save file scanning
CLUSTER_ROOT=C:/ARK\Servers

# Database path (default: bot.db)
DATABASE_PATH=bot.db
```

## Benefits Over Old System

✅ **Real database tracking** - Not just showing guild members
✅ **Save file integration** - Captures all players, even offline
✅ **Timestamp tracking** - Shows relative time ("3 days ago")
✅ **Server-specific location** - Shows exact map/server
✅ **Automatic updates** - Background service keeps data fresh
✅ **Multi-character support** - Tracks all characters per player

## Migration from Arkon Bot

The old `/playerstats` command from Arkon showed multiple characters per player.
Our `/mystats` shows your primary linked character with more accurate data.

**Screenshot comparison:**
- Old: Multiple "# unknown" maps (broken)
- New: Single accurate server name with timestamp

## Testing

Run manual test:
```bash
python check_boldphoenix_detailed.py
```

Force cache scan (admin only in Discord):
```
/playercache action:Scan Now
```

View your stats:
```
/mystats
/whereami
```

## Future Enhancements

- [ ] Show all characters for a player (multi-character support)
- [ ] Add playtime tracking per server
- [ ] Show tribe information
- [ ] Add "Find Player" command for admins
- [ ] Historical location tracking graph
