"""
ARK ASA Save File Reader
Reads and extracts data from ARK Ascended save files (.ark, .arkprofile, .arktribe)
"""

import sqlite3
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime

from .binary_reader import BinaryReader, PropertyReader
from .simple_property_reader import extract_player_data_simple, extract_tribe_data_simple


@dataclass
class PlayerData:
    """Player character data"""

    character_name: str = ""
    player_name: str = ""
    eos_id: str = ""
    tribe_id: Optional[int] = None
    level: int = 0
    experience: float = 0.0
    lat: float = 0.0
    lon: float = 0.0
    last_seen: Optional[datetime] = None
    file_path: str = ""


@dataclass
class TribeData:
    """Tribe data"""

    tribe_id: int
    tribe_name: str = ""
    owner_name: str = ""
    member_count: int = 0
    dino_count: int = 0
    last_active: Optional[datetime] = None
    file_path: str = ""


class ArkSaveReader:
    """
    Reads ARK ASA save files (SQLite format)
    """

    def __init__(self, save_dir: Path):
        """
        Initialize reader with path to save directory

        Args:
            save_dir: Path to SavedArks directory (e.g., C:/ARK/asaserver_astraeos/.../Astraeos_WP/)
        """
        self.save_dir = Path(save_dir)
        self.world_save = self.save_dir / f"{self.save_dir.name}.ark"

    def is_valid(self) -> bool:
        """Check if save directory exists and contains valid save files"""
        return self.save_dir.exists() and self.world_save.exists()

    def get_database_info(self) -> Dict[str, Any]:
        """Get basic info about the save database"""
        if not self.world_save.exists():
            return {}

        try:
            conn = sqlite3.connect(str(self.world_save))
            cursor = conn.cursor()

            # Get table info
            cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')
            tables = [t[0] for t in cursor.fetchall()]

            info = {"tables": {}}
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                info["tables"][table] = count

            info["file_size"] = self.world_save.stat().st_size
            info["file_modified"] = datetime.fromtimestamp(self.world_save.stat().st_mtime)

            conn.close()
            return info

        except Exception as e:
            return {"error": str(e)}

    def read_save_header(self) -> Dict[str, Any]:
        """
        Read the SaveHeader from the custom table
        This contains metadata about the save
        """
        if not self.world_save.exists():
            return {}

        try:
            conn = sqlite3.connect(str(self.world_save))
            cursor = conn.cursor()

            # Get SaveHeader from custom table
            cursor.execute("SELECT value FROM custom WHERE key = ?", ("SaveHeader",))
            result = cursor.fetchone()

            if result:
                header_data = result[0]
                # Basic header parsing - first few bytes contain version info
                # Full parsing requires understanding UE5 serialization format
                header = {
                    "size": len(header_data),
                    "raw_preview": (
                        header_data[:100].hex() if len(header_data) >= 100 else header_data.hex()
                    ),
                }
                conn.close()
                return header

            conn.close()
            return {}

        except Exception as e:
            return {"error": str(e)}

    def list_profile_files(self) -> List[Path]:
        """List all .arkprofile files in save directory"""
        if not self.save_dir.exists():
            return []
        return list(self.save_dir.glob("*.arkprofile"))

    def list_tribe_files(self) -> List[Path]:
        """List all .arktribe files in save directory"""
        if not self.save_dir.exists():
            return []
        return list(self.save_dir.glob("*.arktribe"))

    def read_profile_file(self, profile_path: Path) -> Optional[PlayerData]:
        """
        Read a .arkprofile file
        These are binary files with UE5 serialization (NOT SQLite)
        """
        if not profile_path.exists():
            return None

        try:
            player = PlayerData()
            player.file_path = str(profile_path)

            # Extract EOS ID from filename (format: <eos_id>.arkprofile)
            player.eos_id = profile_path.stem

            # Get file modification time as last seen
            file_stat = profile_path.stat()
            player.last_seen = datetime.fromtimestamp(file_stat.st_mtime)

            # Extract detailed player data using enhanced parser
            try:
                player_data = extract_player_data_simple(profile_path, player.eos_id)
                if player_data:
                    player.player_name = player_data.get("player_name", "")
                    player.character_name = player_data.get("character_name", "")
                    player.tribe_id = player_data.get("tribe_id")
                    player.level = player_data.get("level", 1)
                    player.experience = player_data.get("experience", 0.0)
            except Exception as parse_error:
                # Parsing failed - keep basic metadata
                pass

            return player

        except Exception as e:
            print(f"Error reading profile {profile_path}: {e}")
            return None

    def read_tribe_file(self, tribe_path: Path) -> Optional[TribeData]:
        """
        Read a .arktribe file
        These are binary files with UE5 serialization (NOT SQLite)
        """
        if not tribe_path.exists():
            return None

        try:
            # Get tribe ID from filename
            tribe_id = int(tribe_path.stem)

            tribe = TribeData(tribe_id=tribe_id)
            tribe.file_path = str(tribe_path)

            # Get file modification time
            file_stat = tribe_path.stat()
            tribe.last_active = datetime.fromtimestamp(file_stat.st_mtime)

            # Extract detailed tribe data using enhanced parser
            try:
                tribe_data = extract_tribe_data_simple(tribe_path, tribe_id)
                if tribe_data:
                    tribe.tribe_name = tribe_data.get("tribe_name", "")
                    tribe.owner_name = f"ID:{tribe_data.get('owner_id', 0)}"
                    members = tribe_data.get("members", [])
                    tribe.member_count = len(members)
                    # Could extract dino count from TamedDinoCount property if needed
            except Exception as parse_error:
                # Parsing failed - keep basic metadata
                pass

            return tribe

        except Exception as e:
            print(f"Error reading tribe {tribe_path}: {e}")
            return None

    def get_all_players(self) -> List[PlayerData]:
        """Get all player data from profile files"""
        players = []
        for profile_path in self.list_profile_files():
            player = self.read_profile_file(profile_path)
            if player:
                players.append(player)
        return players

    def get_all_tribes(self) -> List[TribeData]:
        """Get all tribe data from tribe files"""
        tribes = []
        for tribe_path in self.list_tribe_files():
            tribe = self.read_tribe_file(tribe_path)
            if tribe:
                tribes.append(tribe)
        return tribes


def scan_all_servers(cluster_root: Path) -> Dict[str, ArkSaveReader]:
    """
    Scan all ASA servers in cluster and create readers

    Args:
        cluster_root: Path to cluster root (e.g., C:/ARK)

    Returns:
        Dict mapping server name to ArkSaveReader
    """
    readers = {}

    for server_dir in cluster_root.glob("asaserver_*"):
        if not server_dir.is_dir():
            continue

        # Find SavedArks directory
        saved_arks_dir = server_dir / "ShooterGame" / "Saved" / "SavedArks"
        if not saved_arks_dir.exists():
            continue

        # Find the map directory (should be only one)
        for map_dir in saved_arks_dir.iterdir():
            if map_dir.is_dir():
                reader = ArkSaveReader(map_dir)
                if reader.is_valid():
                    server_name = server_dir.name.replace("asaserver_", "")
                    readers[server_name] = reader
                break

    return readers
