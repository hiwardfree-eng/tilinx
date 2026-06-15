import os
import logging
from typing import Dict, Any, Optional, List
from .memory_store import MemoryStore
from .anomaly_engine import AnomalyEngine

log = logging.getLogger("tilinx.brain.scoring")

_PENALTY_PER_STEP = int(os.environ.get("TilinX_BRAIN_PENALTY", "20"))
_PENALTY_CAP = int(os.environ.get("TilinX_BRAIN_PENALTY_CAP", "80"))
_DECAY_RATE = int(os.environ.get("TilinX_BRAIN_DECAY", "5"))


class RiskScoring:
    """
    Calcula score 0-100 de riesgo dinamico por IP.
    Combina: volumen, anomalias, penalidad historica.
    """
    def __init__(self, store: MemoryStore, anomaly: AnomalyEngine):
        self.store = store
        self.anomaly = anomaly

    def _volume_score(self, hits: int) -> int:
        if hits > 120:
            return 35
        if hits > 80:
            return 25
        if hits > 40:
            return 15
        if hits > 15:
            return 8
        return 0

    def _anomaly_score(self, anomalies: Dict[str, Any]) -> int:
        weights = {"burst": 25, "scraping": 20, "loop": 15, "fast_refresh": 12}
        return sum(weights.get(k, 0) for k in anomalies)

    def calculate(self, ip: str, behaviors: list, hits: int, anomalies: Optional[Dict[str, Any]] = None) -> int:
        score = self._volume_score(hits)

        if not anomalies:
            anomalies = self.anomaly.analyze(ip, behaviors, hits)
        score += self._anomaly_score(anomalies)

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
        cur = min(cur + _PENALTY_PER_STEP, _PENALTY_CAP)
        self.store.set(key, cur, ex=86400)
        log.info("Penalty +%s for %s (now %s, reason: %s)", _PENALTY_PER_STEP, ip, cur, reason)

    def decay_history(self) -> None:
        prefix = "brain:history:"
        for key in self.store.keys(prefix):
            raw = self.store.get(key)
            if raw is not None:
                try:
                    val = int(raw)
                    if val > 0:
                        decayed = max(0, val - _DECAY_RATE)
                        self.store.set(key, decayed, ex=86400)
                except (ValueError, TypeError):
                    pass
