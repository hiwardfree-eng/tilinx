import re, os, time, logging
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import unquote
from file_utils import safe_read_json, safe_write_json

logger = logging.getLogger("tilinx.waf")

WAF_PATH = os.environ.get("TilinX_WAF_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "waf_rules.json"))

SQLI_PATTERNS = [
    re.compile(r"(?i)(\bselect\b.{0,40}\bfrom\b)", re.DOTALL),
    re.compile(r"(?i)(\bunion\b.{0,40}\bselect\b)", re.DOTALL),
    re.compile(r"(?i)(\binsert\s+into\b)"),
    re.compile(r"(?i)(\bdelete\s+from\b)"),
    re.compile(r"(?i)(\bdrop\s+table\b)"),
    re.compile(r"(?i)(\bexec\b.*\()"),
    re.compile(r"(?i)(\bxp_cmdshell\b)"),
    re.compile(r"(?i)('.{0,10}--)"),
    re.compile(r"(?i)'.{0,10}--\s"),
    re.compile(r"(?i)('|%27)\s*(or|and|union|select|exec|drop|insert|delete)\s"),
    re.compile(r"(?i)\b(or|and)\s+\d+\s*=\s*\d+\b"),
    re.compile(r"(?i)(\binto\s+(out|dump)file\b)"),
    re.compile(r"(?i)(\bload_file\s*\()"),
    re.compile(r"(?i)(\binformation_schema\b)"),
    re.compile(r"(?i)(\bchar\s*\()"),
    re.compile(r"(?i)(\bwaitfor\s+delay\b)"),
    re.compile(r"(?i)(\bbenchmark\s*\()"),
    re.compile(r"(?i)(0x[0-9a-f]{8,})"),
    re.compile(r"(?i)((?:%23|#).*\s*(?:select|union|insert|delete|drop|update)\s)"),
    re.compile(r"(?i)(\b(?:admin|root)\s*['\"]\s*--\s*)"),
]

XSS_PATTERNS = [
    re.compile(r"(?i)<script[^>]*>"),
    re.compile(r"(?i)<[^>]*\bonerror\s*="),
    re.compile(r"(?i)<[^>]*\bonload\s*="),
    re.compile(r"(?i)<[^>]*\bonclick\s*="),
    re.compile(r"(?i)<[^>]*\bonmouseover\s*="),
    re.compile(r"(?i)<[^>]*\bonfocus\s*="),
    re.compile(r"(?i)<[^>]*\bonblur\s*="),
    re.compile(r"(?i)<[^>]*\bonsubmit\s*="),
    re.compile(r"(?i)<[^>]*\bonchange\s*="),
    re.compile(r"(?i)<[^>]*\bonkeypress\s*="),
    re.compile(r"(?i)<[^>]*\bonkeydown\s*="),
    re.compile(r"(?i)<[^>]*\bonkeyup\s*="),
    re.compile(r"(?i)<[^>]*\bondblclick\s*="),
    re.compile(r"(?i)<[^>]*\bonmouseenter\s*="),
    re.compile(r"(?i)javascript\s*:"),
    re.compile(r"(?i)<iframe[^>]*>"),
    re.compile(r"(?i)<embed[^>]*>"),
    re.compile(r"(?i)<object[^>]*>"),
    re.compile(r"(?i)<svg[^>]*>"),
    re.compile(r"(?i)expression\s*\(.*\)"),
    re.compile(r"(?i)alert\s*\(.*\)"),
    re.compile(r"(?i)prompt\s*\(.*\)"),
    re.compile(r"(?i)confirm\s*\(.*\)"),
    re.compile(r"(?i)document\.cookie"),
    re.compile(r"(?i)window\.location"),
    re.compile(r"(?i)eval\s*\("),
    re.compile(r"(?i)fromCharCode"),
    re.compile(r"(?i)\$\{.*\}"),
]

PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"(\.\.\\/)"),
    re.compile(r"(\.\.\/)"),
    re.compile(r"(%2e%2e%2f)"),
    re.compile(r"(%2e%2e\/)"),
    re.compile(r"(%2e%2e%5c)"),
    re.compile(r"(%252e%252e%252f)"),
    re.compile(r"(/etc/passwd)"),
    re.compile(r"(/etc/shadow)"),
    re.compile(r"(/etc/hosts)"),
    re.compile(r"(/proc/self/)"),
    re.compile(r"(/var/log/)"),
    re.compile(r"(/boot/)"),
    re.compile(r"(/windows/system32)"),
    re.compile(r"(/winnt/)"),
    re.compile(r"(boot\.ini)"),
    re.compile(r"(~root)"),
]

CMD_INJECTION_PATTERNS = [
    re.compile(r"(?i)(\||;)\s*(ping|nslookup|tracert|curl|wget|nc|bash|cmd|powershell|sh|python|perl|ruby)"),
    re.compile(r"(?i)(`.*`)"),
    re.compile(r"(?i)(\$\(.*\))"),
    re.compile(r"(?i)(\|\||&&)"),
    re.compile(r"(?i)(;.*;)"),
]

LOG_INJECTION_PATTERNS = [
    re.compile(r"(?i)\r?\n"),
    re.compile(r"%0[dd]|%0[aa]"),
]

SCANNER_AGENTS = [
    "nmap", "masscan", "zgrab", "gobuster", "dirbuster", "nikto",
    "sqlmap", "openvas", "nessus", "burpsuite", "acunetix",
    "netsparker", "awvs", "appscan", "w3af", "arachni",
    "crawl", "spider", "scrapy", "wpscan", "joomscan",
]

_RULES_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_SAFE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".css", ".js", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".webm", ".pdf")
_HIT_COUNTER: Dict[str, int] = {}
_HIT_WINDOW = 60.0
_HIT_CLEANUP_TS = 0.0
_HIT_THRESHOLD = 30


def _load_rules() -> Dict[str, Any]:
    now = time.time()
    if now - _RULES_CACHE["ts"] < 30 and _RULES_CACHE["data"] is not None:
        return _RULES_CACHE["data"]
    data = safe_read_json(WAF_PATH, {"enabled": True, "block_threshold": 6, "mode": "block"})
    _RULES_CACHE["data"] = data
    _RULES_CACHE["ts"] = now
    return data


def _save_rules(data: dict) -> None:
    safe_write_json(WAF_PATH, data)


class WAFResult:
    def __init__(self):
        self.blocked = False
        self.reasons: List[str] = []
        self.score = 0.0
        self.severity: str = "info"

    def add(self, reason: str, score: float = 1.0):
        self.reasons.append(reason)
        self.score += score
        if self.score >= 10:
            self.severity = "critical"
        elif self.score >= 5:
            self.severity = "high"
        elif self.score >= 2:
            self.severity = "medium"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blocked": self.blocked,
            "reasons": self.reasons,
            "score": self.score,
            "severity": self.severity,
        }


def _normalize_text(text: str) -> str:
    decoded = unquote(text) if isinstance(text, str) else text
    if "%25" in decoded:
        decoded = unquote(decoded)
    return decoded


def _check_hit_rate(ip: str) -> Optional[str]:
    global _HIT_CLEANUP_TS
    now = time.time()
    if now - _HIT_CLEANUP_TS > 60:
        _HIT_COUNTER.clear()
        _HIT_CLEANUP_TS = now
    count = _HIT_COUNTER.get(ip, 0) + 1
    _HIT_COUNTER[ip] = count
    if count > _HIT_THRESHOLD:
        return f"High hit rate ({count}/{_HIT_WINDOW}s)"
    return None


def _scan_text(text: str, categories: List[str]) -> WAFResult:
    result = WAFResult()
    if "sqli" in categories:
        for i, pat in enumerate(SQLI_PATTERNS):
            m = pat.search(text)
            if m:
                result.add(f"SQLi #{i + 1}: {m.group(0)[:40]}", 3.0)
    if "xss" in categories:
        for i, pat in enumerate(XSS_PATTERNS):
            m = pat.search(text)
            if m:
                result.add(f"XSS #{i + 1}: {m.group(0)[:40]}", 2.0)
    if "path_traversal" in categories:
        for i, pat in enumerate(PATH_TRAVERSAL_PATTERNS):
            m = pat.search(text)
            if m:
                result.add(f"PT #{i + 1}: {m.group(0)[:40]}", 3.0)
    if "cmd_injection" in categories:
        for i, pat in enumerate(CMD_INJECTION_PATTERNS):
            m = pat.search(text)
            if m:
                result.add(f"CMD #{i + 1}: {m.group(0)[:40]}", 4.0)
    if "log_injection" in categories:
        for i, pat in enumerate(LOG_INJECTION_PATTERNS):
            m = pat.search(text)
            if m:
                result.add(f"LOG #{i + 1}: {m.group(0)[:40]}", 1.0)
    config = _load_rules()
    if result.score >= config.get("block_threshold", 6):
        result.blocked = True
    return result


def check_request(method: str, path: str, headers: Dict[str, str], body: str = "", src_ip: str = "") -> WAFResult:
    config = _load_rules()
    if not config.get("enabled", True):
        return WAFResult()

    if path.lower().endswith(_SAFE_EXTENSIONS) and method == "GET":
        return WAFResult()

    if src_ip and _check_hit_rate(src_ip):
        result = WAFResult()
        result.add(f"Rate exceeded for {src_ip}", 6.0)
        if result.score >= config.get("block_threshold", 6):
            result.blocked = True
        return result

    categories = ["sqli", "xss", "path_traversal", "cmd_injection", "log_injection"]
    decoded = _normalize_text(path)
    all_text = f"{decoded} {body}" if body else decoded

    result = _scan_text(all_text, categories)

    ua = headers.get("user-agent", "").lower()
    for agent in SCANNER_AGENTS:
        if agent in ua:
            result.add(f"Scanner: {agent}", 5.0)

    if not result.blocked and headers:
        hdr_text = _normalize_text(json.dumps(dict(headers)))
        hdr_result = _scan_text(hdr_text, categories)
        result.score += hdr_result.score
        result.reasons.extend(hdr_result.reasons)
        if result.score >= config.get("block_threshold", 6):
            result.blocked = True

    if result.score > 0:
        mode = config.get("mode", "block")
        if mode == "block":
            result.blocked = True
        prefix = "WAF BLOCK" if result.blocked else "WAF WARN"
        logger.warning(f"{prefix}: {method} {path[:80]} score={result.score} sev={result.severity} {result.reasons}")

    return result


def get_stats() -> Dict[str, Any]:
    return {"rules_count": {
        "sqli": len(SQLI_PATTERNS), "xss": len(XSS_PATTERNS),
        "path_traversal": len(PATH_TRAVERSAL_PATTERNS),
        "cmd_injection": len(CMD_INJECTION_PATTERNS),
        "log_injection": len(LOG_INJECTION_PATTERNS),
        "scanner_agents": len(SCANNER_AGENTS),
    }}


def set_mode(mode: str) -> None:
    if mode in ("log", "block", "off"):
        data = _load_rules()
        data["mode"] = mode
        data["enabled"] = mode != "off"
        _save_rules(data)


def set_threshold(threshold: int) -> None:
    data = _load_rules()
    data["block_threshold"] = max(1, min(100, threshold))
    _save_rules(data)
