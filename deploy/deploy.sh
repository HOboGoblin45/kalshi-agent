#!/bin/bash
# Kalshi Bot — Deploy updates to server
#
# Usage:
#   ./deploy/deploy.sh [user@host]
#
# Example:
#   ./deploy/deploy.sh kalshi@123.45.67.89

set -euo pipefail

SERVER="${1:-kalshi@YOUR_VPS_IP}"

echo "Deploying to $SERVER..."

# Sync code (exclude data, secrets, and local-only files)
rsync -avz --delete \
    --exclude 'data/' \
    --exclude '.env' \
    --exclude 'venv/' \
    --exclude 'node_modules/' \
    --exclude 'dist/' \
    --exclude 'keys/' \
    --exclude '__pycache__/' \
    --exclude '.git/' \
    --exclude 'kalshi-trades.json' \
    --exclude 'kalshi-calibration.json' \
    --exclude 'kalshi-config.json' \
    --exclude '*.log' \
    . "$SERVER:~/kalshi-bot/"

# Install any new dependencies
ssh "$SERVER" "cd ~/kalshi-bot && venv/bin/pip install -q -r requirements.txt"

# Build React frontend
ssh "$SERVER" "cd ~/kalshi-bot && npm install --production=false && npm run build"

# Restart the service
ssh "$SERVER" "sudo systemctl restart kalshi-bot"

echo ""
echo "Deployed and restarted."
echo "Check status: ssh $SERVER 'sudo systemctl status kalshi-bot'"
echo "Watch logs:   ssh $SERVER 'journalctl -u kalshi-bot -f'"
