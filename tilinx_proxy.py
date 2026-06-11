"""
TilinX Proxy
Secured mitmproxy addon: IP-based authentication, rate limiting, admin whitelist.
"""
import os, json, time, logging, threading, hashlib, base64
from mitmproxy import http, ctx

# ─── Configuration ───────────────────────────────────────────
BASE_DIR   = os.environ.get("TilinX_BASE_DIR", "/opt/tilinx")
DATA_DIR   = os.path.join(BASE_DIR, "data", "TilinX")
DB_PATH    = os.environ.get("TilinX_DB_PATH",  os.path.join(BASE_DIR, "ips.json"))
LOG_DIR    = os.environ.get("TilinX_LOG_DIR",  os.path.join(BASE_DIR, "logs"))

ADMIN_WHITELIST = [ip.strip() for ip in os.environ.get("TilinX_ADMIN_IP_WHITELIST", "").split(",") if ip.strip()]
PROXY_RATE_LIMIT = int(os.environ.get("TilinX_RATE_LIMIT", "30"))

LOG_PREFIX = "【TilinX】"

# Intercept patterns (request hook)
INTERCEPT_PATTERNS = ["cache_res", "fileinfo"]

# Anti-cheat patterns to block
ANTICHEAT_PATTERNS = [
    "CheckHackBehavior", "anticheat",
    "GetMatchmakingBlacklist", "antijuda",
]

# Protected login hosts
PROTECTED_HOSTS = [
    "loginbp.ggpolarbear.com",
    "clientbp.ggpolarbear.com",
    "gate.ggpolarbear.com",
]
LOGIN_KEYWORD = "majorlogin"

# In-game messages
MSG_SUCCESS      = "[00FF88]✅ Authentication Successful\n[FFFFFF]TilinX is active."
MSG_BANNED       = "[FF0000]⛔ Access Revoked\n[FFFFFF]Your account is banned."
MSG_EXPIRED      = "[FF8800]⏰ Subscription Expired\n[FFFFFF]Renew now via bot."
MSG_NOT_FOUND    = "[FF6600]🔒 Not Registered\n[FFFFFF]Get access via bot."
MSG_DENIED       = "[FF0000]🚫 Access Denied\n[FFFFFF]Register via bot first."

# ─── Logging ─────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "tilinx_proxy.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("tilinx")

# ─── File cache ───────────────────────────────
FILE_CACHE = {}

def load_files():
    if not os.path.exists(DATA_DIR):
        log.error(f"Data dir not found: {DATA_DIR}")
        return
    for pattern in INTERCEPT_PATTERNS:
        for name in [pattern, pattern + ".txt", pattern + ".bin"]:
            path = os.path.join(DATA_DIR, name)
            if os.path.exists(path):
                with open(path, "rb") as f:
                    raw = f.read()
                try:
                    text = raw.decode("ascii").strip()
                    clean = text.replace(" ", "").replace("\n", "").replace("\r", "")
                    if all(c in "0123456789abcdefABCDEF" for c in clean) and len(clean) > 10:
                        binary = bytes.fromhex(clean)
                        FILE_CACHE[pattern] = binary
                        ctx.log.info(f"{LOG_PREFIX} Loaded {pattern}: {len(raw)} hex -> {len(binary)} binary bytes")
                        break
                except (UnicodeDecodeError, ValueError):
                    pass
                FILE_CACHE[pattern] = raw
                ctx.log.info(f"{LOG_PREFIX} Loaded {pattern}: {len(raw)} binary bytes")
                break
    ctx.log.info(f"{LOG_PREFIX} Files ready: {list(FILE_CACHE.keys())}")

# ─── IP Database (cached, TTL 15s) ─────────────
DB_CACHE = {"data": {}, "ts": 0}
DB_TTL = 15

def _db_key():
    raw = os.environ.get("TilinX_DB_KEY", "")
    if not raw:
        kf = os.path.join(os.path.dirname(DB_PATH), ".db_key")
        if os.path.exists(kf):
            raw = open(kf).read().strip()
        else:
            import socket
            raw = socket.gethostname() + "-tilinx-db-key"
    return hashlib.sha256(raw.encode()).digest()[:16]

def _db_decrypt(payload):
    try:
        key = _db_key()
        raw = base64.b64decode(payload.encode("ascii"))
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode("utf-8")
    except Exception:
        return None

def load_db():
    now = time.time()
    if now - DB_CACHE["ts"] < DB_TTL:
        return DB_CACHE["data"]
    if not os.path.exists(DB_PATH):
        return {}
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return {}
        # Auto-detect encrypted vs plain JSON
        if not raw.startswith("{"):
            decrypted = _db_decrypt(raw)
            if decrypted:
                raw = decrypted
        DB_CACHE["data"] = json.loads(raw)
        DB_CACHE["ts"] = now
    except Exception:
        pass
    return DB_CACHE.get("data", {})

# ─── Rate limiter ──────────────────────────────
RL_LOCK = threading.Lock()
RL_DATA = {}

def check_rate_limit(ip):
    now = time.time()
    with RL_LOCK:
        entry = RL_DATA.get(ip)
        if not entry or now - entry[1] > 60:
            RL_DATA[ip] = [1, now]
            return True
        entry[0] += 1
        if entry[0] > PROXY_RATE_LIMIT:
            return False
        return True

# ─── Auth ──────────────────────────────────────
def is_admin_ip(ip):
    return ip in ADMIN_WHITELIST

def is_active_ip(ip):
    db = load_db()
    user = db.get(ip)
    if not user:
        return False
    status = user.get("status", "")
    if status == "blocked":
        return False
    if status == "active":
        exp = user.get("expires_at", 0) or 0
        try:
            exp = float(exp)
        except (TypeError, ValueError):
            exp = 0
        return exp == 0 or exp > time.time()
    return False

def get_ip_status(ip):
    if is_admin_ip(ip):
        return "ADMIN"
    db = load_db()
    user = db.get(ip)
    if not user:
        return "NOT_FOUND"
    status = user.get("status", "")
    if status == "blocked":
        return "BANNED"
    if status == "active":
        exp = user.get("expires_at", 0) or 0
        try:
            exp = float(exp)
        except (TypeError, ValueError):
            exp = 0
        if exp == 0 or exp > time.time():
            return "ACTIVE"
        return "EXPIRED"
    return "NOT_FOUND"

def make_block_response(flow, message, status=403):
    flow.response = http.Response.make(
        status,
        message.encode("utf-8"),
        {"Content-Type": "text/plain; charset=utf-8", "Connection": "close"},
    )

def get_client_ip(flow):
    try:
        return flow.client_conn.peername[0]
    except Exception:
        return None

# ─── Proxy Addon ─────────────────────────────────────────────
class TilinxProxy:

    def load(self, loader):
        ctx.log.info(f"{LOG_PREFIX} Proxy starting...")
        if ADMIN_WHITELIST:
            ctx.log.info(f"{LOG_PREFIX} Admin IPs: {', '.join(ADMIN_WHITELIST)}")
        ctx.log.info(f"{LOG_PREFIX} Rate limit: {PROXY_RATE_LIMIT} req/min per IP")
        load_files()
        ctx.log.info(f"{LOG_PREFIX} Ready on port {ctx.options.listen_port}")

    def request(self, flow: http.HTTPFlow):
        url = flow.request.pretty_url
        url_lower = url.lower()
        client_ip = get_client_ip(flow)

        # ── Global IP check (ALL traffic) ──────────
        if not client_ip:
            make_block_response(flow, MSG_DENIED)
            return

        # Rate limit
        if not check_rate_limit(client_ip):
            make_block_response(flow, "[FF0000]🚫 Rate Limited\n[FFFFFF]Too many requests.")
            ctx.log.warn(f"{LOG_PREFIX} [RATE_LIMIT] IP {client_ip}")
            log.warning(f"RATE_LIMIT IP={client_ip}")
            return

        # Auth check
        if not is_admin_ip(client_ip) and not is_active_ip(client_ip):
            status = get_ip_status(client_ip)
            msg_map = {"BANNED": MSG_BANNED, "EXPIRED": MSG_EXPIRED}
            msg = msg_map.get(status, MSG_DENIED)
            make_block_response(flow, msg)
            ctx.log.warn(f"{LOG_PREFIX} [BLOCK {status}] IP {client_ip} — {url}")
            log.info(f"BLOCK_IP {client_ip} STATUS={status} URL={url}")
            return

        # ── Block anti-cheat ──────────────────
        for pattern in ANTICHEAT_PATTERNS:
            if pattern.lower() in url_lower:
                flow.response = http.Response.make(200, b"{}", {"Content-Type": "application/json"})
                ctx.log.info(f"[ANTICHEAT BLOCK] {url}")
                log.info(f"BLOCK_ANTICHEAT: {url}")
                return

        # ── Serve modified files ──────────────
        for pattern in INTERCEPT_PATTERNS:
            if pattern.lower() in url_lower:
                data = FILE_CACHE.get(pattern)
                if data:
                    flow.response = http.Response.make(
                        200, data,
                        {
                            "Content-Type": "application/octet-stream",
                            "Content-Length": str(len(data)),
                            "Connection": "close",
                        },
                    )
                    ctx.log.info(f"[INJECT {pattern}] {len(data)} bytes -> {url}")
                    log.info(f"INJECT_{pattern.upper()}: {url}")
                else:
                    ctx.log.warn(f"[MISSING {pattern}] No file loaded")
                return

        # ── Block early for non-ACTIVE (non-admin) on protected hosts ──
        if any(host in url_lower for host in PROTECTED_HOSTS) and LOGIN_KEYWORD not in url_lower:
            if not is_admin_ip(client_ip) and get_ip_status(client_ip) != "ACTIVE":
                msg = MSG_DENIED
                make_block_response(flow, msg)
                ctx.log.warn(f"{LOG_PREFIX} [BLOCK PROTECTED] IP {client_ip} — {url}")
                log.info(f"BLOCK_PROTECTED IP={client_ip} URL={url}")

    def response(self, flow: http.HTTPFlow):
        url = flow.request.pretty_url.lower()
        client_ip = get_client_ip(flow)

        # ── Login detection (IP-based) ──────────────────
        if LOGIN_KEYWORD in url:
            if flow.response.status_code != 200:
                return
            if not client_ip:
                ctx.log.warn(f"{LOG_PREFIX} Login detected but client IP not available")
                return

            status = get_ip_status(client_ip)

            ctx.log.info(f"\n{'='*45}")
            ctx.log.info(f"  {LOG_PREFIX} IP: {client_ip}  |  Status: {status}")
            ctx.log.info(f"{'='*45}")
            log.info(f"LOGIN IP={client_ip} STATUS={status}")

            msg_map = {
                "ACTIVE":    (MSG_SUCCESS,   200),
                "BANNED":    (MSG_BANNED,    400),
                "EXPIRED":   (MSG_EXPIRED,   400),
                "NOT_FOUND": (MSG_NOT_FOUND, 400),
                "ADMIN":     (MSG_SUCCESS,   200),
            }
            message, code = msg_map.get(status, (MSG_NOT_FOUND, 400))
            flow.response.status_code = code
            flow.response.content = message.encode("utf-8")
            flow.response.headers["Content-Type"] = "text/plain; charset=utf-8"
            return

addons = [TilinxProxy()]
