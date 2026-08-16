ARK Server Agent - Remote Management System
============================================

This agent allows your Discord bot to manage ARK servers remotely across different machines.

QUICK START
-----------

1. INSTALLATION
   - Copy the entire dist folder to your ARK server machine
   - Run PhoenixArkAgent.exe -install to install as Windows service
   - Edit config.json with your settings
   - Start the service: net start PhoenixArkAgent

2. CONFIGURATION
   Edit config.json:
   {
     "bot_token": "your_discord_bot_token",
     "service_name": "PhoenixArkAgent",
     "port": 8080,
     "auth_key": "agent_unique_auth_key",
     "ark_servers": []
   }

3. DISCORD SETUP
   - In Discord, use /register_agent with your agent IP and auth key
   - Use /remote_management for GUI control
   - Manage servers remotely through Discord

FEATURES
--------
- Remote server start/stop/restart
- Real-time status monitoring
- Log streaming
- Mod management
- Server updates
- Backup operations
- Progress tracking

SECURITY
--------
- JWT authentication between bot and agents
- Encrypted WebSocket communication
- Command whitelisting (no arbitrary code execution)
- Audit logging of all operations

TROUBLESHOOTING
---------------
1. Agent won't start:
   - Check Windows Event Viewer
   - Verify config.json syntax
   - Ensure port 8080 is not blocked

2. Bot can't connect:
   - Ping agent IP from bot machine
   - Check firewall settings
   - Verify auth key matches

3. Commands fail:
   - Check agent logs in logs\ folder
   - Verify ARK services are running
   - Check RCON connectivity

SERVICE COMMANDS
----------------
Install:   PhoenixArkAgent.exe -install
Remove:    PhoenixArkAgent.exe -remove
Start:     net start PhoenixArkAgent
Stop:      net stop PhoenixArkAgent
Restart:   net stop PhoenixArkAgent && net start PhoenixArkAgent

DEFAULT PORTS
-------------
- Agent WebSocket: 8080
- Agent HTTP API: 8080
- RCON: 27020+ (per server)

FILE LOCATIONS
--------------
- Executable: PhoenixArkAgent.exe
- Config: config.json
- Logs: logs\agent.log
- Service: Windows Services > PhoenixArkAgent

SUPPORT
-------
For issues, check:
1. Windows Event Viewer > Application logs
2. logs\agent.log
3. Discord bot logs
4. Network connectivity (ping, telnet)

VERSION: 1.0.0
UPDATED: 2026-02-10
