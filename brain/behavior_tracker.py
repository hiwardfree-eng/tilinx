import os
import time
import json
import logging
from typing import Dict, Any, Optional, List
from .memory_store import MemoryStore

log = logging.getLogger("tilinx.brain.behavior")

_MAX_EVENTS = 500


class BehaviorTracker:
    """
    Rastrea comportamiento real por IP.
    - sliding window de requests
    - paths visitados
    - frecuencia por endpoint
    - reputacion acumulada
    """
    def __init__(self, store: MemoryStore):
        self.store = store
        self.window = int(os.environ.get("TilinX_BRAIN_WINDOW", "60"))

    def track(self, request: Dict[str, Any]) -> None:
        ip = request.get("ip", "?")
        path = request.get("path", "/")
        method = request.get("method", "GET")
        host = request.get("host", "")
        now = time.time()

        key = f"brain:behavior:{ip}"
        event = {"ts": now, "path": path, "method": method, "host": host}
        self.store.lpush(key, json.dumps(event))
        self.store.ltrim(key, 0, _MAX_EVENTS)
        self.store.expire(key, 3600)

        self.store.incr_expire(f"brain:hits:{ip}", self.window)

        path_key = f"brain:path:{ip}:{path}"
        self.store.incr_expire(path_key, self.window)

    def get_recent(self, ip: str, count: int = 30) -> List[Dict]:
        raw = self.store.lrange(f"brain:behavior:{ip}", 0, count - 1)
        now = time.time()
        events = []
        for r in raw:
            try:
                ev = json.loads(r) if isinstance(r, str) else r
                if isinstance(ev, dict) and now - ev.get("ts", 0) < 120:
                    events.append(ev)
            except (json.JSONDecodeError, TypeError):
                pass
        return events

    def get_hits(self, ip: str) -> int:
        val = self.store.get(f"brain:hits:{ip}")
        return int(val) if val else 0

    def get_path_frequency(self, ip: str, path: str) -> int:
        val = self.store.get(f"brain:path:{ip}:{path}")
        return int(val) if val else 0

    def get_unique_paths(self, ip: str, count: int = 50) -> set:
        events = self.get_recent(ip, count)
        return {e.get("path", "?") for e in events if isinstance(e, dict)}

    def get_known_bad(self, ip: str) -> int:
        val = self.store.get(f"brain:reputation:{ip}")
        return int(val) if val else 0

    def mark_bad(self, ip: str, points: int = 10) -> None:
        key = f"brain:reputation:{ip}"
        cur = int(self.store.get(key) or 0) + points
        self.store.set(key, min(cur, 100), ex=86400)
