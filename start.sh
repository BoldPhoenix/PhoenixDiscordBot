#!/bin/bash
# ============================================
# ARK Discord Bot - Linux/Mac Launcher
# ============================================
# This script launches the bot securely using
# credentials from the .env file
# ============================================

cd "$(dirname "$0")"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: Python 3 is not installed"
    echo ""
    echo "Please install Python 3.8 or higher:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  CentOS/RHEL:   sudo yum install python3 python3-pip"
    echo "  macOS:         brew install python3"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

# Check if virtual environment exists
if [ -f "venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Launch the bot using the secure launcher
python3 launcher.py

# Deactivate virtual environment if it was activated
if [ -f "venv/bin/deactivate" ]; then
    deactivate
fi
