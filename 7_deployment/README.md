# ReconMind — Deployment Guide

Complete deployment instructions for all environments.

---

## Prerequisites

- Docker + Docker Compose installed on your server
- A domain name pointing to your server IP
- Google OAuth credentials (for login)

---

## Quick Deploy (5 minutes)

```bash
# 1. Clone / extract project
cd ReconMind_Complete

# 2. Set environment variables
cp 7_deployment/.env.example .env
nano .env          # Fill in POSTGRES_PASSWORD, GOOGLE keys, JWT_SECRET

# 3. One-click deploy
chmod +x 7_deployment/scripts/deploy.sh
./7_deployment/scripts/deploy.sh
```

That's it! The script:
- Validates your `.env`
- Builds all 4 Docker containers
- Starts DB, Backend, Scanner, AI Worker, Nginx
- Runs health checks

---

## Deployment Architecture

```
Internet
   │
   ▼
[Nginx :80/:443]
   │  Static frontend files
   │  /api/* → proxied to backend
   │  /auth/* → proxied to backend
   │
   ▼
[FastAPI Backend :8000]
   │  REST API
   │  Handles auth, scans, AI routes, reports
   │
   ├──────────────────────────┐
   ▼                          ▼
[PostgreSQL DB]        [AI Worker (background)]
   ▲                          │ reads completed scans
   │                          │ writes risk levels + summaries
[Scanner Worker]              │
  reads PENDING scans         │
  writes results ─────────────┘
```

---

## Files in this folder

| File | Purpose |
|------|---------|
| `docker-compose.yml`     | Full production stack |
| `docker-compose.dev.yml` | Dev overrides (hot reload) |
| `.env.example`           | Environment template |
| `docker/Dockerfile.backend`  | Backend + AI worker container |
| `docker/Dockerfile.scanner`  | Scanner worker container |
| `nginx/nginx.conf`           | Reverse proxy + SSL config |
| `scripts/deploy.sh`          | One-click deploy |
| `scripts/setup_ssl.sh`       | Let's Encrypt SSL setup |
| `scripts/backup_db.sh`       | PostgreSQL backup |
| `github-actions/deploy.yml`  | CI/CD pipeline |

---

## Commands

```bash
# Start everything
docker compose -f 7_deployment/docker-compose.yml up -d

# Stop everything
docker compose -f 7_deployment/docker-compose.yml down

# View logs (all services)
docker compose -f 7_deployment/docker-compose.yml logs -f

# View logs (single service)
docker compose -f 7_deployment/docker-compose.yml logs -f backend
docker compose -f 7_deployment/docker-compose.yml logs -f scanner
docker compose -f 7_deployment/docker-compose.yml logs -f ai_worker

# Rebuild after code changes
docker compose -f 7_deployment/docker-compose.yml build
docker compose -f 7_deployment/docker-compose.yml up -d

# Check status
docker compose -f 7_deployment/docker-compose.yml ps

# Database shell
docker exec -it reconmind_db psql -U reconmind
```

---

## Development Mode

```bash
# Hot reload — code changes reflect immediately
docker compose \
  -f 7_deployment/docker-compose.yml \
  -f 7_deployment/docker-compose.dev.yml \
  up
```

---

## SSL Setup

```bash
# After initial deploy, add HTTPS:
chmod +x 7_deployment/scripts/setup_ssl.sh
./7_deployment/scripts/setup_ssl.sh yourdomain.com your@email.com
```

This installs a Let's Encrypt certificate and sets up auto-renewal.

---

## Database Backup

```bash
# Manual backup
./7_deployment/scripts/backup_db.sh

# Automated (add to crontab):
0 2 * * * /path/to/reconmind/7_deployment/scripts/backup_db.sh
```

Backups are stored in `./backups/` and auto-deleted after 7 days.

---

## CI/CD with GitHub Actions

1. Push your code to GitHub
2. Add these secrets in **Settings → Secrets → Actions**:
   - `SERVER_HOST` — your server IP
   - `SERVER_USER` — SSH username (e.g. ubuntu)
   - `SERVER_SSH_KEY` — private SSH key
   - `DEPLOY_PATH` — `/home/ubuntu/reconmind`
3. Every push to `main` → auto-deploy

Workflow: `7_deployment/github-actions/deploy.yml`

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `POSTGRES_PASSWORD` | ✅ | Strong DB password |
| `GOOGLE_CLIENT_ID`  | ✅ | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | ✅ | Google OAuth secret |
| `JWT_SECRET_KEY`    | ✅ | Random 32-byte hex string |
| `GOOGLE_REDIRECT_URI` | ✅ | `https://yourdomain.com/auth/google/callback` |
| `SERPAPI_KEY`       | Optional | For better scan results |

Generate JWT secret:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## VPS Recommendations

| Provider | Minimum Spec | Cost |
|----------|-------------|------|
| DigitalOcean Droplet | 2 vCPU / 4GB RAM | ~$24/mo |
| Hetzner CX22 | 2 vCPU / 4GB RAM | ~€4/mo |
| AWS EC2 t3.medium | 2 vCPU / 4GB RAM | ~$30/mo |
| Linode 4GB | 2 vCPU / 4GB RAM | ~$24/mo |

For AI model (Phase 5 trained): GPU instance recommended.
