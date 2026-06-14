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


class BrainV2:
    """
    Brain V2 — Anti-bot + anomaly detection layer for TilinX proxy.
    Flujo:
      1. track behavior
      2. analyze anomalies
      3. calculate risk score
      4. decide action
      5. cache decision
    """
    def __init__(self, store: Optional[MemoryStore] = None):
        self.store = store or MemoryStore()
        self.tracker = BehaviorTracker(self.store)
        self.anomaly = AnomalyEngine(self.store)
        self.scoring = RiskScoring(self.store, self.anomaly)
        self.engine = DecisionEngineV2()

    def process(self, request: RequestContext) -> BrainResult:
        ip = request.get("ip", "?")
        path = request.get("path", "/")

        cached = self._get_cached_decision(ip)
        if cached and cached.get("decision", {}).get("action") in ("block", "challenge"):
            cached["_from_cache"] = True
            return cached

        self.tracker.track(request)
        behaviors = self.tracker.get_recent(ip, 30)
        hits = self.tracker.get_hits(ip)
        signals = self.anomaly.analyze(ip, behaviors, hits)
        score = self.scoring.calculate(ip, behaviors, hits, signals)
        decision = self.engine.decide(request, score)

        result = BrainResult(
            ip=ip,
            risk_score=score,
            decision=decision,
            signals=list(signals.keys()),
        )

        self.scoring.apply_penalty(ip, decision["reason"])
        self._cache_decision(ip, result, decision.get("ttl", 30))
        if decision["action"] in ("block", "challenge"):
            log.warning(
                f"[BRAIN] {decision['action'].upper()} "
                f"ip={ip} path={path} "
                f"score={score} reason={decision['reason']} "
                f"signals={list(signals.keys())}"
            )

        return result

    def _get_cached_decision(self, ip: str) -> Optional[BrainResult]:
        cached = self.store.get(f"brain:decision:{ip}")
        if cached:
            try:
                return json.loads(cached)
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
