import json, os, time, secrets, threading
from typing import Optional, Dict, Any, List, Tuple
from config import BASE_DIR, SUPABASE_ENABLED
from logger import log
from file_utils import safe_read_json, safe_write_json

ADMINX_PATH = os.path.join(BASE_DIR, "adminx.json")
_lock = threading.Lock()
PREFIX = "ADMINX-"


def _load() -> Dict[str, Any]:
    if SUPABASE_ENABLED:
        from database.postgres_db import list_users
        users = list_users()
        result = {}
        for u in users:
            username = u.pop("username", "")
            result[username] = {
                "key": u.get("password_hash", ""),
                "created_by": 0,
                "created_at": u.get("created_at", 0),
                "max_key_duration_days": 30,
                "active": u.get("is_active", True),
            }
        return result
    if not os.path.exists(ADMINX_PATH):
        return {}
    return safe_read_json(ADMINX_PATH, {})


def _save(data: dict) -> None:
    if SUPABASE_ENABLED:
        return
    with _lock:
        safe_write_json(ADMINX_PATH, data)


def create_user(username: str, created_by: int, max_days: int = 30) -> Tuple[Optional[str], str]:
    data = _load()
    if username in data:
        return None, "USERNAME_EXISTS"
    key = PREFIX + secrets.token_hex(8).upper()
    if SUPABASE_ENABLED:
        from database.postgres_db import add_user
        add_user(username, password_hash=key, email=f"{username}@tilinx.local", role="adminx")
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


def remove_user(username: str) -> bool:
    if SUPABASE_ENABLED:
        from database.postgres_db import delete_user as pg_del
        return pg_del(username)
    data = _load()
    if username not in data:
        return False
    del data[username]
    _save(data)
    log.info(f"AdminX user removed: {username}")
    return True


def set_active(username: str, active: bool) -> bool:
    if SUPABASE_ENABLED:
        from database.postgres_db import set_user_active as pg_set
        return pg_set(username, active)
    data = _load()
    if username not in data:
        return False
    data[username]["active"] = active
    _save(data)
    log.info(f"AdminX user {username} active={active}")
    return True


def get_user(username: str) -> Optional[Dict[str, Any]]:
    if SUPABASE_ENABLED:
        from database.postgres_db import get_user as pg_get
        u = pg_get(username)
        if u:
            return {
                "key": u.get("password_hash", ""),
                "created_by": u.get("created_by", 0),
                "created_at": u.get("created_at", 0),
                "is_active": u.get("is_active", True),
                "role": u.get("role", "user"),
            }
        return None
    data = _load()
    return data.get(username)


def find_by_key(key: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    if SUPABASE_ENABLED:
        from database.postgres_db import list_users
        for u in list_users():
            if u.get("password_hash") == key:
                return u["username"], {
                    "key": u.get("password_hash", ""),
                    "created_by": 0,
                    "created_at": u.get("created_at", 0),
                    "is_active": u.get("is_active", True),
                    "role": u.get("role", "user"),
                }
        return None, None
    data = _load()
    for username, info in data.items():
        if info["key"] == key:
            return username, info
    return None, None


def list_users() -> List[Tuple[str, Dict[str, Any]]]:
    if SUPABASE_ENABLED:
        from database.postgres_db import list_users as pg_list
        users = pg_list()
        return [
            (u["username"], {
                "key": u.get("password_hash", ""),
                "created_by": u.get("created_by", 0),
                "created_at": u.get("created_at", 0),
                "is_active": u.get("is_active", True),
                "role": u.get("role", "user"),
            })
            for u in users
        ]
    data = _load()
    return sorted(data.items(), key=lambda x: x[1].get("created_at", 0), reverse=True)
