import json, os, time, threading, logging
from typing import Dict, Any, List, Optional
from file_utils import safe_read_json, safe_write_json

logger = logging.getLogger("tilinx.alerts")

ALERTS_PATH = os.environ.get("TilinX_ALERTS_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "alerts.json"))
_alock = threading.Lock()
_a_cache: Dict[str, Any] = {"data": None, "ts": 0.0}
_a_ttl = 60
_a_dirty = False
_a_last_save = 0.0

ALERT_TYPE_CONNECTION_DROP = "connection_drop"
ALERT_TYPE_HIGH_RATE_LIMIT = "high_rate_limit"
ALERT_TYPE_LOGIN_FAILURES = "login_failures"
ALERT_TYPE_SYSTEM_ERROR = "system_error"
ALERT_TYPE_KEY_EXPIRING = "key_expiring"
ALERT_TYPE_NEW_REGISTRATION = "new_registration"

_default_channels = ["telegram"]


def _load() -> Dict[str, Any]:
    with _alock:
        if _a_cache["data"] is not None and time.time() - _a_cache["ts"] < _a_ttl:
            return _a_cache["data"]
    if not os.path.exists(ALERTS_PATH):
        default = {
            "configs": [
                {"id": "default_errors", "type": ALERT_TYPE_SYSTEM_ERROR, "enabled": True, "channels": list(_default_channels), "threshold": 1, "cooldown": 300},
                {"id": "default_rate_limit", "type": ALERT_TYPE_HIGH_RATE_LIMIT, "enabled": True, "channels": list(_default_channels), "threshold": 50, "cooldown": 600},
                {"id": "default_login_failures", "type": ALERT_TYPE_LOGIN_FAILURES, "enabled": True, "channels": list(_default_channels), "threshold": 10, "cooldown": 900},
            ],
            "recent": [],
            "max_recent": 100,
        }
        _save(default)
        return default
    data = safe_read_json(ALERTS_PATH, {"configs": [], "recent": [], "max_recent": 100})
    with _alock:
        _a_cache["data"] = data
        _a_cache["ts"] = time.time()
    return data


def _save(data: dict) -> None:
    global _a_dirty, _a_last_save
    with _alock:
        _a_cache["data"] = data
        _a_cache["ts"] = time.time()
        _a_dirty = True
        now = time.time()
        if now - _a_last_save < 10:
            return
        _a_last_save = now
        _a_dirty = False
    safe_write_json(ALERTS_PATH, data)


def _flush_save() -> None:
    global _a_dirty
    with _alock:
        if not _a_dirty:
            return
        _a_dirty = False
        data = _a_cache["data"]
    safe_write_json(ALERTS_PATH, data)


def add_alert_config(alert_type: str, threshold: int = 1, channels: Optional[List[str]] = None,
                     cooldown: int = 300) -> str:
    data = _load()
    aid = f"alert_{int(time.time())}_{hash(alert_type) % 10000}"
    data["configs"].append({
        "id": aid, "type": alert_type, "enabled": True,
        "channels": channels or list(_default_channels),
        "threshold": threshold, "cooldown": cooldown,
    })
    _save(data)
    return aid


def remove_alert_config(aid: str) -> bool:
    data = _load()
    before = len(data["configs"])
    data["configs"] = [c for c in data["configs"] if c["id"] != aid]
    if len(data["configs"]) < before:
        _save(data)
        return True
    return False


def list_alert_configs() -> List[Dict[str, Any]]:
    data = _load()
    return data.get("configs", [])


_last_alert: Dict[str, float] = {}


def trigger(alert_type: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
    data = _load()
    now = time.time()
    triggered = False
    for cfg in data.get("configs", []):
        if not cfg.get("enabled", True) or cfg["type"] != alert_type:
            continue
        cooldown_key = cfg["id"]
        last = _last_alert.get(cooldown_key, 0)
        if now - last < cfg.get("cooldown", 300):
            continue
        _last_alert[cooldown_key] = now
        triggered = True
        channels = cfg.get("channels", [])
        for channel in channels:
            if channel == "telegram":
                _send_telegram(f"\u26a0\ufe0f ALERT: {message}")
            elif channel == "webhook":
                _send_webhook(alert_type, message, details)
        entry = {"type": alert_type, "message": message, "details": details or {}, "timestamp": now}
        data.setdefault("recent", []).append(entry)
        max_recent = data.get("max_recent", 100)
        if len(data["recent"]) > max_recent:
            data["recent"] = data["recent"][-max_recent:]
    if triggered:
        _save(data)


def get_recent(limit: int = 20) -> List[Dict[str, Any]]:
    data = _load()
    recent = data.get("recent", [])
    return recent[-limit:]


def _send_telegram(message: str) -> None:
    try:
        from config import BOT_TOKEN, ADMIN_ID
        if not BOT_TOKEN or not ADMIN_ID:
            return
        import requests
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"Alert telegram send failed: {e}")


def _send_webhook(alert_type: str, message: str, details: Optional[Dict]) -> None:
    try:
        from webhooks import dispatch
        dispatch(f"alert.{alert_type}", {"message": message, "details": details})
    except Exception as e:
        logger.warning(f"Alert webhook send failed: {e}")


# Periodic flush to disk
def _alert_flush_loop() -> None:
    while True:
        time.sleep(30)
        _flush_save()


threading.Thread(target=_alert_flush_loop, daemon=True).start()
