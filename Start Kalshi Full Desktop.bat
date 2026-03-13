@echo off
setlocal
cd /d "%~dp0"

echo Starting Kalshi backend (dry-run)...
start "Kalshi Backend" cmd /k "python kalshi-agent.py --config kalshi-config.json --dry-run"

timeout /t 3 /nobreak >nul

echo Starting desktop shell...
start "Kalshi Desktop" cmd /k "npm run desktop:dev"
