#!/usr/bin/env python3
"""
Secure launcher for ARK Discord Bot
Loads credentials from .env file and starts the bot
"""

import os
import sys
from pathlib import Path

def main():
    """Launch the bot with proper environment setup."""
    # Get script directory
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)
    
    # Check if .env file exists
    env_file = script_dir / ".env"
    if not env_file.exists():
        print("❌ ERROR: .env file not found!")
        print()
        print("Please create a .env file with your configuration.")
        print("You can copy .env.example as a starting point:")
        print()
        print(f"  1. Copy .env.example to .env")
        print(f"  2. Edit .env and add your Discord bot token")
        print(f"  3. Run this launcher again")
        print()
        input("Press Enter to exit...")
        sys.exit(1)
    
    # Check if main.py exists
    main_script = script_dir / "main.py"
    if not main_script.exists():
        print("❌ ERROR: main.py not found!")
        print(f"Expected location: {main_script}")
        print()
        input("Press Enter to exit...")
        sys.exit(1)
    
    # Launch the bot
    print("🚀 Starting ARK Discord Bot...")
    print(f"📁 Working directory: {script_dir}")
    print(f"🔐 Loading credentials from: {env_file}")
    print()
    
    # Import and run main
    try:
        # Add script directory to Python path
        sys.path.insert(0, str(script_dir))
        
        # Import main module
        import main as bot_main
        
        # Run the bot (uses asyncio.run internally)
        import asyncio
        asyncio.run(bot_main.main())
        
    except KeyboardInterrupt:
        print("\n⏹️  Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print()
        input("Press Enter to exit...")
        sys.exit(1)

if __name__ == "__main__":
    main()
