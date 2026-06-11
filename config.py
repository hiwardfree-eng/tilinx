import os

# ─── Telegram ───────────────────────────────────────────
BOT_TOKEN = os.environ.get("TilinX_BOT_TOKEN", "") or "8602901015:AAF6RWuaurtKU6jPK-rWD856YumQz8cBr40"
ADMIN_ID = int(os.environ.get("TilinX_ADMIN_ID", "8659405330"))
BOT_ENABLED = os.environ.get("TilinX_BOT_ENABLED", "1") == "1"

# ─── Paths ──────────────────────────────────────────────
BASE_DIR = os.environ.get("TilinX_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("TilinX_DB_PATH", os.path.join(BASE_DIR, "ips.json"))
KEYS_PATH = os.environ.get("TilinX_KEYS_PATH", os.path.join(BASE_DIR, "keys.json"))
CHAT_IPS_PATH = os.path.join(BASE_DIR, "chat_ips.json")
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

# ─── Seguridad ─────────────────────────────────────────
ENV = os.environ.get("TilinX_ENV", "production")
RATE_LIMIT = int(os.environ.get("TilinX_RATE_LIMIT", "10"))
SESSION_TIMEOUT = int(os.environ.get("TilinX_SESSION_TIMEOUT", "1800"))
MAX_LOGIN_ATTEMPTS = int(os.environ.get("TilinX_MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_BLOCK_MINUTES = int(os.environ.get("TilinX_LOGIN_BLOCK_MINUTES", "15"))
ADMIN_IP_WHITELIST = os.environ.get("TilinX_ADMIN_IP_WHITELIST", "").split(",")
ADMIN_IP_BIND = os.environ.get("TilinX_ADMIN_IP_BIND", "0") == "1"
CORS_ORIGIN = os.environ.get("TilinX_CORS_ORIGIN", "https://tilinx.onrender.com")

# ─── Admin ──────────────────────────────────────────
ADMIN_USER = os.environ.get("TilinX_ADMIN_USER", "tilinX")
CSRF_ENABLED = os.environ.get("TilinX_CSRF_ENABLED", "1") == "1"
ENCRYPT_DB = os.environ.get("TilinX_ENCRYPT_DB", "1") == "1"
