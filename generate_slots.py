"""
Generate slot machine symbol images and cabinet overlay.
Creates: 10 symbols + cabinet overlay for slots game.
"""

import os
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = "slot_images"
SYMBOL_SIZE = 150
NUM_SYMBOLS = 10

# ARK-themed slot symbols
SYMBOLS = [
    ("dino", "🦖"),    # Dinosaur
    ("egg", "🥚"),     # Egg
    ("meat", "🥩"),    # Meat
    ("berry", "🫐"),   # Berry
    ("diamond", "💎"),  # Diamond
    ("fire", "🔥"),    # Fire
    ("coin", "🪙"),    # Coin
    ("star", "⭐"),    # Star
    ("skull", "💀"),  # Skull
    ("heart", "❤️"),   # Heart
]

def create_symbol(name, emoji, size=SYMBOL_SIZE):
    """Create a single slot symbol image."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw rounded rectangle background
    margin = 5
    draw.rounded_rectangle(
        [margin, margin, size-margin, size-margin],
        radius=15,
        fill=(40, 40, 60),
        outline=(255, 215, 0),
        width=3
    )
    
    # Draw emoji in center
    try:
        font_size = size // 2
        font = ImageFont.truetype("seguisym.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    # Center the emoji
    bbox = draw.textbbox((0, 0), emoji, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (size - text_width) // 2 - bbox[0]
    y = (size - text_height) // 2 - bbox[1]
    
    draw.text((x, y), emoji, font=font)
    
    return img

def create_cabinet_overlay(width, height):
    """Create a slot machine cabinet overlay with transparency in the middle."""
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw cabinet frame
    frame_color = (80, 40, 20)  # Brown wood
    gold = (255, 215, 0)
    
    # Top bar
    draw.rectangle([0, 0, width, 30], fill=frame_color, outline=gold, width=2)
    # Bottom bar
    draw.rectangle([0, height-40, width, height], fill=frame_color, outline=gold, width=2)
    # Left side
    draw.rectangle([0, 0, 20, height], fill=frame_color, outline=gold, width=2)
    # Right side
    draw.rectangle([width-20, 0, width, height], fill=frame_color, outline=gold, width=2)
    
    # "PHOENIX CASINO" text at top
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except:
        font = ImageFont.load_default()
    
    text = "PHOENIX SLOTS"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (width - text_width) // 2
    draw.text((x, 5), text, fill=gold, font=font)
    
    return img

def create_blur_effect(symbol_img):
    """Create a blurred version of a symbol for spin effect."""
    from PIL import ImageFilter
    return symbol_img.filter(ImageFilter.GaussianBlur(radius=3))

def create_win_banner(width, height):
    """Create a WINNER banner overlay."""
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Semi-transparent background
    draw.rectangle([0, height//2 - 25, width, height//2 + 25], fill=(255, 215, 0, 200))
    
    # WINNER text
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except:
        font = ImageFont.load_default()
    
    text = "WINNER!"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (width - text_width) // 2
    draw.text((x, height//2 - 15), text, fill=(255, 0, 0), font=font)
    
    return img

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Create symbols
    for name, emoji in SYMBOLS:
        img = create_symbol(name, emoji)
        filename = f"{name}.png"
        img.save(os.path.join(OUTPUT_DIR, filename))
        print(f"Created {filename}")
    
    # Create cabinet overlay
    cabinet = create_cabinet_overlay(SYMBOL_SIZE * 3 + 40, SYMBOL_SIZE + 70)
    cabinet.save(os.path.join(OUTPUT_DIR, "cabinet.png"))
    print("Created cabinet.png")
    
    # Create win banner
    banner = create_win_banner(SYMBOL_SIZE * 3 + 40, SYMBOL_SIZE + 70)
    banner.save(os.path.join(OUTPUT_DIR, "winner_banner.png"))
    print("Created winner_banner.png")
    
    print(f"\nDone! Created {len(SYMBOLS) + 2} images in {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()
