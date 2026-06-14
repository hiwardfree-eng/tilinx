import os, json, time, logging
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

logger = logging.getLogger("tilinx.postgres")

DEFAULT_CONFIG = {
    "host": os.environ.get("SUPABASE_DB_HOST", ""),
    "port": int(os.environ.get("SUPABASE_DB_PORT", "5432")),
    "dbname": os.environ.get("SUPABASE_DB_NAME", "postgres"),
    "user": os.environ.get("SUPABASE_DB_USER", "postgres"),
    "password": os.environ.get("SUPABASE_DB_PASSWORD", ""),
    "connect_timeout": 10,
}
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
PG_ENABLED = bool(os.environ.get("SUPABASE_DB_HOST", "")) and bool(os.environ.get("SUPABASE_DB_PASSWORD", ""))

# Column whitelists to prevent SQL injection in dynamic updates
IPS_COLUMNS = {"ip", "status", "expires_at", "key_used", "used_at", "device_index", "max_devices", "created_at", "auth_count", "blocked_reason"}
KEYS_COLUMNS = {"code", "label", "duration", "max_devices", "status", "created_at", "used_at", "expires_at", "used_by_ips", "locked_ips", "active_ips"}
USERS_COLUMNS = {"username", "password_hash", "email", "role", "created_at", "last_login", "is_active", "permissions"}


class _PGConn:
    """Context manager that provides a PostgreSQL connection with auto-cleanup."""
    def __init__(self):
        self.conn = None

    def __enter__(self):
        if not HAS_PSYCOPG2:
            raise ImportError("psycopg2-binary not installed")
        self.conn = psycopg2.connect(**DEFAULT_CONFIG)
        self.conn.autocommit = True
        return self.conn

    def __exit__(self, *exc):
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
        return False


def _filter_columns(updates: Dict[str, Any], allowed: set) -> Dict[str, Any]:
    return {k: v for k, v in updates.items() if k in allowed}


def _ensure_tables() -> None:
    if not PG_ENABLED:
        return
    try:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ips (
                        ip TEXT PRIMARY KEY,
                        status TEXT NOT NULL DEFAULT 'active',
                        expires_at DOUBLE PRECISION,
                        key_used TEXT,
                        used_at DOUBLE PRECISION,
                        device_index INTEGER DEFAULT 1,
                        max_devices INTEGER DEFAULT 1,
                        created_at DOUBLE PRECISION,
                        auth_count INTEGER DEFAULT 0,
                        blocked_reason TEXT
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS keys (
                        code TEXT PRIMARY KEY,
                        label TEXT DEFAULT '',
                        duration INTEGER DEFAULT 0,
                        max_devices INTEGER DEFAULT 1,
                        status TEXT DEFAULT 'active',
                        created_at DOUBLE PRECISION,
                        used_at DOUBLE PRECISION,
                        expires_at DOUBLE PRECISION,
                        used_by_ips JSONB DEFAULT '[]',
                        locked_ips JSONB DEFAULT '[]',
                        active_ips JSONB DEFAULT '[]'
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        username TEXT PRIMARY KEY,
                        password_hash TEXT NOT NULL DEFAULT '',
                        email TEXT UNIQUE,
                        role TEXT DEFAULT 'user',
                        created_at DOUBLE PRECISION,
                        last_login DOUBLE PRECISION,
                        is_active BOOLEAN DEFAULT TRUE,
                        permissions JSONB DEFAULT '{}'
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        token TEXT PRIMARY KEY,
                        username TEXT NOT NULL,
                        created_at DOUBLE PRECISION,
                        expires_at DOUBLE PRECISION,
                        ip_address TEXT DEFAULT '',
                        user_agent TEXT DEFAULT ''
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id BIGSERIAL PRIMARY KEY,
                        action TEXT NOT NULL,
                        actor_ip TEXT DEFAULT '',
                        resource TEXT DEFAULT '',
                        status TEXT DEFAULT 'info',
                        details JSONB DEFAULT '{}',
                        timestamp DOUBLE PRECISION
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_status ON ips(status)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_expires ON ips(expires_at)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_keys_status ON keys(status)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp DESC)")
    except Exception as e:
        logger.error(f"Error creating tables: {e}")


# ─── IPS ──────────────────────────────────────────────────

def add_ip(ip: str, status: str = "active", expires_at: float = 0, key_used: str = "",
           used_at: Optional[float] = None, device_index: int = 1, max_devices: int = 1) -> bool:
    if not PG_ENABLED:
        return False
    try:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ips (ip, status, expires_at, key_used, used_at, device_index, max_devices, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ip) DO UPDATE SET
                        status = EXCLUDED.status,
                        expires_at = EXCLUDED.expires_at,
                        key_used = EXCLUDED.key_used,
                        used_at = EXCLUDED.used_at,
                        device_index = EXCLUDED.device_index,
                        max_devices = EXCLUDED.max_devices
                """, (ip, status, expires_at or None, key_used, used_at or time.time(), device_index, max_devices, time.time()))
        return True
    except Exception as e:
        logger.error(f"add_ip error: {e}")
        return False


def get_ip(ip: str) -> Optional[Dict[str, Any]]:
    if not PG_ENABLED:
        return None
    try:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM ips WHERE ip = %s", (ip,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_ip error: {e}")
        return None


def list_ips(status_filter: Optional[str] = None, limit: int = 1000) -> List[Dict[str, Any]]:
    if not PG_ENABLED:
        return []
    try:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if status_filter:
                    cur.execute("SELECT * FROM ips WHERE status = %s ORDER BY created_at DESC NULLS LAST LIMIT %s", (status_filter, limit))
                else:
                    cur.execute("SELECT * FROM ips ORDER BY created_at DESC NULLS LAST LIMIT %s", (limit,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"list_ips error: {e}")
        return []


def update_ip(ip: str, updates: Dict[str, Any]) -> bool:
    if not PG_ENABLED:
        return False
    updates = _filter_columns(updates, IPS_COLUMNS)
    if not updates:
        return False
    try:
        sets = ", ".join(f"{k} = %s" for k in updates)
        vals = list(updates.values()) + [ip]
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE ips SET {sets} WHERE ip = %s", vals)
        return True
    except Exception as e:
        logger.error(f"update_ip error: {e}")
        return False


def delete_ip(ip: str) -> bool:
    if not PG_ENABLED:
        return False
    try:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM ips WHERE ip = %s", (ip,))
        return True
    except Exception as e:
        logger.error(f"delete_ip error: {e}")
        return False


# ─── KEYS ─────────────────────────────────────────────────

def add_key(code: str, duration: int = 0, label: str = "", max_devices: int = 1) -> bool:
    if not PG_ENABLED:
        return False
    try:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                now = time.time()
                cur.execute("""
                    INSERT INTO keys (code, label, duration, max_devices, status, created_at, used_by_ips, locked_ips, active_ips)
                    VALUES (%s, %s, %s, %s, 'active', %s, '[]', '[]', '[]')
                    ON CONFLICT (code) DO UPDATE SET
                        label = EXCLUDED.label,
                        duration = EXCLUDED.duration,
                        max_devices = EXCLUDED.max_devices,
                        status = EXCLUDED.status
                """, (code, label, duration, max_devices, now))
        return True
    except Exception as e:
        logger.error(f"add_key error: {e}")
        return False


def get_key(code: str) -> Optional[Dict[str, Any]]:
    if not PG_ENABLED:
        return None
    try:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM keys WHERE code = %s", (code,))
                row = cur.fetchone()
                if row:
                    d = dict(row)
                    for jfield in ("used_by_ips", "locked_ips", "active_ips"):
                        if isinstance(d.get(jfield), str):
                            d[jfield] = json.loads(d[jfield])
                    return d
                return None
    except Exception as e:
        logger.error(f"get_key error: {e}")
        return None


def list_keys(status_filter: Optional[str] = None, limit: int = 1000) -> List[Dict[str, Any]]:
    if not PG_ENABLED:
        return []
    try:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if status_filter:
                    cur.execute("SELECT * FROM keys WHERE status = %s ORDER BY created_at DESC NULLS LAST LIMIT %s", (status_filter, limit))
                else:
                    cur.execute("SELECT * FROM keys ORDER BY created_at DESC NULLS LAST LIMIT %s", (limit,))
                result = []
                for r in cur.fetchall():
                    d = dict(r)
                    for jfield in ("used_by_ips", "locked_ips", "active_ips"):
                        if isinstance(d.get(jfield), str):
                            d[jfield] = json.loads(d[jfield])
                    result.append(d)
                return result
    except Exception as e:
        logger.error(f"list_keys error: {e}")
        return []


def update_key(code: str, updates: Dict[str, Any]) -> bool:
    if not PG_ENABLED:
        return False
    for jfield in ("used_by_ips", "locked_ips", "active_ips"):
        if jfield in updates and isinstance(updates[jfield], (list, dict)):
            updates[jfield] = json.dumps(updates[jfield])
    updates = _filter_columns(updates, KEYS_COLUMNS)
    if not updates:
        return False
    try:
        sets = ", ".join(f"{k} = %s" for k in updates)
        vals = list(updates.values()) + [code]
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE keys SET {sets} WHERE code = %s", vals)
        return True
    except Exception as e:
        logger.error(f"update_key error: {e}")
        return False


def delete_key(code: str) -> bool:
    if not PG_ENABLED:
        return False
    try:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM keys WHERE code = %s", (code,))
        return True
    except Exception as e:
        logger.error(f"delete_key error: {e}")
        return False


# ─── USERS ────────────────────────────────────────────────

def add_user(username: str, password_hash: str = "", email: str = "", role: str = "user") -> bool:
    if not PG_ENABLED:
        return False
    try:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (username, password_hash, email, role, created_at, is_active)
                    VALUES (%s, %s, %s, %s, %s, TRUE)
                    ON CONFLICT (username) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        email = EXCLUDED.email,
                        role = EXCLUDED.role,
                        is_active = EXCLUDED.is_active
                """, (username, password_hash, email, role, time.time()))
        return True
    except Exception as e:
        logger.error(f"add_user error: {e}")
        return False


def get_user(username: str) -> Optional[Dict[str, Any]]:
    if not PG_ENABLED:
        return None
    try:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE username = %s", (username,))
                row = cur.fetchone()
                if row:
                    d = dict(row)
                    if isinstance(d.get("permissions"), str):
                        d["permissions"] = json.loads(d["permissions"])
                    return d
                return None
    except Exception as e:
        logger.error(f"get_user error: {e}")
        return None


def list_users(limit: int = 1000) -> List[Dict[str, Any]]:
    if not PG_ENABLED:
        return []
    try:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM users ORDER BY created_at DESC NULLS LAST LIMIT %s", (limit,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"list_users error: {e}")
        return []


def set_user_active(username: str, active: bool) -> bool:
    if not PG_ENABLED:
        return False
    try:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET is_active = %s WHERE username = %s", (active, username))
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"set_user_active error: {e}")
        return False


def delete_user(username: str) -> bool:
    if not PG_ENABLED:
        return False
    try:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE username = %s", (username,))
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"delete_user error: {e}")
        return False


# ─── SESSIONS ─────────────────────────────────────────────

def create_session(token: str, username: str, expires_at: float, ip_address: str = "", user_agent: str = "") -> bool:
    if not PG_ENABLED:
        return False
    try:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO sessions (token, username, created_at, expires_at, ip_address, user_agent)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (token, username, time.time(), expires_at, ip_address, user_agent))
        return True
    except Exception as e:
        logger.error(f"create_session error: {e}")
        return False


def get_session(token: str) -> Optional[Dict[str, Any]]:
    if not PG_ENABLED:
        return None
    try:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM sessions WHERE token = %s AND expires_at > %s", (token, time.time()))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_session error: {e}")
        return None


def delete_session(token: str) -> bool:
    if not PG_ENABLED:
        return False
    try:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sessions WHERE token = %s", (token,))
        return True
    except Exception as e:
        logger.error(f"delete_session error: {e}")
        return False


# ─── AUDIT ────────────────────────────────────────────────

def log_audit(action: str, actor_ip: str = "", resource: str = "", status: str = "info", details: Optional[Dict] = None) -> bool:
    if not PG_ENABLED:
        return False
    try:
        with _PGConn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO audit_logs (action, actor_ip, resource, status, details, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (action, actor_ip, resource, status, json.dumps(details or {}), time.time()))
        return True
    except Exception as e:
        logger.error(f"log_audit error: {e}")
        return False


def get_audit_logs(limit: int = 100) -> List[Dict[str, Any]]:
    if not PG_ENABLED:
        return []
    try:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT %s", (limit,))
                result = []
                for r in cur.fetchall():
                    d = dict(r)
                    if isinstance(d.get("details"), str):
                        d["details"] = json.loads(d["details"])
                    result.append(d)
                return result
    except Exception as e:
        logger.error(f"get_audit_logs error: {e}")
        return []


# ─── STATS ────────────────────────────────────────────────

def get_stats() -> Dict[str, Any]:
    if not PG_ENABLED:
        return {"enabled": False}
    try:
        with _PGConn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT status, COUNT(*) as count FROM ips GROUP BY status")
                ips_by_status = {r["status"]: r["count"] for r in cur.fetchall()}
                cur.execute("SELECT status, COUNT(*) as count FROM keys GROUP BY status")
                keys_by_status = {r["status"]: r["count"] for r in cur.fetchall()}
                cur.execute("SELECT COUNT(*) as total FROM users")
                total_users = cur.fetchone()["total"]
                cur.execute("SELECT COUNT(*) as total FROM sessions WHERE expires_at > %s", (time.time(),))
                active_sessions = cur.fetchone()["total"]
        return {
            "enabled": True,
            "ips": dict(ips_by_status),
            "keys": dict(keys_by_status),
            "users": total_users,
            "active_sessions": active_sessions,
        }
    except Exception as e:
        logger.error(f"get_stats error: {e}")
        return {"enabled": False, "error": str(e)}


# ─── Migration from local JSON/SQLite ─────────────────────

def migrate_from_local() -> Dict[str, Any]:
    result = {"ips": 0, "keys": 0, "users": 0, "errors": []}
    try:
        from database import load as load_ips
        from keys import _load as load_keys_file
        from adminx import _load as load_adminx

        ips_data = load_ips()
        for ip, info in ips_data.items():
            if ip == "_integrity":
                continue
            ok = add_ip(ip,
                status=info.get("status", "active"),
                expires_at=info.get("expires_at", 0),
                key_used=info.get("key_used", ""),
                used_at=info.get("used_at"),
                device_index=info.get("device_index", 1),
                max_devices=info.get("max_devices", 1))
            if ok:
                result["ips"] += 1
            else:
                result["errors"].append(f"Failed to migrate IP {ip}")

        keys_data = load_keys_file()
        for code, info in keys_data.items():
            ok = add_key(code,
                duration=info.get("duration", 0),
                label=info.get("label", ""),
                max_devices=info.get("max_devices", 1))
            if ok:
                if info.get("used"):
                    used_by_ips = json.dumps(info.get("active_ips", []))
                    locked_ips = json.dumps(info.get("locked_ips", []))
                    with _PGConn() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE keys SET used_by_ips = %s, locked_ips = %s, active_ips = %s,
                                    used_at = %s, status = 'used'
                                WHERE code = %s
                            """, (used_by_ips, locked_ips, used_by_ips, info.get("used_at"), code))
                result["keys"] += 1
            else:
                result["errors"].append(f"Failed to migrate key {code}")

        adminx_data = load_adminx()
        for username, info in adminx_data.items():
            ok = add_user(username,
                password_hash=info.get("key", ""),
                email=f"{username}@tilinx.local",
                role="adminx")
            if ok:
                result["users"] += 1

        logger.info(f"Migration complete: {result['ips']} IPs, {result['keys']} keys, {result['users']} users")
    except Exception as e:
        logger.error(f"Migration error: {e}")
        result["errors"].append(str(e))
    return result


# ─── Init ─────────────────────────────────────────────────

if PG_ENABLED:
    _ensure_tables()
    logger.info("PostgreSQL configured (Supabase)") if SUPABASE_URL else logger.info("PostgreSQL configured (direct)")
else:
    logger.info("PostgreSQL not configured — set SUPABASE_DB_HOST and SUPABASE_DB_PASSWORD")
