import json, os, time, threading, logging
from typing import Optional, Dict, Any
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger("tilinx.geoip")

_geo_cache: Dict[str, Any] = {}
_geo_lock = threading.Lock()
_geo_ttl = 86400
_GEO_CACHE_MAX = 1000
GEO_API_URL = os.environ.get("TilinX_GEOIP_API", "http://ip-api.com/json/")
_GEO_ENABLED = os.environ.get("TilinX_GEOIP_ENABLED", "0") == "1"


def lookup(ip: str) -> Optional[Dict[str, Any]]:
    if not _GEO_ENABLED:
        return None
    now = time.time()
    with _geo_lock:
        cached = _geo_cache.get(ip)
        if cached and now - cached["ts"] < _geo_ttl:
            return cached["data"]
    try:
        req = Request(f"{GEO_API_URL}{ip}?fields=status,country,countryCode,region,city,isp,proxy,hosting,query", headers={"User-Agent": "TilinX-GeoIP/1.0"})
        resp = urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        if data.get("status") == "success":
            result = {
                "country": data.get("country", ""),
                "country_code": data.get("countryCode", ""),
                "region": data.get("region", ""),
                "city": data.get("city", ""),
                "isp": data.get("isp", ""),
                "proxy": data.get("proxy", False),
                "hosting": data.get("hosting", False),
            }
            with _geo_lock:
                if len(_geo_cache) >= _GEO_CACHE_MAX:
                    _geo_cache.clear()
                _geo_cache[ip] = {"data": result, "ts": now}
            return result
        return None
    except URLError as e:
        logger.warning(f"GeoIP lookup failed for {ip}: {e}")
        return None
    except Exception as e:
        logger.error(f"GeoIP error for {ip}: {e}")
        return None


def is_blocked_country(country_code: str) -> bool:
    from filter_rules import get_geoip_blocked_countries
    return country_code.upper() in get_geoip_blocked_countries()


def is_proxy_or_hosting(ip: str) -> Optional[bool]:
    info = lookup(ip)
    if info:
        return info.get("proxy", False) or info.get("hosting", False)
    return None


def clear_cache() -> None:
    with _geo_lock:
        _geo_cache.clear()


def _geo_cleanup_loop() -> None:
    while True:
        time.sleep(3600)
        now = time.time()
        with _geo_lock:
            for ip in list(_geo_cache.keys()):
                if now - _geo_cache[ip].get("ts", 0) > _geo_ttl:
                    _geo_cache.pop(ip, None)


threading.Thread(target=_geo_cleanup_loop, daemon=True).start()
