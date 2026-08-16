# Phoenix ARK Discord Bot

![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![discord.py](https://img.shields.io/badge/discord.py-2.3.2%2B-5865F2)
![SQLite](https://img.shields.io/badge/database-SQLite-003B57)
![Platform](https://img.shields.io/badge/runs%20on-Linux%20%7C%20Windows%20%7C%20Raspberry%20Pi-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-1192%20passing-brightgreen)

> **Why this exists.** I ran an ARK: Survival Ascended cluster and went looking for a Discord bot
> that could actually administer it — RCON, chat relay, an economy, mod management, starting and
> stopping servers — and could not find one. So I built it, ran it for months against a live
> community, and have now open-sourced it because the cluster is shutting down and the code
> shouldn't die with it. If you are where I was, this is the thing I was looking for.
>
> **Take it apart.** MIT licensed. Deploy it whole, or lift just the Source RCON client, the
> binary ARK save-file parser, or the Go remote-agent service and use those. If you are pointing
> an AI assistant at this repository, start it on [`AGENTS.md`](AGENTS.md).

A multi-tenant Python Discord bot for ARK: Survival Ascended server management. Supports unlimited Discord guilds, direct RCON, a Go-based remote Windows agent, real-time server monitoring, a full economy and shop system, INI file editing, mod management, an in-Discord GUI console for server operations, and a gaming/arcade system with 10 ARK-themed mini-games (all playable).

---

## Key Features

- **Multi-tenant** — one bot instance serves unlimited Discord guilds; every database query is isolated by `guild_id`
- **Setup GUI wizard** — `/setup` walks through all configuration with modal forms and button menus, no config files required
- **Real-time server monitoring** — dynamic voice channels show live player counts and ARK version, updated every 60 seconds
- **Bidirectional chat relay** — in-game chat bridges to Discord and Discord messages post in-game, with full history logging
- **Economy system** — Phoenix Coins, balance stored on linked ARK accounts (`players.balance`); all commands require a linked EOS account
- **Shop system** — `/shop browse`, `/cart`, `/shopadmin` with pending-delivery queue processed every 5 minutes
- **RCON admin console** — broadcast, save world, destroy wild dinos, kick, ban, give items, custom RCON commands
- **Server management GUI** — `/servermgmt` hierarchical button panel: Server Ops, Server Control, Advanced, Diagnostics, Updates
- **INI file editing** — `/inimgmt` for editing GameUserSettings.ini and Game.ini with dynamic/restart-required classification
- **Mod management** — `/modmgmt` to add/remove mods, `/modsearch` full-text search across 5,765 cached mods, `/modinfo` for details
- **Remote agent (PhoenixArkAgent.exe)** — Go Windows service for server start/stop/restart/update (SteamCMD)/backup/log viewing
- **Gaming system** — `/games` hub with 10 ARK-themed mini-games: Dodo Roulette, Mutation Slots, Overseer Code Breaker, Drop Scramble, Taming Risk, Alpha Hunt, Cryo Gamble, Explorer Trivia, Artifact Vault, Crafting Race
- **Log viewer** — `/serverlogs` with pagination, `/searchlogs`, `/logstats` (up to 1000 lines, paginated)
- **Player management** — `/player` self-service, `/playermgmt` admin panel, `/listlinkedplayers`, EOS account linking
- **18 cogs loaded** — comprehensive feature coverage
- **22 database tables** — full multi-tenant data isolation
- **1192 passing tests** — comprehensive test coverage
- **All success responses ephemeral** — admin responses never clutter channels

---

## Architecture

```
Discord (Multi-Guild)
        |
        v
  Pi 5 Bot (Python 3.12+)
  /opt/phoenix-bot/
        |
        +------ Direct RCON (TCP) ---------> ARK Server RCON Port
        |
        +------ WebSocket (port 8080) -----> ARKAgent.exe (Windows)
                                                     |
                                              SteamCMD / ARK Server
```

### Connection Models

| Model | When Used |
|-------|-----------|
| Direct RCON | Bot contacts ARK server RCON port directly (TCP) |
| Remote Agent | Bot -> ARKAgent.exe via WebSocket -> ARK server (start/stop/update) |
| Nitrado API | Future: Bot -> Nitrado REST API |

### Project Layout

```
PhoenixArkDiscordBot/
  main.py                        # Bot entry point, loads all cogs
  sync_commands.py               # Slash command sync utility
  requirements.txt
  bot/
    cogs/                        # Discord command modules (18 cogs)
      setup.py                   # Text-based config commands
      setup_gui.py               # GUI wizard (/setup, add server modal)
      server_monitor.py          # RCON polling + voice channel updates
      chat_relay.py              # ARK <-> Discord chat bridge
      server_management.py       # /servermgmt hierarchical GUI console
      rcon_admin.py              # RCON admin slash commands
      log_viewer.py              # Log fetch + pagination
      player_management.py       # Player linking + admin panel
      economy.py                 # /balance, /history, payday
      shop.py                    # /shop, /cart, /shopadmin
      games.py                   # /games gaming hub
      bot_control.py             # Bot management (/ping, reload)
      help_commands.py           # /help system
      remote_agent.py            # WebSocket agent manager + commands
      remote_agent_gui.py        # Agent Discord GUI
      mod_management.py          # Mod management UI (/modmgmt, /modsearch)
      ini_management.py          # INI editing UI (/inimgmt)
      ask_phoenix.py             # AI Q&A assistant (/askphoenix)
    games/                       # Mini-games (10 games)
      base.py                    # BaseGameView, GameIntroView, GameOutcome
      dodo_roulette.py           # Color betting game
      overseer_code.py           # Mastermind code puzzle
      drop_scramble.py           # Reaction timing game
      taming_risk.py             # Risk/reward choice
      artifact_vault.py          # Lore hint puzzle
      crafting_race.py           # Ingredient matching
      mutation_slot.py           # Slot machine
      alpha_hunt.py              # Combat simulation
      explorer_trivia.py         # ARK trivia
      cryo_gamble.py             # Mystery box
    database/                    # SQLite via aiosqlite (guild_id isolation)
      init_db.py                 # Initializes all tables on startup
      server_config_db.py        # Guild config + ark_servers CRUD
      players_db.py              # Players, sessions, economy functions
      economy_db.py              # Economy settings, roles, payday history
      shop_db.py                 # Store items, cart, transactions, deliveries
      chat_history_db.py         # Chat message storage
      remote_agent_db.py         # Remote agent registration
      curseforge_db.py           # CurseForge mod cache operations
    rcon/
      client.py                  # Async RCON client
    utils/
      config.py                  # Config class (env vars + defaults)
      log_parser.py              # ARK log parsing utilities
      system_monitor.py          # System-level server monitoring
  remote_agent/                  # Go source for ARKAgent.exe
  tests/                         # Full pytest test suite
  pi-staging/                    # Mirror of Pi 5 deployed code
  docs/                          # Implementation plan and notes
```

---

## What ships, and what does not

**Ships:** the bot and all its features, plus the ARK reference data that is tedious to rebuild —
the 1,593-item shop catalogue (`data/seed/store_items.json`), the dino reference list
(`ark_dinos.csv`), XP tables and version data. All of it is public game data.

**Does not ship:** any database, and any account. There are no players, no linked Discord users,
no balances, no transaction history, no server credentials. The bot creates an empty database on
first run and you seed the catalogue yourself (see QUICKSTART step 3b), so the first account in
your instance is yours.

This repository was published from a private working repo with its history intentionally left
behind, since that history contained development credentials and operator-specific configuration.
Nothing here carries prior state.

## Requirements

- Python 3.12+
- pip packages: `discord.py>=2.3.2`, `aiosqlite`, `python-dotenv`, `websockets`
- SQLite (bundled with Python)
- Raspberry Pi 5 (or any Linux host) for production
- ARKAgent.exe (Go binary) on Windows machine hosting ARK servers (optional, for remote control)

---

## Installation (Raspberry Pi 5)

```bash
# Clone the repository
git clone https://github.com/BoldPhoenix/PhoenixArkDiscordBot.git
cd PhoenixArkDiscordBot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp sample.env .env
nano .env   # add your bot token and guild ID

# Create data directory
mkdir -p data

# Sync slash commands to Discord (do this once, or after adding commands)
python sync_commands.py

# Start the bot
python main.py
```

### Environment Variables (`.env`)

```env
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=your_primary_guild_id
DATABASE_PATH=data/phoenix_bot.db
```

### systemd Service (`/etc/systemd/system/phoenix-bot.service`)

```ini
[Unit]
Description=Phoenix ARK Discord Bot
After=network.target

[Service]
Type=simple
User=phoenix-bot
WorkingDirectory=/opt/phoenix-bot
ExecStart=/opt/phoenix-bot/venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/phoenix-bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable phoenix-bot
sudo systemctl start phoenix-bot
sudo journalctl -u phoenix-bot -f
```

---

## First-Time Setup in Discord

After inviting the bot to your Discord server, run `/setup` to launch the configuration wizard.

### Step 0 — Configure Bot Permissions (IMPORTANT!)

**Before running `/setup`, ensure the bot has the correct Discord permissions:**

1. **Go to Server Settings → Roles**
2. **Find your bot's role** (e.g., "Phoenix ARK Bot")
3. **Enable these permissions:**
   - ✅ **Manage Channels** — Required to create/update voice channels
   - ✅ **Manage Roles** — Required for economy role bonuses
   - ✅ **Send Messages** — Required for all bot responses
   - ✅ **Embed Links** — Required for rich embeds
   - ✅ **Read Message History** — Required for chat relay
   - ✅ **Use Slash Commands** — Required for all commands
   - ✅ **Connect** (Voice) — Required for voice channel status
   - ✅ **View Channels** — Required to see all channels

4. **For the "Server Status" category specifically:**
   - Right-click the category → **Edit Category**
   - Go to **Permissions** tab
   - Add your bot role
   - Enable **Manage Channels** and **View Channel**

**Without these permissions, voice channels will fail to create with "403 Forbidden: Missing Permissions"**

### Step 1 — Run `/setup`

The setup wizard presents a button menu. Walk through each section:

1. **Server Configuration** — set the bot admin role and optional log channel
2. **Add ARK Server** — modal prompts for:
   - Server name (display name)
   - Host IP or hostname
   - RCON port and password
   - Max players
   - Map name (optional)
   - Service name (optional, for remote agent control)
   - Server/SteamCMD/log paths (optional, for remote agent)
3. **Channel Configuration** — set the voice channel category for status channels
4. **Economy/Shop** — configure Phoenix Coins starting balance, payday settings, shop channel

### Step 2 — Add ARK Servers

Use `/addserver` or the wizard to add each ARK server. The bot will:
- Validate RCON connectivity
- Create a dynamic voice channel in the configured category (requires **Manage Channels** permission)
- Begin polling the server every 30 seconds
- Auto-recreate voice channels if deleted

### Step 3 — Link ARK Accounts (Players)

Players must link their EOS (Epic Online Services) account to their Discord account before using economy or shop commands. Use `/player link <EOS_ID>` or the admin panel `/playermgmt`.

### Step 4 — Register Remote Agent (Optional)

If you run ARKAgent.exe on your Windows server machine:

```
/register_agent ip:<agent_ip> port:8080 auth_key:<your_key>
```

The bot will connect via WebSocket and maintain the connection with automatic reconnect.

---

## Commands Reference

### Setup and Configuration

| Command | Description |
|---------|-------------|
| `/setup` | Launch the full GUI setup wizard |
| `/addserver` | Add an ARK server (RCON connection required) |
| `/removeserver` | Remove an ARK server |
| `/listservers` | Show all configured ARK servers |
| `/config` | View current guild configuration |

### Server Management Console

| Command | Description |
|---------|-------------|
| `/servermgmt` | Open the hierarchical server management GUI |

The `/servermgmt` console has four panels per server:

- **Server Ops** — Broadcast message, Save World, Destroy Wild Dinos, Set MOTD
- **Server Control** — Start, Stop, Restart, Status (via remote agent)
- **Advanced** — Custom RCON command, Chat Log
- **Diagnostics** — View Log (with line count modal + pagination), View Errors, Crash History
- **Updates** — Multi-server SteamCMD update with optional validation mode and countdown

### RCON Admin

| Command | Description |
|---------|-------------|
| `/broadcast <message>` | Broadcast message to all players on a server |
| `/saveworld` | Force save the world |
| `/destroywilddinos` | Destroy all wild dinosaurs |
| `/rcon <command>` | Execute a raw RCON command |
| `/kickplayer <player>` | Kick a player by name |
| `/banplayer <player>` | Ban a player |
| `/unbanplayer <player>` | Unban a player |
| `/listplayers` | List online players |
| `/getchat` | Fetch recent in-game chat |
| `/setmotd <message>` | Set the message of the day |
| `/give <player> <item> <qty>` | Give items to a player |

### Economy

| Command | Description |
|---------|-------------|
| `/balance` | Check your Phoenix Coin balance (requires linked account) |
| `/history` | View your coin transaction history |
| `/addcoins <player> <amount>` | Admin: add coins to a player |
| `/removecoins <player> <amount>` | Admin: remove coins from a player |

### Shop

| Command | Description |
|---------|-------------|
| `/shop` | Browse the item shop (paginated by category) |
| `/cart` | View and manage your cart |
| `/shopadmin` | Admin panel: add/edit/remove items, view orders |

### Player Management

| Command | Description |
|---------|-------------|
| `/player` | Self-service player panel (link account, view stats) |
| `/playermgmt` | Admin panel: manage player accounts and linking |
| `/listlinkedplayers` | List all players with linked Discord accounts |

### Remote Agent

| Command | Description |
|---------|-------------|
| `/register_agent` | Register a new ARKAgent.exe instance |
| `/agent_status` | Show connection status and last heartbeat |
| `/remove_agent` | Remove registered agent |
| `/agent_control` | GUI panel for agent operations |

### Logs

| Command | Description |
|---------|-------------|
| `/serverlogs` | View server logs with configurable line count and pagination |
| `/searchlogs` | Search logs for a keyword or pattern |
| `/logstats` | Show log statistics (errors, warnings, crash events) |

### Mod Management

| Command | Description |
|---------|-------------|
| `/modmgmt` | Open mod management panel (view, add, remove mods) |
| `/modsearch <query>` | Search cached CurseForge mods by name, ID, author, or description |
| `/modinfo <mod_id>` | Get detailed info about a specific mod |
| `/setmodchannel <channel>` | Set channel for auto-updating mod list embed |
| `/refreshmods` | Manually refresh mod list and send to channel |

The mod management system includes:
- **5,765 ARK: Survival Ascended mods** cached from CurseForge
- **Full-text search** across mod name, author, ID, and description
- **Paginated results** with sorting by name, downloads, date, author, or ID
- **Auto-updating embed** showing all installed mods across servers
- **On-demand mod info** fetched from CurseForge API when adding mods

### INI Management

| Command | Description |
|---------|-------------|
| `/inimgmt` | Open INI management panel (edit Game.ini and GameUserSettings.ini) |

The INI management system includes:
- **Section-based browsing** — Filter by INI section, paginated 8 per page
- **Search** — Find settings by key name or value
- **Dynamic vs Restart-Required** — 🟢 Dynamic settings apply immediately, 🔴 restart-required queue for next stop
- **Line-based editing** — Safe edits that preserve complex multi-line sections
- **Pending changes queue** — Restart-required settings stored and applied on next server stop
- **Auto-backup** — Agent creates .bak file before every write
- **Full logging** — All changes logged to server log channel with details

### Bot

| Command | Description |
|---------|-------------|
| `/ping` | Check bot latency |
| `/help` | Show all command categories and descriptions |

---

## Remote Agent (PhoenixArkAgent.exe)

The remote agent is a Go-based Windows service that runs on the machine hosting your ARK servers. It provides server lifecycle management (start/stop/restart), SteamCMD updates, INI editing, and mod management that direct RCON cannot perform.

### Communication Protocol

| Property | Value |
|----------|-------|
| Transport | WebSocket (`ws://agent_ip:8080/ws`) |
| Auth | Query parameter: `?auth_key=<key>` |
| Format | JSON with `request_id` correlation |
| Ping interval | 30 seconds |
| Read deadline | 120 seconds |
| Reconnect | Exponential backoff (5s to 5 min) |

### Supported Commands

| Command | Description |
|---------|-------------|
| `start_server` | Start ARK server via Windows service or script |
| `stop_server` | Stop ARK server gracefully |
| `restart_server` | Stop then start ARK server |
| `get_status` | Get current server running state |
| `discover_servers` | Auto-discover ARK installations |
| `update_server` | Run SteamCMD update for specified app ID |
| `backup_server` | Create backup of server data |
| `view_logs` | Fetch recent log lines |
| `install_mod` | Install or update a Steam Workshop mod |
| `get_mods` | Get installed mod IDs from Windows Registry |
| `set_mods` | Set installed mod IDs in Windows Registry |
| `read_ini` | Read INI file content |
| `update_ini_setting` | Update single setting via line-based edit |

### Build and Install

```bash
# Build the agent (requires Go toolchain)
cd remote_agent
go build -o PhoenixArkAgent.exe

# Install as Windows service
PhoenixArkAgent.exe -install
net start PhoenixArkAgent

# Or run directly
PhoenixArkAgent.exe
```

Agent configuration (auth key, port, steamcmd paths) is set via the agent's own config file on the Windows machine.

---

## Configuration

### Channels

| Channel | Purpose | Required |
|---------|---------|----------|
| Voice category | Dynamic voice channels for server status | Yes, for monitoring |
| Chat channel | In-game chat relay (cross-server) | No |
| Status channel | Health status embeds | No |
| Shop channel | Purchase logs | No |
| Admin Log channel | Admin RCON command audit log | No |
| Server channel | Server updates/reboots | No |
| Mod channel | Installed mods list | No |
| Economy channel | Payday logs | No |
| Events channel | Event info/transactions | No |

### Economy Settings

Set via `/economycfg` GUI panel:

| Setting | Default | Description |
|---------|---------|-------------|
| `base_payday_amount` | 100 | Base coins per payday |
| `currency_name` | Phoenix Coins | Display name |
| `currency_icon` | 🪙 | Display emoji |
| `payday_enabled` | Yes | Enable/disable payday system |
| `payday_eligibility_role_id` | None | Role required to receive payday (None = all players) |
| `payday_schedule_type` | daily | Schedule type: "daily" or "weekly" |
| `payday_time` | 12:00 | Time of day (HH:MM, 24-hour) |
| `payday_day_of_week` | 0 | Day of week for weekly payday (0=Sunday) |
| `payday_active_only` | No | Only pay players active in last 7 days |

Role bonus multipliers can be configured per Discord role via the `/economycfg` GUI panel.

### ARK Server Fields

When adding a server, these fields are available:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Internal server name (used in commands) |
| `display_name` | No | Pretty name shown in Discord |
| `host` | Yes | Server IP or hostname |
| `rcon_port` | Yes | RCON port number |
| `rcon_password` | Yes | RCON password |
| `max_players` | No (default 70) | Maximum player slots |
| `map_name` | No | ARK map (e.g. `Aberration_WP`) |
| `query_port` | No | Steam query port |
| `server_path` | No | Windows path to ARK install (for agent) |
| `steamcmd_path` | No | Windows path to SteamCMD dir (for agent) |
| `log_path` | No | Windows path to ShooterGame.log (for agent) |
| `service_name` | No | Windows service name (for agent start/stop) |

---

## Database

### Location

| Environment | Path |
|-------------|------|
| Local testing | `data/phoenix_bot.db` (or `DATABASE_PATH` env var) |
| Production (Pi 5) | `/opt/phoenix-bot/data/phoenix_bot.db` |

### Tables (22)

| Table | Purpose |
|-------|---------|
| `guilds` | Registered Discord guilds |
| `server_configs` | Per-guild configuration (channels, roles) |
| `ark_servers` | ARK servers per guild (28+ columns) |
| `voice_channel_mappings` | RCON port → Discord voice channel ID |
| `remote_agents` | Registered PhoenixArkAgent.exe instances |
| `players` | Player records with EOS ID linking and balance |
| `player_sessions` | Login/logout session tracking |
| `users` | Legacy economy table (deprecated for balance) |
| `store_items` | Shop items per guild |
| `transactions` | Purchase transaction log |
| `coin_transactions` | Coin credit/debit ledger (EOS-based) |
| `pending_deliveries` | Items awaiting in-game delivery |
| `cart_items` | Active shopping cart entries |
| `chat_history` | In-game chat message archive |
| `economy_settings` | Per-guild economy configuration |
| `economy_roles` | Role-based payday bonus multipliers |
| `payday_history` | Payday claim records per player |
| `shop_config` | Per-guild shop configuration |
| `curseforge_mods` | CurseForge mod metadata cache (5,765 mods) |
| `server_ini_settings` | Parsed INI settings per server |
| `ini_pending_changes` | Queued INI changes awaiting server stop |
| `admin_logs` | Admin action audit log |

All tables created automatically by `init_db.initialize_database()` on startup. Schema is idempotent (`CREATE TABLE IF NOT EXISTS`).

### Backup

```bash
# On Pi 5
sqlite3 /opt/phoenix-bot/data/phoenix_bot.db ".backup /opt/phoenix-bot/data/backup_$(date +%Y%m%d).db"

# Copy backup off Pi
scp your-pi-host:/opt/phoenix-bot/data/backup_*.db ./backups/
```

---

## Deployment to Pi 5

```bash
# 1. Make changes in bot/ directory locally
# 2. Copy files to Pi staging area (SCP)
"C:\Windows\System32\OpenSSH\scp.exe" -r bot/* your-pi-host:/tmp/bot/
"C:\Windows\System32\OpenSSH\scp.exe" main.py your-pi-host:/tmp/

# 3. SSH to Pi (use Windows native SSH, not Git Bash)
"C:\Windows\System32\OpenSSH\ssh.exe" your-pi-host

# 4. On Pi: copy files, fix ownership, restart
sudo cp -r /tmp/bot/* /opt/phoenix-bot/bot/
sudo cp /tmp/main.py /opt/phoenix-bot/
sudo chown -R phoenix-bot:phoenix-bot /opt/phoenix-bot/
find /opt/phoenix-bot -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
sudo systemctl restart phoenix-bot.service

# 5. Verify
sudo journalctl -u phoenix-bot -f
```

### Sync Slash Commands (after adding new commands)

```bash
# On Pi 5
cd /opt/phoenix-bot
source venv/bin/activate
python sync_commands.py
```

---

## Security

- **All success/confirmation messages are ephemeral** — they are only visible to the invoking user
- **RCON passwords stored in database**, never in source code or environment variables
- **Per-guild data isolation** — every DB query includes `guild_id`; one guild cannot access another's data
- **Admin role checks** on all admin commands; `/playermgmt`, `/shopadmin`, `/servermgmt` require configured admin role or Discord Administrator
- **Remote agent `auth_key` stored in database** and transmitted via WSS query parameter (not exposed in responses)
- **Economy requires linked ARK account** — Discord users cannot earn or spend coins without linking an EOS ID
- **Never expose RCON port to the internet** — RCON should be bound to localhost or a private IP only

### Port Exposure Reference

| Port | Traffic | Exposure |
|------|---------|----------|
| Game port (e.g. 7777) | UDP | Public |
| Query port (e.g. 27015) | UDP | Public |
| RCON port | TCP | **localhost/VPN only** |
| Agent port (8080) | TCP WebSocket | **localhost/VPN only** |

---

## Development

### Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific file
pytest tests/test_database_server_config.py -v

# With coverage report
python -m pytest tests/ --cov=bot --cov-report=html
```

The test suite uses in-memory (temp file) SQLite databases — no external services required. See `tests/test-suite-documentation.md` for full test suite documentation.

### Sync Slash Commands Locally

```bash
python sync_commands.py
```

This syncs guild-scoped commands first, then clears any stale global commands.

### Adding a New Cog

1. Create `bot/cogs/your_cog.py`
2. Write tests in `tests/test_your_cog.py`
3. Add to `main.py` initial extensions list
4. Add to `sync_commands.py` if it contains slash commands
5. Run `python sync_commands.py` after deploy

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write tests first (test-first development)
4. Implement the feature
5. Run the full test suite (`python -m pytest tests/ -v`) — all tests must pass
6. Submit a pull request

---

## License

MIT License — see `LICENSE` file for details.

---

**Built for the ARK: Survival Ascended community.**
GitHub: [https://github.com/BoldPhoenix/PhoenixArkDiscordBot](https://github.com/BoldPhoenix/PhoenixArkDiscordBot)
