import os, sys, csv, json, time
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import load
from logger import log

def generate_csv(output_path: str = None) -> str:
    db = load()
    now = time.time()
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"report_users_{ts}.csv"
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["IP", "Status", "Expires At", "Days Remaining"])
        for ip, info in db.items():
            status = info.get("status", "")
            exp = info.get("expires_at", 0)
            days_rem = round((exp - now) / 86400, 1) if status == "active" and exp > now else 0
            exp_str = datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M") if exp else "—"
            w.writerow([ip, status, exp_str, days_rem])
    log.info(f"CSV report generated: {output_path}")
    return output_path

def generate_json_report(report_type: str = "daily") -> dict:
    db = load()
    now = time.time()
    total = len(db)
    active = sum(1 for u in db.values() if u.get("status") == "active" and u.get("expires_at", 0) > now)
    expired = sum(1 for u in db.values() if u.get("status") == "active" and u.get("expires_at", 0) <= now)
    blocked = sum(1 for u in db.values() if u.get("status") == "blocked")
    return {
        "type": report_type,
        "generated_at": datetime.now().isoformat(),
        "total_users": total,
        "active": active,
        "expired": expired,
        "blocked": blocked,
        "active_pct": round(active / total * 100, 1) if total else 0,
    }

def generate_report_file(report_type: str = "daily") -> str:
    data = generate_json_report(report_type)
    ts = datetime.now().strftime("%Y%m%d")
    path = f"report_{report_type}_{ts}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    log.info(f"Report saved: {path}")
    return path

if __name__ == "__main__":
    if "--csv" in sys.argv:
        generate_csv()
    else:
        for rtype in ["daily", "weekly", "monthly"]:
            generate_report_file(rtype)
            print(f"✅ {rtype} report generated")
