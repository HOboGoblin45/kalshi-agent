#!/bin/bash
# Kalshi Trading Bot — Server Setup Script
# Run this once on a fresh Ubuntu 22.04+ VPS
#
# Usage:
#   scp deploy/setup-server.sh root@YOUR_VPS_IP:~/
#   ssh root@YOUR_VPS_IP "bash setup-server.sh"

set -euo pipefail

echo "══════════════════════════════════════"
echo "  Kalshi Bot — Server Setup"
echo "══════════════════════════════════════"

# ── System updates ──
echo "[1/8] Updating system packages..."
apt update && apt upgrade -y

# ── Install dependencies ──
echo "[2/8] Installing Python, Caddy, and tools..."
apt install -y python3 python3-pip python3-venv git ufw caddy curl

# ── Create dedicated user ──
echo "[3/8] Creating kalshi user..."
if ! id -u kalshi &>/dev/null; then
    useradd -m -s /bin/bash kalshi
    echo "Created user 'kalshi'"
else
    echo "User 'kalshi' already exists"
fi

# ── Clone repository ──
echo "[4/8] Cloning repository..."
REPO_DIR="/home/kalshi/kalshi-bot"
if [ -d "$REPO_DIR" ]; then
    echo "Repository already exists at $REPO_DIR"
    cd "$REPO_DIR"
    sudo -u kalshi git pull origin main || true
else
    sudo -u kalshi git clone https://github.com/HOboGoblin45/kalshi-agent.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# ── Python virtual environment ──
echo "[5/8] Setting up Python environment..."
sudo -u kalshi python3 -m venv "$REPO_DIR/venv"
sudo -u kalshi "$REPO_DIR/venv/bin/pip" install --upgrade pip
sudo -u kalshi "$REPO_DIR/venv/bin/pip" install -r "$REPO_DIR/requirements.txt"

# ── Create data directories ──
echo "[6/8] Creating data directories..."
sudo -u kalshi mkdir -p "$REPO_DIR/data/backups"
sudo -u kalshi mkdir -p "$REPO_DIR/keys"

# ── Install systemd service ──
echo "[7/8] Installing systemd service..."
cp "$REPO_DIR/deploy/kalshi-bot.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable kalshi-bot

# ── Configure firewall ──
echo "[8/8] Configuring firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp    # HTTP (Caddy redirect)
ufw allow 443/tcp   # HTTPS (Caddy)
ufw --force enable

echo ""
echo "══════════════════════════════════════"
echo "  Setup Complete!"
echo "══════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Copy your .env file:"
echo "     scp .env kalshi@YOUR_VPS_IP:~/kalshi-bot/.env"
echo ""
echo "  2. Copy your Kalshi private key:"
echo "     scp kalshi-private-key.key kalshi@YOUR_VPS_IP:~/kalshi-bot/keys/"
echo ""
echo "  3. Copy your config:"
echo "     scp kalshi-config.json kalshi@YOUR_VPS_IP:~/kalshi-bot/"
echo ""
echo "  4. (Optional) Set up HTTPS with Caddy:"
echo "     cp /home/kalshi/kalshi-bot/deploy/Caddyfile /etc/caddy/Caddyfile"
echo "     Edit the domain name, then: systemctl restart caddy"
echo ""
echo "  5. Start the bot:"
echo "     systemctl start kalshi-bot"
echo "     journalctl -u kalshi-bot -f    # watch logs"
echo ""
echo "  Dashboard will be at http://YOUR_VPS_IP:9000"
echo "  (or https://your-domain.com after Caddy setup)"
