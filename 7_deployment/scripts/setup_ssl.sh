#!/bin/bash
# ══════════════════════════════════════════════════════════════
#  ReconMind — SSL Certificate Setup (Let's Encrypt)
#
#  Usage:
#    chmod +x scripts/setup_ssl.sh
#    ./scripts/setup_ssl.sh yourdomain.com your@email.com
# ══════════════════════════════════════════════════════════════

set -e

DOMAIN=$1
EMAIL=$2

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
    echo "Usage: ./setup_ssl.sh yourdomain.com your@email.com"
    exit 1
fi

echo "[SSL] Setting up certificate for: $DOMAIN"

# Install certbot if not present
if ! command -v certbot &>/dev/null; then
    echo "[SSL] Installing certbot..."
    apt-get update -q && apt-get install -y certbot
fi

# Create SSL dir
mkdir -p 7_deployment/nginx/ssl

# Stop nginx temporarily for standalone mode
docker compose -f 7_deployment/docker-compose.yml stop nginx 2>/dev/null || true

# Get certificate
certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    -d "$DOMAIN"

# Copy certs to nginx ssl folder
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem 7_deployment/nginx/ssl/fullchain.pem
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem   7_deployment/nginx/ssl/privkey.pem

# Update domain in nginx.conf
sed -i "s/reconmind.yourdomain.com/$DOMAIN/g" 7_deployment/nginx/nginx.conf

echo "[SSL] ✅ Certificate installed for $DOMAIN"
echo "[SSL] Restarting nginx..."

docker compose -f 7_deployment/docker-compose.yml start nginx

echo "[SSL] Done! HTTPS is active at https://$DOMAIN"

# Auto-renewal cron
echo "[SSL] Setting up auto-renewal..."
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && \
  cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $(pwd)/7_deployment/nginx/ssl/fullchain.pem && \
  cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $(pwd)/7_deployment/nginx/ssl/privkey.pem && \
  docker exec reconmind_nginx nginx -s reload") | crontab -
echo "[SSL] Auto-renewal cron set ✅"
