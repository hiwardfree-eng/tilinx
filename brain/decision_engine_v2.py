import os
import logging
from typing import Dict, Any
from .types import Decision

log = logging.getLogger("tilinx.brain.decision")

_BLOCK_THRESHOLD = int(os.environ.get("TilinX_BRAIN_BLOCK", "80"))
_CHALLENGE_THRESHOLD = int(os.environ.get("TilinX_BRAIN_CHALLENGE", "55"))
_RATE_LIMIT_THRESHOLD = int(os.environ.get("TilinX_BRAIN_RATELIMIT", "25"))


class DecisionEngineV2:
    """
    Decide la accion basada en risk score + contexto.
    allow       -> pasar sin cambios
    rate_limit  -> reducir velocidad
    challenge   -> pedir verificacion
    block       -> denegar acceso
    """
    def decide(self, request: Dict[str, Any], score: int) -> Decision:
        if score >= _BLOCK_THRESHOLD:
            return {
                "action": "block",
                "reason": "high_risk_bot",
                "score": score,
                "ttl": 300,
            }
        if score >= _CHALLENGE_THRESHOLD:
            return {
                "action": "challenge",
                "reason": "suspicious_behavior",
                "score": score,
                "ttl": 120,
            }
        if score >= _RATE_LIMIT_THRESHOLD:
            delay = round(max(0.1, score / 100), 2)
            return {
                "action": "rate_limit",
                "reason": "elevated_risk",
                "score": score,
                "ttl": 60,
                "throttle": delay,
            }
        return {
            "action": "allow",
            "reason": "normal",
            "score": score,
            "ttl": 30,
        }
