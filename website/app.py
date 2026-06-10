import os, sys, time, json, threading, re, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, jsonify, request, redirect, session, url_for, send_from_directory, make_response
from models import db, Log, init_db
from logger import log
from database import load as load_db
from config import RATE_LIMIT, SESSION_TIMEOUT, MAX_LOGIN_ATTEMPTS, LOGIN_BLOCK_MINUTES, ADMIN_IP_WHITELIST, ADMIN_IP_BIND, CORS_ORIGIN, CSRF_ENABLED

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
app.config["MAX_CONTENT_LENGTH"] = 1024 * 100
db.init_app(app)

DASH_PASSWORD = os.environ.get("TilinX_DASH_PASSWORD", "hw132319")

with app.app_context():
    init_db(app)

bot_thread_started = False

def ensure_bot():
    global bot_thread_started
    if bot_thread_started:
        return
    bot_thread_started = True
    try:
        from bot_control import start_bot
        t = threading.Thread(target=start_bot, daemon=True)
        t.start()
        log.info("Bot iniciado desde app.py")
    except Exception as e:
        log.error(f"Error iniciando bot: {e}")

ensure_bot()

# ─── Security: Rate Limiter ──────────────────────────────
RATE_STORE = {}
LOGIN_ATTEMPTS = {}

def _get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"

def _rate_limit(key, max_req=30, window=60):
    now = time.time()
    entry = RATE_STORE.get(key, {"count": 0, "reset": now + window})
    if now > entry["reset"]:
        entry["count"] = 0
        entry["reset"] = now + window
    entry["count"] += 1
    RATE_STORE[key] = entry
    remaining = max(0, max_req - entry["count"])
    if remaining <= 0:
        return False
    return True

def _is_scraper():
    ua = (request.headers.get("User-Agent", "") or "").lower()
    scrapers = ["python-requests", "curl/", "wget/", "go-http-client", "java/", "scrapy",
                 "ruby", "php", "perl", "libwww", "httpclient", "nikto", "nmap",
                 "masscan", "zgrab", "httpx", "gospider", "katana", "feroxbuster"]
    for s in scrapers:
        if s in ua:
            return True
    return False

def _check_admin_ip():
    if not ADMIN_IP_BIND:
        return True
    ip = _get_client_ip()
    if not ADMIN_IP_WHITELIST or ADMIN_IP_WHITELIST == [""]:
        return True
    return ip in ADMIN_IP_WHITELIST

SESSION_FINGERPRINTS = {}

def _get_fingerprint():
    ua = request.headers.get("User-Agent", "")
    accept = request.headers.get("Accept", "")
    return hashlib.md5((ua + accept).encode()).hexdigest()

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
    # CSRF: validate origin for state-changing requests
    if CSRF_ENABLED and request.method in ("POST", "DELETE", "PUT", "PATCH") and not request.path.startswith("/api/login"):
        origin = request.headers.get("Origin", "")
        referer = request.headers.get("Referer", "")
        valid = False
        if origin and (CORS_ORIGIN in origin or "tilinx.onrender.com" in origin):
            valid = True
        if referer and ("tilinx.onrender.com" in referer or "localhost" in referer or "127.0.0.1" in referer):
            valid = True
        if not origin and not referer:
            valid = True
        if not valid:
            log.warning(f"CSRF blocked: {request.method} {request.path} from origin={origin}")
            return jsonify(error="CSRF validation failed"), 403

    # Anti-scraper
    if _is_scraper():
        log.warning(f"Scraper blocked: {_get_client_ip()} UA={request.headers.get('User-Agent','')[:80]}")
        return "Forbidden", 403

    # Honeypot detection
    if request.path == "/wp-admin" or request.path == "/administrator" or \
       request.path == "/.env" or request.path == "/.git/config" or \
       request.path == "/phpmyadmin" or request.path == "/xmlrpc.php":
        log.warning(f"Honeypot triggered: {_get_client_ip()} -> {request.path}")
        return "Not Found", 404

    # Rate limit general
    ip = _get_client_ip()
    if request.path.startswith("/api/"):
        allowed = _rate_limit("api:" + ip, max_req=RATE_LIMIT * 3, window=60)
        if not allowed:
            log.warning(f"Rate limited: {ip} on {request.path}")
            return jsonify(error="Too many requests"), 429

    # Session timeout + fingerprint
    if session.get("logged_in"):
        now = time.time()
        last_activity = session.get("last_activity", 0)
        if now - last_activity > SESSION_TIMEOUT:
            session.clear()
            if request.path.startswith("/admin") or request.path.startswith("/api/"):
                return redirect("/login")
        session["last_activity"] = now
        fp = _get_fingerprint()
        stored = session.get("fingerprint")
        if stored and stored != fp:
            log.warning(f"Fingerprint mismatch! Possible session hijack: {ip}")
            session.clear()
            return redirect("/login")
        if not stored:
            session["fingerprint"] = fp

    # Admin IP check
    if request.path.startswith("/admin") or request.path.startswith("/api/"):
        if not _check_admin_ip():
            log.warning(f"Admin IP blocked: {ip}")
            return "Access Denied", 403

    # Auth redirect for admin
    if request.path.startswith("/admin") and not session.get("logged_in"):
        return redirect("/login")

# ─── Security Headers ─────────────────────────────────────
@app.after_request
def add_security_headers(resp):
    # CSP
    csp = (
        "default-src 'self';"
        "script-src 'self' 'unsafe-inline' https://fonts.googleapis.com;"
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com;"
        "font-src 'self' https://fonts.gstatic.com;"
        "img-src 'self' data: blob:;"
        "connect-src 'self' https://api.telegram.org;"
        "frame-ancestors 'none';"
        "base-uri 'self';"
        "form-action 'self'"
    )
    resp.headers["Content-Security-Policy"] = csp
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-XSS-Protection"] = "1; mode=block"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.path.startswith("/admin") or request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    return resp

# ─── CORS ─────────────────────────────────────────────────
@app.after_request
def add_cors(resp):
    origin = request.headers.get("Origin", "")
    if origin in [CORS_ORIGIN, "https://tilinx.onrender.com"] or (not origin):
        resp.headers["Access-Control-Allow-Origin"] = origin or CORS_ORIGIN
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-Token"
        resp.headers["Access-Control-Allow-Credentials"] = "true"
    return resp

@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        resp = make_response()
        return add_cors(add_security_headers(resp))

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

@app.route("/terminal")
def terminal():
    return render_template("terminal.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/login")
def login_page():
    return render_template("login.html")

# ─── API Routes ────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def api_login():
    ip = _get_client_ip()
    now = time.time()

    # Check brute force block
    entry = LOGIN_ATTEMPTS.get(ip, {"count": 0, "blocked_until": 0})
    if now < entry.get("blocked_until", 0):
        remaining = int(entry["blocked_until"] - now)
        log.warning(f"Login blocked (brute force): {ip} for {remaining}s")
        return jsonify(success=False, error=f"Demasiados intentos. Esperá {remaining}s."), 429

    data = request.get_json() or {}
    if not data or "password" not in data:
        return jsonify(success=False), 400

    password = data.get("password") or data.get("pass", "")
    if password == DASH_PASSWORD:
        session.clear()
        session["logged_in"] = True
        session["fingerprint"] = _get_fingerprint()
        session["last_activity"] = time.time()
        LOGIN_ATTEMPTS.pop(ip, None)
        log_event("admin_login", f"Admin login from {ip}")
        return jsonify(success=True)

    entry["count"] += 1
    if entry["count"] >= MAX_LOGIN_ATTEMPTS:
        entry["blocked_until"] = now + LOGIN_BLOCK_MINUTES * 60
        log.warning(f"Login blocked after {entry['count']} attempts: {ip}")
    LOGIN_ATTEMPTS[ip] = entry
    log_event("login_failed", f"Invalid password attempt from {ip}", "warn")
    return jsonify(success=False), 401

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
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

@app.route("/api/terminal-stats")
def api_terminal_stats():
    import psutil
    import platform
    uptime_secs = time.time() - psutil.boot_time()
    days = int(uptime_secs // 86400)
    hours = int((uptime_secs % 86400) // 3600)
    mins = int((uptime_secs % 3600) // 60)
    uptime_str = f"{days}d {hours}h {mins}m"
    ram = psutil.virtual_memory()
    return jsonify({
        "status": "operational",
        "uptime": uptime_secs,
        "uptime_str": uptime_str,
        "cpu": psutil.cpu_percent(),
        "cpu_percent": psutil.cpu_percent(),
        "cpu_model": platform.processor() or "N/A",
        "cpu_cores": psutil.cpu_count(logical=True),
        "ram": ram.percent,
        "ram_percent": ram.percent,
        "ram_total": f"{ram.total // (1024**3)} GB",
        "ram_used": f"{ram.used // (1024**3)} GB",
        "disk": psutil.disk_usage("/").percent,
        "os": platform.system() + " " + platform.release(),
        "hostname": platform.node(),
        "users": len(psutil.users()),
        "processes": len(psutil.pids()),
    })

@app.route("/tg-verify/<int:chat_id>/<token>")
def tg_verify(chat_id, token):
    try:
        from bot_control import consume_verify_token
        forwarded = request.headers.get("X-Forwarded-For", "")
        ip = forwarded.split(",")[0].strip() if forwarded else request.remote_addr or "unknown"
        result = consume_verify_token(token, ip)
        if result:
            html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>TilinX - IP Verificada</title><style>body{{background:#000;color:#0f0;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;text-align:center;padding:20px}} .box{{border:2px solid rgba(130,0,255,0.6);border-radius:16px;padding:40px;max-width:400px;background:rgba(0,0,0,0.8)}} h1{{color:#b44aff}} .ip{{font-size:24px;color:#00ff41;font-weight:700}} .ok{{color:#00ff41;font-size:48px}}</style></head><body><div class="box"><div class="ok">✅</div><h1>IP Verificada</h1><p style="color:rgba(180,80,255,0.7)">Tu IP:</p><p class="ip">{result["ip"]}</p><p style="color:rgba(180,80,255,0.5);margin-top:16px">Key <b>{result["code"]}</b> activada.<br>Ya podés cerrar esta página.</p></div></body></html>"""
            return html, 200, {"Content-Type": "text/html; charset=utf-8"}
        return "<html><body style='background:#000;color:#ff4444;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh'><div style='text-align:center'><h1>Token invalido o expirado</h1><p style='color:rgba(180,80,255,0.6)'>Solicita uno nuevo con /redeem en el bot.</p></div></body></html>", 200, {"Content-Type": "text/html; charset=utf-8"}
    except Exception as e:
        return f"<html><body style='background:#000;color:#ff4444;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh'>Error: {e}</body></html>", 500, {"Content-Type": "text/html; charset=utf-8"}

@app.route("/api/bot-status")
def api_bot_status():
    try:
        from bot_control import get_bot_status
        s = get_bot_status()
        s["token_preview"] = "****" + (s["token_set"] and "***" or "")
        return jsonify(s)
    except Exception as e:
        return jsonify({"running": False, "error": str(e)})

@app.route("/api/contact", methods=["POST"])
def api_contact():
    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify(success=False), 400
    log_event("contact_message", f"From: {data.get('name','?')} - {data.get('message','')[:100]}")
    return jsonify(success=True, message="Message received")

@app.route("/api/logs")
def api_logs():
    if not session.get("logged_in"):
        return jsonify([]), 401
    limit = request.args.get("limit", 50, type=int)
    limit = min(limit, 200)
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
        status = "active"
        if k.get("used") or (expires_ts > 0 and expires_ts <= now):
            status = "expired"
        out.append({
            "id": k["code"],
            "label": k.get("label", k["code"][:12]),
            "key": k["code"],
            "status": status,
            "expires": time.strftime("%Y-%m-%d", time.localtime(expires_ts)) if k.get("duration", 0) > 0 else "never",
            "uses": len(k.get("active_ips", [])) if k.get("used") else 0,
            "max_devices": k.get("max_devices", 1),
            "active_ips": k.get("active_ips", []),
            "created": time.strftime("%Y-%m-%d %H:%M", time.localtime(k.get("created_at", 0))),
        })
    return jsonify(out)

@app.route("/api/keys", methods=["POST"])
def api_create_key():
    if not session.get("logged_in"):
        return jsonify(success=False), 401
    data = request.get_json() or {}
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify(success=False, error="Label requerido"), 400
    if len(label) > 50:
        return jsonify(success=False, error="Label demasiado largo"), 400
    days = int(data.get("duration", 30))
    if days < 0 or days > 3650:
        return jsonify(success=False, error="Duracion invalida"), 400
    max_devices = int(data.get("max_devices", 1))
    if max_devices < 1 or max_devices > 50:
        return jsonify(success=False, error="Dispositivos invalido (1-50)"), 400
    duration_sec = days * 86400 if days > 0 else 0
    from keys import generate_key
    code = generate_key(duration_sec, label, max_devices)
    log_event("key_created", f"Key {code} ({days}d, max={max_devices}) label={label}")
    return jsonify(success=True, code=code)

@app.route("/api/keys/<code>/extend", methods=["POST"])
def api_extend_key(code):
    if not session.get("logged_in"):
        return jsonify(success=False), 401
    data = request.get_json() or {}
    seconds = int(data.get("seconds", 3600))
    if seconds > 86400 * 365:
        return jsonify(success=False, error="Excede maximo"), 400
    from keys import modify_key_duration
    ok = modify_key_duration(code, seconds)
    if ok:
        log_event("key_extended", f"Key {code} extended by {seconds}s")
        return jsonify(success=True)
    return jsonify(success=False), 404

@app.route("/api/keys/<code>/refresh", methods=["POST"])
def api_refresh_key(code):
    if not session.get("logged_in"):
        return jsonify(success=False), 401
    from keys import refresh_key
    ok = refresh_key(code)
    if ok:
        log_event("key_refreshed", f"Key {code} refreshed for reuse")
        return jsonify(success=True)
    return jsonify(success=False), 404

@app.route("/api/keys/<code>/revoke-ip", methods=["POST"])
def api_revoke_key_ip(code):
    if not session.get("logged_in"):
        return jsonify(success=False), 401
    data = request.get_json() or {}
    ip = data.get("ip", "")
    if not ip:
        return jsonify(success=False, error="IP requerida"), 400
    from keys import remove_ip_from_key
    ok = remove_ip_from_key(code, ip)
    if ok:
        log_event("key_ip_revoked", f"IP {ip} revoked from key {code}")
        return jsonify(success=True)
    return jsonify(success=False), 404

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
        if ip == "_integrity":
            continue
        used_time = data.get("used_at", data.get("expires_at", 0))
        out.append({
            "user": ip.split(".")[-1] if "." in ip else ip,
            "ip": ip,
            "key": data.get("key_used", "--"),
            "device_index": data.get("device_index", 1),
            "max_devices": data.get("max_devices", 1),
            "date": time.strftime("%d/%m/%Y %H:%M", time.localtime(used_time)) if used_time else "--",
            "ok": data.get("status") == "active",
        })
    failed = Log.query.filter(Log.event == "key_redeem_failed").order_by(Log.id.desc()).limit(20).all()
    for f in failed:
        out.append({
            "user": "???",
            "ip": f.detail.split(" ")[-1] if " " in f.detail else "--",
            "key": "--",
            "device_index": 0,
            "max_devices": 0,
            "date": f.timestamp[:16] if f.timestamp else "--",
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
    except Exception as e:
        log.warning(f"Error fetching home stats: {e}")
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
