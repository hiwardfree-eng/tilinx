import os, time, threading, logging
from typing import Dict, Any, List, Optional, Callable
from file_utils import safe_read_json, safe_write_json

logger = logging.getLogger("tilinx.scheduler")

SCHED_PATH = os.environ.get("TilinX_SCHED_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduled_tasks.json"))
_slock = threading.Lock()
_sched_cache: Dict[str, Any] = {"data": {}, "ts": 0.0}
_sched_ttl = 30
_threads: List[threading.Thread] = []
_running = False

TASK_CLEANUP_EXPIRED = "cleanup_expired"
TASK_REPORT = "generate_report"
TASK_BACKUP = "create_backup"
TASK_HEALTH_CHECK = "health_check"


def _load() -> Dict[str, Any]:
    now = time.time()
    with _slock:
        if now - _sched_cache["ts"] < _sched_ttl:
            return _sched_cache["data"]
    data = safe_read_json(SCHED_PATH, {})
    with _slock:
        _sched_cache["data"] = data
        _sched_cache["ts"] = now
    return data


def _save(data: dict) -> None:
    with _slock:
        safe_write_json(SCHED_PATH, data)
        _sched_cache["data"] = data
        _sched_cache["ts"] = time.time()


def register_task(task_type: str, interval_seconds: int, config: Optional[Dict[str, Any]] = None) -> str:
    data = _load()
    tid = f"task_{int(time.time())}_{hash(task_type) % 10000}"
    data[tid] = {
        "type": task_type,
        "interval": interval_seconds,
        "config": config or {},
        "created_at": time.time(),
        "last_run": 0,
        "enabled": True,
    }
    _save(data)
    logger.info(f"Task registered: {tid} ({task_type} every {interval_seconds}s)")
    return tid


def remove_task(tid: str) -> bool:
    data = _load()
    if tid not in data:
        return False
    del data[tid]
    _save(data)
    return True


def list_tasks() -> List[Dict[str, Any]]:
    data = _load()
    return [{"id": k, **v} for k, v in sorted(data.items(), key=lambda x: x[1].get("created_at", 0))]


def _run_cleanup_expired() -> None:
    from database import load, save
    from keys import list_keys
    now = time.time()
    db = load()
    changed = False
    for ip, info in list(db.items()):
        if ip == "_integrity":
            continue
        exp = info.get("expires_at", 0) or 0
        if exp > 0 and exp <= now and info.get("status") == "active":
            db[ip]["status"] = "expired"
            changed = True
            logger.info(f"Cleanup: expired IP {ip}")
    if changed:
        save(db)
    keys = list_keys()
    for k in keys:
        exp = k.get("created_at", 0) + k.get("duration", 0)
        if exp <= now and k.get("used") and not k.get("active_ips"):
            logger.info(f"Cleanup: expired unused key {k['code']}")


def _run_health_check() -> None:
    from monitor import get_metrics
    try:
        metrics = get_metrics()
        cpu = metrics.get("cpu", "?")
        mem = metrics.get("memory", {})
        ram = mem.get("percent", "?") if isinstance(mem, dict) else "?"
        logger.info(f"Health check: CPU={cpu}% RAM={ram}%")
    except Exception as e:
        logger.error(f"Health check failed: {e}")


_HANDLERS: Dict[str, Callable] = {
    TASK_CLEANUP_EXPIRED: _run_cleanup_expired,
    TASK_REPORT: lambda: logger.info("Report generation triggered"),
    TASK_BACKUP: lambda: logger.info("Backup triggered"),
    TASK_HEALTH_CHECK: _run_health_check,
}


def _run_task(tid: str, task: Dict[str, Any]) -> None:
    handler = _HANDLERS.get(task["type"])
    if handler:
        try:
            handler()
            data = _load()
            if tid in data:
                data[tid]["last_run"] = time.time()
                _save(data)
        except Exception as e:
            logger.error(f"Task {tid} ({task['type']}) failed: {e}")
    else:
        logger.warning(f"No handler for task type: {task['type']}")


def _scheduler_loop() -> None:
    global _running
    _running = True
    while _running:
        try:
            data = _load()
            now = time.time()
            for tid, task in data.items():
                if not task.get("enabled", True):
                    continue
                interval = task.get("interval", 3600)
                last_run = task.get("last_run", 0)
                if now - last_run >= interval:
                    t = threading.Thread(target=_run_task, args=(tid, task), daemon=True)
                    t.start()
            time.sleep(30)
        except Exception as e:
            logger.error(f"Scheduler loop error: {e}")
            time.sleep(60)


def start_scheduler() -> None:
    global _running
    if _running:
        return
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()
    _threads.append(t)
    logger.info("Scheduler started")


def stop_scheduler() -> None:
    global _running
    _running = False
    logger.info("Scheduler stopped")


def is_scheduler_running() -> bool:
    return _running
