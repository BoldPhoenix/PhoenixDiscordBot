# Bot Security & Permissions

## Security Model

The bot uses a role-based access control system with two permission levels:

1. **Admin Users**: Users with Discord Administrator permission OR the configured Admin Role
2. **Regular Users**: All authenticated Discord server members

## Admin Role Configuration

Set the admin role using `/setadminrole <role>`. Users with this role can:
- Configure bot settings
- Manage ARK servers
- Execute RCON commands
- Grant coins and manage the shop backend
- View sensitive configuration

## Command Permissions

### 🔒 Admin-Only Commands

#### Setup & Configuration (`setup.py`)
- `/setup` - Initial bot setup wizard
- `/setchannels` - Configure Discord channels
- `/setadminrole` - Set bot admin role
- `/setshop` - Configure shop settings
- `/addserver` - Add ARK server to monitor
- `/removeserver` - Remove ARK server
- `/config` - View current bot configuration (shows sensitive info)
- `/migrate` - Migrate configuration from .env to database
- `/testconnection` - Test ARK server RCON connection

#### RCON Server Management (`rcon_admin.py`)
**Player Management:**
- `/listplayers` - List online players
- `/kickplayer` - Kick player from server
- `/banplayer` - Ban player from server
- `/unbanplayer` - Unban player
- `/whitelistplayer` - Add player to whitelist

**Server Control:**
- `/broadcast` - Broadcast message to all players
- `/saveworld` - Force save the world
- `/destroywilddinos` - Destroy all wild dinosaurs
- `/setmotd` - Set server message of the day

**Item & Dino Management:**
- `/giveitem` - Give item to player
- `/givedino` - Give tamed dinosaur to player
- `/giveexptoplayer` - Give XP to player
- `/setplayerpos` - Teleport player to coordinates

**Admin Utilities:**
- `/rcon` - Execute custom RCON command
- `/getchat` - Get recent chat messages

#### Store Management (`admin.py`)
- `/grantcoins` - Grant Phoenix Coins to user
- `/additem` - Add item to store
- `/removeitem` - Remove item from store
- `/setprice` - Set item price
- `/setstatuschannel` - Set status channel
- `/setchatchannel` - Set chat channel
- `/delivercoins` - Manually deliver coins to player
- `/setplayerid` - Set player's in-game ID
- `/unlinkplayer` - Unlink Discord user from game character
- `/userinfo` - View user information
- `/reloadconfig` - Reload configuration from .env

### 🌐 Public Commands

#### Server Information (`setup.py`)
- `/listservers` - List configured ARK servers (no sensitive data shown)

#### Server Monitoring (`server_monitor.py`)
- `/servers` - View server status
- `/players` - View current players
- `/findplayer` - Find player across servers

#### Shop/Store (`store.py`)
- `/store` - Browse available items
- `/buy` - Purchase item from store
- `/balance` - Check Phoenix Coin balance
- `/transactions` - View purchase history

#### Player Linking (`admin.py`)
- `/linkplayer` - Link Discord account to in-game character
- `/mylink` - View your linked character

## Security Best Practices

### 1. Admin Role Protection
- Set a specific admin role using `/setadminrole` instead of relying on Discord Administrator permission
- Limit the admin role to trusted server moderators only
- Regularly audit who has the admin role

### 2. RCON Password Security
- RCON passwords are stored in the database
- Only admin users can view or modify server configurations
- Never share RCON passwords in public channels

### 3. Shop Security
- Regular users can only purchase items and view their balance
- Only admins can grant coins, add items, or modify prices
- Purchase logs are maintained for auditing

### 4. Command Visibility
- All admin commands show "(admin only)" in their description
- Ephemeral responses (only visible to the command user) are used for sensitive operations
- Failed permission checks show clear error messages

## Implementation Details

### Admin Check Function
```python
async def is_admin(self, interaction: discord.Interaction) -> bool:
    """Check if user has admin permissions."""
    # Check Discord administrator permission
    if interaction.user.guild_permissions.administrator:
        return True
    
    # Check configured admin role
    config = await server_config_db.get_server_config(interaction.guild_id)
    if config and config.get('admin_role_id'):
        admin_role = interaction.guild.get_role(config['admin_role_id'])
        if admin_role and admin_role in interaction.user.roles:
            return True
    
    return False
```

### Command Pattern
```python
@app_commands.command(name="command", description="Description (admin only)")
async def command_function(self, interaction: discord.Interaction):
    """Command description."""
    if not await self.is_admin(interaction):
        await interaction.response.send_message(
            "❌ You need Administrator permission to use this command.",
            ephemeral=True
        )
        return
    
    # Command implementation...
```

## Audit Log

All administrative actions are logged to the configured log channel when available:
- Server configuration changes
- User coin grants
- Item deliveries
- RCON command executions

## Emergency Access

If the admin role is lost or misconfigured:
1. Users with Discord's **Administrator** permission can always execute admin commands
2. Use `/setadminrole` to reconfigure the admin role
3. Database can be manually edited if needed (see documentation)

## Testing Security

Use the test suite to verify security:
```powershell
python tests\test_suite.py
```

Tests include:
- Verification that all admin commands have `is_admin()` checks
- Command defer patterns (prevent timeout)
- Database schema validation
- RCON client security

## Support

For security issues or concerns, contact the bot administrator or open an issue in the GitHub repository.
