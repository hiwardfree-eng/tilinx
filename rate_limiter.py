import os, time, threading, json, logging, re
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict

logger = logging.getLogger("tilinx.ratelimit")

STORAGE_PATH = os.environ.get("TilinX_RL_STORAGE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "rate_limits.json"))

_rlock = threading.Lock()
_windows: Dict[str, List[float]] = defaultdict(list)
_adaptive_scores: Dict[str, float] = defaultdict(float)
_decay_interval = 300
_MAX_WINDOW_ENTRIES = 2000
_IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

SUSPICIOUS_PATTERNS = [
    "/admin", "/api/", "/config", "/.env", "/.git",
    "/wp-admin", "/wp-login", "/xmlrpc", "/phpmyadmin",
    "select", "union", "drop ", "delete ", "insert ", "exec(",
    "<script", "alert(", "onerror=", "onload=",
    "../", "..\\", "%2e%2e%2f",
    "/etc/passwd", "/etc/shadow",
]


def _is_valid_ip(ip: str) -> bool:
    return bool(_IP_RE.match(ip))


def _get_suspicious_score(path: str) -> float:
    path_lower = path.lower()
    score = 0.0
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern.lower() in path_lower:
            score += 0.3
    if any(c in path for c in "'\"`"):
        score += 0.5
    return min(score, 3.0)


def _get_base_limit(ip: str) -> int:
    try:
        per_second = int(os.environ.get("TilinX_RL_PER_SECOND", "10"))
    except (ValueError, TypeError):
        per_second = 10
    try:
        per_minute = int(os.environ.get("TilinX_RL_PER_MINUTE", "60"))
    except (ValueError, TypeError):
        per_minute = 60
    adaptive = _adaptive_scores.get(ip, 0.0)
    if adaptive > 2.0:
        per_second = max(2, per_second // 4)
        per_minute = max(10, per_minute // 4)
    elif adaptive > 1.0:
        per_second = max(4, per_second // 2)
        per_minute = max(20, per_minute // 2)
    return min(per_second, per_minute)


def check(ip: str, path: str = "", endpoint: str = "") -> Tuple[bool, Dict[str, Any]]:
    now = time.time()
    base_limit = _get_base_limit(ip)
    key = f"{ip}:{endpoint}" if endpoint else ip

    score = _get_suspicious_score(path)
    if score > 0:
        with _rlock:
            _adaptive_scores[ip] = min(_adaptive_scores.get(ip, 0.0) + score * 0.1, 5.0)

    with _rlock:
        timestamps = _windows[key]
        # Prune old entries
        cutoff = now - 60
        if timestamps and timestamps[0] < cutoff:
            # Binary search would be faster, but list is small
            timestamps = [t for t in timestamps if t >= cutoff]
        timestamps.append(now)
        # Cap size to prevent memory leak from pathological keys
        if len(timestamps) > _MAX_WINDOW_ENTRIES:
            timestamps = timestamps[-_MAX_WINDOW_ENTRIES:]
        _windows[key] = timestamps
        count_60s = len(timestamps)
        recent_10s = sum(1 for t in timestamps if now - t < 10)

    allowed = count_60s <= base_limit and recent_10s <= max(5, base_limit // 4)
    remaining = max(0, base_limit - count_60s)
    reset_after = 60.0

    if not allowed:
        logger.warning(f"Rate limited: {key} ({count_60s}/{base_limit} in 60s)")
    if score > 1.0:
        logger.info(f"Suspicious score: {ip} ({path[:60]}): {score:.2f}")

    return allowed, {
        "limit": base_limit,
        "remaining": remaining,
        "reset_after": reset_after,
        "count_60s": count_60s,
        "suspicious_score": round(score, 2),
        "adaptive_score": round(_adaptive_scores.get(ip, 0.0), 2),
    }


def reset(ip: str) -> None:
    with _rlock:
        keys = [k for k in _windows if k.startswith(ip)]
        for k in keys:
            _windows.pop(k, None)
        _adaptive_scores.pop(ip, None)


def _window_cleanup_loop() -> None:
    while True:
        time.sleep(300)
        now = time.time()
        cutoff = now - 120
        with _rlock:
            for key in list(_windows.keys()):
                ts_list = _windows[key]
                if not ts_list or ts_list[-1] < cutoff:
                    _windows.pop(key, None)


def _adaptive_decay_loop() -> None:
    while True:
        time.sleep(_decay_interval)
        with _rlock:
            for ip in list(_adaptive_scores.keys()):
                _adaptive_scores[ip] = max(0, _adaptive_scores[ip] - 0.5)
                if _adaptive_scores[ip] <= 0:
                    _adaptive_scores.pop(ip, None)


threading.Thread(target=_adaptive_decay_loop, daemon=True).start()
threading.Thread(target=_window_cleanup_loop, daemon=True).start()
