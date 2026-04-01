# Deployment Guide - GetContact AI Agent

**Version:** 1.0.0
**Last Updated:** 2025-02-25

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Configuration](#environment-configuration)
3. [Docker Deployment](#docker-deployment)
4. [Manual Deployment](#manual-deployment)
5. [Production Setup](#production-setup)
6. [Monitoring & Logging](#monitoring--logging)
7. [Backup & Recovery](#backup--recovery)
8. [Security Hardening](#security-hardening)
9. [Performance Tuning](#performance-tuning)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Production Environment Requirements

**Minimum Specifications:**
- CPU: 2 cores
- RAM: 4 GB
- Storage: 20 GB
- OS: Ubuntu 20.04+ / Debian 11+ / Docker-compatible

**Recommended Specifications:**
- CPU: 4+ cores
- RAM: 8+ GB
- Storage: 50+ GB (SSD recommended)
- OS: Ubuntu 22.04 LTS

**Software Requirements:**
- Docker 20.10+
- Docker Compose 2.0+
- Git
- Nginx (reverse proxy, optional)
- SSL certificate (Let's Encrypt recommended)

**External Services:**
- OpenAI API account
- Serper.dev API account
- Dedicated WhatsApp account
- (Optional) Apify account
- (Optional) Google Cloud project (for Sheets export)

### Network Requirements

**Ports Used:**
- `8000` - Orchestrator API
- `3100` - WhatsApp Service
- `5173` - Frontend dev server (not for production)
- `80/443` - Nginx reverse proxy (production)

**Firewall Configuration:**
```bash
# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow SSH
sudo ufw allow 22/tcp

# Enable firewall
sudo ufw enable
```

---

## Environment Configuration

### Production Environment Variables

Create `.env` file in project root:

```bash
# OpenAI API (Required)
OPENAI_API_KEY=sk-proj-...

# Serper.dev (Required)
SERPER_API_KEY=...

# WhatsApp Service URL (Internal)
WA_SERVICE_URL=http://whatsapp-service:3100

# Webhook URL (Internal)
WEBHOOK_URL=http://orchestrator:8000/webhook/incoming

# Database Path
DATABASE_PATH=/app/data/getcontact.db

# Rate Limiting (Production Values)
MAX_DAILY_CONVERSATIONS=50
MIN_MESSAGE_GAP_SECONDS=180
MAX_IG_PROFILES_PER_DAY=300
IG_REQUEST_DELAY_SECONDS=10

# Outreach Hours (WIB = UTC+7)
OUTREACH_START_HOUR=8
OUTREACH_END_HOUR=21

# AI Settings
AGENT_MODEL=gpt-4o-mini
AGENT_TEMPERATURE=0.1
AGENT_MAX_TOKENS=500
MAX_AI_CONCURRENT=5
SEND_INTERVAL_MS=3000

# Feature Flags
CHATBOT_ENABLED=true
LEARNING_ENABLED=true
AUDIENSI_ENABLED=false

# Instagram Credentials (Optional)
IG_USERNAME=
IG_PASSWORD=

# Apify (Optional)
APIFY_API_KEY=

# Logging
LOG_LEVEL=INFO
```

### Sensitive Data Management

**Never commit `.env` files to version control.**

**Best Practices:**
1. Use `.env.example` as template
2. Add `.env` to `.gitignore`
3. Use secret management in production:
   - Docker Secrets
   - Kubernetes Secrets
   - AWS Secrets Manager
   - HashiCorp Vault

**Example Docker Secret:**
```bash
echo "sk-proj-..." | docker secret create openai_api_key -
```

---

## Docker Deployment

### Quick Start (Docker Compose)

**1. Clone Repository:**

```bash
git clone <repository-url>
cd GetContactAIAgent
```

**2. Configure Environment:**

```bash
cp .env.example .env
nano .env  # Edit with production values
```

**3. Build and Start:**

```bash
# Build images
docker-compose build

# Start services (detached)
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

**4. Initialize Database:**

```bash
# Database auto-initializes, or run:
docker-compose exec orchestrator python scripts/setup_db.py
```

**5. Access Services:**

- Orchestrator API: http://localhost:8000
- WhatsApp Service: http://localhost:3100
- Frontend: http://localhost:8000 (served by orchestrator)

### Docker Compose Configuration

**`docker-compose.yml`:**

```yaml
version: '3.8'

services:
  orchestrator:
    build:
      context: .
      dockerfile: docker/orchestrator.Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    depends_on:
      - whatsapp-service
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/"]
      interval: 30s
      timeout: 10s
      retries: 3

  whatsapp-service:
    build:
      context: .
      dockerfile: docker/whatsapp-service.Dockerfile
    ports:
      - "3100:3100"
    volumes:
      - whatsapp-auth:/app/auth_store
      - whatsapp-auth-backup:/app/auth_store_backup
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3100/status"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  whatsapp-auth:
  whatsapp-auth-backup:
```

### Dockerfiles

**`docker/orchestrator.Dockerfile`:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY orchestrator/ ./orchestrator/
COPY scripts/ ./scripts/

# Create data directory
RUN mkdir -p /app/data /app/logs

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`docker/whatsapp-service.Dockerfile`:**

```dockerfile
FROM node:18-slim

WORKDIR /app

# Copy package files
COPY whatsapp-service/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy source
COPY whatsapp-service/src/ ./src/
COPY whatsapp-service/tsconfig.json ./

# Build TypeScript
RUN npm run build

# Create auth directories
RUN mkdir -p /app/auth_store /app/auth_store_backup

# Expose port
EXPOSE 3100

# Run application
CMD ["node", "dist/index.js"]
```

---

## Manual Deployment

### System Preparation

**1. Install System Dependencies:**

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Git
sudo apt-get install -y git

# Install Nginx (optional)
sudo apt-get install -y nginx
```

**2. Create Application User:**

```bash
# Create user
sudo useradd -m -s /bin/bash getcontact

# Create directories
sudo mkdir -p /opt/getcontact
sudo mkdir -p /var/log/getcontact
sudo chown -R getcontact:getcontact /opt/getcontact
sudo chown -R getcontact:getcontact /var/log/getcontact
```

**3. Deploy Application:**

```bash
# Clone repository
sudo -u getcontact git clone <repository-url> /opt/getcontact/app
cd /opt/getcontact/app

# Setup Python environment
sudo -u getcontact python3.11 -m venv venv
sudo -u getcontact venv/bin/pip install -r requirements.txt

# Setup WhatsApp service
cd whatsapp-service
sudo -u getcontact npm install
npm run build
cd ..
```

### Systemd Services

**Orchestrator Service (`/etc/systemd/system/getcontact-orchestrator.service`):**

```ini
[Unit]
Description=GetContact Orchestrator Service
After=network.target whatsapp-service.service

[Service]
Type=simple
User=getcontact
Group=getcontact
WorkingDirectory=/opt/getcontact/app
Environment="PATH=/opt/getcontact/app/venv/bin"
EnvironmentFile=/opt/getcontact/app/.env
ExecStart=/opt/getcontact/app/venv/bin/uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:/var/log/getcontact/orchestrator.log
StandardError=append:/var/log/getcontact/orchestrator-error.log

[Install]
WantedBy=multi-user.target
```

**WhatsApp Service (`/etc/systemd/system/getcontact-whatsapp.service`):**

```ini
[Unit]
Description=GetContact WhatsApp Service
After=network.target

[Service]
Type=simple
User=getcontact
Group=getcontact
WorkingDirectory=/opt/getcontact/app/whatsapp-service
EnvironmentFile=/opt/getcontact/app/.env
ExecStart=/usr/bin/node dist/index.js
Restart=always
RestartSec=10
StandardOutput=append:/var/log/getcontact/whatsapp.log
StandardError=append:/var/log/getcontact/whatsapp-error.log

[Install]
WantedBy=multi-user.target
```

**Enable and Start Services:**

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable getcontact-orchestrator
sudo systemctl enable getcontact-whatsapp

# Start services
sudo systemctl start getcontact-orchestrator
sudo systemctl start getcontact-whatsapp

# Check status
sudo systemctl status getcontact-orchestrator
sudo systemctl status getcontact-whatsapp
```

### Post-Deploy Verification

**Docker Deployment:**

```bash
cd /opt/getcontact-ai-agent
docker compose -f docker-compose.prod.yml exec -T orchestrator python scripts/test_auth_permissions.py
curl -sf http://localhost:8000/health
curl -sf http://localhost:3100/status
```

**Systemd Deployment:**

```bash
cd /opt/getcontact/app
sudo -u getcontact venv/bin/python scripts/test_auth_permissions.py
curl -sf http://localhost:8000/health
curl -sf http://localhost:3100/status
```

### Nginx Reverse Proxy

**Configuration (`/etc/nginx/sites-available/getcontact`):**

```nginx
# Upstream servers
upstream orchestrator {
    server 127.0.0.1:8000;
}

upstream whatsapp {
    server 127.0.0.1:3100;
}

# HTTP to HTTPS redirect
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Orchestrator API
    location /api/ {
        proxy_pass http://orchestrator;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Webhook endpoint
    location /webhook/ {
        proxy_pass http://orchestrator;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Frontend (static files)
    location / {
        proxy_pass http://orchestrator;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Enable Site:**

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/getcontact /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

---

## Production Setup

### SSL Certificate (Let's Encrypt)

**Install Certbot:**

```bash
sudo apt-get install -y certbot python3-certbot-nginx
```

**Obtain Certificate:**

```bash
sudo certbot --nginx -d your-domain.com
```

**Auto-Renewal:**

```bash
# Test renewal
sudo certbot renew --dry-run

# Renewal is automated via cron
```

### Database Optimization

**SQLite Configuration:**

```python
# In orchestrator/db.py

async def get_db_connection():
    """Get optimized database connection."""
    db = await aiosqlite.connect(DATABASE_PATH)
    # Enable WAL mode for better concurrency
    await db.execute("PRAGMA journal_mode=WAL")
    # Optimize for production
    await db.execute("PRAGMA synchronous=NORMAL")
    await db.execute("PRAGMA cache_size=10000")
    await db.execute("PRAGMA temp_store=MEMORY")
    return db
```

### Log Rotation

**Create `/etc/logrotate.d/getcontact`:**

```
/var/log/getcontact/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 getcontact getcontact
    sharedscripts
    postrotate
        systemctl reload getcontact-orchestrator > /dev/null 2>&1 || true
        systemctl reload getcontact-whatsapp > /dev/null 2>&1 || true
    endscript
}
```

### Monitoring Setup

**Install Monitoring Tools:**

```bash
# System monitoring
sudo apt-get install -y htop iotop

# Process monitoring
sudo apt-get install -y net-tools
```

**Create Health Check Script (`/usr/local/bin/getcontact-healthcheck`):**

```bash
#!/bin/bash

# Check orchestrator
if ! curl -f -s http://localhost:8000/ > /dev/null; then
    echo "ERROR: Orchestrator is down"
    systemctl restart getcontact-orchestrator
fi

# Check WhatsApp service
if ! curl -f -s http://localhost:3100/status > /dev/null; then
    echo "ERROR: WhatsApp service is down"
    systemctl restart getcontact-whatsapp
fi
```

**Add to Cron:**

```bash
# Run every 5 minutes
crontab -e
*/5 * * * * /usr/local/bin/getcontact-healthcheck
```

---

## Monitoring & Logging

### Log Locations

**Docker Deployment:**
```bash
# View logs
docker-compose logs -f orchestrator
docker-compose logs -f whatsapp-service

# Specific service
docker-compose logs --tail=100 orchestrator
```

**Manual Deployment:**
- Orchestrator: `/var/log/getcontact/orchestrator.log`
- WhatsApp Service: `/var/log/getcontact/whatsapp.log`
- Application logs: `/opt/getcontact/app/logs/`

### Log Levels

**Configure in `.env`:**

```bash
# Python logging
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Node.js logging (requires code change)
# In whatsapp-service/src/index.ts
const logger = pino({ level: 'info' });
```

### Metrics Collection

**Database Queries:**

```sql
-- University count by status
SELECT status, COUNT(*) as count
FROM universities
GROUP BY status;

-- Conversation success rate
SELECT state, COUNT(*) as count
FROM conversations
GROUP BY state;

-- Daily quota tracking
SELECT date, conversations_started, messages_sent
FROM daily_quota
ORDER BY date DESC
LIMIT 7;
```

**API Endpoint for Stats:**

```bash
curl http://localhost:8000/api/v1/dashboard/stats
```

### Alerting

**Recommended Alerts:**

1. **Service Down:** Any service not responding
2. **WhatsApp Disconnected:** Connection lost > 5 minutes
3. **Database Errors:** SQLite lock errors
4. **API Rate Limits:** OpenAI quota exceeded
5. **Disk Space:** < 10% free
6. **Memory Usage:** > 90% sustained

---

## Backup & Recovery

### Automated Backups

**Database Backup Script (`/usr/local/bin/backup-getcontact`):**

```bash
#!/bin/bash

BACKUP_DIR="/opt/getcontact/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_PATH="/opt/getcontact/app/data/getcontact.db"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database
cp "$DB_PATH" "$BACKUP_DIR/getcontact_$DATE.db"

# Compress
gzip "$BACKUP_DIR/getcontact_$DATE.db"

# Keep last 30 days
find "$BACKUP_DIR" -name "*.db.gz" -mtime +30 -delete

echo "Backup completed: getcontact_$DATE.db.gz"
```

**Add to Cron:**

```bash
# Daily backup at 2 AM
0 2 * * * /usr/local/bin/backup-getcontact
```

### WhatsApp Auth Backup

**Docker:**
```bash
# Backup auth volume
docker run --rm -v getcontact_whatsapp-auth:/data -v $(pwd):/backup \
  alpine tar czf /backup/whatsapp-auth-$(date +%Y%m%d).tar.gz -C /data .
```

**Manual:**
```bash
# Backup auth store
cp -r /opt/getcontact/app/whatsapp-service/auth_store \
  /opt/getcontact/backups/auth_store-$(date +%Y%m%d)
```

### Recovery Procedure

**Database Recovery:**

```bash
# Stop services
systemctl stop getcontact-orchestrator

# Restore database
cp /opt/getcontact/backups/getcontact_20250225.db.gz /tmp/
gunzip /tmp/getcontact_20250225.db.gz
cp /tmp/getcontact_20250225.db /opt/getcontact/app/data/getcontact.db

# Start services
systemctl start getcontact-orchestrator
```

**WhatsApp Auth Recovery:**

```bash
# Stop service
systemctl stop getcontact-whatsapp

# Restore auth
rm -rf /opt/getcontact/app/whatsapp-service/auth_store/*
cp -r /opt/getcontact/backups/auth_store-20250225/* \
  /opt/getcontact/app/whatsapp-service/auth_store/

# Start service
systemctl start getcontact-whatsapp
```

---

## Security Hardening

### Application Security

**1. Environment Variables:**

```bash
# Restrict file permissions
chmod 600 /opt/getcontact/app/.env
chown getcontact:getcontact /opt/getcontact/app/.env
```

**2. API Authentication (Future):**

```python
# Add to orchestrator/main.py
from fastapi import Header, HTTPException

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != cfg.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
```

**3. Rate Limiting:**

```python
# Add to orchestrator/main.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/v1/universities")
@limiter.limit("100/minute")
async def get_universities():
    ...
```

### System Security

**1. Firewall:**

```bash
# Configure UFW
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

**2. SSH Hardening:**

```bash
# Edit /etc/ssh/sshd_config
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes

# Restart SSH
sudo systemctl restart sshd
```

**3. System Updates:**

```bash
# Automatic security updates
sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### Data Privacy

**1. Encryption at Rest:**

```bash
# Encrypt backup directory
sudo apt-get install -y cryptsetup
```

**2. Data Retention:**

```sql
-- Delete old conversation history
DELETE FROM conversations WHERE created_at < datetime('now', '-1 year');

-- Delete old API logs
DELETE FROM api_logs WHERE created_at < datetime('now', '-90 days');
```

---

## Performance Tuning

### Database Optimization

**1. Indexing:**

```sql
-- Add indexes for common queries
CREATE INDEX IF NOT EXISTS idx_universities_status ON universities(status);
CREATE INDEX IF NOT EXISTS idx_conversations_state ON conversations(state);
CREATE INDEX IF NOT EXISTS idx_conversations_phone ON conversations(contact_phone);
CREATE INDEX IF NOT EXISTS idx_ig_posts_university ON ig_posts(university_id);
```

**2. Query Optimization:**

```python
# Use LIMIT for pagination
await db.execute_fetchall(
    "SELECT * FROM universities WHERE status = ? LIMIT ? OFFSET ?",
    (status, limit, offset)
)

# Use transactions for bulk operations
async with aiosqlite.connect(DATABASE_PATH) as db:
    await db.execute("BEGIN")
    try:
        # Multiple operations
        await db.executemany(...)
        await db.commit()
    except Exception:
        await db.rollback()
```

### Application Tuning

**1. Increase Worker Processes:**

```bash
# Use Gunicorn for production
pip install gunicorn

gunicorn orchestrator.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

**2. Adjust Configuration:**

```bash
# In .env
MAX_AI_CONCURRENT=10  # Increase for more parallel AI calls
SEND_INTERVAL_MS=2000  # Reduce for faster sending (careful!)
MIN_MESSAGE_GAP_SECONDS=120  # Reduce for more frequent outreach
```

### Caching

**Add Redis (Optional):**

```yaml
# Add to docker-compose.yml
redis:
  image: redis:alpine
  ports:
    - "6379:6379"
  restart: unless-stopped
```

```python
# Use in orchestrator
import redis

redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)

# Cache API responses
def get_universities_cached():
    cached = redis_client.get('universities')
    if cached:
        return json.loads(cached)

    data = await get_universities()
    redis_client.setex('universities', 300, json.dumps(data))
    return data
```

---

## Troubleshooting

### Common Deployment Issues

**1. Services Won't Start**

```bash
# Check logs
docker-compose logs orchestrator
# or
journalctl -u getcontact-orchestrator -f

# Check port conflicts
sudo netstat -tulpn | grep LISTEN

# Check disk space
df -h
```

**2. Database Locked**

```bash
# Check for long-running connections
lsof /opt/getcontact/app/data/getcontact.db

# Restart services
systemctl restart getcontact-orchestrator
```

**3. WhatsApp Auth Issues**

```bash
# Clear auth and restart
rm -rf /opt/getcontact/app/whatsapp-service/auth_store/*
systemctl restart getcontact-whatsapp

# Check logs
tail -f /var/log/getcontact/whatsapp.log
```

**4. High Memory Usage**

```bash
# Check memory
free -h

# Check process memory
ps aux --sort=-%mem | head

# Restart if needed
systemctl restart getcontact-orchestrator
```

### Health Checks

**Manual Health Check:**

```bash
#!/bin/bash

echo "Checking services..."

# Orchestrator
if curl -f -s http://localhost:8000/ > /dev/null; then
    echo "✓ Orchestrator: OK"
else
    echo "✗ Orchestrator: FAILED"
fi

# WhatsApp Service
if curl -f -s http://localhost:3100/status > /dev/null; then
    echo "✓ WhatsApp Service: OK"
else
    echo "✗ WhatsApp Service: FAILED"
fi

# Database
if [ -f /opt/getcontact/app/data/getcontact.db ]; then
    echo "✓ Database: OK"
else
    echo "✗ Database: FAILED"
fi

# Disk space
DISK_USAGE=$(df /opt/getcontact | awk 'NR==2 {print $5}' | sed 's/%//')
if [ $DISK_USAGE -lt 90 ]; then
    echo "✓ Disk Space: OK ($DISK_USAGE%)"
else
    echo "✗ Disk Space: LOW ($DISK_USAGE%)"
fi
```

---

## Summary

This deployment guide covers:

- **Docker deployment** using Docker Compose
- **Manual deployment** using systemd services
- **Production setup** with Nginx reverse proxy and SSL
- **Monitoring** via logs and health checks
- **Backup and recovery** procedures
- **Security hardening** recommendations
- **Performance tuning** options

For local development, see [developer-guide.md](developer-guide.md).
For system architecture, see [architecture.md](architecture.md).
For end-user documentation, see [user-guide.md](user-guide.md).
