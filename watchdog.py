import os, sys, time, json, logging, subprocess, threading, signal
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger("tilinx.watchdog")

MONITOR_INTERVAL = 30
RESTART_DELAY = 3
MAX_RESTART_PER_HOUR = 5
HEARTBEAT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".heartbeat")


class ServiceDef:
    def __init__(self, name: str, cmd: List[str], workdir: str = "",
                 env: Optional[Dict[str, str]] = None, port: int = 0,
                 ready_text: str = "", ready_delay: float = 3.0):
        self.name = name
        self.cmd = cmd
        self.workdir = workdir
        self.env = env or {}
        self.port = port
        self.ready_text = ready_text
        self.ready_delay = ready_delay
        self.process: Optional[subprocess.Popen] = None
        self.restart_count = 0
        self.restart_window_start = 0.0
        self.last_start = 0.0
        self.running = False


class Watchdog:
    def __init__(self):
        self.services: Dict[str, ServiceDef] = {}
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._on_restart: List[Callable[[str], None]] = []

    def register(self, svc: ServiceDef) -> None:
        self.services[svc.name] = svc

    def on_restart(self, cb: Callable[[str], None]) -> None:
        self._on_restart.append(cb)

    def _check_port(self, port: int, timeout: float = 2.0) -> bool:
        import socket
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
            s.close()
            return True
        except (OSError, socket.error):
            return False

    def _start_service(self, svc: ServiceDef) -> bool:
        env = os.environ.copy()
        env.update(svc.env)
        try:
            svc.process = subprocess.Popen(
                svc.cmd, cwd=svc.workdir or None,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=env, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            svc.last_start = time.time()
            svc.running = True
            logger.info(f"[WATCHDOG] Started {svc.name} (PID {svc.process.pid})")
            return True
        except Exception as e:
            logger.error(f"[WATCHDOG] Failed to start {svc.name}: {e}")
            svc.running = False
            return False

    def _check_service(self, svc: ServiceDef) -> bool:
        if svc.process is None:
            return False
        poll = svc.process.poll()
        if poll is not None:
            svc.running = False
            logger.warning(f"[WATCHDOG] {svc.name} exited with code {poll}")
            return False
        if svc.port and not self._check_port(svc.port):
            logger.warning(f"[WATCHDOG] {svc.name} port {svc.port} not listening")
            return False
        return True

    def _restart_service(self, svc: ServiceDef) -> None:
        now = time.time()
        if now - svc.restart_window_start > 3600:
            svc.restart_count = 0
            svc.restart_window_start = now
        svc.restart_count += 1
        if svc.restart_count > MAX_RESTART_PER_HOUR:
            logger.critical(f"[WATCHDOG] {svc.name} exceeded {MAX_RESTART_PER_HOUR} restarts/hour — giving up")
            return
        if svc.process and svc.process.poll() is None:
            try:
                svc.process.terminate()
                svc.process.wait(timeout=5)
            except Exception:
                try:
                    svc.process.kill()
                except Exception:
                    pass
        time.sleep(RESTART_DELAY)
        self._start_service(svc)
        for cb in self._on_restart:
            try:
                cb(svc.name)
            except Exception:
                pass

    def _heartbeat_write(self) -> None:
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(str(time.time()))
        except Exception:
            pass

    def run(self) -> None:
        logger.info("[WATCHDOG] Starting")
        while not self._stop.is_set():
            self._heartbeat_write()
            with self._lock:
                for svc in self.services.values():
                    if not self._check_service(svc):
                        self._restart_service(svc)
            self._stop.wait(MONITOR_INTERVAL)
        logger.info("[WATCHDOG] Stopped")

    def stop(self) -> None:
        self._stop.set()

    def get_status(self) -> Dict[str, Any]:
        status = {}
        with self._lock:
            for name, svc in self.services.items():
                alive = self._check_service(svc)
                status[name] = {
                    "alive": alive,
                    "pid": svc.process.pid if svc.process and svc.process.poll() is None else None,
                    "restarts": svc.restart_count,
                    "uptime": time.time() - svc.last_start if svc.last_start else 0,
                    "running": svc.running,
                }
        return status


_WATCHDOG_INSTANCE: Optional[Watchdog] = None
_WATCHDOG_THREAD: Optional[threading.Thread] = None


def get_watchdog() -> Watchdog:
    global _WATCHDOG_INSTANCE
    if _WATCHDOG_INSTANCE is None:
        _WATCHDOG_INSTANCE = Watchdog()
    return _WATCHDOG_INSTANCE


def start_watchdog() -> Watchdog:
    global _WATCHDOG_THREAD
    wd = get_watchdog()
    if _WATCHDOG_THREAD is None or not _WATCHDOG_THREAD.is_alive():
        _WATCHDOG_THREAD = threading.Thread(target=wd.run, daemon=True)
        _WATCHDOG_THREAD.start()
    return wd


def heartbeat_alive(max_age: float = 90.0) -> bool:
    if not os.path.exists(HEARTBEAT_FILE):
        return False
    try:
        ts = float(open(HEARTBEAT_FILE).read().strip())
        return time.time() - ts < max_age
    except Exception:
        return False
