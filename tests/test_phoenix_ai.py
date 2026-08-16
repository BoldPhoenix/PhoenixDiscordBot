"""
Tests for PhoenixAI RAG system.
Tests query classification, FTS search, context building, and rate limiting.
"""

import asyncio
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from bot.utils.phoenix_ai import (
    PhoenixAI,
    get_phoenix_ai,
    cleanup_phoenix_ai,
    _user_cooldowns,
    COOLDOWN_SECONDS,
)


@pytest.fixture
def temp_rag_db():
    """Create a temporary RAG database with test data."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE creatures (
            name TEXT PRIMARY KEY,
            blueprint TEXT,
            taming_method TEXT,
            base_health REAL,
            base_stamina REAL,
            base_weight REAL,
            base_melee REAL,
            incubation_time REAL,
            maturation_time REAL
        )
    """)
    
    cursor.execute("""
        CREATE VIRTUAL TABLE fts_creatures USING fts5(
            name,
            content='creatures',
            content_rowid='rowid'
        )
    """)
    
    cursor.execute("""
        CREATE TRIGGER creatures_ai AFTER INSERT ON creatures BEGIN
            INSERT INTO fts_creatures(rowid, name) VALUES (new.rowid, new.name);
        END
    """)
    
    test_creatures = [
        ("Rex", "Blueprint'/Game/PrimalEarth/Dino/Rex/Rex_Character_BP.Rex_Character_BP'", "Knockout", 1100, 420, 500, 62, 18000, 200000),
        ("Raptor", "Blueprint'/Game/PrimalEarth/Dino/Raptor/Raptor_Character_BP.Raptor_Character_BP'", "Knockout", 200, 150, 140, 15, 7200, 60000),
        ("Giganotosaurus", "Blueprint'/Game/PrimalEarth/Dino/Giganotosaurus/Gigant_Character_BP.Gigant_Character_BP'", "Knockout", 80000, 400, 500, 400, 64800, 500000),
    ]
    
    cursor.executemany(
        "INSERT INTO creatures (name, blueprint, taming_method, base_health, base_stamina, base_weight, base_melee, incubation_time, maturation_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        test_creatures
    )
    
    cursor.execute("""
        CREATE TABLE engrams (
            label TEXT PRIMARY KEY,
            class_string TEXT,
            required_level INTEGER,
            required_points INTEGER
        )
    """)
    
    cursor.execute("""
        CREATE VIRTUAL TABLE fts_engrams USING fts5(
            label,
            content='engrams',
            content_rowid='rowid'
        )
    """)
    
    cursor.execute("""
        CREATE TRIGGER engrams_ai AFTER INSERT ON engrams BEGIN
            INSERT INTO fts_engrams(rowid, label) VALUES (new.rowid, new.label);
        END
    """)
    
    test_engrams = [
        ("Stone Hatchet", "PrimalItem_WeaponStoneHatchet_C", 2, 3),
        ("Pike", "PrimalItem_WeaponPike_C", 25, 12),
        ("Assault Rifle", "PrimalItem_WeaponRifle_C", 55, 24),
    ]
    
    cursor.executemany(
        "INSERT INTO engrams (label, class_string, required_level, required_points) VALUES (?, ?, ?, ?)",
        test_engrams
    )
    
    cursor.execute("""
        CREATE TABLE ini_options (
            label TEXT,
            key TEXT,
            file TEXT,
            header TEXT,
            description TEXT,
            default_value TEXT,
            PRIMARY KEY (label, key)
        )
    """)
    
    cursor.execute("""
        CREATE VIRTUAL TABLE fts_ini USING fts5(
            label, key,
            content='ini_options',
            content_rowid='rowid'
        )
    """)
    
    cursor.execute("""
        CREATE TRIGGER ini_ai AFTER INSERT ON ini_options BEGIN
            INSERT INTO fts_ini(rowid, label, key) VALUES (new.rowid, new.label, new.key);
        END
    """)
    
    test_ini = [
        ("Taming Speed", "TamingSpeedMultiplier", "GameUserSettings.ini", "[ServerSettings]", "Multiplier for taming speed", "1.0"),
        ("XP Multiplier", "XPMultiplier", "GameUserSettings.ini", "[ServerSettings]", "Multiplier for XP gain", "1.0"),
    ]
    
    cursor.executemany(
        "INSERT INTO ini_options (label, key, file, header, description, default_value) VALUES (?, ?, ?, ?, ?, ?)",
        test_ini
    )
    
    cursor.execute("""
        CREATE TABLE qa_pairs (
            instruction TEXT PRIMARY KEY,
            output TEXT
        )
    """)
    
    cursor.execute("""
        CREATE VIRTUAL TABLE fts_qa USING fts5(
            instruction,
            content='qa_pairs',
            content_rowid='rowid'
        )
    """)
    
    cursor.execute("""
        CREATE TRIGGER qa_ai AFTER INSERT ON qa_pairs BEGIN
            INSERT INTO fts_qa(rowid, instruction) VALUES (new.rowid, new.instruction);
        END
    """)
    
    test_qa = [
        ("How do I tame a Rex?", "Use tranq arrows or darts, kibble preferred, protect during taming."),
        ("What is the best weapon for caves?", "Shotgun, crossbow, and sword are recommended for caves."),
    ]
    
    cursor.executemany(
        "INSERT INTO qa_pairs (instruction, output) VALUES (?, ?)",
        test_qa
    )
    
    conn.commit()
    conn.close()
    
    yield db_path
    
    db_path.unlink(missing_ok=True)


@pytest.fixture
def phoenix_ai(temp_rag_db):
    """Create a PhoenixAI instance with temp database."""
    ai = PhoenixAI(api_key="test_key", rag_db_path=temp_rag_db)
    yield ai
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(ai.close())
        loop.close()
    except Exception:
        pass


class TestQueryClassification:
    """Tests for query classification."""
    
    def test_classify_creature_query(self, phoenix_ai):
        result = phoenix_ai._classify_query("How do I tame a rex?")
        assert "creatures" in result
        assert "qa_pairs" in result
    
    def test_classify_engram_query(self, phoenix_ai):
        result = phoenix_ai._classify_query("How do I craft a pike?")
        assert "engrams" in result
    
    def test_classify_loot_query(self, phoenix_ai):
        result = phoenix_ai._classify_query("What loot drops from red beacons?")
        assert "loot_containers" in result
    
    def test_classify_ini_query(self, phoenix_ai):
        result = phoenix_ai._classify_query("How do I change taming speed in ini?")
        assert "ini_options" in result
    
    def test_classify_news_query(self, phoenix_ai):
        result = phoenix_ai._classify_query("What's in the latest patch?")
        assert "news_posts" in result
    
    def test_classify_unknown_defaults_to_common_tables(self, phoenix_ai):
        result = phoenix_ai._classify_query("random question")
        assert "creatures" in result
        assert "engrams" in result
        assert "qa_pairs" in result


class TestFtsQueryConversion:
    """Tests for FTS query conversion."""
    
    def test_simple_query(self, phoenix_ai):
        result = phoenix_ai._convert_to_fts_query("rex taming")
        assert result == "rex* OR taming*"
    
    def test_single_word(self, phoenix_ai):
        result = phoenix_ai._convert_to_fts_query("raptor")
        assert result == "raptor*"
    
    def test_special_chars_removed(self, phoenix_ai):
        result = phoenix_ai._convert_to_fts_query("what's the best?!")
        # Apostrophe is removed by regex, so "what's" becomes "whats"
        assert "whats*" in result
        assert "the*" in result
        assert "best*" in result
        assert "'" not in result
        assert "?" not in result
    
    def test_empty_query_returns_none(self, phoenix_ai):
        result = phoenix_ai._convert_to_fts_query("  ")
        assert result is None
    
    def test_short_words_filtered(self, phoenix_ai):
        result = phoenix_ai._convert_to_fts_query("a an the rex")
        assert "rex*" in result
        assert "a*" not in result


class TestKnowledgeSearch:
    """Tests for knowledge base search."""
    
    @pytest.mark.asyncio
    async def test_search_creatures(self, phoenix_ai):
        results = await phoenix_ai.search_knowledge("rex", max_results=5)
        assert len(results) > 0
        assert any(r.get("name") == "Rex" for r in results)
    
    @pytest.mark.asyncio
    async def test_search_engrams(self, phoenix_ai):
        results = await phoenix_ai.search_knowledge("pike weapon", max_results=5)
        assert len(results) > 0
        assert any("pike" in r.get("label", "").lower() for r in results)
    
    @pytest.mark.asyncio
    async def test_search_ini_options(self, phoenix_ai):
        results = await phoenix_ai.search_knowledge("taming multiplier config", max_results=5)
        assert len(results) > 0
    
    @pytest.mark.asyncio
    async def test_search_returns_source(self, phoenix_ai):
        results = await phoenix_ai.search_knowledge("rex", max_results=5)
        assert all("_source" in r for r in results)
    
    @pytest.mark.asyncio
    async def test_search_no_results_returns_empty(self, phoenix_ai):
        results = await phoenix_ai.search_knowledge("xyznonexistent123", max_results=5)
        assert results == []


class TestContextBuilding:
    """Tests for context building."""
    
    def test_format_creature_context(self, phoenix_ai):
        results = [
            {
                "name": "Rex",
                "blueprint": "Blueprint'/Game/Rex'",
                "taming_method": "Knockout",
                "base_health": 1100,
                "base_stamina": 420,
                "maturation_time": 200000,
            }
        ]
        context = phoenix_ai._format_creature_context(results)
        assert "Rex" in context
        assert "Knockout" in context
        assert "HP:1100" in context
        assert "55.6h" in context  # 200000/3600 rounded
    
    def test_format_engram_context(self, phoenix_ai):
        results = [
            {
                "label": "Stone Hatchet",
                "class_string": "PrimalItem_WeaponStoneHatchet_C",
                "required_level": 2,
                "required_points": 3,
            }
        ]
        context = phoenix_ai._format_engram_context(results)
        assert "Stone Hatchet" in context
        assert "cheat gfi PrimalItem_WeaponStoneHatchet 1 0 0" in context
        assert "Required Level: 2" in context
    
    def test_format_ini_context(self, phoenix_ai):
        results = [
            {
                "label": "Taming Speed",
                "key": "TamingSpeedMultiplier",
                "file": "GameUserSettings.ini",
                "header": "[ServerSettings]",
                "description": "Multiplier for taming",
                "default_value": "1.0",
            }
        ]
        context = phoenix_ai._format_ini_context(results)
        assert "Taming Speed" in context
        assert "TamingSpeedMultiplier" in context
        assert "GameUserSettings.ini" in context
    
    def test_build_context_empty_results(self, phoenix_ai):
        context = phoenix_ai.build_context([])
        assert "No relevant data found" in context
    
    def test_build_context_includes_header(self, phoenix_ai):
        results = [{"name": "Test", "_source": "creatures"}]
        context = phoenix_ai.build_context(results)
        assert "REFERENCE DATA" in context


class TestRateLimiting:
    """Tests for rate limiting."""
    
    def test_first_request_allowed(self, phoenix_ai):
        _user_cooldowns.clear()
        allowed, remaining = phoenix_ai.check_cooldown("user123")
        assert allowed is True
        assert remaining == 0
    
    def test_cooldown_blocks_second_request(self, phoenix_ai):
        _user_cooldowns.clear()
        phoenix_ai.check_cooldown("user123")
        allowed, remaining = phoenix_ai.check_cooldown("user123")
        assert allowed is False
        assert remaining > 0
    
    def test_cooldown_expires(self, phoenix_ai):
        _user_cooldowns.clear()
        _user_cooldowns["user456"] = time.time() - COOLDOWN_SECONDS - 1
        allowed, remaining = phoenix_ai.check_cooldown("user456")
        assert allowed is True
        assert remaining == 0
    
    def test_different_users_independent(self, phoenix_ai):
        _user_cooldowns.clear()
        phoenix_ai.check_cooldown("user1")
        allowed, _ = phoenix_ai.check_cooldown("user2")
        assert allowed is True


class TestAvailability:
    """Tests for availability checking."""
    
    def test_is_available_with_key_and_db(self, phoenix_ai):
        assert phoenix_ai.is_available() is True
    
    def test_not_available_without_key(self, temp_rag_db):
        # Create AI with explicit None and no fallback to Config
        ai = PhoenixAI(api_key=None, rag_db_path=temp_rag_db)
        # Override the fallback from Config
        ai.api_key = None
        assert ai.is_available() is False
    
    def test_not_available_without_db(self):
        ai = PhoenixAI(api_key="test_key", rag_db_path=Path("/nonexistent/path.db"))
        assert ai.is_available() is False


class TestSingleton:
    """Tests for singleton get_phoenix_ai."""
    
    def test_get_phoenix_ai_returns_instance(self):
        from bot.utils import phoenix_ai
        phoenix_ai._phoenix_ai = None
        ai = get_phoenix_ai()
        assert ai is not None
        assert isinstance(ai, PhoenixAI)
    
    def test_get_phoenix_ai_returns_same_instance(self):
        from bot.utils import phoenix_ai
        phoenix_ai._phoenix_ai = None
        ai1 = get_phoenix_ai()
        ai2 = get_phoenix_ai()
        assert ai1 is ai2
    
    @pytest.mark.asyncio
    async def test_cleanup_phoenix_ai(self):
        from bot.utils import phoenix_ai
        phoenix_ai._phoenix_ai = None
        _ = get_phoenix_ai()
        assert phoenix_ai._phoenix_ai is not None
        await cleanup_phoenix_ai()
        assert phoenix_ai._phoenix_ai is None
