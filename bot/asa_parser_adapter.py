from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

# Try to import the external library; fallback to internal reader
try:
    import ark_asa_parser as asa  # type: ignore
    from ark_asa_parser import AsyncArkSaveReader  # type: ignore

    HAS_LIB = True
    HAS_ASYNC = True
except Exception:
    HAS_LIB = False
    HAS_ASYNC = False
    AsyncArkSaveReader = None

from bot.ark_data_parser.save_reader import ArkSaveReader, PlayerData, TribeData
from bot.utils.config import Config


async def get_all_players_from_cluster(cluster_root: Path) -> List[PlayerData]:
    """
    Scan all server save directories in a cluster and return all players.

    Args:
        cluster_root: Path to cluster root containing server directories

    Returns:
        List of all PlayerData objects found across all servers
    """
    all_players = []

    try:
        # Find all server directories (they typically have "SavedArks" subdirectory)
        for server_dir in cluster_root.iterdir():
            if not server_dir.is_dir():
                continue

            # Look for SavedArks directory
            saved_arks = server_dir / "SavedArks"
            if not saved_arks.exists():
                saved_arks = server_dir / "ShooterGame" / "Saved" / "SavedArks"

            if not saved_arks.exists():
                continue

            # Find the world save directory (ends with _WP or similar)
            for world_dir in saved_arks.iterdir():
                if world_dir.is_dir() and world_dir.name.endswith("_WP"):
                    try:
                        adapter = ASAAdapter(world_dir)
                        players = await adapter.async_get_players()
                        all_players.extend(players)
                    except Exception as e:
                        # Log but don't fail on individual server errors
                        pass
    except Exception as e:
        pass

    return all_players


class ASAAdapter:
    """Adapter facade to read ASA save data using ark_asa_parser when available.
    Falls back to internal ArkSaveReader so the bot keeps working.
    """

    def __init__(self, save_dir: Path, xp_table_path: Optional[str] = None):
        self.save_dir = Path(save_dir)
        self._xp_table = self._load_xp_table(xp_table_path or Config.ASA_XP_TABLE_JSON)

    @staticmethod
    def _load_xp_table(path: Optional[str]) -> Optional[List[int]]:
        try:
            if path:
                p = Path(path)
                if p.exists():
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # Allow either {'levels': [...]} or direct list [..]
                        if isinstance(data, dict) and "levels" in data:
                            return data["levels"]
                        if isinstance(data, list):
                            return data
        except Exception:
            pass
        return None

    # --------------------------- Public API ---------------------------
    def get_players(self) -> List[PlayerData]:
        if HAS_LIB:
            try:
                lib_reader = asa.ArkSaveReader(self.save_dir)  # type: ignore[attr-defined]
                # Try to set xp_table attribute if supported
                if self._xp_table is not None:
                    try:
                        setattr(lib_reader, "xp_table", self._xp_table)
                    except Exception:
                        pass
                lib_players = lib_reader.get_all_players()
                return [self._map_player(p) for p in lib_players]
            except Exception:
                # Fall back to internal if anything goes wrong
                pass
        reader = ArkSaveReader(self.save_dir)
        return reader.get_all_players()

    async def async_get_players(self) -> List[PlayerData]:
        """Async version using AsyncArkSaveReader for non-blocking I/O"""
        if HAS_ASYNC and AsyncArkSaveReader:
            try:
                lib_reader = AsyncArkSaveReader(self.save_dir)  # type: ignore[misc]
                if self._xp_table is not None:
                    try:
                        setattr(lib_reader, "xp_table", self._xp_table)
                    except Exception:
                        pass
                lib_players = await lib_reader.async_get_all_players()
                return [self._map_player(p) for p in lib_players]
            except Exception:
                # Fall back to sync if async fails
                pass
        # Fallback to sync version
        return self.get_players()

    def get_tribes(self) -> List[TribeData]:
        if HAS_LIB:
            try:
                lib_reader = asa.ArkSaveReader(self.save_dir)  # type: ignore[attr-defined]
                if self._xp_table is not None:
                    try:
                        setattr(lib_reader, "xp_table", self._xp_table)
                    except Exception:
                        pass
                lib_tribes = lib_reader.get_all_tribes()
                return [self._map_tribe(t) for t in lib_tribes]
            except Exception:
                pass
        reader = ArkSaveReader(self.save_dir)
        return reader.get_all_tribes()

    async def async_get_tribes(self) -> List[TribeData]:
        """Async version using AsyncArkSaveReader for non-blocking I/O"""
        if HAS_ASYNC and AsyncArkSaveReader:
            try:
                lib_reader = AsyncArkSaveReader(self.save_dir)  # type: ignore[misc]
                if self._xp_table is not None:
                    try:
                        setattr(lib_reader, "xp_table", self._xp_table)
                    except Exception:
                        pass
                lib_tribes = await lib_reader.async_get_all_tribes()
                return [self._map_tribe(t) for t in lib_tribes]
            except Exception:
                pass
        # Fallback to sync version
        return self.get_tribes()

    def read_player_inventory(self, profile_path: Path) -> List[Dict[str, Any]]:
        if HAS_LIB:
            try:
                lib_reader = asa.ArkSaveReader(self.save_dir)  # type: ignore[attr-defined]
                if self._xp_table is not None:
                    try:
                        setattr(lib_reader, "xp_table", self._xp_table)
                    except Exception:
                        pass
                read_inv = getattr(lib_reader, "read_player_inventory", None)
                if callable(read_inv):
                    return read_inv(profile_path)
            except Exception:
                return []
        return []

    @staticmethod
    def scan_cluster_adapters(root: Path) -> Dict[str, "ASAAdapter"]:
        from bot.ark_data_parser.save_reader import scan_all_servers

        readers = scan_all_servers(root)
        adapters: Dict[str, ASAAdapter] = {}
        for name, reader in readers.items():
            adapters[name] = ASAAdapter(reader.save_dir)
        return adapters

    # --------------------------- Mappers ---------------------------
    def _map_player(self, src: Any) -> PlayerData:
        # src may be a dataclass/object or dict from ark_asa_parser
        def get_attr(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        p = PlayerData()
        p.character_name = get_attr(src, "character_name", "")
        p.player_name = get_attr(src, "player_name", "")
        p.eos_id = get_attr(src, "eos_id", "")
        p.tribe_id = get_attr(src, "tribe_id", None)
        p.level = int(get_attr(src, "level", 0) or 0)
        p.experience = float(get_attr(src, "experience", 0.0) or 0.0)
        p.lat = float(get_attr(src, "lat", 0.0) or 0.0)
        p.lon = float(get_attr(src, "lon", 0.0) or 0.0)
        p.last_seen = get_attr(src, "last_seen", None)
        p.file_path = get_attr(src, "file_path", "")
        return p

    def _map_tribe(self, src: Any) -> TribeData:
        def get_attr(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        tribe_id = int(get_attr(src, "tribe_id", 0) or 0)
        t = TribeData(tribe_id=tribe_id)
        t.tribe_name = get_attr(src, "tribe_name", "")
        t.owner_name = get_attr(src, "owner_name", "")
        t.member_count = int(get_attr(src, "member_count", 0) or 0)
        t.dino_count = int(get_attr(src, "dino_count", 0) or 0)
        t.last_active = get_attr(src, "last_active", None)
        t.file_path = get_attr(src, "file_path", "")
        return t
