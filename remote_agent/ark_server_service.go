package main

import (
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/eventlog"
	"golang.org/x/sys/windows/svc/mgr"
)

// ARKServerService is the wrapper service that manages an ARK server process.
// It runs as a Windows service and manages ShooterGameServer.exe as a child process.
type ARKServerService struct {
	serverName string
	config     *ServerConfig
	cmd        *exec.Cmd
	process    *os.Process
	stopping   bool
}

// RunARKServerService is the main entry point when running as a service.
// It determines the server name from the service name and reads config from registry.
func RunARKServerService() {
	// Get service name from command line or determine from executable context
	serviceName, err := determineServiceName()
	if err != nil {
		log.Fatalf("Failed to determine service name: %v", err)
	}

	// Extract server name from service name (PhoenixARK_TheIsland → TheIsland)
	serverName := strings.TrimPrefix(serviceName, "PhoenixARK_")
	if serverName == serviceName {
		// Service name doesn't have prefix, use as-is
		serverName = serviceName
	}

	elog, err := eventlog.Open(serviceName)
	if err != nil {
		log.Printf("Warning: Failed to open event log: %v", err)
	}
	defer func() {
		if elog != nil {
			elog.Close()
		}
	}()

	svc := &ARKServerService{
		serverName: serverName,
	}

	if err := svc.Run(serviceName, elog); err != nil {
		log.Fatalf("Service failed: %v", err)
	}
}

// determineServiceName figures out the Windows service name for this instance.
func determineServiceName() (string, error) {
	// When running as a service, the name is passed as an argument
	// or we can query the service controller
	if len(os.Args) > 1 {
		return os.Args[1], nil
	}

	// Try to determine from executable path
	exePath, err := os.Executable()
	if err != nil {
		return "", err
	}

	// The service name is typically the executable name without extension
	// But for our case, we need to query the service manager
	m, err := mgr.Connect()
	if err != nil {
		return "", fmt.Errorf("failed to connect to service manager: %v", err)
	}
	defer m.Disconnect()

	// This is a simplified approach - in production, we'd query which service
	// is running this executable
	return filepath.Base(exePath), nil
}

// Run executes the service main loop.
func (s *ARKServerService) Run(serviceName string, elog *eventlog.Log) error {
	return svc.Run(serviceName, &arkServiceHandler{
		service: s,
		elog:    elog,
	})
}

type arkServiceHandler struct {
	service *ARKServerService
	elog    *eventlog.Log
}

func (h *arkServiceHandler) Execute(args []string, r <-chan svc.ChangeRequest, changes chan<- svc.Status) (ssec bool, errno uint32) {
	const cmdsAccepted = svc.AcceptStop | svc.AcceptShutdown | svc.AcceptPauseAndContinue
	changes <- svc.Status{State: svc.StartPending}

	// Load configuration from registry
	config, err := ReadServerConfig(h.service.serverName)
	if err != nil {
		arkLogError(h.elog, fmt.Sprintf("Failed to read server config: %v", err))
		changes <- svc.Status{State: svc.Stopped}
		return false, 1
	}

	if config == nil {
		arkLogError(h.elog, fmt.Sprintf("Server config not found in registry for: %s", h.service.serverName))
		changes <- svc.Status{State: svc.Stopped}
		return false, 1
	}

	h.service.config = config

	// Start the ARK server process
	if err := h.service.startARKProcess(); err != nil {
		arkLogError(h.elog, fmt.Sprintf("Failed to start ARK server: %v", err))
		changes <- svc.Status{State: svc.Stopped}
		return false, 1
	}

	changes <- svc.Status{State: svc.Running, Accepts: cmdsAccepted}
	arkLogInfo(h.elog, fmt.Sprintf("ARK server service started: %s", h.service.serverName))

	// Monitor the process in a separate goroutine
	go h.service.monitorProcess()

loop:
	for {
		select {
		case c := <-r:
			switch c.Cmd {
			case svc.Interrogate:
				changes <- c.CurrentStatus
			case svc.Stop, svc.Shutdown:
				arkLogInfo(h.elog, "Received stop request")
				changes <- svc.Status{State: svc.StopPending}
				h.service.stopARKProcess()
				break loop
			case svc.Pause:
				arkLogInfo(h.elog, "Received pause request - ARK servers do not support pause")
				changes <- svc.Status{State: svc.Paused, Accepts: cmdsAccepted}
			case svc.Continue:
				arkLogInfo(h.elog, "Received continue request")
				changes <- svc.Status{State: svc.Running, Accepts: cmdsAccepted}
			default:
				arkLogError(h.elog, fmt.Sprintf("Unexpected control request #%d", c))
			}
		}
	}

	changes <- svc.Status{State: svc.Stopped}
	arkLogInfo(h.elog, fmt.Sprintf("ARK server service stopped: %s", h.service.serverName))
	return false, 0
}

// startARKProcess launches the ARK server executable.
func (s *ARKServerService) startARKProcess() error {
	if s.config == nil {
		return fmt.Errorf("no configuration loaded")
	}

	// Build executable path
	exePath := filepath.Join(s.config.ServerPath, "ShooterGame", "Binaries", "Win64", "ShooterGameServer.exe")

	// Build command line arguments
	args := buildARKCommandLine(s.config)

	// Create the command
	s.cmd = exec.Command(exePath, args...)
	s.cmd.Dir = filepath.Dir(exePath)

	// Set environment variables if needed
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

// stopARKProcess gracefully stops the ARK server process.
func (s *ARKServerService) stopARKProcess() error {
	if s.process == nil {
		return nil
	}

	s.stopping = true
	defer func() { s.stopping = false }()

	// Try graceful shutdown first via RCON if available
	if s.config.RCONPort > 0 && s.config.RCONPassword != "" {
		// Send "DoExit" via RCON for graceful shutdown
		// This is a simplified version - full implementation would use RCON client
		log.Printf("[ARKService] Attempting graceful shutdown via RCON")
	}

	// Give the process time to shut down gracefully
	time.Sleep(10 * time.Second)

	// Check if process is still running
	if s.process != nil {
		// Kill the process
		if err := s.process.Kill(); err != nil {
			log.Printf("[ARKService] Failed to kill process: %v", err)
			return err
		}
		log.Printf("[ARKService] Killed ARK server process")
	}

	return nil
}

// monitorProcess watches the ARK server process and restarts it if it crashes.
func (s *ARKServerService) monitorProcess() {
	for {
		if s.stopping {
			return
		}

		if s.cmd != nil {
			err := s.cmd.Wait()
			if err != nil && !s.stopping {
				log.Printf("[ARKService] ARK server process exited unexpectedly: %v", err)
				// Restart the process after a delay
				time.Sleep(30 * time.Second)
				if !s.stopping {
					log.Printf("[ARKService] Restarting ARK server...")
					if err := s.startARKProcess(); err != nil {
						log.Printf("[ARKService] Failed to restart ARK server: %v", err)
					}
				}
			}
		}

		time.Sleep(5 * time.Second)
	}
}

// buildARKCommandLine builds the command line arguments for the ARK server.
func buildARKCommandLine(config *ServerConfig) []string {
	args := []string{config.MapName + "?listen"}

	if config.GamePort > 0 {
		args = append(args, fmt.Sprintf("-port=%d", config.GamePort))
	}
	if config.QueryPort > 0 {
		args = append(args, fmt.Sprintf("-queryport=%d", config.QueryPort))
	}
	if config.RCONPort > 0 {
		args = append(args, fmt.Sprintf("-RCONPort=%d", config.RCONPort))
	}
	if config.RCONPassword != "" {
		args = append(args, fmt.Sprintf("-ServerRCONPassword=%s", config.RCONPassword))
	}
	if config.MaxPlayers > 0 {
		// ASA ignores -MaxPlayers (ASE-era flag) AND the GameUserSettings MaxPlayers
		// entry; -WinLiveMaxPlayers is the only cap the game honors. Field bug since
		// March: every config layer plumbed the value correctly, then the game
		// discarded the flag and defaulted to 70.
		args = append(args, fmt.Sprintf("-WinLiveMaxPlayers=%d", config.MaxPlayers))
		args = append(args, fmt.Sprintf("-MaxPlayers=%d", config.MaxPlayers))
	}
	if config.Mods != "" {
		args = append(args, fmt.Sprintf("-mods=%s", config.Mods))
	}
	if config.ClusterID != "" {
		args = append(args, fmt.Sprintf("-clusterid=%s", config.ClusterID))
	}
	if config.ClusterPath != "" {
		args = append(args, fmt.Sprintf("-ClusterDirOverride=%s", config.ClusterPath))
	}

	return args
}

func arkLogInfo(elog *eventlog.Log, message string) {
	log.Printf("[PhoenixARK] %s", message)
	if elog != nil {
		elog.Info(1000, message)
	}
}

func arkLogError(elog *eventlog.Log, message string) {
	log.Printf("[PhoenixARK] ERROR: %s", message)
	if elog != nil {
		elog.Error(1001, message)
	}
}
