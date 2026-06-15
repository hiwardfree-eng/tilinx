import os, time, json, threading, logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("tilinx.jwt")

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None

TOKENS_PATH = os.environ.get("TilinX_JWT_STORAGE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "jwt_tokens.json"))
JWT_SECRET = os.environ.get("TilinX_JWT_SECRET", "")
if not JWT_SECRET:
    import secrets
    JWT_SECRET = secrets.token_hex(32)
    logger.warning("TilinX_JWT_SECRET not set, using random secret (tokens invalidated on restart)")

JWT_ALGORITHM = "HS256"
JWT_ACCESS_TTL = int(os.environ.get("TilinX_JWT_ACCESS_TTL", "3600"))
JWT_REFRESH_TTL = int(os.environ.get("TilinX_JWT_REFRESH_TTL", "86400"))
_tlock = threading.Lock()

SCOPE_ADMIN = "admin"
SCOPE_API = "api"
SCOPE_MONITOR = "monitor"
SCOPE_READONLY = "readonly"


def _load_tokens() -> Dict[str, Any]:
    try:
        from file_utils import safe_read_json
        return safe_read_json(TOKENS_PATH, {"refresh_tokens": {}, "revoked": []})
    except Exception:
        return {"refresh_tokens": {}, "revoked": []}


def _save_tokens(data: dict) -> None:
    with _tlock:
        try:
            from file_utils import safe_write_json
            safe_write_json(TOKENS_PATH, data)
        except Exception as e:
            logger.error(f"JWT token storage error: {e}")


def create_access_token(subject: str, scopes: Optional[List[str]] = None, metadata: Optional[Dict] = None) -> Optional[str]:
    if not pyjwt:
        logger.error("PyJWT not installed: pip install pyjwt")
        return None
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + JWT_ACCESS_TTL,
        "type": "access",
        "scopes": scopes or [SCOPE_API],
        "jti": os.urandom(16).hex(),
    }
    if metadata:
        payload["meta"] = metadata
    try:
        return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    except Exception as e:
        logger.error(f"JWT encode error: {e}")
        return None


def create_refresh_token(subject: str, scopes: Optional[List[str]] = None) -> Optional[str]:
    if not pyjwt:
        return None
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + JWT_REFRESH_TTL,
        "type": "refresh",
        "jti": os.urandom(16).hex(),
    }
    try:
        token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        data = _load_tokens()
        data["refresh_tokens"][payload["jti"]] = {
            "subject": subject,
            "scopes": scopes or [SCOPE_API],
            "created": now,
            "expires": now + JWT_REFRESH_TTL,
        }
        _save_tokens(data)
        return token
    except Exception as e:
        logger.error(f"JWT refresh encode error: {e}")
        return None


def verify_token(token: str, required_scopes: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    if not pyjwt:
        return None
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") not in ("access", "refresh"):
            return None
        data = _load_tokens()
        if payload.get("jti") in data.get("revoked", []):
            logger.warning(f"Revoked token used: {payload.get('jti', '?')}")
            return None
        if required_scopes:
            token_scopes = payload.get("scopes", [])
            if not all(s in token_scopes for s in required_scopes):
                logger.warning(f"Token missing scopes: need {required_scopes}, have {token_scopes}")
                return None
        return payload
    except pyjwt.ExpiredSignatureError:
        return None
    except Exception as e:
        logger.error(f"JWT verify error: {e}")
        return None


def refresh_access_token(refresh_token: str) -> Optional[Dict[str, str]]:
    payload = verify_token(refresh_token)
    if not payload:
        return None
    if payload.get("type") != "refresh":
        return None
    new_access = create_access_token(payload["sub"], payload.get("scopes"))
    if not new_access:
        return None
    return {"access_token": new_access, "token_type": "Bearer", "expires_in": JWT_ACCESS_TTL}


def revoke_token(jti: str) -> bool:
    data = _load_tokens()
    if jti not in data.get("revoked", []):
        data.setdefault("revoked", []).append(jti)
        _save_tokens(data)
        return True
    return False


def revoke_all_for_user(subject: str) -> int:
    data = _load_tokens()
    count = 0
    for jti, info in list(data.get("refresh_tokens", {}).items()):
        if info.get("subject") == subject:
            if jti not in data.get("revoked", []):
                data.setdefault("revoked", []).append(jti)
                count += 1
    _save_tokens(data)
    return count


def create_token_pair(subject: str, scopes: Optional[List[str]] = None, metadata: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
    access = create_access_token(subject, scopes, metadata)
    refresh = create_refresh_token(subject, scopes)
    if not access or not refresh:
        return None
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": JWT_ACCESS_TTL,
        "scope": " ".join(scopes or [SCOPE_API]),
    }


def list_active_refresh_tokens(subject: Optional[str] = None) -> List[Dict[str, Any]]:
    data = _load_tokens()
    tokens = []
    for jti, info in data.get("refresh_tokens", {}).items():
        if subject and info.get("subject") != subject:
            continue
        if jti in data.get("revoked", []):
            continue
        if info.get("expires", 0) < time.time():
            continue
        tokens.append({"jti": jti, **info})
    return tokens


def token_required(scopes: Optional[List[str]] = None):
    from flask import request, jsonify
    def decorator(f):
        def wrapper(*args, **kwargs):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return jsonify(error="Missing or invalid Authorization header"), 401
            token = auth[7:]
            payload = verify_token(token, scopes)
            if not payload:
                return jsonify(error="Invalid or expired token"), 401
            request.jwt_payload = payload
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator
