import json
import os
import time
import threading
from config import DB_PATH
from logger import log

_lock = threading.Lock()

def load() -> dict:
    if not os.path.exists(DB_PATH):
        return {}
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Error loading DB: {e}")
        return {}

def save(data: dict):
    with _lock:
        _backup()
        try:
            with open(DB_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            log.error(f"Error saving DB: {e}")

def _backup():
    if not os.path.exists(DB_PATH):
        return
    size = os.path.getsize(DB_PATH)
    if size < 100:
        return
    backup_path = DB_PATH + ".bak"
    try:
        import shutil
        shutil.copy2(DB_PATH, backup_path)
    except Exception:
        pass

def get_stats(db: dict) -> tuple:
    now = time.time()
    total = len(db)
    active = sum(1 for u in db.values() if u.get("status") == "active" and u.get("expires_at", 0) > now)
    expired = sum(1 for u in db.values() if u.get("status") == "active" and u.get("expires_at", 0) <= now)
    blocked = sum(1 for u in db.values() if u.get("status") == "blocked")
    return total, active, expired, blocked

def get_user_status_label(user: dict) -> str:
    now = time.time()
    status = user.get("status", "")
    if status == "blocked":
        return "🚫 Banned"
    if status == "active":
        if user.get("expires_at", 0) > now:
            rem = user["expires_at"] - now
            return f"✅ Active ({int(rem // 86400)}d {int((rem % 86400) // 3600)}h left)"
        return "⏰ Expired"
    return "❔ Not Registered"

def get_auth_status(ip: str) -> str:
    db = load()
    if ip not in db:
        return "NOT_FOUND"
    user = db[ip]
    status = user.get("status", "")
    if status == "blocked":
        return "BANNED"
    if status == "active":
        return "ACTIVE" if user.get("expires_at", 0) > time.time() else "EXPIRED"
    return "NOT_FOUND"
