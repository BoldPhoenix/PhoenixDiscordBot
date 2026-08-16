# ARK Discord Bot Management Script
# Provides easy commands for running, testing, and managing the bot

param(
    [Parameter(Position=0)]
    [ValidateSet("run", "setup", "lint", "format", "test", "clean", "install", "help")]
    [string]$Command = "help"
)

$BotDir = $PSScriptRoot
$VenvPath = Join-Path $BotDir "venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$VenvActivate = Join-Path $VenvPath "Scripts\Activate.ps1"

function Write-Header {
    param([string]$Text)
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host ""
}

function Test-VenvExists {
    if (-not (Test-Path $VenvPath)) {
        Write-Host "Virtual environment not found!" -ForegroundColor Red
        Write-Host "Run: .\manage.ps1 install" -ForegroundColor Yellow
        return $false
    }
    return $true
}

function Invoke-InVenv {
    param([string]$Script)
    
    if (-not (Test-VenvExists)) {
        return
    }
    
    & $VenvActivate
    Invoke-Expression $Script
}

switch ($Command) {
    "install" {
        Write-Header "Installing ARK Discord Bot"
        
        Write-Host "Creating virtual environment..." -ForegroundColor Green
        python -m venv venv
        
        Write-Host "Activating virtual environment..." -ForegroundColor Green
        & $VenvActivate
        
        Write-Host "Upgrading pip..." -ForegroundColor Green
        & $VenvPython -m pip install --upgrade pip
        
        Write-Host "Installing dependencies..." -ForegroundColor Green
        & $VenvPython -m pip install -r requirements.txt
        
        Write-Host ""
        Write-Host "✅ Installation complete!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Yellow
        Write-Host "  1. Copy .env.example to .env and configure it"
        Write-Host "  2. Run: .\manage.ps1 setup"
        Write-Host "  3. Run: .\manage.ps1 run"
    }
    
    "setup" {
        Write-Header "Setting Up Database and Configuration"
        
        if (-not (Test-VenvExists)) {
            return
        }
        
        & $VenvActivate
        & $VenvPython scripts\setup.py
    }
    
    "run" {
        Write-Header "Starting ARK Discord Bot"
        
        if (-not (Test-VenvExists)) {
            return
        }
        
        if (-not (Test-Path (Join-Path $BotDir ".env"))) {
            Write-Host "⚠️  .env file not found!" -ForegroundColor Yellow
            Write-Host "Copy .env.example to .env and configure it first" -ForegroundColor Yellow
            return
        }
        
        & $VenvActivate
        & $VenvPython main.py
    }
    
    "lint" {
        Write-Header "Running Linters"
        
        if (-not (Test-VenvExists)) {
            return
        }
        
        & $VenvActivate
        
        Write-Host "Running flake8..." -ForegroundColor Green
        & $VenvPython -m flake8 bot/ main.py
        
        Write-Host ""
        Write-Host "Running pylint..." -ForegroundColor Green
        & $VenvPython -m pylint bot/ main.py
        
        Write-Host ""
        Write-Host "Running mypy..." -ForegroundColor Green
        & $VenvPython -m mypy bot/ --ignore-missing-imports
        
        Write-Host ""
        Write-Host "✅ Linting complete!" -ForegroundColor Green
    }
    
    "format" {
        Write-Header "Formatting Code"
        
        if (-not (Test-VenvExists)) {
            return
        }
        
        & $VenvActivate
        
        Write-Host "Running black..." -ForegroundColor Green
        & $VenvPython -m black bot/ main.py scripts/
        
        Write-Host ""
        Write-Host "✅ Formatting complete!" -ForegroundColor Green
    }
    
    "test" {
        Write-Header "Running Tests"
        
        if (-not (Test-VenvExists)) {
            return
        }
        
        & $VenvActivate
        
        if (Test-Path (Join-Path $BotDir "tests")) {
            & $VenvPython -m pytest tests/ -v
        } else {
            Write-Host "No tests directory found" -ForegroundColor Yellow
        }
    }
    
    "clean" {
        Write-Header "Cleaning Build Artifacts"
        
        Write-Host "Removing __pycache__ directories..." -ForegroundColor Green
        Get-ChildItem -Path $BotDir -Recurse -Filter "__pycache__" -Directory | Remove-Item -Recurse -Force
        
        Write-Host "Removing .pyc files..." -ForegroundColor Green
        Get-ChildItem -Path $BotDir -Recurse -Filter "*.pyc" -File | Remove-Item -Force
        
        Write-Host "Removing build directories..." -ForegroundColor Green
        $CleanDirs = @("build", "dist", "*.egg-info", ".pytest_cache", ".mypy_cache")
        foreach ($dir in $CleanDirs) {
            Get-ChildItem -Path $BotDir -Recurse -Filter $dir -Directory | Remove-Item -Recurse -Force
        }
        
        Write-Host ""
        Write-Host "✅ Cleanup complete!" -ForegroundColor Green
    }
    
    "help" {
        Write-Header "ARK Discord Bot - Management Commands"
        
        Write-Host "Usage: .\manage.ps1 <command>" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Available commands:" -ForegroundColor Green
        Write-Host ""
        Write-Host "  install" -NoNewline -ForegroundColor Cyan
        Write-Host "  - Install dependencies and create virtual environment"
        Write-Host "  setup" -NoNewline -ForegroundColor Cyan
        Write-Host "    - Initialize database and verify configuration"
        Write-Host "  run" -NoNewline -ForegroundColor Cyan
        Write-Host "      - Start the Discord bot"
        Write-Host "  lint" -NoNewline -ForegroundColor Cyan
        Write-Host "     - Run all linters (flake8, pylint, mypy)"
        Write-Host "  format" -NoNewline -ForegroundColor Cyan
        Write-Host "   - Format code with black"
        Write-Host "  test" -NoNewline -ForegroundColor Cyan
        Write-Host "     - Run unit tests"
        Write-Host "  clean" -NoNewline -ForegroundColor Cyan
        Write-Host "    - Remove build artifacts and cache files"
        Write-Host "  help" -NoNewline -ForegroundColor Cyan
        Write-Host "     - Show this help message"
        Write-Host ""
        Write-Host "Examples:" -ForegroundColor Yellow
        Write-Host "  .\manage.ps1 install   # First time setup"
        Write-Host "  .\manage.ps1 setup     # Configure database"
        Write-Host "  .\manage.ps1 run       # Start the bot"
        Write-Host "  .\manage.ps1 lint      # Check code quality"
        Write-Host ""
    }
}
