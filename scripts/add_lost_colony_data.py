#!/usr/bin/env python3
"""
Add Lost Colony expansion data to ARK reference tables.

Lost Colony specific items, resources, and loot crates not in base data.
"""

import asyncio
import aiosqlite
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


LOST_COLONY_ITEMS = [
    {"object_id": "lc_vulpite", "label": "Vulpite", "class_string": "PrimalItemResource_Vulpite_C", "tags": ["resource", "lost_colony"]},
    {"object_id": "lc_red_element", "label": "Red Element", "class_string": "PrimalItemResource_Element_Red_C", "tags": ["resource", "element", "lost_colony"]},
    {"object_id": "lc_blood_shard", "label": "Blood Shard", "class_string": "PrimalItemResource_BloodShard_C", "tags": ["resource", "lost_colony"]},
    {"object_id": "lc_template_hammer", "label": "Template Hammer", "class_string": "PrimalItem_WeaponTemplateHammer_C", "tags": ["tool", "weapon", "lost_colony"]},
    {"object_id": "lc_fabricated_crossbow", "label": "Fabricated Crossbow", "class_string": "PrimalItem_WeaponFabricatedCrossbow_C", "tags": ["weapon", "ranged", "lost_colony"]},
    {"object_id": "lc_tek_spear", "label": "Tek Spear", "class_string": "PrimalItem_WeaponTekSpear_C", "tags": ["weapon", "tek", "lost_colony"]},
    {"object_id": "lc_holo_decoy", "label": "Holo-Decoy", "class_string": "PrimalItem_WeaponHoloDecoy_C", "tags": ["weapon", "tool", "lost_colony"]},
    {"object_id": "lc_bloodforge", "label": "Bloodforge", "class_string": "PrimalItemStructure_Bloodforge_C", "tags": ["structure", "crafting", "lost_colony"]},
    {"object_id": "lc_cryo_hospital", "label": "Cryo-Hospital", "class_string": "PrimalItemStructure_CryoHospital_C", "tags": ["structure", "healing", "lost_colony"]},
    {"object_id": "lc_medical_stand", "label": "Medical Stand", "class_string": "PrimalItemStructure_MedicalStand_C", "tags": ["structure", "healing", "lost_colony"]},
    {"object_id": "lc_war_bench", "label": "War Bench", "class_string": "PrimalItemStructure_WarBench_C", "tags": ["structure", "crafting", "lost_colony"]},
]

LOST_COLONY_LOOT_SOURCES = [
    {"object_id": "lc_city_t1", "label": "City Loot Chest (Tier 1)", "class_string": "SupplyCrate_LostLootChest_T1_C", "tags": ["loot_crate", "lost_colony", "city"]},
    {"object_id": "lc_city_t2", "label": "City Loot Chest (Tier 2)", "class_string": "SupplyCrate_LostLootChest_T2_C", "tags": ["loot_crate", "lost_colony", "city"]},
    {"object_id": "lc_city_t3", "label": "City Loot Chest (Tier 3)", "class_string": "SupplyCrate_LostLootChest_T3_C", "tags": ["loot_crate", "lost_colony", "city"]},
    {"object_id": "lc_cave_t1", "label": "Lost Colony Cave (Tier 1)", "class_string": "SupplyCrate_LostLootChest_CAVE_T1_C", "tags": ["loot_crate", "lost_colony", "cave"]},
    {"object_id": "lc_cave_t2", "label": "Lost Colony Cave (Tier 2)", "class_string": "SupplyCrate_LostLootChest_CAVE_T2_C", "tags": ["loot_crate", "lost_colony", "cave"]},
    {"object_id": "lc_cave_t3", "label": "Lost Colony Cave (Tier 3)", "class_string": "SupplyCrate_LostLootChest_CAVE_T3_C", "tags": ["loot_crate", "lost_colony", "cave"]},
    {"object_id": "lc_outpost_defend_gamma", "label": "Defense Outpost (Gamma)", "class_string": "StructureBP_Mission_Outpost_LootStructure_Defend_Gamma_C", "tags": ["loot_crate", "lost_colony", "outpost", "mission"]},
    {"object_id": "lc_outpost_defend_beta", "label": "Defense Outpost (Beta)", "class_string": "StructureBP_Mission_Outpost_LootStructure_Defend_Beta_C", "tags": ["loot_crate", "lost_colony", "outpost", "mission"]},
    {"object_id": "lc_outpost_defend_alpha", "label": "Defense Outpost (Alpha)", "class_string": "StructureBP_Mission_Outpost_LootStructure_Defend_Alpha_C", "tags": ["loot_crate", "lost_colony", "outpost", "mission"]},
    {"object_id": "lc_outpost_attack_gamma", "label": "Attack Outpost (Gamma)", "class_string": "StructureBP_Mission_Outpost_LootStructure_Attack_Training_Gamma_C", "tags": ["loot_crate", "lost_colony", "outpost", "mission"]},
    {"object_id": "lc_outpost_attack_beta", "label": "Attack Outpost (Beta)", "class_string": "StructureBP_Mission_Outpost_LootStructure_Attack_Training_Beta_C", "tags": ["loot_crate", "lost_colony", "outpost", "mission"]},
    {"object_id": "lc_outpost_attack_alpha", "label": "Attack Outpost (Alpha)", "class_string": "StructureBP_Mission_Outpost_LootStructure_Attack_Training_Alpha_C", "tags": ["loot_crate", "lost_colony", "outpost", "mission"]},
    {"object_id": "lc_thrall_cultist", "label": "Thrall Cultist Drop", "class_string": "DinoDropInventoryComponent_Thrall_Cultist_C", "tags": ["dino_drop", "lost_colony", "thrall"]},
    {"object_id": "lc_thrall_fighter", "label": "Thrall Fighter Drop", "class_string": "DinoDropInventoryComponent_Thrall_Fighter_C", "tags": ["dino_drop", "lost_colony", "thrall"]},
    {"object_id": "lc_thrall_soldier_flamethrower", "label": "Thrall Soldier (Flamethrower) Drop", "class_string": "DinoDropInventoryComponent_Thrall_SoldierWithFlamethrower_C", "tags": ["dino_drop", "lost_colony", "thrall"]},
    {"object_id": "lc_thrall_soldier_spear", "label": "Thrall Soldier (Spear) Drop", "class_string": "DinoDropInventoryComponent_Thrall_SoldierWithSpear_C", "tags": ["dino_drop", "lost_colony", "thrall"]},
    {"object_id": "lc_thrall_soldier", "label": "Thrall Soldier Drop", "class_string": "DinoDropInventoryComponent_Thrall_Soldier_C", "tags": ["dino_drop", "lost_colony", "thrall"]},
    {"object_id": "lc_thrall_soldier_bola", "label": "Thrall Soldier (Bola) Drop", "class_string": "DinoDropInventoryComponent_Thrall_Soldier_WithBola_C", "tags": ["dino_drop", "lost_colony", "thrall"]},
    {"object_id": "lc_thrall_soldier_crossbow", "label": "Thrall Soldier (Crossbow) Drop", "class_string": "DinoDropInventoryComponent_Thrall_Soldier_WithCrossbow_C", "tags": ["dino_drop", "lost_colony", "thrall"]},
    {"object_id": "lc_thrall_soldier_rocket", "label": "Thrall Soldier (Rocket) Drop", "class_string": "DinoDropInventoryComponent_Thrall_Soldier_WithRocketLauncher_C", "tags": ["dino_drop", "lost_colony", "thrall"]},
    {"object_id": "lc_thrall_soldier_shotgun", "label": "Thrall Soldier (Shotgun) Drop", "class_string": "DinoDropInventoryComponent_Thrall_Soldier_WithShotgun_C", "tags": ["dino_drop", "lost_colony", "thrall"]},
    {"object_id": "lc_thrall_soldier_sniper", "label": "Thrall Soldier (Sniper) Drop", "class_string": "DinoDropInventoryComponent_Thrall_Soldier_WithSniperRifle_C", "tags": ["dino_drop", "lost_colony", "thrall"]},
    {"object_id": "lc_thrall_tamer", "label": "Thrall Tamer Drop", "class_string": "DinoDropInventoryComponent_Thrall_Tamer_C", "tags": ["dino_drop", "lost_colony", "thrall"]},
]


async def add_lost_colony_data(db_path: str):
    """Add Lost Colony data to database."""
    import json
    
    async with aiosqlite.connect(db_path) as db:
        print("Removing old Lost Colony entries...")
        await db.execute("DELETE FROM ark_ref_items WHERE content_pack_id='lost_colony'")
        await db.execute("DELETE FROM ark_ref_loot_sources WHERE content_pack_id='lost_colony'")
        
        print("Adding Lost Colony items...")
        for item in LOST_COLONY_ITEMS:
            await db.execute("""
                INSERT OR REPLACE INTO ark_ref_items (
                    object_id, label, class_string, tags, content_pack_id
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                item["object_id"],
                item["label"],
                item["class_string"],
                json.dumps(item.get("tags", [])),
                "lost_colony",
            ))
        
        print(f"  Added {len(LOST_COLONY_ITEMS)} items")
        
        print("Adding Lost Colony loot sources...")
        for loot in LOST_COLONY_LOOT_SOURCES:
            await db.execute("""
                INSERT OR REPLACE INTO ark_ref_loot_sources (
                    object_id, label, class_string, tags, content_pack_id
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                loot["object_id"],
                loot["label"],
                loot["class_string"],
                json.dumps(loot.get("tags", [])),
                "lost_colony",
            ))
        
        print(f"  Added {len(LOST_COLONY_LOOT_SOURCES)} loot sources")
        
        await db.commit()
    
    print("\nLost Colony data updated successfully!")


async def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/opt/phoenix-bot/data/phoenix_bot.db"
    print(f"Database: {db_path}\n")
    await add_lost_colony_data(db_path)


if __name__ == "__main__":
    asyncio.run(main())
