"""
Build script for creating standalone EXE of ARK Discord Bot.

This builds a single-file executable that includes:
- All Python dependencies
- Bot code
- Embedded bot token (for SaaS distribution)

Users only need to:
1. Run the EXE
2. Invite the bot to their Discord
3. Configure their ARK servers via Discord commands
"""

import PyInstaller.__main__
import os
import sys
from pathlib import Path

# Get the bot's root directory
ROOT_DIR = Path(__file__).parent
BUILD_DIR = ROOT_DIR / "build"
DIST_DIR = ROOT_DIR / "dist"

# Bot version
VERSION = "2.0.0"

def build_exe():
    """Build the EXE using PyInstaller."""
    print("\nPreparing build environment...\n")
    version_file = create_version_info()
    
    print("=" * 60)
    print("ARK Discord Bot - EXE Builder")
    print("=" * 60)
    print(f"Version: {VERSION}")
    print(f"Build Type: SaaS (Embedded Token)")
    print("=" * 60)
    
    # Check if .env exists
    if not (ROOT_DIR / '.env').exists():
        print("\nWARNING: .env file not found!")
        print("The bot token will need to be configured after building.")
        print("Create a .env file with DISCORD_BOT_TOKEN before building.\n")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            print("Build cancelled.")
            sys.exit(0)
    else:
        print("OK Found .env file - token will be embedded\n")
    
    # PyInstaller arguments
    args = [
        str(ROOT_DIR / 'main.py'),          # Entry point
        '--name=ArkDiscordBot',             # EXE name
        '--onefile',                        # Single file
        f'--distpath={DIST_DIR}',           # Output directory
        f'--workpath={BUILD_DIR}/work',     # Work directory
        f'--specpath={BUILD_DIR}',          # Spec file directory
        '--clean',                          # Clean build
        
        # Include data files (use absolute paths)
        f'--add-data={ROOT_DIR}/bot{os.pathsep}bot',  # Include bot package
        f'--add-data={ROOT_DIR}/.env{os.pathsep}.',   # Include .env file (with token)
        
        # Hidden imports (packages not auto-detected)
        '--hidden-import=discord',
        '--hidden-import=discord.ext',
        '--hidden-import=discord.ext.commands',
        '--hidden-import=discord.app_commands',
        '--hidden-import=aiosqlite',
        '--hidden-import=ark_asa_parser',
        '--hidden-import=asyncio',
        '--hidden-import=sqlite3',
        '--hidden-import=logging',
        '--hidden-import=dotenv',
        '--hidden-import=pyasn1',
        
        # Exclude unnecessary packages
        '--exclude-module=tkinter',
        '--exclude-module=matplotlib',
        '--exclude-module=numpy',
        '--exclude-module=pandas',
        '--exclude-module=PIL',
        '--exclude-module=pytest',
        
        # Console mode options
        '--console',                        # Show console for logging
        
        # Version info
        f'--version-file={version_file}',  # Use the created version file
    ]
    
    print("\nBuilding executable...")
    print("This may take several minutes...\n")
    
    try:
        PyInstaller.__main__.run(args)
        print("\n" + "=" * 60)
        print("OK Build completed successfully!")
        print("=" * 60)
        print(f"Output: {DIST_DIR / 'ArkDiscordBot.exe'}")
        print("\nDistribution package includes:")
        print("  - All Python dependencies")
        print("  - Bot code and cogs")
        print("  - Embedded Discord token")
        print("  - SQLite database engine")
        print("\nUsers need:")
        print("  - Windows 10/11 (64-bit)")
        print("  - Internet connection")
        print("  - Discord server admin access")
        print("  - ARK server RCON credentials")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nX Build failed: {e}")
        sys.exit(1)

def create_version_info():
    """Create Windows version info file."""
    version_info = f"""# UTF-8
#
# For more details about fixed file info:
# See: http://msdn.microsoft.com/en-us/library/ms646997.aspx
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({VERSION.replace('.', ', ')}, 0),
    prodvers=({VERSION.replace('.', ', ')}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Return of the Phoenix'),
        StringStruct(u'FileDescription', u'ARK: Survival Ascended Discord Bot'),
        StringStruct(u'FileVersion', u'{VERSION}'),
        StringStruct(u'InternalName', u'ArkDiscordBot'),
        StringStruct(u'LegalCopyright', u'© 2025 Return of the Phoenix. All rights reserved.'),
        StringStruct(u'OriginalFilename', u'ArkDiscordBot.exe'),
        StringStruct(u'ProductName', u'ARK Discord Bot'),
        StringStruct(u'ProductVersion', u'{VERSION}')])
      ]), 
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    
    # Create build directory if it doesn't exist
    build_dir = ROOT_DIR / 'build'
    build_dir.mkdir(exist_ok=True)
    
    version_file = build_dir / 'version_info.txt'
    with open(version_file, 'w', encoding='utf-8') as f:
        f.write(version_info)
    
    print("OK Created version info file")
    return str(version_file)

if __name__ == '__main__':
    import io
    # Fix Windows console encoding
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    
    # Build the EXE
    build_exe()
