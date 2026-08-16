"""
ARK Server Utilities
Parse ARK version from logs and extract server information from registry
"""

import re
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import logging

# winreg is Windows-only
if sys.platform == 'win32':
    import winreg

logger = logging.getLogger(__name__)

# ARK Ascended App ID (Steam)
ARK_APP_ID = 2430930

class ARKParser:
    """Utility class for parsing ARK server information"""
    
    @staticmethod
    def parse_ark_version_from_log(log_path: str) -> Optional[str]:
        """
        Parse ARK version from shootergame.log file

        Args:
            log_path: Path to the shootergame.log file

        Returns:
            ARK version string or None if not found
        """
        try:
            log_file = Path(log_path)
            if not log_file.exists():
                logger.warning(f"Log file not found: {log_path}")
                return None

            # Look for version pattern in log file
            # Pattern: "ARK Version: 79.5" - exact match from PowerShell bot
            # Version appears near the start of log (after restart), so check first 200 lines
            version_pattern = re.compile(r'(?i)ARK Version:\s+(\d+(?:\.\d+)*)')

            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                # Read first 200 lines - version appears near beginning after restart
                lines = []
                for i, line in enumerate(f):
                    if i >= 200:
                        break
                    lines.append(line)

                # Check from the beginning (version appears early)
                for line in lines:
                    match = version_pattern.search(line)
                    if match:
                        version = match.group(1)
                        logger.info(f"Found ARK version {version} in log file")
                        return version

            logger.warning(f"ARK version not found in {log_path}")
            return None

        except Exception as e:
            logger.error(f"Error parsing ARK version from {log_path}: {e}")
            return None
    
    @staticmethod
    def extract_service_info(service_name: str) -> Dict[str, Any]:
        """
        Extract ARK server information from PhoenixARK Windows registry.

        Args:
            service_name: PhoenixARK service name (e.g. PhoenixArk_Aberration)

        Returns:
            Dictionary containing map_name and ark_appid
        """
        info = {
            "map_name": None,
            "ark_appid": ARK_APP_ID  # Use hard-coded App ID
        }

        # winreg is only available on Windows
        if winreg is None:
            logger.debug("PhoenixARK registry not available on non-Windows platform")
            return info

        try:
            # Open the PhoenixARK registry key for this service
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                f"SOFTWARE\\PhoenixARK\\{service_name}"
            )
            map_name, _ = winreg.QueryValueEx(key, "MapName")
            winreg.CloseKey(key)
            if map_name:
                info["map_name"] = map_name
                logger.info(f"Extracted map name '{map_name}' from PhoenixARK registry for '{service_name}'")
        except (FileNotFoundError, OSError) as e:
            logger.warning(f"Could not read PhoenixARK registry for service '{service_name}': {e}")
        except Exception as e:
            logger.error(f"Error reading PhoenixARK registry for service '{service_name}': {e}")

        return info

    # Keep old name as alias for backwards compatibility
    extract_nssm_service_info = extract_service_info
    
    @staticmethod
    def update_server_from_files(server_id: int, server_path: str, log_path: str, service_name: str) -> Dict[str, Any]:
        """
        Update server information by parsing files and registry
        
        Args:
            server_id: Server ID in database
            server_path: Path to server installation
            log_path: Path to server log file
            service_name: PhoenixARK service name

        Returns:
            Dictionary with updated information
        """
        updates = {}
        
        # Parse ARK version from log
        if log_path:
            ark_version = ARKParser.parse_ark_version_from_log(log_path)
            if ark_version:
                updates['ark_version'] = ark_version
        
        # Extract info from PhoenixARK registry
        if service_name:
            service_info = ARKParser.extract_service_info(service_name)
            if service_info.get('map_name'):
                updates['map_name'] = service_info['map_name']
            if service_info.get('ark_appid'):
                updates['ark_appid'] = service_info['ark_appid']
        
        logger.info(f"Server {server_id} updates: {updates}")
        return updates
