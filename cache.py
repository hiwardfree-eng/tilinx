import time
import threading
from typing import Optional, Dict, Any

_lock = threading.Lock()
_cache: Dict[str, tuple] = {}
CACHE_TTL = 300


def get(key: str) -> Optional[Any]:
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        value, expires = entry
        if time.time() > expires:
            del _cache[key]
            return None
        return value


def set(key: str, value: Any, ttl: int = CACHE_TTL) -> None:
    with _lock:
        _cache[key] = (value, time.time() + ttl)


def delete(key: str) -> None:
    with _lock:
        _cache.pop(key, None)


def clear() -> None:
    with _lock:
        _cache.clear()


def stats() -> Dict[str, Any]:
    with _lock:
        return {
            "entries": len(_cache),
            "keys": list(_cache.keys()),
        }
