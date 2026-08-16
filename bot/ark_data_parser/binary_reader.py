"""
Binary data reader for ARK ASA save files
Handles UE5 binary serialization format
"""

import struct
from io import BytesIO
from typing import Any, List, Optional, Tuple


class BinaryReader:
    """
    Helper class for reading binary data from ARK save files
    """

    def __init__(self, data: bytes):
        self.stream = BytesIO(data)
        self.size = len(data)

    def tell(self) -> int:
        """Get current position in stream"""
        return self.stream.tell()

    def seek(self, position: int, whence: int = 0):
        """Seek to position in stream"""
        self.stream.seek(position, whence)

    def read_bytes(self, count: int) -> bytes:
        """Read raw bytes"""
        return self.stream.read(count)

    def read_byte(self) -> int:
        """Read single byte"""
        return struct.unpack("<B", self.stream.read(1))[0]

    def read_bool(self) -> bool:
        """Read boolean value"""
        return self.read_byte() != 0

    def read_int16(self) -> int:
        """Read signed 16-bit integer"""
        return struct.unpack("<h", self.stream.read(2))[0]

    def read_uint16(self) -> int:
        """Read unsigned 16-bit integer"""
        return struct.unpack("<H", self.stream.read(2))[0]

    def read_int32(self) -> int:
        """Read signed 32-bit integer"""
        return struct.unpack("<i", self.stream.read(4))[0]

    def read_uint32(self) -> int:
        """Read unsigned 32-bit integer"""
        return struct.unpack("<I", self.stream.read(4))[0]

    def read_int64(self) -> int:
        """Read signed 64-bit integer"""
        return struct.unpack("<q", self.stream.read(8))[0]

    def read_uint64(self) -> int:
        """Read unsigned 64-bit integer"""
        return struct.unpack("<Q", self.stream.read(8))[0]

    def read_float(self) -> float:
        """Read 32-bit float"""
        return struct.unpack("<f", self.stream.read(4))[0]

    def read_double(self) -> float:
        """Read 64-bit double"""
        return struct.unpack("<d", self.stream.read(8))[0]

    def read_string(self) -> str:
        """
        Read Unreal Engine FString
        Format: int32 length (negative for UTF-16, positive for ASCII), then string data
        """
        length = self.read_int32()

        if length == 0:
            return ""

        if length < 0:
            # UTF-16 string
            actual_length = (-length) * 2
            data = self.stream.read(actual_length)
            # Remove null terminator
            return data[:-2].decode("utf-16-le", errors="ignore")
        else:
            # ASCII/UTF-8 string
            data = self.stream.read(length)
            # Remove null terminator
            return data[:-1].decode("utf-8", errors="ignore")

    def read_ue_array_header(self) -> int:
        """Read Unreal Engine TArray header (returns element count)"""
        return self.read_int32()

    def read_guid(self) -> str:
        """Read Unreal Engine GUID (16 bytes)"""
        data = self.stream.read(16)
        # Format as standard GUID
        return "{:08x}-{:04x}-{:04x}-{:02x}{:02x}-{}".format(
            struct.unpack("<I", data[0:4])[0],
            struct.unpack("<H", data[4:6])[0],
            struct.unpack("<H", data[6:8])[0],
            data[8],
            data[9],
            data[10:16].hex(),
        )

    def read_compressed_int(self) -> int:
        """
        Read compressed integer (Unreal Engine compact index format)
        Used for efficient storage of small integers
        """
        result = 0
        shift = 0

        while True:
            byte = self.read_byte()
            result |= (byte & 0x7F) << shift

            if (byte & 0x80) == 0:
                break

            shift += 7

        return result

    def peek_byte(self) -> int:
        """Peek at next byte without advancing position"""
        pos = self.tell()
        byte = self.read_byte()
        self.seek(pos)
        return byte

    def remaining(self) -> int:
        """Get number of bytes remaining in stream"""
        return self.size - self.tell()

    def has_data(self) -> bool:
        """Check if there's more data to read"""
        return self.remaining() > 0


class PropertyReader:
    """
    Reads Unreal Engine property serialization
    This is the format used in .arkprofile and .arktribe files
    """

    def __init__(self, reader: BinaryReader):
        self.reader = reader

    def read_property(self) -> Optional[Tuple[str, str, Any]]:
        """
        Read a single property
        Returns: (property_name, property_type, value) or None if end of properties
        """
        # Read property name
        if not self.reader.has_data():
            return None

        prop_name = self.reader.read_string()

        # Check for end marker
        if not prop_name or prop_name == "None":
            return None

        # Read property type
        prop_type = self.reader.read_string()

        # Read size and array index
        size = self.reader.read_int64()
        array_index = self.reader.read_int32()

        # Read the value based on type
        value = self._read_property_value(prop_type, size)

        return (prop_name, prop_type, value)

    def read_all_properties(self) -> dict:
        """Read all properties until end marker"""
        properties = {}

        while True:
            prop = self.read_property()
            if prop is None:
                break

            name, prop_type, value = prop
            properties[name] = {"type": prop_type, "value": value}

        return properties

    def _read_property_value(self, prop_type: str, size: int) -> Any:
        """Read property value based on type"""
        if prop_type == "IntProperty":
            return self.reader.read_int32()

        elif prop_type == "Int64Property":
            return self.reader.read_int64()

        elif prop_type == "FloatProperty":
            return self.reader.read_float()

        elif prop_type == "DoubleProperty":
            return self.reader.read_double()

        elif prop_type == "BoolProperty":
            return self.reader.read_bool()

        elif prop_type == "StrProperty":
            return self.reader.read_string()

        elif prop_type == "NameProperty":
            return self.reader.read_string()

        elif prop_type == "ObjectProperty":
            # Object reference - typically an index or path
            return self.reader.read_int32()

        elif prop_type == "StructProperty":
            # Complex structure - read as raw bytes for now
            struct_name = self.reader.read_string()
            struct_guid = self.reader.read_guid()
            # Read the structure data
            return {
                "struct_type": struct_name,
                "guid": struct_guid,
                "data": self.reader.read_bytes(int(size - len(struct_name) - 20)),
            }

        elif prop_type == "ArrayProperty":
            # Array of properties
            element_type = self.reader.read_string()
            count = self.reader.read_int32()

            elements = []
            for _ in range(count):
                elements.append(self._read_array_element(element_type))

            return elements

        else:
            # Unknown type - read as raw bytes
            return self.reader.read_bytes(int(size))

    def _read_array_element(self, element_type: str) -> Any:
        """Read a single array element"""
        if element_type == "IntProperty":
            return self.reader.read_int32()
        elif element_type == "FloatProperty":
            return self.reader.read_float()
        elif element_type == "StrProperty":
            return self.reader.read_string()
        else:
            # For complex types, we'd need more parsing
            return None
