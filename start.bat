@echo off
title Kalshi AI Trading Agent
echo ============================================
echo   Kalshi AI Trading Agent - Starting...
echo ============================================
echo.

cd /d "%~dp0"

:: Kill any old agent still running on port 9000
echo Stopping any old agent process...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":9000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Install Python from https://python.org
    pause
    exit /b 1
)

:: Check for config
if not exist "kalshi-config.json" (
    if not defined KALSHI_API_KEY_ID (
        echo ERROR: No kalshi-config.json found and KALSHI_API_KEY_ID not set.
        echo Create kalshi-config.json or set environment variables. See .env.example.
        pause
        exit /b 1
    )
)

:: Install Python deps if needed
echo [1/3] Checking Python dependencies...
pip install -q -r requirements.txt 2>nul

:: Build frontend if dist/ is missing
if not exist "dist\index.html" (
    echo [2/3] Building frontend...
    node --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo WARNING: Node.js not installed. Frontend UI will not be available.
        echo The agent will still run and trade. Install Node.js to get the UI.
    ) else (
        if not exist "node_modules" npm install
        npm run build
    )
) else (
    echo [2/3] Frontend already built.
)

:: Start agent and open browser
echo [3/3] Starting agent...
echo.
echo ============================================
echo   Open http://localhost:9000 in your browser
echo ============================================
echo.
echo Press Ctrl+C to stop.
echo.

start http://localhost:9000
python kalshi-agent.py --config kalshi-config.json
