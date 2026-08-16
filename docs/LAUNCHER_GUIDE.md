# Secure Launcher System

## Overview

The ARK Discord Bot now uses a secure launcher system that **never stores credentials in startup scripts**. All sensitive data is loaded from the `.env` file, which is:

- ✅ Excluded from Git (in `.gitignore`)
- ✅ Encrypted at rest (if using disk encryption)
- ✅ User-specific (each deployment has its own)
- ✅ Easy to update without modifying code

## Why Not an EXE?

You might think converting to an EXE would "hide" credentials, but:

❌ **EXEs can be decompiled** - Tools like `pyinstaller-extractor` and `uncompyle6` can extract Python code from EXEs  
❌ **Environment variables visible** - Even if embedded, they appear in process memory  
❌ **False security** - Gives impression of security without actual protection  
❌ **Platform-specific** - Requires separate builds for Windows/Linux  
❌ **Harder to update** - Users must download new EXE for any change  

✅ **Better approach:** Use `.env` file with proper file permissions

---

## Launcher Files

### For Users (Distributable):

1. **`start.bat`** - Windows launcher (double-click to start)
2. **`start.sh`** - Linux/Mac launcher (make executable: `chmod +x start.sh`)
3. **`launcher.py`** - Python launcher (used by both scripts above)

### For Developers:

4. **`start_bot.bat`** - Development launcher with pause
5. **`start_bot.cmd`** - Production launcher (no pause)

### Legacy (Deprecated):

- Old `start_bot.cmd` had hardcoded token ❌
- Now loads from `.env` instead ✅

---

## Quick Start

### Windows:

1. Create `.env` file (copy from `.env.example`)
2. Add your Discord bot token to `.env`
3. Double-click `start.bat`

### Linux/Mac:

```bash
# 1. Create .env file
cp .env.example .env

# 2. Edit .env and add your token
nano .env

# 3. Make launcher executable
chmod +x start.sh

# 4. Run
./start.sh
```

---

## How It Works

```
┌──────────────┐
│  start.bat   │  (User double-clicks)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ launcher.py  │  (Checks for .env, validates setup)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   main.py    │  (Loads .env with load_dotenv())
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Bot starts  │  (Credentials from .env)
└──────────────┘
```

### Security Flow:

1. **Launcher checks** if `.env` exists
2. **If missing** → Shows helpful error and exits
3. **If exists** → Launches `main.py`
4. **main.py** loads `.env` using `python-dotenv`
5. **Credentials** loaded into memory only
6. **Never stored** in scripts or code

---

## File Permissions (Important!)

### Windows:

```powershell
# Restrict .env to current user only
icacls .env /inheritance:r
icacls .env /grant:r "$env:USERNAME:(R,W)"
```

### Linux/Mac:

```bash
# Make .env readable only by owner
chmod 600 .env
chown $USER:$USER .env
```

### Why This Matters:

- Prevents other users on the system from reading your token
- Prevents accidental exposure if directory is shared
- Industry standard for sensitive configuration files

---

## Deployment Options

### Option 1: Simple Deployment (Development/Testing)

Just run the launcher:
```bash
# Windows
start.bat

# Linux/Mac
./start.sh
```

### Option 2: Service Deployment (Production)

#### Windows (NSSM):

```powershell
# Install NSSM service
nssm install ArkDiscordBot "C:\Path\To\Python\python.exe" "C:\Path\To\Bot\launcher.py"

# Set working directory
nssm set ArkDiscordBot AppDirectory "C:\Path\To\Bot"

# Service will automatically load .env from working directory
nssm start ArkDiscordBot
```

#### Linux (systemd):

```ini
# /etc/systemd/system/arkbot.service
[Unit]
Description=ARK Discord Bot
After=network.target

[Service]
Type=simple
User=arkbot
WorkingDirectory=/opt/arkdiscordbot
ExecStart=/usr/bin/python3 /opt/arkdiscordbot/launcher.py
Restart=always
RestartSec=10

# .env file is loaded automatically from WorkingDirectory
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl enable arkbot
sudo systemctl start arkbot

# Check status
sudo systemctl status arkbot
```

### Option 3: Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# .env will be mounted as volume or passed as secrets
CMD ["python", "launcher.py"]
```

```yaml
# docker-compose.yml
version: '3'
services:
  arkbot:
    build: .
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env:ro  # Mount .env as read-only
    restart: unless-stopped
```

---

## Updating Credentials

### To Change Bot Token:

```bash
# 1. Stop the bot
# Windows: Ctrl+C or close window
# Service: nssm stop ArkDiscordBot (or systemctl stop arkbot)

# 2. Edit .env
# Windows: notepad .env
# Linux: nano .env

# 3. Change DISCORD_BOT_TOKEN line
DISCORD_BOT_TOKEN=NEW_TOKEN_HERE

# 4. Save and restart bot
```

### To Change RCON Passwords:

RCON passwords are stored in the **database**, not `.env`:

```bash
# Use Discord command:
/editserver servername
# Then update the RCON password field in the modal
```

---

## Troubleshooting

### Error: ".env file not found"

**Solution:** Create `.env` from template:
```bash
cp .env.example .env
# Edit .env and add your credentials
```

### Error: "DISCORD_BOT_TOKEN not found in environment variables"

**Solution:** Check `.env` file has the token:
```env
DISCORD_BOT_TOKEN=your_actual_token_here
```

### Error: "Python is not installed"

**Solution:** Install Python 3.8+:
- Windows: https://www.python.org/downloads/
- Linux: `sudo apt install python3`
- Mac: `brew install python3`

### Bot starts but immediately stops

**Check logs** in `logs/bot.log`:
```bash
tail -f logs/bot.log
```

Common causes:
- Invalid bot token
- Missing permissions
- Database corruption
- Port conflicts

---

## Security Best Practices

### DO:

✅ Use separate `.env` file for each deployment  
✅ Set restrictive file permissions (600 on Linux, NTFS ACLs on Windows)  
✅ Include `.env` in `.gitignore`  
✅ Use strong, unique bot tokens  
✅ Regenerate token if exposed  
✅ Keep `.env` in encrypted directory (if possible)  
✅ Backup `.env` to secure location  

### DON'T:

❌ Hardcode credentials in scripts  
❌ Commit `.env` to Git  
❌ Share `.env` file with others  
❌ Use same token in multiple deployments  
❌ Store `.env` in publicly accessible directory  
❌ Include credentials in error messages or logs  

---

## Migration from Old System

If you're upgrading from the old system (with hardcoded credentials):

### Step 1: Create .env file

```bash
# Copy example
cp .env.example .env
```

### Step 2: Extract credentials from old start_bot.cmd

```bash
# Old start_bot.cmd had:
# set "DISCORD_BOT_TOKEN=..."
# set "DISCORD_GUILD_ID=..."

# Add these to .env:
DISCORD_BOT_TOKEN=your_token_here
DISCORD_GUILD_ID=your_guild_id_here
```

### Step 3: Use new launcher

```bash
# Instead of:
start_bot.cmd

# Use:
start.bat  (or ./start.sh on Linux)
```

### Step 4: Update service (if using NSSM)

```powershell
# Update application path
nssm set ArkDiscordBot Application "C:\Path\To\Python\python.exe"
nssm set ArkDiscordBot AppParameters "C:\Path\To\Bot\launcher.py"

# Remove old environment variables (if set)
nssm set ArkDiscordBot AppEnvironmentExtra ""

# Restart
nssm restart ArkDiscordBot
```

---

## Distribution Checklist

When sharing your bot, ensure:

- [ ] No `.env` file in distribution (only `.env.example`)
- [ ] `start.bat` and `start.sh` included
- [ ] `launcher.py` included
- [ ] `.gitignore` excludes `.env`
- [ ] README includes setup instructions
- [ ] SECURITY_GUIDE.md included
- [ ] No credentials in any script files
- [ ] No credentials in Git history

---

## Advanced: Environment Variable Priority

The bot loads configuration in this order (later overrides earlier):

1. **Default values** in `bot/utils/config.py`
2. **`.env` file** in working directory
3. **System environment variables** (if set)
4. **Service environment** (if running as service)

This allows flexibility:
- Development: Use `.env` file
- Docker: Use environment variables
- Service: Use service configuration

---

## FAQ

**Q: Can I still use the old start_bot.cmd?**  
A: Yes, but it now loads from `.env` instead of having hardcoded credentials.

**Q: Why do I need launcher.py?**  
A: It provides helpful error messages, validates setup, and ensures proper working directory.

**Q: Can I run main.py directly?**  
A: Yes: `python main.py` works if `.env` is in the same directory.

**Q: Does this work with virtual environments?**  
A: Yes! The launchers automatically activate/deactivate venv if present.

**Q: What if I want to use system environment variables instead?**  
A: The bot checks environment first, then `.env`. Set `DISCORD_BOT_TOKEN` in your system environment.

**Q: Is this more secure than an EXE?**  
A: Yes! EXEs can be decompiled. File permissions on `.env` provide real security.

---

## Summary

The new launcher system:

- ✅ **Never stores credentials** in scripts
- ✅ **Cross-platform** (Windows, Linux, Mac)
- ✅ **User-friendly** with helpful error messages
- ✅ **Service-compatible** with NSSM, systemd, Docker
- ✅ **Secure by default** using `.env` with proper permissions
- ✅ **Easy to distribute** without exposing credentials
- ✅ **Simple to update** credentials without code changes

**For more security information, see [SECURITY_GUIDE.md](SECURITY_GUIDE.md)**

---

**Last Updated:** December 2, 2025  
**Version:** 2.0 (Secure Launcher System)
