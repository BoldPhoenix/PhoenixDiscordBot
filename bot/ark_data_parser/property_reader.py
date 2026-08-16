"""
Enhanced property parser for ARK save files
Properly reads UE5 property structures
"""

import struct
from typing import Optional, Any, List


class EnhancedPropertyReader:
    """Read Unreal Engine 5 properties with correct format"""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.size = len(data)

    def read_int(self, size=4, signed=True) -> int:
        """Read integer"""
        if self.pos + size > self.size:
            raise EOFError()
        val = int.from_bytes(self.data[self.pos : self.pos + size], "little", signed=signed)
        self.pos += size
        return val

    def read_string(self) -> str:
        """
        Read UE length-prefixed string
        Format: int32 length (negative for UTF-16, positive for ASCII)
        """
        try:
            length = self.read_int(4, signed=True)
            if length == 0:
                return ""

            if length < 0:
                # UTF-16 string
                length = abs(length)
                if self.pos + length * 2 > self.size:
                    raise EOFError()
                string_bytes = self.data[self.pos : self.pos + length * 2]
                self.pos += length * 2
                # Remove null terminator
                return string_bytes[:-2].decode("utf-16-le", errors="ignore")
            else:
                # ASCII string
                if self.pos + length > self.size:
                    raise EOFError()
                string_bytes = self.data[self.pos : self.pos + length]
                self.pos += length
                # Remove null terminator
                return string_bytes[:-1].decode("ascii", errors="ignore")
        except Exception:
            return ""

    def read_property_value(self, prop_type: str) -> Any:
        """Read property value based on type"""
        try:
            if prop_type == "StrProperty":
                # Skip the size field (int32)
                self.pos += 4
                return self.read_string()

            elif prop_type == "IntProperty":
                return self.read_int(4, signed=True)

            elif prop_type == "UInt32Property":
                return self.read_int(4, signed=False)

            elif prop_type == "UInt64Property":
                return self.read_int(8, signed=False)

            elif prop_type == "FloatProperty":
                val = struct.unpack("<f", self.data[self.pos : self.pos + 4])[0]
                self.pos += 4
                return val

            elif prop_type == "DoubleProperty":
                val = struct.unpack("<d", self.data[self.pos : self.pos + 8])[0]
                self.pos += 8
                return val

            elif prop_type == "BoolProperty":
                val = self.data[self.pos]
                self.pos += 1
                return bool(val)

            elif prop_type == "ArrayProperty":
                # Read array element type
                array_type = self.read_string()
                # Skip null byte
                self.pos += 1
                # Read count
                count = self.read_int(4, signed=False)

                items = []
                if array_type == "StrProperty":
                    for _ in range(min(count, 1000)):  # Safety limit
                        items.append(self.read_string())
                elif array_type in ["IntProperty", "UInt32Property"]:
                    for _ in range(min(count, 1000)):
                        items.append(self.read_int(4))
                elif array_type == "UInt64Property":
                    for _ in range(min(count, 1000)):
                        items.append(self.read_int(8, signed=False))

                return items

        except Exception:
            pass

        return None

    def find_property(self, property_name: str, start_pos: int = 0) -> Optional[Any]:
        """
        Find and read a property value

        UE5 Property structure:
        - Property name (string)
        - Property type (string)
        - Property size (int64)
        - Property value (type-dependent)
        """
        self.pos = start_pos
        attempts = 0
        max_attempts = min(self.size, 50000)  # Don't search forever

        while self.pos < self.size - 20 and attempts < max_attempts:
            attempts += 1
            try:
                start = self.pos
                prop_name = self.read_string()

                # If we found the property name
                if prop_name == property_name:
                    # Read property type
                    prop_type = self.read_string()

                    # Skip the 8-byte size field
                    self.pos += 8

                    # Read the value
                    value = self.read_property_value(prop_type)
                    return value

                # If empty string or "None", we've hit the end of properties
                if not prop_name or prop_name == "None":
                    # Skip ahead a bit and keep trying
                    self.pos = start + 4
                    continue

            except (EOFError, UnicodeDecodeError, struct.error):
                # Skip forward and try again
                self.pos = start + 1
                continue
            except Exception:
                self.pos = start + 1
                continue

        return None


def extract_player_data(file_path, eos_id: str) -> dict:
    """Extract player data from .arkprofile file"""
    try:
        with open(file_path, "rb") as f:
            data = f.read()

        reader = EnhancedPropertyReader(data)

        result = {
            "eos_id": eos_id,
            "player_name": "",
            "character_name": "",
            "tribe_id": None,
            "level": 1,
            "experience": 0.0,
        }

        # Extract player name
        player_name = reader.find_property("PlayerName")
        if player_name:
            result["player_name"] = player_name

        # Extract character name
        reader.pos = 0
        char_name = reader.find_property("PlayerCharacterName")
        if char_name:
            result["character_name"] = char_name

        # Extract tribe ID
        reader.pos = 0
        tribe_id = reader.find_property("TribeID")
        if tribe_id:
            result["tribe_id"] = int(tribe_id)

        # Extract experience
        reader.pos = 0
        exp = reader.find_property("CharacterStatusComponent_ExperiencePoints")
        if exp:
            result["experience"] = float(exp)
            # Simple level calculation
            result["level"] = max(1, int((exp / 100) ** 0.5) + 1)

        return result

    except Exception as e:
        return {"eos_id": eos_id, "player_name": "", "error": str(e)}


def extract_tribe_data(file_path, tribe_id: int) -> dict:
    """Extract tribe data from .arktribe file"""
    try:
        with open(file_path, "rb") as f:
            data = f.read()

        reader = EnhancedPropertyReader(data)

        result = {
            "tribe_id": tribe_id,
            "tribe_name": "",
            "owner_id": 0,
            "members": [],
            "member_ids": [],
            "tribe_log": [],
        }

        # Extract tribe name
        tribe_name = reader.find_property("TribeName")
        if tribe_name:
            result["tribe_name"] = tribe_name

        # Extract owner ID
        reader.pos = 0
        owner_id = reader.find_property("OwnerPlayerDataId")
        if owner_id:
            result["owner_id"] = int(owner_id)

        # Extract member names
        reader.pos = 0
        members = reader.find_property("MembersPlayerName")
        if members and isinstance(members, list):
            result["members"] = members

        # Extract member IDs
        reader.pos = 0
        member_ids = reader.find_property("MembersPlayerDataID")
        if member_ids and isinstance(member_ids, list):
            result["member_ids"] = member_ids

        # Extract tribe log
        reader.pos = 0
        tribe_log = reader.find_property("TribeLog")
        if tribe_log and isinstance(tribe_log, list):
            result["tribe_log"] = tribe_log[-10:]  # Last 10 entries

        return result

    except Exception as e:
        return {"tribe_id": tribe_id, "tribe_name": "", "error": str(e)}
