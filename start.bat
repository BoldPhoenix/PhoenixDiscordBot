@echo off
REM ============================================
REM ARK Discord Bot - Windows Launcher
REM ============================================
REM This script launches the bot securely using
REM credentials from the .env file
REM ============================================

cd /d "%~dp0"

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8 or higher from:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM Check if virtual environment exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Launch the bot using the secure launcher
python launcher.py

REM Deactivate virtual environment if it was activated
if exist "venv\Scripts\deactivate.bat" (
    call venv\Scripts\deactivate.bat
)

pause
