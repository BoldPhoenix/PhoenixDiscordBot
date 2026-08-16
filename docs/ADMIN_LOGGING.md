# Admin Action Logging System

## Overview

The bot provides comprehensive logging of all admin actions with real-time notifications and audit trail tracking. Every admin command is logged to both Discord and the database for transparency and accountability.

## Setup

### 1. Configure Admin Log Channel

Set the channel where admin actions will be logged:

```discord
/setadminlogchannel <channel>
```

Example:
```
/setadminlogchannel #admin-logs
```

### Environment Variable (Optional)

You can also set it in `.env`:
```env
ADMIN_LOG_CHANNEL_ID=1234567890
```

## Logged Actions

The following admin actions are automatically logged:

### Player Management
- **Kick Player** - Removes player from server
- **Ban Player** - Permanently bans player from server
- **Unban Player** - Removes ban from player
- **Whitelist Player** - Adds player to whitelist
- **Give XP** - Awards experience points

### Server Operations
- **Broadcast** - Sends message to all players
- **Save World** - Forces server to save
- **Destroy Wild Dinosaurs** - Clears wild dinos

### Server Control (Self-Hosted Only)
- **Start Server** - Starts the NSSM service
- **Stop Server** - Gracefully shuts down server
- **Restart Server** - Restarts the server
- **Server Status** - Checks service status

### Advanced Operations
- **Update Server** - Updates server via SteamCMD
- **Update All Servers** - Sequential updates for all servers
- **Custom RCON** - Executes custom RCON commands
- **Set MOTD** - Sets message of the day

### Diagnostics
- **View Log** - Views server log files
- **View Errors** - Filters log for errors
- **Crash History** - Shows recent server crashes

## Log Entry Details

Each admin action logged includes:

- **Timestamp** - When the action was executed
- **Admin** - Which admin ran the command (name + Discord ID)
- **Action Type** - Type of action (kick, ban, update, etc)
- **Servers Affected** - Which servers were targeted
- **Target** - Player affected (if applicable)
- **Details** - Full command parameters and context
- **Status** - Success, failed, or partial
- **Results** - Output/response from the server
- **Message ID** - Link to Discord message

## Admin Notifications

When an admin executes a command:

1. **Immediate Notification** - Ephemeral message showing:
   - Which servers will be targeted
   - Command being sent
   - 📤 "Action Sent to Servers"

2. **Result Notification** - After command executes:
   - ✅ Success or ❌ Failed status
   - Server responses
   - Any errors

3. **Log Channel Post** - Permanent record showing:
   - Full action details
   - Results for audit trail
   - Searchable log entry

## Querying Logs

### In Discord

Use `/adminlogs` command to view recent admin actions:

```discord
/adminlogs [admin] [action] [days]
```

Examples:
```
/adminlogs                    # Last 50 actions in last 7 days
/adminlogs admin:@User123     # All actions by that admin
/adminlogs action:kick        # All kick actions
/adminlogs days:30            # Last 30 days of activity
```

### In Database

Logs are stored in SQLite: `bot/database/admin_logs.db`

Table: `admin_logs`

```sql
SELECT * FROM admin_logs 
WHERE action_type = 'kick' 
  AND timestamp > datetime('now', '-7 days')
ORDER BY timestamp DESC;
```

## Privacy & Security

- Only admins can view admin logs
- Logs show which admin performed the action
- All logs are timestamped
- 90-day retention by default (configurable)
- Database stored locally for security

## Cleaning Up Old Logs

By default, logs older than 90 days are automatically removed. To change this:

Edit `bot/cogs/admin.py` and update the cleanup task:

```python
@tasks.loop(hours=24.0)
async def cleanup_admin_logs(self):
    """Daily cleanup of old admin logs"""
    await admin_logs_db.cleanup_old_logs(days=90)  # Change 90 to desired days
```

## Examples

### Kick Example

Admin runs: `/kick Player123` with reason "Griefing"

**Immediate Notification (to admin):**
```
📤 Action Sent to Servers
Sending kick command to servers...

Servers: Amissa, Island

Target: Player123
```

**Result Notification (to admin):**
```
✅ Action Completed
KICK - SUCCESS

Servers: Amissa, Island

Results:
Player Player123 successfully kicked
```

**Admin Log Channel Post:**
```
🔐 Admin Action: KICK
Admin: @User123#1234

Servers Affected: Amissa, Island
Target Player: Player123
Player ID: `123456789`

Details:
command: KickPlayer
reason: Griefing
player_name: Player123

Status: SUCCESS

Results:
Player Player123 successfully kicked

Log ID: 42
```

### Server Update Example

Admin runs: `/updateservers` with Full Validation

**Admin Log Channel Post:**
```
🔐 Admin Action: UPDATE_ALL_SERVERS
Admin: @Admin#5678

Servers Affected: Amissa, Island, Crystal Isles

Details:
mode: Full Validation with SteamCMD
validate: true

Status: SUCCESS

Results:
✅ Amissa: Updated & restarted
✅ Island: Updated & restarted
✅ Crystal Isles: Updated & restarted

Log ID: 43
```

## Troubleshooting

### Logs not appearing in channel

1. Verify `/setadminlogchannel` was run
2. Check bot has message permissions in that channel
3. Verify `ADMIN_LOG_CHANNEL_ID` is set correctly

### Logs not appearing in database

1. Verify `bot/database/admin_logs.db` exists
2. Check bot has write permissions to database directory
3. Check bot logs for database errors

### Missing admin action

Not all actions may be logged if:
- New feature hasn't been integrated yet
- Action failed before execution
- Database write failed silently

Report missing logs for investigation.

## Future Enhancements

Potential additions to logging system:

- [ ] Admin log viewer web interface
- [ ] Log export to CSV
- [ ] Automated alerts for certain actions (bans, kicks, updates)
- [ ] Action approval workflow (admins review before execution)
- [ ] Rollback capabilities for some actions
- [ ] Integration with Discord audit log

