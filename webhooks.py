import json, os, time, threading, logging
from typing import Optional, Dict, Any, List, Callable
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from file_utils import safe_read_json, safe_write_json

logger = logging.getLogger("tilinx.webhooks")

WEBHOOKS_PATH = os.environ.get("TilinX_WEBHOOKS_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "webhooks.json"))
_wlock = threading.Lock()
_wh_cache: Dict[str, Any] = {"data": None, "ts": 0.0}
_wh_ttl = 60

EVENT_KEY_REDEEMED = "key.redeemed"
EVENT_KEY_EXPIRED = "key.expired"
EVENT_IP_BLOCKED = "ip.blocked"
EVENT_IP_ACTIVATED = "ip.activated"
EVENT_LOGIN_FAILED = "login.failed"
EVENT_RATE_LIMIT_HIT = "rate_limit.hit"
EVENT_SYSTEM_ERROR = "system.error"
EVENT_PROXY_STARTED = "proxy.started"
EVENT_PROXY_STOPPED = "proxy.stopped"

_all_events = [
    EVENT_KEY_REDEEMED, EVENT_KEY_EXPIRED,
    EVENT_IP_BLOCKED, EVENT_IP_ACTIVATED,
    EVENT_LOGIN_FAILED, EVENT_RATE_LIMIT_HIT,
    EVENT_SYSTEM_ERROR, EVENT_PROXY_STARTED,
    EVENT_PROXY_STOPPED,
]


def _load() -> Dict[str, Any]:
    with _wlock:
        if _wh_cache["data"] is not None and time.time() - _wh_cache["ts"] < _wh_ttl:
            return _wh_cache["data"]
    if not os.path.exists(WEBHOOKS_PATH):
        return {}
    data = safe_read_json(WEBHOOKS_PATH, {})
    with _wlock:
        _wh_cache["data"] = data
        _wh_cache["ts"] = time.time()
    return data


def _save(data: dict) -> None:
    safe_write_json(WEBHOOKS_PATH, data)
    with _wlock:
        _wh_cache["data"] = data
        _wh_cache["ts"] = time.time()


def register(url: str, events: Optional[List[str]] = None, secret: str = "") -> str:
    data = _load()
    wid = f"wh_{int(time.time())}_{hash(url) % 10000}"
    data[wid] = {
        "url": url,
        "events": events or _all_events,
        "secret": secret,
        "created_at": time.time(),
        "last_success": None,
        "last_failure": None,
        "failure_count": 0,
        "enabled": True,
    }
    _save(data)
    logger.info(f"Webhook registered: {wid} -> {url} ({len(data[wid]['events'])} events)")
    return wid


def remove(wid: str) -> bool:
    data = _load()
    if wid not in data:
        return False
    del data[wid]
    _save(data)
    return True


def list_webhooks() -> List[Dict[str, Any]]:
    data = _load()
    return [{"id": k, **v} for k, v in sorted(data.items(), key=lambda x: x[1].get("created_at", 0))]


def dispatch(event: str, payload: Dict[str, Any]) -> None:
    data = _load()
    for wid, cfg in data.items():
        if not cfg.get("enabled", True):
            continue
        if event not in cfg.get("events", _all_events):
            continue
        t = threading.Thread(target=_send, args=(wid, cfg["url"], cfg.get("secret", ""), event, payload), daemon=True)
        t.start()


def _send(wid: str, url: str, secret: str, event: str, payload: Dict[str, Any]) -> None:
    body = json.dumps({
        "event": event,
        "timestamp": time.time(),
        "data": payload,
    }).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "TilinX-Webhook/1.0",
        "X-Event": event,
    }
    if secret:
        import hmac
        sig = hmac.new(secret.encode(), body, "sha256").hexdigest()
        headers["X-Signature"] = sig
    try:
        req = Request(url, data=body, headers=headers, method="POST")
        resp = urlopen(req, timeout=10)
        data = _load()
        if wid in data:
            if 200 <= resp.status < 300:
                data[wid]["last_success"] = time.time()
                data[wid]["failure_count"] = 0
            else:
                data[wid]["last_failure"] = time.time()
                data[wid]["failure_count"] = data[wid].get("failure_count", 0) + 1
            _save(data)
        logger.info(f"Webhook {wid} sent {event} -> {url} ({resp.status})")
    except Exception as e:
        logger.warning(f"Webhook {wid} failed for {event}: {e}")
        data = _load()
        if wid in data:
            data[wid]["last_failure"] = time.time()
            data[wid]["failure_count"] = data[wid].get("failure_count", 0) + 1
            _save(data)
