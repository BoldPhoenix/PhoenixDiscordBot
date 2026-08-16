# Chat Relay Setup Guide

## Overview

The bot provides **bidirectional chat relay** between Discord and your ARK servers:
- **Discord → ARK**: Messages from Discord are broadcast to all configured servers
- **ARK → Discord**: In-game chat is monitored via log file parsing and posted to Discord

## How It Works

### Discord to ARK
When a user posts in the designated chat channel, the bot:
1. Formats the message as `[Discord] Username: message`
2. Sends it to all servers with `chat_enabled: true` via RCON
3. Confirms delivery with a ✅ reaction

### ARK to Discord
The bot monitors each server's log file:
1. Reads new lines from `ShooterGame.log` every 2 seconds
2. Parses chat messages using regex patterns
3. Posts formatted messages to Discord as embeds
4. Prevents duplicate messages with deduplication logic

## Configuration

### 1. Enable Chat Relay

In your `.env` file, set the chat channel:
```env
CHAT_CHANNEL_ID=555555555555555555
```

### 2. Configure Server Log Paths

Add `log_path` to each server in `ARK_SERVERS`:

```json
ARK_SERVERS=[
  {
    "name": "Aberration",
    "host": "127.0.0.1",
    "rcon_port": 27001,
    "rcon_password": "your_password",
    "chat_enabled": true,
    "log_path": "C:/ARK/Servers/Aberration/ShooterGame/Saved/Logs/ShooterGame.log"
  },
  {
    "name": "The Island",
    "host": "127.0.0.1",
    "rcon_port": 27008,
    "rcon_password": "your_password",
    "chat_enabled": true,
    "log_path": "C:/ARK/Servers/TheIsland/ShooterGame/Saved/Logs/ShooterGame.log"
  }
]
```

**Important Notes:**
- Use forward slashes `/` in paths (even on Windows)
- Path must be accessible by the bot process
- If running as NSSM service, ensure the service account has read access
- Log file must exist before bot starts

### 3. Finding Your Log Files

ARK log files are typically located at:
```
<ARK_Install_Path>/ShooterGame/Saved/Logs/ShooterGame.log
```

**Common paths:**
- Default install: `C:/Program Files/ARK/ShooterGame/Saved/Logs/ShooterGame.log`
- Custom install: `<YourPath>/ARK/ShooterGame/Saved/Logs/ShooterGame.log`
- Multiple servers: Each server has its own directory with separate logs

## Testing

### Verify Log Monitoring

1. Check bot logs for initialization messages:
```
INFO - Initialized log monitor for Aberration: C:/ARK/.../ShooterGame.log
```

2. Send a test message in-game and verify it appears in Discord

3. Send a test message in Discord and verify it appears in-game

### Troubleshooting

**No messages from ARK to Discord:**
- Verify log file path is correct
- Check file permissions (bot needs read access)
- Ensure `chat_enabled: true` for the server
- Check bot logs for errors
- Verify CHAT_CHANNEL_ID is set correctly

**Messages not appearing in ARK:**
- Test RCON connectivity: `/broadcast test message`
- Verify RCON password is correct
- Check if server is running and accepting RCON commands

**Duplicate messages:**
- The bot includes deduplication logic
- If duplicates persist, check for multiple bot instances running

**Log file doesn't exist:**
- ARK creates log files on first server start
- Verify the server has run at least once
- Check the exact path in Windows Explorer

## Chat Message Formats

### Supported Patterns

The bot recognizes these chat formats:
1. `[timestamp] PlayerName: message` (standard ASA format)
2. `<PlayerName> message` (alternative format)

### Filtered Messages

The bot automatically filters out:
- Empty messages
- System messages
- Commands starting with `/`
- Duplicate messages

## Performance

- **Polling interval**: 2 seconds (configurable via `CHAT_POLL_INTERVAL`)
- **File I/O**: Async file operations via `aiofiles`
- **Memory usage**: Maintains position pointer to avoid re-reading entire file
- **Deduplication cache**: Stores last 100 unique messages per server

## Advanced Configuration

### Adjusting Poll Interval

In `.env`:
```env
CHAT_POLL_INTERVAL=2  # Check logs every 2 seconds (default: 5)
```

Lower values = more responsive chat, but higher CPU usage.

### Custom Chat Patterns

To support additional log formats, edit `bot/cogs/chat_relay.py`:

```python
self.chat_patterns = [
    re.compile(r'\[[\d:\.]+\]\s+(.+?):\s+(.+)'),  # Standard
    re.compile(r'<(.+?)>\s+(.+)'),  # Alternative
    re.compile(r'YOUR_CUSTOM_PATTERN'),  # Add yours here
]
```

## Discord Slash Commands

### User Commands
- *None* (chat relay works automatically)

### Admin Commands
- `/setchatchannel <channel>` - Change the chat relay channel
- `/reloadconfig` - Reload configuration (including log paths)

## Migration from Other Bots

If migrating from Arkon Bot or ASA-Bot:
1. Set `CHAT_CHANNEL_ID` to your existing chat channel
2. Configure log paths for each server
3. Disable chat relay in old bots to prevent duplicates
4. Test with `/broadcast test` before full cutover

## Security Notes

- Log files may contain sensitive information (player IPs, etc.)
- Bot only reads chat messages (filters other content)
- Ensure bot host has restricted access to server files
- Use Windows service account with minimal permissions

## Limitations

- **Log rotation**: If ARK rotates logs, bot may miss messages during rotation
- **Server restarts**: Bot needs log file to exist; will resume on next check
- **Very high traffic**: Consider increasing poll interval if CPU usage is high
- **No message history**: Bot only sees new messages after startup

## Support

If chat relay isn't working:
1. Check bot logs for errors
2. Verify configuration with `/config`
3. Test RCON connectivity with `/serverstatus`
4. Ensure log file permissions are correct
5. Review this guide for common issues
