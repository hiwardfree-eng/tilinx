import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request, redirect, session, url_for, send_from_directory
from models import db, Log, init_db
from logger import log
from database import load as load_db

app = Flask(__name__)
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory(ASSETS_DIR, filename)

app.secret_key = os.environ.get("TilinX_WEB_SECRET", os.urandom(32).hex())
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "TilinX_DATABASE_URL", "sqlite:///" + os.path.join(os.path.dirname(__file__), "tilinx.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

DASH_PASSWORD = os.environ.get("TilinX_DASH_PASSWORD", "hw132319")

with app.app_context():
    init_db(app)

# ─── Auth ─────────────────────────────────────────────────
def require_auth():
    if not session.get("logged_in"):
        return redirect("/login")

def log_event(event, detail="", level="info"):
    with app.app_context():
        l = Log(event=event, detail=detail, level=level)
        db.session.add(l)
        db.session.commit()

@app.before_request
def before_request():
    if request.path.startswith("/assets") or request.path.startswith("/api") or \
       request.path.startswith("/static") or request.path in ("/login", "/contact"):
        return
    if request.path.startswith("/admin") and not session.get("logged_in"):
        return redirect("/login")

# ─── Public Routes ─────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/downloads")
def downloads():
    return render_template("downloads.html")

@app.route("/status")
def status():
    return redirect("/")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

# ─── API Routes ────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    password = data.get("password") or data.get("pass", "")
    if password == DASH_PASSWORD:
        session["logged_in"] = True
        log_event("admin_login", "Admin logged in")
        return jsonify(success=True)
    log_event("login_failed", "Invalid password attempt", "warn")
    return jsonify(success=False), 401

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("logged_in", None)
    return jsonify(success=True)

@app.route("/api/status")
def api_status():
    import psutil
    uptime = time.time() - psutil.boot_time()
    return jsonify({
        "status": "operational",
        "uptime": round(uptime),
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("/").percent,
    })

@app.route("/api/contact", methods=["POST"])
def api_contact():
    data = request.get_json()
    log_event("contact_message", f"From: {data.get('name','?')} - {data.get('message','')[:100]}")
    return jsonify(success=True, message="Message received")

@app.route("/api/logs")
def api_logs():
    if not session.get("logged_in"):
        return jsonify([]), 401
    limit = request.args.get("limit", 50, type=int)
    logs = Log.query.order_by(Log.id.desc()).limit(limit).all()
    return jsonify([{"event": l.event, "detail": l.detail, "level": l.level, "time": l.timestamp} for l in logs])

# ─── Keys API ──────────────────────────────────────────────
@app.route("/api/keys")
def api_keys():
    if not session.get("logged_in"):
        return jsonify([]), 401
    from keys import list_keys
    raw = list_keys()
    out = []
    for k in raw:
        expires_ts = k.get("created_at", 0) + k.get("duration", 0)
        now = time.time()
        status = "active" if (not k.get("used") and expires_ts > now) else "expired"
        if k.get("used"):
            status = "expired"
        out.append({
            "id": k["code"],
            "label": k.get("label", k["code"][:12]),
            "key": k["code"],
            "status": status,
            "expires": time.strftime("%Y-%m-%d", time.localtime(expires_ts)) if k.get("duration", 0) > 0 else "never",
            "uses": 1 if k.get("used") else 0,
            "created": time.strftime("%Y-%m-%d %H:%M", time.localtime(k.get("created_at", 0))),
        })
    return jsonify(out)

@app.route("/api/keys", methods=["POST"])
def api_create_key():
    if not session.get("logged_in"):
        return jsonify(success=False), 401
    data = request.get_json()
    label = (data or {}).get("label", "")
    days = int((data or {}).get("duration", 30))
    duration_sec = days * 86400
    from keys import generate_key
    code = generate_key(duration_sec, label)
    log_event("key_created", f"Key {code} ({days}d) label={label}")
    return jsonify(success=True, code=code)

@app.route("/api/keys/<code>", methods=["DELETE"])
def api_delete_key(code):
    if not session.get("logged_in"):
        return jsonify(success=False), 401
    from keys import delete_key
    ok = delete_key(code)
    if ok:
        log_event("key_deleted", f"Key {code} deleted")
        return jsonify(success=True)
    return jsonify(success=False), 404

# ─── IPs API ───────────────────────────────────────────────
@app.route("/api/ips")
def api_ips():
    if not session.get("logged_in"):
        return jsonify([]), 401
    db = load_db()
    out = []
    for ip, data in db.items():
        used_time = data.get("used_at", data.get("expires_at", 0))
        out.append({
            "user": ip.split(".")[-1] if "." in ip else ip,
            "ip": ip,
            "key": data.get("key_used", "—"),
            "date": time.strftime("%d/%m/%Y %H:%M", time.localtime(used_time)) if used_time else "—",
            "ok": data.get("status") == "active",
        })
    # Add failed attempts from logs
    failed = Log.query.filter(Log.event == "key_redeem_failed").order_by(Log.id.desc()).limit(20).all()
    for f in failed:
        out.append({
            "user": "???",
            "ip": f.detail.split(" ")[-1] if " " in f.detail else "—",
            "key": "—",
            "date": f.timestamp[:16] if f.timestamp else "—",
            "ok": False,
        })
    out.sort(key=lambda x: x["date"], reverse=True)
    return jsonify(out)

# ─── Home Stats API ────────────────────────────────────────
@app.route("/api/home-stats")
def api_home_stats():
    try:
        from keys import list_keys
        raw = list_keys()
        total = len(raw)
        active = sum(1 for k in raw if not k.get("used") and (k.get("duration", 0) == 0 or k.get("created_at", 0) + k.get("duration", 0) > time.time()))
        used = sum(1 for k in raw if k.get("used"))
    except Exception:
        total = active = used = 0
    return jsonify(total=total, active=active, used=used)

# ─── Admin Routes ──────────────────────────────────────────
@app.route("/admin")
def admin_index():
    return render_template("admin.html")

# ─── 404 ───────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template("index.html"), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", os.environ.get("TilinX_WEB_PORT", 8080)))
    log.info(f"TilinX Website starting on :{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
