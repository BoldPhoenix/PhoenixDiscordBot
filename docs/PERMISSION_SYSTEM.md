# Permission System

## Overview

Phoenix ArkBot implements a two-tier permission system for controlling access to features:

1. **Admin Role** - For bot management and server administration
2. **User Role** - For verified users who can access bot features

## Role Types

### Admin Role (👑)
**Purpose**: Bot management and server administration

**Permissions**:
- Add/edit/remove ARK servers (`/servermgmt`)
- Manage players and economy (`/playermgmt`)
- Create and manage kits (`/kitsmgmt`)
- Execute RCON commands (kick, ban, broadcast, etc.)
- Control server services (start, stop, restart)
- Manage shop items and prices
- Grant coins to players
- Configure bot settings (`/setupcfg`)

**Who Should Have It**: Server owners, administrators, moderators

**Set Via**: `/setupcfg` → Admin Role

---

### User Role (👤)
**Purpose**: Access control for verified/trusted community members

**Permissions**:
- Link Discord account to ARK character (`/linkplayer`)
- Claim starter kits (`/kit`)
- Use the shop and purchase items
- View server status and player lists
- Check their linked account (`/mylink`)

**Who Should Have It**: Verified community members, players who have been vetted

**Set Via**: `/setupcfg` → User Role

**Behavior If Not Set**: All Discord members can access user features (open access)

---

## Permission Hierarchy

```
Everyone
├── View public info (server status, help)
│
└── Has User Role OR Admin Role
    ├── Link account (/linkplayer)
    ├── Claim kits (/kit)
    ├── Use shop
    ├── View personal stats
    │
    └── Has Admin Role
        ├── All user permissions
        ├── Server management
        ├── Player management
        ├── RCON commands
        └── Bot configuration
```

## Implementation Details

### Checking Permissions in Code

The bot uses utility functions from `bot/utils/permissions.py`:

```python
from bot.utils.permissions import require_verified_user, require_admin

# For user commands (kits, shop, linking)
@app_commands.command(name="kit")
async def claim_kit(self, interaction: discord.Interaction):
    if not await require_verified_user(interaction):
        return  # Error message already sent
    # Command logic...

# For admin commands (server management, RCON)
@app_commands.command(name="servermgmt")
async def server_mgmt(self, interaction: discord.Interaction):
    if not await require_admin(interaction):
        return  # Error message already sent
    # Command logic...
```

### Permission Functions

- `is_admin(interaction)` - Returns True if user has admin permissions
- `is_verified_user(interaction)` - Returns True if user has user role or is admin
- `require_admin(interaction)` - Checks admin, sends error if unauthorized
- `require_verified_user(interaction)` - Checks user role, sends error if unauthorized

### Admin Bypass

**Important**: Admin role members automatically pass user role checks. Admins don't need the user role.

---

## Setup Workflow

### Initial Setup (New Server)

1. **Run Setup Wizard**: `/setupcfg`

2. **Set Admin Role**:
   - Click "Admin Role"
   - Select the role for bot administrators
   - This role gets full bot control

3. **Set User Role** (Optional):
   - Click "User Role"
   - Select the role for verified users
   - If skipped, all users can access features

4. **Assign Roles**:
   - Give admin role to moderators/admins
   - Give user role to verified community members
   - Or use "Not Set" for open access

### Recommended Setup

**Small/Private Servers**:
- Set admin role only
- Leave user role unset (open access)
- Everyone can use features

**Large/Public Servers**:
- Set admin role for staff
- Set user role for vetted members
- New joins can't spam kits/shop until verified
- Prevents abuse from random users

**Gated Community**:
- Require user role for all features
- Manually assign after vetting
- Maximum control

---

## Protected Commands

### User Role Required
- `/linkplayer` - Link Discord to ARK character
- `/kit` - Claim starter kits
- `/mylink` - View linked account
- Shop commands (if implemented)

### Admin Role Required
- `/setupcfg` - Bot configuration
- `/servermgmt` - Server management
- `/playermgmt` - Player management
- `/kitsmgmt` - Kit management
- `/giveitem`, `/givedino`, `/giveexptoplayer` - Item/dino/XP rewards
- `/broadcast`, `/saveworld`, `/destroywilddinos` - RCON commands
- `/kickplayer`, `/banplayer` - Moderation
- `/serverstart`, `/serverstop`, `/serverrestart` - Service control

### No Role Required
- `/help` - Command help
- `/about`, `/info` - Bot information
- `/servers` - View server status
- `/players` - View online players
- `/findplayer` - Find player location

---

## Error Messages

### User Not Verified
```
❌ You need @Verified role to use this command.

Please contact a server administrator to get verified.
```

### User Not Admin
```
❌ You need Administrator permission or the admin role to use this command.
```

---

## Database Schema

User role ID is stored in `server_configs` table:

```sql
CREATE TABLE server_configs (
    guild_id INTEGER PRIMARY KEY,
    admin_role_id INTEGER,      -- Admin role
    user_role_id INTEGER,        -- User/verified role
    ...
)
```

---

## Migration Notes

### Updating from Old Version

The system will auto-migrate:
1. `user_role_id` column added automatically on bot startup
2. If column doesn't exist, migration creates it
3. Default: NULL (no user role, open access)

No manual database changes needed.

---

## Best Practices

1. **Set Admin Role First**: Always configure admin role before other settings

2. **Test with Alt Account**: Use an alt without roles to test user role restrictions

3. **Document Your Roles**: Tell users which role they need for bot access

4. **Don't Over-Restrict**: Consider leaving user role unset for small communities

5. **Admin Role Security**: Only give to trusted staff - they have full RCON access

6. **User Role for Gating**: Use to prevent abuse in public servers

---

## Troubleshooting

**Problem**: Users can't use /kit or /linkplayer

**Solution**: 
- Check if user role is set in `/setupcfg`
- Verify user has the required role
- Admins can always use these commands

**Problem**: Admins getting "not verified" errors

**Solution**:
- Ensure user has admin role or Administrator permission
- Check admin_role_id is set correctly in config

**Problem**: Want to remove restrictions

**Solution**:
- Run `/setupcfg`
- Click "User Role"
- Select a role, then manually delete user_role_id from database
- Or give everyone the user role

---

## Future Enhancements

Potential additions:
- Per-kit role requirements
- Shop item role restrictions
- Role-based coin bonuses
- Temporary verified role (expires after time)
- Auto-assign user role on first link
