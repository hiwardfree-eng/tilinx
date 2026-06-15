import os, json, time, logging
import threading
from typing import Dict, Any, List, Optional

log = logging.getLogger("tilinx.brain.memory")


class MemoryStore:
    """
    Redis-compatible in-memory store.
    Drop-in replacement: swap self.store for a real Redis client when available.
    Thread-safe via lock. Background cleanup of expired keys.
    """
    MAX_KEYS = 100000
    MAX_LIST_ITEMS = 10000

    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self._lists: Dict[str, list] = {}
        self._expiry: Dict[str, float] = {}
        self._stop_cleanup = threading.Event()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def _cleanup_loop(self) -> None:
        while not self._stop_cleanup.is_set():
            self.cleanup_expired()
            self._stop_cleanup.wait(60)

    def stop(self) -> None:
        self._stop_cleanup.set()

    def _expire(self, key: str) -> None:
        exp = self._expiry.get(key)
        if exp is not None and time.time() > exp:
            self._data.pop(key, None)
            self._lists.pop(key, None)
            self._expiry.pop(key, None)

    def _get_raw(self, key: str):
        self._expire(key)
        return self._data.get(key)

    def get(self, key: str):
        with self._lock:
            return self._get_raw(key)

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        with self._lock:
            if key not in self._data and len(self._data) >= self.MAX_KEYS:
                return
            self._data[key] = value
            if ex is not None:
                self._expiry[key] = time.time() + ex

    def incr(self, key: str) -> int:
        with self._lock:
            self._expire(key)
            val = int(self._data.get(key, 0))
            val += 1
            self._data[key] = val
            return val

    def incr_expire(self, key: str, seconds: int) -> int:
        with self._lock:
            self._expire(key)
            val = int(self._data.get(key, 0))
            val += 1
            self._data[key] = val
            self._expiry[key] = time.time() + seconds
            return val

    def decr(self, key: str) -> int:
        with self._lock:
            self._expire(key)
            val = int(self._data.get(key, 0))
            val -= 1
            self._data[key] = val
            return val

    def expire(self, key: str, seconds: int) -> None:
        with self._lock:
            self._expiry[key] = time.time() + seconds

    def ttl(self, key: str) -> int:
        with self._lock:
            exp = self._expiry.get(key)
            if exp is None:
                return -1
            remaining = int(exp - time.time())
            return max(0, remaining)

    def keys(self, pattern: str = "") -> list:
        with self._lock:
            if pattern:
                return [k for k in self._data if k.startswith(pattern)]
            return list(self._data.keys())

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)
            self._lists.pop(key, None)
            self._expiry.pop(key, None)

    def lpush(self, key: str, value: Any) -> None:
        with self._lock:
            if key not in self._lists:
                self._lists[key] = []
            self._lists[key].insert(0, value)
            if len(self._lists[key]) > self.MAX_LIST_ITEMS:
                self._lists[key] = self._lists[key][:self.MAX_LIST_ITEMS]

    def rpush(self, key: str, value: Any) -> None:
        with self._lock:
            if key not in self._lists:
                self._lists[key] = []
            self._lists[key].append(value)
            if len(self._lists[key]) > self.MAX_LIST_ITEMS:
                self._lists[key] = self._lists[key][-self.MAX_LIST_ITEMS:]

    def lrange(self, key: str, start: int, end: int) -> List[Any]:
        with self._lock:
            items = self._lists.get(key, [])
            n = len(items)
            if n == 0:
                return []
            if start < 0:
                start = max(0, n + start)
            if end < 0:
                end = n + end + 1
            return items[start:end] if start < n else []

    def cleanup_expired(self) -> int:
        now = time.time()
        removed = 0
        with self._lock:
            expired_keys = [k for k, exp in self._expiry.items() if now > exp]
            for k in expired_keys:
                self._data.pop(k, None)
                self._lists.pop(k, None)
                self._expiry.pop(k, None)
                removed += 1
        return removed

    def ltrim(self, key: str, start: int, end: int) -> None:
        with self._lock:
            items = self._lists.get(key, [])
            self._lists[key] = items[start:end]

    def llen(self, key: str) -> int:
        with self._lock:
            return len(self._lists.get(key, []))

    def smembers(self, key: str) -> set:
        with self._lock:
            self._expire(key)
            val = self._data.get(key)
            if isinstance(val, set):
                return set(val)
            if isinstance(val, list):
                return set(val)
            return set()

    def sadd(self, key: str, member: Any) -> None:
        with self._lock:
            self._expire(key)
            if key not in self._data or not isinstance(self._data.get(key), set):
                self._data[key] = set()
            self._data[key].add(member)

    def srem(self, key: str, member: Any) -> None:
        with self._lock:
            self._expire(key)
            s = self._data.get(key)
            if isinstance(s, set):
                s.discard(member)

    def persist_to_disk(self, path: str) -> None:
        import tempfile
        tmp = path + ".tmp"
        with self._lock:
            payload = {
                "data": {k: v for k, v in self._data.items() if not isinstance(v, set)},
                "sets": {k: list(v) for k, v in self._data.items() if isinstance(v, set)},
                "lists": dict(self._lists),
                "expiry": dict(self._expiry),
            }
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception as exc:
            log.error("persist_to_disk failed: %s", exc)

    def load_from_disk(self, path: str) -> None:
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            log.error("load_from_disk failed: %s", exc)
            return
        with self._lock:
            self._data.clear()
            self._lists.clear()
            self._expiry.clear()
            self._data.update(payload.get("data", {}))
            for k, v in payload.get("sets", {}).items():
                self._data[k] = set(v)
            self._lists.update(payload.get("lists", {}))
            self._expiry.update(payload.get("expiry", {}))

    def pipeline(self):
        return self._Pipeline(self)

    class _Pipeline:
        def __init__(self, store):
            self.store = store
            self._cmds = []

        def incr(self, key):
            self._cmds.append(("incr", (key,), {}))
            return self

        def expire(self, key, seconds):
            self._cmds.append(("expire", (key, seconds), {}))
            return self

        def incr_expire(self, key, seconds):
            self._cmds.append(("incr_expire", (key, seconds), {}))
            return self

        def execute(self):
            results = []
            for cmd, args, kwargs in self._cmds:
                method = getattr(self.store, cmd)
                results.append(method(*args, **kwargs))
            self._cmds = []
            return results
