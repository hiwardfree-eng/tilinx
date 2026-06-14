"""
TilinX Proxy
mitmproxy addon: dual auth (IP + UID), protobuf login parsing, rate limiting, admin whitelist.
"""
import os, json, time, logging, threading, hashlib, base64
from typing import Optional, Dict, Any, List, Tuple
from mitmproxy import http
from dotenv import load_dotenv; load_dotenv()

BASE_DIR   = os.environ.get("TilinX_BASE_DIR", "/opt/tilinx")
DATA_DIR   = os.environ.get("TilinX_DATA_DIR", os.path.join(BASE_DIR, "data", "TilinX"))
DB_PATH    = os.environ.get("TilinX_DB_PATH",  os.path.join(BASE_DIR, "ips.json"))
UID_PATH   = os.environ.get("TilinX_UID_PATH", os.path.join(BASE_DIR, "uids.json"))
LOG_DIR    = os.environ.get("TilinX_LOG_DIR",  os.path.join(BASE_DIR, "logs"))

ADMIN_WHITELIST = [ip.strip() for ip in os.environ.get("TilinX_ADMIN_IP_WHITELIST", "").split(",") if ip.strip()]
PROXY_RATE_LIMIT = int(os.environ.get("TilinX_RATE_LIMIT", "30"))
LOG_PREFIX = "[TilinX]"

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

MSG_SUCCESS      = "[00FF88]\u2705 Authentication Successful\n[FFFFFF]TilinX is active."
MSG_BANNED       = "[FF0000]\u26d4 Access Revoked\n[FFFFFF]Your account is banned."
MSG_EXPIRED      = "[FF8800]\u23f0 Subscription Expired\n[FFFFFF]Renew now via bot."
MSG_NOT_FOUND    = "[FF6600]\U0001f512 Not Registered\n[FFFFFF]Get access via bot."
MSG_DENIED       = "[FF0000]\U0001f6ab Access Denied\n[FFFFFF]Register via bot first."

# --- Logging ---
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "tilinx_proxy.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("tilinx")

import filter_rules
import geoip
import webhooks
import alerts
import waf as waf_module
import rate_limiter

try:
    from brain import BrainV2
    _brain = BrainV2()
    log.info(f"{LOG_PREFIX} Brain V2 loaded (behavioral security)")
except Exception as e:
    _brain = None
    log.warning(f"{LOG_PREFIX} Brain V2 not available: {e}")

# --- Thread-safe state ---
_FILES_LOCK = threading.Lock()
_DB_CACHE_LOCK = threading.Lock()
_DB_CACHE: Dict[str, Any] = {"data": {}, "ts": 0.0}
_DB_TTL = 15

FILE_CACHE: Dict[str, bytes] = {}
_FILE_CACHE_MAX = 10 * 1024 * 1024  # 10MB max cache
_PROXY_START_TIME = time.time()


def _watchdog_loop() -> None:
    while True:
        time.sleep(300)
        try:
            for key in list(FILE_CACHE.keys()):
                if len(FILE_CACHE) > 10:
                    FILE_CACHE.pop(key, None)
                    break
            from brain.memory_store import MemoryStore
            ms = getattr(_brain, 'store', None)
            if ms and hasattr(ms, '_data'):
                ds = len(ms._data)
                dl = len(ms._lists)
                de = len(ms._expiry)
            else:
                ds = dl = de = 0
            log.info(
                f"{LOG_PREFIX} [HEALTH] uptime={int((time.time()-_PROXY_START_TIME)/60)}m "
                f"cache_files={len(FILE_CACHE)} brain_keys={ds} brain_lists={dl} brain_expiry={de}"
            )
        except Exception as e:
            log.error(f"{LOG_PREFIX} [WATCHDOG_ERROR] {e}")


threading.Thread(target=_watchdog_loop, daemon=True).start()


def load_files() -> None:
    if not os.path.exists(DATA_DIR):
        log.error(f"Data dir not found: {DATA_DIR}")
        return
    for pattern in INTERCEPT_PATTERNS:
        for name in [pattern, pattern + ".txt", pattern + ".bin"]:
            path = os.path.join(DATA_DIR, name)
            if os.path.exists(path):
                with open(path, "rb") as f:
                    raw: bytes = f.read()
                try:
                    text = raw.decode("ascii").strip()
                    clean = text.replace(" ", "").replace("\n", "").replace("\r", "")
                    if all(c in "0123456789abcdefABCDEF" for c in clean) and len(clean) > 10:
                        binary = bytes.fromhex(clean)
                        with _FILES_LOCK:
                            FILE_CACHE[pattern] = binary
                        log.info(f"{LOG_PREFIX} Loaded {pattern}: {len(raw)} hex -> {len(binary)} binary bytes")
                        break
                except (UnicodeDecodeError, ValueError):
                    pass
                with _FILES_LOCK:
                    FILE_CACHE[pattern] = raw
                log.info(f"{LOG_PREFIX} Loaded {pattern}: {len(raw)} binary bytes")
                break
    with _FILES_LOCK:
        log.info(f"{LOG_PREFIX} Files ready: {list(FILE_CACHE.keys())}")


def _db_key() -> bytes:
    raw = os.environ.get("TilinX_DB_KEY", "")
    if not raw:
        kf = os.path.join(os.path.dirname(DB_PATH), ".db_key")
        if os.path.exists(kf):
            with open(kf) as f:
                raw = f.read().strip()
        else:
            import socket
            raw = socket.gethostname() + "-tilinx-db-key"
    return hashlib.sha256(raw.encode()).digest()[:16]


def _db_decrypt(payload: str) -> Optional[str]:
    try:
        key = _db_key()
        raw_bytes = base64.b64decode(payload.encode("ascii"))
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw_bytes)).decode("utf-8")
    except Exception:
        return None


def load_db() -> Dict[str, Any]:
    now = time.time()
    with _DB_CACHE_LOCK:
        if now - _DB_CACHE["ts"] < _DB_TTL:
            return _DB_CACHE["data"]
    if not os.path.exists(DB_PATH):
        return {}
    raw = ""
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            raw = f.read().strip()
    except:
        return {}
    if not raw:
        return {}
    try:
        if not raw.startswith("{"):
            decrypted = _db_decrypt(raw)
            if decrypted:
                raw = decrypted
        data = json.loads(raw)
        with _DB_CACHE_LOCK:
            _DB_CACHE["data"] = data
            _DB_CACHE["ts"] = now
        return data
    except Exception as e:
        log.warning(f"Failed to load DB: {e}")
        if raw and raw.startswith('\ufeff'):
            try:
                data = json.loads(raw.lstrip('\ufeff'))
                with _DB_CACHE_LOCK:
                    _DB_CACHE["data"] = data
                    _DB_CACHE["ts"] = now
                log.info("DB loaded after stripping BOM")
                return data
            except Exception as e2:
                log.error(f"Failed to load DB after BOM fix: {e2}")
    return {}


def load_uids() -> Dict[str, Any]:
    if not os.path.exists(UID_PATH):
        return {}
    try:
        with open(UID_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_uids(data: dict) -> None:
    try:
        with open(UID_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.error(f"Error saving uids.json: {e}")


def get_uid_status(uid: str) -> str:
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


def _decode_varint(data: bytes, pos: int) -> Tuple[int, int]:
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def extract_uid(proto_bytes: bytes) -> Optional[str]:
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


# --- Rate limiter ---





def is_admin_ip(ip: str) -> bool:
    return ip in ADMIN_WHITELIST


def is_active_ip(ip: str) -> bool:
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


def get_ip_status(ip: str) -> str:
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


def make_block_response(flow: http.HTTPFlow, message: str, status: int = 403) -> None:
    flow.response = http.Response.make(
        status,
        message.encode("utf-8"),
        {"Content-Type": "text/plain; charset=utf-8", "Connection": "close"},
    )


def get_client_ip(flow: http.HTTPFlow) -> Optional[str]:
    try:
        return flow.client_conn.peername[0]
    except Exception:
        return None


# --- Proxy Addon ---
class TilinxProxy:

    def load(self, loader) -> None:
        log.info(f"{LOG_PREFIX} Proxy starting...")
        webhooks.dispatch("proxy.started", {"pid": os.getpid(), "port": os.environ.get('TilinX_PROXY_PORT', '8884')})
        if ADMIN_WHITELIST:
            log.info(f"{LOG_PREFIX} Admin IPs: {', '.join(ADMIN_WHITELIST)}")
        log.info(f"{LOG_PREFIX} Rate limit: {PROXY_RATE_LIMIT} req/min per IP")
        log.info(f"{LOG_PREFIX} DB: {DB_PATH}")
        log.info(f"{LOG_PREFIX} UIDs: {UID_PATH}")
        log.info(f"{LOG_PREFIX} Data: {DATA_DIR}")
        load_files()
        log.info(f"{LOG_PREFIX} Ready on port {os.environ.get('TilinX_PROXY_PORT', '8884')}")

    def _log_url(self, flow: http.HTTPFlow) -> str:
        try:
            h = flow.request.pretty_host or flow.request.host or "?"
            p = flow.request.port or 0
            return f"{h}:{p}"
        except Exception:
            return "?:0"

    def request(self, flow: http.HTTPFlow) -> None:
        try:
            self._request_body(flow)
        except Exception as e:
            try:
                client_ip = get_client_ip(flow) or "?"
            except Exception:
                client_ip = "?"
            log.critical(f"{LOG_PREFIX} [CRASH] request handler: {e}", exc_info=True)
            try:
                alerts.trigger("system_error", f"Proxy crash: {e}", {"ip": client_ip, "error": str(e)})
            except Exception:
                pass
            try:
                make_block_response(flow, f"[FF0000]\u26d4 Server Error\n[FFFFFF]Please retry.")
            except Exception:
                pass

    def _request_body(self, flow: http.HTTPFlow) -> None:
        url_lower = flow.request.pretty_url.lower()
        client_ip = get_client_ip(flow)
        safe = self._log_url(flow)

        if not client_ip:
            make_block_response(flow, MSG_DENIED)
            return

        try:
            rl_allowed, rl_info = rate_limiter.check(client_ip, flow.request.pretty_url)
        except Exception:
            rl_allowed, rl_info = True, {}
        if not rl_allowed:
            make_block_response(flow, "[FF0000]\U0001f6ab Smart Rate Limit\n[FFFFFF]Demasiadas peticiones.")
            log.warning(f"{LOG_PREFIX} [SMART_RL] {client_ip} score={rl_info.get('adaptive_score', '?')}")
            return

        body_text = ""
        try:
            body_text = flow.request.get_text(strict=False) or ""
        except Exception:
            pass
        waf_result = waf_module.check_request(
            flow.request.method,
            flow.request.pretty_url,
            dict(flow.request.headers),
            body_text,
        )
        if waf_result.blocked and waf_result.severity in ("high", "critical"):
            make_block_response(flow, f"[FF0000]\u26d4 Request Blocked by WAF\n[FFFFFF]{waf_result.reasons[0] if waf_result.reasons else 'Suspicious activity'}")
            log.warning(f"{LOG_PREFIX} [WAF_BLOCK] {client_ip} -> {safe}: {waf_result.reasons}")
            alerts.trigger("waf.blocked", f"WAF bloque\u00f3: {client_ip}", {"ip": client_ip, "host": safe, "reasons": waf_result.reasons, "score": waf_result.score})
            return
        if waf_result.score > 0:
            log.info(f"WAF_SCORE IP={client_ip} HOST={safe} SCORE={waf_result.score} SEVERITY={waf_result.severity} REASONS={waf_result.reasons}")

        if _brain is not None:
            try:
                brain_result = _brain.process({
                    "ip": client_ip,
                    "path": flow.request.pretty_url,
                    "method": flow.request.method,
                    "host": safe,
                    "user_agent": flow.request.headers.get("user-agent", ""),
                })
                decision = brain_result.get("decision", {})
                action = decision.get("action", "allow")
                if action == "block":
                    make_block_response(flow, f"[FF0000]\u26d4 Access Blocked\n[FFFFFF]{decision.get('reason', 'security')}")
                    log.warning(f"{LOG_PREFIX} [BRAIN_BLOCK] {client_ip} -> {safe}: {decision}")
                    alerts.trigger("brain.blocked", f"Brain bloque\u00f3: {client_ip}", {"ip": client_ip, "host": safe, "decision": decision, "signals": brain_result.get("signals", [])})
                    return
                if action == "challenge":
                    make_block_response(flow, "[FF6600]\U0001f6ab Verification Required\n[FFFFFF]Complete the challenge.", status=401)
                    log.warning(f"{LOG_PREFIX} [BRAIN_CHALLENGE] {client_ip} -> {safe}: score={brain_result.get('risk_score')}")
                    return
                if action == "rate_limit":
                    throttle = decision.get("throttle", 0.5)
                    time.sleep(throttle)
                    log.info(f"{LOG_PREFIX} [BRAIN_THROTTLE] {client_ip} -> {safe}: {throttle}s delay")
                    return
            except Exception as e:
                log.error(f"{LOG_PREFIX} [BRAIN_ERROR] {client_ip} -> {safe}: {e}")

        try:
            blocked, reason = filter_rules.check_url_blocked(flow.request.pretty_url)
        except Exception as e:
            log.error(f"{LOG_PREFIX} [FILTER_ERROR] {e}")
            blocked, reason = False, ""
        if blocked:
            make_block_response(flow, f"[FF0000]\u26d4 URL Blocked\n[FFFFFF]{reason}")
            log.warning(f"{LOG_PREFIX} [URL_BLOCKED] {client_ip} -> {safe}: {reason}")
            log.info(f"URL_BLOCK IP={client_ip} HOST={safe} REASON={reason}")
            return

        try:
            geo_info = geoip.lookup(client_ip)
        except Exception as e:
            log.error(f"{LOG_PREFIX} [GEOIP_ERROR] {client_ip}: {e}")
            geo_info = None
        if geo_info:
            try:
                blocked_country = geoip.is_blocked_country(geo_info.get("country_code", ""))
            except Exception as e:
                log.error(f"{LOG_PREFIX} [GEOIP_CHECK_ERROR] {client_ip}: {e}")
                blocked_country = False
            if blocked_country:
                make_block_response(flow, f"[FF0000]\U0001f310 Country Blocked\n[FFFFFF]{geo_info.get('country', '')}")
                log.warning(f"{LOG_PREFIX} [GEO_BLOCK] {client_ip} -> {geo_info.get('country_code', '')}")
                log.info(f"GEO_BLOCK IP={client_ip} COUNTRY={geo_info.get('country_code', '')}")
                alerts.trigger("geoip.blocked", f"Pa\u00eds bloqueado: {geo_info.get('country_code', '')}", {"ip": client_ip, "country": geo_info.get('country_code', '')})
                return

        try:
            flow.request.headers = filter_rules.apply_header_rules(flow.request.pretty_url, dict(flow.request.headers))
        except Exception as e:
            log.error(f"{LOG_PREFIX} [HEADER_RULES_ERROR] {client_ip}: {e}")

        if not is_admin_ip(client_ip):
            if is_active_ip(client_ip):
                pass
            else:
                uids_db = load_uids()
                ip_uid_map = {v.get("ip", ""): k for k, v in uids_db.items() if v.get("ip")}
                uid = ip_uid_map.get(client_ip)
                if uid and get_uid_status(uid) == "ACTIVE":
                    pass
                else:
                    status = get_ip_status(client_ip)
                    msg_map = {"BANNED": MSG_BANNED, "EXPIRED": MSG_EXPIRED}
                    msg = msg_map.get(status, MSG_DENIED)
                    make_block_response(flow, msg)
                    log.warning(f"{LOG_PREFIX} [BLOCK {status}] {client_ip} -> {safe}")
                    log.info(f"BLOCK_IP {client_ip} STATUS={status} HOST={safe}")
                    return

        for pattern in ANTICHEAT_PATTERNS:
            if pattern.lower() in url_lower:
                flow.response = http.Response.make(200, b"{}", {"Content-Type": "application/json"})
                log.info(f"[ANTICHEAT] {client_ip} -> {safe}")
                log.info(f"BLOCK_ANTICHEAT IP={client_ip} HOST={safe}")
                return

        for pattern in INTERCEPT_PATTERNS:
            if pattern.lower() in url_lower:
                with _FILES_LOCK:
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
                    log.info(f"[INJECT {pattern}] {len(data)}B {client_ip} -> {safe}")
                    log.info(f"INJECT_{pattern.upper()} IP={client_ip} HOST={safe}")
                else:
                    log.warning(f"[MISSING {pattern}] {client_ip} -> {safe}")
                return

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
                    log.warning(f"{LOG_PREFIX} [BLOCK PROTECTED] {client_ip} -> {safe}")
                    log.info(f"BLOCK_PROTECTED IP={client_ip} HOST={safe}")
                    return

    def response(self, flow: http.HTTPFlow) -> None:
        try:
            self._response_body(flow)
        except Exception as e:
            log.error(f"{LOG_PREFIX} [CRASH] response handler: {e}", exc_info=True)

    def _response_body(self, flow: http.HTTPFlow) -> None:
        url_lower = flow.request.pretty_url.lower()
        client_ip = get_client_ip(flow)
        safe = self._log_url(flow)

        if LOGIN_KEYWORD in url_lower:
            if flow.response.status_code != 200:
                return
            if not client_ip:
                log.warning(f"{LOG_PREFIX} Login detected but no IP")
                return

            uid = extract_uid(flow.response.content)
            if uid:
                status = get_uid_status(uid)
                uids_db = load_uids()
                if uid in uids_db:
                    uids_db[uid]["ip"] = client_ip
                    save_uids(uids_db)
                log.info(f"\n{'='*45}")
                log.info(f"  {LOG_PREFIX} UID: {uid}  |  {client_ip}  |  {status}")
                log.info(f"{'='*45}")
                log.info(f"LOGIN UID={uid} IP={client_ip} STATUS={status}")
                webhooks.dispatch("key.redeemed" if status == "ACTIVE" else "login.failed", {"uid": uid, "ip": client_ip, "status": status})

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

            status = get_ip_status(client_ip)
            log.info(f"\n{'='*45}")
            log.info(f"  {LOG_PREFIX} {client_ip}  |  {status} (IP fallback)")
            log.info(f"{'='*45}")
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
