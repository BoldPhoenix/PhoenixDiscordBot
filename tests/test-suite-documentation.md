# Phoenix ARK Bot — Test Suite Documentation

## Overview

The Phoenix ARK Discord Bot test suite provides comprehensive coverage of all database operations, utility functions, cog business logic, and Discord UI components.

| Metric | Value |
|--------|-------|
| Test files | 31 |
| Total test functions | 921 |
| Test framework | pytest + pytest-asyncio |
| Database strategy | In-memory SQLite (temp file per test) |
| Mock philosophy | Minimal mocks; prefer real objects (see Conventions) |
| External dependencies required | None (all tests run offline) |

### How to Run

```bash
# Full suite
python -m pytest tests/ -v

# Single file
python -m pytest tests/test_database_server_config.py -v

# With coverage
python -m pytest tests/ --cov=bot --cov-report=html

# Debug output
python -m pytest tests/test_server_management.py -v -s

# Stop on first failure
python -m pytest tests/ -x -v
```

All tests must pass before deploying to Pi 5. This is a hard requirement.

---

## Test Conventions

### In-Memory SQLite via Config.DATABASE_PATH

Tests never use the real `data/phoenix_bot.db`. Instead `conftest.py` redirects `Config.DATABASE_PATH` to a `tmp_path` temp file for each test:

```python
@pytest.fixture
def config_db_path(tmp_db_path):
    from bot.utils.config import Config
    original_path = Config.DATABASE_PATH
    Config.DATABASE_PATH = tmp_db_path
    yield tmp_db_path
    Config.DATABASE_PATH = original_path
```

Every database test fixture depends on `config_db_path`. This ensures complete isolation between test runs with no leftover state.

### Async Tests

All async tests use `@pytest.mark.asyncio`. The session-scoped event loop is defined in `conftest.py`:

```python
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

### No-Mocks Philosophy

The project follows a "no mocks" methodology wherever possible. Tests use:
- Real `aiosqlite` database connections
- Real `discord.py` View/Modal/Embed objects
- `types.SimpleNamespace` as a lightweight bot stand-in (not `MagicMock`)
- Real `RemoteAgentManager` instances with real error paths (connection to port 99999 genuinely fails)

Mocks are used only when unavoidable (e.g. `MagicMock` for a `parent_view` argument in a Discord modal that requires one).

### Fixtures Hierarchy (`conftest.py`)

| Fixture | What it creates |
|---------|----------------|
| `tmp_db_path` | Path string for a temp SQLite file |
| `config_db_path` | Redirects `Config.DATABASE_PATH` to temp file |
| `initialized_db` | Runs `initialize_database()` on the temp DB |
| `server_config_db` | Runs `init_server_config_tables()` only |
| `players_db` | Runs `init_players_tables()` only |
| `full_db` | Runs all four init functions (full schema) |
| `rcon_test_server` | Starts a real RCON test server on a free port |
| `discord_bot_token` | Skips if real token not present in env |

---

## Per-File Test Descriptions

---

### `test_database_init.py` — 11 tests

**Purpose:** Verify that `initialize_database()` creates the correct schema and is safe to call multiple times.

**What it covers:**
- All expected tables are present after initialization (guilds, remote_agents, server_configs, ark_servers, players, player_sessions, users, store_items, transactions, coin_transactions, pending_deliveries, voice_channel_mappings, economy_settings, economy_roles, payday_history, shop_config, cart_items)
- `initialize_database()` is idempotent (calling it twice does not raise)
- Schema validation for guilds, remote_agents, server_configs, players, ark_servers, voice_channel_mappings tables (via `PRAGMA table_info`)
- Basic database connectivity
- Table creation order (FK dependency: server_configs before ark_servers)
- Custom database path via `Config.DATABASE_PATH` override

**Key test functions:**
- `test_initialize_database_creates_tables` — asserts all 17+ tables exist
- `test_initialize_database_idempotent` — calls init twice, expects no error
- `test_guilds_table_exists` — checks `guild_id`, `guild_name` columns
- `test_remote_agents_table_exists` — checks `guild_id`, `agent_id`, `agent_ip`, `agent_port`, `auth_key`
- `test_players_table_exists` — checks `guild_id`, `player_name`, `discord_user_id`
- `test_initialize_database_with_custom_path` — verifies custom path works and DB is created

---

### `test_database_server_config.py` — 13 tests

**Purpose:** Full CRUD coverage for `server_config_db.py`: guild configs, ARK servers, voice channel mappings, MOTD, hosting type, and log channel.

**What it covers:**
- `create_or_update_server_config` insert and update
- `get_server_config` returns None for non-existent guild
- `add_ark_server` returns integer server ID, defaults are applied (max_players=70)
- `get_ark_servers` returns empty list when no servers
- `get_ark_server_by_port` finds by RCON port, returns None for missing port
- `set_server_voice_channel_id` / `get_voice_channel_id` / `clear_server_voice_channel_id` create-read-delete
- `set_server_motd` / `get_server_motd` round-trip; defaults when not set
- `get_hosting_type` / `set_hosting_type` / `is_self_hosted` full flow
- `set_log_channel_id` updates guild config
- `get_all_guild_ids` returns all configured guild IDs

**Key test functions:**
- `test_create_server_config` — insert + retrieve, check `hosting_type` default is `self_hosted`
- `test_update_server_config` — rename guild, set `status_channel_id`
- `test_add_ark_server` — insert server, verify default `max_players`
- `test_set_server_voice_channel_id` — map RCON port to voice channel ID
- `test_clear_server_voice_channel_id` — verify removal
- `test_hosting_type_management` — full self_hosted / nitrado toggle
- `test_get_all_guild_ids` — multi-guild isolation

---

### `test_database_economy.py` — 16 tests

**Purpose:** Cover `economy_db.py`: economy settings, role bonus configuration, and payday history.

**What it covers:**
- `get_economy_settings` returns defaults (`base_payday_amount=100`, `currency_name="Phoenix Coins"`, etc.) when no row exists
- `update_economy_settings` creates row on first call, upserts on subsequent calls
- `update_economy_settings` ignores unknown column names (returns `False`)
- Settings are isolated per guild
- `get_economy_roles` / `set_economy_role` / `remove_economy_role` full lifecycle
- `set_economy_role` updates existing role on conflict
- `get_economy_roles` returns roles sorted by `bonus_amount` DESC
- Economy roles are isolated per guild
- `record_payday` / `get_last_payday` round-trip
- `get_last_payday` returns most recent record when multiple exist
- `get_last_payday` returns None when no record
- Payday records are isolated per guild

**Key test functions:**
- `test_get_economy_settings_defaults` — verifies all default values
- `test_update_economy_settings_ignores_invalid_keys` — invalid key returns `False`
- `test_update_economy_settings_guild_isolation` — two guilds, different values
- `test_get_economy_roles_sorted_by_bonus` — verifies DESC sort order
- `test_deduct_coins_race_safe` (covered in `test_economy_migration.py`)

---

### `test_database_shop.py` — 31 tests

**Purpose:** Full CRUD coverage for `shop_db.py`: shop configuration, store items, shopping cart, transactions, and pending deliveries.

**What it covers:**
- `get_shop_config` returns defaults (`shop_enabled=1`, `require_linked_account=1`)
- `update_shop_config` creates row, upserts, ignores invalid keys
- Shop config guild isolation
- `add_store_item` returns positive integer ID
- `get_store_item` by ID, returns None for unknown
- `get_store_items` empty list, filter by category, guild isolation
- `get_categories` returns distinct categories with item counts
- `update_store_item` field changes, returns `False` for invalid keys
- `delete_store_item` removes item
- Cart: `add_to_cart` new entry, quantity combining for identical item+quality+blueprint, separate entries for different quality
- Cart: `get_cart` empty, includes `ark_command` join
- `remove_from_cart` by cart_id, `clear_cart` removes all user items
- `record_transaction` returns positive `transaction_id`
- `update_transaction_status` changes status field, stores `error_message`
- `add_pending_delivery` returns positive `delivery_id`
- `get_pending_deliveries` by guild, all guilds (no filter)
- `delete_pending_delivery` removes record

**Key test functions:**
- `test_add_to_cart_combines_quantity` — adding same item twice merges quantity
- `test_add_to_cart_different_quality_separate_entries` — quality creates separate entry
- `test_get_cart_includes_ark_command` — verifies JOIN with store_items
- `test_update_transaction_status_with_error` — error_message persisted
- `test_get_pending_deliveries_all` — verifies cross-guild delivery fetch

---

### `test_economy_migration.py` — 11 tests

**Purpose:** Verify economy functions on `players_db.py` that live on `players.balance` (the migrated architecture, where balance is NOT in `users.phoenix_coins`).

**What it covers:**
- `get_balance(guild_id, eos_id)` returns correct balance; returns 0 for non-existent player
- `get_balance_by_discord_id(guild_id, discord_user_id)` returns `(balance, eos_id)` tuple for linked player; returns `(0, None)` when not linked
- `add_coins` returns updated balance, accumulates correctly
- `add_coins` creates `coin_transactions` record with correct `eos_id`, `amount`, `transaction_type="credit"`, `reason`, `admin_id`
- `deduct_coins` succeeds when balance is sufficient, returns `True`
- `deduct_coins` returns `False` and leaves balance unchanged when insufficient
- `deduct_coins` is race-safe (`WHERE balance >= ?`): exact amount works, subsequent deduction fails
- `get_coin_history` returns all transactions with correct types; returns empty list when none

**Key test functions:**
- `test_deduct_coins_race_safe` — verifies atomic balance check
- `test_add_coins_logs_transaction_with_eos_id` — verifies audit trail in `coin_transactions`
- `test_get_balance_by_discord_id_not_linked` — returns `(0, None)` sentinel

---

### `test_database_chat_history.py` — 9 tests

**Purpose:** Verify `chat_history_db.py` multi-tenant chat storage, retrieval, filtering, cleanup, and statistics.

**What it covers:**
- `init_chat_history_table` creates table and `idx_chat_server_timestamp` index
- `store_chat_message` / `get_chat_history` round-trip with correct field values
- `get_chat_history` respects `limit` parameter
- `get_chat_history` respects `hours` filter (inserts with specific timestamps, verifies old messages excluded)
- `get_chat_history` filters by server name
- `cleanup_old_messages` deletes messages older than specified days, returns count
- `get_chat_stats` returns `total_messages`, `per_server` dict with counts, `oldest_message_timestamp`
- `get_chat_stats` returns zeros/empty for empty database
- `store_chat_message` handles gracefully (no exceptions on normal input)

**Key test functions:**
- `test_get_chat_history_with_hours_filter` — manual timestamp insertion to test time-based filter
- `test_cleanup_old_messages` — inserts 5-day-old and 1-day-old, deletes only old one
- `test_get_chat_stats` — multi-server count aggregation

---

### `test_server_management.py` — 57 tests

**Purpose:** Comprehensive coverage of `server_management.py` — the `/servermgmt` hierarchical GUI console. Largest test file in the suite.

**Test classes and what they cover:**

#### `TestBuildServerOptions` (7 tests)
- Basic server produces correct `label`, `value`, `description`
- Missing `map_name` shows "Not set" in description
- Empty servers list returns empty
- Non-dict entries skipped
- Fallback to `server_id` when name/display_name absent
- Label truncated at 100 characters (Discord limit)
- `display_name` preferred over `name`

#### `TestServerLabel` (5 tests)
- `display_name` preferred over `name`
- Fallback to `name`, then to `id`
- Whitespace-only display name treated as empty

#### `TestGetServerByIdentifier` (7 tests)
- Find by `name`, by `display_name`, by `id` (as string)
- Returns None for non-existent identifier
- Empty string and None identifiers return None
- Non-dict entries in list are skipped

#### `TestEmbedBuilders` (9 tests)
- `_main_panel_embed` includes server count in description
- `_category_panel_embed` shows server name, service name, hosting type
- Missing service name shows "N/A"
- All six panel embeds (`_server_ops_embed`, `_server_control_embed`, `_advanced_embed`, `_diagnostics_embed`, `_updates_embed`) have correct titles and content

#### `TestViewConstruction` (12 tests)
- `ServerManagementView` with servers has 2 children (select + updates button)
- `ServerManagementView` with no servers has 1 child (updates button only)
- `ServerSelectedView` has exactly 5 buttons
- Back button has `«` prefix
- `ServerOperationsView` has Broadcast, Save World, Destroy Wild, MOTD, Back buttons
- Destroy Wild button uses T-Rex emoji
- `ServerControlView` has Stop, Start, Restart, Status, Back buttons
- `ServerControlView` receives server dict directly (no re-selection)
- `AdvancedToolsView` has Custom RCON, Chat Log, Back
- `DiagnosticsView` has View Log, Errors, Crash History, Back
- `ServerUpdatesView` has 3 selects and Start Update + Back buttons
- Updates view auto-selects all servers when none selected

#### `TestModals` (3 tests)
- `BroadcastModal`, `MOTDModal`, `CustomRCONModal` all store the server reference

#### `TestServerManagementCog` (1 test)
- Cog initializes and stores bot reference

#### `TestPSBotIconAlignment` (7 tests)
- Exact emoji/label strings verified for all four category buttons
- ServerOps exact button labels verified
- ServerControl exact labels and `ButtonStyle` verified (Stop=danger, Start=success, Restart=primary)
- Advanced exact labels
- Diagnostics exact labels
- Save World=success, Destroy Wild=danger button style verified

#### `TestFindAgentForGuild` (3 tests)
- No `agent_manager` attribute returns None
- `agent_manager=None` returns None
- Real `_FakeAgentManager` returns None (no connection)

#### `TestBuildServerOptionsEdgeCases` (3 tests)
- Server with no name/display_name/id gets "Server #?" fallback label
- Mixed valid and invalid entries; invalid skipped, valid processed
- Missing `host` key shows "Unknown Host"

---

### `test_setup_gui_server_update.py` — 5 tests

**Purpose:** Verify `ServerDirectoriesModal` in `setup_gui.py` — the modal that configures server/steamcmd/log paths.

**What it covers:**
- Modal stores `server` and `parent_view` references
- All four fields (`server_path`, `steamcmd_path`, `log_path`, `service_name`) are not required (empty = keep existing)
- Fields pre-populated with existing server data as defaults
- Update data structure with new values
- Update data structure with None values (clearing fields)
- `update_ark_server()` called with `**kwargs` correctly updates all four path fields

**Key test functions:**
- `test_server_directories_modal_validation` — field labels, not-required constraint
- `test_server_directories_modal_pre_population` — default values from server dict
- `test_server_directories_modal_database_update` — real DB: add server, update paths, verify storage

---

### `test_server_update_fix.py` — 3 tests

**Purpose:** Verify `update_ark_server()` function signature and behavior. Written to prevent regression of a specific bug where the function was called with a positional dict instead of kwargs.

**What it covers:**
- `update_ark_server(server_id, **kwargs)` updates core fields correctly
- Optional fields (`server_path`, `service_name`, `query_port`) persisted correctly
- Minimal update with `enabled=False` works; `server_path` and `service_name` remain `None` when not passed

**Key test functions:**
- `test_update_ark_server_function` — core fields update
- `test_update_ark_server_with_optional_fields` — full optional field set
- `test_update_ark_server_minimal_data` — direct SQL query to verify `enabled=False` and untouched nullable columns

---

### `test_server_config_gui.py` — 4 tests

**Purpose:** Verify the multi-step server configuration modal system in `setup_gui.py` via real database operations.

**What it covers:**
- `AddServerModal` is importable
- `EditServerModal` can reference server data with correct fields
- `ServerDirectoriesModal` stores and retrieves path configuration from DB
- `ServerActionsView` (or equivalent) creates embed showing `max_players` and server name

**Key test functions:**
- `test_server_directories_modal` — add server, update with paths, verify all four path columns in DB
- `test_server_actions_view_embed` — server created with `max_players=70`, verified in DB

---

### `test_remote_agent_real.py` — 11 tests

**Purpose:** Verify `RemoteAgentManager` and `RemoteAgentCommands` cog with real objects and real network error paths.

**Test classes:**

#### `TestRemoteAgentManagerReal` (7 tests)
- `RemoteAgentManager` initializes with empty `agents`, `connections`, `_listeners`, `_pending`, `_reconnect_tasks`
- `register_agent` with invalid port (99999) genuinely fails and returns `(False, "Failed to connect...")` or `"Connection timed out"`; agents dict stays empty
- Agent data structure stores guild_id, ip, port, auth_key, connected_at correctly
- `send_command` to non-existent agent raises `ConnectionError("not connected")`
- `send_command_fire_and_forget` to non-existent agent returns `False`
- `get_agent_status` returns agent dict with `connected=False`; returns `None` for unknown agent
- `get_connected_agent_for_guild` returns None when no agents, when agent exists but not connected, and when agent belongs to different guild
- `close_all()` completes without error even with no connections; cleans up `connections` dict

#### `TestRemoteAgentCommandsReal` (2 tests)
- Admin check passes with `guild_permissions.administrator=True`, fails with `False`
- Admin check returns `False` when `interaction.guild` is `None`

#### `TestRemoteAgentIntegrationReal` (1 test)
- Full lifecycle: init, failed registration, manual agent insertion, status check, send command error, fire-and-forget, close_all

---

### `test_bot_agent_communication.py` — 5 tests

**Purpose:** Verify bot-to-agent communication contracts and parameter construction. Written to prevent regression of a SteamCMD path configuration bug.

**What it covers:**
- WebSocket connection to a live agent (skipped if agent not reachable)
- Agent database config structure (`agent_id`, `agent_ip`, `agent_port`, `auth_key` keys all present)
- RemoteAgent cog loading flow exists (step names validated)
- SteamCMD path construction: `os.path.join(steam_directory, "steamcmd.exe")` for Windows and Linux paths
- `update_server` command parameter structure: `type`, `server`, `request_id`, `params` with `steamcmd_path`, `server_path`, `use_custom_script`, `ark_appid`

**Key test functions:**
- `test_bot_agent_connection_status` — live WebSocket test, skipped when agent unreachable
- `test_steamcmd_path_construction` — three path construction cases
- `test_command_parameter_validation` — full `update_server` command dict validation

---

### `test_utils_config.py` — 14 tests

**Purpose:** Verify `bot/utils/config.py` Config class defaults, environment variable loading, and structure.

**Test classes:**

#### `TestConfigDefaults` (6 tests)
- `DATABASE_PATH` is not None
- `BOT_PREFIX` is `"!"`
- `LOG_LEVEL` is one of INFO/DEBUG/WARNING/ERROR
- Shop defaults: `SHOP_STARTING_BALANCE=1000`, `SHOP_DAILY_LOGIN_BONUS=100`, `SHOP_ITEMS_PER_PAGE=10`, `SHOP_DELIVERY_COOLDOWN=60`
- Status intervals: `STATUS_UPDATE_INTERVAL=60`, `CHAT_POLL_INTERVAL=5`
- `CURRENCY_NAME` is `"Phoenix Coins"`

#### `TestConfigEnvironmentVariables` (4 tests)
- `DISCORD_BOT_TOKEN` loadable from environment
- `DATABASE_PATH` overrideable via environment
- `DISCORD_APP_ID` loadable from environment
- `DISCORD_GUILD_ID` loadable from environment

#### `TestConfigValidation` (2 tests)
- Config skips token validation when `PYTEST_CURRENT_TEST` is set
- Config class has expected attribute structure

#### `TestConfigIntegration` (2 tests)
- Config importable from `bot.utils.config`
- All six expected attributes (`DISCORD_BOT_TOKEN`, `DATABASE_PATH`, `BOT_PREFIX`, `LOG_LEVEL`, `STATUS_UPDATE_INTERVAL`, `CHAT_POLL_INTERVAL`) exist

---

### `test_utils_log_parser.py` — 2 tests

**Purpose:** Minimal coverage of `bot/utils/log_parser.py` without file I/O.

**What it covers:**
- `_find_agent_for_server` returns `None` when `agent_manager=None`
- `parse_server_startup_info` with dummy path returns defaults: `max_players=None`, `cluster_id=None`, `cluster_folder_path=None`

---

### `test_utils_system_monitor.py` — 4 tests

**Purpose:** Verify `SystemServerMonitor` initialization and configuration without live server I/O.

**What it covers:**
- `SystemServerMonitor(agent_manager=None)` stores `None` correctly
- `set_agent_manager()` replaces the manager reference
- `add_server()` accepts a server name and log path without error
- Log path storage via `add_server()` does not raise

---

### `test_help_commands_embed.py` — 1 test

**Purpose:** Verify the `/help` embed does not exceed Discord's hard limits.

**What it covers:**
- `HelpCommands.create_all_commands_embed()` returns embed with no more than 25 fields (Discord maximum)
- Each field value is no longer than 1024 characters (Discord field value limit)

Uses a real `commands.Bot` with `discord.Intents.none()` — no Discord connection required.

---

### `test_suite.py` and `test_suite_with_batches.py`

These are legacy test runner scripts (standalone `asyncio.run()` style) predating the pytest migration. They contain additional functional tests but are superseded by the per-module pytest files above. They are retained for reference.

---

## Coverage Summary

| Component | File(s) Tested | Coverage |
|-----------|----------------|----------|
| Database initialization | `test_database_init.py` | Table creation, idempotency, schema validation |
| Guild / server config | `test_database_server_config.py` | Full CRUD, voice channels, MOTD, hosting type |
| Economy settings | `test_database_economy.py` | Settings, roles, payday history, guild isolation |
| Economy (balance) | `test_economy_migration.py` | get/add/deduct coins, history, race safety |
| Shop | `test_database_shop.py` | Config, items, cart, transactions, deliveries |
| Chat history | `test_database_chat_history.py` | Store, retrieve, filter, cleanup, stats |
| Server management GUI | `test_server_management.py` | Helpers, embeds, views, modals, icon alignment |
| Setup GUI — server edit | `test_setup_gui_server_update.py`, `test_server_config_gui.py` | DirectoriesModal, EditServerModal, DB update |
| `update_ark_server` | `test_server_update_fix.py` | kwargs signature, optional fields, enabled=False |
| Config class | `test_utils_config.py` | Defaults, env vars, structure |
| Log parser | `test_utils_log_parser.py` | `_find_agent_for_server`, `parse_server_startup_info` |
| System monitor | `test_utils_system_monitor.py` | Init, set_agent_manager, add_server |
| Remote agent manager | `test_remote_agent_real.py` | Lifecycle, error paths, admin check |
| Bot-agent protocol | `test_bot_agent_communication.py` | Path construction, command structure |
| Help embed | `test_help_commands_embed.py` | Discord field limits |

---

## CI / Deployment Requirements

1. **All 252+ tests must pass before any deployment to Pi 5.** No exceptions.
2. Run the full suite locally after every change: `python -m pytest tests/ -v`
3. Tests requiring a live Discord token or live agent are automatically skipped when those environment variables are absent — they will not cause CI failures.
4. The `PYTEST_CURRENT_TEST` environment variable is set by pytest automatically; `conftest.py` also sets `DISCORD_BOT_TOKEN=test-token-not-real` as a sentinel so Config does not error during tests.
5. After fixing a bug, add a regression test to the relevant file before closing the issue.
6. New cogs must have a corresponding `tests/test_<cog_name>.py` file before the PR is merged.
