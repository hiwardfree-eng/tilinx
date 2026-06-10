# TilinX — Contributing Guide

## Convenciones
- **Código**: Python 3.10+, sin tipado forzado, sin comentarios inline
- **Commits**: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- **Ramas**: `feature/<nombre>` desde `develop`
- **PRs**: a `develop` siempre, mínimo 1 reviewer

## Estructura
```
tilinx/
├── bot_control.py       # Bot Telegram
├── tilinx_proxy.py      # Addon mitmproxy
├── config.py            # Config centralizada
├── database.py          # DB ips.json
├── cache.py             # Caché en memoria
├── logger.py            # Logging
├── utils.py             # Helpers
├── monitor.py           # Métricas
├── src/
│   ├── dashboard.py     # Flask dashboard
│   └── templates/       # HTML templates
├── config/
│   ├── __init__.py      # Config jerárquica
│   ├── *.env            # Entornos
├── tests/
│   └── test_all.py      # Tests unitarios
├── scripts/
│   ├── backup.py/sh     # Backups
│   ├── restore.sh       # Restore
│   ├── reports.py/sh    # Reportes
│   └── run_tests.sh     # Test runner
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md
│   ├── SCALABILITY.md
│   └── CONVENTIONS.md
└── .github/workflows/
    └── ci-cd.yml
```

## Primera vez
```bash
git clone <repo-url>
cd tilinx
bash install.sh
bash scripts/run_tests.sh
git checkout -b feature/mi-feature develop
```

## Código de conducta
1. No pushear directo a `main`
2. No exponer tokens/keys en commits
3. Correr tests antes de cada PR
