import json, os, time, secrets, threading
from config import BASE_DIR
from logger import log

ADMINX_PATH = os.path.join(BASE_DIR, "adminx.json")
_lock = threading.Lock()
PREFIX = "ADMINX-"

def _load():
    if not os.path.exists(ADMINX_PATH):
        return {}
    try:
        with open(ADMINX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Error loading adminx.json: {e}")
        return {}

def _save(data):
    with _lock:
        try:
            with open(ADMINX_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"Error saving adminx.json: {e}")

def create_user(username, created_by, max_days=30):
    data = _load()
    if username in data:
        return None, "USERNAME_EXISTS"
    key = PREFIX + secrets.token_hex(8).upper()
    data[username] = {
        "key": key,
        "created_by": created_by,
        "created_at": time.time(),
        "max_key_duration_days": max(max_days, 1),
        "active": True,
    }
    _save(data)
    log.info(f"AdminX user created: {username} key={key} max_days={max_days}")
    return key, "OK"

def remove_user(username):
    data = _load()
    if username not in data:
        return False
    del data[username]
    _save(data)
    log.info(f"AdminX user removed: {username}")
    return True

def set_active(username, active):
    data = _load()
    if username not in data:
        return False
    data[username]["active"] = active
    _save(data)
    log.info(f"AdminX user {username} active={active}")
    return True

def get_user(username):
    data = _load()
    return data.get(username)

def find_by_key(key):
    data = _load()
    for username, info in data.items():
        if info["key"] == key:
            return username, info
    return None, None

def list_users():
    data = _load()
    return sorted(data.items(), key=lambda x: x[1].get("created_at", 0), reverse=True)
