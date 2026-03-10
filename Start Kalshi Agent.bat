@echo off
title Kalshi AI Agent
cd /d "C:\Users\ccres\OneDrive\Desktop\kalshi-agent"

echo.
echo   Starting Kalshi AI Agent...
echo   Dashboard will open in Chrome shortly.
echo   Keep this window open. Close it to stop the agent.
echo.

:: Open dashboard in Chrome after a 3 second delay
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:9000"

:: Start the agent
python kalshi-agent.py --config kalshi-config.json
