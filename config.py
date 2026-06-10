import os

# ─── Telegram ───────────────────────────────────────────
BOT_TOKEN = os.environ.get("TilinX_BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("TilinX_ADMIN_ID", "0"))

# ─── Paths ──────────────────────────────────────────────
BASE_DIR = os.environ.get("TilinX_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("TilinX_DB_PATH", os.path.join(BASE_DIR, "ips.json"))
KEYS_PATH = os.environ.get("TilinX_KEYS_PATH", os.path.join(BASE_DIR, "keys.json"))
DATA_DIR = os.environ.get("TilinX_DATA_DIR", os.path.join(BASE_DIR, "data", "TilinX"))
LOG_DIR = os.environ.get("TilinX_LOG_DIR", os.path.join(BASE_DIR, "logs"))

# ─── Proxy (SOCKS5 / HTTP / HTTPS) ──────────────────────
PROXY_ENABLED = os.environ.get("TilinX_PROXY_ENABLED", "0") == "1"
PROXY_URL = os.environ.get("TilinX_PROXY_URL", "")
PROXY_TYPE = os.environ.get("TilinX_PROXY_TYPE", "socks5")  # socks5, http, https

# ─── Proxy credenciales (para mitmproxy) ────────────────
PROXY_AUTH_USER = os.environ.get("TilinX_PROXY_AUTH_USER", "TilinX")
PROXY_AUTH_PASS = os.environ.get("TilinX_PROXY_AUTH_PASS", "TilinX")
PROXY_PORT = int(os.environ.get("TilinX_PROXY_PORT", "8884"))

# ─── Entorno ────────────────────────────────────────────
ENV = os.environ.get("TilinX_ENV", "production")  # development | testing | production
