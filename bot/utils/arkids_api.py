"""
ARK IDs API Integration
Provides item and creature lookup from local cache
Note: arkids.net doesn't have a public API, so this uses a cached/fallback approach
"""

import aiohttp
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger("ArkIDsAPI")


@dataclass
class ArkItem:
    """Represents an ARK item"""

    name: str
    blueprint: str
    category: str
    type: str  # 'item' or 'creature'

    def __str__(self):
        return f"{self.name} ({self.category})"


class ArkIDsAPI:
    """Client for ARK item/creature database with fallback support"""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._items_cache: List[ArkItem] = []
        self._creatures_cache: List[ArkItem] = []
        self._cache_loaded = False
        self._initialize_static_data()

    def _initialize_static_data(self):
        """Initialize with common ARK items and creatures."""
        # Common items
        common_items = [
            ("Metal Ingot", "PrimalItemResource_MetalIngot", "Resources"),
            ("Stone", "PrimalItemResource_Stone", "Resources"),
            ("Wood", "PrimalItemResource_Wood", "Resources"),
            ("Fiber", "PrimalItemResource_Fiber", "Resources"),
            ("Hide", "PrimalItemResource_Hide", "Resources"),
            ("Chitin", "PrimalItemResource_Chitin", "Resources"),
            ("Crystal", "PrimalItemResource_Crystal", "Resources"),
            ("Polymer", "PrimalItemResource_Polymer", "Resources"),
            ("Electronics", "PrimalItemResource_Electronics", "Resources"),
            ("Element", "PrimalItemResource_Element", "Resources"),
            ("Black Pearl", "PrimalItemResource_BlackPearl", "Resources"),
            ("Cementing Paste", "PrimalItemResource_ChitinPaste", "Resources"),
            ("Simple Rifle Ammo", "PrimalItemAmmo_SimpleRifleAmmo", "Ammo"),
            ("Advanced Rifle Bullet", "PrimalItemAmmo_AdvancedRifleBullet", "Ammo"),
            ("Shotgun Ammo", "PrimalItemAmmo_SimpleShotgunAmmo", "Ammo"),
            ("Tranq Arrow", "PrimalItemAmmo_ArrowTranq", "Ammo"),
            ("Metal Arrow", "PrimalItemAmmo_ArrowMetal", "Ammo"),
            ("Assault Rifle", "PrimalItem_WeaponRifle", "Weapons"),
            ("Pump Shotgun", "PrimalItem_WeaponPumpShotgun", "Weapons"),
            ("Longneck Rifle", "PrimalItem_WeaponOneShotRifle", "Weapons"),
            ("Fabricated Pistol", "PrimalItem_WeaponMachinedPistol", "Weapons"),
            ("Rocket Launcher", "PrimalItem_WeaponRocketLauncher", "Weapons"),
        ]

        for name, blueprint, category in common_items:
            self._items_cache.append(
                ArkItem(name=name, blueprint=blueprint, category=category, type="item")
            )

        # Common creatures
        common_creatures = [
            ("Rex", "Rex_Character_BP_C", "Carnivore"),
            ("Raptor", "Raptor_Character_BP_C", "Carnivore"),
            ("Carnotaurus", "Carno_Character_BP_C", "Carnivore"),
            ("Argentavis", "Argent_Character_BP_C", "Flyer"),
            ("Pteranodon", "Ptero_Character_BP_C", "Flyer"),
            ("Ankylosaurus", "Ankylo_Character_BP_C", "Herbivore"),
            ("Triceratops", "Trike_Character_BP_C", "Herbivore"),
            ("Brontosaurus", "Sauropod_Character_BP_C", "Herbivore"),
            ("Stegosaurus", "Stego_Character_BP_C", "Herbivore"),
            ("Giganotosaurus", "Gigant_Character_BP_C", "Carnivore"),
            ("Spinosaurus", "Spino_Character_BP_C", "Carnivore"),
            ("Allosaurus", "Allo_Character_BP_C", "Carnivore"),
            ("Megalodon", "Megalodon_Character_BP_C", "Aquatic"),
            ("Mosasaurus", "Mosa_Character_BP_C", "Aquatic"),
            ("Basilosaurus", "Basilosaurus_Character_BP_C", "Aquatic"),
            ("Dire Wolf", "Direwolf_Character_BP_C", "Carnivore"),
            ("Sabertooth", "Saber_Character_BP_C", "Carnivore"),
            ("Mammoth", "Mammoth_Character_BP_C", "Herbivore"),
            ("Quetzalcoatlus", "Quetz_Character_BP_C", "Flyer"),
            ("Therizinosaurus", "Therizino_Character_BP_C", "Herbivore"),
        ]

        for name, blueprint, category in common_creatures:
            self._creatures_cache.append(
                ArkItem(name=name, blueprint=blueprint, category=category, type="creature")
            )

        self._cache_loaded = True
        logger.info(
            f"Initialized static ARK data: {len(self._items_cache)} items, {len(self._creatures_cache)} creatures"
        )

    async def _ensure_session(self):
        """Ensure aiohttp session exists"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def load_items_cache(self) -> bool:
        """Load items cache (already loaded from static data)"""
        return self._cache_loaded

    async def search_items(self, query: str, limit: int = 25) -> List[ArkItem]:
        """Search for items by name (case-insensitive)

        Args:
            query: Search term
            limit: Maximum results to return

        Returns:
            List of matching ArkItem objects
        """
        query_lower = query.lower()
        results = [
            item
            for item in self._items_cache
            if query_lower in item.name.lower() or query_lower in item.blueprint.lower()
        ]

        return results[:limit]

    async def search_creatures(self, query: str, limit: int = 25) -> List[ArkItem]:
        """Search for creatures by name (case-insensitive)

        Args:
            query: Search term
            limit: Maximum results to return

        Returns:
            List of matching ArkItem objects
        """
        query_lower = query.lower()
        results = [
            creature
            for creature in self._creatures_cache
            if query_lower in creature.name.lower() or query_lower in creature.blueprint.lower()
        ]

        return results[:limit]

    async def get_item_by_name(self, name: str) -> Optional[ArkItem]:
        """Get exact item by name"""
        for item in self._items_cache:
            if item.name.lower() == name.lower():
                return item
        return None

    async def get_creature_by_name(self, name: str) -> Optional[ArkItem]:
        """Get exact creature by name"""
        for creature in self._creatures_cache:
            if creature.name.lower() == name.lower():
                return creature
        return None

    def get_all_items(self) -> List[ArkItem]:
        """Get all cached items"""
        return self._items_cache.copy()

    def get_all_creatures(self) -> List[ArkItem]:
        """Get all cached creatures"""
        return self._creatures_cache.copy()

    def add_custom_item(self, name: str, blueprint: str, category: str = "Custom"):
        """Add a custom item to the cache."""
        self._items_cache.append(
            ArkItem(name=name, blueprint=blueprint, category=category, type="item")
        )

    def add_custom_creature(self, name: str, blueprint: str, category: str = "Custom"):
        """Add a custom creature to the cache."""
        self._creatures_cache.append(
            ArkItem(name=name, blueprint=blueprint, category=category, type="creature")
        )


# Global instance
_arkids_client: Optional[ArkIDsAPI] = None


def get_arkids_client() -> ArkIDsAPI:
    """Get or create global ArkIDsAPI instance"""
    global _arkids_client
    if _arkids_client is None:
        _arkids_client = ArkIDsAPI()
    return _arkids_client


async def cleanup_arkids_client():
    """Clean up global client session"""
    global _arkids_client
    if _arkids_client:
        await _arkids_client.close()
        _arkids_client = None
