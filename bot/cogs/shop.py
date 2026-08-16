"""
Shop cog — Browse items, cart, purchase, and delivery.

Delivery uses: GiveItemToPlayer <PlayerID> "<blueprint>" <qty> <quality> <force_blueprint>
Players found via players.last_player_id and last_seen_server.
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Modal, TextInput
import logging
import io
import csv
import json
import re
from typing import Optional
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from bot.database import shop_db, players_db, economy_db
from bot.database.shop_db import QUALITY_NAMES, VALID_QUALITIES
from bot.utils.subscription_checker import check_feature
from bot.utils.config import Config

logger = logging.getLogger("ShopCog")

# ARK RCON may return "Keep Alive" or ListPlayers data as buffered responses —
# those are not failures. Only reject on explicit ARK error messages.
DELIVERY_FAILURE_PATTERNS = [
    "not found", 
    "not logged in", 
    "no character", 
    "invalid player", 
    "failed to give"
    # NOTE: "server received, but no response" is NOT a failure - ARK successfully received the command
    # This response appears due to ARK's RCON buffering, but the item IS delivered
]

SHOP_THUMBNAIL = "https://i.imgur.com/ydZdAqo.png"
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]

# ---------------------------------------------------------------------------
# Shop Import / Export helpers
# ---------------------------------------------------------------------------

# Column aliases — matches PhoenixShop_Prices.xlsx header names exactly
_COL_ALIASES: dict[str, list[str]] = {
    "name":                    ["item name", "name", "item"],
    "cost":                    ["price per item", "price", "cost"],
    "supports_quality":        ["allow quality select", "quality tiers", "supports quality", "quality"],
    "allow_blueprint_select":  ["allow blueprint select", "blueprint select", "allow blueprint"],
    "category":                ["category"],
    "description":             ["description", "desc"],
    "ark_command":             ["blueprint path", "blueprint"],
    "enabled":                 ["enabled", "active"],
}

# Export column order — matches PhoenixShop_Prices.xlsx exactly for round-tripping
_EXPORT_COLUMNS = [
    ("Item Name",              "name"),
    ("Price Per Item",         "cost"),
    ("Allow Quality Select",   "supports_quality"),
    ("Allow Blueprint Select", "allow_blueprint_select"),
    ("Category",               "category"),
    ("Description",            "description"),
    ("Blueprint Path",         "ark_command"),
    ("Enabled",                "enabled"),
]

_SAMPLE_ITEMS = [
    # (name, cost, supports_quality, category, description, blueprint_path)
    # Blueprint paths match the ARK:SA GiveItemToPlayer format (no _C suffix)
    ("Advanced Bullet", 10, False, "Ammo",
     "High-quality rifle ammunition",
     "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Ammo/PrimalItemAmmo_AdvancedBullet.PrimalItemAmmo_AdvancedBullet'"),
    ("Simple Bullet", 5, False, "Ammo",
     "Basic rifle ammunition",
     "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Ammo/PrimalItemAmmo_SimpleBullet.PrimalItemAmmo_SimpleBullet'"),
    ("Assault Rifle", 500, True, "Weapons",
     "Automatic rifle — supports quality tiers",
     "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Weapons/PrimalItem_WeaponRifle.PrimalItem_WeaponRifle'"),
    ("Riot Helmet", 300, True, "Armor",
     "High-tier riot armor helmet",
     "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Armor/Riot/PrimalItemArmor_RiotHelmet.PrimalItemArmor_RiotHelmet'"),
    ("Element", 1000, False, "Resources",
     "Element for TEK tier crafting",
     "Blueprint'/Game/PrimalEarth/CoreBlueprints/Resources/PrimalItemResource_Element.PrimalItemResource_Element'"),
    ("Metal Ingot", 5, False, "Resources",
     "Metal ingot for crafting",
     "Blueprint'/Game/PrimalEarth/CoreBlueprints/Resources/PrimalItemResource_MetalIngot.PrimalItemResource_MetalIngot'"),
    ("Artifact of the Clever", 50, False, "Boss Items",
     "Artifact from The Island boss arenas",
     "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Artifacts/PrimalItemConsumable_Artifact_03.PrimalItemConsumable_Artifact_03'"),
    ("Raptor Saddle", 200, True, "Saddles",
     "Saddle for Raptor",
     "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Saddle/PrimalItemArmor_RaptorSaddle.PrimalItemArmor_RaptorSaddle'"),
]


def _parse_bool_field(val, default: bool = True) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).lower().strip()
    if s in ("yes", "true", "1", "on", "enabled"):
        return True
    if s in ("no", "false", "0", "off", "disabled", ""):
        return False
    return default


def _find_col_value(row: dict, aliases: list[str]):
    """Find a value in a dict row by case-insensitive alias matching."""
    for k, v in row.items():
        if k is not None and str(k).lower().strip() in aliases:
            return v
    return None


def _strip_blueprint_quotes(val: str) -> str:
    """Strip outer double-quotes from blueprint paths if present."""
    val = val.strip()
    if val.startswith('"') and val.endswith('"'):
        val = val[1:-1]
    return val


def _parse_shop_row(row: dict, row_num: int) -> tuple:
    """Parse a single row dict into a shop item dict. Returns (item_or_None, error_or_None).

    Disabled items (Enabled=no) are imported with enabled=False rather than skipped,
    so admins can toggle them via /shopadmin toggle without re-uploading.
    """
    name_val  = _find_col_value(row, _COL_ALIASES["name"])
    cost_val  = _find_col_value(row, _COL_ALIASES["cost"])
    bp_val    = _find_col_value(row, _COL_ALIASES["ark_command"])
    cat_val   = _find_col_value(row, _COL_ALIASES["category"])
    desc_val  = _find_col_value(row, _COL_ALIASES["description"])
    enabled_val = _find_col_value(row, _COL_ALIASES["enabled"])
    sq_val    = _find_col_value(row, _COL_ALIASES["supports_quality"])
    abs_val   = _find_col_value(row, _COL_ALIASES["allow_blueprint_select"])

    # Skip completely blank rows silently
    if not name_val and not bp_val:
        return None, None

    if not name_val:
        return None, f"Row {row_num}: missing item name"
    if not bp_val:
        return None, f"Row {row_num}: '{name_val}' missing blueprint path"
    if not cat_val:
        return None, f"Row {row_num}: '{name_val}' missing category"

    try:
        if isinstance(cost_val, (int, float)):
            cost = int(cost_val)
        else:
            cost = int(str(cost_val).strip().replace(",", ""))
        if cost < 0:
            raise ValueError
    except (ValueError, TypeError):
        return None, f"Row {row_num}: '{name_val}' invalid price '{cost_val}'"

    return {
        "name": str(name_val).strip(),
        "cost": cost,
        "ark_command": _strip_blueprint_quotes(str(bp_val)),
        "category": str(cat_val).strip().lower(),
        "description": str(desc_val).strip() if desc_val else "",
        "enabled": _parse_bool_field(enabled_val, default=True),
        "supports_quality": _parse_bool_field(sq_val, default=False),
        "allow_blueprint_select": _parse_bool_field(abs_val, default=False),
    }, None


def _parse_packs_sheet(ws, items_by_name: dict) -> tuple:
    """Parse the Packs worksheet into pack item dicts.

    items_by_name: {lower_name: item_dict} — used to resolve item references.
    Returns (packs, errors).

    Pack sheet columns: Pack Name, Price, Category, Description, Items, Enabled
    where Items is a comma-separated list of item names from the items sheet.
    """
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []

    headers = [str(c).strip() if c is not None else "" for c in rows[0]]
    packs, errors = [], []

    for i, row_vals in enumerate(rows[1:], start=2):
        row = dict(zip(headers, row_vals))

        pack_name = _find_col_value(row, ["pack name", "name"])
        price_val = _find_col_value(row, ["price", "cost", "price per item"])
        category  = _find_col_value(row, ["category"])
        desc      = _find_col_value(row, ["description", "desc"])
        items_str = _find_col_value(row, ["items", "item names", "item list"])
        enabled   = _find_col_value(row, ["enabled", "active"])

        # Skip blank rows silently
        if not pack_name and not items_str:
            continue

        # Skip disabled packs silently
        if not _parse_bool_field(enabled, default=True):
            continue

        if not pack_name:
            errors.append(f"Packs row {i}: missing pack name")
            continue
        if not items_str:
            errors.append(f"Packs row {i}: '{pack_name}' missing items list")
            continue
        if not category:
            errors.append(f"Packs row {i}: '{pack_name}' missing category")
            continue

        try:
            if isinstance(price_val, (int, float)):
                cost = int(price_val)
            else:
                cost = int(str(price_val).strip().replace(",", ""))
            if cost < 0:
                raise ValueError
        except (ValueError, TypeError):
            errors.append(f"Packs row {i}: '{pack_name}' invalid price '{price_val}'")
            continue

        # Resolve item names to blueprints. Supports "Item Name x5" quantity syntax.
        raw_entries = [n.strip() for n in str(items_str).split(",") if n.strip()]
        pack_items = []
        unknown = []
        for entry in raw_entries:
            qty_match = re.match(r'^(.+?)\s*[xX](\d+)$', entry)
            if qty_match:
                item_name = qty_match.group(1).strip()
                qty = max(1, int(qty_match.group(2)))
            else:
                item_name = entry
                qty = 1
            found = items_by_name.get(item_name.lower())
            if not found:
                unknown.append(item_name)
            else:
                pack_items.append({
                    "name": found["name"],
                    "ark_command": found["ark_command"],
                    "quantity": qty,
                })

        if unknown:
            errors.append(f"Pack '{pack_name}' references unknown item(s): {', '.join(unknown)}")

        if not pack_items:
            errors.append(f"Pack '{pack_name}' has no valid items — skipped")
            continue

        packs.append({
            "name": str(pack_name).strip(),
            "cost": cost,
            "ark_command": "#PACK#",
            "category": str(category).strip().lower(),
            "description": str(desc).strip() if desc else "",
            "supports_quality": False,
            "is_pack": True,
            "pack_contents": json.dumps(pack_items),
        })

    return packs, errors


def _parse_xlsx_shop(data: bytes) -> tuple:
    """Parse xlsx bytes → (all_items, errors).

    Parses the 'items' sheet for regular items and the 'Packs' sheet (if present)
    for pack bundles. Returns a combined list of item dicts.
    """
    if len(data) < 4 or data[:2] != b'PK':
        return [], [
            f"File does not appear to be a valid .xlsx file "
            f"(received {len(data):,} bytes, magic={data[:4] if data else b'empty'}). "
            "This usually means the upload was interrupted or the wrong file was attached. "
            "Please try again."
        ]
    buf = io.BytesIO(data)
    try:
        wb = openpyxl.load_workbook(buf, read_only=True, data_only=True)
    except Exception as e:
        return [], [f"Failed to open Excel file: {e}. File size was {len(data):,} bytes."]

    # --- Items sheet --- (case-insensitive sheet name match)
    sheet_names_lower = {s.lower(): s for s in wb.sheetnames}
    items_sheet_name = sheet_names_lower.get("items")
    ws_items = wb[items_sheet_name] if items_sheet_name else wb.active
    rows = list(ws_items.iter_rows(values_only=True))
    if not rows:
        return [], ["Empty spreadsheet — no rows found"]

    headers = [str(c).strip() if c is not None else "" for c in rows[0]]
    normalized = [h.lower() for h in headers]

    missing = []
    for field in ("name", "cost", "ark_command", "category"):
        if not any(alias in normalized for alias in _COL_ALIASES[field]):
            missing.append(_COL_ALIASES[field][0].title())
    if missing:
        return [], [f"Missing required column(s): {', '.join(missing)}. Found: {[h for h in headers if h]}"]

    items, errors = [], []
    for i, row_vals in enumerate(rows[1:], start=2):
        row = dict(zip(headers, row_vals))
        item, err = _parse_shop_row(row, i)
        if err:
            errors.append(err)
        elif item:
            items.append(item)

    # --- Packs sheet (optional) ---
    pack_sheet_names = [n for n in wb.sheetnames if n.lower() in ("packs", "pack", "boss packs")]
    if pack_sheet_names:
        ws_packs = wb[pack_sheet_names[0]]
        # Build lookup by lowercase name for resolving pack item references
        items_by_name = {item["name"].lower(): item for item in items}
        packs, pack_errors = _parse_packs_sheet(ws_packs, items_by_name)
        items.extend(packs)
        errors.extend(pack_errors)

    return items, errors


def _parse_csv_shop(data: bytes) -> tuple:
    """Parse CSV bytes → (items, errors)."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ["Empty CSV or missing header row"]

    items, errors = [], []
    for i, row in enumerate(reader, start=2):
        item, err = _parse_shop_row(dict(row), i)
        if err:
            errors.append(err)
        elif item:
            items.append(item)
    return items, errors


def _write_items_sheet(ws, items: list, header_font, header_fill):
    """Write regular (non-pack) items to a worksheet."""
    col_headers = [col[0] for col in _EXPORT_COLUMNS]
    for col_idx, header in enumerate(col_headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for item in items:
        if item.get("is_pack"):
            continue  # packs go in their own sheet
        row_vals = []
        for _, field in _EXPORT_COLUMNS:
            if field in ("enabled", "supports_quality", "allow_blueprint_select"):
                row_vals.append("yes" if item.get(field) else "no")
            else:
                row_vals.append(item.get(field, ""))
        ws.append(row_vals)

    col_widths = [40, 15, 18, 20, 20, 40, 80, 10]
    for col_idx, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width


def _write_packs_sheet(ws, packs: list, header_font, header_fill):
    """Write pack items to the Packs worksheet."""
    pack_headers = ["Pack Name", "Price", "Category", "Description", "Items", "Enabled"]
    for col_idx, header in enumerate(pack_headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for pack in packs:
        # Reconstruct comma-separated item names from pack_contents JSON
        items_str = ""
        try:
            pack_items = json.loads(pack.get("pack_contents") or "[]")
            items_str = ", ".join(
                f"{pi['name']} x{pi['quantity']}" if pi.get("quantity", 1) > 1 else pi["name"]
                for pi in pack_items
            )
        except Exception:
            pass
        ws.append([
            pack.get("name", ""),
            pack.get("cost", 0),
            pack.get("category", ""),
            pack.get("description", ""),
            items_str,
            "yes",
        ])

    pack_col_widths = [40, 12, 20, 40, 80, 10]
    for col_idx, width in enumerate(pack_col_widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width


def _build_shop_xlsx(items: list) -> bytes:
    """Build an xlsx export from items list (includes Packs sheet if packs exist). Returns bytes."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "items"

    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    _write_items_sheet(ws, items, header_font, header_fill)

    packs = [it for it in items if it.get("is_pack")]
    if packs:
        ws_packs = wb.create_sheet(title="Packs")
        _write_packs_sheet(ws_packs, packs, header_font, header_fill)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


_SAMPLE_PACKS = [
    # (pack_name, price, category, description, items_csv)
    ("Starter Pack", 250, "Starter Packs",
     "Everything you need to get started",
     "Advanced Bullet, Metal Ingot"),
    ("Boss Fighter Pack", 800, "Boss Packs",
     "Gear up for boss fights",
     "Assault Rifle, Riot Helmet, Element"),
    ("Resource Bundle", 150, "Resource Packs",
     "Large resource bundle for building",
     "Metal Ingot, Element"),
]


def _build_sample_xlsx() -> bytes:
    """Build a sample template xlsx with example ARK items and packs."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "items"

    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    col_headers = [col[0] for col in _EXPORT_COLUMNS]
    for col_idx, header in enumerate(col_headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for name, cost, sq, category, desc, bp in _SAMPLE_ITEMS:
        ws.append([name, cost, "yes" if sq else "no", "no", category, desc, bp, "yes"])

    col_widths = [40, 15, 18, 20, 20, 40, 80, 10]
    for col_idx, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Packs sheet
    ws_packs = wb.create_sheet(title="Packs")
    pack_headers = ["Pack Name", "Price", "Category", "Description", "Items", "Enabled"]
    for col_idx, header in enumerate(pack_headers, start=1):
        cell = ws_packs.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for pack_name, price, category, desc, items_csv in _SAMPLE_PACKS:
        ws_packs.append([pack_name, price, category, desc, items_csv, "yes"])

    pack_col_widths = [40, 12, 20, 40, 60, 10]
    for col_idx, width in enumerate(pack_col_widths, start=1):
        ws_packs.column_dimensions[get_column_letter(col_idx)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# Shop Browse View
# ---------------------------------------------------------------------------

class ShopView(View):
    """Stateful shop browsing view: home → category → item → buy.

    Navigation uses paginated button layout (4-per-page) matching the
    PowerShell version: ⏮️◀️▶️⏭️ nav + numbered 1/2/3/4 select buttons.
    """

    PAGE_SIZE = 4

    def __init__(self, guild_id: int, discord_id: int, balance: int, currency_name: str, currency_icon: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.discord_id = discord_id
        self.balance = balance
        self.currency_name = currency_name
        self.currency_icon = currency_icon
        self.all_categories: list = []
        self.cat_page: int = 0
        self.current_category: Optional[str] = None
        self.items: list = []
        self.item_page: int = 0
        self.selected_item: Optional[dict] = None

    def _footer(self) -> str:
        return f"{self.currency_icon} Balance: {self.balance:,} {self.currency_name}"

    async def show_home(self, interaction: discord.Interaction, *, first_load: bool = False):
        """Build and display the paginated category home screen."""
        if not self.all_categories:
            self.all_categories = await shop_db.get_categories(self.guild_id)

        total_pages = max(1, (len(self.all_categories) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        start = self.cat_page * self.PAGE_SIZE
        page_cats = self.all_categories[start:start + self.PAGE_SIZE]

        desc = "**Categories**\n\n"
        for i, cat in enumerate(page_cats):
            desc += f"{NUMBER_EMOJIS[i]} **{cat['category'].title()}**\nItems: {cat['count']}\n\n"

        embed = discord.Embed(
            title="🔥 Phoenix Shop",
            description=desc,
            color=discord.Color.orange(),
        )
        embed.set_thumbnail(url=SHOP_THUMBNAIL)
        embed.add_field(name="💰 Your Balance", value=f"{self.balance:,} Phoenix Coins", inline=False)
        embed.set_footer(text=f"Page {self.cat_page + 1}/{total_pages}")

        self.clear_items()

        # Row 0: ⏮️ ◀️ ▶️ ⏭️ navigation
        first_btn = discord.ui.Button(emoji="⏮️", style=discord.ButtonStyle.primary, row=0,
                                      disabled=(self.cat_page == 0))
        first_btn.callback = self._nav_first
        self.add_item(first_btn)

        prev_btn = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.primary, row=0,
                                     disabled=(self.cat_page == 0))
        prev_btn.callback = self._nav_prev
        self.add_item(prev_btn)

        next_btn = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.primary, row=0,
                                     disabled=(self.cat_page >= total_pages - 1))
        next_btn.callback = self._nav_next
        self.add_item(next_btn)

        last_btn = discord.ui.Button(emoji="⏭️", style=discord.ButtonStyle.primary, row=0,
                                     disabled=(self.cat_page >= total_pages - 1))
        last_btn.callback = self._nav_last
        self.add_item(last_btn)

        # Row 1: 1️⃣ 2️⃣ 3️⃣ 4️⃣ category selector buttons
        for i in range(self.PAGE_SIZE):
            if i < len(page_cats):
                btn = discord.ui.Button(label=NUMBER_EMOJIS[i], style=discord.ButtonStyle.success, row=1)
                btn.callback = self._make_cat_btn(page_cats[i]["category"])
            else:
                btn = discord.ui.Button(label=NUMBER_EMOJIS[i], style=discord.ButtonStyle.success, row=1,
                                        disabled=True)
                btn.callback = self._noop
            self.add_item(btn)

        # Row 2: Back (disabled on home) / Cart / Search
        back_btn = discord.ui.Button(label="🔙 Back", style=discord.ButtonStyle.secondary, row=2, disabled=True)
        back_btn.callback = self._back_to_home
        self.add_item(back_btn)

        cart_btn = discord.ui.Button(label="🛒 Cart", style=discord.ButtonStyle.secondary, row=2)
        cart_btn.callback = self._view_cart
        self.add_item(cart_btn)

        search_btn = discord.ui.Button(label="🔍 Search", style=discord.ButtonStyle.secondary, row=2)
        search_btn.callback = self._search_placeholder
        self.add_item(search_btn)

        # Row 3: Quick Buy Phoenix Coins
        qb_btn = discord.ui.Button(
            label="💰 Buy Phoenix Coins (Quick)", style=discord.ButtonStyle.success, row=3
        )
        qb_btn.callback = self._quick_buy_coins
        self.add_item(qb_btn)

        if first_load:
            await interaction.response.send_message(embed=embed, view=self, ephemeral=True)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def show_category(self, interaction: discord.Interaction):
        """Build and display the paginated item list for the current category."""
        total_pages = max(1, (len(self.items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        start = self.item_page * self.PAGE_SIZE
        page_items = self.items[start:start + self.PAGE_SIZE]

        desc = "**Items**\n\n"
        for i, item in enumerate(page_items):
            if item.get("cost", 0) <= 0:
                desc += f"{NUMBER_EMOJIS[i]} ~~**{item['name']}**~~ ❌ UNAVAILABLE\nPrice: N/A\n\n"
            else:
                line = f"{NUMBER_EMOJIS[i]} **{item['name']}**\nPrice: {item['cost']:,}"
                if item.get("description"):
                    line += f"\n_{item['description']}_"
                desc += line + "\n\n"
        desc += "_Total Item Cost = Base Price × Quantity × Tier_\n_Listed price assumes Tier 1._"

        embed = discord.Embed(
            title=f"🔥 Phoenix Shop - {self.current_category.title()}",
            description=desc,
            color=discord.Color.gold(),
        )
        embed.add_field(name="💰 Your Balance", value=f"{self.balance:,} {self.currency_name}", inline=True)
        embed.add_field(name="📦 Items", value=str(len(self.items)), inline=True)
        embed.set_footer(text=f"Page {self.item_page + 1}/{total_pages}")

        self.clear_items()

        # Row 0: 1️⃣ 2️⃣ 3️⃣ 4️⃣ item buttons — open PurchaseModal directly
        for i in range(self.PAGE_SIZE):
            if i < len(page_items):
                item = page_items[i]
                disabled = item.get("cost", 0) <= 0
                btn = discord.ui.Button(label=NUMBER_EMOJIS[i], style=discord.ButtonStyle.primary, row=0,
                                        disabled=disabled)
                btn.callback = self._make_item_btn(item)
            else:
                btn = discord.ui.Button(label=NUMBER_EMOJIS[i], style=discord.ButtonStyle.primary, row=0,
                                        disabled=True)
                btn.callback = self._noop
            self.add_item(btn)

        # Row 1: Previous / Next pagination (only shown when applicable)
        if self.item_page > 0:
            prev_btn = discord.ui.Button(label="◀️ Previous", style=discord.ButtonStyle.secondary, row=1)
            prev_btn.callback = self._item_prev
            self.add_item(prev_btn)
        if (self.item_page + 1) < total_pages:
            next_btn = discord.ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self._item_next
            self.add_item(next_btn)

        # Row 2: Back to Categories / View Cart
        back_btn = discord.ui.Button(label="◀️ Back to Categories", style=discord.ButtonStyle.primary, row=2)
        back_btn.callback = self._back_to_home
        self.add_item(back_btn)

        cart_btn = discord.ui.Button(label="🛒 View Cart", style=discord.ButtonStyle.success, row=2)
        cart_btn.callback = self._view_cart
        self.add_item(cart_btn)

        await interaction.response.edit_message(embed=embed, view=self)

    # ------------------------------------------------------------------
    # Navigation callbacks — category pagination
    # ------------------------------------------------------------------

    async def _nav_first(self, interaction: discord.Interaction):
        self.cat_page = 0
        await self.show_home(interaction)

    async def _nav_prev(self, interaction: discord.Interaction):
        self.cat_page = max(0, self.cat_page - 1)
        await self.show_home(interaction)

    async def _nav_next(self, interaction: discord.Interaction):
        total_pages = max(1, (len(self.all_categories) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.cat_page = min(total_pages - 1, self.cat_page + 1)
        await self.show_home(interaction)

    async def _nav_last(self, interaction: discord.Interaction):
        total_pages = max(1, (len(self.all_categories) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.cat_page = total_pages - 1
        await self.show_home(interaction)

    def _make_cat_btn(self, category: str):
        """Factory: returns a callback that navigates into the given category."""
        async def callback(interaction: discord.Interaction):
            self.current_category = category
            self.items = await shop_db.get_store_items(self.guild_id, category=category)
            self.item_page = 0
            await self.show_category(interaction)
        return callback

    # ------------------------------------------------------------------
    # Navigation callbacks — item pagination
    # ------------------------------------------------------------------

    async def _item_prev(self, interaction: discord.Interaction):
        self.item_page = max(0, self.item_page - 1)
        await self.show_category(interaction)

    async def _item_next(self, interaction: discord.Interaction):
        total_pages = max(1, (len(self.items) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.item_page = min(total_pages - 1, self.item_page + 1)
        await self.show_category(interaction)

    def _make_item_btn(self, item: dict):
        """Factory: returns a callback that opens PurchaseModal for the given item."""
        async def callback(interaction: discord.Interaction):
            self.selected_item = item
            await interaction.response.send_modal(PurchaseModal(self))
        return callback

    # ------------------------------------------------------------------
    # Action callbacks
    # ------------------------------------------------------------------

    async def _back_to_home(self, interaction: discord.Interaction):
        self.current_category = None
        await self.show_home(interaction)

    async def _view_cart(self, interaction: discord.Interaction):
        items = await shop_db.get_cart(self.guild_id, self.discord_id)
        if not items:
            await interaction.response.send_message("🛒 Your cart is empty.", ephemeral=True)
            return
        # Refresh balance — it may have changed since the shop was opened
        balance, _ = await players_db.get_balance_by_discord_id(self.guild_id, self.discord_id)
        view = CartView(self.guild_id, self.discord_id, items, balance, self.currency_name, self.currency_icon)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)

    async def _search_placeholder(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔍 Search coming soon! Use `/buy` to search by name.", ephemeral=True)

    async def _quick_buy_coins(self, interaction: discord.Interaction):
        items = await shop_db.search_store_items(self.guild_id, "Phoenix Coin", limit=5)
        item = next((i for i in items if i["name"].lower() == "phoenix coin"), None)
        if not item:
            await interaction.response.send_message(
                "❌ 'Phoenix Coins' item not found in the shop. Ask an admin to add it.",
                ephemeral=True,
            )
            return
        full_item = await shop_db.get_store_item(item["item_id"])
        if not full_item:
            await interaction.response.send_message("❌ Item not found.", ephemeral=True)
            return
        await interaction.response.send_modal(QuickBuyModal(self, full_item))

    async def _noop(self, interaction: discord.Interaction):
        await interaction.response.defer()


# ---------------------------------------------------------------------------
# Purchase Modal
# ---------------------------------------------------------------------------

class PurchaseModal(Modal):
    quantity = TextInput(label="Enter amount", placeholder="ex: 100", default="1", required=False, max_length=3)
    quality = TextInput(
        label="Quality Tier",
        style=discord.TextStyle.paragraph,
        placeholder="Enter tier: 1=Primitive, 2=Ramshackle, 4=Apprentice, 6=Journeyman, 8=Mastercraft, 10=Ascendant",
        default="1", required=False, max_length=2,
    )
    blueprint = TextInput(
        label="Add as blueprint? (yes/no)",
        placeholder="ex: yes (defaults to no)",
        default="no", required=False, max_length=3,
    )

    def __init__(self, shop_view: "ShopView", cart_mode: bool = False):
        item = shop_view.selected_item or {}
        title = f"Configure {item.get('name', 'Item')}"
        super().__init__(title=title[:45])  # Discord modal title max 45 chars
        self.shop_view = shop_view
        self.cart_mode = cart_mode
        # Only show quality field for items that support it
        if not item.get("supports_quality"):
            self.remove_item(self.quality)
        # Only show blueprint field for items that support it
        if not item.get("allow_blueprint_select"):
            self.remove_item(self.blueprint)

    async def on_submit(self, interaction: discord.Interaction):
        item = self.shop_view.selected_item
        sv = self.shop_view

        try:
            qty_raw = (self.quantity.value or "1").strip() or "1"
            qty = max(1, min(100, int(qty_raw)))
        except ValueError:
            await interaction.response.send_message("❌ Invalid quantity.", ephemeral=True)
            return

        quality = 1
        if item.get("supports_quality"):
            try:
                quality = int((self.quality.value or "1").strip() or "1")
                if quality not in VALID_QUALITIES:
                    await interaction.response.send_message(
                        f"❌ Invalid quality. Choose from: {', '.join(str(q) for q in VALID_QUALITIES)}",
                        ephemeral=True,
                    )
                    return
            except ValueError:
                quality = 1

        # Blueprint field only present in modal when item supports it
        force_blueprint = (
            item.get("allow_blueprint_select")
            and hasattr(self, "blueprint")
            and self.blueprint.value.strip().lower() in ("yes", "y", "true", "1")
        )
        total_cost = item["cost"] * qty * quality
        quality_name = QUALITY_NAMES.get(quality, "Primitive")
        bp_str = " (Blueprint)" if force_blueprint else ""

        desc_lines = [
            f"**{item['name']}** x{qty}",
            f"{quality_name}{bp_str}",
            "",
            f"**Cost:** {total_cost:,} coins",
            f"**Your Balance:** {sv.balance:,} coins",
            "",
            "Choose an action:",
        ]
        embed = discord.Embed(
            title="🛒 Purchase Options",
            description="\n".join(desc_lines),
            color=discord.Color.gold(),
        )

        view = ConfirmPurchaseView(sv, item, qty, quality, force_blueprint, total_cost)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ---------------------------------------------------------------------------
# Confirm Purchase View
# ---------------------------------------------------------------------------

class ConfirmPurchaseView(View):
    def __init__(self, shop_view, item, qty, quality, force_blueprint, total_cost, cart_mode: bool = False):
        super().__init__(timeout=None)
        self.shop_view = shop_view
        self.item = item
        self.qty = qty
        self.quality = quality
        self.force_blueprint = force_blueprint
        self.total_cost = total_cost
        self.cart_mode = cart_mode

    @discord.ui.button(label="💳 Buy Now", style=discord.ButtonStyle.success)
    async def buy_now(self, interaction: discord.Interaction, button: discord.ui.Button):
        sv = self.shop_view
        self.stop()
        await interaction.response.defer(ephemeral=True)
        # Clear the confirmation embed immediately so users can't double-click
        try:
            await interaction.edit_original_response(content="⏳ Processing your purchase...", embed=None, view=None)
        except Exception:
            pass
        shop_cog = interaction.client.get_cog("ShopCog")
        if not shop_cog:
            await interaction.followup.send("❌ Shop system unavailable.", ephemeral=True)
            return
        try:
            await shop_cog.process_purchase(
                interaction, sv.guild_id, sv.discord_id,
                self.item, self.qty, self.quality, self.force_blueprint, self.total_cost,
            )
        except Exception as e:
            logger.error(f"Buy Now failed: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Purchase error: {e}", ephemeral=True)

    @discord.ui.button(label="🛒 Add to Cart", style=discord.ButtonStyle.primary)
    async def add_to_cart(self, interaction: discord.Interaction, button: discord.ui.Button):
        sv = self.shop_view
        self.stop()
        try:
            success = await shop_db.add_to_cart(
                sv.guild_id, sv.discord_id, self.item["item_id"],
                self.qty, self.quality, self.force_blueprint,
            )
            if not success:
                await interaction.response.edit_message(content="❌ Failed to add to cart.", embed=None, view=None)
                return
            # Open the cart view directly so the user can checkout immediately
            balance, _ = await players_db.get_balance_by_discord_id(sv.guild_id, sv.discord_id)
            items = await shop_db.get_cart(sv.guild_id, sv.discord_id)
            cart_view = CartView(sv.guild_id, sv.discord_id, items, balance, sv.currency_name, sv.currency_icon)
            await interaction.response.edit_message(embed=cart_view.build_embed(), view=cart_view, content=None)
        except Exception as e:
            logger.error(f"Add to Cart failed: {e}", exc_info=True)
            try:
                await interaction.response.edit_message(content=f"❌ Error: {e}", embed=None, view=None)
            except Exception:
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(content="Purchase cancelled.", embed=None, view=None)


# ---------------------------------------------------------------------------
# Quick Buy Modal (Phoenix Coins)
# ---------------------------------------------------------------------------

class QuickBuyModal(Modal, title="💰 Buy Phoenix Coins"):
    quantity = TextInput(
        label="How many Phoenix Coins?",
        placeholder="ex: 100",
        default="1",
        required=True,
        max_length=6,
    )

    def __init__(self, shop_view: ShopView, item: dict):
        super().__init__()
        self.shop_view = shop_view
        self.item = item

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = max(1, min(10000, int(self.quantity.value.strip())))
        except ValueError:
            await interaction.response.send_message("❌ Invalid quantity.", ephemeral=True)
            return

        total_cost = self.item["cost"] * qty
        sv = self.shop_view

        await interaction.response.defer(ephemeral=True)
        shop_cog = interaction.client.get_cog("ShopCog")
        if shop_cog:
            await shop_cog.process_purchase(
                interaction, sv.guild_id, sv.discord_id,
                self.item, qty, 1, False, total_cost,
            )
        else:
            await interaction.followup.send("❌ Shop system unavailable.", ephemeral=True)


# ---------------------------------------------------------------------------
# Cart View
# ---------------------------------------------------------------------------

class CartView(View):
    def __init__(self, guild_id: int, discord_id: int, items: list, balance: int, currency_name: str, currency_icon: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.discord_id = discord_id
        self.items = items
        self.balance = balance
        self.currency_name = currency_name
        self.currency_icon = currency_icon

        # Dynamic remove select
        if items:
            options = [
                discord.SelectOption(
                    label=item["name"][:100],
                    value=str(item["cart_id"]),
                    description=f"x{item['quantity']} · {item['cost'] * item['quantity'] * item['quality']:,} coins",
                )
                for item in items[:25]
            ]
            sel = discord.ui.Select(placeholder="Remove an item from cart...", options=options, row=0)
            sel.callback = self._remove_item
            self.add_item(sel)

    def build_embed(self) -> discord.Embed:
        total = sum(i["cost"] * i["quantity"] * i["quality"] for i in self.items)
        can_afford = self.balance >= total
        embed = discord.Embed(
            title="🛒 Shopping Cart",
            color=discord.Color.green() if can_afford else discord.Color.red(),
        )
        for item in self.items:
            item_total = item["cost"] * item["quantity"] * item["quality"]
            q_name = QUALITY_NAMES.get(item["quality"], "Primitive")
            bp = " (Blueprint)" if item.get("blueprint") else ""
            embed.add_field(
                name=f"{item['name']}{bp}",
                value=f"x{item['quantity']} · {q_name} · **{item_total:,}** {self.currency_icon}",
                inline=False,
            )
        embed.add_field(name="Total", value=f"**{total:,}** {self.currency_icon}", inline=False)
        status = "✅ Ready to checkout" if can_afford else f"❌ Need {total - self.balance:,} more coins"
        embed.set_footer(text=f"{status} · Balance: {self.balance:,} {self.currency_name}")
        return embed

    async def _remove_item(self, interaction: discord.Interaction):
        cart_id = int(interaction.data["values"][0])
        await shop_db.remove_from_cart(cart_id)
        self.items = await shop_db.get_cart(self.guild_id, self.discord_id)
        if not self.items:
            await interaction.response.edit_message(content="Your cart is now empty.", embed=None, view=None)
        else:
            new_view = CartView(self.guild_id, self.discord_id, self.items, self.balance, self.currency_name, self.currency_icon)
            await interaction.response.edit_message(embed=new_view.build_embed(), view=new_view)

    @discord.ui.button(label="🛒 Checkout", style=discord.ButtonStyle.success, row=1)
    async def checkout(self, interaction: discord.Interaction, button: discord.ui.Button):
        total = sum(i["cost"] * i["quantity"] * i["quality"] for i in self.items)
        if self.balance < total:
            await interaction.response.send_message(
                f"❌ Insufficient funds. Total is **{total:,}** coins but you only have **{self.balance:,}**.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        # Clear the cart view immediately so users can't double-click checkout
        try:
            await interaction.edit_original_response(content="⏳ Processing checkout...", embed=None, view=None)
        except Exception:
            pass
        shop_cog = interaction.client.get_cog("ShopCog")
        if not shop_cog:
            await interaction.followup.send("❌ Shop system unavailable.", ephemeral=True)
            return

        try:
            results = []
            any_queued = False
            for cart_item in self.items:
                full_item = await shop_db.get_store_item(cart_item["item_id"])
                if not full_item:
                    results.append(f"❌ {cart_item['name']}: Item no longer available")
                    continue
                item_cost = full_item["cost"] * cart_item["quantity"] * cart_item["quality"]
                delivered, msg = await shop_cog.process_cart_item(
                    interaction, self.guild_id, self.discord_id,
                    full_item, cart_item["quantity"], cart_item["quality"],
                    bool(cart_item.get("blueprint")), item_cost,
                )
                results.append(msg)
                # Log each item to shop channel
                await shop_cog._log_purchase(
                    self.guild_id, interaction.user, full_item,
                    cart_item["quantity"], cart_item["quality"],
                    bool(cart_item.get("blueprint")), item_cost,
                    None, delivered=delivered,
                )
                if not delivered:
                    any_queued = True

            await shop_db.clear_cart(self.guild_id, self.discord_id)
            summary = "\n".join(results) if results else "No items processed."
            await interaction.followup.send(f"🛒 **Checkout Complete!**\n{summary}", ephemeral=True)

            if any_queued:
                queued_lines = [r for r in results if r.startswith("🕐")]
                if queued_lines:
                    try:
                        dm_embed = discord.Embed(
                            title="🕐 Items Queued for Delivery",
                            description="\n".join(queued_lines),
                            color=discord.Color.yellow(),
                        )
                        dm_embed.set_footer(text="Auto-delivers ~2 min after login")
                        await interaction.user.send(embed=dm_embed)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Checkout failed for guild={self.guild_id} user={self.discord_id}: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Checkout error: {e}", ephemeral=True)
        finally:
            self.stop()

    @discord.ui.button(label="🧹 Clear Cart", style=discord.ButtonStyle.danger, row=1)
    async def clear_cart_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await shop_db.clear_cart(self.guild_id, self.discord_id)
        self.stop()
        await interaction.response.edit_message(content="🧹 Cart cleared.", embed=None, view=None)


# ---------------------------------------------------------------------------
# Admin Modals
# ---------------------------------------------------------------------------

class AddItemModal(Modal, title="➕ Add Store Item"):
    name = TextInput(label="Item Name", max_length=100, required=True)
    cost = TextInput(label="Cost (Phoenix Coins)", placeholder="100", max_length=8, required=True)
    ark_command = TextInput(
        label="Blueprint Path",
        placeholder="Blueprint'/Game/.../PrimalItem_Name.PrimalItem_Name'",
        max_length=500,
        required=True,
        style=discord.TextStyle.short,
    )
    category = TextInput(label="Category", placeholder="ammunition, structures, tek, utility...", max_length=50, required=True)
    supports_quality = TextInput(
        label="Quality Tiers? (yes/no)",
        placeholder="no", default="no", max_length=3, required=False,
    )

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cost = int(self.cost.value.strip())
            if cost <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Cost must be a positive number.", ephemeral=True)
            return

        supports_q = self.supports_quality.value.strip().lower() in ("yes", "y", "true", "1")
        item_id = await shop_db.add_store_item(
            guild_id=self.guild_id,
            name=self.name.value.strip(),
            description="",
            cost=cost,
            ark_command=self.ark_command.value.strip(),
            category=self.category.value.strip(),
            supports_quality=supports_q,
        )
        embed = discord.Embed(
            title="✅ Item Added",
            color=discord.Color.green(),
        )
        embed.add_field(name="Name", value=self.name.value.strip(), inline=True)
        embed.add_field(name="Cost", value=f"{cost:,} coins", inline=True)
        embed.add_field(name="Category", value=self.category.value.strip().lower(), inline=True)
        embed.add_field(name="Item ID", value=f"#{item_id}", inline=True)
        embed.add_field(name="Quality Tiers", value="Yes" if supports_q else "No", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class EditItemModal(Modal, title="✏️ Edit Store Item"):
    name = TextInput(label="Item Name", max_length=100, required=True)
    cost = TextInput(label="Cost (Phoenix Coins)", max_length=8, required=True)
    description = TextInput(
        label="Description", max_length=200, required=False,
        style=discord.TextStyle.short,
    )
    category = TextInput(label="Category", max_length=50, required=True)
    supports_quality = TextInput(
        label="Quality Tiers? (yes/no)", max_length=3, required=False,
    )

    def __init__(self, item: dict):
        super().__init__()
        self.item = item
        self.name.default = item.get("name", "")
        self.cost.default = str(item.get("cost", ""))
        self.description.default = item.get("description") or ""
        self.category.default = item.get("category", "")
        self.supports_quality.default = "yes" if item.get("supports_quality") else "no"

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cost = int(self.cost.value.strip())
            if cost <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Cost must be a positive number.", ephemeral=True)
            return

        supports_q = self.supports_quality.value.strip().lower() in ("yes", "y", "true", "1")
        await shop_db.update_store_item(
            self.item["item_id"],
            name=self.name.value.strip(),
            cost=cost,
            description=self.description.value.strip() or None,
            category=self.category.value.strip().lower(),
            supports_quality=1 if supports_q else 0,
        )
        await interaction.response.send_message(
            f"✅ **{self.name.value.strip()}** updated.", ephemeral=True
        )


# ---------------------------------------------------------------------------
# Shop Cog
# ---------------------------------------------------------------------------

class ShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.delivery_loop.start()

    def cog_unload(self):
        self.delivery_loop.cancel()

    # ------------------------------------------------------------------
    # Delivery helpers
    # ------------------------------------------------------------------

    async def _deliver_pack(self, server_name: str, player_id: int, pack_contents_json: str, guild_id: int = 0) -> bool:
        """Deliver all items in a pack. Returns True only if all items delivered."""
        try:
            pack_items = json.loads(pack_contents_json or "[]")
        except Exception:
            logger.warning(f"Invalid pack_contents JSON for delivery")
            return False

        if not pack_items:
            return False

        results = []
        for pi in pack_items:
            delivered = await self._deliver_item(
                server_name, player_id, pi["ark_command"], pi.get("quantity", 1), 1, False, guild_id=guild_id
            )
            results.append(delivered)

        return all(results)

    async def _deliver_item(
        self, server_name: str, player_id: int, blueprint: str,
        qty: int, quality: int, force_blueprint: bool, guild_id: int = 0
    ) -> bool:
        """Attempt RCON item delivery. Returns True on success."""
        try:
            bp_flag = 1 if force_blueprint else 0
            cmd = f'GiveItemToPlayer {player_id} "{blueprint}" {qty} {quality} {bp_flag}'
            logger.info(f"RCON delivery: [{server_name}] {cmd[:120]}")
            monitor_cog = self.bot.get_cog("ServerMonitor")
            rcon_manager = monitor_cog.guild_rcon_managers.get(guild_id) if monitor_cog else None
            if not rcon_manager:
                logger.warning("Delivery skipped: no RCONManager available")
                return False
            success, response = await rcon_manager.execute_command(server_name, cmd)
            logger.info(f"RCON delivery result: success={success} response={repr(response)}")
            if not success:
                return False
            # If ARK received the command (success=True), treat as delivered.
            # Buffered "Keep Alive" or ListPlayers packets can appear as the response body
            # due to ARK's RCON protocol — they don't mean failure. Only reject on explicit error text.
            resp_lower = (response or "").lower()
            if any(pattern in resp_lower for pattern in DELIVERY_FAILURE_PATTERNS):
                logger.warning(f"RCON delivery rejected — ARK error: {response!r}")
                return False
            return True
        except Exception as e:
            logger.warning(f"Delivery failed for {server_name}/{player_id}: {e}")
            return False

    def _is_player_online_in_cache(self, eos_id: str, server_name: str) -> bool:
        """Return True only if the player's EOS ID appears in the latest RCON scan for this server.
        Prevents delivery attempts against stale last_seen_server data."""
        monitor_cog = self.bot.get_cog("ServerMonitor")
        if not monitor_cog:
            return False
        # guild_server_caches: {guild_id: {server_name: status_dict}}
        for guild_cache in monitor_cog.guild_server_caches.values():
            cache = guild_cache.get(server_name, {})
            if not cache.get("online"):
                continue
            online_eos_ids = {
                p.get("eos_id") for p in cache.get("players", [])
                if isinstance(p, dict) and p.get("eos_id")
            }
            if str(eos_id) in online_eos_ids:
                return True
        return False

    async def try_deliver_for_player(self, eos_id: str, server_name: str):
        """Attempt pending deliveries immediately when a player is detected online.
        Called from ServerMonitor on each player scan. No-op if nothing pending."""
        try:
            player = await players_db.get_player_by_eos_id(eos_id)
            if not player:
                return
            if not player.get("discord_user_id"):
                return
            discord_user_id = player["discord_user_id"]
            player_id = player.get("specimen_id") or player.get("last_player_id")
            if not player_id:
                logger.debug(f"try_deliver: no specimen_id for EOS {eos_id[:12]}, cannot deliver")
                return
            # Do NOT filter by player.guild_id — link_player stores guild_id=0 by default.
            # Get all pending deliveries, filter by discord_user_id, use guild_id from the delivery record.
            all_pending = await shop_db.get_pending_deliveries()
            user_pending = [d for d in all_pending if d["discord_user_id"] == discord_user_id]
            if not user_pending:
                return
            # Guild ID comes from the delivery record (set correctly at purchase time)
            guild_id = user_pending[0]["guild_id"]
            logger.info(f"Instant delivery: {len(user_pending)} item(s) for EOS {eos_id[:12]}... on {server_name}")
            guild = self.bot.get_guild(guild_id)
            member = guild.get_member(discord_user_id) if guild else None
            settings = await economy_db.get_economy_settings(guild_id)
            icon = settings.get("currency_icon", "🪙")
            landed = []
            for delivery in user_pending:
                delivered = await self._deliver_item(
                    server_name, player_id,
                    delivery["item_blueprint"], delivery["quantity"],
                    delivery["quality"], bool(delivery.get("force_blueprint")),
                    guild_id=guild_id,
                )
                if delivered:
                    await shop_db.delete_pending_delivery(delivery["id"])
                    landed.append(delivery)
                    logger.info(f"Instant delivery {delivery['id']} completed for {eos_id[:12]}... on {server_name}")
                    if member:
                        try:
                            dm_embed = discord.Embed(
                                title="✅ Pending delivery arrived!",
                                description=f"Your queued item has been delivered on **{server_name}**.",
                                color=discord.Color.green(),
                            )
                            dm_embed.set_footer(text=f"Server: {server_name} • {icon} Phoenix Shop")
                            await member.send(embed=dm_embed)
                        except Exception:
                            pass
            # One embed for the batch, not one per item: five items arriving at once is a single
            # event to an admin reading the channel, and five embeds is noise that buries it.
            await self._log_delivery(
                guild_id, member, server_name, landed, player.get("character_name")
            )
        except Exception as e:
            logger.error(f"try_deliver_for_player error for {eos_id}: {e}", exc_info=True)

    async def process_purchase(
        self, interaction: discord.Interaction,
        guild_id: int, discord_id: int, item: dict,
        qty: int, quality: int, force_blueprint: bool, total_cost: int,
    ):
        """Deduct coins, attempt delivery, queue if offline. Used for direct buy."""
        player = await players_db.get_player_by_discord_id(guild_id, discord_id)
        if not player:
            await interaction.followup.send("❌ Your ARK account is not linked.", ephemeral=True)
            return

        eos_id = player.get("eos_id")
        # specimen_id is the ARK character implant ID stored at link-time; fallback to last_player_id
        player_id = player.get("specimen_id") or player.get("last_player_id")
        # last_seen_server is updated by server monitor each scan; fall back to last_server column
        server = player.get("last_seen_server") or player.get("last_server")

        success = await players_db.deduct_coins(
            guild_id=guild_id, eos_id=eos_id, amount=total_cost,
            reason=f"Shop: {item['name']} x{qty} ({QUALITY_NAMES.get(quality, 'Primitive')})",
            discord_id=discord_id,
        )
        if not success:
            await interaction.followup.send(
                f"❌ Insufficient funds. You need **{total_cost:,}** coins.", ephemeral=True
            )
            return

        tx_id = await shop_db.record_transaction(
            guild_id=guild_id, discord_id=discord_id, item_id=item["item_id"],
            cost=total_cost, quantity=qty, server_name=server, status="pending",
        )

        settings = await economy_db.get_economy_settings(guild_id)
        icon = settings.get("currency_icon", "🪙")
        quality_name = QUALITY_NAMES.get(quality, "Primitive")
        bp_str = " (Blueprint)" if force_blueprint else ""
        is_pack = bool(item.get("is_pack"))

        delivered = False
        # Only attempt immediate delivery if player is confirmed online in the current RCON scan.
        # Using stale last_seen_server (player just logged out) causes false delivery and "back online" glitches.
        if player_id and server and eos_id and self._is_player_online_in_cache(eos_id, server):
            if is_pack:
                delivered = await self._deliver_pack(server, player_id, item.get("pack_contents", "[]"), guild_id=guild_id)
            else:
                delivered = await self._deliver_item(
                    server, player_id, item["ark_command"], qty, quality, force_blueprint, guild_id=guild_id
                )

        if delivered:
            await shop_db.update_transaction_status(tx_id, "completed")
            desc = (
                f"**{item['name']}** delivered to **{server}**!"
                if is_pack
                else f"**{item['name']}{bp_str}** x{qty} ({quality_name}) delivered to **{server}**!"
            )
            embed = discord.Embed(title="✅ Purchase Successful!", description=desc, color=discord.Color.green())
            embed.set_footer(text=f"Spent: {total_cost:,} {icon}")
            await interaction.followup.send(embed=embed, ephemeral=True)
            await self._log_purchase(guild_id, interaction.user, item, qty, quality, force_blueprint, total_cost, server, delivered=True)
        else:
            if is_pack:
                # Queue each pack item as a separate pending delivery
                try:
                    pack_items = json.loads(item.get("pack_contents") or "[]")
                    for pi in pack_items:
                        await shop_db.add_pending_delivery(
                            guild_id=guild_id, discord_user_id=discord_id, eos_id=eos_id,
                            server_name=server or "unknown", item_blueprint=pi["ark_command"],
                            quantity=pi.get("quantity", 1), quality=1, force_blueprint=False,
                        )
                except Exception as e:
                    logger.warning(f"Failed to queue pack deliveries for {item['name']}: {e}")
                desc = (
                    f"**{item['name']}** purchased!\n"
                    f"All items will be delivered next time you're online on an ARK server."
                )
            else:
                await shop_db.add_pending_delivery(
                    guild_id=guild_id, discord_user_id=discord_id, eos_id=eos_id,
                    server_name=server or "unknown", item_blueprint=item["ark_command"],
                    quantity=qty, quality=quality, force_blueprint=force_blueprint,
                )
                desc = (
                    f"**{item['name']}{bp_str}** x{qty} ({quality_name}) purchased!\n"
                    f"It will be delivered next time you're online on an ARK server."
                )
            embed = discord.Embed(title="🕐 Purchase Queued", description=desc, color=discord.Color.yellow())
            embed.set_footer(text=f"Spent: {total_cost:,} {icon} • Auto-delivers on login")
            await interaction.followup.send(embed=embed, ephemeral=True)
            try:
                dm_embed = discord.Embed(title="🕐 Purchase Queued for Delivery", description=desc, color=discord.Color.yellow())
                dm_embed.set_footer(text=f"Spent: {total_cost:,} {icon} • Auto-delivers ~2 min after login")
                await interaction.user.send(embed=dm_embed)
            except Exception:
                pass
            await self._log_purchase(guild_id, interaction.user, item, qty, quality, force_blueprint, total_cost, server, delivered=False)

    async def process_cart_item(
        self, interaction: discord.Interaction,
        guild_id: int, discord_id: int, item: dict,
        qty: int, quality: int, force_blueprint: bool, total_cost: int,
    ) -> tuple[bool, str]:
        """Process one cart item during checkout. Returns (delivered, message)."""
        player = await players_db.get_player_by_discord_id(guild_id, discord_id)
        if not player:
            return False, f"❌ {item['name']}: Account not linked"

        eos_id = player.get("eos_id")
        player_id = player.get("specimen_id") or player.get("last_player_id")
        server = player.get("last_seen_server") or player.get("last_server")

        success = await players_db.deduct_coins(
            guild_id=guild_id, eos_id=eos_id, amount=total_cost,
            reason=f"Shop: {item['name']} x{qty}",
            discord_id=discord_id,
        )
        if not success:
            return False, f"❌ {item['name']}: Insufficient funds"

        await shop_db.record_transaction(
            guild_id=guild_id, discord_id=discord_id, item_id=item["item_id"],
            cost=total_cost, quantity=qty, server_name=server, status="pending",
        )

        is_pack = bool(item.get("is_pack"))
        delivered = False
        # Only attempt immediate delivery if player is confirmed online in the current RCON scan.
        if player_id and server and eos_id and self._is_player_online_in_cache(eos_id, server):
            if is_pack:
                delivered = await self._deliver_pack(server, player_id, item.get("pack_contents", "[]"), guild_id=guild_id)
            else:
                delivered = await self._deliver_item(server, player_id, item["ark_command"], qty, quality, force_blueprint, guild_id=guild_id)

        quality_name = QUALITY_NAMES.get(quality, "Primitive")
        bp_str = " (Blueprint)" if force_blueprint else ""
        settings = await economy_db.get_economy_settings(guild_id)
        icon = settings.get("currency_icon", "🪙")
        if delivered:
            msg = f"✅ {item['name']} — delivered to {server}" if is_pack else f"✅ {item['name']}{bp_str} x{qty} ({quality_name}) — delivered to {server} • Spent: {total_cost:,} {icon}"
            return True, msg
        else:
            if is_pack:
                try:
                    pack_items = json.loads(item.get("pack_contents") or "[]")
                    for pi in pack_items:
                        await shop_db.add_pending_delivery(
                            guild_id=guild_id, discord_user_id=discord_id, eos_id=eos_id,
                            server_name=server or "unknown", item_blueprint=pi["ark_command"],
                            quantity=pi.get("quantity", 1), quality=1, force_blueprint=False,
                        )
                except Exception as e:
                    logger.warning(f"Failed to queue pack cart deliveries: {e}")
                return False, f"🕐 {item['name']} (pack) — queued • Spent: {total_cost:,} {icon}"
            else:
                await shop_db.add_pending_delivery(
                    guild_id=guild_id, discord_user_id=discord_id, eos_id=eos_id,
                    server_name=server or "unknown", item_blueprint=item["ark_command"],
                    quantity=qty, quality=quality, force_blueprint=force_blueprint,
                )
                bp_str = " (Blueprint)" if force_blueprint else ""
                return False, f"🕐 {item['name']}{bp_str} x{qty} ({quality_name}) — queued • Spent: {total_cost:,} {icon}"

    async def _log_purchase(
        self, guild_id: int, user: discord.Member, item: dict,
        qty: int, quality: int, force_blueprint: bool, cost: int, server: str,
        *, delivered: bool = True,
    ):
        """Post purchase log to configured shop log channel for all purchases."""
        try:
            config = await shop_db.get_shop_config(guild_id)
            log_channel_id = config.get("log_channel_id")
            if not log_channel_id:
                return
            channel = self.bot.get_channel(int(log_channel_id))
            if not channel:
                return
            quality_name = QUALITY_NAMES.get(quality, "Primitive")
            bp_str = " (Blueprint)" if force_blueprint else ""
            settings = await economy_db.get_economy_settings(guild_id)
            icon = settings.get("currency_icon", "🪙")
            is_pack = bool(item.get("is_pack"))

            if delivered:
                status_icon = "✅"
                status_text = f"on **{server}**" if server else "in-game"
                color = discord.Color.green()
            else:
                status_icon = "🕐"
                status_text = "queued for delivery"
                color = discord.Color.yellow()

            if is_pack:
                desc = f"{status_icon} **{user.mention}** bought pack **{item['name']}** for **{cost:,}** {icon} — {status_text}"
            else:
                desc = f"{status_icon} **{user.mention}** bought **{item['name']}{bp_str}** x{qty} ({quality_name}) for **{cost:,}** {icon} — {status_text}"

            embed = discord.Embed(description=desc, color=color)
            await channel.send(embed=embed)
        except Exception as e:
            logger.warning(f"Failed to log purchase: {e}")

    async def _log_delivery(
        self, guild_id: int, member, server_name: str,
        deliveries: list, character_name: str | None = None,
    ):
        """Post 'it arrived' to the same shop log channel the purchase went to.

        Carl, 2026-08-12: "give me some logging in the same shop log channel telling me the stuff
        showed up on their doorstep."

        The gap this closes: a purchase that could not be delivered immediately logged
        "🕐 queued for delivery" and then NOTHING, ever. Both delivery paths DM'd the player and
        wrote to journald, but neither posted to the log channel — so from the admin's side a
        queued purchase and a lost one looked identical. That is exactly how Deez_Knutz721's five
        items sat unnoticed for two days.

        ON THE WORD "DELIVERED", because it is doing real work here. ARK's RCON answers
        `GiveItemToPlayer` with 'Server received, But no response!!' whether the item landed or
        not — this file's own delivery_loop comment says it plainly: "ARK's GiveItemToPlayer
        silently drops items for offline players but returns success". So the strongest honest
        claim is not "the item is in their inventory", it is:

            the player was confirmed present in the live RCON player scan for that server
            (_is_player_online_in_cache) at the moment the command was accepted

        which IS the doorstep test — it is the check that stops us handing items to an empty
        server. The footer says so, so nobody reads this embed as proof of receipt and the next
        person to debug a "missing item" knows exactly how much this line is worth.
        """
        try:
            if not deliveries:
                return
            config = await shop_db.get_shop_config(guild_id)
            log_channel_id = config.get("log_channel_id")
            if not log_channel_id:
                return
            channel = self.bot.get_channel(int(log_channel_id))
            if not channel:
                return

            lines = []
            for d in deliveries:
                blueprint = d.get("item_blueprint") or ""
                name = await shop_db.get_item_name_by_command(guild_id, blueprint)
                if not name:
                    # Renamed or removed from the shop since purchase — still log it, using the
                    # tail of the blueprint, which is the readable part.
                    tail = blueprint.rstrip("'").split(".")[-1] or blueprint
                    name = f"`{tail[:60]}`"
                qty = d.get("quantity", 1)
                quality_name = QUALITY_NAMES.get(d.get("quality", 1), "Primitive")
                lines.append(f"• **{name}** ×{qty} ({quality_name})")

            who = member.mention if member else "an unlinked player"
            as_char = f" (**{character_name}**)" if character_name else ""
            noun = "item" if len(deliveries) == 1 else "items"
            embed = discord.Embed(
                title="📦 Delivered",
                description=(
                    f"**{len(deliveries)}** queued {noun} handed to {who}{as_char} "
                    f"on **{server_name}**\n\n" + "\n".join(lines[:15])
                ),
                color=discord.Color.green(),
            )
            if len(lines) > 15:
                embed.add_field(name="…", value=f"and {len(lines) - 15} more", inline=False)
            embed.set_footer(
                text=f"{server_name} • player confirmed online at delivery • "
                     "ARK does not acknowledge item receipt"
            )
            await channel.send(embed=embed)
        except Exception as e:
            # Never let logging break a delivery that already succeeded.
            logger.warning(f"Failed to log delivery: {e}")

    # ------------------------------------------------------------------
    # Pending Delivery Loop
    # ------------------------------------------------------------------

    @tasks.loop(minutes=5)
    async def delivery_loop(self):
        """Retry pending deliveries for all guilds."""
        for guild in self.bot.guilds:
            try:
                pending = await shop_db.get_pending_deliveries(guild_id=guild.id)
                # Collected per (member, server) so the log is one "📦 Delivered" per player per
                # sweep rather than one per item — same reason as the instant path.
                landed_by_player: dict = {}
                for delivery in pending:
                    player = await players_db.get_player_by_discord_id(guild.id, delivery["discord_user_id"])
                    if not player:
                        continue
                    # specimen_id is the ARK character implant ID set at link-time
                    player_id = player.get("specimen_id") or player.get("last_player_id")
                    if not player_id:
                        continue
                    # Use player's current server (updated each monitor scan), fallback to stored
                    server_name = player.get("last_seen_server") or player.get("last_server") or delivery["server_name"]
                    if not server_name or server_name == "unknown":
                        continue
                    # Only deliver if player is confirmed online in the current RCON scan.
                    # ARK's GiveItemToPlayer silently drops items for offline players but
                    # returns success — without this check the delivery fires, the queue
                    # record is deleted, and the player never receives their item.
                    eos_id = player.get("eos_id")
                    if not eos_id or not self._is_player_online_in_cache(eos_id, server_name):
                        continue
                    delivered = await self._deliver_item(
                        server_name,
                        player_id,
                        delivery["item_blueprint"],
                        delivery["quantity"],
                        delivery["quality"],
                        bool(delivery.get("force_blueprint")),
                        guild_id=guild.id,
                    )
                    if delivered:
                        await shop_db.delete_pending_delivery(delivery["id"])
                        member = guild.get_member(delivery["discord_user_id"])
                        landed_by_player.setdefault(
                            (delivery["discord_user_id"], server_name),
                            {"member": member, "items": [],
                             "character": player.get("character_name")},
                        )["items"].append(delivery)
                        if member:
                            try:
                                settings = await economy_db.get_economy_settings(guild.id)
                                icon = settings.get("currency_icon", "🪙")
                                dm_embed = discord.Embed(
                                    title="✅ Pending delivery arrived!",
                                    description=f"Your queued item has been delivered to you on **{server_name}**.",
                                    color=discord.Color.green(),
                                )
                                dm_embed.set_footer(text=f"Server: {server_name} • {icon} Phoenix Shop")
                                await member.send(embed=dm_embed)
                            except Exception:
                                pass
                        logger.info(f"Pending delivery {delivery['id']} completed for {delivery.get('eos_id')} on {server_name}")
                for (_uid, srv), batch in landed_by_player.items():
                    await self._log_delivery(
                        guild.id, batch["member"], srv, batch["items"], batch["character"]
                    )
            except Exception as e:
                logger.error(f"Delivery loop error for guild {guild.id}: {e}")

    @delivery_loop.before_loop
    async def before_delivery_loop(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Player Commands
    # ------------------------------------------------------------------

    @app_commands.command(name="shop", description="Browse the Phoenix ARK shop.")
    async def shop(self, interaction: discord.Interaction):
        if not await check_feature(interaction, "shop"):
            return
        
        config = await shop_db.get_shop_config(interaction.guild_id)
        if not config.get("shop_enabled", 1):
            await interaction.response.send_message("🔒 The shop is currently closed.", ephemeral=True)
            return

        balance, eos_id = await players_db.get_balance_by_discord_id(interaction.guild_id, interaction.user.id)
        if eos_id is None:
            await interaction.response.send_message(
                "❌ You need a linked ARK account to use the shop. Use `/player` to link.", ephemeral=True
            )
            return

        settings = await economy_db.get_economy_settings(interaction.guild_id)
        currency_name = settings.get("currency_name", "Phoenix Coins")
        currency_icon = settings.get("currency_icon", "🪙")

        view = ShopView(interaction.guild_id, interaction.user.id, balance, currency_name, currency_icon)
        # Pre-load categories to check if shop has items
        categories = await shop_db.get_categories(interaction.guild_id)
        if not categories:
            await interaction.response.send_message(
                "🛒 **The shop has no items yet.**\n\n"
                "Please notify your Discord admin to configure the shop.\n\n"
                "**Admins:** Use `/shopcfg` to add items, or:\n"
                "1. `/downloadsample` - Download the shop template\n"
                "2. Edit the CSV file with your items\n"
                "3. `/uploadshop` - Upload your configured shop",
                ephemeral=True
            )
            return
        view.all_categories = categories
        await view.show_home(interaction, first_load=True)

    @app_commands.command(name="buy", description="Quickly find and purchase a shop item by name.")
    @app_commands.describe(item="Type to search items — select from the dropdown")
    async def buy_cmd(self, interaction: discord.Interaction, item: str):
        if not await check_feature(interaction, "shop"):
            return
        
        balance, eos_id = await players_db.get_balance_by_discord_id(interaction.guild_id, interaction.user.id)
        if eos_id is None:
            await interaction.response.send_message(
                "❌ You need a linked ARK account to use the shop. Use `/player` to link.", ephemeral=True
            )
            return

        try:
            item_id = int(item)
        except ValueError:
            await interaction.response.send_message("❌ Invalid item selection.", ephemeral=True)
            return

        item_obj = await shop_db.get_store_item(item_id)
        if not item_obj or item_obj.get("guild_id") != interaction.guild_id or not item_obj.get("enabled"):
            await interaction.response.send_message("❌ Item not found or unavailable.", ephemeral=True)
            return

        settings = await economy_db.get_economy_settings(interaction.guild_id)
        currency_name = settings.get("currency_name", "Phoenix Coins")
        currency_icon = settings.get("currency_icon", "🪙")

        sv = ShopView(interaction.guild_id, interaction.user.id, balance, currency_name, currency_icon)
        sv.selected_item = item_obj
        await interaction.response.send_modal(PurchaseModal(sv))

    @buy_cmd.autocomplete("item")
    async def buy_autocomplete(self, interaction: discord.Interaction, current: str):
        items = await shop_db.search_store_items(interaction.guild_id, current)
        return [
            app_commands.Choice(
                name=f"{i['name']} — {i['cost']:,} coins"[:100],
                value=str(i["item_id"]),
            )
            for i in items
        ]

    # ------------------------------------------------------------------
    # Bulk Import / Export Commands
    # Note: All shop administration is now handled by /shopcfg GUI
    # ------------------------------------------------------------------

    @app_commands.command(name="uploadshop", description="Upload shop items from an Excel (.xlsx) or CSV file.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        file="Excel (.xlsx) or CSV (.csv) file containing shop items",
        mode="Replace all existing items (default) or append without clearing",
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Replace — clear all existing items first", value="replace"),
        app_commands.Choice(name="Append — add items without clearing existing", value="append"),
    ])
    async def uploadshop(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        mode: str = "replace",
    ):
        await interaction.response.defer(ephemeral=True)
        if not await check_feature(interaction, "shop"):
            return

        filename = file.filename.lower()
        if not (filename.endswith(".xlsx") or filename.endswith(".csv")):
            await interaction.followup.send("❌ Only `.xlsx` or `.csv` files are supported.", ephemeral=True)
            return

        if file.size > 25 * 1024 * 1024:
            await interaction.followup.send("❌ File too large (max 25 MB).", ephemeral=True)
            return

        data = await file.read()

        if filename.endswith(".xlsx"):
            items, parse_errors = _parse_xlsx_shop(data)
        else:
            items, parse_errors = _parse_csv_shop(data)

        if not items and parse_errors:
            err_text = "\n".join(parse_errors[:10])
            await interaction.followup.send(
                f"❌ Import failed — no valid items found.\n```\n{err_text}\n```",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild_id

        if mode == "replace":
            await shop_db.clear_all_store_items(guild_id)

        inserted, insert_errors = await shop_db.bulk_add_store_items(guild_id, items)

        all_errors = parse_errors + insert_errors
        color = discord.Color.green() if not all_errors else discord.Color.yellow()
        title = "✅ Shop Import Complete" if not all_errors else "⚠️ Shop Import Finished with Warnings"

        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="File", value=file.filename, inline=True)
        embed.add_field(name="Mode", value=mode.title(), inline=True)
        embed.add_field(name="Items Imported", value=f"**{inserted:,}**", inline=True)

        skipped = len(items) - inserted
        if skipped > 0:
            embed.add_field(name="Skipped", value=str(skipped), inline=True)

        if all_errors:
            shown = all_errors[:8]
            more = len(all_errors) - len(shown)
            err_text = "\n".join(shown)
            if more > 0:
                err_text += f"\n… and {more} more"
            embed.add_field(name=f"⚠️ {len(all_errors)} Warning(s)", value=f"```\n{err_text}\n```", inline=False)

        # Summary breakdown
        regular = [it for it in items if not it.get("is_pack")]
        packs = [it for it in items if it.get("is_pack")]
        if packs:
            embed.add_field(name="📦 Packs", value=str(len(packs)), inline=True)
        embed.add_field(name="🛍️ Items", value=str(len(regular)), inline=True)

        # Category breakdown (regular items only)
        cats: dict[str, int] = {}
        for item in regular:
            cats[item["category"].title()] = cats.get(item["category"].title(), 0) + 1
        if cats:
            cat_lines = "\n".join(f"**{cat}**: {cnt}" for cat, cnt in sorted(cats.items())[:12])
            if len(cats) > 12:
                cat_lines += f"\n… and {len(cats) - 12} more categories"
            embed.add_field(name=f"Categories ({len(cats)})", value=cat_lines, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="downloadshop", description="Download all shop items as an Excel file.")
    @app_commands.checks.has_permissions(administrator=True)
    async def downloadshop(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await check_feature(interaction, "shop"):
            return

        items = await shop_db.get_store_items(interaction.guild_id, enabled_only=False)
        if not items:
            await interaction.followup.send("❌ No shop items to export.", ephemeral=True)
            return

        data = _build_shop_xlsx(items)

        embed = discord.Embed(
            title="📥 Shop Export",
            description=f"Exported **{len(items):,}** items.",
            color=discord.Color.blue(),
        )

        await interaction.followup.send(
            embed=embed,
            file=discord.File(io.BytesIO(data), filename="shop_items.xlsx"),
            ephemeral=True,
        )

    @app_commands.command(name="downloadsample", description="Download a blank shop template showing the required import format.")
    @app_commands.checks.has_permissions(administrator=True)
    async def downloadsample(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await check_feature(interaction, "shop"):
            return

        # Try to read from templates directory first
        template_path = Path(Config.DATABASE_PATH).parent / "templates" / "PhoenixShop_Template.xlsx"
        
        if template_path.exists():
            # Use the actual template file
            data = template_path.read_bytes()
            filename = "PhoenixShop_Template.xlsx"
            logger.info(f"Using template from {template_path}")
        else:
            # Fall back to generated sample
            data = _build_sample_xlsx()
            filename = "shop_template.xlsx"
            logger.info("Template file not found, using generated sample")

        embed = discord.Embed(
            title="📋 Shop Import Template",
            description=(
                "This template shows the format required for `/uploadshop`.\n\n"
                "**Required columns:**\n"
                "• `Item Name` — display name shown in the shop\n"
                "• `Price Per Item` — positive integer\n"
                "• `Blueprint Path` — full `Blueprint'...'` path as used in RCON\n"
                "• `Category` — e.g. weapons, ammo, armor, resources\n\n"
                "**Optional columns:**\n"
                "• `Allow Quality Select` — yes/no, enables quality multipliers\n"
                "• `Description` — short description shown in item detail\n"
                "• `Enabled` — yes/no (disabled rows are skipped)\n\n"
                "**Notes:**\n"
                "• Blueprint paths stored **exactly as provided** — no `_C` suffix added\n"
                "• Outer double-quotes are stripped automatically\n"
                "• Any unrecognised columns (e.g. `Allow Blueprint Select`) are ignored\n\n"
                "**Packs sheet:** Add a `Packs` tab with columns `Pack Name, Price, Category, Description, Items, Enabled` "
                "where `Items` is a comma-separated list of item names from the items sheet."
            ),
            color=discord.Color.blue(),
        )

        await interaction.followup.send(
            embed=embed,
            file=discord.File(io.BytesIO(data), filename=filename),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(ShopCog(bot))
