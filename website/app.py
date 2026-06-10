import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request, redirect, session, url_for
from models import db, Log, init_db
from logger import log

app = Flask(__name__)
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
       request.path in ("/login", "/contact"):
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
    return render_template("status.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/login")
def login_page():
    return render_template("login.html")

# ─── API Routes ────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    if data and data.get("password") == DASH_PASSWORD:
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
