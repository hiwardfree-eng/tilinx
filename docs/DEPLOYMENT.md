# TilinX — Despliegue

## Requisitos
- Python 3.10+
- pip (python-telegram-bot, requests, mitmproxy, flask)
- Linux (Ubuntu/Debian recomendado)

## Instalación Rápida
```bash
git clone <repo-url> ~/tilinx
cd ~/tilinx
bash install.sh
```

## Configuración
```bash
export TilinX_BOT_TOKEN=tu_token_aqui
export TilinX_ADMIN_ID=123456789
export TilinX_PROXY_ENABLED=false
```

### Proxy SOCKS5 (opcional)
```bash
export TilinX_PROXY_ENABLED=true
export TilinX_PROXY_TYPE=socks5
export TilinX_PROXY_HOST=127.0.0.1
export TilinX_PROXY_PORT=1080
export TilinX_PROXY_USER=user
export TilinX_PROXY_PASS=pass
```

## Inicio
```bash
# Solo bot
bash start_bot.sh

# Solo proxy (mitmproxy)
bash start_proxy.sh

# Ambos
bash start_all.sh

# Dashboard
bash src/start_dashboard.sh

# Estado
bash status.sh

# Detener
bash stop_all.sh
```

## Testing
```bash
bash scripts/run_tests.sh
```

## Backups
```bash
# Manual
bash scripts/backup.sh

# Restore
bash scripts/restore.sh backups/uids_backup_20260101_120000.json
```

## CI/CD
- GitHub Actions en `.github/workflows/ci-cd.yml`
- Push a `main` → tests + lint → build
- Push a `testing` → tests + lint
- Push a `develop` → tests

## Git Workflow
```bash
main ← testing ← develop ← feature/*
```
- `feature/*` → PR a `develop`
- `develop` → merge a `testing`
- `testing` → merge a `main` (producción)
