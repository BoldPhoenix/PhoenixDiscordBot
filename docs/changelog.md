# Phoenix ARK Bot - Changelog

## Mar 3, 2026

### Remote Agent v3.2.1 + Bot Wiring Complete
- **`maintain_server` agent command** — atomic stop→SteamCMD→start on agent side; agent continues autonomously if bot disconnects; persistent job log written to `jobs/` dir next to exe
- **Bot now calls `maintain_server`** — `_run_update_sequence` in `server_management.py` replaced 3 separate agent calls (stop_server + update_server + start_server) with single `maintain_server` call (timeout=3600s); progress streams to Discord as `📋 X% — [1/3]...`
- **`runSteamCMDUpdate` filepath bug fixed** — `filepath.Dir()` was called on a directory path, sending SteamCMD to wrong folder (`C:\` instead of `C:\SteamCMD`); now detects directory vs file and uses path directly (v3.2.0)
- **ARK version broadcast timing fixed** — agent now polls ShooterGame.log every 15s for up to 8 min after service RUNNING, comparing against pre-update version; broadcasts once version changes instead of reading once after 5s (when ARK hasn't loaded yet) (v3.2.1)
- **Windows exe metadata** — version info embedded in exe Details tab via `goversioninfo`; `versioninfo.json` auto-synced from `AgentVersion` in main.go by `sync_version.ps1`; `build.bat` orchestrates full pipeline
- **`_retry_voice_update` AttributeError fixed** — `server_monitor.py` still referenced removed `server_status_cache` attribute; now uses `guild_server_caches[guild_id][server_name]` and accepts `guild_id` param
- **`/setup` command** — `setup.py` is NOT loaded (legacy); `/setup` command now defined in `setup_gui.py`'s `SetupGUI` class
- **Manage server embed RCON status** — was always "⚪ Unknown"; now reads live status from `ServerMonitor.guild_server_caches` at selection time
- **Update completion message** — `interaction.followup.send()` silently fails after 15 min (Discord token expiry); now posts results to log channel first (reliable), then tries ephemeral followup as best-effort
- **analytics_dashboard cog** — now loading correctly (was missing from cog list)
- **Subscription downgrade handling** — `ManageServersView` shows disabled servers as `⚠️ Name (Disabled)`; `enable_tier_limited_servers()` re-enables only tier-limited rows on upgrade

## Mar 2, 2026

### Tier Gating Fixes and Stability Improvements
- Server monitor loop crash — fixed by restart; root cause unknown (silent crash)
- `/listplayers` crash — fixed `server_status_cache` → `guild_server_caches` (multi-tenant)
- Missing `get_ark_server_by_id()` — added to `server_config_db.py`
- Remote agent crash on version detection — added panic recovery (`defer recover()`) to Go agent
- Tier gating for shop — added `check_feature("shop")` to `/shop`, `/buy`, `/cart` commands
- Tier gating for player management — added `check_feature("player_management")` to `/player`, `/playermgmt`, `/listlinkedplayers`
- Fixed duplicate "maintenance" entry in `FEATURE_TIERS` (was both "free" and "premium")
- Updated `/about` command — global stats (bot-wide), local stats (per-guild), tier-based feature list
- Added `get_linked_player_count()` to `players_db.py`

## Mar 1, 2026

### Phase 16 Freemium Strategy
- Free tier (1 agent, 2 servers), Premium/Lifetime (unlimited)
- Auth key binding to prevent exploitation
- Server/agent limits enforced at registration with upgrade prompts
- Mod/INI/server management enabled for free tier
- Agent control panel auto-refresh
- Mod removal auto-refresh
- INI editing auto-refresh (dynamic and queued)
- Fixed agent count data mixing bug
- Removed duplicate /setupcfg command
- Server limit enforcement at button level

## Feb 27, 2026

### Phase 10 Enterprise Overhaul
- `/maintenance` command (renamed from `/maintcfg`)
- Multiple backup schedules
- All-Server backup
- verify_backup Go agent command
- RestoreConfirmView defer+followup fix
- SteamCMD string removed from progress messages
- Manual backup completion logged to log channel
- 96 new tests, 0 regressions. Deployed + commands synced. (1,357 tests passing)

## Feb 26, 2026

### Voice Channel & Game Fixes
- Voice channel version display — fixed to show "(v83.2)" format with space, version now pulled directly from server_config (not re-queried)
- Voice channel update logic — now checks every 30 seconds but only updates voice channel when data changes (status, player count, or version)
- Voice channel first-run update — now updates on first bot loop run after restart when version differs from cache
- Remote agent version handler — triggers immediate voice channel update when ARK version changes in database
- Survivor Cards — fixed embed layout: wager and balance now appear below hands (inline=False)
- Fossil Excavation — fixed grid calculation (was 5x4, now 4x4) causing interaction failures
- Card images — synced heart, diamond, club suits to Pi 5
- Sync direction rule — added to opencode.json: "ONLY sync FROM pi-staging TO pi 5, NEVER the other direction unless explicitly specified"
- Explorer Trivia — removed from games (deferred improvements to future phase)

## Feb 20, 2026 (Evening)

### Economy & Channel Configuration
- `economy.py` — added payday eligibility role, schedule configuration (daily/weekly, time, active-only)
- `economy.py` — moved economy log channel to server_configs, uses economy_channel_id instead of economy_settings.economy_log_channel_id
- `setup_gui.py` — expanded channel configuration to 9 channels with role/channel selectors
- `setup_gui.py` + all GUI cogs — removed all Close/Done/Back buttons from ephemeral views
- `init_db.py` — added migrations for economy_settings (eligibility_role, schedule_type, day_of_week, time, active_only)
- `server_config_db.py` — added migrations for new channel columns (server_channel_id, mod_channel_id, economy_channel_id, events_channel_id)

## Feb 20, 2026

### Economy GUI & Player Sessions
- `shop.py` — fixed "Buy Phoenix Coins (Quick)" button searching for "phoenix coins" (plural) when inventory item is "Phoenix Coin" (singular)
- `players_db.py` + `server_monitor.py` — added player session tracking (join/leave detection, end all on server offline)
- `players_db.py` — added session backfill on player link
- `chat_relay.py` — added admin command filtering to admin_log_channel_id
- `players_db.py` — fixed `link_player` to require `guild_id`, updated all callers
- `players_db.py` — added `get_top_balances()` and `get_all_balances()` for leaderboard/reports
- `economy.py` — added `/economycfg` GUI panel with Settings, Role Bonuses, Leaderboard, Payday, Balance Report buttons
- `economy.py` — added `/leaderboard` command

## Feb 17, 2026

### Economy Migration to Players Table
- `economy.py` — **migrated from `user_db` to `players_db`** (EOS ID-based balance on `players.balance`, removed `on_message` listener, all commands require linked account, all responses ephemeral)
- `players_db.py` — added economy functions: `get_balance`, `get_balance_by_discord_id`, `add_coins` (returns new balance), `deduct_coins` (race-safe `WHERE balance >= ?`), `get_coin_history`
- `init_db.py` — added `eos_id` column to `coin_transactions`, made `discord_id` nullable, added migrations for `eos_id` on `coin_transactions` and `balance` on `players`
- `player_management.py` — switched `AddCoinsModal`/`RemoveCoinsModal` from `user_db` to `players_db`, `/player` balance reads from `players.balance`, all coin operations require linked account
- `user_db.py` — deprecated economy functions (`get_balance`, `add_coins`, `deduct_coins`, `get_coin_history`) with docstring notices
- Fixed old economy doubling bug: `create_or_update_user` was granting `SHOP_STARTING_BALANCE` (1000) before `add_coins`, causing 2x credits

### Chat History & Player Management
- `chat_history_db.py` — rewrote for multi-tenant with `guild_id` on all functions
- `init_db.py` — added missing `chat_history` table creation
- `player_management.py` — merged admin GUI from `player_management_gui.py`, added Discord UserSelect dropdowns for link/unlink/coins
- Removed stale `player_management_gui.py` cog (had duplicate `/playermgmt` command)

### Infrastructure Cleanup
- Installed missing `aiofiles` package on Pi 5
- Removed stale 0-byte `/opt/phoenix-bot/bot.db` file
- Reconciled file drift between pi-staging, bot/cogs, and Pi 5 (bot/cogs is canonical)
- Cleaned junk files from Pi 5 cogs dir (main.py, server_config_db.py, ark_parser.py, .backup, .b64 files)

### Remote Agent Fixes
- `remote_agent_gui.py` — fixed `send_command` calls (was expecting tuples, now handles dict/exceptions)
- `rcon_admin.py` — fixed broken refs: removed `Config.ARK_SERVERS` (doesn't exist), removed `Config.ADMIN_ROLE_ID` (doesn't exist), fixed `self.logger` → `logger`, fixed `players_db.get_player_by_discord_id` missing `guild_id` arg, fixed undefined `server_monitor`/`found_server_name` in `give_item`, added `give_item_alias` to autocomplete registration
- `main.py` — added `self.agent_manager = None` to `ArkBot.__init__`, added `agent_manager.close_all()` on shutdown
- `remote_agent.py` — fixed key name mismatch in `load_agents_from_db` (`agent_ip`/`agent_port` vs `ip`/`port`)
- `remote_agent.py` — added proactive server config push on reconnect (fixes agent having empty `ark_servers` and no version detection)

### Go Agent Handlers
- All 9 implemented with real operations (get_status, view_logs, discover_servers, start_server, stop_server, restart_server, update_server, backup_server, install_mod)
- Python agent recv loop, request-response correlation, shared agent_manager, auto-reconnect

## Feb 11, 2026

### Remote Agent Infrastructure
- WebSocket response listener — asyncio task running `websocket.recv()` loop, parse responses, dispatch to pending futures by `request_id`
- Request-response correlation — `send_command()` returns an awaitable future that resolves when agent responds with matching `request_id`
- Shared agent_manager on bot object — set `bot.agent_manager` in main.py so all cogs share one connection pool
- Auto-reconnect — background task that detects dropped WebSocket and re-establishes connection
- Server management GUI (dropdown + button panels using real agent data)
