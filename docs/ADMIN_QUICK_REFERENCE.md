# 🎮 ARK Server Management - Quick Reference

## 🚀 Most Used Commands

### Check Status
```
/serverstatus                                    # All servers status
/listplayers server_name:Aberration            # Who's online
```

### Server Control
```
/saveworld                                       # Save all servers
/saveworld server_name:Aberration               # Save specific server
/broadcast message:"Maintenance at 8pm"         # Announce to all
/destroywilddinos                               # Wipe wild dinos (all servers)
```

### Service Management (Local Servers)
```
/serverstart server_name:asa_aberration         # Start server
/serverstop server_name:asa_aberration          # Stop server
/serverrestart server_name:asa_aberration       # Restart server
```

### Player Management
```
/kickplayer player_name:BadPlayer server_name:Aberration
/banplayer player_name:BadPlayer server_name:Aberration
/unbanplayer player_id:76561198012345678 server_name:Aberration
```

### Rewards
```
/giveitem player_name:Winner item_id:PrimalItemResource_MetalIngot_C quantity:1000 server_name:Aberration
/givedino player_name:Winner dino_type:Rex_Character_BP_C level:150 server_name:Aberration
/giveexptoplayer player_name:Winner xp_amount:100000 server_name:Aberration
```

---

## 📋 Common Item IDs

```
PrimalItemResource_MetalIngot_C          # Metal Ingot
PrimalItemResource_Polymer_C             # Polymer
PrimalItemResource_Element_C             # Element
PrimalItemResource_Crystal_C             # Crystal
PrimalItemWeapon_Rifle_C                 # Fabricated Rifle
PrimalItemArmor_RiotShield_C            # Riot Shield
```

---

## 🦕 Common Dino Types

```
Rex_Character_BP_C                       # T-Rex
Giga_Character_BP_C                      # Giganotosaurus  
Argent_Character_BP_C                    # Argentavis
Ankylo_Character_BP_C                    # Ankylosaurus
Wyvern_Character_BP_C                    # Wyvern
```

---

## 🔧 Emergency Procedures

### Server Crash Recovery
```
1. /serverstatus                         # Check status
2. /serverstart server_name:asa_aberration
3. /broadcast message:"Server is back online"
```

### Stuck Player Help
```
/setplayerpos player_name:Player1 x:0 y:0 z:1000 server_name:Aberration
```

### Urgent Maintenance
```
1. /broadcast message:"URGENT: Server restart in 2 minutes"
2. /saveworld server_name:Aberration
3. /serverstop server_name:asa_aberration countdown:120
4. (perform maintenance)
5. /serverstart server_name:asa_aberration
```

---

## 🎯 Routine Maintenance Checklist

### Daily
- [ ] `/serverstatus` - Check all servers running
- [ ] `/listplayers` - Check player counts
- [ ] `/saveworld` - Force save

### Weekly  
- [ ] `/destroywilddinos` - Refresh wild spawns
- [ ] `/serverlogs` - Review logs for issues
- [ ] Backup server data

### Monthly
- [ ] `/serverupdate` - Check for game updates
- [ ] Review ban list
- [ ] Clean up old logs

---

## 🌐 Works With

- ✅ Local servers (NSSM services)
- ✅ Nitrado servers
- ✅ Any server with RCON enabled
- ✅ Remote dedicated servers

---

## 💡 Pro Tips

1. **Use autocomplete** - Start typing, Discord suggests servers
2. **Save before restart** - Always `/saveworld` first
3. **Countdown warnings** - Use countdown parameter for player warning
4. **Batch commands** - Omit server name to apply to all servers
5. **Steam IDs** - More reliable than player names for bans

---

## 📞 Quick Support

**Server won't start?**
```
/serverstatus                            # Check current status
/serverlogs server_name:asa_aberration   # Check logs
```

**RCON not working?**
- Verify RCON enabled in server settings
- Check RCON password correct
- Ensure firewall allows RCON port

**Player complaints?**
```
/getchat server_name:Aberration          # Review recent chat
/listplayers server_name:Aberration      # Check who's online
```

---

**See RCON_ADMIN_COMMANDS.md for complete documentation**
