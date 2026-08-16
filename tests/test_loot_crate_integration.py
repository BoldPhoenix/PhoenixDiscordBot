"""
Integration test for loot crate workflow: parse → store → edit → export
"""

import pytest
import asyncio
import tempfile
import os

from bot.utils.loot_crate_parser import parse_all_crates
from bot.database.loot_crate_db import (
    init_loot_crate_tables,
    import_crate_from_ini,
    get_crate_with_sets,
    update_crate_config,
    create_item_set,
    create_set_item,
    export_crate_to_ini,
)


REAL_GAME_INI = '''
[/Script/ShooterGame.ShooterGameMode]
ConfigOverrideSupplyCrateItems=(
    SupplyCrateClassString="SupplyCrate_Level15_C",
    MinItemSets=1,
    MaxItemSets=1,
    bPreventDuplicates=True,
    ItemSets=(
        (
            MinNumItems=2,
            MaxNumItems=4,
            SetWeight=1.0,
            ItemEntries=(
                (
                    EntryWeight=1.0,
                    ItemClassStrings=("PrimalItem_WeaponStonePick_C"),
                    ItemsWeights=(1),
                    MinQuantity=1,
                    MaxQuantity=1,
                    MinQuality=0,
                    MaxQuality=0,
                    bForceBlueprint=False,
                    ChanceToBeBlueprintOverride=0.0
                ),
                (
                    EntryWeight=0.5,
                    ItemClassStrings=("PrimalItem_WeaponStoneHatchet_C"),
                    ItemsWeights=(1),
                    MinQuantity=1,
                    MaxQuantity=2,
                    MinQuality=0,
                    MaxQuality=0.5,
                    bForceBlueprint=False,
                    ChanceToBeBlueprintOverride=0.1
                )
            )
        )
    )
)
'''


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    asyncio.run(init_loot_crate_tables(path))
    
    yield path
    
    os.unlink(path)


class TestFullWorkflow:
    """Test the complete workflow from parsing to export."""
    
    @pytest.mark.asyncio
    async def test_parse_store_edit_export(self, temp_db):
        crates = parse_all_crates(REAL_GAME_INI)
        assert len(crates) == 1
        
        crate_data = crates[0]
        assert crate_data['class_string'] == 'SupplyCrate_Level15_C'
        
        crate_id = await import_crate_from_ini(
            guild_id=123456,
            server_name="TestServer",
            class_string=crate_data['class_string'],
            crate_data=crate_data,
            db_path=temp_db
        )
        
        assert crate_id is not None
        
        stored_crate = await get_crate_with_sets(crate_id, temp_db)
        assert stored_crate is not None
        assert stored_crate['class_string'] == 'SupplyCrate_Level15_C'
        assert len(stored_crate['item_sets']) == 1
        
        item_set = stored_crate['item_sets'][0]
        assert len(item_set['items']) == 2
        assert item_set['items'][0]['class_string'] == 'PrimalItem_WeaponStonePick_C'
        assert item_set['items'][1]['class_string'] == 'PrimalItem_WeaponStoneHatchet_C'
        
        await update_crate_config(
            crate_config_id=crate_id,
            db_path=temp_db,
            min_item_sets=2,
            max_item_sets=3,
            label="Modified Level 15"
        )
        
        new_set_id = await create_item_set(
            crate_config_id=crate_id,
            set_name="Bonus Items",
            min_items=1,
            max_items=1,
            weight=0.5,
            db_path=temp_db
        )
        
        await create_set_item(
            item_set_id=new_set_id,
            class_string="PrimalItem_WeaponMetalPick_C",
            label="Metal Pick",
            min_quantity=1,
            max_quantity=1,
            quality_min=1.0,
            quality_max=2.0,
            chance_to_be_blueprint=0.5,
            db_path=temp_db
        )
        
        updated_crate = await get_crate_with_sets(crate_id, temp_db)
        assert updated_crate['min_item_sets'] == 2
        assert updated_crate['max_item_sets'] == 3
        assert updated_crate['label'] == "Modified Level 15"
        assert len(updated_crate['item_sets']) == 2
        
        ini_output = await export_crate_to_ini(crate_id, temp_db)
        
        assert "ConfigOverrideSupplyCrateItems=" in ini_output
        assert "SupplyCrate_Level15_C" in ini_output
        assert "MinItemSets=2" in ini_output
        assert "MaxItemSets=3" in ini_output
        assert "PrimalItem_WeaponStonePick_C" in ini_output
        assert "PrimalItem_WeaponStoneHatchet_C" in ini_output
        assert "PrimalItem_WeaponMetalPick_C" in ini_output
        assert "MinQuality=1.0" in ini_output
        assert "MaxQuality=2.0" in ini_output
    
    @pytest.mark.asyncio
    async def test_multiple_crates_workflow(self, temp_db):
        multi_crate_ini = '''
[/Script/ShooterGame.ShooterGameMode]
ConfigOverrideSupplyCrateItems=(
    SupplyCrateClassString="SupplyCrate_Level15_C",
    MinItemSets=1,
    MaxItemSets=1,
    ItemSets=((
        MinNumItems=1,
        MaxNumItems=1,
        SetWeight=1.0,
        ItemEntries=((
            ItemClassStrings=("PrimalItem_WeaponStonePick_C"),
            MinQuantity=1
        ))
    ))
)
ConfigOverrideSupplyCrateItems=(
    SupplyCrateClassString="SupplyCrate_Level30_C",
    MinItemSets=2,
    MaxItemSets=3,
    ItemSets=((
        MinNumItems=2,
        MaxNumItems=4,
        SetWeight=1.0,
        ItemEntries=((
            ItemClassStrings=("PrimalItem_WeaponMetalPick_C"),
            MinQuantity=1
        ))
    ))
)
'''
        
        crates = parse_all_crates(multi_crate_ini)
        assert len(crates) == 2
        
        for crate_data in crates:
            crate_id = await import_crate_from_ini(
                guild_id=123456,
                server_name="TestServer",
                class_string=crate_data['class_string'],
                crate_data=crate_data,
                db_path=temp_db
            )
            assert crate_id is not None
        
        from bot.database.loot_crate_db import get_crate_configs
        stored_crates = await get_crate_configs(123456, "TestServer", temp_db)
        assert len(stored_crates) == 2
    
    @pytest.mark.asyncio
    async def test_lost_colony_workflow(self, temp_db):
        lost_colony_ini = '''
ConfigOverrideSupplyCrateItems=(
    SupplyCrateClassString="SupplyCrate_LostLootChest_T1_C",
    MinItemSets=1,
    MaxItemSets=1,
    bPreventDuplicates=True,
    ItemSets=(
        (
            MinNumItems=1,
            MaxNumItems=2,
            SetWeight=1.0,
            ItemEntries=(
                (
                    EntryWeight=1.0,
                    ItemClassStrings=("PrimalItem_WeaponTekSpear_C"),
                    ItemsWeights=(1),
                    MinQuantity=1,
                    MaxQuantity=1,
                    MinQuality=1.0,
                    MaxQuality=2.0,
                    bForceBlueprint=False,
                    ChanceToBeBlueprintOverride=0.5
                )
            )
        )
    )
)
'''
        
        crates = parse_all_crates(lost_colony_ini)
        assert len(crates) == 1
        
        crate_data = crates[0]
        assert crate_data['class_string'] == 'SupplyCrate_LostLootChest_T1_C'
        
        crate_id = await import_crate_from_ini(
            guild_id=123456,
            server_name="LostColonyServer",
            class_string=crate_data['class_string'],
            crate_data=crate_data,
            db_path=temp_db
        )
        
        stored = await get_crate_with_sets(crate_id, temp_db)
        assert stored['class_string'] == 'SupplyCrate_LostLootChest_T1_C'
        assert len(stored['item_sets']) == 1
        
        item = stored['item_sets'][0]['items'][0]
        assert item['class_string'] == 'PrimalItem_WeaponTekSpear_C'
        assert item['quality_min'] == 1.0
        assert item['quality_max'] == 2.0
        assert item['chance_to_be_blueprint'] == 0.5
