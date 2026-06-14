from typing import TypedDict, Optional, List, Dict, Any


class RequestContext(TypedDict, total=False):
    ip: str
    path: str
    method: str
    host: str
    user_agent: str
    headers: Dict[str, str]
    body: str


class Decision(TypedDict, total=False):
    action: str           # allow | rate_limit | challenge | block
    reason: str
    score: int
    ttl: int              # seconds for the decision to be cached


class BrainResult(TypedDict, total=False):
    ip: str
    risk_score: int
    decision: Decision
    signals: List[str]
