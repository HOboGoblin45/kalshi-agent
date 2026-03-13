@echo off
setlocal
cd /d "%~dp0"

where npm >nul 2>&1
if %errorlevel% neq 0 (
  echo ERROR: npm is not installed or not in PATH.
  pause
  exit /b 1
)

if not exist node_modules (
  echo Installing frontend/desktop dependencies...
  npm install
  if %errorlevel% neq 0 (
    echo ERROR: npm install failed.
    pause
    exit /b 1
  )
)

echo Launching Kalshi Agent Desktop shell...
start "Kalshi Agent Desktop" npm run desktop:dev
