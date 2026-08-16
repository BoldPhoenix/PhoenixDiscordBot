"""
Generate simple playing card images for Dino Jack game.
Creates 52 cards + card back, sized at 64x96 pixels.
"""

import os
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = "card_images"
CARD_WIDTH = 64
CARD_HEIGHT = 96

SUITS = {
    'spades': ('♠', (0, 0, 0)),
    'hearts': ('♥', (220, 20, 60)),
    'diamonds': ('♦', (220, 20, 60)),
    'clubs': ('♣', (0, 0, 0)),
}

RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

def create_card(suit_name, rank, suit_symbol, color):
    """Create a single playing card image."""
    img = Image.new('RGB', (CARD_WIDTH, CARD_HEIGHT), 'white')
    draw = ImageDraw.Draw(img)
    
    # Draw border
    draw.rectangle([0, 0, CARD_WIDTH-1, CARD_HEIGHT-1], outline='black', width=1)
    
    # Use default font
    try:
        font_large = ImageFont.truetype("arial.ttf", 20)
        font_small = ImageFont.truetype("arial.ttf", 12)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # Draw rank in top-left
    draw.text((3, 2), rank, fill=color, font=font_small)
    
    # Draw suit in center
    try:
        font_suit = ImageFont.truetype("arial.ttf", 28)
    except:
        font_suit = ImageFont.load_default()
    
    # Center the suit symbol
    bbox = draw.textbbox((0, 0), suit_symbol, font=font_suit)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (CARD_WIDTH - text_width) // 2
    y = (CARD_HEIGHT - text_height) // 2 - 2
    draw.text((x, y), suit_symbol, fill=color, font=font_suit)
    
    # Draw rank in bottom-right (inverted)
    draw.text((CARD_WIDTH - 10, CARD_HEIGHT - 14), rank, fill=color, font=font_small)
    
    return img

def create_card_back():
    """Create a card back image."""
    img = Image.new('RGB', (CARD_WIDTH, CARD_HEIGHT), 'white')
    draw = ImageDraw.Draw(img)
    
    # Draw border
    draw.rectangle([0, 0, CARD_WIDTH-1, CARD_HEIGHT-1], outline='black', width=1)
    
    # Fill with blue pattern
    draw.rectangle([2, 2, CARD_WIDTH-3, CARD_HEIGHT-3], fill=(50, 100, 200))
    
    # Draw a simple pattern
    for i in range(0, CARD_WIDTH, 8):
        draw.line([(i, 0), (i, CARD_HEIGHT)], fill=(30, 70, 170), width=1)
    for i in range(0, CARD_HEIGHT, 8):
        draw.line([(0, i), (CARD_WIDTH, i)], fill=(30, 70, 170), width=1)
    
    return img

def main():
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Generate all cards
    for suit_name, (suit_symbol, color) in SUITS.items():
        for rank in RANKS:
            filename = f"{rank}{suit_name[0].upper()}.png"
            img = create_card(suit_name, rank, suit_symbol, color)
            img.save(os.path.join(OUTPUT_DIR, filename))
            print(f"Created {filename}")
    
    # Create card back
    img_back = create_card_back()
    img_back.save(os.path.join(OUTPUT_DIR, "back.png"))
    print("Created back.png")
    
    print(f"\nDone! Created {len(RANKS) * len(SUITS)} cards + back in {OUTPUT_DIR}/")

if __name__ == "__main__":
    main()
