@echo off
REM Development startup script for ARK Discord Bot
REM Credentials are loaded from .env file (not stored here!)
REM See .env.example for required environment variables

cd /d "%~dp0"
python main.py
pause
