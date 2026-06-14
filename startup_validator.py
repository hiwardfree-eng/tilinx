"""Startup validation: checks config, data files, imports, and prints a report."""
import os, sys, json, time, logging
from typing import List, Tuple

logger = logging.getLogger("tilinx.startup")

Check = Tuple[str, bool, str]


def validate_all() -> List[Check]:
    results: List[Check] = []
    results.append(("Python version", True, sys.version.split()[0]))

    # Config sanity
    results.append(_check_env("TilinX_BOT_TOKEN", "BOT_TOKEN", optional=True))
    results.append(_check_env("TilinX_ADMIN_ID", "ADMIN_ID", optional=True))
    port = os.environ.get("TilinX_PROXY_PORT", "8884")
    try:
        p = int(port)
        ok = 1 <= p <= 65535
        results.append(("Proxy port", ok, f"port={p}"))
    except ValueError:
        results.append(("Proxy port", False, f"invalid port: {port}"))

    # Data file integrity
    results.append(_check_json_file("ips.json", "IP database"))
    results.append(_check_json_file("keys.json", "Keys database"))
    results.append(_check_json_file("filters.json", "Filter rules"))
    results.append(_check_json_file("webhooks.json", "Webhook configs"))
    results.append(_check_json_file("alerts.json", "Alert configs"))
    results.append(_check_json_file("adminx.json", "AdminX users"))

    # Directory writability
    results.append(_check_dir_writable("logs", "Log directory"))
    results.append(_check_dir_writable("data", "Data directory"))

    # Critical imports
    critical = [
        "tilinx_proxy", "config", "filter_rules", "geoip",
        "alerts", "webhooks", "keys", "adminx", "bot_control",
        "file_utils", "database",
        "brain.brain_v2", "brain.memory_store",
        "brain.behavior_tracker", "brain.anomaly_engine",
        "brain.risk_scoring", "brain.decision_engine_v2",
    ]
    for mod_name in critical:
        results.append(_check_import(mod_name))

    return results


def _check_env(var: str, label: str, optional: bool = False) -> Check:
    val = os.environ.get(var, "")
    if not val:
        if optional:
            return (label, True, "not set (optional)")
        return (label, False, "missing")
    masked = val[:8] + "***" if len(val) > 12 else val
    return (label, True, f"set ({masked})")


def _check_json_file(name: str, label: str) -> Check:
    base = os.environ.get("TilinX_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, name)
    if not os.path.exists(path):
        return (label, True, "not found (will be created)")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = f.read().strip()
        if not data:
            return (label, True, "empty file (ok)")
        json.loads(data)
        return (label, True, f"valid ({len(data)} bytes)")
    except json.JSONDecodeError as e:
        return (label, False, f"corrupted: {e}")
    except OSError as e:
        return (label, False, f"unreadable: {e}")


def _check_dir_writable(rel_path: str, label: str) -> Check:
    base = os.environ.get("TilinX_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, rel_path)
    try:
        os.makedirs(path, exist_ok=True)
        test_file = os.path.join(path, ".write_test")
        with open(test_file, "w") as f:
            f.write("ok")
        os.unlink(test_file)
        return (label, True, "writable")
    except OSError as e:
        return (label, False, f"not writable: {e}")


def _check_import(mod_name: str) -> Check:
    try:
        __import__(mod_name)
        return (mod_name, True, "imported")
    except ImportError as e:
        return (mod_name, False, f"import error: {e}")
    except Exception as e:
        return (mod_name, False, f"load error: {e}")


def print_report(results: List[Check]) -> None:
    fails = [r for r in results if not r[1]]
    total = len(results)
    print("=" * 50)
    print("  TilinX Startup Validation Report")
    print("=" * 50)
    for name, ok, detail in results:
        icon = "[OK]" if ok else "[FAIL]"
        print(f"  {icon} {name:30s} {detail}")
    print("-" * 50)
    if fails:
        print(f"  {len(fails)}/{total} checks FAILED:")
        for name, _, detail in fails:
            print(f"    - {name}: {detail}")
    else:
        print(f"  All {total} checks PASSED")
    print("=" * 50)


def run_validation_and_exit_on_failure() -> None:
    results = validate_all()
    print_report(results)
    fails = [r for r in results if not r[1]]
    if fails:
        logger.error(f"Startup validation failed: {len(fails)} error(s)")
        sys.exit(1)


if __name__ == "__main__":
    results = validate_all()
    print_report(results)
