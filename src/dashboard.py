import sys, os, json, time, secrets
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request, redirect, session, url_for
from database import load, get_stats
from monitor import get_metrics
from keys import generate_key, list_keys, delete_key
from utils import parse_duration
from logger import log

app = Flask(__name__)
app.secret_key = os.environ.get("TilinX_DASH_SECRET", secrets.token_hex(32))
DASH_PASSWORD = os.environ.get("TilinX_DASH_PASSWORD", "admin")

@app.before_request
def check_auth():
    if request.path.startswith("/static") or request.path == "/login" or request.path == "/api/login":
        return
    if not session.get("logged_in"):
        return redirect(url_for("login"))

@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    if data and data.get("password") == DASH_PASSWORD:
        session["logged_in"] = True
        return jsonify(success=True)
    return jsonify(success=False), 401

@app.route("/")
def index():
    db = load()
    total, active, expired, blocked = get_stats(db)
    metrics = get_metrics()
    return render_template("dashboard.html",
        total=total, active=active, expired=expired, blocked=blocked,
        metrics=metrics, db_size=len(json.dumps(db)),
    )

@app.route("/api/stats")
def api_stats():
    db = load()
    total, active, expired, blocked = get_stats(db)
    return jsonify(total=total, active=active, expired=expired, blocked=blocked)

@app.route("/api/metrics")
def api_metrics():
    return jsonify(get_metrics())

@app.route("/api/users")
def api_users():
    db = load()
    status_filter = request.args.get("status", "")
    now = time.time()
    result = []
    for ip, info in db.items():
        s = info.get("status", "")
        exp = info.get("expires_at", 0)
        is_active = s == "active" and exp > now
        is_expired = s == "active" and exp <= now
        is_blocked = s == "blocked"
        if status_filter == "active" and not is_active: continue
        if status_filter == "expired" and not is_expired: continue
        if status_filter == "blocked" and not is_blocked: continue
        result.append({
            "ip": ip,
            "status": "blocked" if is_blocked else ("active" if is_active else "expired"),
            "expires_at": exp,
        })
    return jsonify(result)

@app.route("/api/users/<ip>", methods=["DELETE"])
def api_delete_user(ip):
    db = load()
    if ip in db:
        db.pop(ip)
        from database import save
        save(db)
        return jsonify(success=True)
    return jsonify(success=False, error="Not found"), 404

@app.route("/api/keys/generate", methods=["POST"])
def api_generate_key():
    data = request.get_json()
    duration_str = data.get("duration", "30d")
    try:
        secs = parse_duration(duration_str)
    except ValueError as e:
        return jsonify(success=False, error=str(e)), 400
    code = generate_key(secs)
    return jsonify(success=True, code=code, duration=duration_str)

@app.route("/api/keys/list")
def api_list_keys():
    keys = list_keys()
    return jsonify(keys)

@app.route("/api/keys/delete", methods=["POST"])
def api_delete_key():
    data = request.get_json()
    code = data.get("code", "")
    if delete_key(code):
        return jsonify(success=True)
    return jsonify(success=False, error="Not found"), 404

if __name__ == "__main__":
    port = int(os.environ.get("TilinX_DASHBOARD_PORT", 5000))
    log.info(f"Dashboard starting on :{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
