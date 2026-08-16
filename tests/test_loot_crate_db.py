"""
Tests for loot_crate_db.py

Tests for loot crate configuration database operations.
"""

import pytest
import asyncio
import aiosqlite
import tempfile
import os
from pathlib import Path

from bot.database.loot_crate_db import (
    init_loot_crate_tables,
    create_crate_config,
    get_crate_config,
    get_crate_configs,
    get_crate_with_sets,
    update_crate_config,
    delete_crate_config,
    create_item_set,
    update_item_set,
    delete_item_set,
    create_set_item,
    update_set_item,
    delete_set_item,
    import_crate_from_ini,
    export_crate_to_ini,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    asyncio.run(init_loot_crate_tables(path))
    
    yield path
    
    os.unlink(path)


class TestCrateConfigCRUD:
    """Tests for crate config CRUD operations."""
    
    @pytest.mark.asyncio
    async def test_create_crate_config(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            label="Level 15 Crate",
            min_item_sets=1,
            max_item_sets=2,
            prevent_duplicates=True,
            db_path=temp_db
        )
        
        assert crate_id is not None
        assert crate_id > 0
    
    @pytest.mark.asyncio
    async def test_get_crate_config(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            label="Level 15 Crate",
            db_path=temp_db
        )
        
        config = await get_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        assert config is not None
        assert config['id'] == crate_id
        assert config['label'] == "Level 15 Crate"
        assert config['min_item_sets'] == 1
    
    @pytest.mark.asyncio
    async def test_get_crate_configs_list(self, temp_db):
        await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            label="Level 15 Crate",
            db_path=temp_db
        )
        
        await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level30_C",
            label="Level 30 Crate",
            db_path=temp_db
        )
        
        configs = await get_crate_configs(
            guild_id=123456,
            server_name="TestServer",
            db_path=temp_db
        )
        
        assert len(configs) == 2
    
    @pytest.mark.asyncio
    async def test_get_crate_configs_guild_isolation(self, temp_db):
        await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        await create_crate_config(
            guild_id=999999,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        configs1 = await get_crate_configs(123456, "TestServer", temp_db)
        configs2 = await get_crate_configs(999999, "TestServer", temp_db)
        
        assert len(configs1) == 1
        assert len(configs2) == 1
    
    @pytest.mark.asyncio
    async def test_update_crate_config(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            min_item_sets=1,
            db_path=temp_db
        )
        
        success = await update_crate_config(
            crate_config_id=crate_id,
            db_path=temp_db,
            min_item_sets=3,
            max_item_sets=5,
            label="Updated Label"
        )
        
        assert success == True
        
        config = await get_crate_config(123456, "TestServer", "SupplyCrate_Level15_C", temp_db)
        assert config['min_item_sets'] == 3
        assert config['max_item_sets'] == 5
        assert config['label'] == "Updated Label"
    
    @pytest.mark.asyncio
    async def test_delete_crate_config(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        success = await delete_crate_config(crate_id, temp_db)
        assert success == True
        
        config = await get_crate_config(123456, "TestServer", "SupplyCrate_Level15_C", temp_db)
        assert config is None
    
    @pytest.mark.asyncio
    async def test_duplicate_crate_unique_constraint(self, temp_db):
        await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        with pytest.raises(Exception):
            await create_crate_config(
                guild_id=123456,
                server_name="TestServer",
                class_string="SupplyCrate_Level15_C",
                db_path=temp_db
            )


class TestItemSetCRUD:
    """Tests for item set CRUD operations."""
    
    @pytest.mark.asyncio
    async def test_create_item_set(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        set_id = await create_item_set(
            crate_config_id=crate_id,
            set_name="Basic Items",
            min_items=1,
            max_items=3,
            weight=1.0,
            db_path=temp_db
        )
        
        assert set_id is not None
    
    @pytest.mark.asyncio
    async def test_update_item_set(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        set_id = await create_item_set(
            crate_config_id=crate_id,
            min_items=1,
            db_path=temp_db
        )
        
        success = await update_item_set(
            item_set_id=set_id,
            db_path=temp_db,
            min_items=2,
            max_items=5,
            weight=0.5
        )
        
        assert success == True
    
    @pytest.mark.asyncio
    async def test_delete_item_set(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        set_id = await create_item_set(
            crate_config_id=crate_id,
            db_path=temp_db
        )
        
        success = await delete_item_set(set_id, temp_db)
        assert success == True
    
    @pytest.mark.asyncio
    async def test_multiple_sets_ordered(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        set_id1 = await create_item_set(crate_id, "Set 1", db_path=temp_db)
        set_id2 = await create_item_set(crate_id, "Set 2", db_path=temp_db)
        set_id3 = await create_item_set(crate_id, "Set 3", db_path=temp_db)
        
        crate = await get_crate_with_sets(crate_id, temp_db)
        assert len(crate['item_sets']) == 3
        assert crate['item_sets'][0]['set_order'] == 0
        assert crate['item_sets'][1]['set_order'] == 1
        assert crate['item_sets'][2]['set_order'] == 2


class TestSetItemCRUD:
    """Tests for set item CRUD operations."""
    
    @pytest.mark.asyncio
    async def test_create_set_item(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        set_id = await create_item_set(
            crate_config_id=crate_id,
            db_path=temp_db
        )
        
        item_id = await create_set_item(
            item_set_id=set_id,
            class_string="PrimalItem_WeaponStonePick_C",
            label="Stone Pick",
            min_quantity=1,
            max_quantity=2,
            db_path=temp_db
        )
        
        assert item_id is not None
    
    @pytest.mark.asyncio
    async def test_update_set_item(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        set_id = await create_item_set(crate_id, db_path=temp_db)
        
        item_id = await create_set_item(
            item_set_id=set_id,
            class_string="PrimalItem_WeaponStonePick_C",
            min_quantity=1,
            db_path=temp_db
        )
        
        success = await update_set_item(
            item_id=item_id,
            db_path=temp_db,
            min_quantity=2,
            max_quantity=5,
            quality_min=0.5,
            quality_max=1.0
        )
        
        assert success == True
    
    @pytest.mark.asyncio
    async def test_delete_set_item(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        set_id = await create_item_set(crate_id, db_path=temp_db)
        
        item_id = await create_set_item(
            item_set_id=set_id,
            class_string="PrimalItem_WeaponStonePick_C",
            db_path=temp_db
        )
        
        success = await delete_set_item(item_id, temp_db)
        assert success == True
    
    @pytest.mark.asyncio
    async def test_multiple_items_ordered(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        set_id = await create_item_set(crate_id, db_path=temp_db)
        
        item1 = await create_set_item(set_id, "Item1_C", db_path=temp_db)
        item2 = await create_set_item(set_id, "Item2_C", db_path=temp_db)
        item3 = await create_set_item(set_id, "Item3_C", db_path=temp_db)
        
        crate = await get_crate_with_sets(crate_id, temp_db)
        items = crate['item_sets'][0]['items']
        
        assert len(items) == 3
        assert items[0]['item_order'] == 0
        assert items[1]['item_order'] == 1
        assert items[2]['item_order'] == 2


class TestGetCrateWithSets:
    """Tests for retrieving complete crate data."""
    
    @pytest.mark.asyncio
    async def test_get_full_crate(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            label="Level 15 Drop",
            min_item_sets=1,
            max_item_sets=2,
            db_path=temp_db
        )
        
        set_id = await create_item_set(
            crate_config_id=crate_id,
            set_name="Tools",
            min_items=1,
            max_items=2,
            weight=1.0,
            db_path=temp_db
        )
        
        await create_set_item(
            item_set_id=set_id,
            class_string="PrimalItem_WeaponStonePick_C",
            label="Stone Pick",
            min_quantity=1,
            max_quantity=1,
            quality_min=0,
            quality_max=0.5,
            chance_to_be_blueprint=0.1,
            db_path=temp_db
        )
        
        crate = await get_crate_with_sets(crate_id, temp_db)
        
        assert crate is not None
        assert crate['class_string'] == "SupplyCrate_Level15_C"
        assert crate['label'] == "Level 15 Drop"
        assert len(crate['item_sets']) == 1
        
        item_set = crate['item_sets'][0]
        assert item_set['set_name'] == "Tools"
        assert len(item_set['items']) == 1
        
        item = item_set['items'][0]
        assert item['class_string'] == "PrimalItem_WeaponStonePick_C"
        assert item['quality_max'] == 0.5


class TestImportExport:
    """Tests for import/export operations."""
    
    @pytest.mark.asyncio
    async def test_import_crate_from_parsed_data(self, temp_db):
        crate_data = {
            'class_string': 'SupplyCrate_Level15_C',
            'min_item_sets': 1,
            'max_item_sets': 1,
            'prevent_duplicates': True,
            'item_sets': [
                {
                    'min_items': 2,
                    'max_items': 4,
                    'weight': 1.0,
                    'items': [
                        {
                            'class_string': 'PrimalItem_WeaponStonePick_C',
                            'min_quantity': 1,
                            'max_quantity': 2,
                            'quality_min': 0,
                            'quality_max': 0,
                            'chance_to_be_blueprint': 0.1
                        }
                    ]
                }
            ]
        }
        
        crate_id = await import_crate_from_ini(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            crate_data=crate_data,
            db_path=temp_db
        )
        
        assert crate_id is not None
        
        crate = await get_crate_with_sets(crate_id, temp_db)
        assert len(crate['item_sets']) == 1
        assert len(crate['item_sets'][0]['items']) == 1
    
    @pytest.mark.asyncio
    async def test_export_to_ini_format(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            min_item_sets=1,
            max_item_sets=1,
            db_path=temp_db
        )
        
        set_id = await create_item_set(
            crate_config_id=crate_id,
            min_items=1,
            max_items=2,
            weight=1.0,
            db_path=temp_db
        )
        
        await create_set_item(
            item_set_id=set_id,
            class_string="PrimalItem_WeaponStonePick_C",
            min_quantity=1,
            max_quantity=1,
            db_path=temp_db
        )
        
        ini_output = await export_crate_to_ini(crate_id, temp_db)
        
        assert "ConfigOverrideSupplyCrateItems=" in ini_output
        assert "SupplyCrate_Level15_C" in ini_output
        assert "PrimalItem_WeaponStonePick_C" in ini_output
        assert "MinItemSets=1" in ini_output


class TestCascadeDelete:
    """Tests for cascade deletion behavior."""
    
    @pytest.mark.asyncio
    async def test_delete_crate_cascades_to_sets_and_items(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        set_id = await create_item_set(crate_id, db_path=temp_db)
        
        item_id = await create_set_item(set_id, "Item_C", db_path=temp_db)
        
        await delete_crate_config(crate_id, temp_db)
        
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute("SELECT * FROM loot_crate_configs WHERE id = ?", (crate_id,))
            assert await cursor.fetchone() is None
            
            cursor = await db.execute("SELECT * FROM loot_item_sets WHERE id = ?", (set_id,))
            assert await cursor.fetchone() is None
            
            cursor = await db.execute("SELECT * FROM loot_set_items WHERE id = ?", (item_id,))
            assert await cursor.fetchone() is None
    
    @pytest.mark.asyncio
    async def test_delete_set_cascades_to_items(self, temp_db):
        crate_id = await create_crate_config(
            guild_id=123456,
            server_name="TestServer",
            class_string="SupplyCrate_Level15_C",
            db_path=temp_db
        )
        
        set_id = await create_item_set(crate_id, db_path=temp_db)
        
        item_id = await create_set_item(set_id, "Item_C", db_path=temp_db)
        
        await delete_item_set(set_id, temp_db)
        
        async with aiosqlite.connect(temp_db) as db:
            cursor = await db.execute("SELECT * FROM loot_set_items WHERE id = ?", (item_id,))
            assert await cursor.fetchone() is None
