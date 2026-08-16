package main

import (
	"fmt"
	"log"
	"time"

	"golang.org/x/sys/windows/registry"
)

// ServerConfig represents the configuration for an ARK server stored in the Windows Registry.
// Registry path: HKLM\SOFTWARE\PhoenixARK\{server_name}
type ServerConfig struct {
	DisplayName     string `json:"display_name"`
	GamePort        int    `json:"game_port"`
	QueryPort       int    `json:"query_port"`
	RCONPort        int    `json:"rcon_port"`
	RCONPassword    string `json:"rcon_password"`
	ServerPassword  string `json:"server_password"` // Server join password
	AdminPassword   string `json:"admin_password"`  // Server admin password
	MaxPlayers      int    `json:"max_players"`
	MapName         string `json:"map_name"`
	ServerPath      string `json:"server_path"`
	SteamCMDPath    string `json:"steamcmd_path"`
	Mods            string `json:"mods"` // Comma-separated mod IDs
	ServiceName     string `json:"service_name"`
	ClusterID       string `json:"cluster_id"`
	ClusterPath     string `json:"cluster_path"`
	BattlEyeEnabled bool   `json:"battleye_enabled"` // BattlEye anti-cheat
	ActiveEvent     string `json:"active_event"`     // Seasonal event name (e.g. "WinterWonderland", "Easter")
	CreatedAt       string `json:"created_at"`
	UpdatedAt       string `json:"updated_at"`
}

const (
	// RegistryRoot is the base registry path for Phoenix ARK configurations
	RegistryRoot = `SOFTWARE\PhoenixARK`
)

// getServerRegistryPath returns the full registry path for a server
func getServerRegistryPath(serverName string) string {
	return RegistryRoot + `\` + serverName
}

// ReadServerConfig reads a server configuration from the Windows Registry.
// Returns nil if the server does not exist in the registry.
func ReadServerConfig(serverName string) (*ServerConfig, error) {
	keyPath := getServerRegistryPath(serverName)

	key, err := registry.OpenKey(registry.LOCAL_MACHINE, keyPath, registry.READ)
	if err != nil {
		// Server not found in registry
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
	config.CreatedAt, _, _ = key.GetStringValue("CreatedAt")
	config.UpdatedAt, _, _ = key.GetStringValue("UpdatedAt")

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

// WriteServerConfig writes a server configuration to the Windows Registry.
// Creates the registry key if it doesn't exist.
func WriteServerConfig(serverName string, config *ServerConfig) error {
	keyPath := getServerRegistryPath(serverName)

	// Ensure the PhoenixARK root key exists
	rootKey, _, err := registry.CreateKey(registry.LOCAL_MACHINE, RegistryRoot, registry.ALL_ACCESS)
	if err != nil {
		return fmt.Errorf("failed to create PhoenixARK registry root: %v", err)
	}
	rootKey.Close()

	// Create or open the server key
	key, _, err := registry.CreateKey(registry.LOCAL_MACHINE, keyPath, registry.ALL_ACCESS)
	if err != nil {
		return fmt.Errorf("failed to create server registry key: %v", err)
	}
	defer key.Close()

	// Write string values
	if config.DisplayName != "" {
		key.SetStringValue("DisplayName", config.DisplayName)
	}
	if config.RCONPassword != "" {
		key.SetStringValue("RCONPassword", config.RCONPassword)
	}
	if config.ServerPassword != "" {
		key.SetStringValue("ServerPassword", config.ServerPassword)
	}
	if config.AdminPassword != "" {
		key.SetStringValue("AdminPassword", config.AdminPassword)
	}
	if config.MapName != "" {
		key.SetStringValue("MapName", config.MapName)
	}
	if config.ServerPath != "" {
		key.SetStringValue("ServerPath", config.ServerPath)
	}
	if config.SteamCMDPath != "" {
		key.SetStringValue("SteamCMDPath", config.SteamCMDPath)
	}
	if config.Mods != "" {
		key.SetStringValue("Mods", config.Mods)
	}
	if config.ServiceName != "" {
		key.SetStringValue("ServiceName", config.ServiceName)
	}
	if config.ClusterID != "" {
		key.SetStringValue("ClusterID", config.ClusterID)
	}
	if config.ClusterPath != "" {
		key.SetStringValue("ClusterPath", config.ClusterPath)
	}
	// Always write ActiveEvent (empty string clears a previous value)
	key.SetStringValue("ActiveEvent", config.ActiveEvent)

	// Set timestamps
	now := time.Now().UTC().Format(time.RFC3339)
	if config.CreatedAt == "" {
		key.SetStringValue("CreatedAt", now)
	}
	key.SetStringValue("UpdatedAt", now)

	// Write integer values
	key.SetDWordValue("GamePort", uint32(config.GamePort))
	key.SetDWordValue("QueryPort", uint32(config.QueryPort))
	key.SetDWordValue("RCONPort", uint32(config.RCONPort))
	key.SetDWordValue("MaxPlayers", uint32(config.MaxPlayers))

	// Write boolean values
	battlEyeVal := uint32(0)
	if config.BattlEyeEnabled {
		battlEyeVal = 1
	}
	key.SetDWordValue("BattlEyeEnabled", battlEyeVal)

	log.Printf("[Registry] Wrote config for server '%s' to %s", serverName, keyPath)
	return nil
}

// DeleteServerConfig removes a server configuration from the Windows Registry.
func DeleteServerConfig(serverName string) error {
	keyPath := getServerRegistryPath(serverName)

	// Delete the server key and all its values
	err := registry.DeleteKey(registry.LOCAL_MACHINE, keyPath)
	if err != nil {
		return fmt.Errorf("failed to delete server registry key: %v", err)
	}

	log.Printf("[Registry] Deleted config for server '%s' from %s", serverName, keyPath)
	return nil
}

// ListServerConfigs returns a list of all server names configured in the registry.
func ListServerConfigs() ([]string, error) {
	key, err := registry.OpenKey(registry.LOCAL_MACHINE, RegistryRoot, registry.READ)
	if err != nil {
		// Root key doesn't exist yet - no servers configured
		return []string{}, nil
	}
	defer key.Close()

	// Read all subkeys (each subkey is a server name)
	names, err := key.ReadSubKeyNames(-1)
	if err != nil {
		return nil, fmt.Errorf("failed to read server names from registry: %v", err)
	}

	return names, nil
}

// ServerConfigExists checks if a server configuration exists in the registry.
func ServerConfigExists(serverName string) bool {
	keyPath := getServerRegistryPath(serverName)
	key, err := registry.OpenKey(registry.LOCAL_MACHINE, keyPath, registry.READ)
	if err != nil {
		return false
	}
	key.Close()
	return true
}
