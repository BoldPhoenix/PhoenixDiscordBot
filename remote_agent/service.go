package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
	"time"

	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/eventlog"
	"golang.org/x/sys/windows/svc/mgr"
)

var (
	serviceName = "PhoenixArkAgent"
	elog        *eventlog.Log
)

func logInfo(message string) {
	log.Printf("[PhoenixArkAgent] %s", message)
	if elog != nil {
		elog.Info(1000, message)
	}
}

func logError(message string) {
	log.Printf("[PhoenixArkAgent] ERROR: %s", message)
	if elog != nil {
		elog.Error(1001, message)
	}
}

type arkagentservice struct {
	agent *ARKAgent
}

func runServiceMode() {
	isIntSess, err := svc.IsWindowsService()
	if err != nil {
		log.Fatalf("failed to determine if we are running in service: %v", err)
	}

	if !isIntSess {
		log.Printf("Not running as service, exiting")
		return
	}

	// Initialize event log
	elog, err = eventlog.Open(serviceName)
	if err != nil {
		log.Printf("failed to open event log: %v", err)
		// Continue without event log if it fails
	}
	defer func() {
		if elog != nil {
			elog.Close()
		}
	}()

	logInfo(fmt.Sprintf("Starting %s service", serviceName))
	if err := svc.Run(serviceName, &arkagentservice{}); err != nil {
		logError(fmt.Sprintf("%s service failed: %v", serviceName, err))
		return
	}
	logInfo(fmt.Sprintf("%s service stopped", serviceName))
}

func (m *arkagentservice) Execute(args []string, r <-chan svc.ChangeRequest, changes chan<- svc.Status) (ssec bool, errno uint32) {
	const cmdsAccepted = svc.AcceptStop | svc.AcceptShutdown | svc.AcceptPauseAndContinue
	changes <- svc.Status{State: svc.StartPending}

	// Initialize agent
	m.agent = NewARKAgent()
	if err := m.agent.loadConfig(); err != nil {
		logError(fmt.Sprintf("Failed to load agent config: %v", err))
		changes <- svc.Status{State: svc.Stopped}
		return false, 1
	}

	// Start agent in background
	go func() {
		if err := m.agent.start(); err != nil {
			logError(fmt.Sprintf("Agent failed to start: %v", err))
		} else {
			logInfo("ARK Agent started successfully")
		}
	}()

	changes <- svc.Status{State: svc.Running, Accepts: cmdsAccepted}
	logInfo("Phoenix ARK Agent service is now running")

loop:
	for {
		select {
		case c := <-r:
			switch c.Cmd {
			case svc.Interrogate:
				changes <- c.CurrentStatus
			case svc.Stop, svc.Shutdown:
				logInfo("Stopping ARK Agent service")
				changes <- svc.Status{State: svc.StopPending}

				// Stop agent gracefully
				if m.agent != nil {
					if err := m.agent.stop(); err != nil {
						logError(fmt.Sprintf("Error stopping agent: %v", err))
					}
				}

				break loop
			case svc.Pause:
				logInfo("Pausing ARK Agent service")
				changes <- svc.Status{State: svc.Paused, Accepts: cmdsAccepted}
			case svc.Continue:
				logInfo("Continuing ARK Agent service")
				changes <- svc.Status{State: svc.Running, Accepts: cmdsAccepted}
			default:
				logError(fmt.Sprintf("unexpected control request #%d", c))
			}
		}
	}

	changes <- svc.Status{State: svc.Stopped}
	return false, 0
}

// Windows service installation functions
func installService() error {
	// 1. Install registry keys so Windows can format our logs
	err := eventlog.InstallAsEventCreate(serviceName, eventlog.Info|eventlog.Error|eventlog.Warning)
	if err != nil {
		log.Printf("Warning: Failed to install event log source: %v", err)
		// Continue with service installation even if event log fails
	}

	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("failed to get executable path: %v", err)
	}

	// Ensure we're using the actual executable path, not a temporary one
	if filepath.Base(exePath) == "___go_build_PhoenixArkAgent.exe" {
		exePath = filepath.Join(filepath.Dir(exePath), "PhoenixArkAgent.exe")
	}

	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("failed to connect to service manager: %v", err)
	}
	defer m.Disconnect()

	s, err := m.OpenService(serviceName)
	if err == nil {
		s.Close()
		return fmt.Errorf("service %s already exists", serviceName)
	}

	s, err = m.CreateService(serviceName, exePath, mgr.Config{
		DisplayName:      "Phoenix ARK Agent",
		Description:      "Remote agent for managing ARK servers via Discord bot",
		StartType:        mgr.StartAutomatic,
		DelayedAutoStart: true,
	})
	if err != nil {
		return fmt.Errorf("failed to create service: %v", err)
	}
	defer s.Close()

	logInfo(fmt.Sprintf("Service %s installed", serviceName))
	return nil
}

func removeService() error {
	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("failed to connect to service manager: %v", err)
	}
	defer m.Disconnect()

	s, err := m.OpenService(serviceName)
	if err != nil {
		return fmt.Errorf("service %s not found", serviceName)
	}
	defer s.Close()

	if err := s.Delete(); err != nil {
		return fmt.Errorf("failed to delete service: %v", err)
	}

	logInfo(fmt.Sprintf("Service %s removed", serviceName))
	return nil
}

func startService() error {
	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("failed to connect to service manager: %v", err)
	}
	defer m.Disconnect()

	s, err := m.OpenService(serviceName)
	if err != nil {
		return fmt.Errorf("service %s not found", serviceName)
	}
	defer s.Close()

	status, err := s.Query()
	if err != nil {
		return fmt.Errorf("failed to query service status: %v", err)
	}

	if status.State != svc.Stopped {
		return fmt.Errorf("service is already running")
	}

	err = s.Start()
	if err != nil {
		return fmt.Errorf("failed to start service: %v", err)
	}

	logInfo(fmt.Sprintf("Service %s started", serviceName))
	return nil
}

func stopService() error {
	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("failed to connect to service manager: %v", err)
	}
	defer m.Disconnect()

	s, err := m.OpenService(serviceName)
	if err != nil {
		return fmt.Errorf("service %s not found", serviceName)
	}
	defer s.Close()

	_, err = s.Control(svc.Stop)
	if err != nil {
		return fmt.Errorf("failed to stop service: %v", err)
	}

	logInfo(fmt.Sprintf("Service %s stopped", serviceName))
	return nil
}

// ============================================================================
// ARK Server Service Management (Phase 16)
// ============================================================================

// InstallARKServerService creates a new Windows service for an ARK server.
// The service runs PhoenixARKServerService.exe (wrapper) which manages ShooterGameServer.exe.
func InstallARKServerService(serverName string, config *ServerConfig) error {
	// Validate required fields
	if config.ServerPath == "" {
		return fmt.Errorf("ServerPath is required")
	}
	// Use server name as service name if not specified
	if config.ServiceName == "" {
		config.ServiceName = serverName
	}
	if config.MapName == "" {
		return fmt.Errorf("MapName is required")
	}

	// Write configuration to registry first
	if err := WriteServerConfig(serverName, config); err != nil {
		return fmt.Errorf("failed to write server config to registry: %v", err)
	}

	// Get the path to PhoenixARKServerService.exe (wrapper executable)
	// It should be in the same directory as PhoenixArkAgent.exe
	agentExe, err := os.Executable()
	if err != nil {
		return fmt.Errorf("failed to get agent executable path: %v", err)
	}
	wrapperExe := filepath.Join(filepath.Dir(agentExe), "PhoenixARKServerService.exe")

	// Check if wrapper executable exists
	if _, err := os.Stat(wrapperExe); os.IsNotExist(err) {
		return fmt.Errorf("PhoenixARKServerService.exe not found at: %s", wrapperExe)
	}

	// Install event log source for the service
	eventlog.InstallAsEventCreate(config.ServiceName, eventlog.Info|eventlog.Error|eventlog.Warning)

	// Connect to service manager
	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("failed to connect to service manager: %v", err)
	}
	defer m.Disconnect()

	// Check if service already exists
	s, err := m.OpenService(config.ServiceName)
	if err == nil {
		s.Close()
		return fmt.Errorf("service %s already exists", config.ServiceName)
	}

	// Create the service
	// The wrapper exe takes the server name as an argument
	s, err = m.CreateService(config.ServiceName, wrapperExe, mgr.Config{
		DisplayName:      config.DisplayName,
		Description:      fmt.Sprintf("Phoenix ARK Server: %s (%s)", serverName, config.MapName),
		StartType:        mgr.StartAutomatic,
		DelayedAutoStart: true,
	}, serverName)
	if err != nil {
		return fmt.Errorf("failed to create service: %v", err)
	}
	defer s.Close()

	logInfo(fmt.Sprintf("Created ARK server service: %s", config.ServiceName))
	return nil
}

// UninstallARKServerService removes an ARK server service and its registry configuration.
func UninstallARKServerService(serverName string, serviceName string) error {
	// Connect to service manager
	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("failed to connect to service manager: %v", err)
	}
	defer m.Disconnect()

	// Open the service
	s, err := m.OpenService(serviceName)
	if err != nil {
		// Service doesn't exist - just clean up registry
		logInfo(fmt.Sprintf("Service %s not found, cleaning registry only", serviceName))
	} else {
		// Stop the service first if running
		status, err := s.Query()
		if err == nil && status.State == svc.Running {
			if _, err := s.Control(svc.Stop); err != nil {
				s.Close()
				return fmt.Errorf("failed to stop service: %v", err)
			}
		}

		// Delete the service (must be done before closing handle)
		if err := s.Delete(); err != nil {
			s.Close()
			return fmt.Errorf("failed to delete service: %v", err)
		}

		// Close the handle after delete
		s.Close()

		// Remove event log source
		eventlog.Remove(serviceName)
	}

	// Delete registry configuration
	DeleteServerConfig(serverName)

	logInfo(fmt.Sprintf("Removed ARK server service: %s", serviceName))
	return nil
}

// StartARKServerService starts an ARK server service.
func StartARKServerService(serviceName string) error {
	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("failed to connect to service manager: %v", err)
	}
	defer m.Disconnect()

	s, err := m.OpenService(serviceName)
	if err != nil {
		return fmt.Errorf("service %s not found: %v", serviceName, err)
	}
	defer s.Close()

	status, err := s.Query()
	if err != nil {
		return fmt.Errorf("failed to query service status: %v", err)
	}

	if status.State == svc.Running {
		return fmt.Errorf("service is already running")
	}

	err = s.Start()
	if err != nil {
		return fmt.Errorf("failed to start service: %v", err)
	}

	logInfo(fmt.Sprintf("Started service: %s", serviceName))
	return nil
}

// StopARKServerService stops an ARK server service and waits until it reaches Stopped state.
func StopARKServerService(serviceName string) error {
	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("failed to connect to service manager: %v", err)
	}
	defer m.Disconnect()

	s, err := m.OpenService(serviceName)
	if err != nil {
		return fmt.Errorf("service %s not found: %v", serviceName, err)
	}
	defer s.Close()

	status, err := s.Query()
	if err != nil {
		return fmt.Errorf("failed to query service status: %v", err)
	}

	if status.State == svc.Stopped {
		// Already stopped — treat as success
		logInfo(fmt.Sprintf("Service %s is already stopped", serviceName))
		return nil
	}

	_, err = s.Control(svc.Stop)
	if err != nil {
		return fmt.Errorf("failed to stop service: %v", err)
	}

	// Poll until service reaches Stopped state (max 60s)
	for i := 0; i < 30; i++ {
		time.Sleep(2 * time.Second)
		status, err = s.Query()
		if err != nil {
			return fmt.Errorf("failed to query service status while waiting for stop: %v", err)
		}
		if status.State == svc.Stopped {
			logInfo(fmt.Sprintf("Stopped service: %s", serviceName))
			return nil
		}
	}

	return fmt.Errorf("service %s did not stop within 60s (current state: %v)", serviceName, status.State)
}

// RestartARKServerService restarts an ARK server service, waiting for it to stop first.
func RestartARKServerService(serviceName string) error {
	// Stop and wait for stopped state
	if err := StopARKServerService(serviceName); err != nil {
		return fmt.Errorf("failed to stop service during restart: %v", err)
	}

	m, err := mgr.Connect()
	if err != nil {
		return fmt.Errorf("failed to connect to service manager: %v", err)
	}
	defer m.Disconnect()

	s, err := m.OpenService(serviceName)
	if err != nil {
		return fmt.Errorf("service %s not found: %v", serviceName, err)
	}
	defer s.Close()

	// Start the service
	if err := s.Start(); err != nil {
		return fmt.Errorf("failed to start service: %v", err)
	}

	logInfo(fmt.Sprintf("Restarted service: %s", serviceName))
	return nil
}

// GetARKServerServiceStatus returns the current status of an ARK server service.
func GetARKServerServiceStatus(serviceName string) (string, error) {
	m, err := mgr.Connect()
	if err != nil {
		return "UNKNOWN", fmt.Errorf("failed to connect to service manager: %v", err)
	}
	defer m.Disconnect()

	s, err := m.OpenService(serviceName)
	if err != nil {
		return "NOT_FOUND", nil
	}
	defer s.Close()

	status, err := s.Query()
	if err != nil {
		return "UNKNOWN", fmt.Errorf("failed to query service: %v", err)
	}

	switch status.State {
	case svc.Stopped:
		return "STOPPED", nil
	case svc.StartPending:
		return "STARTING", nil
	case svc.StopPending:
		return "STOPPING", nil
	case svc.Running:
		return "RUNNING", nil
	default:
		return "UNKNOWN", nil
	}
}

// ListARKServerServices returns a list of all Phoenix ARK server services.
func ListARKServerServices() ([]string, error) {
	// Read all server configs from registry to get service names
	serverNames, err := ListServerConfigs()
	if err != nil {
		return nil, fmt.Errorf("failed to list server configs: %v", err)
	}

	var serviceNames []string
	for _, serverName := range serverNames {
		config, err := ReadServerConfig(serverName)
		if err != nil {
			log.Printf("Warning: failed to read config for %s: %v", serverName, err)
			continue
		}
		if config != nil && config.ServiceName != "" {
			serviceNames = append(serviceNames, config.ServiceName)
		}
	}

	return serviceNames, nil
}
