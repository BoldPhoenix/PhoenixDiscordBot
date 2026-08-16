# DEV ENVIRONMENT SETUP GUIDE
## Fresh Installation for Testing

### Current State:
- ✅ Dev database backed up and removed
- ✅ Dev .env backed up and removed
- ✅ Code is clean and ready
- ✅ Production untouched and running

### Tomorrow's Setup Steps:

1. **Create Test Discord Server**
   - Create new Discord server OR use private test channel
   - Invite Phoenix bot with admin permissions
   - Note the Guild ID (right-click server → Copy Server ID)

2. **Create .env File**
   Create `C:\Users\YourUser\Documents\Github\ArkDiscordBot\.env`:
   ```
   # Discord Bot Token (same token, different server)
   DISCORD_BOT_TOKEN=<your_bot_token>
   
   # Test Discord Server
   DISCORD_GUILD_ID=<test_server_id>
   
   # Database
   DATABASE_PATH=bot.db
   
   # Bot Settings
   BOT_PREFIX=!
   STATUS_UPDATE_INTERVAL=60
   CHAT_POLL_INTERVAL=5
   ```

3. **Set Up Local ARK Server**
   In database, add your test server:
   - Server name: "TestServer"
   - Map: TheIsland (or whatever you're running)
   - IP: 127.0.0.1
   - Game port: 7777
   - Query port: 27015
   - RCON port: 27020
   - RCON password: <your_test_rcon_password>

4. **Initialize Database**
   ```powershell
   cd C:\Users\YourUser\Documents\Github\ArkDiscordBot
   python -m bot.database.init_db
   ```

5. **Run Bot on Dev**
   ```powershell
   python main.py
   ```

6. **Test in Discord**
   - `/setupcfg` - Configure the test server
     - Set hosting type
     - Configure channels
     - Set admin role (your role)
     - Set user role (optional - for access control)
   - `/linkplayer` - Link your test account
   - `/giveitem` - Test item delivery
   - Verify voice channels work
   - Test all features without production impact

### Key Differences from Production:
- **Dev**: Single test server, test Discord, bot.db on this PC
- **Production**: 9 servers, production Discord, bot.db on 192.168.1.50
- **No sync script** - keep them completely separate

### When Ready for Production:
1. Disable Arkon bot on production servers
2. Test Phoenix bot thoroughly in dev
3. Document any issues
4. Deploy tested features to production
5. Monitor for RCON conflicts

### Backup Location:
`C:\Users\YourUser\Documents\Github\ArkDiscordBot\backup_dev_20251203_231055\`
