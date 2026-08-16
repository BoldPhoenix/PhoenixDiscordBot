"""
Utility for checking the latest ARK Survival Ascended version via SteamCMD.
Uses a local version mapping file to convert build IDs to version numbers.
"""

import asyncio
import logging
import re
import subprocess
import json
from pathlib import Path
from typing import Optional

logger = logging.getLogger("SteamCmdVersion")

# SteamCMD app ID for ARK Survival Ascended
ARK_APP_ID = "2430930"

# Path to version mapping file
VERSION_MAPPING_FILE = Path(__file__).parent.parent / "config" / "ark_versions.json"


def load_version_mappings() -> dict:
    """
    Load ARK version mappings from config file.
    
    Returns:
        Dict mapping build_id -> version_string
        Example: {"21015190": "75.27", "XXXXX": "76.1"}
    """
    if not VERSION_MAPPING_FILE.exists():
        logger.warning(f"Version mapping file not found at {VERSION_MAPPING_FILE}")
        return {}
    
    try:
        with open(VERSION_MAPPING_FILE, 'r') as f:
            data = json.load(f)
        
        # Convert list to dict for easy lookup
        mapping = {}
        for entry in data.get("ark_versions", []):
            build_id = entry.get("build_id")
            version = entry.get("version")
            if build_id and version:
                mapping[build_id] = version
        
        logger.info(f"Loaded {len(mapping)} version mappings")
        return mapping
        
    except Exception as e:
        logger.error(f"Failed to load version mappings: {e}")
        return {}


def build_id_to_version(build_id: Optional[str]) -> Optional[str]:
    """
    Convert a build ID to the corresponding version number.
    
    Args:
        build_id: Build ID from SteamCMD (e.g., "21015190")
        
    Returns:
        Version string (e.g., "75.27") or None if not found
        
    Example:
        version = build_id_to_version("21015190")
        # Returns: "75.27"
    """
    if not build_id:
        return None
    
    mappings = load_version_mappings()
    return mappings.get(build_id)


async def get_latest_ark_buildid(steamcmd_path: Optional[str] = None) -> Optional[str]:
    """
    Get the latest ARK Survival Ascended build ID from SteamCMD.
    
    Args:
        steamcmd_path: Path to steamcmd.exe. If None, uses standard locations.
        
    Returns:
        Build ID as string (e.g., "21015190") or None if unable to retrieve.
        
    Example:
        latest_buildid = await get_latest_ark_buildid()
        if latest_buildid:
            print(f"Latest ARK Build ID: {latest_buildid}")
    """
    
    # Determine SteamCMD path
    if not steamcmd_path:
        possible_paths = [
            Path("C:\\SteamCMD\\steamcmd.exe"),
            Path("R:\\PhoenixArk\\SteamCMD_Island\\steamcmd.exe"),
            Path("R:\\PhoenixArk\\SteamCMD_Extinction\\steamcmd.exe"),
        ]
        
        for path in possible_paths:
            if path.exists():
                steamcmd_path = str(path)
                break
    
    if not steamcmd_path:
        logger.error("SteamCMD not found in standard locations")
        return None
    
    if not Path(steamcmd_path).exists():
        logger.error(f"SteamCMD not found at {steamcmd_path}")
        return None
    
    try:
        # Run SteamCMD to get app info
        cmd = [
            steamcmd_path,
            "+login", "anonymous",
            "+app_info_print", ARK_APP_ID,
            "+quit"
        ]
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
        )
        
        if not result.stdout:
            logger.error("No output from SteamCMD")
            return None
        
        # Extract buildid from output
        # Format: "buildid"             "21015190"
        match = re.search(r'"buildid"\s+"(\d+)"', result.stdout)
        if match:
            buildid = match.group(1)
            logger.info(f"Latest ARK Build ID retrieved: {buildid}")
            return buildid
        
        logger.warning("Could not parse buildid from SteamCMD output")
        return None
        
    except subprocess.TimeoutExpired:
        logger.error("SteamCMD command timed out")
        return None
    except Exception as e:
        logger.error(f"Failed to get latest ARK build ID: {e}")
        return None


async def get_latest_ark_version(steamcmd_path: Optional[str] = None) -> Optional[str]:
    """
    Get the latest ARK Survival Ascended version string from the build ID.
    
    This is a wrapper that converts build ID to a user-friendly version number.
    For now, returns the build ID, but can be extended to map build IDs to versions.
    
    Args:
        steamcmd_path: Path to steamcmd.exe. If None, uses standard locations.
        
    Returns:
        Version string or build ID, or None if unable to retrieve.
    """
    return await get_latest_ark_buildid(steamcmd_path)


def compare_versions(current: Optional[str], latest_build_id: Optional[str]) -> dict:
    """
    Compare two ARK version strings to determine if an update is needed.
    
    Args:
        current: Current server version (e.g., "75.27", "75.27.100", None)
        latest_build_id: Latest build ID from SteamCMD (e.g., "21015190")
        
    Returns:
        Dict with keys:
            - update_needed: bool - True if update is available
            - current_version: str - Current version or "Unknown"
            - latest_version: str - Latest version or "Unknown"
            - latest_build_id: str - Latest build ID (for reference)
            - message: str - Human readable comparison message
            
    Example:
        result = compare_versions("75.27", "21015190")
        # Returns: {
        #   "update_needed": True,
        #   "current_version": "75.27",
        #   "latest_version": "76.1",
        #   "latest_build_id": "21015190",
        #   "message": "Update available: 75.27 → 76.1"
        # }
    """
    
    # Convert build ID to version number
    latest_version = None
    if latest_build_id:
        latest_version = build_id_to_version(latest_build_id)
    
    # Handle missing versions
    if not current:
        current = "Unknown"
    if not latest_version:
        latest_version = "Unknown"
    
    # If we don't have both versions, we can't compare
    if current == "Unknown" or latest_version == "Unknown":
        # If only current is unknown but we have latest, assume update needed
        if current == "Unknown" and latest_version != "Unknown":
            return {
                "update_needed": True,
                "current_version": current,
                "latest_version": latest_version,
                "latest_build_id": latest_build_id,
                "message": f"Current version unknown - cannot determine update status. Latest available: {latest_version}"
            }
        return {
            "update_needed": False,
            "current_version": current,
            "latest_version": latest_version,
            "latest_build_id": latest_build_id,
            "message": f"Cannot determine update status: Current={current}, Latest={latest_version}"
        }
    
    # Try to parse as semantic versions
    try:
        current_parts = [int(x) for x in current.split('.')]
        latest_parts = [int(x) for x in latest_version.split('.')]
        
        # Pad to same length
        max_len = max(len(current_parts), len(latest_parts))
        current_parts.extend([0] * (max_len - len(current_parts)))
        latest_parts.extend([0] * (max_len - len(latest_parts)))
        
        # Compare version tuples
        update_needed = tuple(current_parts) < tuple(latest_parts)
        
        if update_needed:
            message = f"Update available: {current} → {latest_version}"
        else:
            message = f"Up to date: {current}"
        
        return {
            "update_needed": update_needed,
            "current_version": current,
            "latest_version": latest_version,
            "latest_build_id": latest_build_id,
            "message": message
        }
        
    except (ValueError, AttributeError):
        # If we can't parse versions, we can't compare
        return {
            "update_needed": False,
            "current_version": current,
            "latest_version": latest_version,
            "latest_build_id": latest_build_id,
            "message": f"Version check inconclusive: {current} vs {latest_version}"
        }
