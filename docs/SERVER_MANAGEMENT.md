# Server Management - NSSM Integration

Complete guide to managing ARK servers through Discord using NSSM service control.

## Overview

The bot provides full control over ARK servers running as NSSM (Non-Sucking Service Manager) Windows services. Admins can start, stop, restart, update, and monitor servers directly from Discord without needing remote desktop access.

## Features

### 🎯 Core Capabilities

- **Service Control**: Start, stop, and restart any ARK server
- **Status Monitoring**: Real-time status checking for all servers
- **Automated Updates**: Update servers via SteamCMD with validation
- **Log Viewing**: Read recent server logs from Discord
- **Countdown Warnings**: Automatic in-game warnings before shutdowns/restarts
- **Audit Logging**: All actions logged to status channel with admin attribution

### 🔒 Security

- All commands require the configured admin role
- Commands are ephemeral (only visible to the user who ran them)
- Server actions are logged with timestamps and user attribution
- Safe defaults (60-second countdown for stops/restarts)

## Commands

### `/serverstatus`

Check the status of all ARK servers at once.

**Output**: Embed showing all servers with status indicators:
- 🟢 Running
- 🔴 Stopped  
- 🟡 Paused
- ⚪ Unknown

**Example**:
```
/serverstatus
```

---

### `/serverstart <server>`

Start a stopped ARK server.

**Parameters**:
- `server` (required): The server to start (autocomplete available)

**Features**:
- Checks if server is already running
- Sends confirmation to status channel
- Shows admin who started the server

**Example**:
```
/serverstart server:Aberration
```

---

### `/serverstop <server> [countdown]`

Stop a running ARK server with optional countdown.

**Parameters**:
- `server` (required): The server to stop
- `countdown` (optional): Seconds before stopping (default: 60)

**Features**:
- In-game warnings at 60, 30, 10, and 5 seconds
- Prevents accidental instant shutdowns
- Can be set to 0 for immediate stop
- Checks if server is already stopped

**Examples**:
```
/serverstop server:The Island countdown:120
/serverstop server:Ragnarok countdown:0
```

**In-Game Warnings**: Players see messages like:
```
[SERVER] Server restarting in 60 seconds!
[SERVER] Server restarting in 30 seconds!
[SERVER] Server restarting in 10 seconds!
[SERVER] Server restarting in 5 seconds!
```

---

### `/serverrestart <server> [countdown]`

Restart an ARK server with countdown warnings.

**Parameters**:
- `server` (required): The server to restart
- `countdown` (optional): Seconds before restarting (default: 60)

**Features**:
- Same countdown system as `/serverstop`
- Automatically restarts after stopping
- Useful for applying configuration changes
- Works on both running and stopped servers

**Examples**:
```
/serverrestart server:Aberration countdown:300
/serverrestart server:Scorched Earth
```

---

### `/serverupdate <server> [validate]`

Update an ARK server using SteamCMD.

**Parameters**:
- `server` (required): The server to update
- `validate` (optional): Validate all files (default: false)

**Features**:
- Stops server before updating
- Runs SteamCMD with ARK Ascended App ID (2430930)
- Restarts server if it was running before update
- 30-minute timeout protection
- Optional file validation for troubleshooting

**Process**:
1. Stops the server if running
2. Runs SteamCMD update
3. Validates files (if requested)
4. Restarts server (if it was running)
5. Posts completion status to status channel

**Examples**:
```
/serverupdate server:The Island validate:false
/serverupdate server:Extinction validate:true
```

**Note**: Validation is much slower but useful for fixing corrupted files.

---

### `/serverlogs <server> [lines]`

View recent log entries from a server.

**Parameters**:
- `server` (required): The server to view logs for
- `lines` (optional): Number of lines to show (default: 20)

**Features**:
- Reads from ShooterGame.log
- Displays in formatted code block
- Automatically truncates if too long
- Shows timestamp and line count

**Examples**:
```
/serverlogs server:Aberration lines:50
/serverlogs server:The Center
```

## Configuration

### Server Mapping

The bot knows about all your NSSM services. Current servers configured:

| Service Name | Display Name |
|--------------|--------------|
| `asa_aberration` | Aberration |
| `asa_amissa` | Amissa |
| `asa_astraeos` | Astraeos |
| `asa_center` | The Center |
| `asa_eventmap` | Event Map |
| `asa_eventmap_old` | Event Map (Old) |
| `asa_extinction` | Extinction |
| `asa_insaluna` | Insaluna |
| `asa_island` | The Island |
| `asa_ragnarok` | Ragnarok |
| `asa_ragvegas` | Ragvegas |
| `asa_scorched` | Scorched Earth |
| `asa_valguero` | Valguero |

### File Paths

These are configured in `bot/cogs/server_management.py`:

```python
NSSM_PATH = r"C:\nssm\nssm.exe"
ARK_BASE_PATH = r"C:/ARK\Servers"
STEAMCMD_PATH = r"C:\SteamCMD\steamcmd.exe"
```

**To modify**:
1. Open `bot/cogs/server_management.py`
2. Update the paths in the `ServerManagement` class
3. Restart the bot

### Adding New Servers

To add a new server to the management system:

1. Open `bot/cogs/server_management.py`
2. Add entry to `ARK_SERVICES` dictionary:
   ```python
   ARK_SERVICES = {
       ...
       "asa_newmap": "New Map Display Name",
   }
   ```
3. Ensure the NSSM service name matches exactly
4. Restart the bot

## Integration with Other Features

### RCON Integration

Server management commands integrate with the RCON system:
- Countdown warnings are sent via RCON `ServerChat` command
- Players see in-game notifications before stops/restarts
- Requires server to be running and RCON configured

### Status Channel

All server management actions are logged to the configured status channel:
- Start/stop/restart notifications
- Update completion messages
- Admin attribution (who performed the action)
- Timestamps for all operations

### Voice Channel Status

Server status changes automatically update voice channel indicators (if configured):
- 🟢 Shows when server starts
- 🔴 Shows when server stops
- Player count updates every 30 seconds

## Workflow Examples

### Routine Daily Restart

```
/serverrestart server:Aberration countdown:300
```
- Warns players 5 minutes before restart
- Automatically restarts the server
- Logs action to status channel

### Applying Config Changes

1. Make changes to GameUserSettings.ini or Game.ini
2. Run: `/serverrestart server:The Island countdown:60`
3. Server restarts and loads new config

### Weekly Update Maintenance

```
/serverupdate server:Ragnarok validate:false
```
- Stops server gracefully
- Downloads latest ARK updates
- Restarts server automatically
- Takes 5-15 minutes typically

### Emergency Server Stop

```
/serverstop server:Scorched Earth countdown:0
```
- Stops immediately without countdown
- Use only in emergencies

### Troubleshooting Crashes

```
/serverlogs server:Extinction lines:100
```
- View last 100 log lines
- Look for errors or crash indicators
- Help diagnose server issues

## Best Practices

### ✅ Do

- Always use countdown for stops/restarts during active play
- Check `/serverstatus` before performing maintenance
- Use validation when troubleshooting file corruption
- View logs after crashes to diagnose issues
- Coordinate with players in Discord before restarts

### ❌ Don't

- Don't use `countdown:0` during active play
- Don't update multiple servers simultaneously (resource intensive)
- Don't interrupt updates in progress (30-minute timeout)
- Don't forget to check logs if server won't start after update

## Troubleshooting

### Server Won't Start

1. Check service status: `/serverstatus`
2. View logs: `/serverlogs server:ServerName lines:50`
3. Look for errors in output
4. Try validation update: `/serverupdate server:ServerName validate:true`

### Update Fails

1. Check SteamCMD is installed at configured path
2. Verify disk space (ARK updates can be large)
3. Try manual SteamCMD update
4. Check firewall/antivirus isn't blocking

### Commands Not Working

1. Verify you have the admin role
2. Check bot is running on the actual server (not dev machine)
3. Verify NSSM path is correct: `C:\nssm\nssm.exe`
4. Check Windows services show the ARK services

### Countdown Warnings Not Appearing In-Game

1. Verify RCON is configured correctly for the server
2. Check server is in the RCON client list
3. Test with `/rcon ServerChat Test message`
4. Verify server name in RCON matches display name

## Technical Details

### NSSM Command Reference

The bot uses these NSSM commands internally:

```powershell
# Check status
C:\nssm\nssm.exe status asa_aberration

# Start service
C:\nssm\nssm.exe start asa_aberration

# Stop service
C:\nssm\nssm.exe stop asa_aberration

# Restart service
C:\nssm\nssm.exe restart asa_aberration
```

### SteamCMD Update Command

```powershell
C:\SteamCMD\steamcmd.exe `
  +force_install_dir "C:/ARK\Servers\Aberration" `
  +login anonymous `
  +app_update 2430930 `
  +quit
```

### Log File Locations

```
C:/ARK\Servers\{ServerName}\ShooterGame\Saved\Logs\ShooterGame.log
```

## Future Enhancements

Potential additions for future versions:

- [ ] Bulk operations (restart all servers)
- [ ] Scheduled maintenance windows
- [ ] Automatic crash detection and restart
- [ ] Performance monitoring (CPU/RAM usage)
- [ ] Backup management commands
- [ ] Config file editing from Discord
- [ ] Mod update notifications
- [ ] Player count graphs/analytics

## Support

If you encounter issues:

1. Check the bot logs for error messages
2. Verify file paths are correct for your system
3. Test NSSM commands manually in PowerShell
4. Check Discord permissions for the bot
5. Review the admin role configuration

## Security Considerations

- Commands require admin role (configured in .env)
- File paths are validated before access
- Subprocess timeouts prevent hanging
- All actions are logged with user attribution
- Commands are ephemeral (private responses)
- No user input is executed directly in shell
