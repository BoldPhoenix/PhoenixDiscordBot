# Remote Agent Build & Distribution

## Current Build (Manual)

### Prerequisites
- Install Go: https://go.dev/dl/
- Minimum version: Go 1.19+

### Build Steps

**Always use `build.bat`** — it syncs the version from `main.go` → `versioninfo.json`,
generates the Windows resource (exe Details tab), then compiles.

```powershell
cd c:\Projects\PhoenixArkDiscordBot\remote_agent
.\build.bat
```

When bumping the version:
1. Change `const AgentVersion = "X.Y.Z"` in `main.go` (only place to edit)
2. Run `.\build.bat` — `versioninfo.json` is updated automatically

The compiled `PhoenixArkAgent.exe` is placed in both the `remote_agent/` folder
and copied to `dist/` for distribution.

### Deployment to Production Server
1. Stop the service: `sc stop PhoenixArkAgent`
2. Copy `PhoenixArkAgent.exe` to the service directory (e.g. `C:\Program Files\Phoenix Ark Agent\`)
3. Start the service: `sc start PhoenixArkAgent`

---

## Job Logs (v3.1+)

When the bot disconnects mid-update, the agent continues running and writes a
persistent job log to disk so nothing is lost.

**Location:** `jobs\` folder in the same directory as `PhoenixArkAgent.exe`

| Default path (if installed to standard location) |
|---------------------------------------------------|
| `C:\Program Files\Phoenix Ark Agent\jobs\`        |

**File naming:** `maintain_{servername}_{unix_timestamp}.json`
Example: `maintain_island_1772500000.json`

**Contents:**
```json
{
  "job_id": "maintain_island_1772500000",
  "server": "Island",
  "type": "maintain_server",
  "started_at": "2026-03-03T18:00:00Z",
  "completed_at": "2026-03-03T18:28:14Z",
  "status": "completed",
  "steps": [
    { "name": "stop",   "status": "completed", "timestamp": "...", "message": "Service ArkAscended_Island stopped" },
    { "name": "update", "status": "completed", "timestamp": "...", "message": "SteamCMD update completed successfully" },
    { "name": "start",  "status": "completed", "timestamp": "...", "message": "Service ArkAscended_Island running" }
  ]
}
```

**Statuses:** `running` · `completed` · `failed`
**Step statuses:** `completed` · `failed` · `warning` (stop timeout — update still proceeds)

The bot can query recent job logs via the `get_job_log` WebSocket command.
Job files accumulate over time — periodically clear old ones from the `jobs\` folder.

---

## Future Distribution Strategy (For Customer Deployments)

### Option 1: GitHub Releases (Recommended)
- Tag releases in git (e.g., `v1.2.0`)
- Use GitHub Actions to auto-build Windows executable
- Customers download from GitHub Releases page
- Includes auto-update checker in agent

### Option 2: Direct Download Server
- Host compiled executables on your web server
- Agent checks for updates via HTTP endpoint
- Auto-download and install updates (with user approval)

### Option 3: Installer Package
- Create MSI installer with WiX Toolset
- Includes service installation + auto-update
- Professional deployment for enterprise customers

---

## Recent Changes

### Version 1.1.0 (Current)
- Added `detect_cluster_ids` command
- Scans `<cluster_root_path>/clusters/` directory
- Returns list of all cluster IDs for multi-cluster support

### Deployment Notes
- This version requires Python bot update (already deployed to Pi 5)
- Cluster detection requires remote agent running on Windows server with filesystem access
