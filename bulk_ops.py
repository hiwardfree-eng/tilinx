import csv, io, json, time, threading
from typing import List, Dict, Any, Optional, Iterator
from database import load, save
from keys import generate_key, list_keys, delete_key, remove_ip_from_key

_csv_lock = threading.Lock()


def export_ips_csv() -> str:
    db = load()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ip", "status", "expires_at", "key_used", "used_at", "device_index", "max_devices"])
    now = time.time()
    for ip, info in sorted(db.items()):
        if ip == "_integrity":
            continue
        exp = info.get("expires_at", 0) or 0
        exp_str = "permanent" if exp == 0 else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp))
        used_str = ""
        if info.get("used_at"):
            used_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(info["used_at"]))
        writer.writerow([
            ip,
            info.get("status", ""),
            exp_str,
            info.get("key_used", ""),
            used_str,
            info.get("device_index", 1),
            info.get("max_devices", 1),
        ])
    return output.getvalue()


def export_keys_csv() -> str:
    keys = list_keys()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["code", "label", "duration_seconds", "created_at", "used", "used_by_ip",
                     "max_devices", "active_ips_count", "locked_ips_count"])
    for k in keys:
        writer.writerow([
            k["code"],
            k.get("label", ""),
            k.get("duration", 0),
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(k.get("created_at", 0))),
            "yes" if k.get("used") else "no",
            k.get("used_by_ip", ""),
            k.get("max_devices", 1),
            len(k.get("active_ips", [])),
            len(k.get("locked_ips", [])),
        ])
    return output.getvalue()


def import_ips_csv(content: str) -> Dict[str, Any]:
    result = {"imported": 0, "skipped": 0, "errors": 0, "lines": []}
    reader = csv.DictReader(io.StringIO(content))
    db = load()
    for row in reader:
        ip = row.get("ip", "").strip()
        if not ip:
            result["errors"] += 1
            continue
        status = row.get("status", "active").strip()
        exp_str = row.get("expires_at", "permanent").strip().lower()
        if exp_str == "permanent":
            expires_at = 0
        else:
            try:
                expires_at = time.mktime(time.strptime(exp_str, "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                expires_at = 0
        if ip in db:
            result["skipped"] += 1
            result["lines"].append({"ip": ip, "action": "skipped", "reason": "already_exists"})
            continue
        db[ip] = {
            "status": status if status in ("active", "blocked") else "active",
            "expires_at": expires_at,
            "key_used": row.get("key_used", "").strip(),
            "used_at": time.time(),
            "device_index": int(row.get("device_index", 1)),
            "max_devices": int(row.get("max_devices", 1)),
        }
        result["imported"] += 1
        result["lines"].append({"ip": ip, "action": "imported"})
    save(db)
    return result


def import_keys_csv(content: str, default_duration: int = 86400) -> Dict[str, Any]:
    result = {"imported": 0, "errors": 0, "lines": []}
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        label = row.get("label", "").strip()
        dur_str = row.get("duration_seconds", "").strip()
        duration = int(dur_str) if dur_str.isdigit() else default_duration
        max_devices = int(row.get("max_devices", 1))
        try:
            code = generate_key(duration, label, max_devices)
            result["imported"] += 1
            result["lines"].append({"code": code, "action": "generated"})
        except Exception:
            result["errors"] += 1
    return result


def bulk_add_ips(ip_list: List[str], duration: int = 0, key_code: str = "") -> Dict[str, Any]:
    result = {"added": 0, "skipped": 0, "errors": 0}
    db = load()
    for ip in ip_list:
        ip = ip.strip()
        if not ip:
            continue
        if ip in db:
            result["skipped"] += 1
            continue
        db[ip] = {
            "status": "active",
            "expires_at": duration if duration > 0 else 0,
            "key_used": key_code,
            "used_at": time.time(),
            "device_index": 1,
            "max_devices": 1,
        }
        result["added"] += 1
    save(db)
    return result


def bulk_remove_ips(ip_list: List[str]) -> Dict[str, Any]:
    result = {"removed": 0, "not_found": 0}
    db = load()
    for ip in ip_list:
        ip = ip.strip()
        if not ip:
            continue
        if ip not in db:
            result["not_found"] += 1
            continue
        key_code = db[ip].get("key_used", "")
        if key_code and key_code.startswith("TILINX-"):
            remove_ip_from_key(key_code, ip)
        del db[ip]
        result["removed"] += 1
    save(db)
    return result


def bulk_set_status(ip_list: List[str], status: str) -> Dict[str, Any]:
    result = {"updated": 0, "not_found": 0}
    if status not in ("active", "blocked"):
        return result
    db = load()
    for ip in ip_list:
        ip = ip.strip()
        if not ip:
            continue
        if ip not in db:
            result["not_found"] += 1
            continue
        db[ip]["status"] = status
        result["updated"] += 1
    save(db)
    return result
