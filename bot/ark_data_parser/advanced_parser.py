"""
Advanced ARK Save Parser
Implements deeper understanding of ARK's UE5 save format
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import struct

from .binary_reader import BinaryReader, PropertyReader


@dataclass
class ArkProfileData:
    """Detailed ARK player profile data"""

    eos_id: str
    player_name: str = ""
    character_name: str = ""
    tribe_id: Optional[int] = None
    level: int = 0
    experience: float = 0.0
    spawned_at_level: int = 0
    num_level_ups_applied: int = 0

    # Stats
    health: float = 0.0
    stamina: float = 0.0
    oxygen: float = 0.0
    food: float = 0.0
    water: float = 0.0
    weight: float = 0.0
    melee_damage: float = 0.0
    movement_speed: float = 0.0

    # Coordinates
    spawn_region_index: int = 0

    # File metadata
    file_path: str = ""
    file_size: int = 0


@dataclass
class ArkTribeData:
    """Detailed ARK tribe data"""

    tribe_id: int
    tribe_name: str = ""
    owner_player_data_id: int = 0
    tribe_rank_groups: List[str] = None
    set_government: int = 0

    # Members
    members_player_name: List[str] = None
    members_player_data_id: List[int] = None
    tribe_admins: List[int] = None

    # Stats
    num_tribe_members: int = 0
    tamed_dino_count: int = 0

    # Logs
    tribe_log: List[str] = None

    # File metadata
    file_path: str = ""
    file_size: int = 0

    def __post_init__(self):
        if self.members_player_name is None:
            self.members_player_name = []
        if self.members_player_data_id is None:
            self.members_player_data_id = []
        if self.tribe_admins is None:
            self.tribe_admins = []
        if self.tribe_rank_groups is None:
            self.tribe_rank_groups = []
        if self.tribe_log is None:
            self.tribe_log = []


class AdvancedArkParser:
    """
    Advanced parser for ARK save files
    Attempts to extract detailed data from binary formats
    """

    # Known property names from ARK's code
    PROFILE_PROPERTIES = {
        "PlayerName": "player_name",
        "PlayerCharacterName": "character_name",
        "TribeID": "tribe_id",
        "CharacterStatusComponent_ExperiencePoints": "experience",
        "CharacterStatusComponent_CurrentStatusValues": "stats",
        "SpawnRegionIndex": "spawn_region_index",
        "MyCharacterStatusComponent": "status_component",
    }

    TRIBE_PROPERTIES = {
        "TribeName": "tribe_name",
        "OwnerPlayerDataID": "owner_player_data_id",
        "MembersPlayerName": "members_player_name",
        "MembersPlayerDataID": "members_player_data_id",
        "TribeAdmins": "tribe_admins",
        "SetGovernment": "set_government",
        "TribeRankGroups": "tribe_rank_groups",
        "TribeLog": "tribe_log",
        "NumTribeMembers": "num_tribe_members",
        "TamedDinoCount": "tamed_dino_count",
    }

    @staticmethod
    def parse_profile_advanced(file_path: Path) -> Optional[ArkProfileData]:
        """
        Advanced parsing of .arkprofile file
        Attempts to extract all available data
        """
        if not file_path.exists():
            return None

        try:
            with open(file_path, "rb") as f:
                data = f.read()

            profile = ArkProfileData(
                eos_id=file_path.stem, file_path=str(file_path), file_size=len(data)
            )

            reader = BinaryReader(data)

            # ARK save file structure:
            # 1. Header (version info, GUID)
            # 2. Object class path
            # 3. Object name
            # 4. Parent object names
            # 5. Property data

            try:
                # Skip header (first ~7 bytes are version/magic)
                reader.seek(7)

                # Read GUID (16 bytes)
                guid = reader.read_guid()

                # Read class path
                class_path = reader.read_string()

                # Skip some object references
                while reader.has_data():
                    try:
                        name = reader.read_string()
                        if not name or len(name) > 100:
                            break

                        # Look for property markers
                        if "Property" in name or "Component" in name:
                            break
                    except:
                        break

                # Now try to read properties
                prop_reader = PropertyReader(reader)
                properties = {}

                # Try to read multiple properties
                for _ in range(100):  # Safety limit
                    try:
                        prop = prop_reader.read_property()
                        if prop is None:
                            break

                        name, prop_type, value = prop
                        properties[name] = {"type": prop_type, "value": value}
                    except:
                        break

                # Extract known properties
                if "PlayerName" in properties:
                    profile.player_name = str(properties["PlayerName"]["value"])

                if "TribeID" in properties:
                    profile.tribe_id = int(properties["TribeID"]["value"])

                if "CharacterStatusComponent_ExperiencePoints" in properties:
                    profile.experience = float(
                        properties["CharacterStatusComponent_ExperiencePoints"]["value"]
                    )

            except Exception as parse_error:
                # If advanced parsing fails, we still have basic metadata
                pass

            return profile

        except Exception as e:
            print(f"Error parsing profile {file_path}: {e}")
            return None

    @staticmethod
    def parse_tribe_advanced(file_path: Path) -> Optional[ArkTribeData]:
        """
        Advanced parsing of .arktribe file
        Attempts to extract all available data
        """
        if not file_path.exists():
            return None

        try:
            with open(file_path, "rb") as f:
                data = f.read()

            tribe = ArkTribeData(
                tribe_id=int(file_path.stem), file_path=str(file_path), file_size=len(data)
            )

            reader = BinaryReader(data)

            try:
                # Skip header
                reader.seek(7)

                # Read GUID
                guid = reader.read_guid()

                # Read class path
                class_path = reader.read_string()

                # Skip object references
                while reader.has_data():
                    try:
                        name = reader.read_string()
                        if not name or len(name) > 100:
                            break
                        if "Property" in name or "TribeName" in name:
                            reader.seek(reader.tell() - len(name) - 5)  # Back up
                            break
                    except:
                        break

                # Try to read properties
                prop_reader = PropertyReader(reader)
                properties = {}

                for _ in range(100):
                    try:
                        prop = prop_reader.read_property()
                        if prop is None:
                            break

                        name, prop_type, value = prop
                        properties[name] = {"type": prop_type, "value": value}
                    except:
                        break

                # Extract tribe data
                if "TribeName" in properties:
                    tribe.tribe_name = str(properties["TribeName"]["value"])

                if "OwnerPlayerDataID" in properties:
                    tribe.owner_player_data_id = int(properties["OwnerPlayerDataID"]["value"])

                if "MembersPlayerName" in properties:
                    members = properties["MembersPlayerName"]["value"]
                    if isinstance(members, list):
                        tribe.members_player_name = members

                if "NumTribeMembers" in properties:
                    tribe.num_tribe_members = int(properties["NumTribeMembers"]["value"])

                if "TamedDinoCount" in properties:
                    tribe.tamed_dino_count = int(properties["TamedDinoCount"]["value"])

            except Exception as parse_error:
                # If advanced parsing fails, we still have basic metadata
                pass

            return tribe

        except Exception as e:
            print(f"Error parsing tribe {file_path}: {e}")
            return None

    @staticmethod
    def extract_strings_from_binary(
        data: bytes, min_length: int = 4, max_length: int = 100
    ) -> List[Tuple[int, str]]:
        """
        Extract all readable strings from binary data
        Useful for reverse engineering the format

        Returns: List of (offset, string) tuples
        """
        strings = []
        reader = BinaryReader(data)

        while reader.has_data():
            pos = reader.tell()
            try:
                # Try to read as UE string
                string = reader.read_string()
                if string and min_length <= len(string) <= max_length:
                    # Check if it's printable
                    if all(c.isprintable() or c.isspace() for c in string):
                        strings.append((pos, string))
            except:
                # Move forward and try again
                reader.seek(pos + 1)

        return strings
