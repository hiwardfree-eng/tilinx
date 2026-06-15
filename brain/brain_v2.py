import os
import time
import json
import logging
from typing import Dict, Any, Optional
from .types import Decision, BrainResult, RequestContext
from .memory_store import MemoryStore
from .behavior_tracker import BehaviorTracker
from .anomaly_engine import AnomalyEngine
from .risk_scoring import RiskScoring
from .decision_engine_v2 import DecisionEngineV2

log = logging.getLogger("tilinx.brain.v2")

_PERSIST_PATH = os.environ.get("TilinX_BRAIN_PERSIST_PATH", "")
_PERSIST_INTERVAL = int(os.environ.get("TilinX_BRAIN_PERSIST_INTERVAL", "300"))


class BrainV2:
    """
    Brain V2 — Anti-bot + anomaly detection layer for TilinX proxy.
    Flujo:
      1. track behavior (always)
      2. check cache for fast block
      3. analyze anomalies
      4. calculate risk score
      5. decide action
      6. cache decision
    """
    def __init__(self, store: Optional[MemoryStore] = None):
        self.store = store or MemoryStore()
        self.tracker = BehaviorTracker(self.store)
        self.anomaly = AnomalyEngine(self.store)
        self.scoring = RiskScoring(self.store, self.anomaly)
        self.engine = DecisionEngineV2()
        self._load_persisted()
        self._last_persist = time.time()

    def _load_persisted(self) -> None:
        if _PERSIST_PATH:
            self.store.load_from_disk(_PERSIST_PATH)

    def _maybe_persist(self) -> None:
        if _PERSIST_PATH and time.time() - self._last_persist > _PERSIST_INTERVAL:
            self.store.persist_to_disk(_PERSIST_PATH)
            self._last_persist = time.time()

    def process(self, request: RequestContext) -> BrainResult:
        ip = request.get("ip", "?")
        path = request.get("path", "/")

        self.tracker.track(request)

        cached = self._get_cached_decision(ip)
        if cached and cached.get("decision", {}).get("action") in ("block", "challenge"):
            cached["_from_cache"] = True
            return cached

        behaviors = self.tracker.get_recent(ip, 30)
        hits = self.tracker.get_hits(ip)
        reputation = self.tracker.get_known_bad(ip)
        signals = self.anomaly.analyze(ip, behaviors, hits)
        score = self.scoring.calculate(ip, behaviors, hits, signals)
        score = min(score + reputation, 100)
        decision = self.engine.decide(request, score)

        result = BrainResult(
            ip=ip,
            risk_score=score,
            decision=decision,
            signals=list(signals.keys()),
        )

        if decision["action"] in ("block", "challenge"):
            self.tracker.mark_bad(ip)
            self.scoring.apply_penalty(ip, decision["reason"])

        self._cache_decision(ip, result, decision.get("ttl", 30))
        if decision["action"] in ("block", "challenge"):
            log.warning(
                "[BRAIN] %s ip=%s path=%s score=%s reason=%s signals=%s",
                decision["action"].upper(), ip, path, score,
                decision["reason"], list(signals.keys()),
            )
        elif decision["action"] == "rate_limit":
            log.info(
                "[BRAIN] RATE_LIMIT ip=%s score=%s delay=%ss",
                ip, score, decision.get("throttle", 0),
            )

        self._maybe_persist()
        return result

    def _get_cached_decision(self, ip: str) -> Optional[BrainResult]:
        cached = self.store.get(f"brain:decision:{ip}")
        if cached:
            try:
                return json.loads(cached) if isinstance(cached, str) else cached
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def _cache_decision(self, ip: str, result: BrainResult, ttl: int) -> None:
        serializable = {
            "ip": result["ip"],
            "risk_score": result["risk_score"],
            "decision": dict(result["decision"]),
            "signals": list(result.get("signals", [])),
        }
        self.store.set(f"brain:decision:{ip}", json.dumps(serializable), ex=ttl)
