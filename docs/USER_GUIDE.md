# ARK Discord Bot - User Guide

## Quick Start (For Discord Server Admins)

### What is This Bot?

This bot connects your ARK: Survival Ascended servers to Discord, providing:
- 🎮 Server status monitoring
- 💬 In-game chat relay
- 👥 Player tracking
- 📊 Server statistics
- 🛠️ Admin commands via Discord

### Step 1: Invite the Bot

1. Click the invite link provided by the bot administrator
2. Select your Discord server
3. Authorize the required permissions
4. The bot will join your server!

### Step 2: Initial Setup

Run these commands in Discord:

```
/setadminrole @YourAdminRole
```
This sets which role can configure the bot.

```
/setchannels
```
This opens a menu to configure:
- **Chat Channel** - Where ARK chat messages appear
- **Status Channel** - Where server status is posted

### Step 3: Add Your ARK Server

```
/addserver 
  name: "My Server" 
  host: "192.168.1.100" 
  game_port: 7777
  query_port: 27015
  rcon_port: 27020 
  rcon_password: "your_rcon_password"
```

**Replace with your server's actual details!**

### Step 4: Test Connection

```
/testconnection
```

If successful, you're done! 🎉

---

## Common Commands

### For All Users:

- `/help` - Show all available commands
- `/serverstatus` - Check server status
- `/listservers` - View configured servers
- `/serverinfo` - Detailed server information

### For Admins Only:

- `/broadcast message:"Hello!"` - Send message to ARK server
- `/saveworld` - Save the ARK world
- `/listplayers` - Show online players
- `/destroywilddinos` - Wipe wild dinos

---

## Requirements

### Your Discord Server Needs:
- Admin access to invite the bot
- Channels for chat relay and status

### Your ARK Server Needs:
- RCON enabled
- RCON password configured
- Accessible from the bot's server

---

## ARK Server Configuration

### Enable RCON

Edit your `GameUserSettings.ini`:

```ini
[ServerSettings]
ServerAdminPassword=YourRCONPassword
RCONEnabled=True
RCONPort=27020
```

### Firewall Rules

**For the bot to connect, allow:**
- RCON Port (e.g., 27020) from the bot's IP address

**For players to connect, allow:**
- Game Port (e.g., 7777) from anywhere
- Query Port (e.g., 27015) from anywhere

⚠️ **NEVER** expose RCON port to the public internet!

---

## Troubleshooting

### Bot Shows as Offline
- Contact the bot administrator
- Bot may be restarting or updating

### Can't Use Commands
- Check you have the configured admin role
- Verify bot has proper Discord permissions
- Make sure you're using slash commands (`/command`)

### Bot Can't Connect to ARK Server
- Verify RCON password is correct: `/testconnection`
- Check firewall allows bot IP to RCON port
- Ensure ARK server is running
- Confirm RCON is enabled in GameUserSettings.ini

### Chat Relay Not Working
- Check chat channel is configured: `/setchannels`
- Verify bot has permissions in the chat channel
- Ensure ARK server log path is correct

---

## FAQ

**Q: Do I need to install anything?**  
A: No! The bot is hosted by the administrator. Just invite it to your Discord.

**Q: Can multiple Discord servers use the same bot?**  
A: Yes! Each Discord server has isolated configuration.

**Q: How many ARK servers can I connect?**  
A: Unlimited! Add as many as you want with `/addserver`.

**Q: Is my RCON password secure?**  
A: Yes, it's encrypted in the bot's database and never displayed in Discord.

**Q: Can other Discord members see my RCON password?**  
A: No, it's only visible to you when configuring and is masked as `●●●●●●●●●●●●`.

**Q: What if I want to remove the bot?**  
A: Just kick it from your Discord server. Your data remains in the bot's database if you want to re-invite later.

---

## Support

Need help? Contact the bot administrator or join the support server (link provided by admin).

---

## Privacy

The bot stores:
- Your Discord server ID
- Configured channels
- ARK server details (IP, ports, RCON password)
- Player data from ARK servers
- Admin role configuration

This data is:
- ✅ Isolated per Discord server
- ✅ Encrypted when sensitive
- ✅ Only accessible by the bot
- ✅ Not shared with other Discord servers

---

## Updates

The bot is updated automatically by the administrator. You'll never need to do anything!

If the bot restarts, your configuration persists.

---

**Enjoy your ARK Discord integration!** 🚀🦖
