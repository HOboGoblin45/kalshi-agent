@echo off
title Kalshi AI Trading Agent
echo ============================================
echo   Kalshi AI Trading Agent - Starting...
echo ============================================
echo.

cd /d "%~dp0"

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Install Python from https://python.org
    pause
    exit /b 1
)

:: Check for Node
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js is not installed or not in PATH.
    echo Install Node.js from https://nodejs.org
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
echo [1/4] Checking Python dependencies...
pip install -q -r requirements.txt 2>nul

:: Install Node deps if needed
if not exist "node_modules" (
    echo [2/4] Installing Node dependencies...
    npm install
) else (
    echo [2/4] Node dependencies OK.
)

:: Start the Python agent in background
echo [3/4] Starting Kalshi agent (port 9000)...
if exist "kalshi-config.json" (
    start /b "KalshiAgent" cmd /c "python kalshi-agent.py --config kalshi-config.json"
) else (
    start /b "KalshiAgent" cmd /c "python kalshi-agent.py"
)

:: Wait for agent to start
timeout /t 3 /nobreak >nul

:: Start Vite dev server and open browser
echo [4/4] Starting frontend...
echo.
echo ============================================
echo   Agent:     http://localhost:9000
echo   Frontend:  http://localhost:5173
echo ============================================
echo.
echo Press Ctrl+C to stop.
echo.

start http://localhost:5173
npm run dev
