"""
Quick setup script to initialize the bot environment.
Run this script to set up the database and verify configuration.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.database.init_db import initialize_database, add_sample_items
from bot.utils.config import Config


async def main():
    print("=" * 60)
    print("ARK Discord Bot - Quick Setup")
    print("=" * 60)
    print()

    # Check for required environment variables
    print("Checking configuration...")

    if not Config.DISCORD_BOT_TOKEN:
        print("❌ DISCORD_BOT_TOKEN not set in .env file")
        print("   Please add your bot token to the .env file")
        return False
    else:
        print("✅ Discord bot token found")

    if not Config.ARK_SERVERS:
        print("⚠️  No ARK servers configured in .env file")
        print("   You can add them later")
    else:
        print(f"✅ Found {len(Config.ARK_SERVERS)} ARK server(s) configured")

    print()
    print("Initializing database...")

    try:
        await initialize_database()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False

    print()
    response = input("Do you want to add sample store items? (y/n): ")

    if response.lower() == "y":
        try:
            await add_sample_items()
            print("✅ Sample items added to store")
        except Exception as e:
            print(f"❌ Failed to add sample items: {e}")

    print()
    print("=" * 60)
    print("Setup complete! You can now run the bot with:")
    print("  python main.py")
    print("=" * 60)

    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
