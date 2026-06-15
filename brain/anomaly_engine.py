import os
import time
import logging
from typing import Dict, Any, List, Set
from .memory_store import MemoryStore

log = logging.getLogger("tilinx.brain.anomaly")

_WHITELIST = {"127.0.0.1", "::1", "localhost"}
_CUSTOM_WL = {ip.strip() for ip in os.environ.get("TilinX_BRAIN_WHITELIST", "").split(",") if ip.strip()}


class AnomalyEngine:
    """
    Detecta patrones sospechosos:
    - Burst: muchas requests en poco tiempo (granular)
    - Scraping: alta repeticion de paths
    - Loop: misma URL repetida
    - Fast refresh: requests rapidas consecutivas
    """
    def __init__(self, store: MemoryStore):
        self.store = store
        self.burst_hits = int(os.environ.get("TilinX_BRAIN_BURST_HITS", "150"))
        self.burst_window = float(os.environ.get("TilinX_BRAIN_BURST_WINDOW", "2.0"))
        self.burst_max = int(os.environ.get("TilinX_BRAIN_BURST_MAX", "8"))
        self.scrape_ratio = float(os.environ.get("TilinX_BRAIN_SCRAPE_RATIO", "0.12"))
        self.scrape_min = int(os.environ.get("TilinX_BRAIN_SCRAPE_MIN", "15"))
        self.refresh_gap = float(os.environ.get("TilinX_BRAIN_REFRESH_GAP", "1.2"))

    def is_whitelisted(self, ip: str) -> bool:
        return ip in _WHITELIST or ip in _CUSTOM_WL

    def detect_burst(self, ip: str, hits: int) -> bool:
        if hits > self.burst_hits:
            return True
        ts_key = f"brain:burst_ts:{ip}"
        count_key = f"brain:burst_count:{ip}"
        last_ts = self.store.get(ts_key)
        now = time.time()

        if last_ts is not None:
            try:
                last_ts = float(last_ts)
            except (ValueError, TypeError):
                last_ts = now

            if now - last_ts < self.burst_window:
                count = int(self.store.get(count_key) or 0) + 1
                self.store.set(count_key, count, ex=10)
                if count > self.burst_max:
                    return True
            else:
                self.store.set(count_key, 1, ex=10)
        else:
            self.store.set(count_key, 1, ex=10)

        self.store.set(ts_key, now, ex=10)
        return False

    def detect_scraping(self, behaviors: List[Dict]) -> bool:
        if len(behaviors) < self.scrape_min:
            return False
        paths = [b.get("path", "?") for b in behaviors if isinstance(b, dict)]
        if not paths:
            return False
        unique = len(set(paths))
        return unique < len(paths) * self.scrape_ratio

    def detect_loop(self, behaviors: List[Dict]) -> bool:
        if len(behaviors) < 5:
            return False
        paths = [b.get("path", "?") for b in behaviors if isinstance(b, dict)]
        if len(paths) < 5:
            return False
        return len(set(paths[-5:])) == 1

    def detect_fast_refresh(self, behaviors: List[Dict]) -> bool:
        if len(behaviors) < 3:
            return False
        timestamps = [b.get("ts", 0) for b in behaviors[:3] if isinstance(b, dict)]
        if len(timestamps) < 3:
            return False
        gaps = [timestamps[i] - timestamps[i + 1] for i in range(len(timestamps) - 1)]
        return all(0 < g < self.refresh_gap for g in gaps)

    def analyze(self, ip: str, behaviors: List[Dict], hits: int) -> Dict[str, Any]:
        if self.is_whitelisted(ip):
            return {}

        signals = {}
        if self.detect_burst(ip, hits):
            signals["burst"] = "high_volume_burst"
        if self.detect_scraping(behaviors):
            signals["scraping"] = "high_path_repetition"
        if self.detect_loop(behaviors):
            signals["loop"] = "same_url_loop"
        if self.detect_fast_refresh(behaviors):
            signals["fast_refresh"] = "rapid_request_loop"
        return signals
