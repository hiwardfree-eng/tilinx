import json, os, time, threading, re, logging
from typing import Dict, Any, List, Optional, Tuple
from file_utils import safe_read_json, safe_write_json

logger = logging.getLogger("tilinx.filters")

FILTERS_PATH = os.environ.get("TilinX_FILTERS_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "filters.json"))
_flock = threading.Lock()
_f_cache: Dict[str, Any] = {"data": None, "ts": 0.0}
_f_ttl = 60


def _load() -> Dict[str, Any]:
    with _flock:
        if _f_cache["data"] is not None and time.time() - _f_cache["ts"] < _f_ttl:
            return _f_cache["data"]
    if not os.path.exists(FILTERS_PATH):
        default = {
            "url_blacklist": [],
            "url_whitelist": [],
            "header_rules": [],
            "geoip_blocked_countries": [],
            "enabled": True,
        }
        _save(default)
        return default
    data = safe_read_json(FILTERS_PATH, {})
    with _flock:
        _f_cache["data"] = data
        _f_cache["ts"] = time.time()
    return data


def _save(data: dict) -> None:
    safe_write_json(FILTERS_PATH, data)
    with _flock:
        _f_cache["data"] = data
        _f_cache["ts"] = time.time()


def add_url_blacklist(pattern: str) -> None:
    data = _load()
    if pattern not in data.get("url_blacklist", []):
        data.setdefault("url_blacklist", []).append(pattern)
        _save(data)
        logger.info(f"URL blacklist added: {pattern}")


def remove_url_blacklist(pattern: str) -> bool:
    data = _load()
    if pattern in data.get("url_blacklist", []):
        data["url_blacklist"] = [p for p in data["url_blacklist"] if p != pattern]
        _save(data)
        return True
    return False


def add_url_whitelist(pattern: str) -> None:
    data = _load()
    if pattern not in data.get("url_whitelist", []):
        data.setdefault("url_whitelist", []).append(pattern)
        _save(data)
        logger.info(f"URL whitelist added: {pattern}")


def remove_url_whitelist(pattern: str) -> bool:
    data = _load()
    if pattern in data.get("url_whitelist", []):
        data["url_whitelist"] = [p for p in data["url_whitelist"] if p != pattern]
        _save(data)
        return True
    return False


def check_url_blocked(url: str) -> Tuple[bool, str]:
    data = _load()
    if not data.get("enabled", True):
        return False, ""
    url_lower = url.lower()
    for pattern in data.get("url_blacklist", []):
        if pattern.lower() in url_lower:
            return True, f"blacklisted: {pattern}"
    for pattern in data.get("url_whitelist", []):
        if pattern.lower() in url_lower:
            return False, ""
    return False, ""


def add_header_rule(action: str, header: str, value: str = "", match_url: str = "") -> None:
    data = _load()
    rule = {"action": action, "header": header, "value": value, "match_url": match_url}
    data.setdefault("header_rules", []).append(rule)
    _save(data)
    logger.info(f"Header rule added: {action} {header}")


def remove_header_rule(index: int) -> bool:
    data = _load()
    rules = data.get("header_rules", [])
    if 0 <= index < len(rules):
        del rules[index]
        _save(data)
        return True
    return False


def apply_header_rules(url: str, headers: Dict[str, str]) -> Dict[str, str]:
    data = _load()
    if not data.get("enabled", True):
        return headers
    url_lower = url.lower()
    out = dict(headers)
    for rule in data.get("header_rules", []):
        match_url = rule.get("match_url", "")
        if match_url and match_url.lower() not in url_lower:
            continue
        action = rule.get("action", "")
        hdr = rule.get("header", "")
        val = rule.get("value", "")
        if action == "set":
            out[hdr] = val
        elif action == "remove":
            out.pop(hdr, None)
        elif action == "add":
            out[hdr] = out.get(hdr, "") + val
    return out


def add_geoip_blocked_country(country_code: str) -> None:
    data = _load()
    code = country_code.upper()
    if code not in data.get("geoip_blocked_countries", []):
        data.setdefault("geoip_blocked_countries", []).append(code)
        _save(data)
        logger.info(f"GeoIP blocked country added: {code}")


def remove_geoip_blocked_country(country_code: str) -> bool:
    data = _load()
    code = country_code.upper()
    if code in data.get("geoip_blocked_countries", []):
        data["geoip_blocked_countries"] = [c for c in data["geoip_blocked_countries"] if c != code]
        _save(data)
        return True
    return False


def get_geoip_blocked_countries() -> List[str]:
    data = _load()
    return data.get("geoip_blocked_countries", [])


def get_rules() -> Dict[str, Any]:
    return _load()
