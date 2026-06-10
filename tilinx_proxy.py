"""
TilinX Proxy
Request hook: serves modified game files (cache_res, assetindexer, fileinfo)
Response hook: IP-based login validation
"""
import os
import json
import time
import logging
from mitmproxy import http, ctx

# ─── Configuration ───────────────────────────────────────────
BASE_DIR   = os.environ.get("TilinX_BASE_DIR", "/opt/tilinx")
DATA_DIR   = os.path.join(BASE_DIR, "data", "TilinX")
DB_PATH    = os.environ.get("TilinX_DB_PATH",  os.path.join(BASE_DIR, "ips.json"))
LOG_DIR    = os.environ.get("TilinX_LOG_DIR",  os.path.join(BASE_DIR, "logs"))
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
                        ctx.log.info(f"{LOG_PREFIX} Loaded {pattern}: {len(raw)} hex → {len(binary)} binary bytes")
                        break
                except (UnicodeDecodeError, ValueError):
                    pass
                FILE_CACHE[pattern] = raw
                ctx.log.info(f"{LOG_PREFIX} Loaded {pattern}: {len(raw)} binary bytes")
                break
    ctx.log.info(f"{LOG_PREFIX} Files ready: {list(FILE_CACHE.keys())}")

# ─── IP Database ─────────────────────────────────────────────
def load_db():
    if not os.path.exists(DB_PATH):
        return {}
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def get_auth_status(ip):
    if not ip:
        return "NOT_FOUND"
    db = load_db()
    if ip not in db:
        return "NOT_FOUND"
    user = db[ip]
    status = user.get("status", "")
    if status == "blocked":
        return "BANNED"
    if status == "active":
        return "ACTIVE" if user.get("expires_at", 0) > time.time() else "EXPIRED"
    return "NOT_FOUND"

def make_block_response(flow, message, status=400):
    flow.response = http.Response.make(
        status,
        message.encode("utf-8"),
        {"Content-Type": "text/plain; charset=utf-8"},
    )

def get_client_ip(flow) -> str:
    try:
        return flow.client_conn.peername[0]
    except Exception:
        return None

# ─── Proxy Addon ─────────────────────────────────────────────
class TilinxProxy:

    def load(self, loader):
        ctx.log.info(f"{LOG_PREFIX} Proxy starting...")
        load_files()
        ctx.log.info(f"{LOG_PREFIX} Ready on port {ctx.options.listen_port}")

    def request(self, flow: http.HTTPFlow):
        url = flow.request.pretty_url
        url_lower = url.lower()
        client_ip = get_client_ip(flow)

        # ── Block anti-cheat ──────────────────
        for pattern in ANTICHEAT_PATTERNS:
            if pattern.lower() in url_lower:
                flow.response = http.Response.make(200, b"{}", {"Content-Type": "application/json"})
                ctx.log.info(f"[BLOCK anticheat] {url}")
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
                    ctx.log.info(f"[INJECT {pattern}] {len(data)} bytes → {url}")
                    log.info(f"INJECT_{pattern.upper()}: {url}")
                else:
                    ctx.log.warn(f"[MISSING {pattern}] No file loaded")
                return

        # ── Block early for unauthorized IPs ───
        if any(host in url_lower for host in PROTECTED_HOSTS) and LOGIN_KEYWORD not in url_lower:
            if not client_ip:
                return
            status = get_auth_status(client_ip)
            if status != "ACTIVE":
                msg = {"BANNED": MSG_BANNED, "EXPIRED": MSG_EXPIRED}.get(status, MSG_NOT_FOUND)
                make_block_response(flow, msg)
                ctx.log.warn(f"{LOG_PREFIX} [BLOCK {status}] IP {client_ip} — {url}")
                log.info(f"BLOCK_IP {client_ip} STATUS={status} URL={url}")

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

            status = get_auth_status(client_ip)

            ctx.log.info(f"\n{'═'*45}")
            ctx.log.info(f"  {LOG_PREFIX} IP: {client_ip}  |  Status: {status}")
            ctx.log.info(f"{'═'*45}")
            log.info(f"LOGIN IP={client_ip} STATUS={status}")

            msg_map = {
                "ACTIVE":    (MSG_SUCCESS,   200),
                "BANNED":    (MSG_BANNED,    400),
                "EXPIRED":   (MSG_EXPIRED,   400),
                "NOT_FOUND": (MSG_NOT_FOUND, 400),
            }
            message, code = msg_map.get(status, (MSG_NOT_FOUND, 400))
            flow.response.status_code = code
            flow.response.content = message.encode("utf-8")
            flow.response.headers["Content-Type"] = "text/plain; charset=utf-8"
            return

addons = [TilinxProxy()]
