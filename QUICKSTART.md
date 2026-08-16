# ARK Discord Bot - Quick Start Guide

## Prerequisites Checklist

Before running the bot, make sure you have:

- [ ] Python 3.11 or higher installed
- [ ] Discord bot created at https://discord.com/developers/applications
- [ ] Bot token copied
- [ ] Bot invited to your Discord server
- [ ] ARK server(s) running with RCON enabled
- [ ] RCON passwords for your servers

## Quick Setup Steps

### 1. Install Python Dependencies

```powershell
# Create virtual environment
python -m venv venv

# Activate it
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```powershell
# Copy example env file
Copy-Item .env.example .env

# Edit with your settings
notepad .env
```

**Required settings:**
- `DISCORD_BOT_TOKEN` - Your bot token from Discord Developer Portal
- `DISCORD_GUILD_ID` - Your Discord server ID (right-click server → Copy ID)
- `ARK_SERVERS` - Your ARK server details in JSON format

**Optional settings:**
- `CHAT_CHANNEL_ID` - Channel for cross-chat (right-click channel → Copy ID)
- `STATUS_CHANNEL_ID` - Channel for status updates
- `ADMIN_ROLE_ID` - Role that can use admin commands

### 3. Run Setup Script

```powershell
python scripts\setup.py
```

This will:
- Verify your configuration
- Create the database
- Optionally add sample store items

### 3b. Seed the shop catalogue (recommended)

The bot ships with **no database** — one is created empty on first run, so you start with a clean
slate and nobody else's data. It *does* ship with the ARK item catalogue: 1,593 items
(structures, saddles, skins, consumables, resources, chibis, mod items, event items) with names,
descriptions, costs and blueprint paths, in `data/seed/store_items.json`.

Shop items are stored per Discord server, so import them under your own guild id:

```powershell
python scripts\seed_shop_items.py --guild-id YOUR_SERVER_ID
```

Get the id by enabling Developer Mode in Discord (User Settings -> Advanced), then right-clicking
your server and choosing "Copy Server ID". Useful variations:

```powershell
python scripts\seed_shop_items.py --guild-id 123... --dry-run          # preview, write nothing
python scripts\seed_shop_items.py --guild-id 123... --category mods    # one category only
```

Re-running is safe — existing items are updated rather than duplicated, so this is also how you
pull in catalogue changes later. Prices are a starting point; edit them to suit your economy.

### 4. Start the Bot

```powershell
python main.py
```

## Discord Bot Setup

### Enable Required Intents

1. Go to https://discord.com/developers/applications
2. Select your application
3. Go to **Bot** section
4. Scroll to **Privileged Gateway Intents**
5. Enable:
   - ✅ Presence Intent
   - ✅ Server Members Intent
   - ✅ Message Content Intent
6. Save Changes

### Generate Invite URL

1. Go to **OAuth2** → **URL Generator**
2. Select scopes: `bot` and `applications.commands`
3. Select permissions:
   - Read Messages/View Channels
   - Send Messages
   - Embed Links
   - Read Message History
   - Add Reactions
   - Use Slash Commands
4. Copy the URL and open in browser
5. Select your server and authorize

## ARK Server Configuration

Add to your `GameUserSettings.ini`:

```ini
[ServerSettings]
RCONEnabled=True
RCONPort=27020
ServerAdminPassword=YourRCONPasswordHere
```

**Important:** Each server needs a unique RCON port!

Restart ARK server after changes.

## Testing the Bot

### Test Commands

1. In Discord, type `/help` - should show command list
2. Type `/balance` - should show your Phoenix Coins (0 initially)
3. Type `/servers` - should show your ARK servers status

### Grant Yourself Coins (Admin)

```
/grantcoins @YourUsername 1000
```

### Add a Test Item

```
/additem
  name: Test Item
  cost: 10
  ark_command: GiveItemNumToPlayer {player_id} 1 1 0 false
  description: A test item
  category: test
```

### Test Purchase

1. Log into your ARK server
2. In Discord: `/buy 1 YourCharacterName`
3. Item should appear in-game!

## Troubleshooting

### Bot not responding?
- Check bot is online (green dot in Discord)
- Verify bot has permissions in the channel
- Check `logs/bot.log` for errors

### RCON connection failed?
- Verify RCON is enabled in GameUserSettings.ini
- Check firewall allows RCON port
- Test with RCON tool like `RCONPassword.exe`

### Item not delivered?
- Make sure you're **online** in-game
- Character name must be **exact** (case-sensitive)
- Character must be **fully loaded** in world

## Next Steps

- Add your actual store items using `/additem`
- Set up status channel updates
- Configure cross-chat channel
- Grant Phoenix Coins to your players
- Customize currency name/emoji in `.env`

## Getting Help

- Check the main README.md for full documentation
- Review bot logs in `logs/bot.log`
- Check ARK server logs for RCON issues
- Open an issue on GitHub

## Useful Commands Reference

### For Players
- `/store` - Browse shop
- `/buy <id> <character>` - Purchase item
- `/balance` - Check coins
- `/servers` - View servers
- `/players` - See who's online
- `/help` - Show all commands

### For Admins - Currency & Store
- `/grantcoins <user> <amount>` - Give coins
- `/additem` - Add store item
- `/removeitem <id>` - Remove item
- `/setprice <id> <price>` - Change price
- `/userinfo <user>` - View user stats

### For Admins - Bot Configuration
- `/config` - View current configuration
- `/setchatchannel <channel>` - Set chat relay channel
- `/setstatuschannel <channel>` - Set status updates channel
- `/addserver` - Add new ARK server to monitor
- `/removeserver <name>` - Remove ARK server
- `/updateserver` - Update server settings (host, port, password)
- `/listservers` - List all configured servers

**Note:** Configuration changes via commands update the `.env` file but require a bot restart to fully take effect.

## Dynamic Configuration from Discord

You can now configure most bot settings directly from Discord without editing files:

### Adding a New ARK Server

```
/addserver
  name: The Center
  host: 127.0.0.1
  rcon_port: 27030
  rcon_password: YourPassword
  chat_enabled: True
```

**Note:** Use `127.0.0.1` for host if the bot runs on the same machine as your ARK servers.

### Updating Server Settings

```
/updateserver
  name: Aberration
  host: 192.168.1.100
  rcon_port: 27001
```

Only specify the fields you want to change!

### Changing Channels

```
/setchatchannel #ark-chat
/setstatuschannel #server-status
```

### Viewing Configuration

```
/config
```

Shows current channels, servers, and settings.

---

**Need more help?** Check the full README.md or contact your server admin!
