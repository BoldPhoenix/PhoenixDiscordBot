"""
Utility functions for parsing ARK server log files.
Extracts cluster information, startup parameters, and server configuration.
"""

import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import os

logger = logging.getLogger("LogParser")


async def _find_agent_for_server(server_name: str, agent_manager) -> Optional[Any]:
    """Find the remote agent responsible for a given server name.

    Returns None if no agent_manager is provided or no matching agent found.
    """
    if agent_manager is None:
        return None
    try:
        return await agent_manager.get_agent_for_server(server_name)
    except Exception:
        return None


def parse_server_startup_info(log_path: str) -> Dict[str, Any]:
    """
    Parse server startup information from ShooterGame.log.

    Extracts:
    - Cluster ID
    - Cluster folder path
    - Max players (MaxPlayers parameter)
    - Other startup parameters

    Args:
        log_path: Path to ShooterGame.log file

    Returns:
        Dictionary with extracted information
    """
    result = {
        "cluster_id": None,
        "cluster_folder_path": None,
        "max_players": None,
        "startup_params": None,
    }

    log_file = Path(log_path)
    if not log_file.exists():
        logger.warning(f"Log file does not exist: {log_path}")
        return result

    try:
        # Read the first 5000 lines (startup info is at the beginning)
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= 5000:
                    break
                lines.append(line)

        content = "".join(lines)

        # Extract cluster ID
        # Pattern: ClusterDirOverride=<path> or ClusterId=<id>
        cluster_id_match = re.search(r"ClusterId[=\s]+([^\s,\]]+)", content, re.IGNORECASE)
        if cluster_id_match:
            result["cluster_id"] = cluster_id_match.group(1).strip("\"'")

        # Extract cluster folder path
        cluster_dir_match = re.search(
            r"ClusterDirOverride[=\s]+([^\s,\]]+)", content, re.IGNORECASE
        )
        if cluster_dir_match:
            result["cluster_folder_path"] = cluster_dir_match.group(1).strip("\"'")

        # Extract max players
        # Pattern: MaxPlayers=<number> or -MaxPlayers=<number>
        max_players_match = re.search(r"-?MaxPlayers[=\s]+(\d+)", content, re.IGNORECASE)
        if max_players_match:
            result["max_players"] = int(max_players_match.group(1))

        # Extract full command line (startup parameters)
        # Pattern: Log file open, <date> (often followed by command line)
        cmd_match = re.search(r"CommandLine:\s*(.+?)(?:\r?\n|$)", content, re.IGNORECASE)
        if cmd_match:
            result["startup_params"] = cmd_match.group(1).strip()

        logger.debug(f"Parsed startup info from {log_path}: {result}")

    except Exception as e:
        logger.error(f"Failed to parse startup info from {log_path}: {e}")

    return result


def extract_cluster_info(log_path: str) -> Optional[Dict[str, str]]:
    """
    Extract just cluster information from log file.

    Args:
        log_path: Path to ShooterGame.log

    Returns:
        Dictionary with cluster_id and cluster_folder_path, or None
    """
    info = parse_server_startup_info(log_path)

    if info["cluster_id"] or info["cluster_folder_path"]:
        return {
            "cluster_id": info["cluster_id"],
            "cluster_folder_path": info["cluster_folder_path"],
        }

    return None


def detect_cluster_ids_from_filesystem(cluster_root_path: str) -> List[str]:
    """
    Detect cluster IDs by scanning the filesystem.
    
    ARK creates cluster folders at: <cluster_root_path>/clusters/<cluster_id>/
    This function scans that directory to find all cluster IDs.
    
    Args:
        cluster_root_path: Path to cluster root (e.g., R:\\PhoenixArk\\PhoenixArkCluster)
        
    Returns:
        List of cluster IDs found (folder names in clusters/ directory)
    """
    cluster_ids = []
    
    if not cluster_root_path:
        return cluster_ids
    
    clusters_dir = Path(cluster_root_path) / "clusters"
    
    if not clusters_dir.exists() or not clusters_dir.is_dir():
        logger.debug(f"Clusters directory does not exist: {clusters_dir}")
        return cluster_ids
    
    try:
        # List all subdirectories in clusters/
        for item in clusters_dir.iterdir():
            if item.is_dir():
                cluster_ids.append(item.name)
                logger.info(f"Detected cluster ID from filesystem: {item.name}")
    except Exception as e:
        logger.error(f"Failed to scan clusters directory {clusters_dir}: {e}")
    
    return cluster_ids


def extract_max_players(log_path: str) -> Optional[int]:
    """
    Extract MaxPlayers value from log file.

    Args:
        log_path: Path to ShooterGame.log

    Returns:
        Max players as integer, or None if not found
    """
    info = parse_server_startup_info(log_path)
    return info["max_players"]


def extract_ark_version(log_path: str) -> Optional[str]:
    """
    Extract ARK game version from server log file.
    
    Looks for version information in startup lines like:
    - "Build: <version>"
    - "BuildVersion: <version>"
    - "Version: <version>"
    - "Release version: <version>"
    
    Args:
        log_path: Path to ShooterGame.log file
        
    Returns:
        Version string (e.g., "1127.12"), or None if not found
    """
    log_file = Path(log_path)
    if not log_file.exists():
        logger.warning(f"Log file does not exist: {log_path}")
        return None
    
    try:
        # Read the first 3000 lines (version info is at the beginning)
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= 3000:
                    break
                lines.append(line)
        
        content = "\n".join(lines)
        
        # Try multiple patterns for version strings
        patterns = [
            r"Release version:\s+(\d+\.\d+(?:\.\d+)?)",  # Release version: 1127.12
            r"BuildVersion[=\s]+(\d+\.\d+(?:\.\d+)?)",   # BuildVersion=1127.12
            r"Build:\s+(\d+\.\d+(?:\.\d+)?)",             # Build: 1127.12
            r"Version[=\s]+(\d+\.\d+(?:\.\d+)?)",         # Version=1127.12
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                version = match.group(1)
                logger.debug(f"Extracted ARK version from {log_path}: {version}")
                return version
        
        # If no exact version found, try to find any version-like string in startup
        startup_match = re.search(r"(?:version|build):\s+(\S+)", content, re.IGNORECASE)
        if startup_match:
            version = startup_match.group(1).strip("\"'")
            return version
        
        logger.debug(f"No ARK version found in {log_path}")
        return None
        
    except Exception as e:
        logger.error(f"Failed to extract ARK version from {log_path}: {e}")
        return None
