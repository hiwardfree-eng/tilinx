import os
import time
import threading
from typing import Optional, Dict, Any
from logger import log

try:
    import psutil
except ImportError:
    psutil = None

METRICS: Dict[str, Any] = {}
_lock = threading.Lock()
_interval = 30

_START_TIME = time.time()


def _collect_cpu() -> Optional[float]:
    if psutil:
        try:
            return psutil.cpu_percent(interval=0.1)
        except Exception:
            return None
    return None


def _collect_memory() -> Optional[Dict[str, int]]:
    if psutil:
        try:
            mem = psutil.virtual_memory()
            return {
                "total_mb": mem.total // (1024 * 1024),
                "available_mb": mem.available // (1024 * 1024),
                "percent": mem.percent,
            }
        except Exception:
            return None
    return None


def _collect_disk() -> Optional[Dict[str, Any]]:
    if psutil:
        try:
            d = psutil.disk_usage("/")
            return {
                "total_gb": round(d.total / (1024**3), 1),
                "free_gb": round(d.free / (1024**3), 1),
                "used_pct": d.percent,
            }
        except Exception:
            return None
    return None


def collect() -> None:
    cpu = _collect_cpu()
    mem = _collect_memory()
    disk = _collect_disk()
    now = time.time()
    with _lock:
        METRICS["timestamp"] = now
        METRICS["uptime"] = round(time.time() - _START_TIME)
        METRICS["cpu"] = cpu
        METRICS["memory"] = mem
        METRICS["disk"] = disk
        METRICS["errors_1m"] = METRICS.get("errors_1m", 0)
        METRICS["ops_1m"] = METRICS.get("ops_1m", 0)

def incr_error() -> None:
    with _lock:
        METRICS["errors_1m"] = METRICS.get("errors_1m", 0) + 1


def incr_op() -> None:
    with _lock:
        METRICS["ops_1m"] = METRICS.get("ops_1m", 0) + 1


def get_metrics() -> Dict[str, Any]:
    with _lock:
        return dict(METRICS)


def start_collector(interval: int = _interval) -> threading.Thread:
    def _loop() -> None:
        while True:
            try:
                collect()
            except Exception as e:
                log.error(f"Metrics collector error: {e}")
            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    log.info(f"Metrics collector started (interval={interval}s)")
    return t
