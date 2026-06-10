import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path

def backup_db(db_path: str, backup_dir: str = None) -> str:
    if not os.path.exists(db_path):
        return ""
    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"ips_backup_{ts}.json"
    dest = os.path.join(backup_dir, name)
    import shutil
    shutil.copy2(db_path, dest)
    return dest

def restore_db(backup_path: str, db_path: str) -> bool:
    if not os.path.exists(backup_path):
        return False
    import shutil
    shutil.copy2(backup_path, db_path)
    return True

def list_backups(backup_dir: str) -> list:
    if not os.path.exists(backup_dir):
        return []
    backups = sorted(Path(backup_dir).glob("ips_backup_*.json"), reverse=True)
    return [str(b) for b in backups]

def start_auto_backup(db_path: str, interval_hours: int = 6):
    def _loop():
        while True:
            try:
                dest = backup_db(db_path)
                if dest:
                    print(f"[Backup] Created: {dest}")
            except Exception as e:
                print(f"[Backup] Error: {e}")
            time.sleep(interval_hours * 3600)
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t
