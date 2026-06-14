import re, os, json, time, logging
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import unquote, urlparse, parse_qs

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
    re.compile(r"(?i)('.{0,10}--\s)"),
    re.compile(r"(?i)('|%27)\s*(or|and|union|select|exec|drop|insert|delete)\s"),
    re.compile(r"(?i)\b(or|and)\s+\d+\s*=\s*\d+\b"),
    re.compile(r"(?i)(\binto\s+(out|dump)file\b)"),
    re.compile(r"(?i)(\bload_file\s*\()"),
    re.compile(r"(?i)(\binformation_schema\b)"),
    re.compile(r"(?i)(\bchar\s*\()"),
    re.compile(r"(?i)(\bwaitfor\s+delay\b)"),
    re.compile(r"(?i)(\bbenchmark\s*\()"),
]

XSS_PATTERNS = [
    re.compile(r"(?i)(<script[^>]*>)"),
    re.compile(r"(?i)(<[^>]*\bonerror\s*=)"),
    re.compile(r"(?i)(<[^>]*\bonload\s*=)"),
    re.compile(r"(?i)(<[^>]*\bonclick\s*=)"),
    re.compile(r"(?i)(<[^>]*\bonmouseover\s*=)"),
    re.compile(r"(?i)(<[^>]*\bonfocus\s*=)"),
    re.compile(r"(?i)(<[^>]*\bonblur\s*=)"),
    re.compile(r"(?i)(<[^>]*\bonsubmit\s*=)"),
    re.compile(r"(?i)(<[^>]*\bonchange\s*=)"),
    re.compile(r"(?i)(javascript\s*:)"),
    re.compile(r"(?i)(<iframe[^>]*>)"),
    re.compile(r"(?i)(<embed[^>]*>)"),
    re.compile(r"(?i)(<object[^>]*>)"),
    re.compile(r"(?i)(expression\s*\(.*\))"),
    re.compile(r"(?i)(alert\s*\(.*\))"),
    re.compile(r"(?i)(prompt\s*\(.*\))"),
    re.compile(r"(?i)(confirm\s*\(.*\))"),
    re.compile(r"(?i)(document\.cookie)"),
    re.compile(r"(?i)(window\.location)"),
    re.compile(r"(?i)(eval\s*\()"),
    re.compile(r"(?i)(fromCharCode)"),
]

PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"(\.\.\\/)"),
    re.compile(r"(\.\.\/)"),
    re.compile(r"(%2e%2e%2f)"),
    re.compile(r"(%2e%2e\/)"),
    re.compile(r"(%2e%2e%5c)"),
    re.compile(r"(/etc/passwd)"),
    re.compile(r"(/etc/shadow)"),
    re.compile(r"(/etc/hosts)"),
    re.compile(r"(/proc/self/)"),
    re.compile(r"(/var/log/)"),
    re.compile(r"(/boot/)"),
    re.compile(r"(/windows/system32)"),
    re.compile(r"(/winnt/)"),
    re.compile(r"(boot\.ini)"),
]

CMD_INJECTION_PATTERNS = [
    re.compile(r"(?i)(\||;)\s*(ping|nslookup|tracert|curl|wget|nc|bash|cmd|powershell|sh|python|perl|ruby)"),
    re.compile(r"(?i)(`.*`)"),
    re.compile(r"(?i)(\$\(.*\))"),
    re.compile(r"(?i)(\|\||&&)"),
    re.compile(r"(?i)(;.*;)"),
]

LOG_INJECTION_PATTERNS = [
    re.compile(r"(?i)(\r?\n)"),
    re.compile(r"(%0d|%0a|%0D|%0A)"),
]

SCANNER_AGENTS = [
    "nmap", "masscan", "zgrab", "gobuster", "dirbuster", "nikto",
    "sqlmap", "openvas", "nessus", "burpsuite", "acunetix",
    "netsparker", "awvs", "appscan", "w3af", "arachni",
    "crawl", "spider", "scrapy", "wpscan", "joomscan",
]


_RULES_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_SAFE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".css", ".js", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".webm", ".pdf")


def _load_rules() -> Dict[str, Any]:
    now = time.time()
    if now - _RULES_CACHE["ts"] < 30 and _RULES_CACHE["data"] is not None:
        return _RULES_CACHE["data"]
    if not os.path.exists(WAF_PATH):
        data = {"enabled": True, "block_threshold": 10, "mode": "log"}
        _RULES_CACHE["data"] = data
        _RULES_CACHE["ts"] = now
        return data
    try:
        with open(WAF_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _RULES_CACHE["data"] = data
        _RULES_CACHE["ts"] = now
        return data
    except Exception:
        _RULES_CACHE["data"] = {"enabled": True, "block_threshold": 10, "mode": "log"}
        _RULES_CACHE["ts"] = now
        return _RULES_CACHE["data"]


def _save_rules(data: dict) -> None:
    try:
        with open(WAF_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"WAF save error: {e}")


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


def _scan_text(text: str, categories: List[str]) -> WAFResult:
    result = WAFResult()
    if "sqli" in categories:
        for i, pat in enumerate(SQLI_PATTERNS):
            m = pat.search(text)
            if m:
                result.add(f"SQLi pattern #{i + 1}: {m.group(0)[:40]}", 3.0)
    if "xss" in categories:
        for i, pat in enumerate(XSS_PATTERNS):
            m = pat.search(text)
            if m:
                result.add(f"XSS pattern #{i + 1}: {m.group(0)[:40]}", 2.0)
    if "path_traversal" in categories:
        for i, pat in enumerate(PATH_TRAVERSAL_PATTERNS):
            m = pat.search(text)
            if m:
                result.add(f"Path traversal #{i + 1}: {m.group(0)[:40]}", 3.0)
    if "cmd_injection" in categories:
        for i, pat in enumerate(CMD_INJECTION_PATTERNS):
            m = pat.search(text)
            if m:
                result.add(f"CMD injection #{i + 1}: {m.group(0)[:40]}", 4.0)
    if "log_injection" in categories:
        for i, pat in enumerate(LOG_INJECTION_PATTERNS):
            m = pat.search(text)
            if m:
                result.add(f"Log injection #{i + 1}: {m.group(0)[:40]}", 1.0)
    config = _load_rules()
    if result.score >= config.get("block_threshold", 10):
        result.blocked = True
    return result


def check_request(method: str, path: str, headers: Dict[str, str], body: str = "") -> WAFResult:
    config = _load_rules()
    if not config.get("enabled", True):
        return WAFResult()

    # Skip expensive scan for static assets
    if path.lower().endswith(_SAFE_EXTENSIONS) and method == "GET":
        return WAFResult()

    categories = ["sqli", "xss", "path_traversal", "cmd_injection", "log_injection"]
    decoded_path = unquote(path) if isinstance(path, str) else path

    # Build text to scan efficiently — avoid json.dumps if body is empty
    if body:
        all_text = f"{decoded_path} {body}"
    else:
        all_text = decoded_path

    result = _scan_text(all_text, categories)

    # Check headers separately for scanner UA
    ua = headers.get("user-agent", "").lower()
    for agent in SCANNER_AGENTS:
        if agent in ua:
            result.add(f"Scanner detected: {agent}", 5.0)

    # Re-check with headers included only if needed
    if not result.blocked and headers:
        hdr_text = json.dumps(dict(headers))
        hdr_result = _scan_text(hdr_text, categories)
        result.score += hdr_result.score
        result.reasons.extend(hdr_result.reasons)
        if hdr_result.score >= config.get("block_threshold", 10):
            result.blocked = True

    if result.score > 0:
        logger.warning(f"WAF: {method} {path[:80]} -> score={result.score} severity={result.severity} reasons={result.reasons}")

    return result


def get_stats() -> Dict[str, Any]:
    return {"rules_count": {"sqli": len(SQLI_PATTERNS), "xss": len(XSS_PATTERNS), "path_traversal": len(PATH_TRAVERSAL_PATTERNS), "cmd_injection": len(CMD_INJECTION_PATTERNS), "log_injection": len(LOG_INJECTION_PATTERNS), "scanner_agents": len(SCANNER_AGENTS)}}


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
