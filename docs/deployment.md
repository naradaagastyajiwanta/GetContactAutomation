# GCP Compute Engine — Deployment Guide

## Prerequisites

Before starting, make sure you have:
- GCP account with billing enabled
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- SSH key pair for VM access

---

## Step 1: Create the VM

```bash
# Set your project
gcloud config set project YOUR_PROJECT_ID

# Create VM (Ubuntu 22.04 LTS, 4 vCPU, 8 GB RAM)
gcloud compute instances create getcontact-server \
  --zone=asia-southeast2-a \
  --machine-type=e2-standard-2 \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB \
  --boot-disk-type=pd-ssd \
  --tags=http-server,https-server \
  --enable-display-device \
  --no-shielded-secure-boot

# Open firewall ports
gcloud compute firewall-rules create allow-http \
  --allow=tcp:80,tcp:3200,tcp:8000,tcp:3100 \
  --target-tags=http-server \
  --description="Allow HTTP traffic for GetContact AI"

# Get the external IP
gcloud compute instances describe getcontact-server \
  --zone=asia-southeast2-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

---

## Step 2: SSH into VM and Install Docker

```bash
# SSH into VM
gcloud compute ssh getcontact-server --zone=asia-southeast2-a

# Once inside the VM:
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# Add Docker GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Add Docker repo
echo \
  "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add current user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify Docker
docker --version
docker compose version
```

---

## Step 3: Create GCP Service Account for GitLab CI (Recommended)

Instead of using root SSH keys, create a dedicated service account for deployments:

```bash
# Create service account
gcloud iam service-accounts create gitlab-deploy \
  --display-name="GitLab CI Deploy"

# Grant permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:gitlab-deploy@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/compute.instanceAdmin.v1"

# Create key (download the JSON)
gcloud iam service-accounts keys create gitlab-deploy-key.json \
  --iam-account=gitlab-deploy@YOUR_PROJECT_ID.iam.gserviceaccount.com

# The JSON content goes into GitLab CI/CD variable: GCP_SERVICE_ACCOUNT_KEY
```

For simpler setup (acceptable for small teams), use SSH key method instead:

```bash
# On your LOCAL machine, generate SSH key
ssh-keygen -t ed25519 -C "gitlab-ci" -f gitlab_deploy_key

# Copy public key to VM
gcloud compute scp gitlab_deploy_key.pub \
  getcontact-server:/tmp/gitlab_deploy_key.pub \
  --zone=asia-southeast2-a

# Add to authorized_keys on VM
gcloud compute ssh getcontact-server --zone=asia-southeast2-a \
  --command="cat /tmp/gitlab_deploy_key.pub >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

# Copy private key content to GitLab CI/CD variable: SSH_PRIVATE_KEY
cat gitlab_deploy_key
```

---

## Step 4: Prepare Deployment Directory on VM

```bash
gcloud compute ssh getcontact-server --zone=asia-southeast2-a

# Create deployment directory
sudo mkdir -p /var/www/get_contact_jiwan
sudo chown $USER:$USER /var/www/get_contact_jiwan
cd /var/www/get_contact_jiwan

# Create data directories (for volume mounts)
mkdir -p data data/audiensi_docs data/templates data/ig_sessions data/pw_sessions
mkdir -p whatsapp-service/auth_store whatsapp-service/auth_store_backup \
       whatsapp-service/auth_store_device_1 whatsapp-service/auth_store_device_2 \
       whatsapp-service/auth_store_device_3 whatsapp-service/auth_store_device_4 \
       whatsapp-service/auth_store_device_5 whatsapp-service/data

# Create production env file
nano .env.production
```

### `.env.production` template:

```bash
# ============================================================
# .env.production — GetContact AI Agent
# ============================================================

# CORE (REQUIRED)
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...

# SERVICE URLs (for internal Docker networking)
WA_SERVICE_URL=http://whatsapp:3100
WEBHOOK_URL=http://orchestrator:8000/webhook/incoming
DATABASE_PATH=data/getcontact.db

# INSTAGRAM SCRAPING
IG_SESSION_ID=...
APIFY_API_KEY=...

# OPERATION LIMITS
MAX_DAILY_CONVERSATIONS=20
MIN_MESSAGE_GAP_SECONDS=300
OUTREACH_START_HOUR=7
OUTREACH_END_HOUR=22

# EMAIL / SMTP (if using email blast)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=your@email.com
SMTP_PASSWORD=your-app-password
SMTP_USE_SSL=true

# AUTH
AUTH_COOKIE_NAME=dms_marketing_session
AUTH_SESSION_TTL_HOURS=12
AUTH_COOKIE_SECURE=false
AUTH_DEFAULT_PASSWORD=CHANGE_THIS_PASSWORD
AUTH_DEFAULT_ROLE=viewer
```

---

## Step 5: Clone Repository (Initial Setup on VM)

```bash
# On the VM, clone the repo
cd /var/www/get_contact_jiwan
git clone https://gitlab.com/YOUR_USERNAME/getcontact-ai.git .
git checkout main

# Pull Docker images (pre-built from Docker Hub)
docker compose -f docker-compose.prod.yml pull

# Start services
docker compose -f docker-compose.prod.yml up -d

# Check status
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=20
```

---

## Step 6: Configure GitLab CI/CD Variables

Go to **GitLab → Settings → CI/CD → Variables**:

| Variable | Value | Type | Notes |
|---|---|---|---|
| `SSH_PRIVATE_KEY` | Content of `gitlab_deploy_key` (private) | File | Without `-----BEGIN OPENSSH PRIVATE KEY-----` header |
| `VPS_HOST` | External IP of your GCP VM | Variable | e.g. `34.XX.XX.XX` |
| `VPS_USER` | `ubuntu` (or your SSH user) | Variable | |
| `SSH_KNOWN_HOSTS` | Output of `ssh-keyscan VM_IP` | Variable | For strict host key verification |
| `DOCKERHUB_USER` | `naradaagastya` | Variable | Docker Hub username |
| `DOCKERHUB_TOKEN` | Your Docker Hub PAT | Variable | Create at hub.docker.com → Account Settings → Security |
| `DEPLOY_DIR` | `/var/www/get_contact_jiwan` | Variable | Override default |
| `DEPLOY_TOKEN_USER` | GitLab deploy token user | Variable | Optional: for private repos |
| `DEPLOY_TOKEN_PASS` | GitLab deploy token password | Variable | Optional: for private repos |

### How to get `SSH_KNOWN_HOSTS`:

```bash
# On your local machine
ssh-keyscan -H YOUR_VM_IP >> ~/.ssh/known_hosts
cat ~/.ssh/known_hosts | grep YOUR_VM_IP
```

Copy that line as the value of `SSH_KNOWN_HOSTS` in GitLab.

---

## Step 7: Register GitLab Runner (Optional — Alternative to DinD)

If you prefer a persistent runner instead of Docker-in-Docker:

```bash
# On the VM
curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | sudo bash
sudo apt-get install gitlab-runner
sudo gitlab-runner register

# URL: https://gitlab.com CI/CD → Settings → CI/CD → Runners → Specific runners
# Token: from GitLab CI/CD → Settings → Runners
# Executor: docker
# Docker image: docker:27
```

For this project, **Docker-in-Docker (DinD) is already configured in `.gitlab-ci.yml`**, so a runner is optional.

---

## Step 8: First Deploy via GitLab CI

1. Push any change to `main` branch
2. Go to **GitLab → CI/CD → Pipelines**
3. Watch the pipeline run: `build → deploy → verify`
4. If verify stage passes → deployment successful

---

## Useful Commands on the VM

```bash
# View all container logs
docker compose -f docker-compose.prod.yml logs -f

# View specific service
docker compose -f docker-compose.prod.yml logs -f orchestrator
docker compose -f docker-compose.prod.yml logs -f whatsapp

# Restart a service
docker compose -f docker-compose.prod.yml restart whatsapp

# Stop everything
docker compose -f docker-compose.prod.yml down

# Full restart (pull latest + restart)
docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d --remove-orphans

# Check resource usage
docker stats --no-stream

# SSH into a container
docker exec -it gc-orchestrator bash
docker exec -it gc-whatsapp sh

# Backup auth stores (IMPORTANT — WhatsApp sessions)
tar -czf /tmp/auth_backup_$(date +%Y%m%d).tar.gz whatsapp-service/auth_store* && \
  cp /tmp/auth_backup_*.tar.gz /var/www/backups/

# Clean unused Docker resources
docker system prune -f --filter "until=72h"
```

---

## Nginx Reverse Proxy (Optional — for HTTPS)

If you want HTTPS with Let's Encrypt:

```bash
sudo apt install -y certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d get-contact-automation.airabot.id

# Auto-renew
sudo certbot renew --dry-run
```

---

## Troubleshooting

### WhatsApp disconnected after deploy
```bash
docker compose -f docker-compose.prod.yml exec whatsapp sh
# Then scan QR code from logs
docker compose -f docker-compose.prod.yml logs whatsapp | grep QR
```

### Database migration needed after update
```bash
docker compose -f docker-compose.prod.yml exec orchestrator python scripts/migrate_marketing.py
```

### Out of disk space
```bash
docker system prune -a -f --volumes
```
