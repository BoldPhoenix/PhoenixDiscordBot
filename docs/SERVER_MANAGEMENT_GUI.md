# Server Management GUI - User Guide

## Overview

The **Server Management GUI** provides admins with an interactive, user-friendly interface for managing ARK servers through Discord. No more typing complex commands - just click buttons and fill out simple forms!

## Accessing the GUI

Use the slash command:
```
/servermanager
```

**Requirements:**
- Administrator permissions in Discord OR configured admin role
- The bot must have access to your ARK servers via RCON

## How It Works

### 1. Main Panel

When you open the server management GUI, you'll see:

```
🎮 ARK Server Management Panel

Quick Guide:
1️⃣ Select a server from the dropdown below
2️⃣ Choose an action category
3️⃣ Fill out the simple form
4️⃣ Confirm and execute!

👥 Player Management    🖥️ Server Control    🎁 Rewards & Items    🔧 Advanced
```

### 2. Select a Server

Click the dropdown menu and choose which ARK server you want to manage:
- Shows server name, map, and host
- All configured servers appear in the list

### 3. Choose a Category

Four action categories are available:

#### 👥 Player Management
- **List Online Players** - See who's currently playing
- **Kick Player** - Remove a player temporarily
- **Ban Player** - Permanently ban a player
- **Unban Player** - Remove a player from the ban list
- **Whitelist Player** - Add a player to the whitelist

#### 🖥️ Server Control
- **Broadcast Message** - Send a message to all players
- **Save World** - Manually save the world
- **Destroy Wild Dinos** - Wipe all wild dinosaurs
- **Set MOTD** - Update the message of the day

#### 🎁 Rewards & Items
- **Give Item** - Grant items to players
- **Give Dino** - Spawn and give a tamed dino
- **Give XP** - Award experience points

#### 🔧 Advanced Tools
- **Custom RCON** - Execute any RCON command
- **Get Chat Log** - View recent in-game chat
- **Teleport Player** - Move a player to coordinates

### 4. Fill the Form

When you click an action button, a form will pop up asking for the necessary information.

**Example - Kicking a Player:**
```
Player Name: JohnDoe
Reason (optional): AFK too long
```

**Example - Giving an Item:**
```
Player ID: Steam_12345 or CharacterName
Item Blueprint: PrimalItemResource_Metal_C
Quantity: 500
Quality: 1
```

### 5. Execute & Confirm

- Click "Submit" on the form
- The action executes immediately
- You receive a detailed response showing:
  - Server name
  - Action performed
  - Parameters used
  - RCON response
  - Your name (for logging)

## Action Examples

### Kicking a Player
1. Click 👥 Player Management
2. Click "🚪 Kick Player"
3. Fill in:
   - Player Name: `ToxicPlayer123`
   - Reason: `Griefing`
4. Submit
5. Player is immediately kicked

### Broadcasting a Message
1. Click 🖥️ Server Control
2. Click "📢 Broadcast Message"
3. Fill in:
   - Message: `Server restart in 10 minutes!`
4. Submit
5. All players see the message in chat

### Giving Items
1. Click 🎁 Rewards & Items
2. Click "📦 Give Item"
3. Fill in:
   - Player ID: `PlayerName` or Steam ID
   - Item Blueprint: `PrimalItemResource_Metal_C`
   - Quantity: `1000`
   - Quality: `1`
4. Submit
5. Player receives 1000 metal ingots

### Spawning a Dino
1. Click 🎁 Rewards & Items
2. Click "🦖 Give Dino"
3. Fill in:
   - Player ID: `PlayerName`
   - Dino Type: `Rex_Character_BP_C`
   - Level: `150`
4. Submit
5. Player receives a tamed level 150 Rex

## Common Item & Dino IDs

### Popular Items
```
Metal Ingots:     PrimalItemResource_Metal_C
Polymer:          PrimalItemResource_Polymer_C
Element:          PrimalItemResource_Element_C
Crystal:          PrimalItemResource_Crystal_C
Simple Rifle:     WeaponRifle_C
Flak Armor Set:   PrimalItemArmor_Flak*
```

### Popular Dinos
```
Rex:              Rex_Character_BP_C
Argentavis:       Argent_Character_BP_C
Ankylosaurus:     Ankylo_Character_BP_C
Giganotosaurus:   Gigant_Character_BP_C
Wyvern (Ice):     Wyvern_Character_BP_Ice_C
```

For complete lists, see `RCON_ADMIN_COMMANDS.md`.

## Benefits of the GUI

### ✅ No Typing
- No need to remember command syntax
- No typos in complex commands
- No memorizing blueprint IDs (just copy/paste)

### ✅ User-Friendly Forms
- Clear labels for each field
- Placeholders showing examples
- Optional fields clearly marked
- Validation before submission

### ✅ Immediate Feedback
- See exactly what was executed
- View server responses
- All actions are logged
- Error messages are helpful

### ✅ Safe & Organized
- Admin permissions required
- Actions organized by category
- Easy to find what you need
- Can't accidentally run wrong command

### ✅ Mobile-Friendly
- Works on Discord mobile app
- Tap to select, tap to fill
- No keyboard command typing needed
- Forms adapt to screen size

## Comparison: Commands vs GUI

### Traditional Command Method:
```
/giveitem server:Aberration player:JohnDoe item:PrimalItemResource_Metal_C qty:500 quality:1
```
- Long command to type
- Easy to make typos
- Have to remember all parameters
- Order matters

### GUI Method:
1. Tap `/servermanager`
2. Select "Aberration" from dropdown
3. Tap 🎁 Rewards & Items
4. Tap "📦 Give Item"
5. Fill simple form:
   - Player: `JohnDoe`
   - Item: `PrimalItemResource_Metal_C`
   - Quantity: `500`
   - Quality: `1`
6. Tap Submit
7. Done!

## Tips & Best Practices

### 🎯 Quick Access
- The GUI is ephemeral (only you can see it)
- Open multiple panels if needed
- Each panel times out after 5 minutes
- Just run `/servermanager` again to reopen

### 🎯 Batch Operations
- For multiple actions on the same server, keep the panel open
- Server selection persists across actions
- No need to reselect the server each time

### 🎯 Common Actions
Bookmark these in your mind:
- Quick player check: List Online Players
- Emergency broadcast: Broadcast Message
- Reward good behavior: Give Item/XP
- Handle griefers: Kick/Ban Player

### 🎯 Learning Curve
- First time: Explore all categories
- Practice on a test server
- Keep item/dino ID lists handy
- Custom RCON is for advanced users

## Troubleshooting

### Panel won't open
- Check you have Administrator permission
- Ensure bot has admin role configured
- Verify RCON access to servers

### Server not in dropdown
- Server must be configured in database or .env
- Check RCON port and password are correct
- Verify server is running

### Action fails
- Check RCON connection
- Verify player name/ID is correct
- Blueprint IDs are case-sensitive
- Check server logs for errors

### Form won't submit
- All required fields must be filled
- Check value formats (numbers, IDs)
- Some actions need specific permissions

## Security

- All actions require admin permissions
- Each action shows who executed it
- Actions are logged in admin channel (if configured)
- Panel is private (ephemeral) - only you can see it
- Timeout after 5 minutes of inactivity

## Integration with Help System

The updated `/help` command now includes all RCON admin commands:

```
/help
```

Navigate to the "🎮 RCON Admin" category to see:
- All 15 RCON commands
- Parameters for each command
- What each command does

Both the GUI and traditional slash commands work together:
- Use GUI for most actions (easier)
- Use commands for automation/scripting
- Same functionality, different interface

## Next Steps

1. **Try it out**: Run `/servermanager` and explore
2. **Set up admin role**: Configure who can use these tools
3. **Enable logging**: Set an admin log channel
4. **Train your team**: Share this guide with co-admins
5. **Provide feedback**: Report bugs or suggest improvements

## Support

- See `RCON_ADMIN_COMMANDS.md` for detailed command reference
- See `ADMIN_QUICK_REFERENCE.md` for quick command syntax
- See `INTEGRATION_GUIDE.md` for setup instructions

---

**Happy managing! 🎮🦖**

Remember: With great power comes great responsibility. Use these tools wisely to create an amazing experience for your players!
