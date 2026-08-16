"""
Utility for extracting and caching ARK server version information.
Includes update checking against the latest SteamCMD build.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any
from bot.database import server_config_db
from bot.utils.log_parser import extract_ark_version
from bot.utils.steamcmd_version import get_latest_ark_buildid, compare_versions

logger = logging.getLogger("ArkVersion")


async def detect_and_cache_server_version(server_id: int, server_path: Optional[str]) -> Optional[str]:
    """
    Detect ARK version from server log file and cache it in database.
    
    Args:
        server_id: Database server ID
        server_path: Server installation path (e.g., R:\\PhoenixArk\\asaserver_island)
        
    Returns:
        Version string (e.g., "1127.12"), or None if not found
    """
    if not server_path:
        logger.debug(f"Cannot detect version for server {server_id}: no server_path")
        return None
    
    try:
        # Build log path
        log_path = Path(server_path) / "ShooterGame" / "Saved" / "Logs" / "ShooterGame.log"
        
        if not log_path.exists():
            logger.debug(f"Log file not found for server {server_id}: {log_path}")
            return None
        
        # Extract version from log
        version = extract_ark_version(str(log_path))
        
        if version:
            # Cache in database
            await server_config_db.update_server_ark_version(server_id, version)
            logger.info(f"Cached ARK version {version} for server {server_id}")
            return version
        else:
            logger.debug(f"Could not extract version from log for server {server_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error detecting ARK version for server {server_id}: {e}")
        return None


async def check_server_update_status(
    server_id: int, server_path: Optional[str], steamcmd_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check if a server needs an update by comparing its version against the latest.
    
    Args:
        server_id: Database server ID
        server_path: Server installation path
        steamcmd_path: Path to steamcmd.exe (optional)
        
    Returns:
        Dict with keys:
            - update_needed: bool
            - current_version: str
            - latest_build_id: str
            - message: str
            - error: Optional[str] - Error message if check failed
    """
    try:
        # Get current version from server log
        current_version = None
        if server_path:
            try:
                log_path = Path(server_path) / "ShooterGame" / "Saved" / "Logs" / "ShooterGame.log"
                if log_path.exists():
                    current_version = extract_ark_version(str(log_path))
            except Exception as e:
                logger.debug(f"Could not read current version from log: {e}")
        
        # Get latest build from SteamCMD
        latest_buildid = await get_latest_ark_buildid(steamcmd_path)
        
        if not latest_buildid:
            return {
                "update_needed": False,
                "current_version": current_version or "Unknown",
                "latest_build_id": None,
                "message": "Could not check latest version (SteamCMD unavailable)",
                "error": "SteamCMD check failed"
            }
        
        # Compare versions
        comparison = compare_versions(current_version, latest_buildid)
        
        # Update database with status
        await server_config_db.update_server_update_status(
            server_id,
            comparison["update_needed"],
            latest_buildid
        )
        
        return {
            "update_needed": comparison["update_needed"],
            "current_version": comparison["current_version"],
            "latest_version": comparison["latest_version"],
            "latest_build_id": latest_buildid,
            "message": comparison["message"],
            "error": None
        }
        
    except Exception as e:
        logger.error(f"Error checking update status for server {server_id}: {e}")
        return {
            "update_needed": False,
            "current_version": "Unknown",
            "latest_version": "Unknown",
            "latest_build_id": None,
            "message": f"Error checking updates: {e}",
            "error": str(e)
        }
        return None
