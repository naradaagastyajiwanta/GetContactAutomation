#!/bin/bash
# =============================================================
# Quick helper: sync project files to VPS
# Usage: bash sync-to-vps.sh [user@host]
# Example: bash sync-to-vps.sh root@103.253.145.84
# =============================================================

VPS="${1:-root@103.253.145.84}"
REMOTE_DIR="/opt/getcontact-ai-agent"

echo "Syncing to $VPS:$REMOTE_DIR ..."

rsync -avz --progress \
    --exclude '.git' \
    --exclude 'node_modules' \
    --exclude '__pycache__' \
    --exclude '.venv' \
    --exclude 'venv' \
    --exclude 'frontend/dist' \
    --exclude 'whatsapp-service/dist' \
    --exclude '.env' \
    --exclude '.env.production' \
    --exclude '*.pyc' \
    --exclude '.vscode' \
    --exclude '.idea' \
    --exclude '.claude' \
    --exclude '.superdesign' \
    --exclude '=2.1.2' \
    ./ "$VPS:$REMOTE_DIR/"

echo ""
echo "✓ Files synced!"
echo ""
echo "Next steps on VPS:"
echo "  ssh $VPS"
echo "  cd $REMOTE_DIR"
echo "  cp .env.production.example .env.production"
echo "  nano .env.production    # Fill in API keys"
echo "  bash deploy.sh"
