# ARK Server Management - RCON Admin Commands

Complete guide to managing your ARK servers via Discord using RCON commands. These commands work for both local servers and remote servers (like Nitrado) as long as RCON and query ports are accessible.

## 🎮 Overview

The bot now includes **25+ server management commands** divided into categories:

### NSSM Service Control (Local Servers)
Commands for controlling ARK server services on the host machine:
- `/serverstatus` - Check status of all servers
- `/serverstart` - Start a server
- `/serverstop` - Stop a server (with countdown)
- `/serverrestart` - Restart a server (with countdown)
- `/serverupdate` - Update via SteamCMD
- `/serverlogs` - View recent server logs

### RCON Admin Commands (Local + Remote Servers)
These work for **any server** with RCON access (local or Nitrado):

#### 👥 Player Management
- `/listplayers` - List online players
- `/kickplayer` - Kick a player
- `/banplayer` - Ban a player
- `/unbanplayer` - Unban a player
- `/whitelistplayer` - Add player to whitelist

#### 📢 Server Control
- `/broadcast` - Send message to all players
- `/saveworld` - Force world save
- `/destroywilddinos` - Wipe all wild dinos
- `/setmotd` - Set message of the day

#### 🎁 Item & Dino Management
- `/giveitem` - Give item to player
- `/givedino` - Give tamed dino to player
- `/giveexptoplayer` - Give XP to player

#### ⚙️ Admin Utilities
- `/rcon` - Execute custom RCON command
- `/getchat` - View recent chat messages
- `/setplayerpos` - Teleport player to coordinates

---

## 📋 Command Reference

### Player Management Commands

#### `/listplayers`
Get a list of all players currently online.

**Usage:**
```
/listplayers server_name:Aberration
```

**Parameters:**
- `server_name` (required) - Server to check

**Example Output:**
```
👥 Online Players - Aberration
Total: 3

• Player1 (Steam ID: 76561198012345678)
• Player2 (Steam ID: 76561198087654321)
• Player3 (Steam ID: 76561198011111111)
```

---

#### `/kickplayer`
Kick a player from the server.

**Usage:**
```
/kickplayer player_name:Player1 server_name:Aberration
```

**Parameters:**
- `player_name` (required) - Player name or Steam ID
- `server_name` (required) - Server to kick from

**Notes:**
- Kicked players can rejoin immediately
- Action is logged to admin log channel
- Use for temporary removal

---

#### `/banplayer`
Permanently ban a player from the server.

**Usage:**
```
/banplayer player_name:Player1 server_name:Aberration
```

**Parameters:**
- `player_name` (required) - Player name or Steam ID
- `server_name` (required) - Server to ban from

**Notes:**
- Banned players cannot rejoin until unbanned
- Action is logged to admin log channel
- Ban persists across server restarts

---

#### `/unbanplayer`
Remove a player from the ban list.

**Usage:**
```
/unbanplayer player_id:76561198012345678 server_name:Aberration
```

**Parameters:**
- `player_id` (required) - Steam ID or Player ID
- `server_name` (required) - Server to unban from

**Notes:**
- Requires Steam ID (more reliable than player name)
- Player can rejoin after unban

---

#### `/whitelistplayer`
Add a player to the server whitelist.

**Usage:**
```
/whitelistplayer steam_id:76561198012345678 server_name:Aberration
```

**Parameters:**
- `steam_id` (required) - Player's Steam ID
- `server_name` (required) - Server to whitelist on

**Notes:**
- Useful for private/whitelisted servers
- Player can bypass connection restrictions

---

### Server Control Commands

#### `/broadcast`
Send a message to all players on one or all servers.

**Usage:**
```
/broadcast message:"Server restarting in 10 minutes!" server_name:Aberration
```

**Broadcast to all servers:**
```
/broadcast message:"Happy holidays from the admin team!"
```

**Parameters:**
- `message` (required) - Message to broadcast
- `server_name` (optional) - Specific server (omit for all)

**Notes:**
- Messages appear in server chat
- Use for announcements, warnings, events
- Can broadcast to all servers at once

---

#### `/saveworld`
Force the server to save the current world state.

**Usage:**
```
/saveworld server_name:Aberration
```

**Save all servers:**
```
/saveworld
```

**Parameters:**
- `server_name` (optional) - Specific server (omit for all)

**Notes:**
- Use before updates or maintenance
- Prevents data loss
- Can save all servers simultaneously

---

#### `/destroywilddinos`
Delete all wild dinosaurs to force respawns.

**Usage:**
```
/destroywilddinos server_name:Aberration
```

**Parameters:**
- `server_name` (optional) - Specific server (omit for all)

**Notes:**
- Used to refresh wild dino spawns
- Does not affect tamed dinos
- Dinos respawn gradually after wipe
- Can cause brief server lag

---

#### `/setmotd`
Set the server's message of the day.

**Usage:**
```
/setmotd message:"Welcome to our server! Check Discord for rules." server_name:Aberration
```

**Parameters:**
- `message` (required) - Message of the day
- `server_name` (optional) - Specific server (omit for all)

**Notes:**
- Displayed to players on login
- Can be set for all servers at once
- Useful for rules, events, announcements

---

### Item & Dino Commands

#### `/giveitem`
Give an item to a player.

**Usage:**
```
/giveitem player_name:Player1 item_id:PrimalItemResource_MetalIngot_C quantity:100 quality:0 blueprint:false server_name:Aberration
```

**Parameters:**
- `player_name` (required) - Player name
- `item_id` (required) - Item blueprint ID
- `server_name` (required) - Server
- `quantity` (optional) - Amount (default: 1)
- `quality` (optional) - Quality/tier (default: 0)
- `blueprint` (optional) - Give as blueprint (default: false)

**Common Item IDs:**
- `PrimalItemResource_MetalIngot_C` - Metal Ingot
- `PrimalItemResource_Stone_C` - Stone
- `PrimalItemResource_Wood_C` - Wood
- `PrimalItemResource_Fiber_C` - Fiber
- `PrimalItemWeapon_Rifle_C` - Fabricated Rifle
- `PrimalItemArmor_RiotShield_C` - Riot Shield

**Notes:**
- Player must be online
- Items go to player inventory
- Use quality for ascendant/mastercraft items

---

#### `/givedino`
Give a tamed dinosaur to a player.

**Usage:**
```
/givedino player_name:Player1 dino_type:Rex_Character_BP_C level:150 server_name:Aberration
```

**Parameters:**
- `player_name` (required) - Player name
- `dino_type` (required) - Dinosaur blueprint class
- `level` (required) - Dinosaur level
- `server_name` (required) - Server

**Common Dino Types:**
- `Rex_Character_BP_C` - T-Rex
- `Giga_Character_BP_C` - Giganotosaurus
- `Argent_Character_BP_C` - Argentavis
- `Ankylo_Character_BP_C` - Ankylosaurus
- `Wyvern_Character_BP_C` - Wyvern

**Notes:**
- Spawns tamed dino near player
- Dino will be owned by player
- Use appropriate levels for balance

---

#### `/giveexptoplayer`
Give experience points to a player.

**Usage:**
```
/giveexptoplayer player_name:Player1 xp_amount:100000 tribe_share:false server_name:Aberration
```

**Parameters:**
- `player_name` (required) - Player name or Steam ID
- `xp_amount` (required) - Amount of XP to give
- `server_name` (required) - Server
- `tribe_share` (optional) - Share with tribe (default: false)

**Notes:**
- Use for events, rewards, compensation
- XP applies to player character
- Tribe share distributes XP to tribe members

---

### Admin Utility Commands

#### `/rcon`
Execute a custom RCON command.

**Usage:**
```
/rcon command:"DoTame" server_name:Aberration
```

**Parameters:**
- `command` (required) - RCON command to execute
- `server_name` (required) - Server to execute on

**Common RCON Commands:**
- `DoTame` - Tame dino you're looking at
- `EnemyInvisible true` - Make yourself invisible
- `Fly` - Enable flying
- `Walk` - Disable flying
- `Ghost` - Enable noclip
- `GMBuff` - Give god mode + stats
- `InfiniteStats` - Infinite stats

**Notes:**
- For advanced admins
- Can execute any valid RCON command
- Use with caution

---

#### `/getchat`
View recent chat messages from the server.

**Usage:**
```
/getchat server_name:Aberration
```

**Parameters:**
- `server_name` (required) - Server to get chat from

**Notes:**
- Shows recent in-game chat
- Useful for moderation
- Limited to last ~50 messages

---

#### `/setplayerpos`
Teleport a player to specific coordinates.

**Usage:**
```
/setplayerpos player_name:Player1 x:100000 y:50000 z:10000 server_name:Aberration
```

**Parameters:**
- `player_name` (required) - Player name or Steam ID
- `x` (required) - X coordinate
- `y` (required) - Y coordinate
- `z` (required) - Z coordinate
- `server_name` (required) - Server

**Notes:**
- Player must be online
- Useful for unsticking players
- Get coordinates from in-game GPS

---

## 🔐 Permissions

All RCON admin commands require:
- **Discord Administrator permission**, OR
- **Configured admin role** (set via `/setadminrole`)

This ensures only trusted users can manage servers.

---

## 🌐 Remote Server Support (Nitrado)

These commands work with **remote servers** like Nitrado as long as:

### Requirements:
1. **RCON enabled** on server
2. **RCON port** accessible from bot host
3. **RCON password** configured in bot settings

### Nitrado Configuration:
1. Log into Nitrado web interface
2. Go to your ARK server settings
3. Enable RCON
4. Set RCON password
5. Note the RCON port (usually different from game port)
6. Add RCON port to firewall rules

### Bot Configuration:
Add your Nitrado servers via `/addserver`:
```
/addserver 
  name:Nitrado-Island 
  host:your-nitrado-ip.com 
  rcon_port:27015 
  rcon_password:YourRconPassword 
  max_players:70
```

---

## 🎯 Common Use Cases

### Routine Maintenance
```
1. /broadcast message:"Server maintenance in 10 minutes" server_name:Aberration
2. Wait 10 minutes
3. /saveworld server_name:Aberration
4. /serverstop server_name:asa_aberration countdown:60
5. Perform updates
6. /serverstart server_name:asa_aberration
```

### Dino Refresh Event
```
1. /broadcast message:"Wild dino wipe in 5 minutes!"
2. Wait 5 minutes
3. /destroywilddinos server_name:Aberration
4. /broadcast message:"Wild dinos wiped! Happy hunting!"
```

### Player Management
```
# Check who's online
/listplayers server_name:Aberration

# Kick troublesome player
/kickplayer player_name:BadPlayer server_name:Aberration

# If they return and cause issues
/banplayer player_name:BadPlayer server_name:Aberration

# Unban after appeal
/unbanplayer player_id:76561198012345678 server_name:Aberration
```

### Event Rewards
```
# Give items
/giveitem player_name:Winner1 item_id:PrimalItemResource_MetalIngot_C quantity:1000 server_name:Aberration

# Give dino
/givedino player_name:Winner1 dino_type:Rex_Character_BP_C level:150 server_name:Aberration

# Give XP
/giveexptoplayer player_name:Winner1 xp_amount:500000 server_name:Aberration
```

---

## 🛠️ Troubleshooting

### "Failed to execute RCON command"
**Causes:**
- RCON port not accessible
- Wrong RCON password
- Server offline
- Firewall blocking connection

**Solutions:**
1. Verify server is running: `/serverstatus`
2. Check RCON settings in server config
3. Verify firewall rules allow RCON port
4. Test RCON with external tool first

### "Player not found"
**Causes:**
- Player offline
- Incorrect player name
- Player name has special characters

**Solutions:**
- Use Steam ID instead of name
- Get Steam ID from `/listplayers`
- Verify player is online

### "Command timed out"
**Causes:**
- Server lagging
- Large operation (like destroy wild dinos)
- Network issues

**Solutions:**
- Wait and try again
- Check server performance
- For large operations, expect delays

---

## 📊 Command Summary

| Category | Commands | Purpose |
|----------|----------|---------|
| **Service Control** | 6 commands | Start, stop, restart local servers |
| **Player Management** | 5 commands | Kick, ban, whitelist players |
| **Server Control** | 4 commands | Broadcast, save, dino wipe, MOTD |
| **Items & Dinos** | 3 commands | Give items, dinos, XP |
| **Admin Utilities** | 3 commands | Custom RCON, chat, teleport |
| **TOTAL** | **21 commands** | Complete server management |

---

## 🚀 Quick Start

1. **Set admin role:**
   ```
   /setadminrole role:@ServerAdmin
   ```

2. **Add your servers** (if not using .env):
   ```
   /addserver name:Aberration host:localhost rcon_port:27020 rcon_password:YourPassword max_players:70
   ```

3. **Test connection:**
   ```
   /listplayers server_name:Aberration
   ```

4. **Start managing:**
   ```
   /broadcast message:"Bot is online! Server management active."
   ```

---

## 💡 Pro Tips

1. **Use server autocomplete** - All commands have server name autocomplete for easy selection

2. **Batch operations** - Commands without `server_name` apply to all servers (broadcast, save, dino wipe)

3. **Countdown warnings** - Always use countdown for stop/restart to warn players

4. **Log channel** - Configure `/setchannels` to log admin actions automatically

5. **Steam IDs > Names** - Use Steam IDs for bans/unbans (more reliable)

6. **Test commands** - Test on one server before applying to all

7. **Save before maintenance** - Always `/saveworld` before stopping servers

8. **RCON for remote** - RCON commands work on Nitrado/remote servers too

---

## 📝 Notes

- **Admin permissions required** for all commands
- **RCON must be enabled** on servers
- **Works with local and remote servers** (Nitrado, etc.)
- **Actions are logged** to admin log channel (if configured)
- **Autocomplete available** for server selection
- **Embeds used** for clear, formatted responses

---

## 🎮 Example Workflow: Daily Server Management

```bash
# Morning: Check status
/serverstatus

# Save all servers
/saveworld

# Afternoon: Dino refresh
/broadcast message:"Wild dino wipe in 5 minutes"
# Wait 5 minutes
/destroywilddinos

# Check who's online
/listplayers server_name:Aberration
/listplayers server_name:TheIsland

# Evening: Restart for updates
/broadcast message:"Server restart for updates in 10 minutes"
# Wait 10 minutes
/serverrestart server_name:asa_aberration countdown:60
```

---

## 📧 Support

For issues or feature requests, see the bot's documentation or contact the administrator.

**Available Commands:**
- Type `/` in Discord to see all available commands
- Commands have autocomplete for easy use
- All commands show helpful descriptions

---

**Last Updated:** December 2024
**Version:** 2.0 - RCON Admin Commands Added
