import json
import os
import time
import threading
import hashlib
import base64
from typing import Optional, Dict, Any, Tuple
from config import DB_PATH, ENCRYPT_DB, SUPABASE_ENABLED
from logger import log
from file_utils import safe_read_json

_lock = threading.Lock()
_CIPHER_KEY: Optional[bytes] = None


def _get_cipher_key() -> bytes:
    global _CIPHER_KEY
    if _CIPHER_KEY is None:
        raw = os.environ.get("TilinX_DB_KEY", "")
        if not raw:
            key_file = os.path.join(os.path.dirname(DB_PATH), ".db_key")
            if os.path.exists(key_file):
                with open(key_file) as f:
                    raw = f.read().strip()
            else:
                import socket
                raw = socket.gethostname() + "-tilinx-db-key"
        _CIPHER_KEY = hashlib.sha256(raw.encode()).digest()[:16]
    return _CIPHER_KEY


def _xor_encrypt(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _encrypt_payload(text: str) -> str:
    if not ENCRYPT_DB:
        return text
    key = _get_cipher_key()
    compressed = text.encode("utf-8")
    encrypted = _xor_encrypt(compressed, key)
    return base64.b64encode(encrypted).decode("ascii")


def _decrypt_payload(payload: str) -> str:
    if not ENCRYPT_DB:
        return payload
    try:
        key = _get_cipher_key()
        encrypted = base64.b64decode(payload.encode("ascii"))
        decrypted = _xor_encrypt(encrypted, key)
        return decrypted.decode("utf-8")
    except Exception as e:
        log.error(f"DB decryption failed: {e}")
        return "{}"


def _integrity(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def load() -> Dict[str, Any]:
    if SUPABASE_ENABLED:
        from .postgres_db import list_ips
        ips = list_ips()
        db = {}
        for ip_info in ips:
            ip = ip_info.pop("ip", "")
            db[ip] = ip_info
        return db
    if not os.path.exists(DB_PATH):
        return {}
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return {}
        if ENCRYPT_DB or (raw and not raw.startswith("{")):
            raw = _decrypt_payload(raw)
        data = json.loads(raw)
        stored_hash = data.pop("_integrity", "")
        if stored_hash and data:
            actual = _integrity(data)
            if stored_hash != actual:
                log.warning("DB integrity check FAILED! Possible tampering.")
                return {}
        return data
    except Exception as e:
        log.error(f"Error loading DB: {e}")
        # Attempt backup recovery
        try:
            recovered = safe_read_json(DB_PATH, {})
            if recovered:
                log.info("DB recovered from backup")
                return recovered
        except Exception:
            pass
        return {}


def save(data: dict) -> None:
    if SUPABASE_ENABLED:
        return
    with _lock:
        _backup()
        try:
            data["_integrity"] = _integrity(data)
            raw = json.dumps(data, indent=4, ensure_ascii=False)
            if ENCRYPT_DB:
                raw = _encrypt_payload(raw)
            from file_utils import safe_write_json
            # Use atomic write via temp file
            import tempfile, shutil
            fd, tmp = tempfile.mkstemp(suffix=".tmp", prefix="ips.json.", dir=os.path.dirname(DB_PATH) or ".")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            shutil.move(tmp, DB_PATH)
            data.pop("_integrity", None)
        except Exception as e:
            log.error(f"Error saving DB: {e}")


def _backup() -> None:
    if not os.path.exists(DB_PATH):
        return
    size = os.path.getsize(DB_PATH)
    if size < 100:
        return
    backup_path = DB_PATH + ".bak"
    try:
        import shutil
        shutil.copy2(DB_PATH, backup_path)
    except Exception:
        pass


def get_stats(db: dict) -> Tuple[int, int, int, int]:
    if SUPABASE_ENABLED:
        from .postgres_db import get_stats as pg_stats
        stats = pg_stats()
        if not stats.get("enabled"):
            return 0, 0, 0, 0
        ips_by_status = stats.get("ips", {})
        total = sum(ips_by_status.values())
        active = ips_by_status.get("active", 0)
        blocked = ips_by_status.get("blocked", 0)
        expired = ips_by_status.get("expired", 0)
        return total, active, expired, blocked
    now = time.time()
    total = len(db)
    active = 0
    expired = 0
    for u in db.values():
        if u.get("status") != "active":
            continue
        exp = u.get("expires_at", 0) or 0
        if exp == 0 or exp > now:
            active += 1
        else:
            expired += 1
    blocked = sum(1 for u in db.values() if u.get("status") == "blocked")
    return total, active, expired, blocked


def get_user_status_label(user: dict) -> str:
    now = time.time()
    status = user.get("status", "")
    if status == "blocked":
        return "Banned"
    if status == "active":
        exp = user.get("expires_at", 0) or 0
        if exp == 0:
            return "Active (Permanent)"
        if exp > now:
            rem = exp - now
            return f"Active ({int(rem // 86400)}d {int((rem % 86400) // 3600)}h left)"
        return "Expired"
    return "Not Registered"


def get_auth_status(ip: str) -> str:
    if SUPABASE_ENABLED:
        from .postgres_db import get_ip
        user = get_ip(ip)
        if not user:
            return "NOT_FOUND"
        status = user.get("status", "")
        if status == "blocked":
            return "BANNED"
        if status == "active":
            exp = user.get("expires_at", 0) or 0
            if exp == 0 or exp > time.time():
                return "ACTIVE"
            return "EXPIRED"
        return "NOT_FOUND"
    db = load()
    if ip not in db:
        return "NOT_FOUND"
    user = db[ip]
    status = user.get("status", "")
    if status == "blocked":
        return "BANNED"
    if status == "active":
        exp = user.get("expires_at", 0) or 0
        if exp == 0 or exp > time.time():
            return "ACTIVE"
        return "EXPIRED"
    return "NOT_FOUND"
