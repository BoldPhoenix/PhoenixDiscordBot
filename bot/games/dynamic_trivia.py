"""
Dynamic ARK trivia question generator using game data and lore.
"""

import random
import re
import json
import sqlite3
from typing import Dict, List, Tuple, Any
from bot.database import games_db
from bot.utils.config import Config


class DynamicTriviaGenerator:
    """Generates dynamic ARK trivia questions from game data."""
    
    def __init__(self):
        self.cache = {
            'creatures': [],
            'items': [],
            'engrams': [],
            'maps': [],
            'stats': [],
            'taming': [],
            'breeding': [],
            'resources': []
        }
        self._load_data()
    
    def _load_data(self):
        """Load game data from database."""
        # Load creatures data from ark_ref_creatures table
        self.cache['creatures'] = self._load_creatures_from_db()
        # Load items data
        self.cache['items'] = self._load_items_from_db()
        # Load engrams data
        self.cache['engrams'] = self._load_engrams_from_db()
        # Static data
        self.cache['maps'] = self._load_maps()
        self.cache['stats'] = self._load_stats()
        self.cache['taming'] = self._load_taming_data()
        self.cache['breeding'] = self._load_breeding_data()
        self.cache['resources'] = self._load_resources()
    
    def _load_creatures_from_db(self) -> List[Dict[str, Any]]:
        """Load creature data from ark_ref_creatures table."""
        creatures = []
        try:
            db_path = getattr(Config, 'DATABASE_PATH', 'data/phoenix_bot.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT object_id, label, alternate_label, tags, stats, incubation_time, mature_time FROM ark_ref_creatures WHERE path IS NOT NULL AND path != '' AND (path LIKE '/Game/%' AND path NOT LIKE '/Game/Mods/%')"
            )
            rows = cursor.fetchall()
            for row in rows:
                obj_id = row['object_id']
                label = row['label']
                alt_label = row['alternate_label']
                tags = row['tags'] or ''
                stats_json = row['stats']
                try:
                    stats = json.loads(stats_json) if stats_json else []
                except:
                    stats = []
                creatures.append({
                    'object_id': obj_id,
                    'name': label,
                    'alternate_name': alt_label,
                    'tags': tags,
                    'stats': stats,
                    'incubation_time': row['incubation_time'],
                    'mature_time': row['mature_time']
                })
            conn.close()
        except Exception as e:
            print(f"Error loading creatures: {e}")
            creatures = self._get_fallback_creatures()
        return creatures
    
    def _load_items_from_db(self) -> List[Dict[str, Any]]:
        """Load item data from ark_ref_items table."""
        items = []
        try:
            db_path = getattr(Config, 'DATABASE_PATH', 'data/phoenix_bot.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT object_id, label, alternate_label, stack_size, required_level, required_points, tags, path FROM ark_ref_items WHERE (required_level > 0 OR stack_size > 0) AND path IS NOT NULL AND path != '' AND path LIKE '/Game/%' AND path NOT LIKE '/Game/Mods/%'"
            )
            rows = cursor.fetchall()
            for row in rows:
                items.append({
                    'object_id': row['object_id'],
                    'name': row['label'],
                    'alternate_name': row['alternate_label'],
                    'stack_size': row['stack_size'],
                    'required_level': row['required_level'],
                    'required_points': row['required_points'],
                    'tags': row['tags'] or '',
                    'path': row['path'] or ''
                })
            conn.close()
        except Exception as e:
            print(f"Error loading items: {e}")
            items = self._get_fallback_items()
        return items
    
    def _load_engrams_from_db(self) -> List[Dict[str, Any]]:
        """Load engram data from ark_ref_engrams table."""
        engrams = []
        try:
            db_path = getattr(Config, 'DATABASE_PATH', 'data/phoenix_bot.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT object_id, label, alternate_label, required_level, required_points, stack_size, recipe FROM ark_ref_engrams WHERE (required_level > 0 OR required_points > 0) AND path IS NOT NULL AND path != '' AND path LIKE '/Game/%' AND path NOT LIKE '/Game/Mods/%'"
            )
            rows = cursor.fetchall()
            for row in rows:
                engrams.append({
                    'object_id': row['object_id'],
                    'name': row['label'],
                    'alternate_name': row['alternate_label'],
                    'required_level': row['required_level'],
                    'required_points': row['required_points'],
                    'stack_size': row['stack_size'],
                    'recipe': row['recipe'] or ''
                })
            conn.close()
        except Exception as e:
            print(f"Error loading engrams: {e}")
            engrams = self._get_fallback_engrams()
        return engrams
    
    def _get_fallback_creatures(self) -> List[Dict[str, Any]]:
        """Fallback creatures if database load fails."""
        return [
            {'name': 'Rex', 'type': 'predator', 'diet': 'carnivore', 'size': 'large', 
             'torpor': 'high', 'speed': 'medium', 'health': 'high', 'damage': 'high'},
            {'name': 'Argentavis', 'type': 'bird', 'diet': 'carnivore', 'size': 'large', 
             'torpor': 'medium', 'speed': 'fast', 'health': 'medium', 'damage': 'medium'},
            {'name': 'Brontosaurus', 'type': 'herbivore', 'diet': 'herbivore', 'size': 'huge', 
             'torpor': 'very_high', 'speed': 'slow', 'health': 'very_high', 'damage': 'medium'},
            {'name': 'Quetzal', 'type': 'bird', 'diet': 'carnivore', 'size': 'large', 
             'torpor': 'high', 'speed': 'fast', 'health': 'medium', 'damage': 'low'},
            {'name': 'Titanosaur', 'type': 'herbivore', 'diet': 'herbivore', 'size': 'massive', 
             'torpor': 'extreme', 'speed': 'very_slow', 'health': 'extreme', 'damage': 'high'},
            {'name': 'Dodo', 'type': 'bird', 'diet': 'herbivore', 'size': 'small', 
             'torpor': 'low', 'speed': 'slow', 'health': 'low', 'damage': 'very_low'},
            {'name': 'Parasaur', 'type': 'herbivore', 'diet': 'herbivore', 'size': 'medium', 
             'torpor': 'medium', 'speed': 'medium', 'health': 'medium', 'damage': 'very_low'},
            {'name': 'Raptor', 'type': 'predator', 'diet': 'carnivore', 'size': 'small', 
             'torpor': 'low', 'speed': 'fast', 'health': 'medium', 'damage': 'medium'},
            {'name': 'Spino', 'type': 'predator', 'diet': 'carnivore', 'size': 'large', 
             'torpor': 'high', 'speed': 'medium', 'health': 'high', 'damage': 'high'},
            {'name': 'Triceratops', 'type': 'herbivore', 'diet': 'herbivore', 'size': 'large', 
             'torpor': 'high', 'speed': 'slow', 'health': 'high', 'damage': 'medium'}
        ]
    
    def _get_fallback_items(self) -> List[Dict[str, Any]]:
        """Fallback items if database load fails."""
        return [
            {'name': 'Stone Hatchet', 'type': 'tool', 'tier': 'primitive', 'damage': 'low', 'uses': 'wood,thatch'},
            {'name': 'Metal Pick', 'type': 'tool', 'tier': 'metal', 'damage': 'medium', 'uses': 'stone,metal,obsidian'},
            {'name': 'Crossbow', 'type': 'weapon', 'tier': 'primitive', 'damage': 'medium', 'ammo': 'arrow'},
            {'name': 'Longneck Rifle', 'type': 'weapon', 'tier': 'simple', 'damage': 'high', 'ammo': 'bullet'},
            {'name': 'Rocket Launcher', 'type': 'weapon', 'tier': 'advanced', 'damage': 'extreme', 'ammo': 'rocket'},
            {'name': 'Pike', 'type': 'weapon', 'tier': 'primitive', 'damage': 'medium', 'range': 'melee'},
            {'name': 'Sword', 'type': 'weapon', 'tier': 'simple', 'damage': 'high', 'range': 'melee'},
            {'name': 'Rocket Propelled Grenade', 'type': 'weapon', 'tier': 'advanced', 'damage': 'extreme', 'range': 'explosive'},
            {'name': 'Compound Bow', 'type': 'weapon', 'tier': 'simple', 'damage': 'high', 'ammo': 'arrow'},
            {'name': 'Fabricated Pistol', 'type': 'weapon', 'tier': 'advanced', 'damage': 'medium', 'ammo': 'bullet'}
        ]
    
    def _get_fallback_engrams(self) -> List[Dict[str, Any]]:
        """Fallback engrams if database load fails."""
        return [
            {'name': 'Mastercraft Metal Bullet', 'level': 62, 'points': 18},
            {'name': 'Simple Pistol', 'level': 5, 'points': 0},
            {'name': 'Longneck Rifle', 'level': 35, 'points': 11},
            {'name': 'Rocket Launcher', 'level': 65, 'points': 20},
            {'name': 'Fabricated Sniper', 'level': 78, 'points': 24}
        ]
    def _load_engrams(self) -> List[Dict[str, Any]]:
        """Load engram data."""
        return [
            {'name': 'Stone Hatchet', 'tier': 'primitive', 'level': 1, 'engram_points': 0, 'category': 'tools'},
            {'name': 'Spear', 'tier': 'primitive', 'level': 1, 'engram_points': 0, 'category': 'weapons'},
            {'name': 'Campfire', 'tier': 'primitive', 'level': 2, 'engram_points': 3, 'category': 'structures'},
            {'name': 'Pike', 'tier': 'primitive', 'level': 8, 'engram_points': 4, 'category': 'weapons'},
            {'name': 'Simple Bullet', 'tier': 'simple', 'level': 5, 'engram_points': 5, 'category': 'ammo'},
            {'name': 'Simple Rifle Ammo', 'tier': 'simple', 'level': 9, 'engram_points': 10, 'category': 'ammo'},
            {'name': 'Simple Pistol', 'tier': 'simple', 'level': 5, 'engram_points': 10, 'category': 'weapons'},
            {'name': 'Simple Shotgun Ammo', 'tier': 'simple', 'level': 10, 'engram_points': 15, 'category': 'ammo'},
            {'name': 'Simple Shotgun', 'tier': 'simple', 'level': 10, 'engram_points': 15, 'category': 'weapons'},
            {'name': 'Metal Hatchet', 'tier': 'metal', 'level': 20, 'engram_points': 10, 'category': 'tools'}
        ]
    
    def _load_maps(self) -> List[Dict[str, Any]]:
        """Load map data."""
        return [
            {'name': 'The Island', 'biome': 'island', 'difficulty': 'normal', 'creatures': ['Rex', 'Argentavis', 'Brontosaurus']},
            {'name': 'Scorched Earth', 'biome': 'desert', 'difficulty': 'hard', 'creatures': ['Morellatops', 'Deathworm', 'Phoenix']},
            {'name': 'Aberration', 'biome': 'underground', 'difficulty': 'hard', 'creatures': ['Rock Drake', 'Basilisk', 'Reaper']},
            {'name': 'Extinction', 'biome': 'post-apocalyptic', 'difficulty': 'extreme', 'creatures': ['Managarmr', 'Velonasaur', 'Gacha']},
            {'name': 'Genesis Part 1', 'biome': 'simulation', 'difficulty': 'hard', 'creatures': ['Ferox', 'Bloodstalker', 'Megachelon']},
            {'name': 'Genesis Part 2', 'biome': 'space', 'difficulty': 'extreme', 'creatures': ['Astrodelphis', 'Shadowmane', 'Noglin']},
            {'name': 'Valguero', 'biome': 'mixed', 'difficulty': 'normal', 'creatures': ['Deinonychus', 'Ice Wyvern', 'Chalk Golem']},
            {'name': 'Crystal Isles', 'biome': 'crystal', 'difficulty': 'normal', 'creatures': ['Crystal Wyvern', 'Featherlight', 'Seeker']},
            {'name': 'Lost Island', 'biome': 'jungle', 'difficulty': 'hard', 'creatures': ['Amargasaurus', 'Dinopithecus', 'Sinomacrops']},
            {'name': 'Fjordur', 'biome': 'nordic', 'difficulty': 'hard', 'creatures': ['Andrewsarchus', 'Desmodus', 'Fenrir']}
        ]
    
    def _load_stats(self) -> List[Dict[str, Any]]:
        """Load game stats data."""
        return [
            {'stat': 'Health', 'abbreviation': 'HP', 'max_level': 150, 'wild_increase': 10, 'tamed_increase': 5.4},
            {'stat': 'Stamina', 'abbreviation': 'STA', 'max_level': 150, 'wild_increase': 10, 'tamed_increase': 5.4},
            {'stat': 'Oxygen', 'abbreviation': 'OX', 'max_level': 150, 'wild_increase': 10, 'tamed_increase': 5.4},
            {'stat': 'Food', 'abbreviation': 'FOO', 'max_level': 150, 'wild_increase': 10, 'tamed_increase': 5.4},
            {'stat': 'Weight', 'abbreviation': 'WGT', 'max_level': 150, 'wild_increase': 10, 'tamed_increase': 5.4},
            {'stat': 'Melee Damage', 'abbreviation': 'MD', 'max_level': 150, 'wild_increase': 5, 'tamed_increase': 2.7},
            {'stat': 'Movement Speed', 'abbreviation': 'MS', 'max_level': 150, 'wild_increase': 2, 'tamed_increase': 1.8},
            {'stat': 'Torpor', 'abbreviation': 'TOR', 'max_level': 150, 'wild_increase': 7, 'tamed_increase': 0}
        ]
    
    def _load_taming_data(self) -> List[Dict[str, Any]]:
        """Load taming data."""
        return [
            {'creature': 'Rex', 'preferred_kibble': 'Exceptional', 'food_rate': 'slow', 'torpor_method': 'tranq'},
            {'creature': 'Argentavis', 'preferred_kibble': 'Superior', 'food_rate': 'medium', 'torpor_method': 'tranq'},
            {'creature': 'Brontosaurus', 'preferred_kibble': 'Exceptional', 'food_rate': 'very_slow', 'torpor_method': 'tranq'},
            {'creature': 'Quetzal', 'preferred_kibble': 'Exceptional', 'food_rate': 'slow', 'torpor_method': 'tranq'},
            {'creature': 'Dodo', 'preferred_kibble': 'Basic', 'food_rate': 'fast', 'torpor_method': 'hand'},
            {'creature': 'Parasaur', 'preferred_kibble': 'Basic', 'food_rate': 'medium', 'torpor_method': 'tranq'},
            {'creature': 'Raptor', 'preferred_kibble': 'Simple', 'food_rate': 'medium', 'torpor_method': 'tranq'},
            {'creature': 'Spino', 'preferred_kibble': 'Exceptional', 'food_rate': 'slow', 'torpor_method': 'tranq'},
            {'creature': 'Triceratops', 'preferred_kibble': 'Simple', 'food_rate': 'slow', 'torpor_method': 'tranq'},
            {'creature': 'Titanosaur', 'preferred_kibble': 'None', 'food_rate': 'none', 'torpor_method': 'cannon'}
        ]
    
    def _load_breeding_data(self) -> List[Dict[str, Any]]:
        """Load breeding data."""
        return [
            {'creature': 'Rex', 'gestation': '3d12h', 'baby_stage': '4d', 'maturation': '7d', 'breeding_interval': '18h-48h'},
            {'creature': 'Argentavis', 'gestation': '3d12h', 'baby_stage': '4d', 'maturation': '7d', 'breeding_interval': '18h-48h'},
            {'creature': 'Brontosaurus', 'gestation': '3d12h', 'baby_stage': '4d', 'maturation': '7d', 'breeding_interval': '18h-48h'},
            {'creature': 'Quetzal', 'gestation': '3d12h', 'baby_stage': '4d', 'maturation': '7d', 'breeding_interval': '18h-48h'},
            {'creature': 'Dodo', 'gestation': '3d12h', 'baby_stage': '4d', 'maturation': '7d', 'breeding_interval': '18h-48h'},
            {'creature': 'Parasaur', 'gestation': '3d12h', 'baby_stage': '4d', 'maturation': '7d', 'breeding_interval': '18h-48h'},
            {'creature': 'Raptor', 'gestation': '3d12h', 'baby_stage': '4d', 'maturation': '7d', 'breeding_interval': '18h-48h'},
            {'creature': 'Spino', 'gestation': '3d12h', 'baby_stage': '4d', 'maturation': '7d', 'breeding_interval': '18h-48h'},
            {'creature': 'Triceratops', 'gestation': '3d12h', 'baby_stage': '4d', 'maturation': '7d', 'breeding_interval': '18h-48h'}
        ]
    
    def _load_resources(self) -> List[Dict[str, Any]]:
        """Load resource data."""
        return [
            {'name': 'Stone', 'type': 'basic'},
            {'name': 'Wood', 'type': 'basic'},
            {'name': 'Thatch', 'type': 'basic'},
            {'name': 'Flint', 'type': 'basic'},
            {'name': 'Fiber', 'type': 'basic'},
            {'name': 'Berries', 'type': 'food'},
            {'name': 'Meat', 'type': 'food'},
            {'name': 'Hide', 'type': 'resource'},
            {'name': 'Chitin', 'type': 'resource'},
            {'name': 'Keratin', 'type': 'resource'},
            {'name': 'Obsidian', 'type': 'resource'},
            {'name': 'Crystal', 'type': 'resource'},
            {'name': 'Metal', 'type': 'resource'},
            {'name': 'Oil', 'type': 'resource'},
            {'name': 'Pearl', 'type': 'resource'},
            {'name': 'Sand', 'type': 'basic'}
        ]
    
    def generate_question(self) -> Dict[str, Any]:
        """Generate a random trivia question."""
        question_type = random.choice([
            'creature_facts',
            'item_facts',
            'engram_facts',
            'map_facts',
            'stat_facts',
            'taming_facts',
            'breeding_facts',
            'resource_facts'
        ])
        
        if question_type == 'creature_facts':
            return self._generate_creature_question()
        elif question_type == 'item_facts':
            return self._generate_item_question()
        elif question_type == 'engram_facts':
            return self._generate_engram_question()
        elif question_type == 'map_facts':
            return self._generate_map_question()
        elif question_type == 'stat_facts':
            return self._generate_stat_question()
        elif question_type == 'taming_facts':
            return self._generate_taming_question()
        elif question_type == 'breeding_facts':
            return self._generate_breeding_question()
        elif question_type == 'resource_facts':
            return self._generate_resource_question()
    
    def _generate_creature_question(self) -> Dict[str, Any]:
        """Generate a creature trivia question using database data."""
        creature = random.choice(self.cache['creatures'])
        
        question_type = random.choice([
            'name_from_tags',
            'incubation_time',
            'mature_time',
            'tags_identify'
        ])
        
        if question_type == 'name_from_tags':
            # Given tags, identify the creature
            creature_tags = creature.get('tags', '').split(',') if creature.get('tags') else []
            if not creature_tags or creature_tags == ['']:
                # Fallback to simple question
                question_type = 'incubation_time'
        
        if question_type == 'name_from_tags':
            # Multiple choice: given tags, pick the creature
            options = random.sample([c['name'] for c in self.cache['creatures'] if c.get('tags')], 3)
            if creature['name'] not in options:
                options.append(creature['name'])
            random.shuffle(options)
            question = f"Which creature has the tag '{creature.get('tags', '').split(',')[0]}'?"
            return {
                'q': question,
                'options': options,
                'answer': options.index(creature['name']),
                'category': 'creature'
            }
        
        elif question_type == 'incubation_time':
            # Question about incubation time
            inc_time = creature.get('incubation_time')
            if inc_time and inc_time > 0:
                options = [f"{inc_time:.1f} hours", f"{inc_time * 2:.1f} hours", f"{inc_time * 0.5:.1f} hours", f"{inc_time * 1.5:.1f} hours"]
                options = list(set(options))[:4]
                while len(options) < 4:
                    options.append(f"{random.randint(1, 50)} hours")
                correct = f"{inc_time:.1f} hours"
                if correct not in options:
                    options[0] = correct
                random.shuffle(options)
                return {
                    'q': f"What is the incubation time for {creature['name']}?",
                    'options': options,
                    'answer': options.index(correct),
                    'category': 'creature'
                }
        
        elif question_type == 'mature_time':
            # Question about mature time
            mature_time = creature.get('mature_time')
            if mature_time and mature_time > 0:
                options = [f"{mature_time:.1f} hours", f"{mature_time * 2:.1f} hours", f"{mature_time * 0.5:.1f} hours", f"{mature_time * 1.5:.1f} hours"]
                options = list(set(options))[:4]
                while len(options) < 4:
                    options.append(f"{random.randint(1, 200)} hours")
                correct = f"{mature_time:.1f} hours"
                if correct not in options:
                    options[0] = correct
                random.shuffle(options)
                return {
                    'q': f"How long does it take for {creature['name']} to mature?",
                    'options': options,
                    'answer': options.index(correct),
                    'category': 'creature'
                }
        
        # Fallback: creature identification - only use creatures with valid alternate names
        valid_creatures = [c for c in self.cache['creatures'] if c.get('alternate_name') and c['alternate_name'] != 'None']
        if not valid_creatures:
            valid_creatures = self.cache['creatures'][:min(50, len(self.cache['creatures']))]
        
        if len(valid_creatures) < 4:
            # Not enough creatures for meaningful question, skip to stat question
            return self._generate_stat_question()
        
        creature = random.choice(valid_creatures)
        sample_size = min(3, len(valid_creatures))
        options = random.sample([c['name'] for c in valid_creatures], sample_size)
        if creature['name'] not in options:
            options.append(creature['name'])
        random.shuffle(options)
        return {
            'q': f"Which creature is also known as '{creature.get('alternate_name', creature['name'])}'?",
            'options': options,
            'answer': options.index(creature['name']),
            'category': 'creature'
        }
    
    def _generate_item_question(self) -> Dict[str, Any]:
        """Generate an item trivia question using database data."""
        item = random.choice(self.cache['items'])
        
        question_type = random.choice([
            'required_level',
            'stack_size',
            'name_identify'
        ])
        
        if question_type == 'required_level':
            req_level = item.get('required_level', 0)
            if req_level and req_level > 0:
                options = [f"Level {req_level}", f"Level {req_level + 5}", f"Level {req_level - 5}", f"Level {req_level + 10}"]
                options = list(set(options))[:4]
                while len(options) < 4:
                    options.append(f"Level {random.randint(1, 100)}")
                correct = f"Level {req_level}"
                if correct not in options:
                    options[0] = correct
                random.shuffle(options)
                return {
                    'q': f"What level is required to use {item['name']}?",
                    'options': options,
                    'answer': options.index(correct),
                    'category': 'item'
                }
        
        elif question_type == 'stack_size':
            stack_size = item.get('stack_size')
            if stack_size and stack_size > 0:
                options = [str(stack_size), str(stack_size * 2), str(stack_size // 2), str(stack_size + 10)]
                options = list(set(options))[:4]
                while len(options) < 4:
                    options.append(str(random.randint(1, 100)))
                correct = str(stack_size)
                if correct not in options:
                    options[0] = correct
                random.shuffle(options)
                return {
                    'q': f"What is the stack size for {item['name']}?",
                    'options': options,
                    'answer': options.index(correct),
                    'category': 'item'
                }
        
        # Fallback: item identification - only use items with valid required_level
        valid_items = [i for i in self.cache['items'] if i.get('required_level') and i['required_level'] > 0]
        if not valid_items:
            valid_items = self.cache['items'][:min(50, len(self.cache['items']))]
        
        if len(valid_items) < 4:
            return self._generate_stat_question()
        
        item = random.choice(valid_items)
        options = random.sample([i['name'] for i in valid_items], min(3, len(valid_items)))
        if item['name'] not in options:
            options.append(item['name'])
        random.shuffle(options)
        return {
            'q': f"Which item requires Level {item.get('required_level', 0)}?",
            'options': options,
            'answer': options.index(item['name']),
            'category': 'item'
        }
    
    def _generate_engram_question(self) -> Dict[str, Any]:
        """Generate an engram trivia question using database data."""
        engram = random.choice(self.cache['engrams'])
        
        question_type = random.choice([
            'required_level',
            'required_points',
            'name_identify'
        ])
        
        if question_type == 'required_level':
            req_level = engram.get('required_level', 0)
            if req_level and req_level > 0:
                options = [f"Level {req_level}", f"Level {req_level + 5}", f"Level {req_level - 5}", f"Level {req_level + 10}"]
                options = list(set(options))[:4]
                while len(options) < 4:
                    options.append(f"Level {random.randint(1, 100)}")
                correct = f"Level {req_level}"
                if correct not in options:
                    options[0] = correct
                random.shuffle(options)
                return {
                    'q': f"At what level do you learn {engram['name']}?",
                    'options': options,
                    'answer': options.index(correct),
                    'category': 'engram'
                }
        
        elif question_type == 'required_points':
            req_points = engram.get('required_points', 0)
            if req_points is not None:
                options = [str(req_points), str(req_points + 5), str(max(0, req_points - 5)), str(req_points + 10)]
                options = list(set(options))[:4]
                while len(options) < 4:
                    options.append(str(random.randint(0, 30)))
                correct = str(req_points)
                if correct not in options:
                    options[0] = correct
                random.shuffle(options)
                return {
                    'q': f"How many engram points does {engram['name']} cost?",
                    'options': options,
                    'answer': options.index(correct),
                    'category': 'engram'
                }
        
        # Fallback: engram identification
        options = random.sample([e['name'] for e in self.cache['engrams']], 3)
        if engram['name'] not in options:
            options.append(engram['name'])
        random.shuffle(options)
        return {
            'q': f"Which engram costs {engram.get('required_points', 0)} points?",
            'options': options,
            'answer': options.index(engram['name']),
            'category': 'engram'
        }
        
        return {
            'q': question,
            'options': options,
            'answer': answer,
            'category': 'engram'
        }
    
    def _generate_map_question(self) -> Dict[str, Any]:
        """Generate a map trivia question."""
        map_data = random.choice(self.cache['maps'])
        
        question_type = random.choice([
            'biome',
            'difficulty',
            'creatures'
        ])
        
        if question_type == 'biome':
            question = f"What biome is {map_data['name']}?"
            options = ['island', 'desert', 'underground', 'post-apocalyptic', 'simulation', 'space', 'mixed', 'crystal', 'jungle', 'nordic']
            answer = ['island', 'desert', 'underground', 'post-apocalyptic', 'simulation', 'space', 'mixed', 'crystal', 'jungle', 'nordic'].index(map_data['biome'])
        elif question_type == 'difficulty':
            question = f"What difficulty is {map_data['name']}?"
            options = ['easy', 'normal', 'hard', 'extreme']
            answer = ['easy', 'normal', 'hard', 'extreme'].index(map_data['difficulty'])
        elif question_type == 'creatures':
            question = f"Which creature is found on {map_data['name']}?"
            creatures = map_data['creatures']
            correct_creature = random.choice(creatures)
            # Generate distractors
            all_creatures = [c['name'] for c in self.cache['creatures']]
            distractors = random.sample([c for c in all_creatures if c not in creatures], 3)
            options = [correct_creature] + distractors
            random.shuffle(options)
            answer = options.index(correct_creature)
            return {
                'q': question,
                'options': options,
                'answer': answer,
                'category': 'map'
            }
        
        return {
            'q': question,
            'options': options,
            'answer': answer,
            'category': 'map'
        }
    
    def _generate_stat_question(self) -> Dict[str, Any]:
        """Generate a stat trivia question."""
        stat = random.choice(self.cache['stats'])
        
        question_type = random.choice([
            'max_level',
            'wild_increase',
            'tamed_increase'
        ])
        
        if question_type == 'max_level':
            question = f"What is the max level for {stat['stat']} stat?"
            options = ['100', '120', '150', '180']
            answer = ['100', '120', '150', '180'].index(str(stat['max_level']))
        elif question_type == 'wild_increase':
            question = f"How much does {stat['stat']} increase per wild level?"
            options = ['5', '7', '10']
            answer = ['5', '7', '10'].index(str(stat['wild_increase']))
        elif question_type == 'tamed_increase':
            question = f"How much does {stat['stat']} increase per tamed level?"
            options = ['2.7', '5.4', '7.2']
            answer = ['2.7', '5.4', '7.2'].index(str(stat['tamed_increase']))
        
        return {
            'q': question,
            'options': options,
            'answer': answer,
            'category': 'stat'
        }
    
    def _generate_taming_question(self) -> Dict[str, Any]:
        """Generate a taming trivia question."""
        taming = random.choice(self.cache['taming'])
        
        question_type = random.choice([
            'preferred_kibble',
            'food_rate',
            'torpor_method'
        ])
        
        if question_type == 'preferred_kibble':
            question = f"What kibble does a {taming['creature']} prefer?"
            options = ['Basic', 'Simple', 'Regular', 'Superior', 'Exceptional', 'Extraordinary']
            kibble = taming['preferred_kibble']
            if kibble == 'None':
                kibble = 'Regular'  # Default to Regular if None
            answer = ['Basic', 'Simple', 'Regular', 'Superior', 'Exceptional', 'Extraordinary'].index(kibble)
        elif question_type == 'food_rate':
            question = f"How fast does a {taming['creature']} eat?"
            options = ['very_fast', 'fast', 'medium', 'slow', 'very_slow', 'none']
            answer = ['very_fast', 'fast', 'medium', 'slow', 'very_slow', 'none'].index(taming['food_rate'])
        elif question_type == 'torpor_method':
            question = f"How do you knock out a {taming['creature']}?"
            # Special handling for creatures requiring heavy weapons
            if taming['creature'] == 'Titanosaur':
                options = ['Cannon', 'Rockets', 'Mek Siege Cannon', 'Catapult Turret', 'Ballista Turret']
                answer = 0  # Cannon is most efficient
            else:
                options = ['Tranquilizer', 'Hand', 'Club', 'Slingshot', 'Passive']
                answer = ['tranq', 'hand', 'club', 'slingshot', 'passive'].index(taming['torpor_method'])
        
        return {
            'q': question,
            'options': options,
            'answer': answer,
            'category': 'taming'
        }
    
    def _generate_breeding_question(self) -> Dict[str, Any]:
        """Generate a breeding trivia question."""
        breeding = random.choice(self.cache['breeding'])
        
        question_type = random.choice([
            'gestation',
            'baby_stage',
            'maturation',
            'breeding_interval'
        ])
        
        if question_type == 'gestation':
            question = f"How long is gestation for a {breeding['creature']}?"
            options = ['1d', '2d', '3d12h', '4d']
            answer = ['1d', '2d', '3d12h', '4d'].index(breeding['gestation'])
        elif question_type == 'baby_stage':
            question = f"How long is baby stage for a {breeding['creature']}?"
            options = ['2d', '3d', '4d', '5d']
            answer = ['2d', '3d', '4d', '5d'].index(breeding['baby_stage'])
        elif question_type == 'maturation':
            question = f"How long until maturation for a {breeding['creature']}?"
            options = ['5d', '6d', '7d', '8d']
            answer = ['5d', '6d', '7d', '8d'].index(breeding['maturation'])
        elif question_type == 'breeding_interval':
            question = f"What is the breeding interval for a {breeding['creature']}?"
            options = ['12h-24h', '18h-48h', '24h-72h', '48h-96h']
            answer = ['12h-24h', '18h-48h', '24h-72h', '48h-96h'].index(breeding['breeding_interval'])
        
        return {
            'q': question,
            'options': options,
            'answer': answer,
            'category': 'breeding'
        }
    
    def _generate_resource_question(self) -> Dict[str, Any]:
        """Generate a resource trivia question."""
        resource = random.choice(self.cache['resources'])
        
        question = f"What type of resource is {resource['name']}?"
        options = ['basic', 'food', 'resource', 'crafting']
        answer = 0
        if resource.get('type') in options:
            answer = options.index(resource['type'])
        
        return {
            'q': question,
            'options': options,
            'answer': answer,
            'category': 'resource'
        }
    
    def get_question_count(self) -> int:
        """Get total number of possible questions."""
        return (
            len(self.cache['creatures']) * 5 +  # 5 question types per creature
            len(self.cache['items']) * 4 +      # 4 question types per item
            len(self.cache['engrams']) * 3 +    # 3 question types per engram
            len(self.cache['maps']) * 3 +      # 3 question types per map
            len(self.cache['stats']) * 3 +     # 3 question types per stat
            len(self.cache['taming']) * 3 +    # 3 question types per taming
            len(self.cache['breeding']) * 4 +  # 4 question types per breeding
            len(self.cache['resources']) * 3   # 3 question types per resource
        )


# Global instance
TRIVIA_GENERATOR = DynamicTriviaGenerator()


def get_dynamic_question() -> Dict[str, Any]:
    """Get a random dynamic trivia question."""
    return TRIVIA_GENERATOR.generate_question()


def get_question_count() -> int:
    """Get total number of possible questions."""
    return TRIVIA_GENERATOR.get_question_count()