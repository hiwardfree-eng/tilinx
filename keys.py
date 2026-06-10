import json, os, time, secrets, threading
from config import KEYS_PATH
from logger import log

_lock = threading.Lock()
PREFIX = "TILINX-"

def _load():
    if not os.path.exists(KEYS_PATH):
        return {}
    try:
        with open(KEYS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Error loading keys: {e}")
        return {}

def _save(data: dict):
    with _lock:
        try:
            with open(KEYS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            log.error(f"Error saving keys: {e}")

def generate_key(duration: int, label: str = "") -> str:
    keys = _load()
    code = PREFIX + secrets.token_hex(6).upper()
    keys[code] = {
        "label": label,
        "duration": duration,
        "created_at": time.time(),
        "used": False,
        "used_by_ip": None,
        "used_at": None,
    }
    _save(keys)
    log.info(f"Key generated: {code} ({duration}s) label={label}")
    return code

def redeem_key(code: str, ip: str) -> str:
    keys = _load()
    code = code.upper()
    if not code.startswith(PREFIX):
        code = PREFIX + code
    if code not in keys:
        return "INVALID"
    k = keys[code]
    if k["used"]:
        return "ALREADY_USED"
    duration = k["duration"]
    k["used"] = True
    k["used_by_ip"] = ip
    k["used_at"] = time.time()
    _save(keys)
    from database import load, save
    db = load()
    db[ip] = {
        "status": "active",
        "expires_at": time.time() + duration,
        "key_used": code,
        "used_at": time.time(),
    }
    save(db)
    log.info(f"Key redeemed: {code} → IP {ip} ({duration}s)")
    return "OK"

def list_keys() -> list:
    keys = _load()
    return [
        {"code": k, **v}
        for k, v in sorted(keys.items(), key=lambda x: x[1].get("created_at", 0), reverse=True)
    ]

def modify_key_duration(code: str, seconds: int) -> bool:
    keys = _load()
    code = code.upper()
    if not code.startswith(PREFIX):
        code = PREFIX + code
    if code not in keys:
        return False
    keys[code]["duration"] = keys[code].get("duration", 0) + seconds
    if keys[code]["duration"] < 0:
        keys[code]["duration"] = 0
    _save(keys)
    log.info(f"Key duration modified: {code} ({seconds:+d}s, now {keys[code]['duration']}s)")
    return True

def refresh_key(code: str) -> bool:
    keys = _load()
    code = code.upper()
    if not code.startswith(PREFIX):
        code = PREFIX + code
    if code not in keys:
        return False
    keys[code]["used"] = False
    keys[code]["used_by_ip"] = None
    keys[code]["used_at"] = None
    _save(keys)
    log.info(f"Key refreshed: {code}")
    return True

def delete_key(code: str) -> bool:
    keys = _load()
    code = code.upper()
    if not code.startswith(PREFIX):
        code = PREFIX + code
    if code not in keys:
        return False
    del keys[code]
    _save(keys)
    log.info(f"Key deleted: {code}")
    return True
