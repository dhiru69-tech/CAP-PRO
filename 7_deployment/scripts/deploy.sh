#!/bin/bash
# ══════════════════════════════════════════════════════════════
#  ReconMind — Production Deployment Script
#
#  Usage:
#    chmod +x scripts/deploy.sh
#    ./scripts/deploy.sh
#
#  What it does:
#    1. Checks prerequisites (Docker, .env file)
#    2. Pulls latest images / builds containers
#    3. Runs database migrations
#    4. Starts all services
#    5. Runs health checks
# ══════════════════════════════════════════════════════════════

set -e  # Exit on any error

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
RESET="\033[0m"

COMPOSE_FILE="7_deployment/docker-compose.yml"
ENV_FILE=".env"

log()     { echo -e "${BLUE}[ReconMind]${RESET} $1"; }
success() { echo -e "${GREEN}[✓]${RESET} $1"; }
warn()    { echo -e "${YELLOW}[!]${RESET} $1"; }
error()   { echo -e "${RED}[✗]${RESET} $1"; exit 1; }

echo ""
echo -e "${BOLD}══════════════════════════════════════${RESET}"
echo -e "${BOLD}  ReconMind — Deployment Script${RESET}"
echo -e "${BOLD}══════════════════════════════════════${RESET}"
echo ""

# ─────────────────────────────────────
# Step 1: Prerequisites check
# ─────────────────────────────────────
log "Checking prerequisites..."

command -v docker >/dev/null 2>&1 || error "Docker not installed. Install from https://docker.com"
command -v docker compose >/dev/null 2>&1 || error "Docker Compose not found. Update Docker to latest version."
success "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"

# Check .env
if [ ! -f "$ENV_FILE" ]; then
    warn ".env file not found. Creating from template..."
    cp 7_deployment/.env.example .env
    error "Please fill in .env before deploying:\n  nano .env\n  Then run this script again."
fi

# Check required env vars
source .env
REQUIRED_VARS=("POSTGRES_PASSWORD" "GOOGLE_CLIENT_ID" "GOOGLE_CLIENT_SECRET" "JWT_SECRET_KEY")
for var in "${REQUIRED_VARS[@]}"; do
    val="${!var}"
    if [ -z "$val" ] || [[ "$val" == *"CHANGE_THIS"* ]] || [[ "$val" == *"your-"* ]] || [[ "$val" == *"GENERATE"* ]]; then
        error "Required variable $var is not set in .env"
    fi
done
success "Environment variables validated"

# ─────────────────────────────────────
# Step 2: Build containers
# ─────────────────────────────────────
log "Building Docker containers..."
docker compose -f "$COMPOSE_FILE" build --no-cache
success "Containers built"

# ─────────────────────────────────────
# Step 3: Start database first
# ─────────────────────────────────────
log "Starting database..."
docker compose -f "$COMPOSE_FILE" up -d db

log "Waiting for database to be ready..."
sleep 5
until docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U "$POSTGRES_USER" > /dev/null 2>&1; do
    echo -n "."
    sleep 2
done
echo ""
success "Database is ready"

# ─────────────────────────────────────
# Step 4: Start all services
# ─────────────────────────────────────
log "Starting all services..."
docker compose -f "$COMPOSE_FILE" up -d
success "All services started"

# ─────────────────────────────────────
# Step 5: Health checks
# ─────────────────────────────────────
log "Running health checks..."
sleep 8

# Check backend
BACKEND_HEALTH=$(curl -sf http://localhost:8000/health 2>/dev/null || echo "FAIL")
if [[ "$BACKEND_HEALTH" == *"healthy"* ]]; then
    success "Backend API is healthy"
else
    warn "Backend health check failed. Check: docker logs reconmind_backend"
fi

# Check nginx
NGINX_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost 2>/dev/null || echo "000")
if [ "$NGINX_STATUS" = "200" ] || [ "$NGINX_STATUS" = "301" ] || [ "$NGINX_STATUS" = "302" ]; then
    success "Nginx is serving (HTTP $NGINX_STATUS)"
else
    warn "Nginx check: HTTP $NGINX_STATUS. Check: docker logs reconmind_nginx"
fi

# ─────────────────────────────────────
# Done
# ─────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════${RESET}"
echo -e "${GREEN}${BOLD}  🚀 ReconMind Deployed!${RESET}"
echo -e "${BOLD}══════════════════════════════════════${RESET}"
echo ""
echo -e "  ${BOLD}Frontend:${RESET}   http://localhost"
echo -e "  ${BOLD}API:${RESET}        http://localhost:8000"
echo -e "  ${BOLD}API Docs:${RESET}   http://localhost:8000/docs"
echo ""
echo -e "  Logs:    ${BLUE}docker compose -f $COMPOSE_FILE logs -f${RESET}"
echo -e "  Stop:    ${BLUE}docker compose -f $COMPOSE_FILE down${RESET}"
echo -e "  Status:  ${BLUE}docker compose -f $COMPOSE_FILE ps${RESET}"
echo ""
