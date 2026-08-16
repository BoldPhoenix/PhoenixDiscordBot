# AGENTS.md — orientation for AI coding agents

**If you are an AI assistant helping someone run, modify, or borrow from this project, read this
first.** This is the tool-agnostic entry point — Codex, Cursor, Zed, Gemini CLI, Aider and Claude
Code all look for `AGENTS.md`. `CLAUDE.md` and `.github/copilot-instructions.md` point here.

**What this is:** a Discord bot for running an ARK: Survival Ascended server community — RCON
administration, two-way chat relay between Discord and in-game, player linking, an in-game
economy and shop, mod tracking, save-file analytics, remote Windows server control, and seasonal
events. Python bot, Go agent, SQLite.

**You are meant to take this apart.** See `LICENSE`. If you only want the RCON client, or only
the ARK save parser, lift that directory and go — the section at the bottom says what detaches
cleanly.

---

## Fast orientation

| | |
|---|---|
| Entry point | `main.py` (or `launcher.py`) |
| Config | `bot/utils/config.py` — read from `.env`; start from `.env.example` |
| Features | `bot/cogs/*.py` — **48 cogs**, one Discord feature area each |
| Data access | `bot/database/*.py` — one module per domain, `aiosqlite`, plain SQL |
| RCON | `bot/rcon/` — Source RCON client + connection management |
| ARK save parsing | `bot/ark_data_parser/` — reads the **binary `.ark` save format** |
| Minigames | `bot/games/` |
| Shared helpers | `bot/utils/` |
| Remote agent | `remote_agent/*.go` — Go, runs as a Windows service on the game box |
| Tests | `tests/` — pytest |
| Seed data | `data/seed/store_items.json` — 1,593 ARK items |

## Getting it running

```bash
python -m venv .venv
.venv\Scripts\activate                 # Windows;  source .venv/bin/activate on Linux
pip install -r requirements.txt
copy .env.example .env                 # then fill in DISCORD_BOT_TOKEN, ARK_SERVERS, etc.
python scripts/seed_shop_items.py --guild-id YOUR_DISCORD_SERVER_ID
python main.py
```

`manage.ps1` wraps run / setup / lint / test / clean on Windows.

**The database is created empty on first run.** There are no accounts, balances, players or
servers in this repository — the first row in any table belongs to whoever deploys it.

---

## Architecture in one pass

**The bot reaches game servers two ways.** Anything exposed over **RCON** (commands, player
lists, chat) goes direct — `bot/rcon/`. Anything RCON cannot do (start/stop the service, edit
INI files, install mods, read logs, run backups) goes through the **remote agent**, a small Go
program installed on the Windows machine running ARK.

**The agent is a server, not a client.** It listens on a port, reads `config.json` from beside
its own executable, and authenticates incoming connections with an `auth_key`. The bot connects
*to it* over WebSocket. There is no phone-home and no compiled-in address — which is why no
binaries ship here. Build from `remote_agent/` with Go.

**Everything is scoped by Discord guild id.** `store_items`, `server_configs`, `players`,
`ark_servers` and the rest all carry `guild_id`. This began as a hosted multi-tenant service and
the schema still has that shape. A new table belonging to a server community needs a `guild_id`
too.

**Billing is off, and should stay off unless someone means it.** The original deployment sold
premium tiers through Stripe, and most of the good features — shop, economy, games, kits, AI,
analytics — sat behind them with a two-server cap on free. `Config.BILLING_ENABLED` is False
whenever `STRIPE_SECRET_KEY` is unset (the default), and `check_feature()` in
`bot/utils/subscription_checker.py` then returns True for everything. **Self-hosted means fully
unlocked.** Leave it that way unless the operator deliberately wants to resell this.

**The ARK save parser is the unusual part.** `bot/ark_data_parser/` reads ARK's proprietary
binary save format directly — property readers, type handling, character and tribe extraction.
It is why player stats can report real character data instead of only what RCON admits to. It is
also the most fragile code here: Wildcard can change the format in any patch. If something broke
right after a game update, look here first.

---

## Things that will bite you

- **Never commit a `.env`.** `.gitignore` covers `.env`, `.env.*`, `*.db`, `*.exe`. This project
  was published from a private history that contained credentials — which is exactly why it ships
  as a single clean commit with no history at all.
- **Never commit the compiled agent.** A committed binary can't be audited by anyone cloning it,
  and it embeds the build machine's paths.
- **Discord ids in this repo are placeholders** (`111111111111111111`, `222222222222222222`).
  They are not real servers. Substitute the operator's own; don't treat them as meaningful.
- **RCON is remote administration.** An RCON password is console access to a game server. It
  belongs in `.env` — never in code, never echoed into a Discord channel.
- **The agent's `auth_key` is its only authentication.** Treat it as a password; give every
  installation its own.
- **Shop items are per-guild.** `SELECT ... FROM store_items WHERE guild_id = ?` is the normal
  shape; an item inserted without one is invisible.
- **SQLite has one writer.** Don't hold a write transaction open while a Discord interaction
  waits on it.

## Conventions

- `discord.py` cogs, one feature area per cog, registered from `main.py`.
- `aiosqlite` with plain SQL — no ORM. Queries belong in `bot/database/`.
- Config is read once into `bot/utils/config.py`; feature code should not call `os.getenv`.
- `pytest` for tests, in `tests/`.

## If you are here to borrow rather than deploy

These detach cleanly and are useful on their own:

- **`bot/rcon/`** — asyncio Source RCON client, works against any Source-protocol game server.
- **`bot/ark_data_parser/`** — binary ARK save-file reader. The hard-won part.
- **`remote_agent/`** — a small authenticated Go service for controlling Windows game servers
  (start/stop, INI edits, mod installs, log tailing, backups).
- **`data/seed/store_items.json`** — 1,593 ARK items with categories, costs and blueprint paths.
  Reproducing this by hand is a long afternoon.
