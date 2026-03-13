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
if %errorlevel% neq 0 goto :nonode

:: Check for Python
where python >nul 2>&1
if %errorlevel% neq 0 goto :nopython

:: Install deps if needed
if not exist "node_modules" goto :installdeps
goto :checkbuild

:installdeps
echo  [INFO] Installing dependencies...
call npm install

:checkbuild
if not exist "dist\index.html" goto :build
goto :checkconfig

:build
echo  [INFO] Building frontend...
call npm run build

:checkconfig
if not exist "kalshi-config.json" goto :makeconfig
goto :launch

:makeconfig
echo  [INFO] Creating default config...
echo {"dry_run": true, "dashboard_port": 9000, "dashboard_host": "127.0.0.1"} > kalshi-config.json

:launch
echo.
echo  [OK] Launching Electron desktop app...
echo  The app will auto-start the backend agent.
echo  Close this window to stop the agent.
echo.
call npx electron .
echo.
echo  [INFO] Kalshi Agent stopped.
pause
goto :eof

:nonode
echo  [ERR] node.js not found in PATH
echo  Install from https://nodejs.org
pause
exit /b 1

:nopython
echo  [ERR] python not found in PATH
echo  Install from https://python.org
pause
exit /b 1
