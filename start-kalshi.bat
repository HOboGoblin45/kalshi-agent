@echo off
title Kalshi Agent - Starting...
cd /d "%~dp0"

echo.
echo   _  __   _   _    ___ _  _ ___
echo  ^| ^|/ /  /_\ ^| ^|  / __^| ^|^| ^|_ _^|
echo  ^| ' ^<  / _ \^| ^|__\__ \ __ ^|^| ^|
echo  ^|_^|\_\/_/ \_\____^|___/_^|^|_^|___^|
echo.
echo  [INFO] Kalshi Agent Desktop Launcher
echo  ==========================================

:: Check for Node
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERR] node.js not found in PATH
    echo  Install from https://nodejs.org
    pause
    exit /b 1
)

:: Check for Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERR] python not found in PATH
    echo  Install from https://python.org
    pause
    exit /b 1
)

:: Install deps if needed
if not exist "node_modules" (
    echo  [INFO] Installing dependencies...
    call npm install
)

:: Build if dist is missing
if not exist "dist\index.html" (
    echo  [INFO] Building frontend...
    call npm run build
)

:: Create config if missing
if not exist "kalshi-config.json" (
    echo  [INFO] Creating default config (dry-run mode)...
    echo {"dry_run": true, "dashboard_port": 9000, "dashboard_host": "127.0.0.1"} > kalshi-config.json
)

echo.
echo  [OK] Launching Electron desktop app...
echo  The app will auto-start the backend agent.
echo  Close this window to stop the agent.
echo.

:: Launch Electron (it handles starting the Python backend itself)
call npx electron .

echo.
echo  [INFO] Kalshi Agent stopped.
pause
