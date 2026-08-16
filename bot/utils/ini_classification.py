"""
INI Setting Classification - Determines which settings can change at runtime.

Dynamic settings can be written to INI while server is running and will take
effect on next save or via ForceUpdateDynamicConfig RCON command.

Restart-required settings MUST be written while server is stopped, or changes
will be overwritten when the server shuts down (server writes in-memory state
to INI on shutdown).
"""

from typing import Set


DYNAMIC_SETTINGS: Set[str] = {
    "TamingSpeedMultiplier",
    "HarvestAmountMultiplier",
    "HarvestHealthMultiplier",
    "XPMultiplier",
    "BabyMatureSpeedMultiplier",
    "MatingIntervalMultiplier",
    "EggHatchSpeedMultiplier",
    "MatingSpeedMultiplier",
    "BabyCuddleIntervalMultiplier",
    "BabyImprintAmountMultiplier",
    "BabyFoodConsumptionSpeedMultiplier",
    "CropGrowthSpeedMultiplier",
    "LayEggIntervalMultiplier",
    "PoopIntervalMultiplier",
    "CropDecaySpeedMultiplier",
    "ResourceNoReplenishRadiusPlayers",
    "ResourceNoReplenishRadiusStructures",
    "DinoHarvestingDamageMultiplier",
    "PlayerHarvestingDamageMultiplier",
    "DinoTurretDamageMultiplier",
    "PerPlatformMaxStructuresMultiplier",
    "StructureDamageMultiplier",
    "StructureResistanceMultiplier",
    "FuelConsumptionIntervalMultiplier",
    "CraftXPMultiplier",
    "GenericXPMultiplier",
    "HarvestXPMultiplier",
    "KillXPMultiplier",
    "SpecialXPMultiplier",
    "AutoPvEStartTimeSeconds",
    "AutoPvEStopTimeSeconds",
    "AutoPvEToggleTimeInSeconds",
}

RESTART_REQUIRED_PATTERNS: Set[str] = {
    "ServerName",
    "ServerPassword",
    "ServerAdminPassword",
    "MaxPlayers",
    "DifficultyOffset",
    "MaxDifficulty",
    "MapName",
    "ActiveMods",
    "TotalConversionMod",
    "RCONEnabled",
    "RCONPort",
    "SessionName",
    "Port",
    "QueryPort",
    "MultiHome",
    "ClusterDirOverride",
    "clusterid",
    "AltSaveDirectoryName",
}

SERVER_SPECIFIC_KEYS: Set[str] = {
    # Identity — unique per server instance
    "ServerName",
    "SessionName",
    "MapName",
    # Network — each server binds its own ports
    "Port",
    "QueryPort",
    "RCONPort",
    "MultiHome",
    # Auth — servers can have different passwords / spectator keys
    "ServerPassword",
    "ServerAdminPassword",
    "SpectatorPassword",
    # Storage — each server writes to its own save path
    "AltSaveDirectoryName",
    "ClusterDirOverride",
    # Unique GUIDs generated per server instance
    "ServerId",
}

# Entire sections that are server-specific and should be excluded from batch editing
SERVER_SPECIFIC_SECTIONS: Set[str] = {
    "MessageOfTheDay",  # MOTD content (Message, Duration, MessageSetterID) is per-server
}


def is_server_specific(key_name: str, section_name: str = "") -> bool:
    """Return True if this key/section must differ per server and should be excluded from batch edits."""
    if section_name in SERVER_SPECIFIC_SECTIONS:
        return True
    return key_name in SERVER_SPECIFIC_KEYS


GAME_INI_ALWAYS_RESTART: Set[str] = {
    "ConfigOverrideSupplyCrateItems",
    "ConfigOverrideItemCraftingCosts",
    "ConfigOverrideItemMaxQuantity",
    "ConfigAddNPCSpawnEntriesContainer",
    "ConfigSubtractNPCSpawnEntriesContainer",
    "ConfigOverrideNPCSpawnEntriesContainer",
    "DinoSpawnWeightMultipliers",
    "NPCReplacements",
    "DinoClassDamageMultipliers",
    "DinoClassResistanceMultipliers",
    "TamedDinoClassSpeedMultipliers",
    "TamedDinoClassStaminaMultipliers",
    "OverrideEngramEntries",
    "OverrideNamedEngramEntries",
    "EngramEntryAutoUnlocks",
    "LevelExperienceRampOverrides",
    "OverridePlayerLevelEngramPoints",
    "PerLevelStatsMultiplier",
    "PlayerBaseStatMultipliers",
    "MutagenLevelBoost",
    "MutagenLevelBoost_Bred",
}


def is_dynamic_setting(key_name: str, file_name: str = "GameUserSettings.ini") -> bool:
    """
    Check if a setting can be changed while the server is running.
    
    Args:
        key_name: The INI key name
        file_name: The INI file name (Game.ini or GameUserSettings.ini)
        
    Returns:
        True if the setting can be changed at runtime
    """
    if key_name in DYNAMIC_SETTINGS:
        return True
    
    if file_name == "Game.ini":
        return False
    
    if key_name in RESTART_REQUIRED_PATTERNS:
        return False
    
    for pattern in GAME_INI_ALWAYS_RESTART:
        if key_name.startswith(pattern):
            return False

    # Unknown GameUserSettings.ini keys default to dynamic — most GUS keys can be
    # changed at runtime and applied via ForceUpdateDynamicConfig.  Only keys
    # explicitly listed in RESTART_REQUIRED_PATTERNS need a restart.
    return True


def get_setting_category(key_name: str, file_name: str = "GameUserSettings.ini") -> str:
    """
    Get the category of a setting for UI display.
    
    Args:
        key_name: The INI key name
        file_name: The INI file name
        
    Returns:
        "dynamic" or "restart_required"
    """
    return "dynamic" if is_dynamic_setting(key_name, file_name) else "restart_required"


def get_category_icon(key_name: str, file_name: str = "GameUserSettings.ini") -> str:
    """
    Get an icon for the setting category.
    
    Args:
        key_name: The INI key name
        file_name: The INI file name
        
    Returns:
        Emoji icon for display
    """
    if is_dynamic_setting(key_name, file_name):
        return "🔄"
    return "🔴"


def get_apply_description(key_name: str, file_name: str = "GameUserSettings.ini", server_running: bool = True) -> str:
    """
    Get a description of how the setting will be applied.
    
    Args:
        key_name: The INI key name
        file_name: The INI file name
        server_running: Whether the server is currently running
        
    Returns:
        Human-readable description
    """
    is_dynamic = is_dynamic_setting(key_name, file_name)
    
    if is_dynamic:
        if server_running:
            return "🔄 Dynamic setting - Will apply immediately"
        return "🔄 Dynamic setting - Will apply on server start"
    
    if server_running:
        return "🔴 Restart required - Will be queued for next server stop"
    return "🔴 Restart required - Will apply immediately (server is stopped)"
