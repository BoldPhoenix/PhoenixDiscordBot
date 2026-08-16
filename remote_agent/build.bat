@echo off
echo Building Phoenix ARK Agent...
echo.

REM Check if Go is installed
go version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Go is not installed or in PATH
    echo Please install Go from https://golang.org/dl/
    pause
    exit /b 1
)

REM Download dependencies
echo Downloading Go dependencies...
go mod tidy
if %errorlevel% neq 0 (
    echo ERROR: Failed to download dependencies
    pause
    exit /b 1
)

REM Sync AgentVersion from main.go → versioninfo.json (single source of truth)
echo Syncing version from main.go...
powershell -ExecutionPolicy Bypass -File "%~dp0sync_version.ps1"
if %errorlevel% neq 0 (
    echo ERROR: Failed to sync version from main.go
    pause
    exit /b 1
)

REM Embed Windows version info (shows in exe Details tab)
REM Requires: go install github.com/josephspurrier/goversioninfo/cmd/goversioninfo@latest
echo Generating Windows version resource...
goversioninfo -64 -o resource.syso versioninfo.json >nul 2>&1
if %errorlevel% neq 0 (
    REM Try with full GOPATH in case goversioninfo isn't on PATH
    set GOPATH=%USERPROFILE%\go
    %GOPATH%\bin\goversioninfo -64 -o resource.syso versioninfo.json >nul 2>&1
    if %errorlevel% neq 0 (
        echo WARNING: goversioninfo not found - exe will not have version details
        echo To fix: go install github.com/josephspurrier/goversioninfo/cmd/goversioninfo@latest
        del resource.syso >nul 2>&1
    ) else (
        echo Version resource generated OK
    )
) else (
    echo Version resource generated OK
)

REM Build main agent executable
echo Building PhoenixArkAgent.exe...
go build -o PhoenixArkAgent.exe .
if %errorlevel% neq 0 (
    echo ERROR: Failed to build PhoenixArkAgent.exe
    pause
    exit /b 1
)

REM Build ARK server wrapper service executable
echo Building PhoenixARKServerService.exe (wrapper)...
cd wrapper
go build -o ..\PhoenixARKServerService.exe .
if %errorlevel% neq 0 (
    echo ERROR: Failed to build PhoenixARKServerService.exe
    cd ..
    pause
    exit /b 1
)
cd ..

REM Create distribution directory
if not exist dist mkdir dist

REM Copy files to distribution directory
echo Copying files to distribution directory...
copy PhoenixArkAgent.exe dist\
copy PhoenixARKServerService.exe dist\
copy config.json dist\
copy README.txt dist\

REM Create logs directory
if not exist dist\logs mkdir dist\logs

echo.
echo Build completed successfully!
echo.
echo Files created in dist\ directory:
echo   - PhoenixArkAgent.exe (main agent executable)
echo   - PhoenixARKServerService.exe (ARK server wrapper)
echo   - config.json (configuration file)
echo   - README.txt (instructions)
echo   - logs\ (log directory)
echo.
echo Next steps:
echo   1. Copy the dist\ folder to your ARK server
echo   2. Run PhoenixArkAgent.exe -install to install as Windows service
echo   3. Edit config.json with your settings
echo   4. Start the service: net start PhoenixArkAgent
