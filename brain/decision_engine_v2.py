import time
import logging
from typing import Dict, Any
from .types import Decision

log = logging.getLogger("tilinx.brain.decision")


class DecisionEngineV2:
    """
    Decide la acción basada en risk score + contexto.
    allow  → pasar sin cambios
    rate_limit → reducir velocidad
    challenge → pedir verificación
    block  → denegar acceso
    """
    def decide(self, request: Dict[str, Any], score: int) -> Decision:
        if score >= 80:
            return {
                "action": "block",
                "reason": "high_risk_bot",
                "score": score,
                "ttl": 300,
            }
        if score >= 60:
            return {
                "action": "challenge",
                "reason": "suspicious_behavior",
                "score": score,
                "ttl": 120,
            }
        if score >= 30:
            throttle = max(0.1, score / 100)
            return {
                "action": "rate_limit",
                "reason": "elevated_risk",
                "score": score,
                "ttl": 60,
                "throttle": round(throttle, 2),
            }
        return {
            "action": "allow",
            "reason": "normal",
            "score": score,
            "ttl": 30,
        }
