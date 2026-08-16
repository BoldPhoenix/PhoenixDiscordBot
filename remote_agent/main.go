package main

//go:generate goversioninfo -64 -o resource.syso versioninfo.json

import (
	"archive/zip"
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"sync"

	"github.com/gorilla/mux"
	"github.com/gorilla/websocket"
)

const AgentVersion = "3.3.2"

type ARKAgent struct {
	config      AgentConfig
	server      *http.Server
	connections map[string]*websocket.Conn
	connMu      sync.RWMutex // protects connections map
	writeMu     sync.Mutex   // serializes all WebSocket writes
	startTime   time.Time
	jobs        *JobManager
}

// JobStep represents a single step within a job
type JobStep struct {
	Name      string `json:"name"`
	Status    string `json:"status"` // running, completed, failed, warning
	Timestamp string `json:"timestamp"`
	Message   string `json:"message"`
}

// JobLog is a persistent on-disk record of a long-running agent job
type JobLog struct {
	JobID       string    `json:"job_id"`
	Server      string    `json:"server"`
	Type        string    `json:"type"`
	StartedAt   string    `json:"started_at"`
	CompletedAt string    `json:"completed_at,omitempty"`
	Status      string    `json:"status"` // running, completed, failed
	Steps       []JobStep `json:"steps"`
}

// JobManager handles persistence of JobLog files in the jobs/ directory
type JobManager struct {
	jobsDir string
	mu      sync.Mutex
}

func NewJobManager(exeDir string) *JobManager {
	dir := filepath.Join(exeDir, "jobs")
	os.MkdirAll(dir, 0755)
	return &JobManager{jobsDir: dir}
}

func (jm *JobManager) Save(job *JobLog) error {
	jm.mu.Lock()
	defer jm.mu.Unlock()
	filename := filepath.Join(jm.jobsDir, job.JobID+".json")
	data, err := json.MarshalIndent(job, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filename, data, 0644)
}

func (jm *JobManager) LoadRecent(serverName string, limit int) ([]*JobLog, error) {
	jm.mu.Lock()
	defer jm.mu.Unlock()
	entries, err := os.ReadDir(jm.jobsDir)
	if err != nil {
		if os.IsNotExist(err) {
			return []*JobLog{}, nil
		}
		return nil, err
	}
	var jobs []*JobLog
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(jm.jobsDir, entry.Name()))
		if err != nil {
			continue
		}
		var job JobLog
		if err := json.Unmarshal(data, &job); err != nil {
			continue
		}
		if serverName == "" || strings.EqualFold(job.Server, serverName) {
			jobs = append(jobs, &job)
		}
	}
	// Sort newest first
	sort.Slice(jobs, func(i, j int) bool {
		return jobs[i].StartedAt > jobs[j].StartedAt
	})
	if limit > 0 && len(jobs) > limit {
		jobs = jobs[:limit]
	}
	return jobs, nil
}

type AgentConfig struct {
	BotToken    string      `json:"bot_token"`
	ServiceName string      `json:"service_name"`
	Port        int         `json:"port"`
	AuthKey     string      `json:"auth_key"`
	ARKServers  []ARKServer `json:"ark_servers"`
}

type ARKServer struct {
	Name         string `json:"name"`
	ServiceName  string `json:"service_name"`
	InstallPath  string `json:"install_path"`
	SteamCMDPath string `json:"steamcmd_path"`
	RCONPort     int    `json:"rcon_port"`
	RCONPassword string `json:"rcon_password"`
	LogPath      string `json:"log_path"`
}

type Command struct {
	Type      string      `json:"type"`
	Server    string      `json:"server"`
	Params    interface{} `json:"params"`
	RequestID string      `json:"request_id"`
}

type Response struct {
	Type      string      `json:"type"`
	RequestID string      `json:"request_id"`
	Data      interface{} `json:"data"`
	Error     string      `json:"error,omitempty"`
	Progress  int         `json:"progress,omitempty"`
	Status    string      `json:"status,omitempty"`
}

// parseARKVersionFromLog parses ARK version from shootergame.log file
func parseARKVersionFromLog(logPath string) string {
	defer func() {
		if r := recover(); r != nil {
			logError(fmt.Sprintf("PANIC in parseARKVersionFromLog for %s: %v", logPath, r))
		}
	}()

	log.Printf("Parsing ARK version from log file: %s", logPath)

	// Try to open the log file
	file, err := os.Open(logPath)
	if err != nil {
		log.Printf("Failed to open ARK log file %s: %v", logPath, err)
		return ""
	}
	defer file.Close()

	// Read first 200 lines (version appears near the beginning after restart)
	scanner := bufio.NewScanner(file)
	var lines []string
	maxLines := 200 // Read first 200 lines - version appears near beginning

	log.Printf("Reading log file, looking for version information...")

	// Read first maxLines lines
	lineCount := 0
	for scanner.Scan() {
		if lineCount >= maxLines {
			break
		}
		lines = append(lines, scanner.Text())
		lineCount++
	}

	if err := scanner.Err(); err != nil {
		log.Printf("Error reading ARK log file: %v", err)
		return ""
	}

	log.Printf("Read %d lines from log file", len(lines))

	// Check from the beginning (version appears early)
	for i := 0; i < len(lines); i++ {
		line := lines[i]

		// Look for version pattern: "ARK Version: 79.5" (case insensitive)
		versionRegex := regexp.MustCompile(`(?i)ARK Version:\s*(\d+(?:\.\d+)*)`)
		matches := versionRegex.FindStringSubmatch(line)
		if len(matches) > 1 {
			version := matches[1]
			logInfo(fmt.Sprintf("Found ARK version %s in log file at line %d", version, i+1))
			return version
		}

		// Alternative pattern: "ark.*version[:\s]+(\d+(?:\.\d+)*)"
		altRegex := regexp.MustCompile(`(?i)ark.*version[:\s]+(\d+(?:\.\d+)*)`)
		altMatches := altRegex.FindStringSubmatch(line)
		if len(altMatches) > 1 {
			version := altMatches[1]
			logInfo(fmt.Sprintf("Found ARK version %s (alt pattern) in log file at line %d", version, i+1))
			return version
		}

		// Alternative pattern: "Version v378.15"
		altRegex2 := regexp.MustCompile(`(?i)version\s*v?(\d+(?:\.\d+)*)`)
		altMatches2 := altRegex2.FindStringSubmatch(line)
		if len(altMatches2) > 1 {
			version := altMatches2[1]
			logInfo(fmt.Sprintf("Found ARK version %s (alt pattern2) in log file at line %d", version, i+1))
			return version
		}
	}

	log.Printf("ARK version not found in log file %s", logPath)
	return ""
}

// updateARKVersions updates ARK versions for all configured servers
func (agent *ARKAgent) updateARKVersions() {
	defer func() {
		if r := recover(); r != nil {
			logError(fmt.Sprintf("PANIC in updateARKVersions: %v", r))
		}
	}()

	logInfo("=== Starting ARK Version Update Process ===")

	// Request server configuration from bot if no servers configured locally
	if len(agent.config.ARKServers) == 0 {
		logInfo("No servers configured locally, requesting from bot...")
		agent.requestServerConfiguration()
		return
	}

	logInfo(fmt.Sprintf("Processing %d configured servers...", len(agent.config.ARKServers)))

	for i, server := range agent.config.ARKServers {
		logInfo(fmt.Sprintf("=== Processing Server %d/%d: %s ===", i+1, len(agent.config.ARKServers), server.Name))

		if server.InstallPath == "" {
			logError(fmt.Sprintf("Skipping server %s: no install path configured", server.Name))
			continue
		}

		// Construct log file path: <install_path>\ShooterGame\Saved\Logs\ShooterGame.log
		logPath := filepath.Join(server.InstallPath, "ShooterGame", "Saved", "Logs", "ShooterGame.log")
		logInfo(fmt.Sprintf("Log file path: %s", logPath))

		// Check if log file exists before parsing
		if _, err := os.Stat(logPath); os.IsNotExist(err) {
			logError(fmt.Sprintf("Log file does not exist: %s", logPath))
			continue
		}

		logInfo(fmt.Sprintf("Parsing ARK version for server %s...", server.Name))
		version := parseARKVersionFromLog(logPath)

		if version != "" {
			logInfo(fmt.Sprintf("Successfully parsed ARK version: %s", version))

			// Send version update to bot via WebSocket
			response := Response{
				Type: "ark_version_update",
				Data: map[string]interface{}{
					"server_name": server.Name,
					"ark_version": version,
				},
			}

			// Broadcast to all connected clients (safe)
			agent.broadcastResponse(response)
			logInfo(fmt.Sprintf("Sent ARK version update to all clients: %s -> %s", server.Name, version))
		} else {
			logError(fmt.Sprintf("Could not determine ARK version for %s", server.Name))
		}
	}

	logInfo("=== ARK Version Update Process Completed ===")
}

// requestServerConfiguration requests server configuration from the bot
func (agent *ARKAgent) requestServerConfiguration() {
	logInfo("Requesting server configuration from bot...")
	log.Printf("Requesting server configuration from bot...")

	// Send configuration request to bot
	response := Response{
		Type: "server_config_request",
		Data: map[string]interface{}{
			"agent_id": fmt.Sprintf("%s:%d", "localhost", agent.config.Port),
		},
	}

	// Broadcast to all connected clients (safe)
	agent.broadcastResponse(response)
	logInfo("Server config request sent to all clients")
}

// configureServers configures servers received from bot
func (agent *ARKAgent) configureServers(servers []ARKServer) {
	log.Printf("Configuring %d servers from bot...", len(servers))

	// Update agent's server configuration
	agent.config.ARKServers = servers

	// Now update ARK versions with the new configuration
	go func() {
		time.Sleep(1 * time.Second) // Brief delay
		agent.updateARKVersions()
	}()
}

// configureServersCommand handles configure_servers command from bot
func (agent *ARKAgent) configureServersCommand(connID string, cmd Command) {
	logInfo("Received configure_servers command")
	logInfo(fmt.Sprintf("Command RequestID: %s", cmd.RequestID))

	// Extract servers from command parameters
	serversData, ok := cmd.Params.([]interface{})
	if !ok {
		logError("Invalid servers data format - not an array")
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "Invalid servers data format",
		})
		return
	}

	logInfo(fmt.Sprintf("Received %d server entries from bot", len(serversData)))

	var servers []ARKServer
	for i, serverData := range serversData {
		logInfo(fmt.Sprintf("Processing server entry %d", i+1))

		serverMap, ok := serverData.(map[string]interface{})
		if !ok {
			logError(fmt.Sprintf("Server entry %d is not a map", i+1))
			continue
		}

		server := ARKServer{
			Name:         getString(serverMap, "name"),
			ServiceName:  getString(serverMap, "service_name"),
			InstallPath:  getString(serverMap, "install_path"),
			SteamCMDPath: getString(serverMap, "steamcmd_path"),
			RCONPort:     getInt(serverMap, "rcon_port"),
			RCONPassword: getString(serverMap, "rcon_password"),
			LogPath:      getString(serverMap, "log_path"),
		}

		logInfo(fmt.Sprintf("Parsed server: Name=%s, Service=%s, Path=%s, LogPath=%s, RCON=%d, SteamCMD=%s",
			server.Name, server.ServiceName, server.InstallPath, server.LogPath, server.RCONPort, server.SteamCMDPath))
		servers = append(servers, server)
	}

	logInfo(fmt.Sprintf("Successfully parsed %d servers, configuring agent...", len(servers)))

	// Configure the servers
	agent.configureServers(servers)

	// Send confirmation
	agent.sendResponse(connID, Response{
		Type:      "complete",
		RequestID: cmd.RequestID,
		Data:      fmt.Sprintf("Configured %d servers", len(servers)),
	})

	logInfo(fmt.Sprintf("configure_servers command completed for %d servers", len(servers)))
}

// Helper functions for data extraction
func getString(m map[string]interface{}, key string) string {
	if val, ok := m[key]; ok {
		if str, ok := val.(string); ok {
			return str
		}
	}
	return ""
}

func getInt(m map[string]interface{}, key string) int {
	if val, ok := m[key]; ok {
		if num, ok := val.(float64); ok {
			return int(num)
		}
	}
	return 0
}

func NewARKAgent() *ARKAgent {
	exePath, _ := os.Executable()
	exeDir := filepath.Dir(exePath)
	return &ARKAgent{
		connections: make(map[string]*websocket.Conn),
		startTime:   time.Now(),
		jobs:        NewJobManager(exeDir),
	}
}

func (agent *ARKAgent) loadConfig() error {
	// Get the executable directory to find config file
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("failed to get executable path: %v", err)
	}
	exeDir := filepath.Dir(exePath)
	configFile := filepath.Join(exeDir, "config.json")

	if _, err := os.Stat(configFile); os.IsNotExist(err) {
		// Create default config
		agent.config = AgentConfig{
			ServiceName: "ARKAgent",
			Port:        8080,
			AuthKey:     generateAuthKey(),
		}
		return agent.saveConfig()
	}

	data, err := os.ReadFile(configFile)
	if err != nil {
		return fmt.Errorf("failed to read config: %v", err)
	}

	return json.Unmarshal(data, &agent.config)
}

func (agent *ARKAgent) saveConfig() error {
	data, err := json.MarshalIndent(agent.config, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal config: %v", err)
	}

	// Get the executable directory to save config file
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("failed to get executable path: %v", err)
	}
	exeDir := filepath.Dir(exePath)
	configFile := filepath.Join(exeDir, "config.json")

	return os.WriteFile(configFile, data, 0644)
}

func (agent *ARKAgent) setupRoutes() {
	router := mux.NewRouter()

	// WebSocket endpoint for real-time communication
	router.HandleFunc("/ws", agent.handleWebSocket).Methods("GET")

	// REST API endpoints
	router.HandleFunc("/api/status", agent.handleStatus).Methods("GET")
	router.HandleFunc("/api/servers", agent.handleServers).Methods("GET")
	router.HandleFunc("/api/command", agent.handleCommand).Methods("POST")
	router.HandleFunc("/api/debug", agent.handleDebug).Methods("GET")

	agent.server = &http.Server{
		Addr:    fmt.Sprintf(":%d", agent.config.Port),
		Handler: router,
	}
}

func (agent *ARKAgent) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	// Use Event Viewer for logging since file logging isn't working in service
	log.Printf("WebSocket connection attempt from %s", r.RemoteAddr)

	upgrader := websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool {
			return true // Allow connections from Discord bot
		},
		// Add these settings for better Python compatibility
		HandshakeTimeout: 10 * time.Second,
		ReadBufferSize:   1024,
		WriteBufferSize:  1024,
	}

	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("WebSocket upgrade failed: %v", err)
		return
	}
	defer conn.Close()

	log.Printf("WebSocket upgraded successfully")

	// Authenticate connection
	authKey := r.URL.Query().Get("auth_key")
	log.Printf("Auth attempt from %s", r.RemoteAddr)
	if authKey != agent.config.AuthKey {
		log.Printf("Auth key mismatch - rejecting connection from %s", r.RemoteAddr)
		conn.WriteMessage(websocket.TextMessage, []byte(`{"error":"Invalid auth key"}`))
		// Send proper close frame
		conn.WriteMessage(websocket.CloseMessage, []byte{})
		return
	}

	log.Printf("Auth successful - connection accepted")

	connID := generateConnectionID()
	agent.connMu.Lock()
	agent.connections[connID] = conn
	agent.connMu.Unlock()
	defer func() {
		agent.connMu.Lock()
		delete(agent.connections, connID)
		agent.connMu.Unlock()
	}()

	log.Printf("WebSocket connection established: %s", connID)

	// Send initial status immediately
	agent.sendResponse(connID, Response{
		Type: "connected",
		Data: "Agent connected successfully",
	})

	// Request server configuration immediately if no servers configured locally
	if len(agent.config.ARKServers) == 0 {
		logInfo("No local server configuration, requesting from bot...")
		agent.requestServerConfiguration()
	}

	// Set up proper connection handling for Python client
	conn.SetReadLimit(65536)

	// Python websockets sends pings every 30s (ping_interval=30).
	// Reset the read deadline each time a ping arrives so the connection
	// stays alive indefinitely without any server-side ticker.
	conn.SetPingHandler(func(appData string) error {
		log.Printf("Ping received from client, resetting read deadline")
		conn.SetReadDeadline(time.Now().Add(120 * time.Second))
		// Must send pong ourselves when overriding the default handler
		return conn.WriteControl(websocket.PongMessage, []byte(appData), time.Now().Add(10*time.Second))
	})

	// Also extend deadline on pong (in case the bot sends unsolicited pongs)
	conn.SetPongHandler(func(appData string) error {
		conn.SetReadDeadline(time.Now().Add(120 * time.Second))
		return nil
	})

	// Initial read deadline — Python will send a ping within 30s to extend it
	conn.SetReadDeadline(time.Now().Add(120 * time.Second))

	// Simple read loop — keepalive is handled by the ping handler above
	for {
		var cmd Command
		err := conn.ReadJSON(&cmd)
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				log.Printf("WebSocket error: %v", err)
			} else if err.Error() == "EOF" {
				log.Printf("Client disconnected gracefully")
			} else {
				log.Printf("Read error: %v", err)
			}
			return
		}

		log.Printf("Received command: %s", cmd.Type)
		go func(id string, c Command) {
			defer func() {
				if r := recover(); r != nil {
					logError(fmt.Sprintf("PANIC in processCommand(%s): %v", c.Type, r))
				}
			}()
			agent.processCommand(id, c)
		}(connID, cmd)
	}
}

func (agent *ARKAgent) processCommand(connID string, cmd Command) {
	logInfo(fmt.Sprintf("Processing command: %s for server: %s", cmd.Type, cmd.Server))

	switch cmd.Type {
	case "start_server":
		logInfo("Dispatching to startServer")
		agent.startServer(connID, cmd)
	case "stop_server":
		agent.stopServer(connID, cmd)
	case "restart_server":
		agent.restartServer(connID, cmd)
	case "get_status":
		agent.getServerStatus(connID, cmd)
	case "discover_servers":
		agent.discoverServers(connID, cmd)
	case "install_mod":
		agent.installMod(connID, cmd)
	case "update_server":
		agent.updateServer(connID, cmd)
	case "view_logs":
		agent.viewLogs(connID, cmd)
	case "backup_server":
		logInfo("Dispatching to backupServer")
		agent.backupServer(connID, cmd)
	case "restore_server":
		agent.restoreServer(connID, cmd)
	case "verify_backup":
		agent.verifyBackup(connID, cmd)
	case "read_ini":
		agent.readINI(connID, cmd)
	case "write_ini":
		agent.writeINI(connID, cmd)
	case "update_ini_setting":
		agent.updateIniSetting(connID, cmd)
	case "get_server_config":
		agent.getServerConfig(connID, cmd)
	case "check_update":
		agent.checkUpdate(connID, cmd)
	case "get_mods":
		agent.getMods(connID, cmd)
	case "set_mods":
		agent.setMods(connID, cmd)
	case "configure_servers":
		logInfo("Received configure_servers command - processing...")
		agent.configureServersCommand(connID, cmd)
	case "detect_cluster_ids":
		agent.detectClusterIDs(connID, cmd)
	case "maintain_server":
		agent.maintainServer(connID, cmd)
	case "get_job_log":
		agent.getJobLogs(connID, cmd)
	// Phase 16: ARK Server Service Management
	case "create_server_service":
		agent.createServerService(connID, cmd)
	case "update_server_config":
		agent.updateServerConfig(connID, cmd)
	case "read_server_config":
		agent.readServerConfig(connID, cmd)
	case "delete_server_service":
		agent.deleteServerService(connID, cmd)
	case "list_server_services":
		agent.listServerServices(connID, cmd)
	case "start_ark_service":
		agent.startArkService(connID, cmd)
	case "stop_ark_service":
		agent.stopArkService(connID, cmd)
	case "restart_ark_service":
		agent.restartArkService(connID, cmd)
	case "get_ark_service_status":
		agent.getArkServiceStatus(connID, cmd)
	case "ping":
		agent.sendResponse(connID, Response{
			Type:      "pong",
			RequestID: cmd.RequestID,
			Data:      "pong",
		})
	default:
		logError(fmt.Sprintf("Unknown command type: %s", cmd.Type))
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Unknown command type: %s", cmd.Type),
		})
	}
}

func (agent *ARKAgent) findServer(name string) *ARKServer {
	log.Printf("findServer: looking for '%s' among %d servers", name, len(agent.config.ARKServers))
	for i := range agent.config.ARKServers {
		log.Printf("findServer: checking '%s' vs '%s'", name, agent.config.ARKServers[i].Name)
		if strings.EqualFold(agent.config.ARKServers[i].Name, name) {
			log.Printf("findServer: FOUND '%s'", name)
			return &agent.config.ARKServers[i]
		}
	}
	log.Printf("findServer: NOT FOUND '%s'", name)
	return nil
}

func (agent *ARKAgent) queryServiceState(serviceName string) (string, error) {
	out, err := exec.Command("sc", "query", serviceName).CombinedOutput()
	if err != nil {
		return "UNKNOWN", err
	}
	output := string(out)
	if strings.Contains(output, "RUNNING") {
		return "RUNNING", nil
	} else if strings.Contains(output, "STOPPED") {
		return "STOPPED", nil
	} else if strings.Contains(output, "START_PENDING") {
		return "START_PENDING", nil
	} else if strings.Contains(output, "STOP_PENDING") {
		return "STOP_PENDING", nil
	}
	return "UNKNOWN", nil
}

func (agent *ARKAgent) startServer(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 0,
		Status: fmt.Sprintf("Starting service %s...", srv.ServiceName),
	})

	out, err := exec.Command("sc", "start", srv.ServiceName).CombinedOutput()
	if err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Failed to start service: %s - %s", err, string(out)),
		})
		return
	}

	// Poll until running or timeout (120s)
	for i := 0; i < 60; i++ {
		time.Sleep(2 * time.Second)
		state, _ := agent.queryServiceState(srv.ServiceName)
		progress := min((i+1)*100/60, 99)
		agent.sendResponse(connID, Response{
			Type: "progress", RequestID: cmd.RequestID, Progress: progress,
			Status: fmt.Sprintf("Service state: %s", state),
		})
		if state == "RUNNING" {
			// Parse ARK version after server starts
			go func() {
				defer func() {
					if r := recover(); r != nil {
						logError(fmt.Sprintf("PANIC in post-start version update: %v", r))
					}
				}()
				time.Sleep(5 * time.Second) // Wait for server to fully start
				logPath := filepath.Join(srv.InstallPath, "ShooterGame", "Saved", "Logs", "ShooterGame.log")
				version := parseARKVersionFromLog(logPath)

				if version != "" {
					response := Response{
						Type: "ark_version_update",
						Data: map[string]interface{}{
							"server_name": srv.Name,
							"ark_version": version,
						},
					}
					agent.broadcastResponse(response)
					logInfo(fmt.Sprintf("Updated ARK version for %s after start: %s", srv.Name, version))
				}
			}()

			agent.sendResponse(connID, Response{
				Type: "complete", RequestID: cmd.RequestID, Progress: 100,
				Data: fmt.Sprintf("Server %s started successfully", cmd.Server),
			})
			return
		}
	}

	agent.sendResponse(connID, Response{
		Type: "complete", RequestID: cmd.RequestID, Progress: 100,
		Data: fmt.Sprintf("Start command sent for %s (may still be loading)", cmd.Server),
	})
}

func (agent *ARKAgent) stopServer(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 0,
		Status: fmt.Sprintf("Stopping service %s...", srv.ServiceName),
	})

	out, err := exec.Command("sc", "stop", srv.ServiceName).CombinedOutput()
	if err != nil {
		// May already be stopped
		state, _ := agent.queryServiceState(srv.ServiceName)
		if state == "STOPPED" {
			agent.sendResponse(connID, Response{
				Type: "complete", RequestID: cmd.RequestID, Progress: 100,
				Data: fmt.Sprintf("Server %s is already stopped", cmd.Server),
			})
			return
		}
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Failed to stop service: %s - %s", err, string(out)),
		})
		return
	}

	// Poll until stopped or timeout (60s)
	for i := 0; i < 30; i++ {
		time.Sleep(2 * time.Second)
		state, _ := agent.queryServiceState(srv.ServiceName)
		progress := min((i+1)*100/30, 99)
		agent.sendResponse(connID, Response{
			Type: "progress", RequestID: cmd.RequestID, Progress: progress,
			Status: fmt.Sprintf("Service state: %s", state),
		})
		if state == "STOPPED" {
			agent.sendResponse(connID, Response{
				Type: "complete", RequestID: cmd.RequestID, Progress: 100,
				Data: fmt.Sprintf("Server %s stopped successfully", cmd.Server),
			})
			return
		}
	}

	agent.sendResponse(connID, Response{
		Type: "complete", RequestID: cmd.RequestID, Progress: 100,
		Data: fmt.Sprintf("Stop command sent for %s (may still be shutting down)", cmd.Server),
	})
}

func (agent *ARKAgent) restartServer(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	// Stop
	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 10,
		Status: "Stopping server...",
	})
	exec.Command("sc", "stop", srv.ServiceName).CombinedOutput()

	// Wait for stop
	for i := 0; i < 30; i++ {
		time.Sleep(2 * time.Second)
		state, _ := agent.queryServiceState(srv.ServiceName)
		agent.sendResponse(connID, Response{
			Type: "progress", RequestID: cmd.RequestID, Progress: 10 + (i * 40 / 30),
			Status: fmt.Sprintf("Stopping... (%s)", state),
		})
		if state == "STOPPED" {
			break
		}
	}

	// Brief pause
	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 50,
		Status: "Server stopped, starting...",
	})
	time.Sleep(3 * time.Second)

	// Start
	exec.Command("sc", "start", srv.ServiceName).CombinedOutput()

	for i := 0; i < 60; i++ {
		time.Sleep(2 * time.Second)
		state, _ := agent.queryServiceState(srv.ServiceName)
		agent.sendResponse(connID, Response{
			Type: "progress", RequestID: cmd.RequestID, Progress: 50 + (i * 49 / 60),
			Status: fmt.Sprintf("Starting... (%s)", state),
		})
		if state == "RUNNING" {
			// Parse ARK version after server restarts
			go func() {
				defer func() {
					if r := recover(); r != nil {
						logError(fmt.Sprintf("PANIC in post-restart version update: %v", r))
					}
				}()
				time.Sleep(5 * time.Second) // Wait for server to fully start
				logPath := filepath.Join(srv.InstallPath, "ShooterGame", "Saved", "Logs", "ShooterGame.log")
				version := parseARKVersionFromLog(logPath)

				if version != "" {
					response := Response{
						Type: "ark_version_update",
						Data: map[string]interface{}{
							"server_name": srv.Name,
							"ark_version": version,
						},
					}
					agent.broadcastResponse(response)
					log.Printf("Updated ARK version for %s after restart: %s", srv.Name, version)
				}
			}()

			agent.sendResponse(connID, Response{
				Type: "complete", RequestID: cmd.RequestID, Progress: 100,
				Data: fmt.Sprintf("Server %s restarted successfully", cmd.Server),
			})
			return
		}
	}

	agent.sendResponse(connID, Response{
		Type: "complete", RequestID: cmd.RequestID, Progress: 100,
		Data: fmt.Sprintf("Restart initiated for %s (may still be loading)", cmd.Server),
	})
}

func (agent *ARKAgent) getServerStatus(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	state, _ := agent.queryServiceState(srv.ServiceName)
	isOnline := state == "RUNNING"

	// Get ARK version from log file
	arkVersion := ""
	if srv.LogPath != "" {
		arkVersion = parseARKVersionFromLog(srv.LogPath)
	}

	// Check install path exists
	pathExists := false
	if srv.InstallPath != "" {
		if _, err := os.Stat(srv.InstallPath); err == nil {
			pathExists = true
		}
	}

	status := map[string]interface{}{
		"name":          srv.Name,
		"service_name":  srv.ServiceName,
		"service_state": state,
		"online":        isOnline,
		"install_path":  srv.InstallPath,
		"path_exists":   pathExists,
		"rcon_port":     srv.RCONPort,
		"ark_version":   arkVersion,
	}

	agent.sendResponse(connID, Response{
		Type:      "status",
		RequestID: cmd.RequestID,
		Data:      status,
	})
}

func (agent *ARKAgent) discoverServers(connID string, cmd Command) {
	// Return real servers from config with status checks
	type ServerInfo struct {
		Name         string `json:"name"`
		ServiceName  string `json:"service_name"`
		InstallPath  string `json:"install_path"`
		RCONPort     int    `json:"rcon_port"`
		ServiceState string `json:"service_state"`
		PathExists   bool   `json:"path_exists"`
	}

	var servers []ServerInfo
	for _, srv := range agent.config.ARKServers {
		state, _ := agent.queryServiceState(srv.ServiceName)
		pathExists := false
		if srv.InstallPath != "" {
			if _, err := os.Stat(srv.InstallPath); err == nil {
				pathExists = true
			}
		}
		servers = append(servers, ServerInfo{
			Name:         srv.Name,
			ServiceName:  srv.ServiceName,
			InstallPath:  srv.InstallPath,
			RCONPort:     srv.RCONPort,
			ServiceState: state,
			PathExists:   pathExists,
		})
	}

	agent.sendResponse(connID, Response{
		Type:      "servers",
		RequestID: cmd.RequestID,
		Data:      servers,
	})
}

func (agent *ARKAgent) installMod(connID string, cmd Command) {
	// TODO: Phase 6 - CurseForge mod management
	agent.sendResponse(connID, Response{
		Type: "error", RequestID: cmd.RequestID,
		Error: "Mod installation not yet implemented (Phase 6)",
	})
}

func (agent *ARKAgent) updateServer(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	// Look for SteamCMD - ONLY use configured path from bot
	steamcmdPaths := []string{}

	// Only check if server has a configured steamcmd_path
	if srv.SteamCMDPath != "" {
		steamcmdPaths = append(steamcmdPaths, srv.SteamCMDPath)
	}

	// Also accept via params
	var serverPath string
	var arkAppID = 2430930
	var useCustomScript bool
	var doValidate bool

	if params, ok := cmd.Params.(map[string]interface{}); ok {
		if p, ok := params["steamcmd_path"].(string); ok && p != "" {
			steamcmdPaths = append([]string{p}, steamcmdPaths...)
		}
		if sp, ok := params["server_path"].(string); ok && sp != "" {
			serverPath = sp
		}
		if aid, ok := params["ark_appid"].(float64); ok {
			arkAppID = int(aid)
		}
		if use, ok := params["use_custom_script"].(bool); ok {
			useCustomScript = use
		}
		if validate, ok := params["validate"].(bool); ok {
			doValidate = validate
		}
	}

	var steamcmdPath string
	for _, p := range steamcmdPaths {
		if _, err := os.Stat(p); err == nil {
			steamcmdPath = p
			break
		}
	}

	if steamcmdPath == "" {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: "SteamCMD not found. Checked: " + strings.Join(steamcmdPaths, ", "),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 5,
		Status: "Found SteamCMD, starting update...",
	})

	var cmd2 *exec.Cmd
	var stdout io.Reader
	var cmdErr error

	if useCustomScript && serverPath != "" {
		logInfo("=== Using Custom Script Mode ===")
		logInfo(fmt.Sprintf("Received params: %+v", cmd.Params))

		// Use the configured SteamCMD directory directly from params
		var steamcmdDir string
		if params, ok := cmd.Params.(map[string]interface{}); ok {
			// Bot sends steam directory directly - that's all we need
			if dir, ok := params["steamcmd_path"].(string); ok && dir != "" {
				steamcmdDir = dir
				logInfo(fmt.Sprintf("Received steam directory: %s", dir))
			}
			logInfo(fmt.Sprintf("Params steamcmd_path (directory): %s", params["steamcmd_path"]))
			logInfo(fmt.Sprintf("Params server_path: %s", params["server_path"]))
		}

		tempFile := filepath.Join(os.TempDir(), fmt.Sprintf("ark_update_%s.bat", cmd.Server))
		// MUST have steamcmd_dir from configured path
		if steamcmdDir == "" {
			agent.sendResponse(connID, Response{
				Type: "error", RequestID: cmd.RequestID,
				Error: "Custom script mode requires configured steamcmd_path",
			})
			return
		}

		batchScript := fmt.Sprintf(`@echo off
set STEAMCMDDIR=%s
set SERVERDIR=%s
set ARKAPPID=%d

echo [ARKAgent] Using SteamCMD in: %%STEAMCMDDIR%%
echo [ARKAgent] Updating ARK server in: %%SERVERDIR%%
echo [ARKAgent] App ID: %%ARKAPPID%%
cd /d %%STEAMCMDDIR%%
echo [ARKAgent] Current directory: %%CD%%
echo [ARKAgent] Deleting existing steamcmd.exe...
del steamcmd.exe
timeout /t 5 /nobreak >nul
echo [ARKAgent] Downloading fresh SteamCMD...
curl -o steamcmd.zip https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip
echo [ARKAgent] Extracting SteamCMD...
powershell Expand-Archive -Path .\steamcmd.zip -DestinationPath .\
echo [ARKAgent] Running SteamCMD update for %%SERVERDIR%%...
start "" /wait steamcmd.exe +force_install_dir "%%SERVERDIR%%" +login anonymous +app_update %%ARKAPPID%% %s +quit
echo [ARKAgent] SteamCMD finished with exit code %%ERRORLEVEL%%
`, steamcmdDir, serverPath, arkAppID, func() string {
			if doValidate {
				return "validate"
			}
			return ""
		}())

		if err := os.WriteFile(tempFile, []byte(batchScript), 0644); err != nil {
			agent.sendResponse(connID, Response{
				Type: "error", RequestID: cmd.RequestID,
				Error: fmt.Sprintf("Failed to create update script: %v", err),
			})
			return
		}
		defer os.Remove(tempFile)

		agent.sendResponse(connID, Response{
			Type: "progress", RequestID: cmd.RequestID, Progress: 10,
			Status: "Running SteamCMD update script...",
		})

		cmd2 = exec.Command("cmd", "/c", tempFile)
		// Run the batch script from the SteamCMD directory
		cmd2.Dir = steamcmdDir
		stdout, cmdErr = cmd2.StdoutPipe()
		if cmdErr != nil {
			agent.sendResponse(connID, Response{
				Type: "error", RequestID: cmd.RequestID,
				Error: fmt.Sprintf("Failed to create pipe: %v", cmdErr),
			})
			return
		}
		cmd2.Stderr = cmd2.Stdout
	} else {
		// Standard SteamCMD update using install path from server config
		installPath := serverPath
		if installPath == "" {
			installPath = srv.InstallPath
		}

		// Get the SteamCMD directory from configured path ONLY
		var steamcmdDir string
		if srv.SteamCMDPath != "" {
			steamcmdDir = filepath.Dir(srv.SteamCMDPath)
		}

		// MUST have configured steamcmd_path
		if steamcmdDir == "" {
			agent.sendResponse(connID, Response{
				Type: "error", RequestID: cmd.RequestID,
				Error: "Server must have configured steamcmd_path",
			})
			return
		}

		// Build arguments based on validation setting
		args := []string{
			"+@ShutdownOnFailedCommand", "1",
			"+@NoPromptForPassword", "1",
			"+login", "anonymous",
			"+force_install_dir", installPath,
			"+app_update", fmt.Sprintf("%d", arkAppID),
		}

		// Add validate flag if requested
		if doValidate {
			args = append(args, "validate")
		}

		args = append(args, "+quit")

		cmd2 = exec.Command(srv.SteamCMDPath, args...)
		// Run steamcmd from the correct SteamCMD directory
		cmd2.Dir = steamcmdDir
		stdout, cmdErr = cmd2.StdoutPipe()
		if cmdErr != nil {
			agent.sendResponse(connID, Response{
				Type: "error", RequestID: cmd.RequestID,
				Error: fmt.Sprintf("Failed to start SteamCMD: %v", cmdErr),
			})
			return
		}
		cmd2.Stderr = cmd2.Stdout
	}

	if err := cmd2.Start(); err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Failed to start SteamCMD: %v", err),
		})
		return
	}

	// Stream SteamCMD output as progress
	scanner := bufio.NewScanner(stdout)
	lineCount := 0
	for scanner.Scan() {
		line := scanner.Text()
		lineCount++
		// Estimate progress based on output
		progress := min(5+(lineCount*90/200), 95)
		if strings.Contains(line, "downloading") || strings.Contains(line, "Downloading") {
			agent.sendResponse(connID, Response{
				Type: "progress", RequestID: cmd.RequestID, Progress: progress,
				Status: line,
			})
		} else if strings.Contains(line, "validating") || strings.Contains(line, "Validating") {
			agent.sendResponse(connID, Response{
				Type: "progress", RequestID: cmd.RequestID, Progress: progress,
				Status: line,
			})
		} else if strings.Contains(line, "Success") || strings.Contains(line, "already up to date") {
			agent.sendResponse(connID, Response{
				Type: "progress", RequestID: cmd.RequestID, Progress: 98,
				Status: line,
			})
		}
	}

	cmdErr = cmd2.Wait()
	if cmdErr != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("SteamCMD exited with error: %v", cmdErr),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type: "complete", RequestID: cmd.RequestID, Progress: 100,
		Data: fmt.Sprintf("Server %s update completed via SteamCMD", cmd.Server),
	})
}

func (agent *ARKAgent) viewLogs(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	// Default log path
	logPath := filepath.Join(srv.InstallPath, "ShooterGame", "Saved", "Logs", "ShooterGame.log")

	// Allow override via params
	if params, ok := cmd.Params.(map[string]interface{}); ok {
		if p, ok := params["log_path"].(string); ok && p != "" {
			logPath = p
		}
	}

	// Number of lines to return (default 50)
	numLines := 50
	if params, ok := cmd.Params.(map[string]interface{}); ok {
		if n, ok := params["lines"].(float64); ok && n > 0 {
			numLines = int(n)
		}
	}

	file, err := os.Open(logPath)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Cannot open log file %s: %v", logPath, err),
		})
		return
	}
	defer file.Close()

	// Read all lines and return the last N
	var allLines []string
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024) // 1MB buffer for long lines
	for scanner.Scan() {
		allLines = append(allLines, scanner.Text())
	}

	start := 0
	if len(allLines) > numLines {
		start = len(allLines) - numLines
	}
	lines := allLines[start:]

	agent.sendResponse(connID, Response{
		Type:      "logs",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"log_path":    logPath,
			"total_lines": len(allLines),
			"returned":    len(lines),
			"lines":       lines,
		},
	})
}

func (agent *ARKAgent) backupServer(connID string, cmd Command) {
	log.Printf("backupServer: STARTING - server=%s", cmd.Server)

	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	savedDir := filepath.Join(srv.InstallPath, "ShooterGame", "Saved")

	// Parse params
	essentialsOnly := true
	backupDir := filepath.Join(srv.InstallPath, "Backups")
	if params, ok := cmd.Params.(map[string]interface{}); ok {
		if e, ok := params["essentials_only"].(bool); ok {
			essentialsOnly = e
		}
		// Use caller-supplied backup_path if provided (custom target directory)
		if bp, ok := params["backup_path"].(string); ok && bp != "" {
			backupDir = bp
		}
	}

	if err := os.MkdirAll(backupDir, 0755); err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Cannot create backup directory %s: %v", backupDir, err),
		})
		return
	}

	backupType := "full"
	if essentialsOnly {
		backupType = "essentials"
	}
	timestamp := time.Now().Format("20060102_150405")
	zipFileName := fmt.Sprintf("%s_backup_%s_%s.zip", srv.Name, timestamp, backupType)
	zipFilePath := filepath.Join(backupDir, zipFileName)

	log.Printf("Backup: server=%s, savedDir=%s, zipFile=%s, type=%s", srv.Name, savedDir, zipFilePath, backupType)

	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 5,
		Status: "Starting backup...",
	})

	// Create the zip file
	zipFile, err := os.Create(zipFilePath)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Failed to create zip file: %v", err),
		})
		return
	}

	zipWriter := zip.NewWriter(zipFile)

	// Extensions included for an "essentials" backup
	essentialsExts := map[string]bool{
		".ark": true, ".arkprofile": true, ".arktribe": true,
		".arktributetribe": true, ".ini": true,
	}

	fileCount := 0

	addToZip := func(filePath, archiveName string) {
		f, err := os.Open(filePath)
		if err != nil {
			log.Printf("backup: cannot open %s: %v", filePath, err)
			return
		}
		defer f.Close()
		w, err := zipWriter.Create(archiveName)
		if err != nil {
			log.Printf("backup: cannot create zip entry %s: %v", archiveName, err)
			return
		}
		if _, err := io.Copy(w, f); err != nil {
			log.Printf("backup: cannot write %s to zip: %v", archiveName, err)
			return
		}
		fileCount++
	}

	// Walk SavedArks — map saves, player profiles, tribe data
	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 20,
		Status: "Backing up save files...",
	})
	savedArksDir := filepath.Join(savedDir, "SavedArks")
	if _, err := os.Stat(savedArksDir); err == nil {
		filepath.Walk(savedArksDir, func(path string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() {
				return nil
			}
			ext := strings.ToLower(filepath.Ext(path))
			if essentialsOnly && !essentialsExts[ext] {
				return nil
			}
			rel, _ := filepath.Rel(savedDir, path)
			addToZip(path, rel)
			return nil
		})
	}

	// Walk Config directory — INI files
	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 60,
		Status: "Backing up config files...",
	})
	configDir := filepath.Join(savedDir, "Config")
	if _, err := os.Stat(configDir); err == nil {
		filepath.Walk(configDir, func(path string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() {
				return nil
			}
			ext := strings.ToLower(filepath.Ext(path))
			if essentialsOnly && ext != ".ini" {
				return nil
			}
			rel, _ := filepath.Rel(savedDir, path)
			addToZip(path, rel)
			return nil
		})
	}

	// Full backup only: also include Logs
	if !essentialsOnly {
		agent.sendResponse(connID, Response{
			Type: "progress", RequestID: cmd.RequestID, Progress: 80,
			Status: "Backing up logs...",
		})
		logsDir := filepath.Join(savedDir, "Logs")
		if _, err := os.Stat(logsDir); err == nil {
			filepath.Walk(logsDir, func(path string, info os.FileInfo, err error) error {
				if err != nil || info.IsDir() {
					return nil
				}
				rel, _ := filepath.Rel(savedDir, path)
				addToZip(path, rel)
				return nil
			})
		}
	}

	zipWriter.Close()
	zipFile.Close()

	// Report the final zip size
	var sizeMB float64
	if info, err := os.Stat(zipFilePath); err == nil {
		sizeMB = float64(info.Size()) / 1024 / 1024
	}

	log.Printf("Backup complete: %s (%.1f MB, %d files)", zipFilePath, sizeMB, fileCount)

	agent.sendResponse(connID, Response{
		Type: "complete", RequestID: cmd.RequestID, Progress: 100,
		Data: map[string]interface{}{
			"backup_file": zipFilePath,
			"backup_type": backupType,
			"size_mb":     fmt.Sprintf("%.1f", sizeMB),
			"file_count":  fileCount,
		},
	})
}

func (agent *ARKAgent) restoreServer(connID string, cmd Command) {
	// Get backup path and target path from params
	var backupPath string
	var targetPath string
	if params, ok := cmd.Params.(map[string]interface{}); ok {
		if bp, ok := params["backup_path"].(string); ok {
			backupPath = bp
		}
		if tp, ok := params["target_path"].(string); ok {
			targetPath = tp
		}
	}

	if backupPath == "" {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: "backup_path parameter is required",
		})
		return
	}

	// Check if backup file exists
	if _, err := os.Stat(backupPath); os.IsNotExist(err) {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Backup file not found: %s", backupPath),
		})
		return
	}

	// Find the server - we need to determine which server this backup belongs to
	// The backup filename format is: ServerName_backup_timestamp_type.zip
	backupFileName := filepath.Base(backupPath)
	// Extract server name from filename (e.g., "Aberration_backup_20260227_020000_essentials.zip")
	serverName := strings.TrimSuffix(strings.TrimPrefix(backupFileName, "_backup_"), "_backup_")
	parts := strings.Split(backupFileName, "_backup_")
	if len(parts) > 0 {
		serverName = parts[0]
	}

	// Find server config by name
	srv := agent.findServer(serverName)
	if srv == nil {
		// Try to find by matching any server name in the backup path or config
		for _, s := range agent.config.ARKServers {
			if strings.Contains(backupPath, s.Name) || strings.Contains(backupFileName, s.Name) {
				srv = &s
				break
			}
		}
	}

	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Could not determine server for backup: %s", backupFileName),
		})
		return
	}

	// Determine restore target - use target_path if provided, otherwise use Saved directory
	restoreDir := ""
	if targetPath != "" {
		// Validate target path
		if _, err := os.Stat(targetPath); os.IsNotExist(err) {
			// Create if it doesn't exist
			if err := os.MkdirAll(targetPath, 0755); err != nil {
				agent.sendResponse(connID, Response{
					Type: "error", RequestID: cmd.RequestID,
					Error: fmt.Sprintf("Failed to create target directory: %v", err),
				})
				return
			}
		}
		restoreDir = targetPath
	} else {
		// Default to Saved directory
		savedDir := filepath.Join(srv.InstallPath, "ShooterGame", "Saved")
		if _, err := os.Stat(savedDir); os.IsNotExist(err) {
			agent.sendResponse(connID, Response{
				Type: "error", RequestID: cmd.RequestID,
				Error: fmt.Sprintf("Saved directory not found: %s", savedDir),
			})
			return
		}
		restoreDir = savedDir
	}

	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 5,
		Status: "Starting restore...",
	})

	// Open the zip file
	zipReader, err := zip.OpenReader(backupPath)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Failed to open backup file: %v", err),
		})
		return
	}
	defer zipReader.Close()

	// Extract files
	fileCount := 0
	restoredCount := 0
	totalFiles := len(zipReader.File)

	for _, zf := range zipReader.File {
		// Send progress update
		if fileCount%5 == 0 {
			progress := 5 + (fileCount * 90 / totalFiles)
			agent.sendResponse(connID, Response{
				Type: "progress", RequestID: cmd.RequestID, Progress: progress,
				Status: fmt.Sprintf("Restoring files... (%d/%d)", fileCount, totalFiles),
			})
		}

		// Skip directories
		if zf.FileInfo().IsDir() {
			fileCount++
			continue
		}

		// Create destination path
		destPath := filepath.Join(restoreDir, zf.Name)

		// Create parent directories if needed
		parentDir := filepath.Dir(destPath)
		if err := os.MkdirAll(parentDir, 0755); err != nil {
			log.Printf("Failed to create directory %s: %v", parentDir, err)
			fileCount++
			continue
		}

		// Read from zip
		reader, err := zf.Open()
		if err != nil {
			log.Printf("Failed to open %s in zip: %v", zf.Name, err)
			fileCount++
			continue
		}

		// Write to destination
		writer, err := os.Create(destPath)
		if err != nil {
			log.Printf("Failed to create %s: %v", destPath, err)
			reader.Close()
			fileCount++
			continue
		}

		if _, err := io.Copy(writer, reader); err != nil {
			log.Printf("Failed to write %s: %v", destPath, err)
			writer.Close()
			reader.Close()
			fileCount++
			continue
		}

		writer.Close()
		reader.Close()
		restoredCount++
		fileCount++
	}

	agent.sendResponse(connID, Response{
		Type: "complete", RequestID: cmd.RequestID, Progress: 100,
		Data: map[string]interface{}{
			"server_name":    srv.Name,
			"backup_file":    backupPath,
			"files_restored": restoredCount,
		},
	})
}

func (agent *ARKAgent) verifyBackup(connID string, cmd Command) {
	var backupPath string
	if params, ok := cmd.Params.(map[string]interface{}); ok {
		if bp, ok := params["backup_path"].(string); ok {
			backupPath = bp
		}
	}

	if backupPath == "" {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: "backup_path parameter is required",
		})
		return
	}

	stat, err := os.Stat(backupPath)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type: "complete", RequestID: cmd.RequestID,
			Data: map[string]interface{}{
				"exists":      false,
				"backup_file": backupPath,
				"error":       fmt.Sprintf("File not found: %v", err),
			},
		})
		return
	}

	sizeMB := float64(stat.Size()) / (1024 * 1024)
	agent.sendResponse(connID, Response{
		Type: "complete", RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"exists":      true,
			"backup_file": backupPath,
			"size_mb":     fmt.Sprintf("%.1f", sizeMB),
		},
	})
}

// New handlers for INI and config management

func (agent *ARKAgent) readINI(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	// Determine which INI file to read
	fileName := "GameUserSettings.ini"
	if params, ok := cmd.Params.(map[string]interface{}); ok {
		if f, ok := params["file_name"].(string); ok && f != "" {
			fileName = f
		}
	}

	iniPath := filepath.Join(srv.InstallPath, "ShooterGame", "Saved", "Config", "WindowsServer", fileName)

	data, err := os.ReadFile(iniPath)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Cannot read %s: %v", iniPath, err),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "complete",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"file_path": iniPath,
			"file_name": fileName,
			"content":   string(data),
			"size":      len(data),
		},
	})
}

func (agent *ARKAgent) writeINI(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	params, ok := cmd.Params.(map[string]interface{})
	if !ok {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: "Missing params (file_name, content required)",
		})
		return
	}

	fileName, _ := params["file_name"].(string)
	content, _ := params["content"].(string)
	if fileName == "" || content == "" {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: "file_name and content are required",
		})
		return
	}

	iniPath := filepath.Join(srv.InstallPath, "ShooterGame", "Saved", "Config", "WindowsServer", fileName)

	// Create backup before writing
	backupPath := iniPath + ".bak"
	if existingData, err := os.ReadFile(iniPath); err == nil {
		os.WriteFile(backupPath, existingData, 0644)
	}

	err := os.WriteFile(iniPath, []byte(content), 0644)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Failed to write %s: %v", iniPath, err),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "complete",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"file_path":     iniPath,
			"backup":        backupPath,
			"bytes_written": len(content),
		},
	})
}

func (agent *ARKAgent) updateIniSetting(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	params, ok := cmd.Params.(map[string]interface{})
	if !ok {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: "Missing params (file_name, section, key, value required)",
		})
		return
	}

	fileName, _ := params["file_name"].(string)
	section, _ := params["section"].(string)
	key, _ := params["key"].(string)
	value, _ := params["value"].(string)

	if fileName == "" || section == "" || key == "" {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: "file_name, section, and key are required",
		})
		return
	}

	iniPath := filepath.Join(srv.InstallPath, "ShooterGame", "Saved", "Config", "WindowsServer", fileName)

	data, err := os.ReadFile(iniPath)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Cannot read %s: %v", iniPath, err),
		})
		return
	}

	content := string(data)
	lines := strings.Split(content, "\n")

	inTargetSection := false
	sectionHeader := "[" + section + "]"
	found := false

	for i, line := range lines {
		trimmed := strings.TrimSpace(line)

		if strings.HasPrefix(trimmed, "[") && strings.HasSuffix(trimmed, "]") {
			inTargetSection = (trimmed == sectionHeader)
			continue
		}

		if inTargetSection && strings.Contains(line, "=") {
			eqPos := strings.Index(line, "=")
			currentKey := strings.TrimSpace(line[:eqPos])

			if currentKey == key {
				indent := ""
				for _, ch := range line {
					if ch == ' ' || ch == '\t' {
						indent += string(ch)
					} else {
						break
					}
				}
				lines[i] = indent + key + "=" + value
				found = true
				break
			}
		}
	}

	if !found {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Key '%s' not found in section '[%s]'", key, section),
		})
		return
	}

	backupPath := iniPath + ".bak"
	os.WriteFile(backupPath, data, 0644)

	newContent := strings.Join(lines, "\n")
	err = os.WriteFile(iniPath, []byte(newContent), 0644)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Failed to write %s: %v", iniPath, err),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "complete",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"file_path": iniPath,
			"backup":    backupPath,
			"section":   section,
			"key":       key,
			"value":     value,
		},
	})
}

func (agent *ARKAgent) getServerConfig(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	config := map[string]interface{}{
		"name":         srv.Name,
		"service_name": srv.ServiceName,
		"install_path": srv.InstallPath,
		"rcon_port":    srv.RCONPort,
	}

	// Try to read GameUserSettings.ini for max_players and other settings
	iniPath := filepath.Join(srv.InstallPath, "ShooterGame", "Saved", "Config", "WindowsServer", "GameUserSettings.ini")
	if data, err := os.ReadFile(iniPath); err == nil {
		content := string(data)
		lines := strings.Split(content, "\n")
		for _, line := range lines {
			line = strings.TrimSpace(line)
			if strings.HasPrefix(line, "MaxPlayers=") {
				config["max_players"] = strings.TrimPrefix(line, "MaxPlayers=")
			} else if strings.HasPrefix(line, "ServerName=") {
				config["server_name_ini"] = strings.TrimPrefix(line, "ServerName=")
			} else if strings.HasPrefix(line, "ServerPassword=") {
				config["has_password"] = strings.TrimPrefix(line, "ServerPassword=") != ""
			} else if strings.HasPrefix(line, "MapName=") || strings.HasPrefix(line, "MapRotation=") {
				// Sometimes map is in the INI
				config["map_name_ini"] = strings.TrimPrefix(line, "MapName=")
			}
		}
	}

	// Check service status
	state, _ := agent.queryServiceState(srv.ServiceName)
	config["service_state"] = state
	config["online"] = state == "RUNNING"

	agent.sendResponse(connID, Response{
		Type:      "complete",
		RequestID: cmd.RequestID,
		Data:      config,
	})
}

// checkUpdate checks if a Steam update is available for the server
func (agent *ARKAgent) checkUpdate(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	// Get current version from log file
	currentVersion := ""
	logPath := filepath.Join(srv.InstallPath, "ShooterGame", "Saved", "Logs", "ShooterGame.log")
	if _, err := os.Stat(logPath); err == nil {
		currentVersion = parseARKVersionFromLog(logPath)
	}

	// Try to find SteamCMD - ONLY use configured path from bot
	steamcmdPaths := []string{}

	// Only check if server has a configured steamcmd_path
	if srv.SteamCMDPath != "" {
		steamcmdPaths = append(steamcmdPaths, srv.SteamCMDPath)
	}

	var steamcmdPath string
	for _, p := range steamcmdPaths {
		if _, err := os.Stat(p); err == nil {
			steamcmdPath = p
			break
		}
	}

	if steamcmdPath == "" {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: "SteamCMD not found",
		})
		return
	}

	// Get latest version using SteamCMD
	// This runs steamcmd +app_update 2430930 -beta -validate to check for updates
	// For now, just return current version info
	result := map[string]interface{}{
		"server_name":      srv.Name,
		"current_version":  currentVersion,
		"install_path":     srv.InstallPath,
		"steamcmd_path":    steamcmdPath,
		"app_id":           "2430930", // ASA
		"update_available": false,     // Would need Steam API to check properly
	}

	agent.sendResponse(connID, Response{
		Type:      "complete",
		RequestID: cmd.RequestID,
		Data:      result,
	})
}

func (agent *ARKAgent) getMods(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	serviceName := srv.ServiceName
	if serviceName == "" {
		serviceName = cmd.Server
	}

	// Read from PhoenixARK registry — use serviceName (registry key), not display name
	phoenixConfig, err := ReadServerConfig(serviceName)
	if err != nil || phoenixConfig == nil {
		agent.sendResponse(connID, Response{
			Type:      "complete",
			RequestID: cmd.RequestID,
			Data: map[string]interface{}{
				"server_name":  cmd.Server,
				"service_name": serviceName,
				"mod_ids":      []string{},
				"raw_params":   "",
				"source":       "phoenix_registry",
			},
		})
		return
	}

	modIDs := []string{}
	if phoenixConfig.Mods != "" {
		modIDs = strings.Split(phoenixConfig.Mods, ",")
		// Trim whitespace from each mod ID
		for i := range modIDs {
			modIDs[i] = strings.TrimSpace(modIDs[i])
		}
	}

	agent.sendResponse(connID, Response{
		Type:      "complete",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"server_name":  cmd.Server,
			"service_name": serviceName,
			"mod_ids":      modIDs,
			"raw_params":   phoenixConfig.Mods,
			"source":       "phoenix_registry",
		},
	})
}

func parseModsFromRegistry(regOutput string) []string {
	reQuoted := regexp.MustCompile(`-mods="([^"]+)"`)
	if matches := reQuoted.FindStringSubmatch(regOutput); len(matches) > 1 {
		return strings.Split(matches[1], ",")
	}

	reUnquoted := regexp.MustCompile(`-mods=([0-9,\s]+?)(?:\s|$|-)`)
	if matches := reUnquoted.FindStringSubmatch(regOutput); len(matches) > 1 {
		modsStr := strings.TrimSpace(matches[1])
		return strings.Split(modsStr, ",")
	}

	return []string{}
}

func (agent *ARKAgent) setMods(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	params, ok := cmd.Params.(map[string]interface{})
	if !ok {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: "Missing params (mod_ids required)",
		})
		return
	}

	var modIDs []string
	if ids, ok := params["mod_ids"].([]interface{}); ok {
		for _, id := range ids {
			if str, ok := id.(string); ok {
				modIDs = append(modIDs, str)
			}
		}
	} else if ids, ok := params["mod_ids"].(string); ok {
		if ids != "" {
			modIDs = strings.Split(ids, ",")
		}
	}

	setModsServiceName := srv.ServiceName
	if setModsServiceName == "" {
		setModsServiceName = cmd.Server
	}

	// Read current config from PhoenixARK registry — use serviceName (registry key)
	currentConfig, err := ReadServerConfig(setModsServiceName)
	if err != nil || currentConfig == nil {
		currentConfig = &ServerConfig{}
	}

	previousMods := currentConfig.Mods

	// Update mods in PhoenixARK registry
	modsString := ""
	if len(modIDs) > 0 {
		modsString = strings.Join(modIDs, ",")
	}

	currentConfig.Mods = modsString

	if err := WriteServerConfig(setModsServiceName, currentConfig); err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Failed to update PhoenixARK registry: %v", err),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "complete",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"server_name":      cmd.Server,
			"mod_ids":          modIDs,
			"previous_mods":    previousMods,
			"new_mods":         modsString,
			"restart_required": true,
			"source":           "phoenix_registry",
		},
	})
}

func (agent *ARKAgent) detectClusterIDs(connID string, cmd Command) {
	logInfo("Detecting cluster IDs from filesystem")

	// Extract cluster_root_path from params
	params, ok := cmd.Params.(map[string]interface{})
	if !ok {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "Invalid params format",
		})
		return
	}

	clusterRootPath, ok := params["cluster_root_path"].(string)
	if !ok || clusterRootPath == "" {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "cluster_root_path parameter required",
		})
		return
	}

	// Build path to clusters directory
	clustersDir := filepath.Join(clusterRootPath, "clusters")
	logInfo(fmt.Sprintf("Scanning for cluster IDs in: %s", clustersDir))

	// Check if clusters directory exists
	if _, err := os.Stat(clustersDir); os.IsNotExist(err) {
		agent.sendResponse(connID, Response{
			Type:      "complete",
			RequestID: cmd.RequestID,
			Data: map[string]interface{}{
				"cluster_ids": []string{},
				"message":     fmt.Sprintf("Clusters directory does not exist: %s", clustersDir),
			},
		})
		return
	}

	// Read directory entries
	entries, err := os.ReadDir(clustersDir)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Failed to read clusters directory: %v", err),
		})
		return
	}

	// Collect cluster IDs (directory names)
	var clusterIDs []string
	for _, entry := range entries {
		if entry.IsDir() {
			clusterIDs = append(clusterIDs, entry.Name())
			logInfo(fmt.Sprintf("Found cluster ID: %s", entry.Name()))
		}
	}

	agent.sendResponse(connID, Response{
		Type:      "complete",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"cluster_ids": clusterIDs,
			"count":       len(clusterIDs),
		},
	})
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func (agent *ARKAgent) sendResponse(connID string, response Response) {
	agent.connMu.RLock()
	conn, exists := agent.connections[connID]
	agent.connMu.RUnlock()
	if !exists {
		return
	}

	data, err := json.Marshal(response)
	if err != nil {
		log.Printf("Failed to marshal response: %v", err)
		return
	}

	agent.writeMu.Lock()
	err = conn.WriteMessage(websocket.TextMessage, data)
	agent.writeMu.Unlock()
	if err != nil {
		log.Printf("Failed to send response: %v", err)
		agent.connMu.Lock()
		delete(agent.connections, connID)
		agent.connMu.Unlock()
	}
}

// broadcastResponse sends a response to all connected clients safely.
func (agent *ARKAgent) broadcastResponse(response Response) {
	agent.connMu.RLock()
	snapshot := make(map[string]*websocket.Conn, len(agent.connections))
	for id, c := range agent.connections {
		snapshot[id] = c
	}
	agent.connMu.RUnlock()

	for connID, conn := range snapshot {
		agent.writeMu.Lock()
		err := conn.WriteJSON(response)
		agent.writeMu.Unlock()
		if err != nil {
			logError(fmt.Sprintf("Failed to broadcast to %s: %v", connID, err))
			agent.connMu.Lock()
			delete(agent.connections, connID)
			agent.connMu.Unlock()
		}
	}
}

// runSteamCMDUpdate executes SteamCMD to update an ARK server, calling progressFn
// with (percent 0-100, statusLine) as output is processed. Returns an error on failure.
func (agent *ARKAgent) runSteamCMDUpdate(cmd Command, srv *ARKServer, serverPath string, steamcmdPaths []string, arkAppID int, doValidate bool, useCustomScript bool, progressFn func(int, string)) error {
	var steamcmdPath string
	for _, p := range steamcmdPaths {
		if _, err := os.Stat(p); err == nil {
			steamcmdPath = p
			break
		}
	}
	if steamcmdPath == "" {
		return fmt.Errorf("SteamCMD not found. Checked: %s", strings.Join(steamcmdPaths, ", "))
	}
	progressFn(5, fmt.Sprintf("Found SteamCMD at %s", steamcmdPath))

	var cmd2 *exec.Cmd
	var stdout io.Reader
	var cmdErr error

	if useCustomScript && serverPath != "" {
		// steamcmd_path from the bot is the SteamCMD directory, not a file path.
		// Use it directly; only call filepath.Dir if it actually points to a file.
		steamcmdDir := steamcmdPath
		if info, err := os.Stat(steamcmdPath); err == nil && !info.IsDir() {
			steamcmdDir = filepath.Dir(steamcmdPath)
		}
		tempFile := filepath.Join(os.TempDir(), fmt.Sprintf("ark_update_%s.bat", cmd.Server))
		validateFlag := ""
		if doValidate {
			validateFlag = "validate"
		}
		batchScript := fmt.Sprintf(`@echo off
set STEAMCMDDIR=%s
set SERVERDIR=%s
set ARKAPPID=%d
cd /d %%STEAMCMDDIR%%
del steamcmd.exe
timeout /t 5 /nobreak >nul
curl -o steamcmd.zip https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip
powershell Expand-Archive -Path .\steamcmd.zip -DestinationPath .\
start "" /wait steamcmd.exe +force_install_dir "%%SERVERDIR%%" +login anonymous +app_update %%ARKAPPID%% %s +quit
`, steamcmdDir, serverPath, arkAppID, validateFlag)
		if err := os.WriteFile(tempFile, []byte(batchScript), 0644); err != nil {
			return fmt.Errorf("failed to create update script: %v", err)
		}
		defer os.Remove(tempFile)
		progressFn(10, "Running SteamCMD update script...")
		cmd2 = exec.Command("cmd", "/c", tempFile)
		cmd2.Dir = steamcmdDir
		stdout, cmdErr = cmd2.StdoutPipe()
		if cmdErr != nil {
			return fmt.Errorf("failed to create pipe: %v", cmdErr)
		}
		cmd2.Stderr = cmd2.Stdout
	} else {
		installPath := serverPath
		if installPath == "" {
			installPath = srv.InstallPath
		}
		var steamcmdDir string
		if srv.SteamCMDPath != "" {
			steamcmdDir = filepath.Dir(srv.SteamCMDPath)
		}
		if steamcmdDir == "" && steamcmdPath != "" {
			steamcmdDir = filepath.Dir(steamcmdPath)
		}
		args := []string{
			"+@ShutdownOnFailedCommand", "1",
			"+@NoPromptForPassword", "1",
			"+login", "anonymous",
			"+force_install_dir", installPath,
			"+app_update", fmt.Sprintf("%d", arkAppID),
		}
		if doValidate {
			args = append(args, "validate")
		}
		args = append(args, "+quit")
		cmd2 = exec.Command(steamcmdPath, args...)
		if steamcmdDir != "" {
			cmd2.Dir = steamcmdDir
		}
		stdout, cmdErr = cmd2.StdoutPipe()
		if cmdErr != nil {
			return fmt.Errorf("failed to start SteamCMD: %v", cmdErr)
		}
		cmd2.Stderr = cmd2.Stdout
	}

	if err := cmd2.Start(); err != nil {
		return fmt.Errorf("failed to launch SteamCMD: %v", err)
	}

	scanner := bufio.NewScanner(stdout)
	lineCount := 0
	for scanner.Scan() {
		line := scanner.Text()
		lineCount++
		progress := min(10+(lineCount*85/200), 95)
		lower := strings.ToLower(line)
		if strings.Contains(lower, "download") || strings.Contains(lower, "validat") ||
			strings.Contains(lower, "success") || strings.Contains(lower, "already up to date") {
			progressFn(progress, line)
		}
	}
	return cmd2.Wait()
}

// maintainServer performs an atomic stop → update → start sequence for a single ARK server.
// All steps are persisted to disk as a JobLog so the bot can query what happened even after
// a disconnect. Progress updates are streamed to the connected client throughout.
func (agent *ARKAgent) maintainServer(connID string, cmd Command) {
	srv := agent.findServer(cmd.Server)
	if srv == nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Server '%s' not found in config", cmd.Server),
		})
		return
	}

	// Parse params (same as updateServer)
	var steamcmdPaths []string
	if srv.SteamCMDPath != "" {
		steamcmdPaths = append(steamcmdPaths, srv.SteamCMDPath)
	}
	var serverPath string
	var arkAppID = 2430930
	var useCustomScript bool
	var doValidate bool
	if params, ok := cmd.Params.(map[string]interface{}); ok {
		if p, ok := params["steamcmd_path"].(string); ok && p != "" {
			steamcmdPaths = append([]string{p}, steamcmdPaths...)
		}
		if sp, ok := params["server_path"].(string); ok && sp != "" {
			serverPath = sp
		}
		if aid, ok := params["ark_appid"].(float64); ok {
			arkAppID = int(aid)
		}
		if use, ok := params["use_custom_script"].(bool); ok {
			useCustomScript = use
		}
		if validate, ok := params["validate"].(bool); ok {
			doValidate = validate
		}
	}

	// Create the persistent job log
	serverSlug := strings.ReplaceAll(strings.ToLower(cmd.Server), " ", "_")
	jobID := fmt.Sprintf("maintain_%s_%d", serverSlug, time.Now().Unix())
	job := &JobLog{
		JobID:     jobID,
		Server:    cmd.Server,
		Type:      "maintain_server",
		StartedAt: time.Now().UTC().Format(time.RFC3339),
		Status:    "running",
		Steps:     []JobStep{},
	}
	agent.jobs.Save(job)
	logInfo(fmt.Sprintf("maintainServer: started job %s for %s", jobID, cmd.Server))

	addStep := func(name, status, message string) {
		job.Steps = append(job.Steps, JobStep{
			Name:      name,
			Status:    status,
			Timestamp: time.Now().UTC().Format(time.RFC3339),
			Message:   message,
		})
		agent.jobs.Save(job)
		logInfo(fmt.Sprintf("maintainServer [%s]: step %s → %s: %s", jobID, name, status, message))
	}

	// ── Step 1: Stop ────────────────────────────────────────────────────────
	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 2,
		Status: fmt.Sprintf("[1/3] Stopping %s...", srv.ServiceName),
	})
	exec.Command("sc", "stop", srv.ServiceName).CombinedOutput()

	stopped := false
	for i := 0; i < 30; i++ {
		time.Sleep(2 * time.Second)
		state, _ := agent.queryServiceState(srv.ServiceName)
		progress := 2 + (i * 20 / 30)
		agent.sendResponse(connID, Response{
			Type: "progress", RequestID: cmd.RequestID, Progress: progress,
			Status: fmt.Sprintf("[1/3] Stopping... (%s)", state),
		})
		if state == "STOPPED" {
			stopped = true
			break
		}
	}

	if stopped {
		addStep("stop", "completed", fmt.Sprintf("Service %s stopped successfully", srv.ServiceName))
	} else {
		addStep("stop", "warning", "Stop timeout — proceeding with update anyway")
	}

	// Capture pre-update version so we can detect when the server has loaded the new one
	logPath := filepath.Join(srv.InstallPath, "ShooterGame", "Saved", "Logs", "ShooterGame.log")
	preUpdateVersion := parseARKVersionFromLog(logPath)
	logInfo(fmt.Sprintf("maintainServer: pre-update version for %s: %q", cmd.Server, preUpdateVersion))

	// ── Step 2: SteamCMD update ─────────────────────────────────────────────
	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 25,
		Status: "[2/3] Starting SteamCMD update...",
	})

	updateErr := agent.runSteamCMDUpdate(cmd, srv, serverPath, steamcmdPaths, arkAppID, doValidate, useCustomScript, func(pct int, status string) {
		mapped := 25 + pct*55/100
		agent.sendResponse(connID, Response{
			Type: "progress", RequestID: cmd.RequestID, Progress: mapped,
			Status: fmt.Sprintf("[2/3] %s", status),
		})
	})

	if updateErr != nil {
		addStep("update", "failed", fmt.Sprintf("SteamCMD error: %v", updateErr))
		job.Status = "failed"
		job.CompletedAt = time.Now().UTC().Format(time.RFC3339)
		agent.jobs.Save(job)
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Update failed for %s: %v (job: %s)", cmd.Server, updateErr, jobID),
		})
		return
	}
	addStep("update", "completed", "SteamCMD update completed successfully")

	// ── Step 3: Start ────────────────────────────────────────────────────────
	agent.sendResponse(connID, Response{
		Type: "progress", RequestID: cmd.RequestID, Progress: 82,
		Status: fmt.Sprintf("[3/3] Starting %s...", srv.ServiceName),
	})

	out, err := exec.Command("sc", "start", srv.ServiceName).CombinedOutput()
	if err != nil {
		addStep("start", "failed", fmt.Sprintf("sc start error: %s %s", err, string(out)))
		job.Status = "failed"
		job.CompletedAt = time.Now().UTC().Format(time.RFC3339)
		agent.jobs.Save(job)
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Failed to start %s after update: %v (job: %s)", cmd.Server, err, jobID),
		})
		return
	}

	started := false
	for i := 0; i < 60; i++ {
		time.Sleep(2 * time.Second)
		state, _ := agent.queryServiceState(srv.ServiceName)
		progress := 82 + (i * 17 / 60)
		agent.sendResponse(connID, Response{
			Type: "progress", RequestID: cmd.RequestID, Progress: progress,
			Status: fmt.Sprintf("[3/3] Starting... (%s)", state),
		})
		if state == "RUNNING" {
			started = true
			// Poll ShooterGame.log until the version changes from the pre-update value.
			// ARK takes several minutes to load and write a new version entry — 5s is not enough.
			go func() {
				defer func() {
					if r := recover(); r != nil {
						logError(fmt.Sprintf("PANIC in maintainServer post-start version update: %v", r))
					}
				}()
				// Poll every 15s for up to ~8 minutes (32 iterations)
				for i := 0; i < 32; i++ {
					time.Sleep(15 * time.Second)
					version := parseARKVersionFromLog(logPath)
					if version != "" && version != preUpdateVersion {
						agent.broadcastResponse(Response{
							Type: "ark_version_update",
							Data: map[string]interface{}{
								"server_name": srv.Name,
								"ark_version": version,
							},
						})
						logInfo(fmt.Sprintf("maintainServer: version updated %s → %s for %s", preUpdateVersion, version, srv.Name))
						return
					}
				}
				// Max wait reached — log that version didn't change (server may not have updated)
				logInfo(fmt.Sprintf("maintainServer: version still %q after max wait for %s", preUpdateVersion, srv.Name))
			}()
			break
		}
	}

	if started {
		addStep("start", "completed", fmt.Sprintf("Service %s running", srv.ServiceName))
	} else {
		addStep("start", "warning", "Start timeout — service may still be loading")
	}

	job.Status = "completed"
	job.CompletedAt = time.Now().UTC().Format(time.RFC3339)
	agent.jobs.Save(job)
	logInfo(fmt.Sprintf("maintainServer: job %s completed for %s", jobID, cmd.Server))

	agent.sendResponse(connID, Response{
		Type: "complete", RequestID: cmd.RequestID, Progress: 100,
		Data: map[string]interface{}{
			"message": fmt.Sprintf("Server %s maintained successfully (stop → update → start)", cmd.Server),
			"job_id":  jobID,
		},
	})
}

// getJobLogs returns recent job log entries for a server (or all servers if cmd.Server is empty).
func (agent *ARKAgent) getJobLogs(connID string, cmd Command) {
	serverName := cmd.Server
	limit := 10
	if params, ok := cmd.Params.(map[string]interface{}); ok {
		if n, ok := params["limit"].(float64); ok && n > 0 {
			limit = int(n)
		}
	}
	jobs, err := agent.jobs.LoadRecent(serverName, limit)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type: "error", RequestID: cmd.RequestID,
			Error: fmt.Sprintf("Failed to load job logs: %v", err),
		})
		return
	}
	agent.sendResponse(connID, Response{
		Type: "complete", RequestID: cmd.RequestID,
		Data: jobs,
	})
}

func (agent *ARKAgent) handleDebug(w http.ResponseWriter, r *http.Request) {
	// Return current config for debugging
	w.Header().Set("Content-Type", "application/json")

	debugInfo := map[string]interface{}{
		"current_auth_key":   agent.config.AuthKey,
		"service_name":       agent.config.ServiceName,
		"port":               agent.config.Port,
		"active_connections": len(agent.connections),
	}

	json.NewEncoder(w).Encode(debugInfo)
}

func (agent *ARKAgent) handleStatus(w http.ResponseWriter, r *http.Request) {
	uptime := time.Since(agent.startTime)
	hours := int(uptime.Hours())
	minutes := int(uptime.Minutes()) % 60
	var uptimeStr string
	if hours > 0 {
		uptimeStr = fmt.Sprintf("%d hours %d minutes", hours, minutes)
	} else {
		uptimeStr = fmt.Sprintf("%d minutes", minutes)
	}
	status := map[string]interface{}{
		"agent_version": AgentVersion,
		"uptime":        uptimeStr,
		"connections":   len(agent.connections),
		"servers":       len(agent.config.ARKServers),
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(status)
}

func (agent *ARKAgent) handleServers(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(agent.config.ARKServers)
}

func (agent *ARKAgent) handleCommand(w http.ResponseWriter, r *http.Request) {
	var cmd Command
	if err := json.NewDecoder(r.Body).Decode(&cmd); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Process command (simplified for REST endpoint)
	go agent.processCommand("rest", cmd)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "command_queued"})
}

func (agent *ARKAgent) start() error {
	logInfo("=== Starting Phoenix ARK Agent ===")

	if err := agent.loadConfig(); err != nil {
		logError(fmt.Sprintf("Failed to load config: %v", err))
		return fmt.Errorf("failed to load config: %v", err)
	}
	logInfo("Configuration loaded successfully")
	logInfo(fmt.Sprintf("Port: %d", agent.config.Port))
	logInfo(fmt.Sprintf("Auth Key: %s", agent.config.AuthKey))
	logInfo(fmt.Sprintf("Configured servers: %d", len(agent.config.ARKServers)))

	// Update ARK versions for all servers on startup
	// This runs once during agent startup/restart
	go func() {
		defer func() {
			if r := recover(); r != nil {
				logError(fmt.Sprintf("PANIC in initial ARK version update: %v", r))
			}
		}()
		logInfo("Scheduling initial ARK version update...")
		// Wait a moment for the agent to fully start
		time.Sleep(2 * time.Second)
		logInfo("Starting initial ARK version update...")
		agent.updateARKVersions()
	}()

	agent.setupRoutes()
	logInfo("HTTP routes configured")

	logInfo(fmt.Sprintf("Starting ARK Agent on port %d", agent.config.Port))
	return agent.server.ListenAndServe()
}

func (agent *ARKAgent) stop() error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	return agent.server.Shutdown(ctx)
}

// ============================================================================
// Phase 16: ARK Server Service Management Handlers
// ============================================================================

func (agent *ARKAgent) createServerService(connID string, cmd Command) {
	logInfo(fmt.Sprintf("createServerService: %+v", cmd))

	// Parse parameters
	params, ok := cmd.Params.(map[string]interface{})
	if !ok {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "Invalid parameters for create_server_service",
		})
		return
	}

	// Extract server name
	serverName, _ := params["server_name"].(string)
	if serverName == "" {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "server_name is required",
		})
		return
	}

	// Build ServerConfig from params
	config := &ServerConfig{
		DisplayName:     getStringParam(params, "display_name", serverName),
		GamePort:        getIntParam(params, "game_port", 7777),
		QueryPort:       getIntParam(params, "query_port", 27015),
		RCONPort:        getIntParam(params, "rcon_port", 27020),
		RCONPassword:    getStringParam(params, "rcon_password", ""),
		ServerPassword:  getStringParam(params, "server_password", ""),
		AdminPassword:   getStringParam(params, "admin_password", ""),
		MaxPlayers:      getIntParam(params, "max_players", 70),
		MapName:         getStringParam(params, "map_name", ""),
		ServerPath:      getStringParam(params, "server_path", ""),
		SteamCMDPath:    getStringParam(params, "steamcmd_path", ""),
		Mods:            getStringParam(params, "mods", ""),
		ServiceName:     getStringParam(params, "service_name", serverName),
		ClusterID:       getStringParam(params, "cluster_id", ""),
		ClusterPath:     getStringParam(params, "cluster_path", ""),
		BattlEyeEnabled: getBoolParam(params, "battleye_enabled", false),
		ActiveEvent:     getStringParam(params, "active_event", ""),
	}

	// Install the service
	if err := InstallARKServerService(serverName, config); err != nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Failed to create service: %v", err),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "create_server_service",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"server_name":  serverName,
			"service_name": config.ServiceName,
			"status":       "created",
		},
	})
}

func (agent *ARKAgent) updateServerConfig(connID string, cmd Command) {
	logInfo(fmt.Sprintf("updateServerConfig: %+v", cmd))

	params, ok := cmd.Params.(map[string]interface{})
	if !ok {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "Invalid parameters for update_server_config",
		})
		return
	}

	serverName, _ := params["server_name"].(string)
	if serverName == "" {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "server_name is required",
		})
		return
	}

	// Read existing config
	config, err := ReadServerConfig(serverName)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Failed to read existing config: %v", err),
		})
		return
	}

	if config == nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Server config not found: %s", serverName),
		})
		return
	}

	// Update fields from params
	if v, ok := params["display_name"].(string); ok {
		config.DisplayName = v
	}
	if v, ok := params["game_port"].(float64); ok {
		config.GamePort = int(v)
	}
	if v, ok := params["query_port"].(float64); ok {
		config.QueryPort = int(v)
	}
	if v, ok := params["rcon_port"].(float64); ok {
		config.RCONPort = int(v)
	}
	if v, ok := params["rcon_password"].(string); ok {
		config.RCONPassword = v
	}
	if v, ok := params["max_players"].(float64); ok {
		config.MaxPlayers = int(v)
	}
	if v, ok := params["map_name"].(string); ok {
		config.MapName = v
	}
	if v, ok := params["server_path"].(string); ok {
		config.ServerPath = v
	}
	if v, ok := params["steamcmd_path"].(string); ok {
		config.SteamCMDPath = v
	}
	if v, ok := params["mods"].(string); ok {
		config.Mods = v
	}
	if v, ok := params["cluster_id"].(string); ok {
		config.ClusterID = v
	}
	if v, ok := params["cluster_path"].(string); ok {
		config.ClusterPath = v
	}
	if v, ok := params["server_password"].(string); ok {
		config.ServerPassword = v
	}
	if v, ok := params["admin_password"].(string); ok {
		config.AdminPassword = v
	}
	if v, ok := params["active_event"].(string); ok {
		config.ActiveEvent = v
	}
	if v, ok := params["battleye_enabled"].(bool); ok {
		config.BattlEyeEnabled = v
	}

	// Write updated config
	if err := WriteServerConfig(serverName, config); err != nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Failed to update config: %v", err),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "update_server_config",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"server_name": serverName,
			"status":      "updated",
		},
	})
}

func (agent *ARKAgent) readServerConfig(connID string, cmd Command) {
	logInfo(fmt.Sprintf("readServerConfig: %+v", cmd))

	serverName := cmd.Server
	if serverName == "" {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "server_name is required",
		})
		return
	}

	config, err := ReadServerConfig(serverName)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Failed to read config: %v", err),
		})
		return
	}

	if config == nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Server config not found: %s", serverName),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "read_server_config",
		RequestID: cmd.RequestID,
		Data:      config,
	})
}

func (agent *ARKAgent) deleteServerService(connID string, cmd Command) {
	logInfo(fmt.Sprintf("deleteServerService: %+v", cmd))

	params, ok := cmd.Params.(map[string]interface{})
	if !ok {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "Invalid parameters for delete_server_service",
		})
		return
	}

	serverName, _ := params["server_name"].(string)
	serviceName, _ := params["service_name"].(string)

	if serverName == "" {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "server_name is required",
		})
		return
	}

	if serviceName == "" {
		serviceName = serverName
	}

	if err := UninstallARKServerService(serverName, serviceName); err != nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Failed to delete service: %v", err),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "delete_server_service",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"server_name":  serverName,
			"service_name": serviceName,
			"status":       "deleted",
		},
	})
}

func (agent *ARKAgent) listServerServices(connID string, cmd Command) {
	logInfo("listServerServices")

	services, err := ListARKServerServices()
	if err != nil {
		logInfo(fmt.Sprintf("ListARKServerServices error: %v", err))
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Failed to list services: %v", err),
		})
		return
	}

	logInfo(fmt.Sprintf("ListARKServerServices returned %d services", len(services)))

	// Get status for each service
	type ServiceInfo struct {
		ServiceName string `json:"service_name"`
		ServerName  string `json:"server_name"`
		Status      string `json:"status"`
	}

	var serviceList []ServiceInfo
	for _, svcName := range services {
		serverName := strings.TrimPrefix(svcName, "PhoenixARK_")
		status, _ := GetARKServerServiceStatus(svcName)
		logInfo(fmt.Sprintf("Service: %s, Server: %s, Status: %s", svcName, serverName, status))
		serviceList = append(serviceList, ServiceInfo{
			ServiceName: svcName,
			ServerName:  serverName,
			Status:      status,
		})
	}

	logInfo(fmt.Sprintf("Sending response with %d services", len(serviceList)))
	agent.sendResponse(connID, Response{
		Type:      "list_server_services",
		RequestID: cmd.RequestID,
		Data:      serviceList,
	})
}

func (agent *ARKAgent) startArkService(connID string, cmd Command) {
	logInfo(fmt.Sprintf("startArkService: %+v", cmd))

	serviceName := cmd.Server
	if serviceName == "" {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "service_name is required",
		})
		return
	}

	if err := StartARKServerService(serviceName); err != nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Failed to start service: %v", err),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "start_ark_service",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"service_name": serviceName,
			"status":       "started",
		},
	})
}

func (agent *ARKAgent) stopArkService(connID string, cmd Command) {
	logInfo(fmt.Sprintf("stopArkService: %+v", cmd))

	serviceName := cmd.Server
	if serviceName == "" {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "service_name is required",
		})
		return
	}

	if err := StopARKServerService(serviceName); err != nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Failed to stop service: %v", err),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "stop_ark_service",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"service_name": serviceName,
			"status":       "stopped",
		},
	})
}

func (agent *ARKAgent) restartArkService(connID string, cmd Command) {
	logInfo(fmt.Sprintf("restartArkService: %+v", cmd))

	serviceName := cmd.Server
	if serviceName == "" {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "service_name is required",
		})
		return
	}

	if err := RestartARKServerService(serviceName); err != nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Failed to restart service: %v", err),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "restart_ark_service",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"service_name": serviceName,
			"status":       "restarted",
		},
	})
}

func (agent *ARKAgent) getArkServiceStatus(connID string, cmd Command) {
	logInfo(fmt.Sprintf("getArkServiceStatus: %+v", cmd))

	serviceName := cmd.Server
	if serviceName == "" {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     "service_name is required",
		})
		return
	}

	status, err := GetARKServerServiceStatus(serviceName)
	if err != nil {
		agent.sendResponse(connID, Response{
			Type:      "error",
			RequestID: cmd.RequestID,
			Error:     fmt.Sprintf("Failed to get service status: %v", err),
		})
		return
	}

	agent.sendResponse(connID, Response{
		Type:      "get_ark_service_status",
		RequestID: cmd.RequestID,
		Data: map[string]interface{}{
			"service_name": serviceName,
			"status":       status,
		},
	})
}

// Helper functions for parameter extraction
func getStringParam(params map[string]interface{}, key string, defaultValue string) string {
	if v, ok := params[key].(string); ok {
		return v
	}
	return defaultValue
}

func getIntParam(params map[string]interface{}, key string, defaultValue int) int {
	if v, ok := params[key].(float64); ok {
		return int(v)
	}
	return defaultValue
}

func getBoolParam(params map[string]interface{}, key string, defaultValue bool) bool {
	if v, ok := params[key].(bool); ok {
		return v
	}
	return defaultValue
}

func generateAuthKey() string {
	return fmt.Sprintf("agent_%d", time.Now().UnixNano())
}

func generateConnectionID() string {
	return fmt.Sprintf("conn_%d", time.Now().UnixNano())
}

func runConsoleMode() {
	log.Printf("Running in console mode")
	agent := NewARKAgent()
	if err := agent.loadConfig(); err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	// Run in console mode for testing
	go func() {
		if err := agent.start(); err != nil {
			log.Printf("Agent failed: %v", err)
		}
	}()

	// Wait for interrupt
	select {}
}

func main() {
	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "console":
			runConsoleMode()
		case "service":
			runServiceMode()
		case "install":
			if err := installService(); err != nil {
				log.Fatalf("Failed to install service: %v", err)
			}
			log.Println("Service installed successfully")
		case "remove":
			if err := removeService(); err != nil {
				log.Fatalf("Failed to remove service: %v", err)
			}
			log.Println("Service removed successfully")
		case "start":
			if err := startService(); err != nil {
				log.Fatalf("Failed to start service: %v", err)
			}
			log.Println("Service started successfully")
		case "stop":
			if err := stopService(); err != nil {
				log.Fatalf("Failed to stop service: %v", err)
			}
			log.Println("Service stopped successfully")
		default:
			log.Printf("Usage: %s [console|service|install|remove|start|stop]", os.Args[0])
		}
		return
	}

	// Default: run as service
	runServiceMode()
}
