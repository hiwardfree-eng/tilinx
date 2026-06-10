import os
import time
import threading
from logger import log

METRICS = {}
_lock = threading.Lock()
_interval = 30  # seconds

def _collect_cpu():
    try:
        with open("/proc/stat") as f:
            line = f.readline().strip().split()
        total = sum(int(v) for v in line[1:])
        idle = int(line[4])
        return {"total": total, "idle": idle}
    except:
        return None

def _collect_memory():
    try:
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                k, v = line.split(":")
                mem[k.strip()] = int(v.strip().split()[0])
            return {
                "total_mb": mem.get("MemTotal", 0) // 1024,
                "free_mb": mem.get("MemFree", 0) // 1024,
                "available_mb": mem.get("MemAvailable", 0) // 1024,
            }
    except:
        return None

def _collect_disk():
    try:
        s = os.statvfs("/")
        return {
            "total_gb": (s.f_frsize * s.f_blocks) / (1024**3),
            "free_gb": (s.f_frsize * s.f_bavail) / (1024**3),
            "used_pct": round(100 - (s.f_bavail / s.f_blocks * 100), 1),
        }
    except:
        return None

def _collect_uptime():
    try:
        with open("/proc/uptime") as f:
            return float(f.readline().split()[0])
    except:
        return 0

def collect():
    cpu = _collect_cpu()
    mem = _collect_memory()
    disk = _collect_disk()
    now = time.time()
    with _lock:
        METRICS["timestamp"] = now
        METRICS["uptime"] = _collect_uptime()
        METRICS["cpu"] = cpu
        METRICS["memory"] = mem
        METRICS["disk"] = disk
        METRICS["errors_1m"] = METRICS.get("errors_1m", 0)
        METRICS["ops_1m"] = METRICS.get("ops_1m", 0)

def incr_error():
    with _lock:
        METRICS["errors_1m"] = METRICS.get("errors_1m", 0) + 1

def incr_op():
    with _lock:
        METRICS["ops_1m"] = METRICS.get("ops_1m", 0) + 1

def get_metrics():
    with _lock:
        return dict(METRICS)

def start_collector(interval=_interval):
    def _loop():
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
