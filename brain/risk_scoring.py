import time
import logging
from typing import Dict, Any, Optional, List
from .memory_store import MemoryStore
from .anomaly_engine import AnomalyEngine

log = logging.getLogger("tilinx.brain.scoring")


class RiskScoring:
    """
    Calcula score 0-100 de riesgo dinámico por IP.
    Combina: volumen, anomalías, penalidad histórica.
    """
    def __init__(self, store: MemoryStore, anomaly: AnomalyEngine):
        self.store = store
        self.anomaly = anomaly

    def calculate(self, ip: str, behaviors: list, hits: int, anomalies: Optional[Dict[str, Any]] = None) -> int:
        score = 0

        if hits > 100:
            score += 40
        elif hits > 50:
            score += 20
        elif hits > 20:
            score += 10

        if not anomalies:
            anomalies = self.anomaly.analyze(ip, behaviors, hits)
        if anomalies.get("burst"):
            score += 30
        if anomalies.get("scraping"):
            score += 25
        if anomalies.get("loop"):
            score += 20
        if anomalies.get("fast_refresh"):
            score += 15

        hist_key = f"brain:history:{ip}"
        hist_score = self.store.get(hist_key)
        if hist_score is not None:
            try:
                score += int(hist_score) * 0.3
            except (ValueError, TypeError):
                pass

        return min(int(score), 100)

    def apply_penalty(self, ip: str, reason: str) -> None:
        key = f"brain:history:{ip}"
        cur = int(self.store.get(key) or 0)
        cur += 20
        self.store.set(key, cur, ex=86400)
        log.info(f"Penalty +20 for {ip} (now {cur}, reason: {reason})")

    def decay_history(self) -> None:
        now = time.time()
        prefix = "brain:history:"
        keys_to_check = []
        with self.store._lock:
            for key in list(self.store._data.keys()):
                if key.startswith(prefix):
                    keys_to_check.append(key)
        for key in keys_to_check:
            raw = self.store.get(key)
            if raw is not None:
                try:
                    val = int(raw)
                    if val > 0:
                        decayed = max(0, val - 5)
                        self.store.set(key, decayed, ex=86400)
                except (ValueError, TypeError):
                    pass
