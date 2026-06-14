import json, os, time, threading, logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("tilinx.templates")

TEMPLATES_PATH = os.environ.get("TilinX_TEMPLATES_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_templates.json"))
_tlock = threading.Lock()
_t_cache: Dict[str, Any] = {"data": {}, "ts": 0.0}
_t_ttl = 30


def _load() -> Dict[str, Any]:
    now = time.time()
    with _tlock:
        if now - _t_cache["ts"] < _t_ttl:
            return _t_cache["data"]
    if not os.path.exists(TEMPLATES_PATH):
        return {}
    try:
        with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        with _tlock:
            _t_cache["data"] = data
            _t_cache["ts"] = now
        return data
    except Exception as e:
        logger.error(f"Error loading templates: {e}")
        return {}


def _save(data: dict) -> None:
    with _tlock:
        try:
            with open(TEMPLATES_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            _t_cache["data"] = data
            _t_cache["ts"] = time.time()
        except Exception as e:
            logger.error(f"Error saving templates: {e}")


_BUILTIN_TEMPLATES = {
    "gaming_default": {
        "label": "Gaming Default",
        "description": "Configuración estándar para gaming",
        "config": {
            "rate_limit": 30,
            "session_timeout": 1800,
            "max_login_attempts": 5,
            "login_block_minutes": 15,
            "encrypt_db": True,
            "url_blacklist": [],
            "url_whitelist": [],
            "header_rules": [
                {"action": "remove", "header": "X-Forwarded-For", "value": "", "match_url": ""},
                {"action": "set", "header": "X-Proxy-Type", "value": "TilinX", "match_url": ""},
            ],
            "block_proxy_ips": False,
            "block_hosting_ips": False,
        },
    },
    "free_fire_optimized": {
        "label": "Free Fire Optimized",
        "description": "Configuración optimizada para Free Fire",
        "config": {
            "rate_limit": 60,
            "session_timeout": 3600,
            "max_login_attempts": 3,
            "login_block_minutes": 30,
            "encrypt_db": True,
            "url_blacklist": ["anticheat", "CheckHackBehavior", "GetMatchmakingBlacklist"],
            "url_whitelist": ["loginbp.ggpolarbear.com", "clientbp.ggpolarbear.com", "gate.ggpolarbear.com"],
            "header_rules": [
                {"action": "remove", "header": "X-Forwarded-For", "value": "", "match_url": ""},
                {"action": "set", "header": "X-Proxy-Type", "value": "TilinX-FF", "match_url": ""},
            ],
            "block_proxy_ips": True,
            "block_hosting_ips": True,
        },
    },
    "maximum_security": {
        "label": "Maximum Security",
        "description": "Máxima seguridad con restricciones estrictas",
        "config": {
            "rate_limit": 10,
            "session_timeout": 900,
            "max_login_attempts": 3,
            "login_block_minutes": 60,
            "encrypt_db": True,
            "url_blacklist": [],
            "url_whitelist": [],
            "header_rules": [
                {"action": "remove", "header": "X-Forwarded-For", "value": "", "match_url": ""},
                {"action": "remove", "header": "X-Real-IP", "value": "", "match_url": ""},
                {"action": "remove", "header": "Via", "value": "", "match_url": ""},
            ],
            "block_proxy_ips": True,
            "block_hosting_ips": True,
        },
    },
}


def list_templates() -> List[Dict[str, Any]]:
    builtins = [{"id": k, "builtin": True, **v} for k, v in _BUILTIN_TEMPLATES.items()]
    customs = _load()
    custom_list = [{"id": k, "builtin": False, **v} for k, v in customs.items()]
    return builtins + custom_list


def get_template(tid: str) -> Optional[Dict[str, Any]]:
    if tid in _BUILTIN_TEMPLATES:
        return {"id": tid, "builtin": True, **_BUILTIN_TEMPLATES[tid]}
    customs = _load()
    if tid in customs:
        return {"id": tid, "builtin": False, **customs[tid]}
    return None


def apply_template(tid: str, target_config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    tmpl = get_template(tid)
    if not tmpl:
        return None
    cfg = dict(tmpl["config"])
    if target_config:
        cfg.update(target_config)
    return cfg


def save_custom_template(tid: str, label: str, description: str, config: Dict[str, Any]) -> None:
    data = _load()
    data[tid] = {
        "label": label,
        "description": description,
        "config": config,
        "created_at": time.time(),
    }
    _save(data)
    logger.info(f"Custom template saved: {tid}")


def delete_custom_template(tid: str) -> bool:
    data = _load()
    if tid not in data:
        return False
    del data[tid]
    _save(data)
    return True
