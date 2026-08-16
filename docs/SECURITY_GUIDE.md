# Security Guide for ARK Discord Bot

## Critical Security Considerations

This guide outlines security best practices for deploying the ARK Discord Bot safely in your own environment.

---

## 1. Environment Variables & Secrets

### ⚠️ NEVER commit sensitive data to Git!

**Protected Files** (already in `.gitignore`):
- `.env` - Your actual configuration
- `.env.*` - Any environment file variants
- `.env.backup*` - Backup files with credentials
- `*.db` - Database files with server passwords
- `.pypirc` - PyPI credentials

**Safe Files** (can be committed):
- `.env.example` - Template with placeholder values
- `.env.template` - Alternative template format

### Environment Variables to Protect:

```bash
DISCORD_BOT_TOKEN=          # Your Discord bot token
DISCORD_GUILD_ID=           # Your Discord server ID (less sensitive)
ARK_SERVERS=                # Contains RCON passwords!
```

### Best Practices:

1. **Never share your `.env` file**
2. **Use strong RCON passwords** (minimum 12 characters, mixed case, numbers, symbols)
3. **Regenerate Discord bot token** if it's ever exposed
4. **Use different RCON passwords** for each server if possible
5. **Backup `.env` to secure location ONLY** (not in git repo)

---

## 2. Discord Permissions & Admin Controls

### Admin Command Protection

All sensitive commands are protected by the `is_admin()` check which verifies:

1. **Discord Administrator Permission** - Built-in Discord admin
2. **Configured Admin Role** - Custom role set via `/setadminrole`

### Protected Commands:

**Setup Commands** (`/setup`, `/addserver`, `/removeserver`, `/editserver`):
- Can configure server connections
- Can set RCON credentials
- Can modify bot behavior

**Admin Commands** (`/broadcast`, `/saveworld`, `/destroywilddinos`):
- Direct server control via RCON
- Can affect gameplay
- Can disrupt players

**Bot Control** (`/restart`, `/shutdown`, `/reload`):
- Can stop the bot
- Can reload cogs
- Can affect service availability

**Store/Kit Management**:
- Can modify shop items
- Can adjust prices
- Can give items/currency to players

### Setting Up Admin Role:

```
1. Create a Discord role (e.g., "ARK Admin")
2. Use command: /setadminrole @RoleName
3. Only users with Administrator permission OR this role can use admin commands
```

---

## 3. RCON Security

### What is RCON?

RCON (Remote Console) allows the bot to control your ARK servers. **Anyone with RCON access can:**
- Execute any admin command
- Kick/ban players
- Destroy structures
- Modify server settings
- Access server console

### RCON Password Security:

✅ **DO:**
- Use strong, unique passwords for each server
- Change RCON passwords if compromised
- Restrict RCON port access via firewall
- Only allow RCON connections from trusted IPs

❌ **DON'T:**
- Use simple passwords (e.g., "admin123")
- Reuse passwords across multiple servers
- Share RCON passwords with untrusted users
- Expose RCON ports to the public internet

### RCON Password Storage:

Passwords are stored:
1. **Encrypted in SQLite database** (`data/bot_database.db`)
2. **In memory** during bot runtime
3. **Masked in Discord** (shows as `●●●●●●●●●●●●`)

### Accessing the Database:

The bot's database contains:
- RCON passwords (encrypted)
- Server configurations
- Player data
- Shop items

**Secure your database file!** It should only be readable by:
- The bot service account
- Server administrators
- Backup systems (encrypted backups)

---

## 4. Network Security

### Port Exposure:

The bot requires access to:

| Port Type | Purpose | Exposure Level |
|-----------|---------|----------------|
| **Game Port** (7802-7818) | Player connections | ✅ Public (Required) |
| **Query Port** (7803-7819) | Server status queries | ✅ Public (Required) |
| **RCON Port** (27002-27067) | Admin console | ⚠️ **RESTRICTED ONLY** |

### Firewall Rules:

**CRITICAL:** RCON ports should **NEVER** be publicly accessible!

**Recommended Configuration:**

```
Game Ports (7802-7818):     Allow from 0.0.0.0/0 (Everyone)
Query Ports (7803-7819):    Allow from 0.0.0.0/0 (Everyone)
RCON Ports (27002-27067):   Allow from:
                            - 127.0.0.1 (localhost)
                            - Your bot server IP only
                            - Trusted admin IPs (optional)
```

**Example Windows Firewall Rule (PowerShell):**

```powershell
# Block RCON from public (if accidentally opened)
New-NetFirewallRule -DisplayName "Block ARK RCON Public" `
    -Direction Inbound `
    -LocalPort 27002-27067 `
    -Protocol TCP `
    -Action Block `
    -Profile Public

# Allow RCON from localhost only
New-NetFirewallRule -DisplayName "Allow ARK RCON Localhost" `
    -Direction Inbound `
    -LocalPort 27002-27067 `
    -Protocol TCP `
    -Action Allow `
    -RemoteAddress 127.0.0.1
```

---

## 5. Bot Token Security

### Discord Bot Token:

Your `DISCORD_BOT_TOKEN` is like a password for your bot. **Anyone with this token can:**
- Control your bot
- Read all messages in channels the bot can see
- Execute commands as the bot
- Impersonate the bot

### If Your Token is Compromised:

1. **Immediately regenerate the token** on Discord Developer Portal
2. Update your `.env` file with new token
3. Restart the bot
4. Review bot activity logs for unauthorized actions
5. Check Discord server audit logs

**To regenerate:**
1. Go to https://discord.com/developers/applications
2. Select your application
3. Go to "Bot" section
4. Click "Reset Token"
5. Copy new token to `.env`

---

## 6. Database Security

### Location:
`data/bot_database.db`

### Contains:
- Server configurations (with RCON passwords)
- Player data (Steam IDs, character names, levels)
- Tribe information
- Shop items and prices
- User currency balances
- Admin role configurations

### Protection:

✅ **DO:**
- Set file permissions to owner-only (chmod 600 on Linux)
- Backup database regularly to **secure, encrypted location**
- Keep backups offline or in separate secure system
- Monitor database file access

❌ **DON'T:**
- Commit database to Git
- Store database in publicly accessible directory
- Share database file
- Run bot as root/administrator (use limited service account)

**Linux File Permissions:**
```bash
chmod 600 data/bot_database.db
chown botuser:botuser data/bot_database.db
```

**Windows File Permissions:**
```powershell
icacls data\bot_database.db /inheritance:r /grant "BotServiceAccount:(R,W)"
```

---

## 7. Log File Security

### Log Contents:

Bot logs may contain:
- Server IP addresses
- RCON connection attempts
- Player activity
- Command execution history
- Error messages (potentially with sensitive info)

### Protection:

1. **Review logs before sharing** - Remove sensitive data
2. **Rotate logs regularly** - Delete old logs (keep 30-90 days)
3. **Secure log directory** - Restrict read access
4. **Disable verbose logging** in production (if not needed)

---

## 8. Distribution Security Checklist

### Before sharing your fork or deployment:

- [ ] Remove all `.env` files (except `.env.example`)
- [ ] Verify `.gitignore` excludes sensitive files
- [ ] Check commit history for accidentally committed secrets
- [ ] Remove any hardcoded passwords or tokens
- [ ] Document your security setup in README
- [ ] Include this SECURITY_GUIDE.md
- [ ] Test with fresh clone to ensure no secrets present
- [ ] Review Discord bot permissions (principle of least privilege)

### Git History Check:

```bash
# Search commit history for secrets
git log --all --full-history --source -- .env
git log -p | grep -i "password\|token\|secret"

# If secrets found in history, consider:
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env*" \
  --prune-empty --tag-name-filter cat -- --all
```

**WARNING:** `filter-branch` rewrites history! Coordinate with all contributors.

---

## 9. Discord Bot Permissions

### Required Permissions:

The bot needs these Discord permissions:

**Essential:**
- `Read Messages/View Channels` - See channels
- `Send Messages` - Post messages
- `Embed Links` - Send rich embeds
- `Read Message History` - Context for commands
- `Use Slash Commands` - Slash command interface

**For Voice Channel Status:**
- `Manage Channels` - Update voice channel names
- `Connect` - Access voice channels (read-only)

**For Chat Relay:**
- `Read Messages` - Monitor chat channel
- `Send Messages` - Relay ARK chat

### Permission Security:

✅ **DO:**
- Grant only required permissions
- Use channel-specific permissions if needed
- Review permissions quarterly
- Test with minimal permissions first

❌ **DON'T:**
- Grant `Administrator` permission (unnecessary)
- Grant `Manage Server` unless specifically needed
- Grant `Mention Everyone` (can be abused)
- Grant `Manage Messages/Roles` unless necessary

---

## 10. Deployment Security

### Service Account:

**Linux (systemd):**
```bash
# Create dedicated user
sudo useradd -r -s /bin/false arkbot

# Set ownership
sudo chown -R arkbot:arkbot /opt/arkdiscordbot

# Run as service
sudo systemctl start arkbot
```

**Windows (NSSM):**
```powershell
# Run as specific user (not Administrator)
nssm set ArkDiscordBot ObjectName ".\ArkBotUser" "password"
```

### Process Isolation:

1. **Run bot with minimal privileges**
2. **Use service account** (not admin/root)
3. **Restrict file system access**
4. **Use read-only mounts** where possible

---

## 11. Update Security

### Keeping Secure:

1. **Update dependencies regularly:**
   ```bash
   pip install --upgrade -r requirements.txt
   ```

2. **Monitor security advisories** for:
   - discord.py
   - aiosqlite
   - Other dependencies

3. **Review changelogs** before updating

4. **Test updates** in staging environment first

### Vulnerability Reporting:

If you discover a security vulnerability:

1. **DO NOT** create a public GitHub issue
2. Contact maintainer privately
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

---

## 12. Monitoring & Auditing

### What to Monitor:

- **Failed RCON login attempts** - Potential brute force
- **Unusual command activity** - Compromised admin accounts
- **Bot restarts** - Crashes or unauthorized restarts
- **Permission changes** - Role modifications
- **Database access** - File read/write activity

### Audit Logs:

Review bot logs regularly:
```bash
tail -f logs/bot.log
grep -i "error\|failed\|unauthorized" logs/bot.log
```

Review Discord audit logs:
1. Discord Server → Settings → Audit Log
2. Filter by bot actions
3. Look for unexpected activity

---

## 13. Incident Response

### If Security Incident Occurs:

1. **Immediate Actions:**
   - Stop the bot service
   - Change all passwords (RCON, bot token)
   - Review logs for extent of compromise
   - Backup current state for forensics

2. **Assessment:**
   - What was accessed?
   - What was modified?
   - How did breach occur?
   - Who was affected?

3. **Recovery:**
   - Restore from clean backup (if needed)
   - Update all credentials
   - Patch vulnerability
   - Restart bot with new credentials

4. **Prevention:**
   - Document incident
   - Update security measures
   - Implement additional controls
   - Train administrators

---

## 14. Security Recommendations Summary

### High Priority:

1. ✅ **Never commit secrets to Git**
2. ✅ **Use strong RCON passwords**
3. ✅ **Restrict RCON ports to localhost/bot IP only**
4. ✅ **Secure bot token** (treat as root password)
5. ✅ **Configure admin role** properly
6. ✅ **Set database file permissions**
7. ✅ **Run bot as service account** (not admin)

### Medium Priority:

8. ✅ **Rotate passwords quarterly**
9. ✅ **Monitor logs regularly**
10. ✅ **Keep dependencies updated**
11. ✅ **Backup database securely**
12. ✅ **Review Discord permissions**

### Low Priority (but still important):

13. ✅ **Enable log rotation**
14. ✅ **Document your security setup**
15. ✅ **Test disaster recovery**
16. ✅ **Audit admin accounts**

---

## 15. Quick Security Checklist

Use this checklist when deploying the bot:

```
Initial Setup:
[ ] Copy .env.example to .env
[ ] Set strong RCON passwords
[ ] Set Discord bot token
[ ] Verify .gitignore excludes .env
[ ] Create dedicated service account
[ ] Set database file permissions

Network Security:
[ ] Configure firewall rules
[ ] Block RCON ports from public
[ ] Allow only localhost RCON access
[ ] Open game/query ports only

Discord Configuration:
[ ] Grant minimal bot permissions
[ ] Set up admin role
[ ] Test admin command restrictions
[ ] Review channel access

Monitoring:
[ ] Enable logging
[ ] Set up log rotation
[ ] Test log access
[ ] Document admin contacts

Maintenance:
[ ] Schedule regular updates
[ ] Plan backup strategy
[ ] Document recovery procedures
[ ] Test incident response
```

---

## Support & Questions

If you have security questions or concerns:

1. Review this guide thoroughly
2. Check Discord bot best practices
3. Consult ARK server security guides
4. Reach out to community (without exposing secrets!)

**Remember:** Security is a continuous process, not a one-time setup!

---

**Last Updated:** December 2, 2025  
**Version:** 1.0
