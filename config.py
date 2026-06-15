import os


def _int_env(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


# ─── Telegram ───────────────────────────────────────────
BOT_TOKEN = os.environ.get("TilinX_BOT_TOKEN", "")
ADMIN_ID = _int_env("TilinX_ADMIN_ID", 0)
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
PROXY_PORT = _int_env("TilinX_PROXY_PORT", 8884)

# ─── Proxy público (endpoint visible a usuarios) ────────
PROXY_PUBLIC_HOST = os.environ.get("TilinX_PROXY_PUBLIC_HOST", "bore.pub")
PROXY_PUBLIC_PORT = _int_env("TilinX_PROXY_PUBLIC_PORT", 31028)
PROXY_PUBLIC_IP = os.environ.get("TilinX_PROXY_PUBLIC_IP", "")  # IP directa opcional
if not PROXY_PUBLIC_IP:
    PROXY_PUBLIC_IP = f"{PROXY_PUBLIC_HOST}:{PROXY_PUBLIC_PORT}"
PROXY_PUBLIC_URL = os.environ.get("TilinX_PROXY_PUBLIC_URL", f"{PROXY_PUBLIC_HOST}:{PROXY_PUBLIC_PORT}")

# ─── URL base pública (web dashboard) ───────────────────
PUBLIC_BASE_URL = os.environ.get("TilinX_PUBLIC_BASE_URL", "https://tilinx.onrender.com")

# ─── Seguridad ─────────────────────────────────────────
ENV = os.environ.get("TilinX_ENV", "production")
RATE_LIMIT = _int_env("TilinX_RATE_LIMIT", 10)
SESSION_TIMEOUT = _int_env("TilinX_SESSION_TIMEOUT", 1800)
MAX_LOGIN_ATTEMPTS = _int_env("TilinX_MAX_LOGIN_ATTEMPTS", 5)
LOGIN_BLOCK_MINUTES = _int_env("TilinX_LOGIN_BLOCK_MINUTES", 15)
ADMIN_IP_WHITELIST = os.environ.get("TilinX_ADMIN_IP_WHITELIST", "").split(",")
ADMIN_IP_BIND = os.environ.get("TilinX_ADMIN_IP_BIND", "0") == "1"
CORS_ORIGIN = os.environ.get("TilinX_CORS_ORIGIN", "https://tilinx.onrender.com")

# ─── Admin ──────────────────────────────────────────
ADMIN_USER = os.environ.get("TilinX_ADMIN_USER", "tilinX")
CSRF_ENABLED = os.environ.get("TilinX_CSRF_ENABLED", "1") == "1"
ENCRYPT_DB = os.environ.get("TilinX_ENCRYPT_DB", "1") == "1"

# ─── PostgreSQL / Supabase ──────────────────────────
SUPABASE_ENABLED = os.environ.get("SUPABASE_ENABLED", "0") == "1"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SUPABASE_DB_HOST = os.environ.get("SUPABASE_DB_HOST", "")
SUPABASE_DB_PORT = _int_env("SUPABASE_DB_PORT", 6543)
SUPABASE_DB_NAME = os.environ.get("SUPABASE_DB_NAME", "postgres")
SUPABASE_DB_USER = os.environ.get("SUPABASE_DB_USER", "postgres")
SUPABASE_DB_PASSWORD = os.environ.get("SUPABASE_DB_PASSWORD", "")
