#!/usr/bin/env bash
# Kalshi Agent Desktop Launcher (Linux/macOS)
set -e
cd "$(dirname "$0")"

echo ""
echo "  _  __   _   _    ___ _  _ ___"
echo " | |/ /  /_\\ | |  / __| || |_ _|"
echo " | ' <  / _ \\| |__\\__ \\ __ || |"
echo " |_|\\_\\/_/ \\_\\____|___/_||_|___|"
echo ""
echo " [INFO] Kalshi Agent Desktop Launcher"
echo " =========================================="

# Check deps
command -v node >/dev/null 2>&1 || { echo " [ERR] node.js not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || { echo " [ERR] python not found"; exit 1; }

# Install if needed
[ -d "node_modules" ] || { echo " [INFO] Installing dependencies..."; npm install; }

# Build if needed
[ -f "dist/index.html" ] || { echo " [INFO] Building frontend..."; npm run build; }

# Config if needed
[ -f "kalshi-config.json" ] || {
    echo " [INFO] Creating default config (dry-run mode)..."
    echo '{"dry_run": true, "dashboard_port": 9000, "dashboard_host": "127.0.0.1"}' > kalshi-config.json
}

echo ""
echo " [OK] Launching Electron desktop app..."
echo ""

npx electron .
