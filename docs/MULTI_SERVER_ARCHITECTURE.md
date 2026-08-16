# Multi-Server Database Architecture

## Overview

The Phoenix ARK Bot has been redesigned to support multiple Discord servers (guilds) with per-server configuration stored in a database. This eliminates the need for complex .env configuration and makes the bot truly distributable.

## Key Changes

### Before (Single Server, .env-based)
- All configuration in .env file
- One bot instance = one Discord server
- Requires code/config changes for each deployment
- Channel IDs, server settings hardcoded

### After (Multi-Server, Database-driven)
- **Only bot token in .env**
- One bot instance = unlimited Discord servers
- Zero configuration files to edit (except token)
- All settings managed through Discord commands
- Each server has independent configuration

## Architecture Components

### 1. Database Schema

#### `server_configs` Table
Stores per-guild configuration:
- Channel IDs (chat, status, shop, log, announcements)
- Admin role ID
- Bot prefix and currency settings
- Shop economy settings
- Update intervals

#### `server_ark_servers` Table
Stores ARK servers per guild:
- Server name, host, RCON port/password
- Max players, chat enabled
- Per-server enable/disable toggle
- Linked to guild via foreign key

### 2. Setup Commands (New Cog)

All configuration through Discord slash commands:

- `/setup` - Interactive setup wizard
- `/setchannels` - Configure Discord channels
- `/setadminrole` - Set bot admin role
- `/setshop` - Configure shop economy
- `/addserver` - Add ARK server to monitor
- `/listservers` - View configured servers
- `/removeserver` - Remove ARK server
- `/config` - View current configuration

### 3. Simplified .env

```env
# Only this is required!
DISCORD_BOT_TOKEN=your_token_here

# Optional (has defaults):
DATABASE_PATH=ark_bot.db
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
```

## Distribution Workflow

### For Bot Developer (You)
1. Develop bot with database-driven config
2. Push to GitHub
3. Share GitHub repo or zip file
4. Provide minimal .env.template (just token)

### For Server Owner (User)
1. Download bot files
2. Create .env with only their bot token
3. Invite bot to their Discord
4. Run bot: `python main.py`
5. Use `/setup` in Discord to configure everything
6. Done! No code editing, no complex configuration

## Migration Path

### Option 1: Fresh Start (Recommended for Distribution)
1. Implement new database schema
2. Create setup.py cog
3. Update existing cogs to read from database
4. Test with clean database
5. Distribute to users

### Option 2: Hybrid (For Your Current Deployment)
1. Keep existing .env configuration
2. Add database config system
3. Bot checks database first, falls back to .env
4. Gradually migrate settings to database
5. Eventually remove .env dependencies

## Implementation Status

### ✅ Created
- `bot/database/server_config_db.py` - Database operations
- `bot/cogs/setup.py` - Setup commands
- `.env.template` - Minimal template

### ⚠️ Needs Updates
- `main.py` - Initialize server_config tables
- `bot/cogs/server_monitor.py` - Read servers from database
- `bot/cogs/chat_relay.py` - Read config from database
- `bot/cogs/store.py` - Read shop config from database
- `bot/cogs/shop_manager.py` - Read channels from database
- `bot/database/user_db.py` - Per-guild user isolation

### 🔄 Database Changes Needed
- Add guild_id to users table (multi-server support)
- Add guild_id to store_items table (per-server shops)
- Add guild_id to transactions table
- Update all queries to filter by guild_id

## Benefits

### For You (Developer)
- ✅ True multi-server bot (host once, serve many)
- ✅ No manual configuration per deployment
- ✅ Users can self-service configuration
- ✅ Easier to support/troubleshoot
- ✅ Configuration backed up in database

### For Users (Server Owners)
- ✅ Simple setup (just bot token)
- ✅ No file editing required
- ✅ User-friendly Discord commands
- ✅ Can't break bot with bad config
- ✅ Easy to add/remove servers
- ✅ Live configuration changes

## Next Steps

1. **Test Current Implementation**
   - Verify server_config_db.py works
   - Test setup.py commands
   - Ensure database tables created correctly

2. **Update Existing Cogs**
   - Modify each cog to query database for config
   - Add guild_id context to all operations
   - Update database queries for multi-guild

3. **Add Migration Tool**
   - Create command to import .env settings to database
   - One-time migration for your deployment
   - Optional for new users

4. **Documentation**
   - README for server owners
   - Quick start guide
   - Troubleshooting section
   - Video tutorial (optional)

## Security Considerations

- Bot token still secured in .env (never in database)
- RCON passwords encrypted in database (TODO)
- Admin commands check guild permissions
- Each guild isolated from others
- No cross-guild data access

## Performance Notes

- Database queries cached per-guild
- Configuration loaded once per guild on startup
- Updates trigger cache refresh
- Voice channels still use in-memory tracking
- Minimal overhead vs .env approach

## Rollback Plan

If multi-server approach causes issues:
1. Keep existing .env configuration
2. Make database config optional
3. Bot prefers .env if present
4. Gradual migration possible
5. No breaking changes required
