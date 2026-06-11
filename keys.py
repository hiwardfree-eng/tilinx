import json, os, time, secrets, threading, re
from config import KEYS_PATH
from logger import log

_lock = threading.Lock()
PREFIX = "TILINX-"
IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

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

def is_valid_ip(text):
    if not IP_RE.match(text):
        return False
    parts = text.split(".")
    return all(0 <= int(p) <= 255 for p in parts)

def generate_key(duration: int, label: str = "", max_devices: int = 1) -> str:
    keys = _load()
    code = PREFIX + secrets.token_hex(6).upper()
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
    }
    _save(keys)
    log.info(f"Key generated: {code} ({duration}s, max_devices={max_devices}) label={label}")
    return code

def redeem_key(code: str, ip: str) -> str:
    keys = _load()
    code = code.upper()
    if not code.startswith(PREFIX):
        code = PREFIX + code
    if code not in keys:
        return "INVALID"
    k = keys[code]

    if not is_valid_ip(ip):
        return "INVALID_IP"

    # If key has locked IPs and this IP is not among them, reject (anti-rotation)
    if k.get("locked_ips") and len(k["locked_ips"]) >= k.get("max_devices", 1):
        if ip not in k["locked_ips"]:
            log.warning(f"Anti-rotation blocked: {code} from {ip}, locked to {k['locked_ips']}")
            return "IP_LOCKED"

    # Check max_devices limit
    active_ips = k.get("active_ips", [])
    if ip not in active_ips and len(active_ips) >= k.get("max_devices", 1):
        log.warning(f"Device limit reached: {code} ({len(active_ips)}/{k['max_devices']})")
        return "DEVICE_LIMIT"

    duration = k["duration"]

    # If key was already used but within device limit (multi-device key), allow
    if k["used"]:
        # Extend existing IP entry or add new one
        pass
    else:
        k["used"] = True

    # Add/update IP in active_ips
    if ip not in active_ips:
        active_ips.append(ip)
    k["active_ips"] = active_ips

    # Lock IP to prevent rotation
    if ip not in k.get("locked_ips", []):
        k["locked_ips"] = k.get("locked_ips", []) + [ip]

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
        "device_index": active_ips.index(ip) + 1,
        "max_devices": k.get("max_devices", 1),
    }
    save(db)
    log.info(f"Key redeemed: {code} -> IP {ip} ({duration}s, device {active_ips.index(ip)+1}/{k['max_devices']})")
    return "OK"

def get_key_info(code: str) -> dict:
    keys = _load()
    code = code.upper()
    if not code.startswith(PREFIX):
        code = PREFIX + code
    k = keys.get(code)
    if not k:
        return None
    return {"code": code, **k}

def remove_ip_from_key(code: str, ip: str) -> bool:
    keys = _load()
    code = code.upper()
    if not code.startswith(PREFIX):
        code = PREFIX + code
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
