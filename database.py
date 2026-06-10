import json
import os
import time
import threading
import hashlib
import base64
from config import DB_PATH, ENCRYPT_DB
from logger import log

_lock = threading.Lock()
_CIPHER_KEY = None

def _get_cipher_key():
    global _CIPHER_KEY
    if _CIPHER_KEY is None:
        raw = os.environ.get("TilinX_DB_KEY", "TilinX_S3cur3_D4t4b4s3_K3y_2026!")
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

def load() -> dict:
    if not os.path.exists(DB_PATH):
        return {}
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return {}
        # Auto-detect encrypted vs plain JSON
        if ENCRYPT_DB or (raw and not raw.startswith("{")):
            raw = _decrypt_payload(raw)
        data = json.loads(raw)
        stored_hash = data.pop("_integrity", "")
        if stored_hash and data:
            actual = _integrity(data)
            if stored_hash != actual:
                log.warning(f"DB integrity check FAILED! Possible tampering.")
                return {}
        return data
    except Exception as e:
        log.error(f"Error loading DB: {e}")
        return {}

def save(data: dict):
    with _lock:
        _backup()
        try:
            data["_integrity"] = _integrity(data)
            raw = json.dumps(data, indent=4, ensure_ascii=False)
            if ENCRYPT_DB:
                raw = _encrypt_payload(raw)
            with open(DB_PATH, "w", encoding="utf-8") as f:
                f.write(raw)
            data.pop("_integrity", None)
        except Exception as e:
            log.error(f"Error saving DB: {e}")

def _backup():
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

def get_stats(db: dict) -> tuple:
    now = time.time()
    total = len(db)
    active = sum(1 for u in db.values() if u.get("status") == "active" and u.get("expires_at", 0) > now)
    expired = sum(1 for u in db.values() if u.get("status") == "active" and u.get("expires_at", 0) <= now)
    blocked = sum(1 for u in db.values() if u.get("status") == "blocked")
    return total, active, expired, blocked

def get_user_status_label(user: dict) -> str:
    now = time.time()
    status = user.get("status", "")
    if status == "blocked":
        return "Banned"
    if status == "active":
        if user.get("expires_at", 0) > now:
            rem = user["expires_at"] - now
            return f"Active ({int(rem // 86400)}d {int((rem % 86400) // 3600)}h left)"
        return "Expired"
    return "Not Registered"

def get_auth_status(ip: str) -> str:
    db = load()
    if ip not in db:
        return "NOT_FOUND"
    user = db[ip]
    status = user.get("status", "")
    if status == "blocked":
        return "BANNED"
    if status == "active":
        return "ACTIVE" if user.get("expires_at", 0) > time.time() else "EXPIRED"
    return "NOT_FOUND"
