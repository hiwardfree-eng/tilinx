"""Safe JSON file read/write with atomic saves and automatic backup recovery."""
import json, os, time, shutil, tempfile, logging
from typing import Any, Dict, TypeVar

T = TypeVar("T")
logger = logging.getLogger("tilinx.file_utils")


def safe_read_json(path: str, default: T) -> T:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning(f"Corrupted JSON at {path}: {e}")
        backup = _find_backup(path)
        if backup:
            logger.info(f"Restoring {path} from backup {backup}")
            try:
                shutil.copy2(backup, path)
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e2:
                logger.error(f"Backup restore failed for {path}: {e2}")
        return default


def safe_write_json(path: str, data: Any, make_backup: bool = True) -> None:
    tmp = None
    try:
        if make_backup and os.path.exists(path):
            _backup_file(path)
        fd, tmp = tempfile.mkstemp(
            suffix=".tmp",
            prefix=os.path.basename(path) + ".",
            dir=os.path.dirname(path) or ".",
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        shutil.move(tmp, path)
        tmp = None
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except Exception:
                pass


def _backup_file(path: str, max_backups: int = 5) -> None:
    backup_dir = os.path.join(os.path.dirname(path) or ".", ".backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.basename(path)
    dst = os.path.join(backup_dir, f"{base}.{ts}.bak")
    try:
        shutil.copy2(path, dst)
    except Exception as e:
        logger.warning(f"Backup failed for {path}: {e}")
        return
    # Prune old backups
    try:
        backups = sorted(
            [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith(base) and f.endswith(".bak")],
            key=os.path.getmtime,
        )
        while len(backups) > max_backups:
            os.unlink(backups.pop(0))
    except Exception:
        pass


def _find_backup(path: str) -> str | None:
    backup_dir = os.path.join(os.path.dirname(path) or ".", ".backups")
    if not os.path.isdir(backup_dir):
        return None
    base = os.path.basename(path)
    backups = sorted(
        [os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith(base) and f.endswith(".bak")],
        key=os.path.getmtime,
        reverse=True,
    )
    return backups[0] if backups else None
