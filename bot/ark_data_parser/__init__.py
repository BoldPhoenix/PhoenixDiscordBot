"""
ARK Data Parser Module
Extracts player, tribe, dino, and structure data from ARK save files.
"""

__version__ = "1.0.0"

from .save_reader import ArkSaveReader, scan_all_servers, PlayerData, TribeData

__all__ = ["ArkSaveReader", "scan_all_servers", "PlayerData", "TribeData"]
