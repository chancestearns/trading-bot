# Windows Setup Guide

## Quick Fix for Common Windows Issues

### Issue 1: "docker-compose not recognized"

**Problem:**
```powershell
docker-compose : The term 'docker-compose' is not recognized...
```

**Solution:**
Docker Desktop for Windows now uses Docker Compose V2, which is integrated as a Docker CLI plugin. Use `docker compose` (without hyphen) instead:

```powershell
# New command (Docker Compose V2)
docker compose up -d
docker compose down
docker compose logs -f trading-bot

# Old command (Docker Compose V1) - only if you have it installed separately
docker-compose up -d
```

### Issue 2: "ModuleNotFoundError: No module named 'bot'"

**Problem:**
```
ImportError while importing test module...
ModuleNotFoundError: No module named 'bot'
```

**Solution:**
Install the bot package in editable mode:

```powershell
# Make sure you're in the project root directory
cd C:\Users\Chance\Documents\trading-bot-main

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install package in editable mode
pip install -e .

# Now tests should work
pytest tests\ -v
```

## Complete Windows Setup Steps

### 1. Prerequisites

- **Python 3.11+** - Download from [python.org](https://www.python.org/downloads/)
- **Docker Desktop** - Download from [docker.com](https://www.docker.com/products/docker-desktop/)
- **Git** - Download from [git-scm.com](https://git-scm.com/)

### 2. Initial Setup

```powershell
# Clone repository (if not already done)
git clone <repository-url>
cd trading-bot-main

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Install bot package in editable mode
pip install -e .
```

### 3. Configuration

```powershell
# Copy example config
Copy-Item config.example.json config.json

# Edit config.json with your favorite editor
notepad config.json
# or
code config.json  # If you have VS Code
```

### 4. Run Tests

```powershell
# Make sure virtual environment is activated
.\.venv\Scripts\Activate.ps1

# Run all tests
pytest tests\ -v

# Run with coverage
pytest tests\ -v --cov=bot

# Run specific test file
pytest tests\test_engine_loop.py -v
```

### 5. Run the Bot

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run with dashboard
python scripts\run_with_dashboard.py --config config.json

# Run backtest
python scripts\run_backtest.py --config config.json

# Run paper trading
python scripts\run_paper_trading.py --config config.json
```

### 6. Docker Deployment (Optional)

```powershell
# Build Docker image
docker build -t trading-bot .

# Run with Docker Compose
docker compose up -d

# View logs
docker compose logs -f trading-bot

# Stop containers
docker compose down

# Restart containers
docker compose restart trading-bot
```

## PowerShell Execution Policy

If you get an error about execution policy when activating the virtual environment:

```powershell
# Check current policy
Get-ExecutionPolicy

# Set policy for current user (recommended)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then try activating again
.\.venv\Scripts\Activate.ps1
```

## Common PowerShell Commands

```powershell
# Check Python version
python --version

# Check pip version
pip --version

# List installed packages
pip list

# Check Docker version
docker --version
docker compose version

# Find running processes
Get-Process python

# Kill stuck process (if needed)
Stop-Process -Name python -Force

# Check port usage
netstat -ano | findstr :8000
```

## Path Issues

If commands aren't found, ensure they're in your PATH:

```powershell
# Check Python path
where.exe python

# Check Docker path
where.exe docker

# Add to PATH temporarily (for current session)
$env:Path += ";C:\Path\To\Your\Directory"

# View current PATH
$env:Path -split ';'
```

## Environment Variables

Set environment variables for configuration:

```powershell
# Temporary (current session only)
$env:TRADING_BOT__ENGINE__MODE = "paper"
$env:TRADING_BOT__ENGINE__BROKER__STARTING_CASH = "50000"

# Permanent (user level)
[System.Environment]::SetEnvironmentVariable('TRADING_BOT__ENGINE__MODE', 'paper', 'User')

# View environment variable
$env:TRADING_BOT__ENGINE__MODE
```

## File Paths in Config

Use forward slashes or escaped backslashes in JSON config files:

```json
{
  "data_dir": "C:/Users/Chance/Documents/trading-bot-main/data",
  "log_dir": "C:\\Users\\Chance\\Documents\\trading-bot-main\\logs"
}
```

## Testing in Windows

```powershell
# Run validation script
python quick_start.py

# Run with verbose output
pytest tests\ -v -s

# Run specific test
pytest tests\test_engine_loop.py::EngineLoopTest::test_backtest_runs_without_errors -v

# Run tests matching pattern
pytest tests\ -k "test_engine" -v

# Stop on first failure
pytest tests\ -x
```

## Dashboard Access

After starting the bot with dashboard:

1. Open browser to: `http://localhost:8000`
2. If port 8000 is in use, specify different port:
   ```powershell
   python scripts\run_with_dashboard.py --port 8080
   ```
3. Check firewall if you can't access dashboard

## Troubleshooting

### Virtual Environment Issues

```powershell
# Deactivate virtual environment
deactivate

# Delete virtual environment
Remove-Item -Recurse -Force .venv

# Recreate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

### Port Already in Use

```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill process (replace PID with actual process ID)
Stop-Process -Id <PID> -Force

# Or use different port
python scripts\run_with_dashboard.py --port 8080
```

### Docker Issues

```powershell
# Check Docker is running
docker ps

# Restart Docker Desktop
# (Use system tray icon or)
Restart-Service docker

# Check Docker Compose version
docker compose version

# Remove all containers and images (clean slate)
docker compose down -v
docker system prune -a --volumes
```

### Test Collection Errors

If pytest can't collect tests:

```powershell
# Ensure bot package is installed
pip install -e .

# Clear pytest cache
Remove-Item -Recurse -Force .pytest_cache
Remove-Item -Recurse -Force bot\__pycache__
Remove-Item -Recurse -Force tests\__pycache__

# Try again
pytest tests\ -v
```

## Performance Tips

- **Use SSD** for better I/O performance
- **Increase Docker memory** in Docker Desktop settings
- **Close unnecessary programs** when running tests
- **Use Windows Terminal** for better PowerShell experience
- **Enable WSL2** for Docker Desktop (faster)

## Getting Help

If you encounter issues:

1. Check this guide first
2. Review error messages carefully
3. Check logs in console output
4. Search for error messages online
5. Check project documentation

## Useful Aliases

Add to your PowerShell profile (`$PROFILE`):

```powershell
# Open profile for editing
notepad $PROFILE

# Add these aliases:
function Activate-TradingBot {
    Set-Location "C:\Users\Chance\Documents\trading-bot-main"
    .\.venv\Scripts\Activate.ps1
}

function Run-TradingBot {
    Activate-TradingBot
    python scripts\run_with_dashboard.py --config config.json
}

function Test-TradingBot {
    Activate-TradingBot
    pytest tests\ -v
}

# Then reload profile
. $PROFILE
```

Now you can use:
```powershell
Activate-TradingBot  # Activates environment
Run-TradingBot       # Runs bot with dashboard
Test-TradingBot      # Runs all tests
```

---

**Last Updated:** November 11, 2025
**For:** Windows 10/11 with PowerShell
