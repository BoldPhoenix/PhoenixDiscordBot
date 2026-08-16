# ARK Data Parser

A Python library for parsing ARK: Survival Ascended (ASA) save files.

## Features

- 📊 **Read world saves (.ark)** - SQLite database access to game objects
- 👤 **Parse player profiles (.arkprofile)** - Extract player data including EOS IDs, last seen times
- 🏛️ **Parse tribe files (.arktribe)** - Extract tribe information and metadata
- 🔍 **Binary format support** - Custom binary reader for Unreal Engine 5 serialization
- 📈 **Cluster scanning** - Scan entire ARK clusters automatically

## Installation

```bash
pip install ark-asa-data-parser
```

Or install from source:

```bash
git clone https://github.com/BoldPhoenix/ArkDiscordBot.git
cd ArkDiscordBot
pip install -e ./bot/ark_data_parser
```

## Quick Start

```python
from bot.ark_data_parser import ArkSaveReader, scan_all_servers
from pathlib import Path

# Read a single server
save_dir = Path(r'C:\ARK\Saved\SavedArks\TheIsland_WP')
reader = ArkSaveReader(save_dir)

# Get database info
info = reader.get_database_info()
print(f"Game objects: {info['tables']['game']:,}")

# Get all players
players = reader.get_all_players()
for player in players:
    print(f"Player: {player.eos_id}, Last seen: {player.last_seen}")

# Get all tribes
tribes = reader.get_all_tribes()
for tribe in tribes:
    print(f"Tribe {tribe.tribe_id}, Last active: {tribe.last_active}")

# Scan entire cluster
cluster_root = Path(r'C:\ARK')
readers = scan_all_servers(cluster_root)
for server_name, reader in readers.items():
    print(f"{server_name}: {len(reader.get_all_players())} players")
```

## Current Capabilities

### ✅ Working
- Read world save files as SQLite databases
- Extract game object counts and statistics
- Read player profile metadata (EOS ID, file size, timestamps)
- Read tribe metadata (ID, file size, timestamps)
- Scan multiple servers in a cluster
- Binary data reading utilities

### 🚧 In Development
- Full UE5 property deserialization
- Player name extraction from profiles
- Player level and stats parsing
- Tribe name extraction
- Tribe member lists
- Dino data extraction
- Structure data extraction

## File Format

ARK: Survival Ascended uses different formats for different save types:

### World Saves (.ark)
- **Format:** SQLite database
- **Tables:**
  - `game`: Contains binary blobs for all game objects (players, dinos, structures)
  - `custom`: Contains metadata like SaveHeader
- **Size:** 50-250 MB typical

### Player Profiles (.arkprofile)
- **Format:** Binary (Unreal Engine 5 serialization)
- **Contains:** Player data, stats, inventory, engrams
- **Size:** 10-50 KB typical

### Tribe Files (.arktribe)
- **Format:** Binary (Unreal Engine 5 serialization)
- **Contains:** Tribe name, members, settings, logs
- **Size:** 1-50 KB typical

## API Reference

### ArkSaveReader

Main class for reading ARK save data.

```python
reader = ArkSaveReader(save_dir: Path)
```

**Methods:**
- `is_valid()` - Check if save directory is valid
- `get_database_info()` - Get info about world save database
- `read_save_header()` - Read SaveHeader from custom table
- `list_profile_files()` - List all .arkprofile files
- `list_tribe_files()` - List all .arktribe files
- `read_profile_file(path)` - Read single profile file
- `read_tribe_file(path)` - Read single tribe file
- `get_all_players()` - Get all player data
- `get_all_tribes()` - Get all tribe data

### PlayerData

Dataclass containing player information.

**Fields:**
- `character_name: str` - Character name (if available)
- `player_name: str` - Player name (if available)
- `eos_id: str` - Epic Online Services ID
- `tribe_id: Optional[int]` - Tribe ID if player is in a tribe
- `level: int` - Character level
- `experience: float` - Total XP
- `lat: float` - Latitude coordinate
- `lon: float` - Longitude coordinate
- `last_seen: Optional[datetime]` - Last time profile was modified
- `file_path: str` - Path to .arkprofile file

### TribeData

Dataclass containing tribe information.

**Fields:**
- `tribe_id: int` - Unique tribe ID
- `tribe_name: str` - Tribe name (if available)
- `owner_name: str` - Owner name (if available)
- `member_count: int` - Number of members
- `dino_count: int` - Number of tamed dinos
- `last_active: Optional[datetime]` - Last time tribe was modified
- `file_path: str` - Path to .arktribe file

### scan_all_servers

Scan all servers in a cluster.

```python
readers = scan_all_servers(cluster_root: Path) -> Dict[str, ArkSaveReader]
```

**Parameters:**
- `cluster_root`: Path to cluster root directory (e.g., `C:/ARK`)

**Returns:** Dictionary mapping server name to ArkSaveReader instance

## Advanced Usage

### Custom Binary Parsing

```python
from bot.ark_data_parser.binary_reader import BinaryReader
from pathlib import Path

# Read binary file
with open('player.arkprofile', 'rb') as f:
    data = f.read()

# Create reader
reader = BinaryReader(data)

# Read data
version = reader.read_int32()
guid = reader.read_guid()
text = reader.read_string()
```

### Property Deserialization

```python
from bot.ark_data_parser.binary_reader import PropertyReader

prop_reader = PropertyReader(reader)
properties = prop_reader.read_all_properties()

for name, prop_data in properties.items():
    print(f"{name}: {prop_data['value']}")
```

## Contributing

Contributions are welcome! This library is under active development as we reverse engineer the ARK ASA save format.

### Priority Areas
1. Complete UE5 property deserialization
2. Property name mappings (which bytes = player name, etc.)
3. Dino data extraction
4. Structure coordinate extraction
5. Documentation improvements

### Development Setup

```bash
git clone https://github.com/BoldPhoenix/ArkDiscordBot.git
cd ArkDiscordBot
pip install -e .[dev]
```

## Examples

See the `examples/` directory for more usage examples:
- `basic_usage.py` - Simple server scanning
- `player_analysis.py` - Player statistics
- `tribe_analysis.py` - Tribe statistics
- `cluster_dashboard.py` - Full cluster overview

## Known Limitations

- **UE5 Binary Format**: Full deserialization of UE5 properties is complex and ongoing
- **Property Names**: Not all property names are known yet
- **Encrypted Data**: Some data may be encoded/compressed
- **Version Compatibility**: Tested with ARK ASA as of December 2025

## Credits

Created by BoldPhoenix for the ARK admin community.

Inspired by:
- VincentHenauGithub/ark-save-parser
- arkutils projects
- ARK modding community

## License

MIT License - See LICENSE file for details

## Support

- **Issues**: [GitHub Issues](https://github.com/BoldPhoenix/ArkDiscordBot/issues)
- **Discord**: [ARK Admin Community]
- **Documentation**: [Wiki](https://github.com/BoldPhoenix/ArkDiscordBot/wiki)

## Changelog

### v0.1.0 (December 2025)
- Initial release
- Basic save file reading
- SQLite world save access
- Profile and tribe metadata extraction
- Cluster scanning functionality
- Binary reader utilities
