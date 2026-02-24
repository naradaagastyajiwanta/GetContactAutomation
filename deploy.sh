#!/bin/bash
# =============================================================
# GetContact AI Agent — VPS Deployment Script
# Run on Ubuntu 24.04 VPS: bash deploy.sh
# =============================================================

set -e

DOMAIN="getcontact.najworks.me"
APP_DIR="/opt/getcontact-ai-agent"
REPO_URL=""  # Set your git repo URL here, or copy files manually

echo "============================================="
echo "  GetContact AI Agent — VPS Deployment"
echo "  Target: $DOMAIN"
echo "============================================="

# ------------------------------------------------------------------
# 1. System update & Docker install
# ------------------------------------------------------------------
echo ""
echo "[1/6] Installing Docker & Docker Compose..."

# Update system
sudo apt-get update -y
sudo apt-get upgrade -y

# Install prerequisites
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    unzip

# Install Docker (official method)
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
    
    # Add current user to docker group
    sudo usermod -aG docker $USER
    echo "  ✓ Docker installed"
else
    echo "  ✓ Docker already installed: $(docker --version)"
fi

# Install Docker Compose plugin (v2)
if ! docker compose version &> /dev/null; then
    sudo apt-get install -y docker-compose-plugin
    echo "  ✓ Docker Compose plugin installed"
else
    echo "  ✓ Docker Compose already available: $(docker compose version)"
fi

# Ensure Docker is running
sudo systemctl enable docker
sudo systemctl start docker

# ------------------------------------------------------------------
# 2. Create app directory & copy files
# ------------------------------------------------------------------
echo ""
echo "[2/6] Setting up application directory..."

sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

if [ -n "$REPO_URL" ]; then
    # Clone from git
    if [ -d "$APP_DIR/.git" ]; then
        cd $APP_DIR
        git pull origin main
    else
        git clone $REPO_URL $APP_DIR
    fi
else
    echo "  ⚠ No REPO_URL set. Please copy project files to $APP_DIR manually."
    echo "  Example: scp -r ./* user@103.253.145.84:$APP_DIR/"
    
    # If we're running from project directory, check if files exist
    if [ -f "docker-compose.yml" ]; then
        echo "  → Found docker-compose.yml in current directory, using current dir..."
        APP_DIR="$(pwd)"
    fi
fi

cd $APP_DIR

# Create data directories
mkdir -p data data/audiensi_docs data/templates data/ig_sessions
mkdir -p whatsapp-service/auth_store whatsapp-service/auth_store_backup

echo "  ✓ Directory structure ready"

# ------------------------------------------------------------------
# 3. Environment configuration
# ------------------------------------------------------------------
echo ""
echo "[3/6] Checking environment configuration..."

if [ ! -f ".env.production" ]; then
    if [ -f ".env.production.example" ]; then
        cp .env.production.example .env.production
        echo "  ⚠ Created .env.production from example."
        echo "  → EDIT IT NOW: nano $APP_DIR/.env.production"
        echo "  → At minimum set: OPENAI_API_KEY, SERPER_API_KEY"
        echo ""
        read -p "  Press Enter after editing .env.production (or Ctrl+C to abort)..."
    else
        echo "  ✗ ERROR: .env.production.example not found!"
        exit 1
    fi
else
    echo "  ✓ .env.production exists"
fi

# Validate required keys
source .env.production 2>/dev/null || true
if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "sk-your-openai-api-key" ]; then
    echo "  ⚠ WARNING: OPENAI_API_KEY not set in .env.production!"
    echo "  → AI features will not work until this is configured."
fi

# ------------------------------------------------------------------
# 4. Configure firewall
# ------------------------------------------------------------------
echo ""
echo "[4/6] Configuring firewall..."

if command -v ufw &> /dev/null; then
    sudo ufw allow 22/tcp     # SSH
    sudo ufw allow 80/tcp     # HTTP (Cloudflare → Nginx)
    sudo ufw allow 443/tcp    # HTTPS (if Cloudflare Full SSL)
    # Do NOT expose 3100 or 8000 publicly — only via Nginx
    sudo ufw --force enable
    echo "  ✓ UFW configured (ports 22, 80, 443 open)"
else
    echo "  ⚠ UFW not found, skipping firewall config"
fi

# ------------------------------------------------------------------
# 5. Build & Start containers
# ------------------------------------------------------------------
echo ""
echo "[5/6] Building and starting Docker containers..."

# Build all images
docker compose build --no-cache

# Start services (detached)
docker compose up -d

echo "  ✓ All containers started"

# ------------------------------------------------------------------
# 6. Verify deployment
# ------------------------------------------------------------------
echo ""
echo "[6/6] Verifying deployment..."

# Wait for services to initialize
echo "  Waiting 15 seconds for services to start..."
sleep 15

# Check container status
echo ""
echo "  Container status:"
docker compose ps

# Health check
echo ""
echo "  Health check:"
HEALTH=$(curl -s http://localhost:80/health 2>/dev/null || echo '{"error": "not reachable"}')
echo "  $HEALTH"

echo ""
echo "============================================="
echo "  Deployment Complete!"
echo "============================================="
echo ""
echo "  Dashboard: https://$DOMAIN"
echo "  API:       https://$DOMAIN/api/"
echo "  Health:    https://$DOMAIN/health"
echo ""
echo "  Cloudflare DNS:"
echo "  → Add A record: getcontact → 103.253.145.84 (Proxied ☁️)"
echo "  → SSL/TLS mode: Full"
echo ""
echo "  Useful commands:"
echo "  → Logs:    docker compose logs -f"
echo "  → Status:  docker compose ps"
echo "  → Restart: docker compose restart"
echo "  → Stop:    docker compose down"
echo "  → Update:  git pull && docker compose up -d --build"
echo ""
echo "  WhatsApp Setup:"
echo "  → Open https://$DOMAIN → WhatsApp page → Scan QR code"
echo ""
echo "  Database location: $APP_DIR/data/getcontact.db"
echo "  WA session:        $APP_DIR/whatsapp-service/auth_store/"
echo "============================================="
