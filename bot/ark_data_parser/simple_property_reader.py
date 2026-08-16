"""
Simple direct property extractor for ARK files
Uses byte pattern searching instead of sequential reading
"""

import struct
from typing import Optional


def read_ue_string_at(data: bytes, offset: int) -> tuple[str, int]:
    """
    Read a UE string at specific offset
    Returns (string, bytes_read)
    """
    if offset + 4 > len(data):
        return ("", 0)

    length = struct.unpack("<i", data[offset : offset + 4])[0]
    start_offset = offset
    offset += 4

    if length == 0:
        return ("", 4)

    if length < 0:
        # UTF-16
        length = abs(length)
        if offset + length * 2 > len(data):
            return ("", 0)
        # Read all bytes including null terminator
        raw_string = data[offset : offset + length * 2]
        string = raw_string.decode("utf-16-le", errors="ignore")
        # Remove null terminator if present
        string = string.rstrip("\x00")
        return (string, 4 + length * 2)
    else:
        # ASCII/UTF-8
        if offset + length > len(data):
            return ("", 0)
        # Read all bytes including null terminator
        raw_string = data[offset : offset + length]
        string = raw_string.decode("utf-8", errors="ignore")
        # Remove null terminator if present
        string = string.rstrip("\x00")
        return (string, 4 + length)


def find_string_property(data: bytes, prop_name: str) -> Optional[str]:
    """Find a string property value in ARK save data"""
    # Search for the property name as bytes
    search_bytes = prop_name.encode("ascii")
    pos = 0

    while True:
        # Find next occurrence of property name
        pos = data.find(search_bytes, pos)
        if pos == -1:
            return None

        # Check if this is a length-prefixed string
        if pos >= 4:
            length = struct.unpack("<i", data[pos - 4 : pos])[0]
            if length == len(prop_name) + 1:  # +1 for null terminator
                # This looks like a valid property name
                # Read the property type
                type_start = pos + len(search_bytes) + 1  # +1 for null terminator
                prop_type, type_bytes = read_ue_string_at(data, type_start)

                if prop_type == "StrProperty":
                    # Skip 8 bytes (int64 size) + 1 byte (null/padding)
                    value_pos = type_start + type_bytes + 8 + 1
                    # Read the actual string value
                    if value_pos <= len(data):
                        value, _ = read_ue_string_at(data, value_pos)
                        if value:
                            return value

        pos += 1


def find_int_property(data: bytes, prop_name: str) -> Optional[int]:
    """Find an integer property value"""
    search_bytes = prop_name.encode("ascii")
    pos = 0

    while True:
        pos = data.find(search_bytes, pos)
        if pos == -1:
            return None

        if pos >= 4:
            length = struct.unpack("<i", data[pos - 4 : pos])[0]
            if length == len(prop_name) + 1:
                # Read property type
                type_start = pos + len(search_bytes) + 1
                prop_type, type_bytes = read_ue_string_at(data, type_start)

                if prop_type in ["IntProperty", "UInt32Property"]:
                    # Skip 8 bytes (int64 size) + 1 byte (null/padding)
                    value_pos = type_start + type_bytes + 8 + 1
                    if value_pos + 4 <= len(data):
                        return struct.unpack("<I", data[value_pos : value_pos + 4])[0]

        pos += 1


def find_uint16_property(data: bytes, prop_name: str) -> Optional[int]:
    """Find a UInt16 property value

    The property name might be embedded in a component path like:
    CharacterStatusComponent_ExtraCharacterLevel
    So we search for the property name and check if it's followed by a null terminator
    and then the property type.
    """
    search_bytes = prop_name.encode("ascii")
    pos = 0

    while True:
        pos = data.find(search_bytes, pos)
        if pos == -1:
            return None

        # Check if this is followed by null terminator (end of property name string)
        if pos + len(search_bytes) < len(data) and data[pos + len(search_bytes)] == 0:
            # Read property type
            type_start = pos + len(search_bytes) + 1
            prop_type, type_bytes = read_ue_string_at(data, type_start)

            if prop_type == "UInt16Property":
                # Skip 8 bytes (int64 size) + 1 byte (null/padding)
                value_pos = type_start + type_bytes + 8 + 1
                if value_pos + 2 <= len(data):
                    return struct.unpack("<H", data[value_pos : value_pos + 2])[0]

        pos += 1


def find_float_property(data: bytes, prop_name: str) -> Optional[float]:
    """Find a Float property value

    The property name might be embedded in a component path.
    So we search for the property name and check if it's followed by a null terminator
    and then the property type.
    """
    search_bytes = prop_name.encode("ascii")
    pos = 0

    while True:
        pos = data.find(search_bytes, pos)
        if pos == -1:
            return None

        # Check if this is followed by null terminator (end of property name string)
        if pos + len(search_bytes) < len(data) and data[pos + len(search_bytes)] == 0:
            # Read property type
            type_start = pos + len(search_bytes) + 1
            prop_type, type_bytes = read_ue_string_at(data, type_start)

            if prop_type == "FloatProperty":
                # Skip 8 bytes (int64 size) + 1 byte (null/padding)
                value_pos = type_start + type_bytes + 8 + 1
                if value_pos + 4 <= len(data):
                    return struct.unpack("<f", data[value_pos : value_pos + 4])[0]

        pos += 1


def find_array_property(data: bytes, prop_name: str) -> Optional[list]:
    """Find an array property value"""
    search_bytes = prop_name.encode("ascii")
    pos = 0

    while True:
        pos = data.find(search_bytes, pos)
        if pos == -1:
            return None

        if pos >= 4:
            length = struct.unpack("<i", data[pos - 4 : pos])[0]
            if length == len(prop_name) + 1:
                # Read property type
                type_start = pos + len(search_bytes) + 1
                prop_type, type_bytes = read_ue_string_at(data, type_start)

                if prop_type == "ArrayProperty":
                    # For ArrayProperty, skip 4 bytes (int32), then element type
                    elem_type_start = type_start + type_bytes + 4
                    elem_type, elem_type_bytes = read_ue_string_at(data, elem_type_start)

                    # After element type: 4 null bytes + int32 + 1 null byte, then count
                    count_pos = elem_type_start + elem_type_bytes + 4 + 4 + 1
                    if count_pos + 4 <= len(data):
                        count = struct.unpack("<I", data[count_pos : count_pos + 4])[0]

                        # Read array elements
                        items = []
                        item_pos = count_pos + 4

                        if elem_type == "StrProperty":
                            for i in range(min(count, 1000)):  # Safety limit
                                item, item_bytes = read_ue_string_at(data, item_pos)
                                if not item_bytes:
                                    break
                                items.append(item)
                                item_pos += item_bytes
                        elif elem_type in ["IntProperty", "UInt32Property"]:
                            for _ in range(min(count, 1000)):
                                if item_pos + 4 > len(data):
                                    break
                                items.append(struct.unpack("<I", data[item_pos : item_pos + 4])[0])
                                item_pos += 4

                        return items

        pos += 1


def extract_player_data_simple(file_path, eos_id: str) -> dict:
    """Extract player data using simple byte search"""
    try:
        with open(file_path, "rb") as f:
            data = f.read()

        # Try both PlayerName and PlayerCharacterName
        player_name = find_string_property(data, "PlayerName") or ""
        character_name = find_string_property(data, "PlayerCharacterName") or ""

        # Parse level and experience from binary properties
        # ExtraCharacterLevel stores displayed_level - 1 (so level 105 is stored as 104)
        extra_char_level = find_uint16_property(data, "ExtraCharacterLevel")
        level = (extra_char_level + 1) if extra_char_level is not None else 1

        # Parse experience points as float
        experience = find_float_property(data, "ExperiencePoints")
        if experience is None:
            experience = 0.0

        return {
            "eos_id": eos_id,
            "player_name": player_name,
            "character_name": character_name,
            "tribe_id": find_int_property(data, "TribeID"),
            "level": level,
            "experience": experience,
        }
    except Exception as e:
        return {"eos_id": eos_id, "player_name": "", "error": str(e)}


def extract_tribe_data_simple(file_path, tribe_id: int) -> dict:
    """Extract tribe data using simple byte search"""
    try:
        with open(file_path, "rb") as f:
            data = f.read()

        return {
            "tribe_id": tribe_id,
            "tribe_name": find_string_property(data, "TribeName") or "",
            "owner_id": find_int_property(data, "OwnerPlayerDataId") or 0,
            "members": find_array_property(data, "MembersPlayerName") or [],
            "member_ids": find_array_property(data, "MembersPlayerDataID") or [],
            "tribe_log": find_array_property(data, "TribeLog") or [],
        }
    except Exception as e:
        return {"tribe_id": tribe_id, "tribe_name": "", "error": str(e)}
