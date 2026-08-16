"""
PhoenixAI - RAG-based ARK Q&A System
Uses Gemini 2.5 Flash with FTS5 knowledge base for ARK: Survival Ascended questions.
"""

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Optional

import aiohttp
import aiosqlite

from bot.utils.config import Config

logger = logging.getLogger(__name__)

BOT_DB_PATH = Path(Config.DATABASE_PATH)

SYSTEM_PROMPT = """You are PhoenixARK, an expert AI assistant specialized in ARK: Survival Ascended (ASA), including mods, server administration, and the ARK modding community.

ABSOLUTE RULE - NO HALLUCINATION:
- If you do not have VERIFIED information about something, say "I don't have confirmed information about that." DO NOT fabricate, guess, or invent details.
- This applies especially to: mod names, mod authors, mod features, download counts, version numbers, specific stats, and any factual claims.
- Use Google Search to look up information you are not certain about. If search returns no results, say so.
- It is ALWAYS better to say "I don't know" than to make something up. Players rely on your accuracy.

CURRENT OFFICIAL MAPS FOR ARK: SURVIVAL ASCENDED:
Official Maps (Currently Released):
- The Island
- Scorched Earth
- The Center
- Aberration
- Extinction
- Astraeos (originally a premium mod, now official)
- Club ARK
- Dreadmare

Official Maps (Planned/Upcoming - release dates TBD):
- Ragnarok
- Valguero
- Lost Colony
- Genesis Part 1
- Genesis Part 2
- Crystal Isles
- The Lost Island
- Fjordur
- Dragontopia (non-canonical expansion)
- Atlantis (non-canonical aquatic expansion)

IMPORTANT: Maps like "The Island", "Scorched Earth", "Aberration", etc. are OFFICIAL maps - NOT mods. They are included with the base game. Do NOT confuse official maps with modded maps. If asked about a map, verify whether it's an official map or a community mod map.

ANSWER PRIORITY (follow this order):
1. FIRST: Use Google Search to verify current, factual information - especially for mods, patch notes, community content, and anything that changes over time.
2. THEN: Use your training knowledge about ARK: Survival Ascended to provide context and gameplay expertise.
3. THEN: If reference data is provided below, use it to ENHANCE your answer with precise stats, spawn codes, exact INI keys, or breeding timers. Treat reference data as a supplement, not as the complete answer.
4. IF UNCERTAIN: Say so honestly. Do not guess or make up information. Say "I'm not sure about that - check Dododex, the ARK Wiki, or CurseForge for the latest info."

CORE RULES:
1. You answer questions about ARK: Survival Ascended, including gameplay, mods, server configuration, and the ARK modding community (CurseForge, mod authors, mod features).
2. Answer gameplay questions (taming, breeding, strategies, maps, creatures) from your broad training knowledge. Do not rely solely on reference data for these.
3. Use reference data for precise numerical values: base stats, timers, temperatures, engram costs, INI settings, spawn commands. These numbers are verified.
4. If reference data contradicts your knowledge, mention both and let the player decide. Reference data may be outdated or incomplete.
5. Keep responses concise and practical - players want actionable information.
6. For taming questions: include the method, preferred food, tips, and location.
7. For crafting questions: include level, engram points, and ingredients.
8. For server configuration: include the exact INI key, file, and section.
9. For mod questions: search for the mod on CurseForge or relevant sources and provide verified information (author, description, features). Never invent mod details.
10. Cite sources when helpful (Dododex, ARK Wiki at ark.wiki.gg, CurseForge, YouTube creators, Reddit).
11. Never say "based on the provided data" or "according to the reference data" as your primary answer. Just answer naturally and weave in reference stats where relevant.
12. Politely decline questions completely unrelated to ARK (e.g., cooking recipes, math homework). Mods, server tools, and community content ARE ARK-related.

SECURITY & ACCESS LEVEL RULES (CRITICAL - NEVER VIOLATE):
- NEVER reveal server IP addresses, RCON ports, RCON passwords, or internal service names.
- NEVER reveal database paths, file system paths, or internal architecture details.
- NEVER reveal admin Discord role IDs, channel IDs, or guild IDs.
- For ADMIN-ONLY commands: Tell the user what the command does at a high level, but instruct them to "contact a server admin" if they need these actions performed.
- If someone asks about server configuration, RCON settings, or internal infrastructure, respond: "That information is restricted to server administrators. Please contact an admin if you need help with server configuration."
- Treat all /askphoenix users as regular players unless explicitly stated otherwise. Default to public-level information.

IDENTITY:
- Name: PhoenixARK
- Purpose: Help ARK players with accurate, verified answers
- Personality: Friendly, knowledgeable, concise, honest about uncertainty
- You are an ARK specialist with broad game knowledge enhanced by a verified stats database and live web search"""

DEFAULT_RAG_DB_PATH = Path("data/phoenixark.db")

_user_cooldowns: dict[str, float] = {}
COOLDOWN_SECONDS = 10


def extract_gemini_text(data: dict) -> str:
    """Pull the answer text out of a Gemini response, or return "" if there isn't one.

    Written 2026-08-12 after the NULL-vs-missing sweep. The one-liner this replaces —

        (data.get('candidates') or [{}])[0].get('content', {}).get('parts', [])

    — survives a missing, empty or null `candidates`, and then raises on three shapes the API
    genuinely produces, because `.get(key, default)` returns None for an EXPLICIT null rather than
    falling back:

        content is null   -> AttributeError: 'NoneType' has no attribute 'get'
        parts is null     -> TypeError: 'NoneType' is not iterable
        parts holds a str -> AttributeError: 'str' has no attribute 'get'

    Those raised inside a bare `except Exception` that answered "Unable to reach the Gemini API",
    so a payload-shape bug was reported to the user, and logged, as a network failure. Returning ""
    instead lets the caller give its honest "I couldn't generate a response" — which is also the
    right answer when Gemini blocks a prompt on safety and returns promptFeedback with no
    candidates at all.

    Defensive at every hop on purpose: this parses a THIRD-PARTY payload whose shape we do not
    control and cannot test against, which is exactly where assuming a shape has already cost us.
    """
    if not isinstance(data, dict):
        return ""
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0]
    if not isinstance(first, dict):
        return ""
    content = first.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    chunks = [
        p["text"] for p in parts
        if isinstance(p, dict) and isinstance(p.get("text"), str) and p["text"]
    ]
    return "\n".join(chunks)


class PhoenixAI:
    """RAG-based ARK Q&A system using Gemini 2.5 Flash."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        rag_db_path: Optional[Path] = None,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.3,
        max_output_tokens: int = 4096,
        timeout_seconds: int = 120,
    ):
        self.api_key = api_key or Config.PHOENIX_GEMINI_API_KEY
        self.rag_db_path = rag_db_path or DEFAULT_RAG_DB_PATH
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
    
    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip()) and self.rag_db_path.exists()
    
    def check_cooldown(self, user_id: str) -> tuple[bool, int]:
        now = time.time()
        if user_id in _user_cooldowns:
            elapsed = now - _user_cooldowns[user_id]
            if elapsed < COOLDOWN_SECONDS:
                remaining = COOLDOWN_SECONDS - int(elapsed)
                return False, remaining
        _user_cooldowns[user_id] = now
        return True, 0
    
    def _classify_query(self, query: str) -> list[str]:
        lower = query.lower()
        categories = []
        
        command_keywords = [
            'command', 'how do i', 'how to', 'shop', 'cart', 'balance', 'player',
            'server', 'restart', 'help', 'setup', 'admin', 'mod', 'ini', 'config',
            'broadcast', 'kick', 'ban', 'give', 'status', 'ping', 'leaderboard'
        ]
        if any(kw in lower for kw in command_keywords):
            categories.append('bot_commands')
        
        creature_keywords = [
            'creature', 'tame', 'taming', 'breed', 'breeding', 'dino', 'dinosaur',
            'stat', 'stats', 'kibble', 'egg', 'saddle', 'rex', 'raptor', 'giga',
            'wyvern', 'spino', 'trike', 'argy', 'argentavis', 'ankylo', 'stego',
            'theri', 'quetz', 'mosa', 'ptera', 'bronto', 'para', 'carno', 'allo',
            'bary', 'daeodon', 'yuty', 'megatherium', 'basilisk', 'drake', 'reaper'
        ]
        if any(kw in lower for kw in creature_keywords):
            categories.append('creatures')
        
        engram_keywords = [
            'engram', 'craft', 'crafting', 'recipe', 'item', 'blueprint',
            'spawn code', 'spawn command', 'gfi', 'cheat', 'structure', 'weapon',
            'armor', 'tool', 'resource'
        ]
        if any(kw in lower for kw in engram_keywords):
            categories.append('engrams')
        
        loot_keywords = ['loot', 'drop', 'beacon', 'supply', 'crate', 'cave', 'artifact']
        if any(kw in lower for kw in loot_keywords):
            categories.append('loot_containers')
        
        ini_keywords = [
            'config', 'ini', 'setting', 'server', 'admin', 'difficulty', 'rate',
            'multiplier', 'harvest', 'xp', 'experience', 'gameusersettings', 'game.ini'
        ]
        if any(kw in lower for kw in ini_keywords):
            categories.append('ini_options')
        
        news_keywords = ['patch', 'update', 'news', 'crunch', 'community', 'changelog']
        if any(kw in lower for kw in news_keywords):
            categories.append('news_posts')
        
        if not categories:
            categories = ['creatures', 'engrams', 'qa_pairs', 'news_posts']
        
        if 'qa_pairs' not in categories:
            categories.append('qa_pairs')
        
        return categories
    
    def _convert_to_fts_query(self, query: str) -> Optional[str]:
        words = re.split(r'\s+', query)
        clean_words = []
        for w in words:
            clean = re.sub(r'[^\w]', '', w)
            if len(clean) >= 2:
                clean_words.append(f"{clean}*")
        
        if not clean_words:
            return None
        return ' OR '.join(clean_words)
    
    async def _search_table(
        self, db: aiosqlite.Connection, table: str, fts_table: str,
        join_col: str, query: str, max_results: int
    ) -> list[dict]:
        fts_query = self._convert_to_fts_query(query)
        if not fts_query:
            return []
        
        sql = f"""
            SELECT t.*, rank
            FROM {fts_table} fts
            JOIN {table} t ON t.{join_col} = fts.{join_col}
            WHERE {fts_table} MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        try:
            async with db.execute(sql, (fts_query, max_results)) as cursor:
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                results = []
                for row in rows:
                    result = dict(zip(columns, row))
                    result['_source'] = table
                    results.append(result)
                return results
        except Exception as e:
            logger.warning(f"FTS search failed on {table}: {e}")
            return []
    
    async def search_knowledge(self, query: str, max_results: int = 5) -> list[dict]:
        if not self.rag_db_path.exists():
            logger.warning(f"RAG database not found at {self.rag_db_path}")
            return []
        
        categories = self._classify_query(query)
        all_results = []
        
        async with aiosqlite.connect(self.rag_db_path) as db:
            db.row_factory = aiosqlite.Row
            
            for category in categories:
                if category == 'creatures':
                    results = await self._search_table(
                        db, 'creatures', 'fts_creatures', 'name', query, max_results
                    )
                elif category == 'engrams':
                    results = await self._search_table(
                        db, 'engrams', 'fts_engrams', 'label', query, max_results
                    )
                elif category == 'loot_containers':
                    results = await self._search_table(
                        db, 'loot_containers', 'fts_loot', 'label', query, max_results
                    )
                elif category == 'ini_options':
                    results = await self._search_table(
                        db, 'ini_options', 'fts_ini', 'label', query, max_results
                    )
                elif category == 'news_posts':
                    results = await self._search_table(
                        db, 'news_posts', 'fts_news', 'title', query, max_results
                    )
                elif category == 'qa_pairs':
                    results = await self._search_table(
                        db, 'qa_pairs', 'fts_qa', 'instruction', query, max_results
                    )
                elif category == 'bot_commands':
                    results = await self._search_table(
                        db, 'bot_commands', 'fts_commands', 'command', query, max_results
                    )
                else:
                    results = []
                
                all_results.extend(results)
        
        return all_results
    
    def _format_creature_context(self, results: list[dict]) -> str:
        lines = ["--- CREATURE DATA ---"]
        for c in results:
            lines.append(f"Creature: {c.get('name', 'Unknown')}")
            if c.get('blueprint'):
                lines.append(f"  Blueprint: {c['blueprint']}")
            if c.get('taming_method'):
                lines.append(f"  Taming Method: {c['taming_method']}")
            
            stats = []
            if c.get('base_health'):
                stats.append(f"HP:{c['base_health']}")
            if c.get('base_stamina'):
                stats.append(f"Stam:{c['base_stamina']}")
            if c.get('base_weight'):
                stats.append(f"Weight:{c['base_weight']}")
            if c.get('base_melee'):
                stats.append(f"Melee:{c['base_melee']}")
            if stats:
                lines.append(f"  Base Stats: {', '.join(stats)}")
            
            if c.get('incubation_time'):
                hours = round(c['incubation_time'] / 3600, 1)
                lines.append(f"  Incubation: {hours}h")
            if c.get('maturation_time'):
                hours = round(c['maturation_time'] / 3600, 1)
                lines.append(f"  Maturation: {hours}h")
            lines.append("")
        return '\n'.join(lines)
    
    def _format_engram_context(self, results: list[dict]) -> str:
        lines = ["--- ENGRAM/ITEM DATA ---"]
        for e in results:
            lines.append(f"Item: {e.get('label', 'Unknown')}")
            if e.get('class_string'):
                spawn = e['class_string'].replace('_C', '')
                lines.append(f"  Spawn Code: cheat gfi {spawn} 1 0 0")
            if e.get('required_level'):
                lines.append(f"  Required Level: {e['required_level']}")
            if e.get('required_points'):
                lines.append(f"  Engram Points: {e['required_points']}")
            lines.append("")
        return '\n'.join(lines)
    
    def _format_loot_context(self, results: list[dict]) -> str:
        lines = ["--- LOOT CONTAINER DATA ---"]
        for l in results:
            lines.append(f"Loot Source: {l.get('label', 'Unknown')}")
            if l.get('class_string'):
                lines.append(f"  Class: {l['class_string']}")
            if l.get('multiplier_min') or l.get('multiplier_max'):
                lines.append(f"  Quality: {l.get('multiplier_min')}-{l.get('multiplier_max')}")
            lines.append("")
        return '\n'.join(lines)
    
    def _format_ini_context(self, results: list[dict]) -> str:
        lines = ["--- SERVER CONFIGURATION ---"]
        for i in results:
            lines.append(f"Setting: {i.get('label', 'Unknown')}")
            if i.get('file') and i.get('header'):
                lines.append(f"  Location: [{i['header']}] in {i['file']}")
            if i.get('key'):
                lines.append(f"  INI Key: {i['key']}")
            if i.get('description'):
                lines.append(f"  Description: {i['description']}")
            if i.get('default_value'):
                lines.append(f"  Default: {i['default_value']}")
            lines.append("")
        return '\n'.join(lines)
    
    def _format_news_context(self, results: list[dict]) -> str:
        lines = ["--- NEWS & PATCH NOTES ---"]
        for n in results:
            lines.append(f"Title: {n.get('title', 'Unknown')}")
            if n.get('content'):
                content = str(n['content'])
                if len(content) > 500:
                    content = content[:500] + '...'
                lines.append(f"  Content: {content}")
            lines.append("")
        return '\n'.join(lines)
    
    def _format_qa_context(self, results: list[dict]) -> str:
        lines = ["--- TRAINING DATA (Q&A) ---"]
        for qa in results:
            lines.append(f"Q: {qa.get('instruction', '')}")
            lines.append(f"A: {qa.get('output', '')}")
            lines.append("")
        return '\n'.join(lines)
    
    def _format_command_context(self, results: list[dict]) -> str:
        lines = ["--- PHOENIX BOT COMMANDS ---"]
        for cmd in results:
            command = cmd.get('command', '/unknown')
            desc = cmd.get('description', '')
            usage = cmd.get('usage', '')
            perms = cmd.get('permissions', '')
            
            lines.append(f"Command: {command}")
            if desc:
                lines.append(f"  Description: {desc}")
            if usage:
                lines.append(f"  Usage: {usage}")
            if perms:
                lines.append(f"  Requires: {perms}")
            lines.append("")
        return '\n'.join(lines)
    
    def build_context(self, results: list[dict], max_tokens: int = 3000) -> str:
        if not results:
            return "No relevant data found in the knowledge base for this query."
        
        grouped: dict[str, list[dict]] = {}
        for r in results:
            source = r.get('_source', 'unknown')
            if source not in grouped:
                grouped[source] = []
            grouped[source].append(r)
        
        context_parts = []
        current_tokens = 0
        
        ordered = ['qa_pairs'] + [s for s in grouped.keys() if s != 'qa_pairs']
        
        for source in ordered:
            if source not in grouped:
                continue
            items = grouped[source]
            
            if source == 'creatures':
                formatted = self._format_creature_context(items)
            elif source == 'engrams':
                formatted = self._format_engram_context(items)
            elif source == 'loot_containers':
                formatted = self._format_loot_context(items)
            elif source == 'ini_options':
                formatted = self._format_ini_context(items)
            elif source == 'news_posts':
                formatted = self._format_news_context(items)
            elif source == 'qa_pairs':
                formatted = self._format_qa_context(items)
            elif source == 'bot_commands':
                formatted = self._format_command_context(items)
            else:
                formatted = '\n'.join([str(item) for item in items])
            
            if formatted:
                tokens = int(len(formatted.split()) * 1.3)
                if current_tokens + tokens <= max_tokens:
                    context_parts.append(formatted)
                    current_tokens += tokens
        
        if not context_parts:
            return "No reference data available for this query."
        
        header = "=== REFERENCE DATA (supplementary stats and verified info) ===\nUse this to enhance your answer with precise numbers."
        return header + '\n\n' + '\n\n'.join(context_parts)
    
    async def query_gemini(self, prompt: str) -> str:
        if not self.api_key:
            return "Error: Gemini API key not configured."
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_output_tokens,
            },
            "tools": [{"google_search": {}}],
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        }
        
        session = await self._get_session()
        try:
            async with session.post(
                url, json=body, timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
            ) as resp:
                if resp.status == 429:
                    return "I'm handling too many requests right now. Please try again in a minute."
                
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Gemini API error {resp.status}: {text}")
                    return f"Error: Gemini API returned status {resp.status}."
                
                data = await resp.json()
                text = extract_gemini_text(data)

                if not text:
                    # Also the honest answer when Gemini blocks on safety: it returns
                    # promptFeedback with no candidates at all.
                    return "I couldn't generate a response. Please try rephrasing your question."

                return text

        except asyncio.TimeoutError:
            return "The AI query timed out. Please try a simpler question."
        except (aiohttp.ClientError, OSError) as e:
            # TRANSPORT failures only. This used to be a bare `except Exception`, which also
            # swallowed every payload-shape bug in the extraction above and reported it as
            # "Unable to reach the Gemini API" — a message that sends whoever debugs it chasing
            # the network and the API key while the API is answering perfectly well.
            logger.error(f"Gemini request failed (transport): {e}")
            return f"Error: Unable to reach the Gemini API. {str(e)}"
        except Exception as e:
            logger.error(f"Gemini response could not be parsed: {e}", exc_info=True)
            return "The AI replied in a format I couldn't read. This has been logged."
    
    async def _fetch_guild_context(self, guild_id: int) -> str:
        """Fetch guild-specific context (servers, mods) from bot database."""
        if not BOT_DB_PATH.exists():
            return ""
        
        context_parts = []
        
        try:
            async with aiosqlite.connect(BOT_DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                
                # Fetch servers
                async with db.execute(
                    "SELECT name, map_name, hosting_type FROM ark_servers WHERE guild_id = ? AND enabled = 1",
                    (guild_id,)
                ) as cursor:
                    servers = await cursor.fetchall()
                
                if servers:
                    server_lines = ["--- YOUR ARK SERVERS ---"]
                    for s in servers:
                        map_info = s['map_name'] or s['name']
                        hosting = s['hosting_type'] or 'self_hosted'
                        server_lines.append(f"- {s['name']} ({map_info}, {hosting})")
                    context_parts.append('\n'.join(server_lines))
                
                # Fetch installed mods
                async with db.execute(
                    """SELECT DISTINCT cm.mod_name 
                       FROM curseforge_mods cm 
                       JOIN ark_servers ars ON cm.guild_id = ars.guild_id 
                       WHERE cm.guild_id = ?""",
                    (guild_id,)
                ) as cursor:
                    mods = await cursor.fetchall()
                
                if mods:
                    mod_names = [m['mod_name'] for m in mods if m['mod_name']]
                    if mod_names:
                        mod_lines = ["--- YOUR INSTALLED MODS ---"]
                        mod_lines.append(', '.join(mod_names[:20]))
                        if len(mod_names) > 20:
                            mod_lines.append(f"... and {len(mod_names) - 20} more")
                        context_parts.append('\n'.join(mod_lines))
        
        except Exception as e:
            logger.warning(f"Failed to fetch guild context: {e}")
        
        return '\n\n'.join(context_parts) if context_parts else ""
    
    async def ask(self, question: str, guild_id: Optional[int] = None, is_admin: bool = False) -> str:
        logger.info(f"PhoenixAI query: {question[:100]}... (guild={guild_id}, admin={is_admin})")
        
        search_results = await self.search_knowledge(question, max_results=5)
        logger.debug(f"Found {len(search_results)} search results")
        
        context = self.build_context(search_results)
        
        guild_context = ""
        if guild_id and is_admin:
            guild_context = await self._fetch_guild_context(guild_id)
            if guild_context:
                guild_context = f"\n\n{guild_context}"
        
        permission_note = ""
        if is_admin:
            permission_note = "\n\n**USER IS AN ADMIN** - You may provide admin commands and sensitive operational details."
        else:
            permission_note = "\n\n**USER IS NOT AN ADMIN** - If asked about admin commands (restart, kick, ban, give items, server config, etc.), politely decline: 'That requires admin permissions. Please contact a server administrator.' Do NOT reveal admin command syntax or details to non-admins."
        
        prompt = f"""USER QUESTION: {question}

CONTEXT FROM KNOWLEDGE BASE:
{context}{guild_context}{permission_note}

Based on the context above, provide a helpful and accurate answer. If the context doesn't contain enough information, say so honestly."""
        
        response = await self.query_gemini(prompt)
        logger.info(f"PhoenixAI response: {len(response)} chars")
        
        return response


_phoenix_ai: Optional[PhoenixAI] = None


def get_phoenix_ai() -> PhoenixAI:
    global _phoenix_ai
    if _phoenix_ai is None:
        rag_path = getattr(Config, 'PHOENIX_RAG_DB_PATH', None)
        if rag_path:
            rag_path = Path(rag_path)
        _phoenix_ai = PhoenixAI(rag_db_path=rag_path)
    return _phoenix_ai


async def cleanup_phoenix_ai():
    global _phoenix_ai
    if _phoenix_ai:
        await _phoenix_ai.close()
        _phoenix_ai = None
