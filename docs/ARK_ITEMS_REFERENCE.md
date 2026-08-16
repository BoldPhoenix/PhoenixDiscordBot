# ARK Item Reference for Store Setup

This document provides commonly used ARK item IDs and commands for setting up your Phoenix Store.

## Command Format

```
GiveItemNumToPlayer {player_id} <ItemID> <Quantity> <Quality> <ForceBlueprint>
```

- `{player_id}` - Placeholder (bot replaces automatically)
- `<ItemID>` - Item's numerical ID
- `<Quantity>` - Number of items
- `<Quality>` - Item quality (0-100, 0 = default)
- `<ForceBlueprint>` - true/false (true for blueprint)

## Popular Store Items

### 🔫 Ammunition

| Item | ID | Sample Command | Suggested Cost |
|------|----|--------------|----|
| Simple Rifle Ammo (100) | 238 | `GiveItemNumToPlayer {player_id} 238 100 0 false` | 25 🪙 |
| Advanced Rifle Bullet (100) | 246 | `GiveItemNumToPlayer {player_id} 246 100 0 false` | 50 🪙 |
| Shotgun Shells (50) | 240 | `GiveItemNumToPlayer {player_id} 240 50 0 false` | 30 🪙 |
| Tranq Darts (50) | 244 | `GiveItemNumToPlayer {player_id} 244 50 0 false` | 75 🪙 |
| Rocket Propelled Grenade | 253 | `GiveItemNumToPlayer {player_id} 253 5 0 false` | 100 🪙 |

### 🏗️ Structures

| Item | ID | Sample Command | Suggested Cost |
|------|----|--------------|----|
| Metal Foundation | 379 | `GiveItemNumToPlayer {player_id} 379 1 0 false` | 25 🪙 |
| Metal Wall | 380 | `GiveItemNumToPlayer {player_id} 380 1 0 false` | 20 🪙 |
| Metal Ceiling | 381 | `GiveItemNumToPlayer {player_id} 381 1 0 false` | 20 🪙 |
| Metal Door Frame | 383 | `GiveItemNumToPlayer {player_id} 383 1 0 false` | 15 🪙 |
| Metal Behemoth Gateway | 391 | `GiveItemNumToPlayer {player_id} 391 1 0 false` | 50 🪙 |

### ⚙️ Crafting Stations

| Item | ID | Sample Command | Suggested Cost |
|------|----|--------------|----|
| Mortar and Pestle | 189 | `GiveItemNumToPlayer {player_id} 189 1 0 false` | 10 🪙 |
| Smithy | 194 | `GiveItemNumToPlayer {player_id} 194 1 0 false` | 25 🪙 |
| Fabricator | 237 | `GiveItemNumToPlayer {player_id} 237 1 0 false` | 75 🪙 |
| Industrial Forge | 238 | `GiveItemNumToPlayer {player_id} 238 1 0 false` | 100 🪙 |
| Chemistry Bench | 328 | `GiveItemNumToPlayer {player_id} 328 1 0 false` | 50 🪙 |

### 🦖 Taming & Breeding

| Item | ID | Sample Command | Suggested Cost |
|------|----|--------------|----|
| Cryopod | 1 | `GiveItemNumToPlayer {player_id} 1 1 0 false` | 75 🪙 |
| Soul Ball | 2 | `GiveItemNumToPlayer {player_id} 2 1 0 false` | 100 🪙 |
| Kibble (Superior) | 3 | `GiveItemNumToPlayer {player_id} 3 50 0 false` | 150 🪙 |
| Mutagen | 4 | `GiveItemNumToPlayer {player_id} 4 10 0 false` | 200 🪙 |

### 💎 Resources

| Item | ID | Sample Command | Suggested Cost |
|------|----|--------------|----|
| Metal Ingot (100) | 151 | `GiveItemNumToPlayer {player_id} 151 100 0 false` | 20 🪙 |
| Polymer (100) | 178 | `GiveItemNumToPlayer {player_id} 178 100 0 false` | 30 🪙 |
| Crystal (100) | 157 | `GiveItemNumToPlayer {player_id} 157 100 0 false` | 25 🪙 |
| Element | 462 | `GiveItemNumToPlayer {player_id} 462 10 0 false` | 500 🪙 |
| Element Dust (100) | 463 | `GiveItemNumToPlayer {player_id} 463 100 0 false` | 100 🪙 |

### 🛡️ Armor Sets

| Item | ID | Sample Command | Suggested Cost |
|------|----|--------------|----|
| Flak Helmet | 293 | `GiveItemNumToPlayer {player_id} 293 1 0 false` | 15 🪙 |
| Flak Chestpiece | 294 | `GiveItemNumToPlayer {player_id} 294 1 0 false` | 25 🪙 |
| Flak Leggings | 295 | `GiveItemNumToPlayer {player_id} 295 1 0 false` | 20 🪙 |
| Flak Gauntlets | 296 | `GiveItemNumToPlayer {player_id} 296 1 0 false` | 15 🪙 |
| Flak Boots | 297 | `GiveItemNumToPlayer {player_id} 297 1 0 false` | 15 🪙 |

### 🔮 Tek Items

| Item | ID | Sample Command | Suggested Cost |
|------|----|--------------|----|
| Tek Generator | 462 | `GiveItemNumToPlayer {player_id} 462 1 0 false` | 250 🪙 |
| Tek Replicator | 465 | `GiveItemNumToPlayer {player_id} 465 1 0 false` | 300 🪙 |
| Tek Transmitter | 466 | `GiveItemNumToPlayer {player_id} 466 1 0 false` | 200 🪙 |
| Tek Sleeping Pod | 467 | `GiveItemNumToPlayer {player_id} 467 1 0 false` | 150 🪙 |
| Tek Teleporter | 468 | `GiveItemNumToPlayer {player_id} 468 1 0 false` | 400 🪙 |

### 🍖 Consumables

| Item | ID | Sample Command | Suggested Cost |
|------|----|--------------|----|
| Cooked Meat (50) | 142 | `GiveItemNumToPlayer {player_id} 142 50 0 false` | 5 🪙 |
| Medical Brew (10) | 205 | `GiveItemNumToPlayer {player_id} 205 10 0 false` | 20 🪙 |
| Energy Brew (10) | 206 | `GiveItemNumToPlayer {player_id} 206 10 0 false` | 20 🪙 |
| Focal Chili (5) | 207 | `GiveItemNumToPlayer {player_id} 207 5 0 false` | 25 🪙 |
| Lazarus Chowder (5) | 208 | `GiveItemNumToPlayer {player_id} 208 5 0 false` | 25 🪙 |

### 🎒 Utility Items

| Item | ID | Sample Command | Suggested Cost |
|------|----|--------------|----|
| Parachute | 301 | `GiveItemNumToPlayer {player_id} 301 1 0 false` | 10 🪙 |
| GPS | 302 | `GiveItemNumToPlayer {player_id} 302 1 0 false` | 50 🪙 |
| Spy Glass | 303 | `GiveItemNumToPlayer {player_id} 303 1 0 false` | 25 🪙 |
| Flashlight Attachment | 304 | `GiveItemNumToPlayer {player_id} 304 1 0 false` | 15 🪙 |
| Climbing Pick | 305 | `GiveItemNumToPlayer {player_id} 305 1 0 false` | 20 🪙 |

## Adding Items to Your Store

### Using Discord Commands:

```
/additem
  name: Advanced Rifle Bullet (100)
  cost: 50
  ark_command: GiveItemNumToPlayer {player_id} 246 100 0 false
  description: 100 Advanced Rifle Bullets for your weapons
  category: ammunition
```

### Via Python Script:

```python
python -m bot.database.init_db
```

This runs the sample items setup.

## Categories

Organize your store with these categories:
- `ammunition` - Bullets, arrows, rockets
- `structures` - Building pieces
- `crafting` - Workbenches and stations
- `resources` - Ingots, polymer, element
- `armor` - Armor sets and pieces
- `weapons` - Guns, tools, melee
- `tek` - Tek tier items
- `consumables` - Food, drinks, medicine
- `utility` - Tools and gadgets
- `taming` - Kibble, cryopods, soul balls

## Important Notes

### Item IDs
- Item IDs may vary between ARK versions
- These are for **ARK: Survival Ascended**
- Test items on a test server first
- Some items may be map-specific

### Quality Values
- `0` = Default quality
- `1-100` = Higher quality (better stats)
- Example for mastercraft: `50`
- Example for ascendant: `80-100`

### Blueprints
- Set last parameter to `true` for blueprint
- Blueprints let players craft the item
- Example: `GiveItemNumToPlayer {player_id} 246 1 0 true`

### Finding Item IDs

Use this in-game command:
```
GiveItem "Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/ItemName.ItemName'" 1 0 false
```

Or check online resources:
- ARK Wiki
- ARK DevKit
- Community databases

## Pricing Strategy

### Tier 1 (Basic) - 5-25 🪙
- Common consumables
- Basic resources
- Low-tier structures

### Tier 2 (Intermediate) - 30-75 🪙
- Advanced ammunition
- Metal structures
- Quality tools

### Tier 3 (Advanced) - 100-200 🪙
- Rare resources
- Crafting stations
- Utility items

### Tier 4 (Tek/Premium) - 250-500+ 🪙
- Tek items
- Element
- High-value resources

## Example Store Setup

```bash
# Starter Pack - 100 🪙
/additem name:"Starter Pack" cost:100 ark_command:"GiveItemNumToPlayer {player_id} 238 200 0 false" description:"200 Simple Rifle Ammo, 50 Cooked Meat" category:utility

# Builder Pack - 250 🪙
/additem name:"Builder Pack" cost:250 ark_command:"GiveItemNumToPlayer {player_id} 379 50 0 false" description:"50 Metal Foundations" category:structures

# Tek Starter - 500 🪙
/additem name:"Tek Generator" cost:500 ark_command:"GiveItemNumToPlayer {player_id} 462 1 0 false" description:"One Tek Generator" category:tek
```

## Tips

1. **Test First**: Always test new items on a test server
2. **Balance Prices**: Keep economy balanced with in-game difficulty
3. **Popular Items**: Stock frequently requested items
4. **Seasonal Sales**: Adjust prices for events
5. **Bundles**: Create item bundles for better value
6. **Limits**: Use purchase limits for rare items

---

Need help finding specific item IDs? Check the ARK Wiki or ask in the Discord!
