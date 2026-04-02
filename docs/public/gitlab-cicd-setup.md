# GitLab CI/CD Setup Guide

## Overview

Pipeline otomatis saat push ke `main`:

```
Push to main → GitLab CI builds Docker images → Push ke Docker Hub → SSH ke VPS → docker compose pull → up -d
```

**Keuntungan**: Server **tidak perlu build** — tinggal pull image jadi dari Docker Hub. Hemat CPU & waktu.

---

## Setup (Sekali saja)

### 1. Docker Hub — Login di VPS

SSH ke VPS dan login Docker Hub (sekali, credentials tersimpan):
```bash
ssh root@103.253.145.84
docker login -u naradaagastya
# Password: <Docker Hub access token>
```

Setelah login, VPS bisa pull image dari `naradaagastya/gc-*`.

### 2. Buat SSH Key untuk CI/CD

Di local:
```bash
ssh-keygen -t ed25519 -C "gitlab-ci-deploy" -f ~/.ssh/gitlab_deploy_key
ssh-copy-id -i ~/.ssh/gitlab_deploy_key.pub root@103.253.145.84
```

Test:
```bash
ssh -i ~/.ssh/gitlab_deploy_key root@103.253.145.84 "echo OK"
```

### 3. Buat GitLab Deploy Token

1. GitLab → Project → **Settings → Repository → Deploy tokens**
2. Name: `vps-deploy`, Scope: `read_repository`
3. Simpan username & token

### 4. Set CI/CD Variables di GitLab

**Settings → CI/CD → Variables**:

| Variable | Type | Value | Protected | Masked |
|---|---|---|---|---|
| `SSH_PRIVATE_KEY` | **File** | Private key (`~/.ssh/gitlab_deploy_key`) | ✅ | ✅ |
| `VPS_HOST` | Variable | `103.253.145.84` | ✅ | ❌ |
| `VPS_USER` | Variable | `root` | ✅ | ❌ |
| `DOCKERHUB_USER` | Variable | `naradaagastya` | ✅ | ❌ |
| `DOCKERHUB_TOKEN` | Variable | `dckr_pat_...` | ✅ | ✅ |
| `DEPLOY_TOKEN_USER` | Variable | Deploy token username | ✅ | ❌ |
| `DEPLOY_TOKEN_PASS` | Variable | Deploy token password | ✅ | ✅ |

> **Penting**: `SSH_PRIVATE_KEY` harus type **File**!

### 5. Pastikan VPS siap

```bash
ssh root@103.253.145.84

# Pastikan .env.production ada
cd /opt/getcontact-ai-agent
nano .env.production  # Isi API keys

# Pastikan data directories ada
mkdir -p data whatsapp-service/auth_store
```

---

## Cara Pakai

### Deploy otomatis
```bash
git add .
git commit -m "feat: update dashboard"
git push origin main
```
Pipeline: **build images** (3-5 min) → **push to Docker Hub** → **SSH pull & restart** (30s) → **health check**

### Manual deploy di server (tanpa CI)
```bash
ssh root@103.253.145.84
cd /opt/getcontact-ai-agent
docker compose pull
docker compose up -d --no-build
```

---

## Pipeline Flow

```
┌──────────┐   push main   ┌────────────────┐   docker push   ┌────────────┐
│Developer │ ─────────────→ │ GitLab Runner  │ ──────────────→ │ Docker Hub │
└──────────┘                │ (builds images)│                 │ (registry) │
                            └───────┬────────┘                 └─────┬──────┘
                                    │ SSH                             │
                                    ▼                                 │
                            ┌────────────────┐   docker pull          │
                            │  VPS Server    │ ←──────────────────────┘
                            │  pulls images  │
                            │  compose up -d │
                            └────────────────┘
```

## Docker Images

| Service | Image | Port |
|---|---|---|
| Orchestrator | `naradaagastya/gc-orchestrator` | 8000 |
| Frontend | `naradaagastya/gc-frontend` | 3200 → 80 |
| WhatsApp | `naradaagastya/gc-whatsapp` | 3100 |

---

## Troubleshooting

### Pipeline gagal di build
- Check Docker Hub token masih valid
- Check Dockerfile syntax

### Pipeline gagal di SSH
- `SSH_PRIVATE_KEY` harus type **File** (bukan Variable)
- Test: `ssh -i <key> root@103.253.145.84`

### Images tidak ke-pull di VPS
- Pastikan sudah `docker login` di VPS
- Test: `docker pull naradaagastya/gc-orchestrator:latest`

### Container crash setelah deploy
```bash
ssh root@103.253.145.84
cd /opt/getcontact-ai-agent
docker compose logs --tail=50
docker compose ps
```
