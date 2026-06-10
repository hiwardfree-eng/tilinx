import time
import threading
from typing import Optional

_lock = threading.Lock()
_cache: dict[str, tuple] = {}
CACHE_TTL = 300  # 5 min default

def get(key: str) -> Optional[object]:
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        value, expires = entry
        if time.time() > expires:
            del _cache[key]
            return None
        return value

def set(key: str, value: object, ttl: int = CACHE_TTL):
    with _lock:
        _cache[key] = (value, time.time() + ttl)

def delete(key: str):
    with _lock:
        _cache.pop(key, None)

def clear():
    with _lock:
        _cache.clear()

def stats() -> dict:
    with _lock:
        return {
            "entries": len(_cache),
            "keys": list(_cache.keys()),
        }
