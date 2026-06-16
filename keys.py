import json, os, time, secrets, threading, re
from typing import Optional, Dict, Any, List
from config import KEYS_PATH, SUPABASE_ENABLED
from logger import log
from file_utils import safe_read_json, safe_write_json

_lock = threading.Lock()
PREFIX = "TILINX-"
FPS_PREFIX = "FPS-"
IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _load() -> Dict[str, Any]:
    if SUPABASE_ENABLED:
        from database.postgres_db import list_keys
        keys = list_keys()
        return {k.pop("code", ""): k for k in keys}
    if not os.path.exists(KEYS_PATH):
        return {}
    data = safe_read_json(KEYS_PATH, {})
    if data is None:
        data = {}
    return data


def _save(data: dict) -> None:
    if SUPABASE_ENABLED:
        return
    with _lock:
        safe_write_json(KEYS_PATH, data)


def is_valid_ip(text: str) -> bool:
    if not IP_RE.match(text):
        return False
    parts = text.split(".")
    return all(0 <= int(p) <= 255 for p in parts)


def generate_key(duration: int, label: str = "", max_devices: int = 1, key_type: str = "proxy") -> str:
    prefix = FPS_PREFIX if key_type == "fps" else PREFIX
    code = prefix + secrets.token_hex(6).upper()
    if SUPABASE_ENABLED:
        from database.postgres_db import add_key
        add_key(code, duration, label, max_devices)
    else:
        keys = _load()
        keys[code] = {
            "label": label,
            "duration": duration,
            "max_devices": max(max_devices, 1),
            "created_at": time.time(),
            "used": False,
            "used_by_ip": None,
            "used_at": None,
            "active_ips": [],
            "locked_ips": [],
            "key_type": key_type,
            "first_use_notified": False,
        }
        _save(keys)
    log.info(f"Key generated: {code} ({duration}s, max_devices={max_devices}) label={label} type={key_type}")
    return code


def redeem_key(code: str, ip: str) -> str:
    code = _normalize(code)
    from database import load, save
    if SUPABASE_ENABLED:
        from database.postgres_db import get_key as pg_get_key, update_key as pg_update_key
        k = pg_get_key(code)
        if not k:
            return "INVALID"
        if k.get("status") != "active":
            return "INVALID"
        if not is_valid_ip(ip):
            return "INVALID_IP"
        locked = k.get("locked_ips") or []
        if locked and len(locked) >= k.get("max_devices", 1):
            if ip not in locked:
                log.warning(f"Anti-rotation blocked: {code} from {ip}, locked to {locked}")
                return "IP_LOCKED"
        active = k.get("active_ips") or []
        if ip not in active and len(active) >= k.get("max_devices", 1):
            log.warning(f"Device limit reached: {code} ({len(active)}/{k['max_devices']})")
            return "DEVICE_LIMIT"
        duration = k.get("duration", 0)
        if ip not in active:
            active.append(ip)
        if ip not in locked:
            locked.append(ip)
        pg_update_key(code, {
            "active_ips": active,
            "locked_ips": locked,
            "used_at": time.time(),
        })
        db = load()
        db[ip] = {
            "status": "active",
            "expires_at": time.time() + duration,
            "key_used": code,
            "used_at": time.time(),
            "device_index": active.index(ip) + 1,
            "max_devices": k.get("max_devices", 1),
        }
        save(db)
        log.info(f"Key redeemed: {code} -> IP {ip} ({duration}s, device {active.index(ip)+1}/{k['max_devices']})")
        return "OK"

    keys = _load()
    if code not in keys:
        return "INVALID"
    k = keys[code]
    if not is_valid_ip(ip):
        return "INVALID_IP"
    if k.get("locked_ips") and len(k["locked_ips"]) >= k.get("max_devices", 1):
        if ip not in k["locked_ips"]:
            log.warning(f"Anti-rotation blocked: {code} from {ip}, locked to {k['locked_ips']}")
            return "IP_LOCKED"
    active_ips = k.get("active_ips", [])
    if ip not in active_ips and len(active_ips) >= k.get("max_devices", 1):
        log.warning(f"Device limit reached: {code} ({len(active_ips)}/{k['max_devices']})")
        return "DEVICE_LIMIT"
    duration = k["duration"]
    if k["used"]:
        pass
    else:
        k["used"] = True
    if ip not in active_ips:
        active_ips.append(ip)
    k["active_ips"] = active_ips
    if ip not in k.get("locked_ips", []):
        k["locked_ips"] = k.get("locked_ips", []) + [ip]
    k["used_by_ip"] = ip
    k["used_at"] = time.time()
    _save(keys)
    db = load()
    db[ip] = {
        "status": "active",
        "expires_at": time.time() + duration,
        "key_used": code,
        "used_at": time.time(),
        "device_index": active_ips.index(ip) + 1,
        "max_devices": k.get("max_devices", 1),
    }
    save(db)
    log.info(f"Key redeemed: {code} -> IP {ip} ({duration}s, device {active_ips.index(ip)+1}/{k['max_devices']})")
    return "OK"


def _normalize(code: str) -> str:
    code = code.upper()
    if not code.startswith(PREFIX):
        code = PREFIX + code
    return code


def get_key_info(code: str) -> Optional[Dict[str, Any]]:
    code = _normalize(code)
    if SUPABASE_ENABLED:
        from database.postgres_db import get_key as pg_get_key
        k = pg_get_key(code)
        if k:
            k["code"] = code
            k.setdefault("used", k.get("status") == "used")
            k.setdefault("used_by_ip", k.get("used_by_ip"))
            k.setdefault("created_at", k.get("created_at"))
            k.setdefault("active_ips", k.get("active_ips") or [])
            k.setdefault("locked_ips", k.get("locked_ips") or [])
        return k
    keys = _load()
    k = keys.get(code)
    if not k:
        return None
    return {"code": code, **k}


def remove_ip_from_key(code: str, ip: str) -> bool:
    code = _normalize(code)
    if SUPABASE_ENABLED:
        from database.postgres_db import get_key as pg_get_key, update_key as pg_update_key
        k = pg_get_key(code)
        if not k:
            return False
        active = [x for x in (k.get("active_ips") or []) if x != ip]
        locked = [x for x in (k.get("locked_ips") or []) if x != ip]
        updates = {"active_ips": active, "locked_ips": locked}
        if not active:
            updates["status"] = "active"
        pg_update_key(code, updates)
        log.info(f"IP {ip} removed from key {code}")
        return True
    keys = _load()
    if code not in keys:
        return False
    k = keys[code]
    if ip in k.get("active_ips", []):
        k["active_ips"] = [x for x in k["active_ips"] if x != ip]
    if ip in k.get("locked_ips", []):
        k["locked_ips"] = [x for x in k.get("locked_ips", []) if x != ip]
    if not k.get("active_ips"):
        k["used"] = False
        k["used_by_ip"] = None
    _save(keys)
    log.info(f"IP {ip} removed from key {code}")
    return True


def list_keys() -> List[Dict[str, Any]]:
    if SUPABASE_ENABLED:
        from database.postgres_db import list_keys as pg_list
        return pg_list()
    keys = _load()
    return [
        {"code": k, **v}
        for k, v in sorted(keys.items(), key=lambda x: x[1].get("created_at", 0), reverse=True)
    ]


def modify_key_duration(code: str, seconds: int) -> bool:
    code = _normalize(code)
    if SUPABASE_ENABLED:
        from database.postgres_db import get_key as pg_get_key, update_key as pg_update_key
        k = pg_get_key(code)
        if not k:
            return False
        new_duration = (k.get("duration", 0) or 0) + seconds
        if new_duration < 0:
            new_duration = 0
        pg_update_key(code, {"duration": new_duration})
        log.info(f"Key duration modified: {code} ({seconds:+d}s, now {new_duration}s)")
        return True
    keys = _load()
    if code not in keys:
        return False
    keys[code]["duration"] = keys[code].get("duration", 0) + seconds
    if keys[code]["duration"] < 0:
        keys[code]["duration"] = 0
    _save(keys)
    log.info(f"Key duration modified: {code} ({seconds:+d}s, now {keys[code]['duration']}s)")
    return True


def refresh_key(code: str) -> bool:
    code = _normalize(code)
    if SUPABASE_ENABLED:
        from database.postgres_db import get_key as pg_get_key, update_key as pg_update_key
        k = pg_get_key(code)
        if not k:
            return False
        pg_update_key(code, {
            "status": "active",
            "used_at": 0,
            "active_ips": [],
        })
        log.info(f"Key refreshed: {code}")
        return True
    keys = _load()
    if code not in keys:
        return False
    keys[code]["used"] = False
    keys[code]["used_by_ip"] = None
    keys[code]["used_at"] = None
    _save(keys)
    log.info(f"Key refreshed: {code}")
    return True


def delete_key(code: str) -> bool:
    code = _normalize_fps(code) if code.upper().startswith("FPS") else _normalize(code)
    if SUPABASE_ENABLED:
        from database.postgres_db import delete_key as pg_del
        return pg_del(code)
    keys = _load()
    if code not in keys:
        return False
    del keys[code]
    _save(keys)
    log.info(f"Key deleted: {code}")
    return True


def _normalize_fps(code: str) -> str:
    code = code.upper()
    if not code.startswith(FPS_PREFIX):
        code = FPS_PREFIX + code
    return code


def generate_fps_key(duration_days: int, label: str = "") -> str:
    return generate_key(duration_days * 86400, label, max_devices=1, key_type="fps")


def validate_fps_key(code: str, client_info: dict = None) -> dict:
    code = _normalize_fps(code)
    if SUPABASE_ENABLED:
        from database.postgres_db import get_key as pg_get_key
        k = pg_get_key(code)
        if not k:
            return {"valid": False, "error": "INVALID"}
        if k.get("key_type", "proxy") != "fps":
            return {"valid": False, "error": "WRONG_TYPE"}
        return {"valid": True, "code": code, "duration": k.get("duration", 0), "first_use": not k.get("used", False)}
    keys = _load()
    k = keys.get(code)
    if not k:
        return {"valid": False, "error": "INVALID"}
    if k.get("key_type", "proxy") != "fps":
        return {"valid": False, "error": "WRONG_TYPE"}
    is_first = not k.get("used", False)
    if not k.get("used", False):
        k["used"] = True
        k["used_at"] = time.time()
    if client_info:
        k.setdefault("active_ips", []).append(client_info.get("ip", "unknown"))
        k["used_by_ip"] = client_info.get("ip", k.get("used_by_ip"))
        k["client_info"] = client_info
    _save(keys)
    return {"valid": True, "code": code, "duration": k.get("duration", 0), "first_use": is_first}


def get_fps_key_usage(code: str) -> Optional[dict]:
    code = _normalize_fps(code)
    keys = _load()
    k = keys.get(code)
    if not k or k.get("key_type") != "fps":
        return None
    return {
        "code": code,
        "used": k.get("used", False),
        "used_at": k.get("used_at"),
        "used_by_ip": k.get("used_by_ip"),
        "client_info": k.get("client_info"),
        "first_use_notified": k.get("first_use_notified", False),
    }


def mark_fps_key_notified(code: str) -> bool:
    code = _normalize_fps(code)
    if SUPABASE_ENABLED:
        return True
    keys = _load()
    if code not in keys:
        return False
    keys[code]["first_use_notified"] = True
    _save(keys)
    return True
