# Arquitectura TilinX

## Componentes

```
┌──────────────────────────────────────────────┐
│                Telegram Bot                   │
│           (bot_control.py)                    │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐        │
│  │ config  │ │ logger  │ │ database │        │
│  └─────────┘ └─────────┘ └──────────┘        │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐        │
│  │  cache  │ │  utils  │ │ monitor  │        │
│  └─────────┘ └─────────┘ └──────────┘        │
└──────────────────────────────────────────────┘
         │ HTTP (mitmproxy external) │
         ▼
┌──────────────────────────────────────────────┐
│            tilinx_proxy.py                    │
│         (mitmproxy addon)                     │
│  → intercepta tráfico Free Fire               │
│  → cache_res / fileinfo / login detection     │
└──────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────┐
│           ips.json (shared DB)                │
└──────────────────────────────────────────────┘
```

## Flujo de datos
1. **Bot** recibe comandos de admin → añade/elimina IPs en `ips.json`
2. **Proxy** (mitmproxy) lee `ips.json` para validar acceso por IP origen
3. **Dashboard** (Flask) lee `ips.json` para mostrar métricas en tiempo real
4. **Monitor** colecta métricas de sistema (CPU, RAM, disco)
5. **Reports** genera CSVs/JSON con estadísticas de uso

## Archivos clave

| Archivo | Rol |
|---------|-----|
| `bot_control.py` | Bot Telegram (orquestador principal) |
| `tilinx_proxy.py` | Addon mitmproxy |
| `config.py` | Config centralizada + variables de entorno |
| `database.py` | CRUD sobre `ips.json` + backups |
| `cache.py` | Caché en memoria con TTL |
| `logger.py` | Logging rotativo (10 MB, 5 backups) |
| `utils.py` | Helpers (format_date, parse_duration) |
| `monitor.py` | Métricas de sistema |
| `src/dashboard.py` | Dashboard web Flask |
| `scripts/` | Instalación, start/stop, reportes, backups |

## Entornos
| Entorno | Archivo env | Rama Git | Uso |
|---------|------------|----------|-----|
| Desarrollo | `config/development.env` | `develop` | Tests locales |
| Testing | `config/testing.env` | `testing` | QA |
| Producción | `config/production.env` | `main` | Producción real |
