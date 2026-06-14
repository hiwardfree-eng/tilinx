import os, json, time, base64, threading, logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("tilinx.2fa")

try:
    import pyotp
except ImportError:
    pyotp = None

try:
    import qrcode
    from io import BytesIO
    import base64 as b64mod
except ImportError:
    qrcode = None

TFA_PATH = os.environ.get("TilinX_TFA_STORAGE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tfa_config.json"))
ISSUER = "TilinX"
_tfa_lock = threading.Lock()


def _load() -> Dict[str, Any]:
    if not os.path.exists(TFA_PATH):
        return {"users": {}}
    try:
        with open(TFA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}}


def _save(data: dict) -> None:
    with _tfa_lock:
        try:
            with open(TFA_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"2FA save error: {e}")


def is_available() -> bool:
    return pyotp is not None


def setup(username: str) -> Optional[Dict[str, Any]]:
    if not pyotp:
        return None
    secret = pyotp.random_base32()
    data = _load()
    data["users"][username] = {
        "secret": secret,
        "enabled": True,
        "setup_at": time.time(),
        "backup_codes": _generate_backup_codes(),
    }
    _save(data)
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)
    qr_b64 = _generate_qr(uri) if qrcode else None
    return {
        "secret": secret,
        "uri": uri,
        "qr_base64": qr_b64,
        "backup_codes": data["users"][username]["backup_codes"],
    }


def _generate_backup_codes(count: int = 8) -> List[str]:
    import secrets
    codes = []
    for _ in range(count):
        codes.append(secrets.token_hex(4).upper())
    return codes


def _generate_qr(uri: str) -> Optional[str]:
    try:
        if not qrcode:
            return None
        img = qrcode.make(uri, box_size=6, border=2)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return b64mod.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.warning(f"QR generation failed: {e}")
        return None


def verify(username: str, code: str) -> bool:
    if not pyotp:
        return False
    data = _load()
    user = data.get("users", {}).get(username)
    if not user or not user.get("enabled"):
        return False
    secret = user.get("secret", "")
    if not secret:
        return False
    totp = pyotp.TOTP(secret)
    if totp.verify(code, valid_window=1):
        return True
    backup = user.get("backup_codes", [])
    if code in backup:
        user["backup_codes"] = [c for c in backup if c != code]
        _save(data)
        return True
    return False


def is_enabled(username: str) -> bool:
    if not pyotp:
        return False
    data = _load()
    user = data.get("users", {}).get(username)
    return user is not None and user.get("enabled", False)


def disable(username: str) -> bool:
    data = _load()
    if username not in data.get("users", {}):
        return False
    data["users"][username]["enabled"] = False
    _save(data)
    return True


def enable(username: str) -> bool:
    data = _load()
    if username not in data.get("users", {}):
        return False
    data["users"][username]["enabled"] = True
    _save(data)
    return True


def get_status(username: str) -> Dict[str, Any]:
    data = _load()
    user = data.get("users", {}).get(username)
    return {
        "enabled": user is not None and user.get("enabled", False),
        "setup_at": user.get("setup_at", 0) if user else 0,
        "has_backup_codes": bool(user and user.get("backup_codes")),
    }
