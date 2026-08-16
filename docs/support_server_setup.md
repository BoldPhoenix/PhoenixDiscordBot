# Phoenix ARK Discord Support Server Setup Guide

**Purpose**: Day-one launch support server with inviting, informative structure

---

## Step 1: Create Server

1. Open Discord → Click "+" → Create My Own Server
2. Server Name: **Phoenix ARK Support**
3. Server Region: Auto (or closest to your users)
4. Icon: Use bot logo or ARK-themed image

---

## Step 2: Create Role Hierarchy

Navigate to: Server Settings → Roles

Create roles in this order (top to bottom = highest to lowest priority):

### Role List

| Role | Color | Permissions | Notes |
|------|-------|-------------|-------|
| `@Owner` | Gold | Administrator | You only |
| `@Staff` | Purple | Manage Messages, Kick/Ban, View Audit Log | Support team |
| `@Lifetime` | Platinum (Light Gray) | View channels, Send messages, Embed links | Auto-assigned by bot |
| `@Premium` | Teal | View channels, Send messages, Embed links | Auto-assigned by bot |
| `@Verified` | Green | View channels, Send messages | User linked their server |
| `@Beta Tester` | Orange | View channels, Send messages | Early access testers |
| `@everyone` | Default | View channels, Send messages (limited) | Default permissions |

### @everyone Permissions (set these)
- ✅ View Channels
- ✅ Read Message History
- ✅ Use Application Commands
- ❌ Send Messages (disable for #welcome, #rules, #announcements)
- ❌ Add Reactions (disable for announcement channels)

---

## Step 3: Create Channel Categories

### Category: 📌 LANDING ZONE

Create these channels as **Text Channels**:

#### `#welcome`
**Purpose**: First impression, read-only
**Permissions**: @everyone can view but NOT send messages

**Pinned Message**:
```
🦖 Welcome to Phoenix ARK Support!

Phoenix ARK Bot is a professional Discord bot for managing ARK: Survival Ascended servers. Monitor players, run an economy, manage mods, and control your servers — all from Discord.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📎 **ADD THE BOT**
[Click here to invite Phoenix ARK Bot to your server]
(https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=8&scope=bot%20applications.commands)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 **QUICK START**
1. Invite bot to your Discord server
2. Run `/setup` to configure channels and roles
3. Add your ARK servers (IP, RCON port, password)
4. (Optional) Install Remote Agent for self-hosted servers

📖 Full setup guide: <#CHANNEL_ID_GETTING_STARTED>
🎮 Remote Agent guide: <#CHANNEL_ID_REMOTE_AGENT_GUIDE>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💎 **GO PREMIUM**
Unlock unlimited servers, economy, player linking, games, and more!
See pricing: <#CHANNEL_ID_PRICING_TIERS>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎫 **NEED HELP?**
• Check <#CHANNEL_ID_FAQ> for quick answers
• Open a ticket in <#CHANNEL_ID_GENERAL_SUPPORT>
• Premium members get priority support in <#CHANNEL_ID_PREMIUM_SUPPORT>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔗 **LINKS**
• Documentation: https://github.com/BoldPhoenix/PhoenixArkDiscordBot
• Remote Agent: https://github.com/BoldPhoenix/PhoenixArkRemoteAgent
• Report Bugs: <#CHANNEL_ID_BUG_REPORTS>
• Feature Requests: <#CHANNEL_ID_FEATURE_REQUESTS>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

*Need help? Check #faq first, then open a ticket!*
```

---

#### `#rules`
**Purpose**: Server rules, read-only
**Permissions**: @everyone can view but NOT send messages

**Pinned Message**:
```
📋 SERVER RULES

1. **Be Respectful** — Treat all members with courtesy. No harassment, discrimination, or toxicity.

2. **Stay On Topic** — Keep discussions in appropriate channels. Use #general-chat for off-topic.

3. **No Spam** — No advertising, self-promotion, or repeated messages.

4. **One Ticket at a Time** — Don't open multiple tickets for the same issue. Be patient.

5. **Provide Details** — When reporting bugs, include bot version, steps to reproduce, and screenshots.

6. **English Only** — Keep discussions in English for staff accessibility.

7. **Follow Discord ToS** — Discord's Terms of Service apply to this server.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ Violations may result in warnings, mutes, or bans depending on severity.
```

---

#### `#announcements`
**Purpose**: Bot updates, new features, maintenance
**Permissions**: @everyone can view, only @Owner/@Staff can send

**First Announcement**:
```
🦖 @everyone Phoenix ARK Bot is Live!

We're excited to launch Phoenix ARK Bot for ARK: Survival Ascended!

✨ Features:
• Server monitoring & status
• Economy & in-game shop
• Player linking & stats
• Mod & INI management
• Remote agent support
• 12 arcade games
• And much more!

📎 Add the bot: #welcome
📖 Get started: #getting-started

Thank you for joining us on this journey!
```

---

#### `#server-status`
**Purpose**: Bot uptime, incidents
**Permissions**: @everyone can view, only bot posts here

**Pinned Message**:
```
📊 BOT STATUS

This channel shows real-time bot status and incident reports.

Status indicators:
🟢 Online — Bot operating normally
🟡 Degraded — Some features may be slow
🔴 Offline — Bot is down (check #announcements for updates)

Current Status: 🟢 Online
Last Updated: Launch Day
```

---

### Category: 📚 INFORMATION HUB

#### `#getting-started`
**Purpose**: Step-by-step setup instructions
**Permissions**: @everyone can view, only @Staff can send

**Pinned Message**:
```
🚀 GETTING STARTED WITH PHOENIX ARK BOT

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1: INVITE THE BOT
Click the invite link in #welcome
Select your Discord server
Authorize the bot with Administrator permissions

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 2: INITIAL SETUP
Run `/setup` in your server
Configure:
• Admin role — Users who can manage bot
• User role — General users
• Channels for logs, status, chat relay

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 3: ADD YOUR ARK SERVERS
In the setup wizard, click "Add Server"
Enter:
• Server name (e.g., "The Island")
• IP address
• RCON port (default: 27020)
• RCON password

The bot will test the connection automatically.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 4: CONFIGURE FEATURES

SERVER MONITORING
• Run `/setup` → Server Monitor → Enable
• Configure update interval (default: 60 seconds)
• Status embeds and voice channels auto-created

CHAT RELAY
• Set a chat channel in `/setup`
• Messages sync between Discord ↔ ARK in-game chat
• Cross-server relay supported

ECONOMY & SHOP (Premium)
• Run `/economycfg` to configure Phoenix Coins
• Run `/shopcfg` to add items to your store
• Players earn coins, purchase items delivered via RCON

PLAYER LINKING (Premium)
• Players run `/player` to link their EOS ID
• Track stats, manage balances, admin controls

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 5: REMOTE AGENT (Self-Hosted Servers)

If you host ARK on your own Windows machine:

1. Download: https://github.com/BoldPhoenix/PhoenixArkRemoteAgent/releases
2. Run installer as Administrator
3. Note the auth_key from config.json
4. In Discord: `/setup` → Remote Agent → Register
5. Enter your PC's IP, port (8080), and auth key

This enables:
• Start/stop/restart servers
• Mod installation
• INI file editing
• Backups and updates

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 6: CREATE NSSM SERVICES (Self-Hosted Servers)

For the Remote Agent to start/stop your ARK servers, each server needs a Windows service.

WHAT IS NSSM?
NSSM (Non-Sucking Service Manager) runs any executable as a Windows service.
Download: https://nssm.cc/download

INSTALLATION:
1. Download nssm-2.24.zip (or latest)
2. Extract to C:\nssm\ (use win64\nssm.exe for 64-bit)

CREATE SERVICE FOR EACH ARK SERVER:
1. Open Command Prompt as Administrator
2. Run: `nssm install ArkIslandServer`
3. In the GUI that opens:
   • Path: Browse to your ARK server executable
     Example: C:/ARK\Servers\Island\ShooterGame\Binaries\Win64\ArkAscendedServer.exe
   • Arguments: Your server launch arguments
     Example: TheIsland?listen?SessionName=MyIsland?RCONEnabled=True?RCONPort=27020 -server -log
   • Startup directory: Your server's Win64 folder
     Example: C:/ARK\Servers\Island\ShooterGame\Binaries\Win64

4. Click "I/O" tab:
   • Output (stdout): C:/ARK\Servers\Island\ShooterGame\Saved\Logs\Island_service.log
   • Error (stderr): C:/ARK\Servers\Island\ShooterGame\Saved\Logs\Island_error.log

5. Click "Install service"

REPEAT FOR EACH SERVER:
• ArkIslandServer
• ArkCenterServer
• ArkRagnarokServer
• etc.

SERVICE COMMANDS:
• Start: `nssm start ArkIslandServer` or `net start ArkIslandServer`
• Stop: `nssm stop ArkIslandServer` or `net stop ArkIslandServer`
• Restart: `nssm restart ArkIslandServer`
• Remove: `nssm remove ArkIslandServer confirm`

VERIFY IN DISCORD:
After creating services, in `/setup`:
1. Edit each ARK server
2. Set the "Service Name" field to match your NSSM service name
3. The bot will now use the service to start/stop servers

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEED HELP?
Open a ticket: #general-support
Check FAQ: #faq
```

---

#### `#commands-reference`
**Purpose**: Complete command list
**Permissions**: @everyone can view, only @Staff can send

**Pinned Message**:
```
📖 COMMAND REFERENCE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 SETUP & CONFIGURATION
/setup — Interactive setup wizard
/setupcfg — View/edit configuration

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🖥️ SERVER MANAGEMENT
/servermgmt — Full control panel (start/stop/restart/mods/INI/logs)
/maintenance — Backup schedules, updates, job history
/modmgmt — Install/remove mods, search CurseForge
/inimgmt — Edit GameUserSettings.ini and Game.ini

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👥 PLAYER MANAGEMENT
/player — Link EOS ID, view stats, check balance
/playermgmt — Admin: link/unlink, add/remove coins, kick/ban
/listlinkedplayers — View all linked players

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 ECONOMY & SHOP (Premium)
/balance — Check Phoenix Coins
/shop — Browse items by category
/cart — Manage shopping cart
/economycfg — Admin: payday, role bonuses, leaderboard
/shopcfg — Admin: add/edit/remove shop items
/report — View analytics dashboards

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎰 GAMES (Premium)
/games — Arcade hub with 12 mini-games
/kits — Claim starter kits

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤖 OTHER
/askphoenix — ARK Q&A assistant (AI)
/subscription — View/manage subscription
/help — Help information

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Admin Commands (Owner-only):
/subadmin — Subscription administration
/botcontrol — Bot restart (Pi 5 only)
```

---

#### `#remote-agent-guide`
**Purpose**: Remote agent installation guide
**Permissions**: @everyone can view, only @Staff can send

**Pinned Message**:
```
🤖 REMOTE AGENT GUIDE

The Phoenix ARK Remote Agent enables advanced features for self-hosted ARK servers.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 WHAT IT DOES
• Start/stop/restart ARK servers
• Install and manage mods
• Edit INI files remotely
• Create and restore backups
• Run SteamCMD updates
• Stream server logs to Discord

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 REQUIREMENTS
• Windows 10/11 or Windows Server 2016+
• ARK: Survival Ascended dedicated server
• Network port 8080 accessible from bot
• Administrator rights on the machine

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📥 INSTALLATION

1. Download the agent:
   https://github.com/BoldPhoenix/PhoenixArkRemoteAgent/releases

2. Run PhoenixArkAgentInstaller.exe as Administrator

3. The installer will:
   • Create service directory (C:\Program Files\Phoenix Ark Agent\)
   • Install Windows service
   • Generate unique auth key
   • Start the service

4. Note your auth_key from:
   C:\Program Files\Phoenix Ark Agent\config.json

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔗 CONNECT TO DISCORD

1. In your Discord server, run `/setup`
2. Click "Remote Agent" → "Register Agent"
3. Enter:
   • Your PC's IP address (local if same network, external if remote)
   • Port: 8080 (default)
   • Auth key from config.json

The bot will test the connection and confirm success.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔥 FIREWALL CONFIGURATION

Windows Firewall must allow port 8080:

1. Open Windows Defender Firewall
2. Click "Allow an app through firewall"
3. Add port 8080 (TCP)
4. Allow on Private (and Public if bot is external)

Or run in PowerShell (Admin):
`New-NetFirewallRule -DisplayName "Phoenix Agent" -Direction Inbound -LocalPort 8080 -Protocol TCP -Action Allow`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🛠️ SERVICE MANAGEMENT

The installer provides menu options for:
• Install / Remove service
• Start / Stop / Restart service

Or use Windows commands:
• Start: `net start PhoenixArkAgent`
• Stop: `net stop PhoenixArkAgent`
• View: `services.msc`

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🖥️ NSSM SERVICES FOR ARK SERVERS

For the agent to start/stop your ARK servers, each server needs a Windows service.

WHAT IS NSSM?
NSSM (Non-Sucking Service Manager) runs any executable as a Windows service.
Download: https://nssm.cc/download

INSTALLATION:
1. Download nssm-2.24.zip (or latest) from https://nssm.cc/download
2. Extract to C:\nssm\
3. Use C:\nssm\win64\nssm.exe for 64-bit Windows

CREATE A SERVICE:
1. Open Command Prompt as Administrator
2. Run: `nssm install <ServiceName>`
   Example: `nssm install ArkIslandServer`

3. In the GUI that opens:

   APPLICATION TAB:
   • Path: Browse to ArkAscendedServer.exe
     Example: C:/ARK\Servers\Island\ShooterGame\Binaries\Win64\ArkAscendedServer.exe
   • Startup directory: Same folder as executable
     Example: C:/ARK\Servers\Island\ShooterGame\Binaries\Win64
   • Arguments: Your server launch line
     Example: TheIsland?listen?SessionName=MyIsland?RCONEnabled=True?RCONPort=27020 -server -log

   I/O TAB (optional but recommended):
   • Output (stdout): Path to log file
     Example: C:/ARK\Servers\Island\ShooterGame\Saved\Logs\service.log
   • Error (stderr): Path to error log
     Example: C:/ARK\Servers\Island\ShooterGame\Saved\Logs\service_error.log

4. Click "Install service"

COMMON SERVICE NAMES:
Use consistent naming for easy management:
• ArkIslandServer
• ArkCenterServer
• ArkRagnarokServer
• ArkExtinctionServer
• etc.

SERVICE MANAGEMENT COMMANDS:
• Start: `nssm start ArkIslandServer` or `net start ArkIslandServer`
• Stop: `nssm stop ArkIslandServer` or `net stop ArkIslandServer`
• Restart: `nssm restart ArkIslandServer`
• Status: `sc query ArkIslandServer`
• Remove: `nssm remove ArkIslandServer confirm`

CONFIGURE IN DISCORD:
After creating services, update each server in `/setup`:
1. Edit your ARK server
2. Set "Service Name" to match your NSSM service name exactly
3. The agent will now use this service for start/stop/restart

QUICK SETUP SCRIPT (PowerShell):
Create a file `create_services.ps1`:

```powershell
$servers = @(
    @{Name="Island"; Map="TheIsland"; Port=27020},
    @{Name="Center"; Map="TheCenter"; Port=27022},
    @{Name="Ragnarok"; Map="Ragnarok"; Port=27024}
)

ForEach ($server in $servers) {
    $serviceName = "Ark$($server.Name)Server"
    $path = "C:/ARK\Servers\$($server.Name)\ShooterGame\Binaries\Win64\ArkAscendedServer.exe"
    $args = "$($server.Map)?listen?SessionName=$($server.Name)?RCONEnabled=True?RCONPort=$($server.Port) -server -log"
    
    Start-Process -FilePath "C:\nssm\win64\nssm.exe" -ArgumentList "install $serviceName `"$path`" $args" -Wait
    Write-Host "Created service: $serviceName"
}
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🐛 TROUBLESHOOTING

Agent won't start?
• Check Windows Event Viewer → Application logs
• Verify port 8080 is not in use: `netstat -ano | findstr 8080`

Bot can't connect?
• Ping the agent IP from bot machine
• Verify auth key matches exactly
• Check firewall allows port 8080

Commands fail?
• Verify ARK service names in Discord server config
• Check RCON ports are open on ARK servers
• Ensure RCON passwords are correct

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📖 Full documentation:
https://github.com/BoldPhoenix/PhoenixArkRemoteAgent
```

---

#### `#pricing-tiers`
**Purpose**: Feature comparison
**Permissions**: @everyone can view, only @Staff can send

**Pinned Message**:
```
💎 PRICING & TIERS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🆓 FREE TIER — $0/month

Perfect for small communities getting started.

✅ Up to 2 ARK servers
✅ 1 remote agent
✅ Server start/stop/restart
✅ Mod management
✅ INI editing
✅ Backup & updates
✅ Chat relay (Discord ↔ ARK)
✅ Server monitoring & voice channels
✅ Basic RCON commands

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⭐ PREMIUM — $9.99/month

Full feature access for active communities.

Everything in Free, PLUS:
✅ Unlimited ARK servers
✅ Unlimited remote agents
✅ Economy & Phoenix Coins
✅ Player linking & stats
✅ In-game shop with delivery
✅ Starter kits
✅ 12 arcade games
✅ AI assistant (20 queries/day)
✅ Analytics dashboards
✅ Priority support

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏆 LIFETIME — $199 one-time

All Premium features forever.

Everything in Premium, PLUS:
✅ One-time payment
✅ All future features included
✅ Highest priority support
✅ Early access to beta features

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💳 HOW TO SUBSCRIBE

1. Run `/subscription` in your server
2. Click "Upgrade to Premium"
3. Complete payment via Stripe
4. Features unlock instantly

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❓ QUESTIONS?
Open a ticket: #general-support
```

---

#### `#faq`
**Purpose**: Frequently asked questions
**Permissions**: @everyone can view, only @Staff can send

**Pinned Message**:
```
❓ FREQUENTLY ASKED QUESTIONS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚀 SETUP QUESTIONS

Q: How do I invite the bot to my server?
A: Click the invite link in #welcome, select your server, authorize.

Q: What permissions does the bot need?
A: Administrator is recommended. Minimum: Manage Channels, Manage Roles, Send Messages, Embed Links.

Q: Can I use the bot without the remote agent?
A: Yes! Direct RCON works for any ARK server. Remote Agent is optional for self-hosted servers needing start/stop/mod control.

Q: Does it work with Nitrado/G-Portal?
A: Yes! Configure RCON in your hosting panel, add server via `/setup`. Remote Agent is not needed for hosted servers.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎮 SERVER QUESTIONS

Q: How many servers can I add?
A: Free tier: 2 servers max. Premium/Lifetime: Unlimited.

Q: Can the bot control multiple ARK servers?
A: Yes, add unlimited servers and control them all from one Discord server.

Q: Does chat relay work across servers?
A: Yes! Enable chat relay in setup. Messages sync between Discord and all your ARK servers.

Q: How do I update my ARK server?
A: Self-hosted: Use `/servermgmt` → Updates panel. Hosted: Use your provider's panel or Remote Agent.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 ECONOMY QUESTIONS (Premium)

Q: How do Phoenix Coins work?
A: Players earn coins via daily payday (automatic). Spend coins in the shop for in-game items delivered via RCON.

Q: How do players link their account?
A: Run `/player` in Discord, click "Link Account", enter their EOS ID from in-game (shown on join).

Q: Can I customize shop items?
A: Yes! Use `/shopcfg` to add, edit, or remove items. Set prices, categories, and ArkCommands.

Q: Can I adjust payday amounts?
A: Yes! Use `/economycfg` to set base payday, role bonuses, and schedule.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤖 REMOTE AGENT QUESTIONS

Q: Do I need the remote agent?
A: Only if you want start/stop, mod management, INI editing, or backups. Not needed for basic RCON monitoring.

Q: Does it work on Linux?
A: Currently Windows only. Linux support is on the roadmap.

Q: Is it secure?
A: Yes. Auth keys are bound to your guild. No arbitrary code execution. All commands are whitelisted.

Q: Can I run multiple agents?
A: Premium/Lifetime: Yes, unlimited. Free: 1 agent max.

Q: What is NSSM and why do I need it?
A: NSSM (Non-Sucking Service Manager) runs your ARK servers as Windows services. Each ARK server needs its own service for the Remote Agent to start/stop it. See #remote-agent-guide for setup instructions.

Q: My server won't start from Discord. What's wrong?
A: Ensure: (1) NSSM service is installed, (2) Service name in Discord matches exactly, (3) Service can start manually via `net start ServiceName`.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💳 BILLING QUESTIONS

Q: How do I upgrade to Premium?
A: Run `/subscription` → "Upgrade to Premium" → Complete Stripe checkout.

Q: Can I pay annually?
A: Currently monthly only. Annual plans coming soon.

Q: What happens if I downgrade?
A: Your tier features lock to Free tier limits. Servers beyond 2 are disabled (not deleted).

Q: What payment methods are accepted?
A: All major credit cards via Stripe. Crypto coming soon.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📧 Still have questions?
Open a ticket: #general-support
```

---

### Category: 🛠️ SUPPORT ZONE

#### `#general-support`
**Purpose**: General help requests
**Permissions**: @everyone can view and send

**Channel Topic**:
```
🎫 Open a ticket for support | 🔍 Search existing tickets first | ⏱️ Response time: 24-48h (Free) / 4h (Premium)
```

**Pinned Message**:
```
🎫 GENERAL SUPPORT

Open a ticket for help with:
• Bot setup and configuration
• Server connection issues
• Feature questions
• Account/billing issues

How to get help:
1. Click the 🎫 ticket button below or type `/ticket` (if available)
2. Describe your issue in detail
3. Wait for staff response

Before opening a ticket:
• Check #faq
• Search for similar issues
• Have your server ID ready

Response times:
• Free tier: 24-48 hours
• Premium/Lifetime: ≤4 hours
```

---

#### `#setup-help`
**Purpose**: Setup-specific assistance
**Permissions**: @everyone can view and send

**Channel Topic**:
```
🔧 Setup assistance | 📖 Read #getting-started first
```

**Pinned Message**:
```
🔧 SETUP HELP

Stuck on setup? Get help here.

Before posting:
• Read #getting-started
• Check #commands-reference
• Verify RCON is enabled on your ARK server

When asking for help, include:
• What step you're on
• Error message (screenshot or paste)
• Your server type (Nitrado, self-hosted, etc.)

Common issues:
• "Connection refused" → Check RCON port and password
• "Bot not responding" → Check bot has Administrator role
• "Setup button doesn't work" → Check bot has Manage Roles permission
```

---

#### `#agent-support`
**Purpose**: Remote agent installation help
**Permissions**: @everyone can view and send

**Channel Topic**:
```
🤖 Remote Agent support | 📖 Read #remote-agent-guide first
```

**Pinned Message**:
```
🤖 REMOTE AGENT SUPPORT

Help with Phoenix ARK Remote Agent.

Before posting:
• Read #remote-agent-guide
• Check Windows Event Viewer for errors
• Verify port 8080 is accessible

Common issues:
• Agent won't start → Check port conflict with `netstat -ano | findstr 8080`
• Bot can't connect → Verify IP and firewall
• Auth key mismatch → Copy/paste from config.json exactly

Provide when asking for help:
• Windows version
• Error messages or logs
• Network setup (same machine / different machine)
```

---

#### `#bug-reports`
**Purpose**: Report bugs
**Permissions**: @everyone can view and send

**Channel Topic**:
```
🐛 Report bugs | 📋 Use template below | 🔍 Search existing reports first
```

**Pinned Message**:
```
🐛 BUG REPORTS

Found a bug? Report it here.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 TEMPLATE (copy and fill out):

**Bot Version**: (check with `/about`)
**Subscription Tier**: Free / Premium / Lifetime
**Discord Server ID**: 
**Description**: What happened?
**Steps to Reproduce**:
1. 
2. 
3. 
**Expected Behavior**: What should have happened?
**Actual Behavior**: What actually happened?
**Screenshots**: (attach if applicable)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before posting:
• Search for existing reports
• Check #server-status for known issues
• Try restarting the bot first

Thanks for helping improve Phoenix ARK Bot!
```

---

#### `#feature-requests`
**Purpose**: Suggest new features
**Permissions**: @everyone can view and send

**Channel Topic**:
```
💡 Suggest features | 👍 React to vote | 📋 Check roadmap first
```

**Pinned Message**:
```
💡 FEATURE REQUESTS

Have an idea? Suggest it here!

How it works:
1. Post your feature idea
2. Community reacts with 👍 to vote
3. High-vote features get prioritized

Before posting:
• Search for similar requests
• Check #announcements for upcoming features

Format:
**Feature**: One-line summary
**Description**: What it does, why it's useful
**Use Case**: How you would use it

Example:
**Feature**: Auto-restart crashed servers
**Description**: Bot detects server crash via RCON failure, auto-restarts after 5 min
**Use Case**: Reduces downtime when I'm asleep

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Top requested features are reviewed weekly.
```

---

### Category: 💎 PREMIUM SUPPORT (Role-gated)

Set category permissions: Only `@Premium`, `@Lifetime`, `@Staff`, `@Owner` can view

#### `#premium-support`
**Purpose**: Priority support for subscribers
**Permissions**: @Premium, @Lifetime, @Staff, @Owner

**Channel Topic**:
```
💎 Premium priority support | ⏱️ Response: ≤4 hours
```

**Pinned Message**:
```
💎 PREMIUM SUPPORT

Thank you for being a Premium/Lifetime subscriber!

You get priority support with guaranteed response within 4 hours.

What's covered:
• Set up and configuration
• Economy and shop setup
• Player management
• Remote agent advanced configuration
• Any feature questions

Just describe your issue and we'll help you out!
```

---

#### `#early-access`
**Purpose**: Beta features and feedback
**Permissions**: @Lifetime, @Staff, @Owner

**Channel Topic**:
```
🧪 Beta features | 💬 Feedback wanted
```

**Pinned Message**:
```
🧪 EARLY ACCESS

Lifetime members get early access to new features before public release.

Current beta features:
(None yet — check back soon!)

How to test:
1. Try the feature
2. Report bugs in #bug-reports
3. Give feedback here

Your input shapes the bot's development!
```

---

### Category: 🎮 COMMUNITY

#### `#showcase`
**Purpose**: Share server setups
**Permissions**: @everyone can view and send

**Channel Topic**:
```
🎮 Show off your server setup | 📸 Screenshots welcome
```

**Pinned Message**:
```
🎮 SHOWCASE YOUR SERVER

Share your Phoenix ARK Bot setup!

What to post:
• Screenshots of your configuration
• Your server list
• Custom shop items
• Economy settings
• Creative uses of the bot

Inspire others with your setup!
```

---

#### `#general-chat`
**Purpose**: Off-topic chat
**Permissions**: @everyone can view and send

**Channel Topic**:
```
💬 General chat | Keep it friendly | #rules apply
```

---

#### `#bot-suggestions`
**Purpose**: General suggestions (not specific features)
**Permissions**: @everyone can view and send

**Channel Topic**:
```
📝 General suggestions | Specific features → #feature-requests
```

---

### Category: 📊 ADMIN ZONE (Owner-only)

Set category permissions: Only `@Owner`, `@Staff` can view

#### `#admin-alerts`
**Purpose**: Bot notifications (new guild joins)
**Permissions**: @Owner only (bot posts here via webhook)

**Pinned Message**:
```
📊 ADMIN ALERTS

Automated notifications from Phoenix ARK Bot:
• New guild joins
• Subscription events
• Critical errors
• System alerts

Keep this channel clean for automated messages.
```

---

#### `#staff-chat`
**Purpose**: Internal staff discussions
**Permissions**: @Staff, @Owner

---

#### `#ticket-transcripts`
**Purpose**: Closed ticket archives
**Permissions**: @Staff, @Owner

---

## Step 4: Configure Ticket System

### Option A: Discord Native (Forum Channels)

1. Create category: 🎫 TICKETS
2. Create forum channel: `#support-tickets`
3. Configure:
   - Tags: Setup, Bug, Billing, Agent, Feature
   - Guidelines: "Create a post for your issue, select a tag"
   - Slow mode: 5 seconds

### Option B: Bot-based Ticket (Recommended)

Use a ticket bot like:
- [Ticket Tool](https://tickettool.xyz/)
- [TicketsBot](https://ticketsbot.net/)
- Or build your own into Phoenix ARK Bot

---

## Step 5: Final Configuration

### Channel Order (Drag to reorder)
```
📌 LANDING ZONE
  #welcome
  #rules
  #announcements
  #server-status

📚 INFORMATION HUB
  #getting-started
  #commands-reference
  #remote-agent-guide
  #pricing-tiers
  #faq

🛠️ SUPPORT ZONE
  #general-support
  #setup-help
  #agent-support
  #bug-reports
  #feature-requests

💎 PREMIUM SUPPORT (locked)
  #premium-support
  #early-access

🎮 COMMUNITY
  #showcase
  #general-chat
  #bot-suggestions

📊 ADMIN ZONE (locked)
  #admin-alerts
  #staff-chat
  #ticket-transcripts
```

### Webhook Setup

In `#admin-alerts`:
1. Server Settings → Integrations → Webhooks
2. Create webhook
3. Copy webhook URL
4. Add to bot's `.env`: `OWNER_ALERT_WEBHOOK_URL=...`
5. Bot will auto-post new guild joins

---

## Step 6: Pre-Launch Checklist

- [ ] All channels created
- [ ] All roles created with correct permissions
- [ ] All pinned messages posted
- [ ] Category permissions set
- [ ] Channel order organized
- [ ] Ticket system configured
- [ ] Webhook set up for #admin-alerts
- [ ] Bot links updated in #welcome
- [ ] Server icon uploaded
- [ ] Rules channel locked (no @everyone send)
- [ ] Announcements locked (staff only)
- [ ] Support server invite added to bot's Discord application
- [ ] Test ticket flow

---

## Maintenance

### Weekly
- Review #feature-requests for top ideas
- Check #bug-reports for patterns
- Update #faq with new questions

### Per Release
- Post changelog to #announcements
- Update #commands-reference if new commands added
- Update #server-status if downtime planned

---

**Document Version**: 1.0
**Last Updated**: 2026-03-03
