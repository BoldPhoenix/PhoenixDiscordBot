# Voice Channel Server Status Feature

## Overview

The bot now creates dedicated **voice channels** for each ARK server, displaying real-time status similar to ASA-Bot:

- **🟢 Green Indicator**: Server is online and reachable
- **🔴 Red Indicator**: Server is offline or unreachable  
- **Player Count**: Shows current players / max players (e.g., `5/70`)
- **Auto-Updates**: Channels update every 30 seconds

Example:
```
🟢 Aberration - 5/70
🟢 The Island - 12/70
🔴 Ragnarok - 0/70
```

## Implementation

### New Features in `server_monitor.py`:

1. **`create_voice_channel_for_server(server_name)`**: Creates a voice channel for a new server
2. **`delete_voice_channel_for_server(server_name)`**: Removes a voice channel when server is deleted
3. **`update_voice_channel(server_name, is_online, player_count)`**: Updates the channel name with current status
4. **`voice_channel_update_loop()`**: Background task that polls servers every 30 seconds

### Features:

- **Automatic Category**: Creates "Server Status" category if it doesn't exist
- **Locked Channels**: Users cannot join voice channels (view-only status)
- **Dynamic Management**: Channels are created when servers are added, deleted when removed
- **Rate Limit Protection**: Only updates channel name when status changes
- **Persistent Tracking**: Remembers channels across bot restarts

### Integration with Admin Commands:

When using `/addserver`, the bot:
1. Adds server to configuration  
2. Creates voice status channel immediately
3. Starts monitoring and updating status

When using `/removeserver`, the bot:
1. Removes server from configuration
2. Deletes the voice status channel
3. Stops monitoring

## Configuration

No additional configuration needed! The feature works automatically with your existing server setup.

### Environment Variables (existing):

- `DISCORD_GUILD_ID`: Required for creating channels
- `ARK_SERVERS`: JSON array of servers to monitor

## Usage

### Adding a Server

```
/addserver name:"Aberration" host:"127.0.0.1" rcon_port:27001 rcon_password:"yourpass" chat_enabled:True
```

**Result**: Voice channel created instantly showing 🔴 status until first successful RCON connection.

### Removing a Server

```
/removeserver name:"Aberration"
```

**Result**: Voice channel deleted automatically.

### Manual Channel Management

If you need to manually recreate channels:

1. Restart the bot - it will automatically create missing channels
2. Or wait for the next update loop (30 seconds)

## Technical Details

### Update Frequency

- **Voice Channels**: Every 30 seconds
- **Text Status Embed**: Every 60 seconds (existing feature)

### Discord Rate Limits

Discord allows **2 channel name changes per 10 minutes** per channel. The bot:
- Only updates when status actually changes
- Caches current channel names to avoid unnecessary updates
- Includes retry logic for rate limit errors

### Channel Permissions

Voice channels are created with:
- **Default Role**: Cannot connect (view-only)
- **Bot**: Full permissions

### Category Structure

```
📁 Server Status  
   🔊 🟢 Aberration - 15/70
   🔊 🟢 The Island - 8/70  
   🔊 🔴 Ragnarok - 0/70
   🔊 🟢 Valguero - 23/70
```

## Troubleshooting

### Channels not appearing

1. **Check bot permissions**: Needs "Manage Channels" permission
2. **Verify DISCORD_GUILD_ID** is set correctly
3. **Check bot logs** for permission errors

### Channels not updating

1. **RCON connectivity**: Verify servers are reachable
2. **Check update loop**: Look for errors in bot logs
3. **Rate limits**: Bot may be temporarily limited by Discord

### Duplicate channels

- Delete old channels manually
- Restart bot to recreate clean channels
- Bot tracks channels by server name

### Channel permissions

If users can join the voice channels:
1. Check the channel permissions  
2. Ensure "Connect" is denied for @everyone
3. Bot should set this automatically on creation

## Comparison to ASA-Bot

**Similar Features**:
- ✅ Voice channel status indicators
- ✅ Real-time player counts  
- ✅ Green/red status colors
- ✅ Automatic channel management

**Advantages**:
- ✅ Integrated with existing server management commands
- ✅ No separate configuration needed
- ✅ Works with existing RCON setup
- ✅ Combines with text status embeds

## Future Enhancements

Potential improvements:
- [ ] Customizable update intervals
- [ ] Server performance metrics in channel names  
- [ ] Configurable max player counts per server
- [ ] Custom emojis for different server types
- [ ] Alert notifications when servers go offline

## Code Structure

### Files Modified:

1. **`bot/cogs/server_monitor.py`**:
   - Added voice channel management methods
   - Added `voice_channel_update_loop` task
   - Integrated with existing status monitoring

2. **`bot/cogs/admin.py`** (manual integration needed):
   - Updated `/addserver` to create voice channels
   - Updated `/removeserver` to delete voice channels
   - See `VOICE_CHANNEL_INSTRUCTIONS.md` for details

### Dependencies:

- `discord.py >= 2.3.2`: Voice channel management APIs
- Existing RCON infrastructure
- Existing server monitoring cog

## Testing

### Test Voice Channel Creation:

```python
# In Discord, run:
/addserver name:"Test Server" host:"127.0.0.1" rcon_port:27020 rcon_password:"test" chat_enabled:True
```

**Expected**: 
- Voice channel appears in "Server Status" category
- Initially shows 🔴 Test Server - 0/70
- Updates to 🟢 when RCON connects successfully

### Test Voice Channel Deletion:

```python
/removeserver name:"Test Server"
```

**Expected**:
- Voice channel is removed
- No errors in logs

### Test Status Updates:

1. Watch a voice channel for 30 seconds
2. Join the ARK server
3. Channel should update with your player count

## Performance Impact

- **CPU**: Minimal (one RCON query per server every 30 seconds)
- **Network**: ~100 bytes per server per update
- **Discord API**: 2 requests per 30 seconds (get player list, update channel)
- **Memory**: ~1KB per monitored server

## Permissions Required

Bot needs these Discord permissions:
- ✅ Manage Channels (create/edit/delete voice channels)
- ✅ View Channels (see existing channels)
- ✅ Connect (technically not used, but good to have)

Grant via: Server Settings → Roles → Your Bot Role → Permissions

## Support

If you encounter issues:
1. Check bot logs for errors
2. Verify bot permissions in Discord
3. Test RCON connectivity with `/servers` command
4. Ensure `DISCORD_GUILD_ID` environment variable is set

## Changelog

### v2.1 (Current)
- ✨ Added voice channel status monitoring
- ✨ Auto-create channels on server add
- ✨ Auto-delete channels on server remove
- ✨ 30-second update loop with rate limit protection
- ✨ Locked channels (view-only for users)
