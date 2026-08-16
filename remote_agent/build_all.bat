@echo off
echo Building ARK Server Agent System...
echo.

REM Check if Go is installed
go version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Go is not installed or not in PATH
    echo Please install Go from https://golang.org/dl/
    pause
    exit /b 1
)

echo Step 1: Building ARK Agent...
cd /d "%~dp0"
go mod tidy
if %errorlevel% neq 0 (
    echo ERROR: Failed to download agent dependencies
    pause
    exit /b 1
)

go build -o PhoenixARKAgent.exe .
if %errorlevel% neq 0 (
    echo ERROR: Failed to build PhoenixARKAgent.exe
    pause
    exit /b 1
)
echo ✅ ARK Agent built successfully

echo.
echo Step 2: Building Installer...
cd installer
go mod tidy
if %errorlevel% neq 0 (
    echo ERROR: Failed to download installer dependencies
    pause
    exit /b 1
)

go build -o PhoenixARKAgentInstaller.exe .
if %errorlevel% neq 0 (
    echo ERROR: Failed to build PhoenixARKAgentInstaller.exe
    pause
    exit /b 1
)
echo Installer built successfully

echo.
echo Step 3: Creating distribution packages...

REM Create agent distribution
if not exist dist mkdir dist
if not exist dist\agent mkdir dist\agent
copy PhoenixARKAgent.exe dist\agent\
copy config.json dist\agent\
copy README.txt dist\agent\
if not exist dist\agent\logs mkdir dist\agent\logs

REM Create installer distribution with both files
if not exist dist\installer mkdir dist\installer
copy installer\PhoenixARKAgentInstaller.exe dist\installer\
copy PhoenixARKAgent.exe dist\installer\

REM Create user package (both files together)
if not exist dist\package mkdir dist\package
copy installer\PhoenixARKAgentInstaller.exe dist\package\
copy PhoenixARKAgent.exe dist\package\

echo Distribution packages created

echo.
echo Step 4: Creating user-friendly package...
if not exist dist\package mkdir dist\package
copy installer\PhoenixARKAgentInstaller.exe dist\package\
echo This is the ARK Server Agent Installer. > dist\package\README.txt
echo. >> dist\package\README.txt
echo Installation Instructions: >> dist\package\README.txt
echo 1. Right-click PhoenixARKAgentInstaller.exe and select "Run as administrator" >> dist\package\README.txt
echo 2. Follow the on-screen instructions >> dist\package\README.txt
echo 3. Copy the Auth Key shown at the end >> dist\package\README.txt
echo 4. Give the Auth Key to your Discord bot admin >> dist\package\README.txt
echo 5. In Discord use: /register_agent ^<server_ip^> ^<auth_key^> >> dist\package\README.txt
echo. >> dist\package\README.txt
echo The installer will: >> dist\package\README.txt
echo - Install ARK Agent as a Windows Service >> dist\package\README.txt
echo - Generate a secure authentication key >> dist\package\README.txt
echo - Configure automatic startup >> dist\package\README.txt
echo - Create necessary directories >> dist\package\README.txt
echo - Test the installation >> dist\package\README.txt

echo ✅ User package created

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                    BUILD COMPLETE!                           ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.
echo 📦 Distribution Files Created:
echo.
echo 🎯 FOR USERS (Simple Installation):
echo   dist\PhoenixARKAgentInstaller.exe
echo   └─ Single EXE installer - just run as admin!
echo.
echo 🔧 FOR ADVANCED USERS:
echo   dist\agent\PhoenixARKAgent.exe
echo   dist\agent\config.json
echo   dist\agent\README.txt
echo   └─ Manual installation files
echo.
echo 📋 Complete Packages:
echo   dist\package\PhoenixARKAgentInstaller.exe
echo   dist\package\README.txt
echo   └─ User-friendly package with instructions
echo.
echo 🚀 Usage Instructions:
echo   1. Give users PhoenixARKAgentInstaller.exe
echo   2. They run it as administrator
echo   3. They get an Auth Key
echo   4. They give the Auth Key to you
echo   5. You register the agent in Discord
echo.
echo ✅ Ready for production deployment!
