#!/bin/bash
# Simple script to sync Discord commands
# Run this after making command changes

echo "Syncing Discord commands..."
cd /opt/phoenix-bot
./venv/bin/python sync_commands.py
echo "Command sync complete!"
