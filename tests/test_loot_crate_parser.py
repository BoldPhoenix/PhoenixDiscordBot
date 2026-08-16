"""
Tests for loot_crate_parser.py

Comprehensive tests for parsing ARK ConfigOverrideSupplyCrateItems.
"""

import pytest
from bot.utils.loot_crate_parser import (
    extract_crate_blocks,
    parse_crate_block,
    parse_all_crates,
    _extract_balanced_block,
    _split_top_level_tuples,
)


class TestExtractBalancedBlock:
    """Tests for balanced parentheses extraction."""
    
    def test_simple_block(self):
        content = "(test)"
        result = _extract_balanced_block(content)
        assert result == "(test)"
    
    def test_nested_block(self):
        content = "(outer (inner) still outer)"
        result = _extract_balanced_block(content)
        assert result == "(outer (inner) still outer)"
    
    def test_deeply_nested(self):
        content = "(a (b (c (d) c) b) a)"
        result = _extract_balanced_block(content)
        assert result == "(a (b (c (d) c) b) a)"
    
    def test_string_with_parens(self):
        content = '(name="test(1)", value=2)'
        result = _extract_balanced_block(content)
        assert result == '(name="test(1)", value=2)'
    
    def test_multiple_strings_with_parens(self):
        content = '(a="(", b=")")'
        result = _extract_balanced_block(content)
        assert result == '(a="(", b=")")'
    
    def test_unclosed_block(self):
        content = "(unclosed"
        result = _extract_balanced_block(content)
        assert result is None
    
    def test_empty_block(self):
        content = "()"
        result = _extract_balanced_block(content)
        assert result == "()"
    
    def test_block_after_prefix(self):
        content = "prefix (content)"
        result = _extract_balanced_block(content)
        assert result is None
    
    def test_block_starting_with_paren(self):
        content = "(content)"
        result = _extract_balanced_block(content)
        assert result == "(content)"


class TestExtractCrateBlocks:
    """Tests for extracting crate blocks from INI content."""
    
    def test_single_crate(self):
        content = '''
[/Script/ShooterGame.ShooterGameMode]
ConfigOverrideSupplyCrateItems=(
    SupplyCrateClassString="SupplyCrate_Level15_C",
    MinItemSets=1,
    MaxItemSets=1
)
'''
        blocks = extract_crate_blocks(content)
        assert len(blocks) == 1
        assert "SupplyCrate_Level15_C" in blocks[0]
    
    def test_multiple_crates(self):
        content = '''
[/Script/ShooterGame.ShooterGameMode]
ConfigOverrideSupplyCrateItems=(
    SupplyCrateClassString="SupplyCrate_Level15_C",
    MinItemSets=1
)
ConfigOverrideSupplyCrateItems=(
    SupplyCrateClassString="SupplyCrate_Level30_C",
    MinItemSets=2
)
'''
        blocks = extract_crate_blocks(content)
        assert len(blocks) == 2
    
    def test_no_crates(self):
        content = '''
[/Script/ShooterGame.ShooterGameMode]
MaxPlayers=70
'''
        blocks = extract_crate_blocks(content)
        assert len(blocks) == 0
    
    def test_crate_with_nested_itemsets(self):
        content = '''
ConfigOverrideSupplyCrateItems=(
    SupplyCrateClassString="SupplyCrate_Cave_QualityTier1_C",
    MinItemSets=1,
    MaxItemSets=1,
    ItemSets=(
        (
            MinNumItems=1,
            MaxNumItems=3,
            ItemEntries=(
                (ItemClassStrings=("PrimalItem_WeaponStonePick_C"), MinQuantity=1)
            )
        )
    )
)
'''
        blocks = extract_crate_blocks(content)
        assert len(blocks) == 1
        assert "ItemSets" in blocks[0]


class TestParseCrateBlock:
    """Tests for parsing individual crate blocks."""
    
    def test_minimal_crate(self):
        block = 'SupplyCrateClassString="SupplyCrate_Level15_C"'
        result = parse_crate_block(block)
        assert result is not None
        assert result['class_string'] == 'SupplyCrate_Level15_C'
        assert result['min_item_sets'] == 1
        assert result['max_item_sets'] == 1
    
    def test_full_basic_crate(self):
        block = '''
(
    SupplyCrateClassString="SupplyCrate_Level15_C",
    MinItemSets=2,
    MaxItemSets=4,
    bPreventDuplicates=False
)
'''
        result = parse_crate_block(block)
        assert result is not None
        assert result['class_string'] == 'SupplyCrate_Level15_C'
        assert result['min_item_sets'] == 2
        assert result['max_item_sets'] == 4
        assert result['prevent_duplicates'] == False
    
    def test_crate_with_single_itemset(self):
        block = '''
(
    SupplyCrateClassString="SupplyCrate_Level15_C",
    MinItemSets=1,
    MaxItemSets=1,
    bPreventDuplicates=True,
    ItemSets=(
        (
            MinNumItems=2,
            MaxNumItems=4,
            SetWeight=1.0
        )
    )
)
'''
        result = parse_crate_block(block)
        assert result is not None
        assert len(result['item_sets']) == 1
        assert result['item_sets'][0]['min_items'] == 2
        assert result['item_sets'][0]['max_items'] == 4
        assert result['item_sets'][0]['weight'] == 1.0
    
    def test_crate_with_items(self):
        block = '''
(
    SupplyCrateClassString="SupplyCrate_Level15_C",
    ItemSets=(
        (
            MinNumItems=1,
            MaxNumItems=2,
            SetWeight=1.0,
            ItemEntries=(
                (
                    ItemClassStrings=("PrimalItem_WeaponStonePick_C"),
                    ItemsWeights=(1),
                    MinQuantity=1,
                    MaxQuantity=2,
                    MinQuality=0,
                    MaxQuality=0,
                    bForceBlueprint=False,
                    ChanceToBeBlueprintOverride=0.5
                )
            )
        )
    )
)
'''
        result = parse_crate_block(block)
        assert result is not None
        assert len(result['item_sets']) == 1
        assert len(result['item_sets'][0]['items']) == 1
        
        item = result['item_sets'][0]['items'][0]
        assert item['class_string'] == 'PrimalItem_WeaponStonePick_C'
        assert item['min_quantity'] == 1
        assert item['max_quantity'] == 2
        assert item['chance_to_be_blueprint'] == 0.5
    
    def test_multiple_itemsets(self):
        block = '''
(
    SupplyCrateClassString="SupplyCrate_Level15_C",
    ItemSets=(
        (
            MinNumItems=1,
            MaxNumItems=1,
            SetWeight=0.5
        )
        ,
        (
            MinNumItems=2,
            MaxNumItems=3,
            SetWeight=0.5
        )
    )
)
'''
        result = parse_crate_block(block)
        assert result is not None
        assert len(result['item_sets']) == 2
        assert result['item_sets'][0]['weight'] == 0.5
        assert result['item_sets'][1]['weight'] == 0.5
    
    def test_missing_class_string(self):
        block = '(MinItemSets=1, MaxItemSets=1)'
        result = parse_crate_block(block)
        assert result is None


class TestSplitTopLevelTuples:
    """Tests for splitting comma-separated tuples."""
    
    def test_single_tuple(self):
        content = "(a=1, b=2)"
        result = _split_top_level_tuples(content)
        assert len(result) == 1
        assert result[0] == "(a=1, b=2)"
    
    def test_multiple_tuples(self):
        content = "(a=1), (b=2), (c=3)"
        result = _split_top_level_tuples(content)
        assert len(result) == 3
    
    def test_nested_tuples_not_split(self):
        content = "(outer (inner) outer)"
        result = _split_top_level_tuples(content)
        assert len(result) == 1
    
    def test_tuples_with_nested_content(self):
        content = '''
(
    MinNumItems=1,
    ItemEntries=((ItemClassStrings=("Item_C")))
)
,
(
    MinNumItems=2,
    ItemEntries=((ItemClassStrings=("Item2_C")))
)
'''
        result = _split_top_level_tuples(content)
        assert len(result) == 2


class TestParseAllCrates:
    """Tests for full INI parsing."""
    
    def test_real_world_game_ini(self):
        """Test with a realistic Game.ini snippet."""
        content = '''
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

ConfigOverrideSupplyCrateItems=(
    SupplyCrateClassString="SupplyCrate_Cave_QualityTier1_C",
    MinItemSets=1,
    MaxItemSets=2,
    bPreventDuplicates=False,
    ItemSets=(
        (
            MinNumItems=1,
            MaxNumItems=3,
            SetWeight=1.0,
            ItemEntries=(
                (
                    EntryWeight=1.0,
                    ItemClassStrings=("PrimalItem_WeaponMetalPick_C"),
                    ItemsWeights=(1),
                    MinQuantity=1,
                    MaxQuantity=1,
                    MinQuality=0.5,
                    MaxQuality=1.0,
                    bForceBlueprint=False,
                    ChanceToBeBlueprintOverride=0.25
                )
            )
        )
    )
)
'''
        crates = parse_all_crates(content)
        assert len(crates) == 2
        
        crate1 = crates[0]
        assert crate1['class_string'] == 'SupplyCrate_Level15_C'
        assert crate1['min_item_sets'] == 1
        assert crate1['max_item_sets'] == 1
        assert crate1['prevent_duplicates'] == True
        assert len(crate1['item_sets']) == 1
        assert len(crate1['item_sets'][0]['items']) == 2
        
        item1 = crate1['item_sets'][0]['items'][0]
        assert item1['class_string'] == 'PrimalItem_WeaponStonePick_C'
        assert item1['min_quantity'] == 1
        assert item1['max_quantity'] == 1
        
        item2 = crate1['item_sets'][0]['items'][1]
        assert item2['class_string'] == 'PrimalItem_WeaponStoneHatchet_C'
        assert item2['max_quantity'] == 2
        assert item2['quality_max'] == 0.5
        
        crate2 = crates[1]
        assert crate2['class_string'] == 'SupplyCrate_Cave_QualityTier1_C'
        assert crate2['max_item_sets'] == 2
        assert crate2['prevent_duplicates'] == False
    
    def test_lost_colony_crate(self):
        """Test with Lost Colony crate format."""
        content = '''
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
        crates = parse_all_crates(content)
        assert len(crates) == 1
        assert crates[0]['class_string'] == 'SupplyCrate_LostLootChest_T1_C'


class TestEdgeCases:
    """Edge case tests."""
    
    def test_empty_ini(self):
        crates = parse_all_crates("")
        assert len(crates) == 0
    
    def test_whitespace_only(self):
        crates = parse_all_crates("   \n\t  \n  ")
        assert len(crates) == 0
    
    def test_class_string_with_special_chars(self):
        block = 'SupplyCrateClassString="SupplyCrate_Test_123_C"'
        result = parse_crate_block(block)
        assert result['class_string'] == 'SupplyCrate_Test_123_C'
    
    def test_zero_values(self):
        block = '''
(
    SupplyCrateClassString="Test_C",
    MinItemSets=0,
    MaxItemSets=0
)
'''
        result = parse_crate_block(block)
        assert result['min_item_sets'] == 0
        assert result['max_item_sets'] == 0
    
    def test_float_weights(self):
        block = '''
(
    SupplyCrateClassString="Test_C",
    ItemSets=(
        (
            SetWeight=0.001
        )
    )
)
'''
        result = parse_crate_block(block)
        assert result['item_sets'][0]['weight'] == 0.001
    
    def test_boolean_case_insensitive(self):
        block1 = 'SupplyCrateClassString="Test_C", bPreventDuplicates=True'
        block2 = 'SupplyCrateClassString="Test_C", bPreventDuplicates=true'
        block3 = 'SupplyCrateClassString="Test_C", bPreventDuplicates=TRUE'
        
        for block in [block1, block2, block3]:
            result = parse_crate_block(block)
            assert result['prevent_duplicates'] == True
