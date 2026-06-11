"""
TilinX Proxy
mitmproxy addon: dual auth (IP + UID), protobuf login parsing, rate limiting, admin whitelist.
"""
import os, json, time, logging, threading, hashlib, base64
from mitmproxy import http, ctx

BASE_DIR   = os.environ.get("TilinX_BASE_DIR", "/opt/tilinx")
DATA_DIR   = os.environ.get("TilinX_DATA_DIR", os.path.join(BASE_DIR, "data", "TilinX"))
DB_PATH    = os.environ.get("TilinX_DB_PATH",  os.path.join(BASE_DIR, "ips.json"))
UID_PATH   = os.environ.get("TilinX_UID_PATH", os.path.join(BASE_DIR, "uids.json"))
LOG_DIR    = os.environ.get("TilinX_LOG_DIR",  os.path.join(BASE_DIR, "logs"))

ADMIN_WHITELIST = [ip.strip() for ip in os.environ.get("TilinX_ADMIN_IP_WHITELIST", "").split(",") if ip.strip()]
PROXY_RATE_LIMIT = int(os.environ.get("TilinX_RATE_LIMIT", "30"))
LOG_PREFIX = "【TilinX】"

INTERCEPT_PATTERNS = ["cache_res", "fileinfo"]

ANTICHEAT_PATTERNS = [
    "CheckHackBehavior", "anticheat",
    "GetMatchmakingBlacklist", "antijuda",
]

PROTECTED_HOSTS = [
    "loginbp.ggpolarbear.com",
    "clientbp.ggpolarbear.com",
    "gate.ggpolarbear.com",
]
LOGIN_KEYWORD = "majorlogin"

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

# ─── File cache (injected game files) ────────────────────────
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

# ─── IP Database (encrypted + plain) ────────────────────────
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
        if not raw.startswith("{"):
            decrypted = _db_decrypt(raw)
            if decrypted:
                raw = decrypted
        DB_CACHE["data"] = json.loads(raw)
        DB_CACHE["ts"] = now
    except Exception:
        pass
    return DB_CACHE.get("data", {})

# ─── UID Database (plain JSON, no cache needed) ─────────────
def load_uids():
    if not os.path.exists(UID_PATH):
        return {}
    try:
        with open(UID_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_uids(data):
    try:
        with open(UID_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.error(f"Error saving uids.json: {e}")

def get_uid_status(uid):
    if not uid:
        return "NOT_FOUND"
    db = load_uids()
    if uid not in db:
        return "NOT_FOUND"
    user = db[uid]
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

# ─── Protobuf parser (extract UID field 1, varint) ──────────
def _decode_varint(data, pos):
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80): break
        shift += 7
    return result, pos

def extract_uid(proto_bytes):
    try:
        pos = 0
        while pos < len(proto_bytes):
            tag, pos = _decode_varint(proto_bytes, pos)
            field_num = tag >> 3
            wire_type = tag & 0x7
            if field_num == 1 and wire_type == 0:
                value, pos = _decode_varint(proto_bytes, pos)
                return str(value)
            elif wire_type == 0:
                _, pos = _decode_varint(proto_bytes, pos)
            elif wire_type == 2:
                length, pos = _decode_varint(proto_bytes, pos)
                pos += length
            elif wire_type == 5:
                pos += 4
            else:
                pos += 8
    except Exception:
        pass
    return None

# ─── Rate limiter ───────────────────────────────────────────
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

# ─── Auth helpers ───────────────────────────────────────────
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
        ctx.log.info(f"{LOG_PREFIX} DB: {DB_PATH}")
        ctx.log.info(f"{LOG_PREFIX} UIDs: {UID_PATH}")
        ctx.log.info(f"{LOG_PREFIX} Data: {DATA_DIR}")
        load_files()
        ctx.log.info(f"{LOG_PREFIX} Ready on port {ctx.options.listen_port}")

    def _log_url(self, flow):
        try:
            h = flow.request.pretty_host or flow.request.host or "?"
            p = flow.request.port or 0
            return f"{h}:{p}"
        except Exception:
            return "?:0"

    def request(self, flow: http.HTTPFlow):
        url_lower = flow.request.pretty_url.lower()
        client_ip = get_client_ip(flow)
        safe = self._log_url(flow)

        if not client_ip:
            make_block_response(flow, MSG_DENIED)
            return

        # Rate limit
        if not check_rate_limit(client_ip):
            make_block_response(flow, "[FF0000]🚫 Rate Limited\n[FFFFFF]Too many requests.")
            ctx.log.warn(f"{LOG_PREFIX} [RATE_LIMIT] {client_ip}")
            log.warning(f"RATE_LIMIT IP={client_ip}")
            return

        # Skip IP auth for admin whitelist
        if not is_admin_ip(client_ip):
            # Check IP-based auth
            if is_active_ip(client_ip):
                pass  # IP is active
            else:
                # Check UID-based auth (if this IP has logged in before)
                uids_db = load_uids()
                ip_uid_map = {v.get("ip", ""): k for k, v in uids_db.items() if v.get("ip")}
                uid = ip_uid_map.get(client_ip)
                if uid and get_uid_status(uid) == "ACTIVE":
                    pass  # UID is active
                else:
                    status = get_ip_status(client_ip)
                    msg_map = {"BANNED": MSG_BANNED, "EXPIRED": MSG_EXPIRED}
                    msg = msg_map.get(status, MSG_DENIED)
                    make_block_response(flow, msg)
                    ctx.log.warn(f"{LOG_PREFIX} [BLOCK {status}] {client_ip} -> {safe}")
                    log.info(f"BLOCK_IP {client_ip} STATUS={status} HOST={safe}")
                    return

        # Block anti-cheat
        for pattern in ANTICHEAT_PATTERNS:
            if pattern.lower() in url_lower:
                flow.response = http.Response.make(200, b"{}", {"Content-Type": "application/json"})
                ctx.log.info(f"[ANTICHEAT] {client_ip} -> {safe}")
                log.info(f"BLOCK_ANTICHEAT IP={client_ip} HOST={safe}")
                return

        # Serve modified files
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
                    ctx.log.info(f"[INJECT {pattern}] {len(data)}B {client_ip} -> {safe}")
                    log.info(f"INJECT_{pattern.upper()} IP={client_ip} HOST={safe}")
                else:
                    ctx.log.warn(f"[MISSING {pattern}] {client_ip} -> {safe}")
                return

        # Block non-ACTIVE on protected hosts (login is allowed)
        if any(host in url_lower for host in PROTECTED_HOSTS) and LOGIN_KEYWORD not in url_lower:
            if not is_admin_ip(client_ip):
                ip_ok = is_active_ip(client_ip)
                uid_ok = False
                if not ip_ok:
                    uids_db = load_uids()
                    ip_uid_map = {v.get("ip", ""): k for k, v in uids_db.items() if v.get("ip")}
                    uid = ip_uid_map.get(client_ip)
                    if uid and get_uid_status(uid) == "ACTIVE":
                        uid_ok = True
                if not ip_ok and not uid_ok:
                    make_block_response(flow, MSG_DENIED)
                    ctx.log.warn(f"{LOG_PREFIX} [BLOCK PROTECTED] {client_ip} -> {safe}")
                    log.info(f"BLOCK_PROTECTED IP={client_ip} HOST={safe}")

    def response(self, flow: http.HTTPFlow):
        url_lower = flow.request.pretty_url.lower()
        client_ip = get_client_ip(flow)
        safe = self._log_url(flow)

        if LOGIN_KEYWORD in url_lower:
            if flow.response.status_code != 200:
                return
            if not client_ip:
                ctx.log.warn(f"{LOG_PREFIX} Login detected but no IP")
                return

            # Try UID auth first (protobuf)
            uid = extract_uid(flow.response.content)
            if uid:
                status = get_uid_status(uid)
                # Store UID mapping for this IP
                uids_db = load_uids()
                if uid in uids_db:
                    uids_db[uid]["ip"] = client_ip
                    save_uids(uids_db)
                ctx.log.info(f"\n{'='*45}")
                ctx.log.info(f"  {LOG_PREFIX} UID: {uid}  |  {client_ip}  |  {status}")
                ctx.log.info(f"{'='*45}")
                log.info(f"LOGIN UID={uid} IP={client_ip} STATUS={status}")

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

            # Fallback: IP-based auth
            status = get_ip_status(client_ip)
            ctx.log.info(f"\n{'='*45}")
            ctx.log.info(f"  {LOG_PREFIX} {client_ip}  |  {status} (IP fallback)")
            ctx.log.info(f"{'='*45}")
            log.info(f"LOGIN IP={client_ip} STATUS={status} (no UID)")

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

addons = [TilinxProxy()]