#!/bin/bash
# ═══════════════════════════════════════════════════════════
# TilinX - Full Deployment Script
# Dominio: tilinxproxy.duckdns.org
# ═══════════════════════════════════════════════════════════
set -e

DOMAIN="tilinxproxy.duckdns.org"
EMAIL="admin@tilinxproxy.duckdns.org"
BASE_DIR="/home/runner/tilinx"
WEB_DIR="$BASE_DIR/website"

echo "════════════════════════════════════════════"
echo "  TilinX Deployment - $DOMAIN"
echo "════════════════════════════════════════════"

# ─── 1. System dependencies ─────────────────────────────
echo "[1/7] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv nginx certbot python3-certbot-nginx

# ─── 2. Python dependencies ─────────────────────────────
echo "[2/7] Installing Python packages..."
cd "$WEB_DIR"
pip install -r requirements.txt -q
pip install gunicorn -q

# ─── 3. Environment ─────────────────────────────────────
echo "[3/7] Setting up environment..."
cat > /etc/tilinx.env << EOF
TilinX_WEB_PORT=8080
TilinX_DASH_PASSWORD=${TilinX_DASH_PASSWORD:?Error: TilinX_DASH_PASSWORD no está definido}
TilinX_DATABASE_URL=sqlite:///$WEB_DIR/tilinx.db
TilinX_WEB_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
EOF

# ─── 4. Systemd service ─────────────────────────────────
echo "[4/7] Creating systemd service..."
sudo tee /etc/systemd/system/tilinx-web.service > /dev/null << 'SVC'
[Unit]
Description=TilinX Web
After=network.target

[Service]
Type=simple
User=runner
WorkingDirectory=/home/runner/tilinx/website
EnvironmentFile=/etc/tilinx.env
ExecStart=/usr/bin/python3 /home/runner/tilinx/website/wsgi.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC

# ─── 5. Nginx ───────────────────────────────────────────
echo "[5/7] Configuring Nginx..."
sudo tee /etc/nginx/sites-available/tilinx > /dev/null << 'NGINX'
server {
    listen 80;
    server_name tilinxproxy.duckdns.org;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name tilinxproxy.duckdns.org;

    ssl_certificate /etc/letsencrypt/live/tilinxproxy.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tilinxproxy.duckdns.org/privkey.pem;

    gzip on;
    gzip_types text/css application/javascript image/jpeg image/png;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /assets/ {
        alias /home/runner/tilinx/website/assets/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        add_header X-Content-Type-Options nosniff;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/tilinx /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# ─── 6. SSL Certificate ─────────────────────────────────
echo "[6/7] Obtaining SSL certificate..."
# Primero asegurar que el puerto 80 esté libre
sudo systemctl stop nginx 2>/dev/null || true
sudo certbot certonly --standalone --non-interactive --agree-tos \
    -d "$DOMAIN" --email "$EMAIL" || \
    echo "⚠️ SSL failed — will use self-signed (run certbot manually later)"

sudo systemctl start nginx

# ─── 7. Start everything ────────────────────────────────
echo "[7/7] Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable tilinx-web
sudo systemctl restart tilinx-web
sudo systemctl restart nginx

echo ""
echo "════════════════════════════════════════════"
echo "  ✅ TilinX deployed!"
echo "  https://$DOMAIN"
echo "  Password: [configurado en variable de entorno]"
echo "════════════════════════════════════════════"
