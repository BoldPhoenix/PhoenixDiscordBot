# Phoenix ArkBot - Command Structure

## GUI Management Commands (Admin Only)

These are the main interactive management interfaces:

### `/setupcfg` - Initial Bot Setup
**Purpose**: Configure Discord channels, roles, hosting type, and basic bot settings  
**Use When**: First time setup or changing core bot configuration  
**Features**:
- Set hosting type (Self-Hosted or Nitrado)
- Configure Discord channels (chat, status, shop, log)
- Set admin role (for bot management)
- Set user role (for access control)
- Configure shop settings
- Set voice channel category

**Roles**:
- **Admin Role**: Can manage bot settings, execute RCON commands, manage servers
- **User Role**: Required to use bot features (shop, kits, linking). If not set, all users can access.

---

### `/servermgmt` - Server Management
**Purpose**: Add, edit, remove, and manage ARK server configurations  
**Use When**: Managing your cluster of ARK servers  
**Features**:
- **Add Server**: Add new ARK server to the bot
- **Manage Servers**: List all servers with edit/remove options
- **Edit Server**: Update server IP, ports, RCON password
- **Remove Server**: Disable server (soft delete)
- View server status and details

**Note**: Each Discord server = one cluster. All ARK servers in a Discord are part of the same cluster.

---

### `/playermgmt` - Player Management
**Purpose**: Manage players, economy, linking, and in-game rewards  
**Use When**: Managing player accounts and giving items/creatures  
**Features**:
- Link/unlink players
- View player economy balances
- **Give Item** (searchable database, auto-detects player's server)
- **Give Creature** (searchable database with level selection)
- Manage player balances
- View player statistics

---

### `/kitsmgmt` - Starter Kits Management
**Purpose**: Create and manage starter kits for players  
**Use When**: Setting up welcome kits or rewards  
**Features**:
- Create new kits
- Edit existing kits
- Set kit cooldowns
- Configure kit requirements
- Enable/disable kits

---

## Quick Command Reference

### Server Status & Info
- `/servers` - View all ARK server status
- `/players` - Show all online players
- `/findplayer <name>` - Find which server a player is on
- `/listservers` - List configured servers with connection details
- `/serverinfo <server>` - Detailed server information panel

### Server Control (Self-Hosted Only)
- `/serverstatus` - Check NSSM service status
- `/serverstart <server>` - Start server service
- `/serverstop <server>` - Stop server service
- `/serverrestart <server>` - Restart server service
- `/serverupdate <server>` - Update via SteamCMD
- `/serverlogs <server>` - View recent logs

### RCON Admin Commands
- `/listplayers <server>` - List online players
- `/kickplayer <server> <name>` - Kick player
- `/banplayer <server> <name>` - Ban player
- `/unbanplayer <server> <id>` - Unban player
- `/whitelistplayer <server> <id>` - Add to whitelist
- `/broadcast <server> <message>` - Broadcast message
- `/saveworld <server>` - Force save
- `/destroywilddinos <server>` - Wipe wild dinos
- `/setmotd <server> <message>` - Set MOTD
- `/giveexptoplayer <server> <player> <amount>` - Give XP
- `/setplayerpos <server> <player> <x> <y> <z>` - Teleport
- `/rcon <server> <command>` - Execute custom RCON command

### Player Commands
- `/linkplayer <server>` - Link your Discord to in-game character
- `/kit <kit_name> <server>` - Claim starter kit
- `/listkits` - View available kits

### Help & Info
- `/help` - Interactive help menu
- `/commands` - Quick command list
- `/about` - About the bot
- `/info` - Quick bot info

---

## Design Philosophy

### Cluster = Discord Server
The bot treats each Discord server as a separate ARK cluster. This means:
- One Discord server = One cluster of ARK servers
- Players are scoped to each Discord server
- Shop/economy is per-Discord-server
- To manage multiple clusters, create separate Discord servers

### Shop Category Limit
Discord dropdown menus support a maximum of **25 options**. The `/shop` category selector will only display the first 25 categories. Keep your item category names consolidated — avoid splitting what could be one category into multiple (e.g., use `Armor` rather than `Light Armor` + `Heavy Armor` + `TEK Armor`). If you exceed 25 categories, the extras will silently not appear in the shop.

### GUI-First Approach
Complex management tasks use GUI interfaces (`/setupcfg`, `/servermgmt`, `/playermgmt`, `/kitsmgmt`) for better UX and fewer errors.

### Player-Centric Actions
Actions that target players (give item, give creature) are in `/playermgmt` and auto-detect which server the player is on, eliminating the need to manually select servers.

### Server-Centric Actions
Actions that target servers (broadcast, dino wipe, save world) remain server-specific and require server selection.

---

## Migration Notes

### Old Command Names → New Command Names
- `/playercfg` → `/playermgmt` (Player Management)
- `/kitscfg` → `/kitsmgmt` (Kits Management)
- Added: `/servermgmt` (Server Management)
- Unchanged: `/setupcfg` (Initial Setup)

### Why the Change?
The new naming scheme makes it clearer what each command does:
- `cfg` = configuration (setup)
- `mgmt` = management (ongoing operations)

This helps users understand at a glance whether they're doing initial setup or managing existing resources.
