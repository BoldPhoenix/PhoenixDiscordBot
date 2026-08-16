package main

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"golang.org/x/sys/windows/registry"
	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/eventlog"
)

const (
	RegistryRoot = `SOFTWARE\PhoenixARK`
)

// ServerConfig represents the configuration for an ARK server
type ServerConfig struct {
	DisplayName     string
	GamePort        int
	QueryPort       int
	RCONPort        int
	RCONPassword    string
	ServerPassword  string
	AdminPassword   string
	MaxPlayers      int
	MapName         string
	ServerPath      string
	SteamCMDPath    string
	Mods            string
	ServiceName     string
	ClusterID       string
	ClusterPath     string
	BattlEyeEnabled bool
	ActiveEvent     string
}

// ARKServerService manages an ARK server process
type ARKServerService struct {
	serverName string
	config     *ServerConfig
	cmd        *exec.Cmd
	process    *os.Process
	stopping   bool
}

func main() {
	// Get server name from command-line argument
	// The service is created with: PhoenixARKServerService.exe <serverName>
	if len(os.Args) < 2 {
		log.Fatalf("Usage: PhoenixARKServerService.exe <serverName>")
	}
	serverName := os.Args[1]

	log.Printf("Phoenix ARK Server Service starting for: %s", serverName)

	// Load config from registry to get service name
	config, err := readServerConfig(serverName)
	if err != nil {
		log.Fatalf("Failed to read server config: %v", err)
	}

	serviceName := config.ServiceName
	if serviceName == "" {
		serviceName = serverName
	}

	log.Printf("Using service name: %s", serviceName)

	// Open event log
	elog, err := eventlog.Open(serviceName)
	if err != nil {
		log.Printf("Warning: Failed to open event log: %v", err)
	}
	defer func() {
		if elog != nil {
			elog.Close()
		}
	}()

	// Run as Windows service
	svc := &ARKServerService{serverName: serverName}
	if err := svc.Run(serviceName, elog); err != nil {
		log.Fatalf("Service failed: %v", err)
	}
}

func (s *ARKServerService) Run(serviceName string, elog *eventlog.Log) error {
	return svc.Run(serviceName, &serviceHandler{
		service: s,
		elog:    elog,
	})
}

type serviceHandler struct {
	service *ARKServerService
	elog    *eventlog.Log
}

func (h *serviceHandler) Execute(args []string, r <-chan svc.ChangeRequest, changes chan<- svc.Status) (ssec bool, errno uint32) {
	const cmdsAccepted = svc.AcceptStop | svc.AcceptShutdown
	changes <- svc.Status{State: svc.StartPending}

	// Load configuration from registry
	config, err := readServerConfig(h.service.serverName)
	if err != nil {
		logError(h.elog, fmt.Sprintf("Failed to read server config: %v", err))
		changes <- svc.Status{State: svc.Stopped}
		return false, 1
	}

	if config == nil {
		logError(h.elog, fmt.Sprintf("Server config not found in registry for: %s", h.service.serverName))
		changes <- svc.Status{State: svc.Stopped}
		return false, 1
	}

	h.service.config = config
	logInfo(h.elog, fmt.Sprintf("Config loaded — MaxPlayers: %d, MapName: %s, ServerPath: %s",
		config.MaxPlayers, config.MapName, config.ServerPath))

	// Start the ARK server process
	if err := h.service.startARKProcess(); err != nil {
		logError(h.elog, fmt.Sprintf("Failed to start ARK server: %v", err))
		changes <- svc.Status{State: svc.Stopped}
		return false, 1
	}

	changes <- svc.Status{State: svc.Running, Accepts: cmdsAccepted}
	logInfo(h.elog, fmt.Sprintf("ARK server service started: %s", h.service.serverName))

	// Monitor the process
	go h.service.monitorProcess(h.elog)

loop:
	for {
		select {
		case c := <-r:
			switch c.Cmd {
			case svc.Interrogate:
				changes <- c.CurrentStatus
			case svc.Stop, svc.Shutdown:
				logInfo(h.elog, "Received stop request")
				changes <- svc.Status{State: svc.StopPending}
				h.service.stopARKProcess(h.elog)
				break loop
			default:
				logError(h.elog, fmt.Sprintf("Unexpected control request #%d", c))
			}
		}
	}

	changes <- svc.Status{State: svc.Stopped}
	logInfo(h.elog, fmt.Sprintf("ARK server service stopped: %s", h.service.serverName))
	return false, 0
}

func (s *ARKServerService) startARKProcess() error {
	if s.config == nil {
		return fmt.Errorf("no configuration loaded")
	}

	// Build executable path
	// ARK: Survival Ascended uses ArkAscendedServer.exe
	exePath := filepath.Join(s.config.ServerPath, "ShooterGame", "Binaries", "Win64", "ArkAscendedServer.exe")

	// Build command line arguments
	args := buildCommandLine(s.config)

	// Log the full command line for debugging
	log.Printf("[ARKService] Server: %s | MaxPlayers: %d | Map: %s", s.serverName, s.config.MaxPlayers, s.config.MapName)
	log.Printf("[ARKService] Executable: %s", exePath)
	log.Printf("[ARKService] Args: %v", args)

	// Create the command
	s.cmd = exec.Command(exePath, args...)
	s.cmd.Dir = filepath.Dir(exePath)

	// Set environment
	s.cmd.Env = append(os.Environ(),
		fmt.Sprintf("ARK_SERVER_NAME=%s", s.serverName),
	)

	// Redirect output to log file
	logPath := filepath.Join(s.config.ServerPath, "ShooterGame", "Saved", "Logs")
	os.MkdirAll(logPath, 0755)
	logFile := filepath.Join(logPath, fmt.Sprintf("PhoenixService_%s.log", s.serverName))

	f, err := os.OpenFile(logFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err == nil {
		s.cmd.Stdout = f
		s.cmd.Stderr = f
	}

	// Start the process
	if err := s.cmd.Start(); err != nil {
		return fmt.Errorf("failed to start ARK server: %v", err)
	}

	s.process = s.cmd.Process
	log.Printf("[ARKService] Started ARK server process (PID: %d)", s.process.Pid)
	return nil
}

func (s *ARKServerService) stopARKProcess(elog *eventlog.Log) error {
	if s.process == nil {
		return nil
	}

	s.stopping = true
	defer func() { s.stopping = false }()

	// Give the process time to shut down gracefully
	time.Sleep(10 * time.Second)

	// Kill the process
	if s.process != nil {
		if err := s.process.Kill(); err != nil {
			log.Printf("[ARKService] Failed to kill process: %v", err)
			return err
		}
		log.Printf("[ARKService] Killed ARK server process")
	}

	return nil
}

func (s *ARKServerService) monitorProcess(elog *eventlog.Log) {
	for {
		if s.stopping {
			return
		}

		if s.cmd != nil {
			err := s.cmd.Wait()
			if err != nil && !s.stopping {
				log.Printf("[ARKService] ARK server process exited unexpectedly: %v", err)
				// Restart after delay
				time.Sleep(30 * time.Second)
				if !s.stopping {
					log.Printf("[ARKService] Restarting ARK server...")
					if err := s.startARKProcess(); err != nil {
						log.Printf("[ARKService] Failed to restart: %v", err)
					}
				}
			}
		}

		time.Sleep(5 * time.Second)
	}
}

func buildCommandLine(config *ServerConfig) []string {
	args := []string{config.MapName + "?listen"}

	if config.ServerPassword != "" {
		args[0] += "?ServerPassword=" + config.ServerPassword
	}
	if config.GamePort > 0 {
		args = append(args, fmt.Sprintf("-port=%d", config.GamePort))
	}
	if config.QueryPort > 0 {
		args = append(args, fmt.Sprintf("-queryport=%d", config.QueryPort))
	}
	// Always enable logs
	args = append(args, "-logs")
	if config.Mods != "" {
		args = append(args, fmt.Sprintf("-mods=%s", config.Mods))
	}
	if config.ClusterID != "" {
		args = append(args, fmt.Sprintf("-clusterid=%s", config.ClusterID))
	}
	if config.ClusterPath != "" {
		args = append(args, fmt.Sprintf("-ClusterDirOverride=%s", config.ClusterPath))
	}
	if config.ActiveEvent != "" {
		args = append(args, fmt.Sprintf("-ActiveEvent=%s", config.ActiveEvent))
	}
	if config.MaxPlayers > 0 {
		// ASA ignores -MaxPlayers (ASE-era flag) AND the GameUserSettings MaxPlayers
		// entry; -WinLiveMaxPlayers is the only cap the game honors. Field bug since
		// March: every config layer plumbed the value correctly, then the game
		// discarded the flag and defaulted to 70.
		args = append(args, fmt.Sprintf("-WinLiveMaxPlayers=%d", config.MaxPlayers))
		args = append(args, fmt.Sprintf("-MaxPlayers=%d", config.MaxPlayers))
	}
	// BattlEye: enabled by default, use -NoBattlEye to disable
	if !config.BattlEyeEnabled {
		args = append(args, "-NoBattlEye")
	}

	return args
}

func readServerConfig(serverName string) (*ServerConfig, error) {
	keyPath := RegistryRoot + `\` + serverName
	log.Printf("[ARKService] Reading registry: HKLM\\%s", keyPath)

	key, err := registry.OpenKey(registry.LOCAL_MACHINE, keyPath, registry.READ)
	if err != nil {
		log.Printf("[ARKService] Registry key not found: %v", err)
		return nil, nil
	}
	defer key.Close()

	config := &ServerConfig{}

	// Read string values
	config.DisplayName, _, _ = key.GetStringValue("DisplayName")
	config.RCONPassword, _, _ = key.GetStringValue("RCONPassword")
	config.ServerPassword, _, _ = key.GetStringValue("ServerPassword")
	config.AdminPassword, _, _ = key.GetStringValue("AdminPassword")
	config.MapName, _, _ = key.GetStringValue("MapName")
	config.ServerPath, _, _ = key.GetStringValue("ServerPath")
	config.SteamCMDPath, _, _ = key.GetStringValue("SteamCMDPath")
	config.Mods, _, _ = key.GetStringValue("Mods")
	config.ServiceName, _, _ = key.GetStringValue("ServiceName")
	config.ClusterID, _, _ = key.GetStringValue("ClusterID")
	config.ClusterPath, _, _ = key.GetStringValue("ClusterPath")
	config.ActiveEvent, _, _ = key.GetStringValue("ActiveEvent")

	// Read integer values
	gamePort, _, _ := key.GetIntegerValue("GamePort")
	config.GamePort = int(gamePort)
	queryPort, _, _ := key.GetIntegerValue("QueryPort")
	config.QueryPort = int(queryPort)
	rconPort, _, _ := key.GetIntegerValue("RCONPort")
	config.RCONPort = int(rconPort)
	maxPlayers, _, _ := key.GetIntegerValue("MaxPlayers")
	config.MaxPlayers = int(maxPlayers)

	// Read boolean values
	battlEye, _, _ := key.GetIntegerValue("BattlEyeEnabled")
	config.BattlEyeEnabled = battlEye != 0

	return config, nil
}

func logInfo(elog *eventlog.Log, message string) {
	log.Printf("[PhoenixARK] %s", message)
	if elog != nil {
		elog.Info(1000, message)
	}
}

func logError(elog *eventlog.Log, message string) {
	log.Printf("[PhoenixARK] ERROR: %s", message)
	if elog != nil {
		elog.Error(1001, message)
	}
}
