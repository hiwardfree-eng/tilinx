import sys, os, re, time, json, threading, secrets, signal
from typing import Optional, Dict, Any, Callable
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
from dotenv import load_dotenv; load_dotenv(_env_path)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import BOT_TOKEN, CHAT_IPS_PATH, ADMIN_ID, PUBLIC_BASE_URL
from logger import log
from keys import redeem_key, list_keys, modify_key_duration, delete_key, remove_ip_from_key
from database import load as load_db, save as save_db
from adminx import create_user as adminx_create, remove_user as adminx_remove, set_active as adminx_set_active, list_users as adminx_list, get_user as adminx_get, find_by_key as adminx_find_by_key
import webhooks
import bulk_ops
import filter_rules
import config_templates
import geoip
import scheduler
import alerts
import waf as waf_module
import rate_limiter
import auth_jwt
import twofa

try:
    import requests
except ImportError:
    requests = None

IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
CHAT_IP_LOCK = threading.Lock()
CHAT_RATE_LOCK = threading.Lock()
CHAT_RATE: Dict[int, float] = {}
COMMAND_COOLDOWN = 0.3
_BOT_THREADS: list[threading.Thread] = []
_SESSION: Optional[requests.Session] = None

HandlerFn = Callable[[int, str, dict], None]

def get_chat_ip(chat_id: int) -> Optional[str]:
    try:
        from file_utils import safe_read_json
        data = safe_read_json(CHAT_IPS_PATH, {})
        return data.get(str(chat_id))
    except Exception:
        return None

def set_chat_ip(chat_id: int, ip: str) -> None:
    with CHAT_IP_LOCK:
        from file_utils import safe_read_json, safe_write_json
        data = safe_read_json(CHAT_IPS_PATH, {})
        data[str(chat_id)] = ip
        safe_write_json(CHAT_IPS_PATH, data)

def generate_verify_token(chat_id: int, code: str) -> str:
    token = secrets.token_hex(8)
    verify_path = CHAT_IPS_PATH.replace(".json", "_pending.json")
    from file_utils import safe_read_json, safe_write_json
    data = safe_read_json(verify_path, {})
    data[token] = {"chat_id": chat_id, "code": code, "time": time.time()}
    safe_write_json(verify_path, data)
    return token

def consume_verify_token(token: str, ip: str) -> Optional[Dict[str, Any]]:
    verify_path = CHAT_IPS_PATH.replace(".json", "_pending.json")
    from file_utils import safe_read_json, safe_write_json
    data = safe_read_json(verify_path, {})
    entry = data.pop(token, None)
    if not entry:
        return None
    if time.time() - entry["time"] > 300:
        safe_write_json(verify_path, data)
        return None
    safe_write_json(verify_path, data)
    chat_id = entry["chat_id"]
    code = entry["code"]
    set_chat_ip(chat_id, ip)
    result = redeem_key(code, ip)
    return {"chat_id": chat_id, "code": code, "ip": ip, "result": result}

START_TIME = time.time()
BOT_RUNNING = False
LAST_UPDATE: float = 0
ERROR_COUNT = 0

def is_valid_ip(text: str) -> bool:
    if not IP_RE.match(text):
        return False
    parts = text.split(".")
    return all(0 <= int(p) <= 255 for p in parts)

def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=0)
        _SESSION.mount("https://", adapter)
    return _SESSION

def bot_req(method: str, **kwargs) -> Optional[dict]:
    if not requests or not BOT_TOKEN:
        return None
    try:
        s = _get_session()
        r = s.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
            params=kwargs,
            timeout=15,
        )
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        log.error(f"Telegram API error ({method}): {e}")
        return None

def bot_send(chat_id: int, text: str, parse_mode: str = "HTML") -> None:
    global LAST_UPDATE
    if not requests or not BOT_TOKEN:
        return
    try:
        s = _get_session()
        s.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        LAST_UPDATE = time.time()
    except Exception as e:
        log.error(f"sendMessage error: {e}")

def _send_split(chat_id: int, msg: str, max_len: int = 4000) -> None:
    while len(msg) > max_len:
        idx = msg.rfind("\n", 0, max_len)
        if idx < 0:
            idx = max_len
        bot_send(chat_id, msg[:idx])
        msg = msg[idx:]
    if msg:
        bot_send(chat_id, msg)

# ─── Stats ──────────────────────────────────────────────

def get_stats_text() -> str:
    try:
        keys = list_keys()
        db = load_db()
        total = len(keys)
        used = sum(1 for k in keys if k.get("used"))
        active = sum(1 for k in keys if not k.get("used") and (k.get("duration", 0) == 0 or k.get("created_at", 0) + k.get("duration", 0) > time.time()))
        active_ips = sum(1 for v in db.values() if v.get("status") == "active")
        uptime = time.time() - START_TIME
        h, r = divmod(int(uptime), 3600)
        m, s = divmod(r, 60)
        uptime_str = f"{h}h {m}m {s}s"
        return (
            f"<b>\U0001f4ca TilinX \u2014 Estad\u00edsticas</b>\n\n"
            f"\U0001f511 Keys totales: {total}\n"
            f"\u2705 Keys activas: {active}\n"
            f"\u274c Keys usadas: {used}\n"
            f"\U0001f465 IPs activas: {active_ips}\n"
            f"\u23f1 Uptime bot: {uptime_str}\n"
            f"\U0001f7e2 Estado: OPERATIVO"
        )
    except Exception as e:
        return f"<b>\U0001f4ca Estad\u00edsticas</b>\n\nError al obtener datos: {e}"

# ─── Command Handlers ───────────────────────────────────

def _cmd_start(chat_id: int, text: str, msg: dict) -> None:
    first = msg["chat"].get("first_name") or ""
    bot_send(chat_id,
        f"<b>\u26a1 Bienvenido a TilinX, {first}!</b>\n\n"
        f"Sistema de protecci\u00f3n y aceleraci\u00f3n para juegos.\n\n"
        f"<b>Comandos disponibles:</b>\n"
        f"\u2022 /login KEY IP \u2014 Activar tu IP con una key\n"
        f"\u2022 /help \u2014 Ayuda detallada\n"
        f"\u2022 /stats \u2014 Estad\u00edsticas del sistema\n"
        f"\u2022 /ping \u2014 Latencia del bot\n"
        f"\u2022 /about \u2014 Informaci\u00f3n del servicio\n\n"
        f"<b>Ejemplo:</b>\n"
        f"<code>/login TILINX-ABC123 192.168.1.100</code>\n\n"
        f"\U0001f4de Contacto: @tilinX_fast"
    )

def _cmd_help(chat_id: int, text: str, msg: dict) -> None:
    bot_send(chat_id,
        "<b>\U0001f4d6 Ayuda TilinX</b>\n\n"
        "<b>\U0001f511 /login KEY IP</b>\n"
        "Canjea tu key y activa tu IP.\n"
        "Ej: <code>/login TILINX-ABC123 192.168.1.100</code>\n\n"
        "<b>\U0001f4ca /stats</b>\n"
        "Muestra estad\u00edsticas del sistema.\n\n"
        "<b>\U0001f3d3 /ping</b>\n"
        "Comprueba la latencia del bot.\n\n"
        "<b>\u2139\ufe0f /about</b>\n"
        "Informaci\u00f3n del servicio.\n\n"
        "\u00bfProblemas? Contacta a @tilinX_fast"
    )

def _cmd_stats(chat_id: int, text: str, msg: dict) -> None:
    bot_send(chat_id, get_stats_text())

def _cmd_ping(chat_id: int, text: str, msg: dict) -> None:
    t1 = time.time()
    bot_req("getMe")
    t2 = time.time()
    ms = round((t2 - t1) * 1000)
    bot_send(chat_id, f"\U0001f3d3 <b>Pong!</b>\n\u23f1 Latencia: {ms}ms\n\U0001f7e2 Bot operativo")

def _cmd_about(chat_id: int, text: str, msg: dict) -> None:
    bot_send(chat_id,
        "<b>\u2139\ufe0f Sobre TilinX</b>\n\n"
        "Plataforma de proxy avanzado para gaming.\n"
        "\u2022 Cifrado SSL/TLS militar\n"
        "\u2022 Autenticaci\u00f3n por key de un solo uso\n"
        "\u2022 IP binding autom\u00e1tico\n"
        "\u2022 Latencia optimizada\n"
        "\u2022 Anti-detecci\u00f3n\n\n"
        "\U0001f6e1\ufe0f Versi\u00f3n 2.0\n"
        "\U0001f4de @tilinX_fast"
    )

def _cmd_clients(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    chat_data: dict = {}
    if os.path.exists(CHAT_IPS_PATH):
        chat_data = json.loads(open(CHAT_IPS_PATH, encoding="utf-8").read())
    db = load_db()
    keys_data = list_keys()
    keys_map = {k["code"]: k for k in keys_data}
    now = time.time()
    lines = ["<b>\U0001f4cb CLIENTES REGISTRADOS</b>\n"]
    for cid_str, ip in sorted(chat_data.items()):
        cid = int(cid_str)
        ip_info = db.get(ip, {})
        key_code = ip_info.get("key_used", "N/A")
        key_status = "N/A"
        key_label = ""
        if key_code != "N/A" and key_code in keys_map:
            k = keys_map[key_code]
            key_label = k.get("label", "")
            expires = k.get("created_at", 0) + k.get("duration", 0)
            if k.get("used") and expires > now:
                key_status = "\u2705 Activa"
            elif k.get("used") and expires <= now:
                key_status = "\u23f3 Expirada"
            elif not k.get("used"):
                key_status = "\U0001f195 Sin usar"
            else:
                key_status = "\u2753 Desconocido"
        used_at = ip_info.get("used_at", "")
        if used_at:
            used_at = time.strftime("%d/%m %H:%M", time.localtime(used_at if isinstance(used_at, (int, float)) else 0))
        lines.append(
            f"\U0001f464 <b>Chat</b>: <code>{cid}</code>\n"
            f"  \U0001f310 IP: <code>{ip}</code>\n"
            f"  \U0001f511 Key: <code>{key_code}</code> {key_label}\n"
            f"  \U0001f4cc Estado: {key_status}\n"
            f"  \U0001f550 Uso: {used_at}\n"
        )
    footer = f"\n<b>Total:</b> {len(chat_data)} cliente(s)"
    msg_text = "\n".join(lines) + footer if len(lines) > 1 else "<b>\U0001f4cb No hay clientes registrados a\u00fan.</b>"
    _send_split(chat_id, msg_text)

def _cmd_api(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, f"\U0001f6ab Comando solo para administradores. (TU ID: {chat_id})")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub in ("list", "ls"):
        db = load_db()
        keys_data = list_keys()
        keys_map = {k["code"]: k for k in keys_data}
        now = time.time()
        lines = ["<b>\U0001f4cb USUARIOS REGISTRADOS</b>\n"]
        for ip, info in sorted(db.items()):
            if ip == "_integrity":
                continue
            status = info.get("status", "?")
            exp = info.get("expires_at", 0)
            exp_str = "Permanente" if exp == 0 else time.strftime("%d/%m %H:%M", time.localtime(exp)) if exp > now else "Expirada"
            key_code = info.get("key_used", "N/A")
            lines.append(f"\U0001f310 <code>{ip}</code>\n  \U0001f511 {key_code}\n  \U0001f4cc {status} | \u23f1 {exp_str}\n")
        footer = f"\n<b>Total:</b> {len([k for k in db if k != '_integrity'])} IP(s)"
        msg_text = "\n".join(lines) + footer if len(lines) > 1 else "<b>\U0001f4cb No hay usuarios registrados.</b>"
        _send_split(chat_id, msg_text)
    elif sub == "remove" and len(parts) >= 3:
        ip = parts[2]
        db = load_db()
        if ip not in db:
            bot_send(chat_id, f"\u274c IP <code>{ip}</code> no encontrada.")
            return
        key_code = db[ip].get("key_used", "")
        if key_code and key_code.startswith("TILINX-"):
            remove_ip_from_key(key_code, ip)
        del db[ip]
        save_db(db)
        bot_send(chat_id, f"\u2705 IP <code>{ip}</code> eliminada y key removida.")
    elif sub == "extend" and len(parts) >= 4:
        ip = parts[2]
        try:
            days = float(parts[3])
        except ValueError:
            bot_send(chat_id, "\u26a0\ufe0f Los d\u00edas deben ser un n\u00famero.")
            return
        db = load_db()
        if ip not in db:
            bot_send(chat_id, f"\u274c IP <code>{ip}</code> no encontrada.")
            return
        key_code = db[ip].get("key_used", "")
        if key_code and key_code.startswith("TILINX-"):
            modify_key_duration(key_code, int(days * 86400))
        current_exp = db[ip].get("expires_at", 0)
        if current_exp != 0:
            db[ip]["expires_at"] = current_exp + (days * 86400)
        save_db(db)
        bot_send(chat_id, f"\u2705 IP <code>{ip}</code> extendida {days} d\u00eda(s).")
    elif sub == "reduce" and len(parts) >= 4:
        ip = parts[2]
        try:
            days = float(parts[3])
        except ValueError:
            bot_send(chat_id, "\u26a0\ufe0f Los d\u00edas deben ser un n\u00famero.")
            return
        db = load_db()
        if ip not in db:
            bot_send(chat_id, f"\u274c IP <code>{ip}</code> no encontrada.")
            return
        key_code = db[ip].get("key_used", "")
        if key_code and key_code.startswith("TILINX-"):
            modify_key_duration(key_code, -int(days * 86400))
        current_exp = db[ip].get("expires_at", 0)
        if current_exp != 0:
            db[ip]["expires_at"] = max(current_exp - (days * 86400), time.time())
        save_db(db)
        bot_send(chat_id, f"\u2705 IP <code>{ip}</code> reducida {days} d\u00eda(s).")
    elif sub == "block" and len(parts) >= 3:
        ip = parts[2]
        db = load_db()
        if ip not in db:
            bot_send(chat_id, f"\u274c IP <code>{ip}</code> no encontrada.")
            return
        db[ip]["status"] = "blocked"
        save_db(db)
        bot_send(chat_id, f"\u26d4 IP <code>{ip}</code> bloqueada.")
    elif sub == "unblock" and len(parts) >= 3:
        ip = parts[2]
        db = load_db()
        if ip not in db:
            bot_send(chat_id, f"\u274c IP <code>{ip}</code> no encontrada.")
            return
        db[ip]["status"] = "active"
        save_db(db)
        bot_send(chat_id, f"\u2705 IP <code>{ip}</code> desbloqueada.")
    else:
        bot_send(chat_id,
            "<b>\U0001f4cb /api \u2014 Gesti\u00f3n de usuarios</b>\n\n"
            "<code>/api list</code> \u2014 Ver todos los usuarios\n"
            "<code>/api remove IP</code> \u2014 Eliminar IP y su key\n"
            "<code>/api extend IP d\u00edas</code> \u2014 Extender tiempo\n"
            "<code>/api reduce IP d\u00edas</code> \u2014 Reducir tiempo\n"
            "<code>/api block IP</code> \u2014 Bloquear IP\n"
            "<code>/api unblock IP</code> \u2014 Desbloquear IP\n\n"
            "Ej: <code>/api extend 192.168.1.1 30</code>"
        )

def _cmd_adminx(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, f"\U0001f6ab Comando solo para administradores. (TU ID: {chat_id})")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "create" and len(parts) >= 3:
        username = parts[2]
        max_days = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else 30
        if max_days > 30:
            max_days = 30
        key, result = adminx_create(username, chat_id, max_days)
        if result == "OK":
            bot_send(chat_id,
                f"\u2705 <b>AdminX creado</b>\n\n"
                f"\U0001f464 Usuario: <code>{username}</code>\n"
                f"\U0001f511 Key: <code>{key}</code>\n"
                f"\U0001f4c6 Max d\u00edas: {max_days}\n\n"
                f"El usuario puede entrar en:\n"
                f"{PUBLIC_BASE_URL}/login\n"
                f"con ese usuario y key."
            )
        elif result == "USERNAME_EXISTS":
            bot_send(chat_id, f"\u274c El usuario <code>{username}</code> ya existe.")
    elif sub == "list":
        users = adminx_list()
        if not users:
            bot_send(chat_id, "<b>\U0001f4cb No hay usuarios AdminX.</b>")
            return
        lines = ["<b>\U0001f4cb ADMINX USERS</b>\n"]
        for uname, info in users:
            status = "\u2705" if info.get("active") else "\u274c"
            created = time.strftime("%d/%m %H:%M", time.localtime(info.get("created_at", 0)))
            lines.append(f"{status} <code>{uname}</code> | {info['key'][:16]}... | Max: {info['max_key_duration_days']}d | {created}")
        bot_send(chat_id, "\n".join(lines))
    elif sub == "remove" and len(parts) >= 3:
        username = parts[2]
        if adminx_remove(username):
            bot_send(chat_id, f"\u2705 AdminX <code>{username}</code> eliminado.")
        else:
            bot_send(chat_id, f"\u274c Usuario <code>{username}</code> no encontrado.")
    elif sub in ("activate", "enable") and len(parts) >= 3:
        username = parts[2]
        if adminx_set_active(username, True):
            bot_send(chat_id, f"\u2705 AdminX <code>{username}</code> activado.")
        else:
            bot_send(chat_id, f"\u274c Usuario <code>{username}</code> no encontrado.")
    elif sub in ("deactivate", "disable") and len(parts) >= 3:
        username = parts[2]
        if adminx_set_active(username, False):
            bot_send(chat_id, f"\u2705 AdminX <code>{username}</code> desactivado.")
        else:
            bot_send(chat_id, f"\u274c Usuario <code>{username}</code> no encontrado.")
    else:
        bot_send(chat_id,
            "<b>\U0001f916 /adminx \u2014 Gesti\u00f3n de AdminX</b>\n\n"
            "<code>/adminx create usuario [max_dias]</code>\n"
            "  Crear AdminX (max 30 d\u00edas)\n\n"
            "<code>/adminx list</code>\n"
            "  Listar todos los AdminX\n\n"
            "<code>/adminx remove usuario</code>\n"
            "  Eliminar AdminX\n\n"
            "<code>/adminx activate usuario</code>\n"
            "  Activar AdminX\n\n"
            "<code>/adminx deactivate usuario</code>\n"
            "  Desactivar AdminX\n"
        )

def _cmd_bulk(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "add" and len(parts) >= 3:
        ips = [p for p in parts[2:] if p.count(".") == 3]
        if not ips:
            bot_send(chat_id, "\u26a0\ufe0f Especifica al menos una IP.")
            return
        result = bulk_ops.bulk_add_ips(ips)
        bot_send(chat_id, f"\u2705 IPs a\u00f1adidas: {result['added']}\nOmitidas: {result['skipped']}")
    elif sub == "remove" and len(parts) >= 3:
        ips = [p for p in parts[2:] if p.count(".") == 3]
        if not ips:
            bot_send(chat_id, "\u26a0\ufe0f Especifica al menos una IP.")
            return
        result = bulk_ops.bulk_remove_ips(ips)
        bot_send(chat_id, f"\u2705 IPs eliminadas: {result['removed']}\nNo encontradas: {result['not_found']}")
    elif sub == "block" and len(parts) >= 3:
        ips = [p for p in parts[2:] if p.count(".") == 3]
        result = bulk_ops.bulk_set_status(ips, "blocked")
        bot_send(chat_id, f"\u26d4 IPs bloqueadas: {result['updated']}\nNo encontradas: {result['not_found']}")
    elif sub == "unblock" and len(parts) >= 3:
        ips = [p for p in parts[2:] if p.count(".") == 3]
        result = bulk_ops.bulk_set_status(ips, "active")
        bot_send(chat_id, f"\u2705 IPs desbloqueadas: {result['updated']}\nNo encontradas: {result['not_found']}")
    else:
        bot_send(chat_id,
            "<b>/bulk \u2014 Operaciones masivas</b>\n\n"
            "<code>/bulk add IP1 IP2 ...</code> \u2014 A\u00f1adir IPs\n"
            "<code>/bulk remove IP1 IP2 ...</code> \u2014 Eliminar IPs\n"
            "<code>/bulk block IP1 IP2 ...</code> \u2014 Bloquear IPs\n"
            "<code>/bulk unblock IP1 IP2 ...</code> \u2014 Desbloquear IPs\n\n"
            "Ej: <code>/bulk add 1.2.3.4 5.6.7.8</code>"
        )


def _cmd_csv(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "export-ips":
        csv_content = bulk_ops.export_ips_csv()
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "export_ips.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_content)
        bot_send(chat_id, f"\U0001f4e5 IPs exportadas a <code>{csv_path}</code>\n{len(csv_content.splitlines())-1} registros.")
    elif sub == "export-keys":
        csv_content = bulk_ops.export_keys_csv()
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "export_keys.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_content)
        bot_send(chat_id, f"\U0001f4e5 Keys exportadas a <code>{csv_path}</code>\n{len(csv_content.splitlines())-1} registros.")
    else:
        bot_send(chat_id,
            "<b>/csv \u2014 Exportar datos</b>\n\n"
            "<code>/csv export-ips</code> \u2014 Exportar IPs a CSV\n"
            "<code>/csv export-keys</code> \u2014 Exportar Keys a CSV\n"
        )


def _cmd_webhook(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "register" and len(parts) >= 3:
        url = parts[2]
        events = parts[3].split(",") if len(parts) >= 4 else []
        wid = webhooks.register(url, events if events else None)
        bot_send(chat_id, f"\u2705 Webhook registrado: <code>{wid}</code>\n{url}")
    elif sub == "remove" and len(parts) >= 3:
        wid = parts[2]
        if webhooks.remove(wid):
            bot_send(chat_id, f"\u2705 Webhook <code>{wid}</code> eliminado.")
        else:
            bot_send(chat_id, f"\u274c Webhook <code>{wid}</code> no encontrado.")
    elif sub == "list":
        whs = webhooks.list_webhooks()
        if not whs:
            bot_send(chat_id, "<b>No hay webhooks registrados.</b>")
            return
        lines = ["<b>\U0001f517 Webhooks registrados</b>\n"]
        for w in whs:
            status = "\u2705" if w.get("enabled") else "\u274c"
            failures = w.get("failure_count", 0)
            lines.append(f"{status} <code>{w['id']}</code>\n  URL: {w['url'][:60]}\n  Eventos: {len(w.get('events', []))} | Fallos: {failures}")
        bot_send(chat_id, "\n".join(lines))
    else:
        bot_send(chat_id,
            "<b>/webhook \u2014 Gesti\u00f3n de Webhooks</b>\n\n"
            "<code>/webhook register URL [events]</code>\n"
            "<code>/webhook remove ID</code>\n"
            "<code>/webhook list</code>\n\n"
            "Events: key.redeemed,ip.blocked,system.error,..."
        )


def _cmd_filter(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "blacklist" and len(parts) >= 3:
        action = parts[2].lower()
        pattern = " ".join(parts[3:]) if len(parts) > 3 else ""
        if action == "add" and pattern:
            filter_rules.add_url_blacklist(pattern)
            bot_send(chat_id, f"\u2705 Blacklist a\u00f1adido: <code>{pattern}</code>")
        elif action == "remove" and pattern:
            if filter_rules.remove_url_blacklist(pattern):
                bot_send(chat_id, f"\u2705 Blacklist quitado: <code>{pattern}</code>")
            else:
                bot_send(chat_id, f"\u274c Patr\u00f3n no encontrado.")
        elif action == "list":
            rules = filter_rules.get_rules()
            bl = rules.get("url_blacklist", [])
            msg_text = "<b>\u26d4 URL Blacklist</b>\n" + ("\n".join(f"  \u2022 <code>{p}</code>" for p in bl) if bl else "  (vac\u00edo)")
            bot_send(chat_id, msg_text)
    elif sub == "whitelist" and len(parts) >= 3:
        action = parts[2].lower()
        pattern = " ".join(parts[3:]) if len(parts) > 3 else ""
        if action == "add" and pattern:
            filter_rules.add_url_whitelist(pattern)
            bot_send(chat_id, f"\u2705 Whitelist a\u00f1adido: <code>{pattern}</code>")
        elif action == "remove" and pattern:
            if filter_rules.remove_url_whitelist(pattern):
                bot_send(chat_id, f"\u2705 Whitelist quitado: <code>{pattern}</code>")
            else:
                bot_send(chat_id, f"\u274c Patr\u00f3n no encontrado.")
        elif action == "list":
            rules = filter_rules.get_rules()
            wl = rules.get("url_whitelist", [])
            msg_text = "<b>\u2705 URL Whitelist</b>\n" + ("\n".join(f"  \u2022 <code>{p}</code>" for p in wl) if wl else "  (vac\u00edo)")
            bot_send(chat_id, msg_text)
    elif sub == "geoip" and len(parts) >= 3:
        action = parts[2].lower()
        code = parts[3].upper() if len(parts) > 3 else ""
        if action == "block" and code:
            filter_rules.add_geoip_blocked_country(code)
            bot_send(chat_id, f"\u2705 Pa\u00eds bloqueado: {code}")
        elif action == "unblock" and code:
            filter_rules.remove_geoip_blocked_country(code)
            bot_send(chat_id, f"\u2705 Pa\u00eds desbloqueado: {code}")
        elif action == "list":
            countries = filter_rules.get_geoip_blocked_countries()
            msg_text = "<b>\U0001f310 Pa\u00edses bloqueados por GeoIP</b>\n" + ("\n".join(f"  \u2022 {c}" for c in countries) if countries else "  (ninguno)")
            bot_send(chat_id, msg_text)
    elif sub == "header" and len(parts) >= 4:
        action = parts[2].lower()
        hdr = parts[3]
        val = " ".join(parts[4:]) if len(parts) > 4 else ""
        if action in ("set", "remove", "add"):
            filter_rules.add_header_rule(action, hdr, val)
            bot_send(chat_id, f"\u2705 Header rule {action} <code>{hdr}</code>")
    else:
        bot_send(chat_id,
            "<b>/filter \u2014 Reglas de filtrado</b>\n\n"
            "<code>/filter blacklist add PATRON</code>\n"
            "<code>/filter blacklist remove PATRON</code>\n"
            "<code>/filter blacklist list</code>\n"
            "<code>/filter whitelist add PATRON</code>\n"
            "<code>/filter whitelist remove PATRON</code>\n"
            "<code>/filter whitelist list</code>\n"
            "<code>/filter geoip block CODIGO</code>\n"
            "<code>/filter geoip unblock CODIGO</code>\n"
            "<code>/filter geoip list</code>\n"
            "<code>/filter header set/remove/add NOMBRE VALOR</code>\n\n"
            "Ej: <code>/filter blacklist add ads.example.com</code>"
        )


def _cmd_template(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "list":
        tmpls = config_templates.list_templates()
        lines = ["<b>\U0001f4cb Plantillas de configuraci\u00f3n</b>\n"]
        for t in tmpls:
            builtin = "\U0001f6e1\ufe0f" if t.get("builtin") else "\U0001f4c4"
            lines.append(f"{builtin} <code>{t['id']}</code> \u2014 {t.get('label', '')}")
        bot_send(chat_id, "\n".join(lines))
    elif sub == "show" and len(parts) >= 3:
        tmpl = config_templates.get_template(parts[2])
        if tmpl:
            lines = [f"<b>Plantilla: {tmpl['id']}</b>", f"{tmpl.get('description', '')}", ""]
            for k, v in tmpl.get("config", {}).items():
                lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False)[:60]}")
            bot_send(chat_id, "\n".join(lines))
        else:
            bot_send(chat_id, "\u274c Plantilla no encontrada.")
    else:
        bot_send(chat_id,
            "<b>/template \u2014 Plantillas de configuraci\u00f3n</b>\n\n"
            "<code>/template list</code> \u2014 Listar plantillas\n"
            "<code>/template show ID</code> \u2014 Mostrar plantilla\n\n"
            "Plantillas predefinidas: gaming_default, free_fire_optimized, maximum_security"
        )


def _cmd_task(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "list":
        tasks = scheduler.list_tasks()
        if not tasks:
            bot_send(chat_id, "<b>No hay tareas programadas.</b>")
            return
        lines = ["<b>\u23f0 Tareas programadas</b>\n"]
        for t in tasks:
            status = "\u2705" if t.get("enabled") else "\u274c"
            last = time.strftime("%H:%M", time.localtime(t.get("last_run", 0))) if t.get("last_run") else "Nunca"
            lines.append(f"{status} <code>{t['id']}</code>\n  Tipo: {t['type']} | Cada: {t['interval']}s | \u00daltima: {last}")
        bot_send(chat_id, "\n".join(lines))
    elif sub == "add" and len(parts) >= 4:
        task_type = parts[2]
        try:
            interval = int(parts[3])
        except ValueError:
            bot_send(chat_id, "\u26a0\ufe0f El intervalo debe ser un n\u00famero (segundos).")
            return
        tid = scheduler.register_task(task_type, interval)
        bot_send(chat_id, f"\u2705 Tarea creada: <code>{tid}</code> ({task_type} cada {interval}s)")
    elif sub == "remove" and len(parts) >= 3:
        tid = parts[2]
        if scheduler.remove_task(tid):
            bot_send(chat_id, f"\u2705 Tarea <code>{tid}</code> eliminada.")
        else:
            bot_send(chat_id, f"\u274c Tarea <code>{tid}</code> no encontrada.")
    elif sub == "start":
        scheduler.start_scheduler()
        bot_send(chat_id, "\u2705 Scheduler iniciado.")
    elif sub == "stop":
        scheduler.stop_scheduler()
        bot_send(chat_id, "\u23f9 Scheduler detenido.")
    else:
        bot_send(chat_id,
            "<b>/task \u2014 Tareas programadas</b>\n\n"
            "<code>/task list</code>\n<code>/task add TIPO INTERVALO_S</code>\n"
            "<code>/task remove ID</code>\n<code>/task start</code>\n<code>/task stop</code>\n\n"
            "Tipos: cleanup_expired, generate_report, create_backup, health_check"
        )


def _cmd_alert(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "list":
        configs = alerts.list_alert_configs()
        lines = ["<b>\U0001f514 Configuraci\u00f3n de alertas</b>\n"]
        for c in configs:
            status = "\u2705" if c.get("enabled") else "\u274c"
            lines.append(f"{status} <code>{c['id']}</code> {c['type']} (umbral: {c['threshold']}, cooldown: {c['cooldown']}s)")
        bot_send(chat_id, "\n".join(lines) if len(lines) > 1 else "<b>No hay configuraciones de alerta.</b>")
    elif sub == "recent":
        recent = alerts.get_recent(10)
        if not recent:
            bot_send(chat_id, "<b>No hay alertas recientes.</b>")
            return
        lines = ["<b>\U0001f514 Alertas recientes</b>\n"]
        for a in recent:
            ts = time.strftime("%H:%M:%S", time.localtime(a["timestamp"]))
            lines.append(f"[{ts}] <b>{a['type']}</b>: {a['message'][:80]}")
        bot_send(chat_id, "\n".join(lines))
    else:
        bot_send(chat_id,
            "<b>/alert \u2014 Sistema de alertas</b>\n\n"
            "<code>/alert list</code> \u2014 Ver configuraciones\n"
            "<code>/alert recent</code> \u2014 Ver alertas recientes\n"
        )


def _cmd_waf(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "status":
        stats = waf_module.get_stats()
        bot_send(chat_id, f"<b>\U0001f6e1 WAF Status</b>\n\nReglas: {stats['rules_count']}")
    elif sub == "mode" and len(parts) >= 3:
        mode = parts[2].lower()
        if mode in ("log", "block", "off"):
            waf_module.set_mode(mode)
            bot_send(chat_id, f"\u2705 WAF mode: {mode}")
        else:
            bot_send(chat_id, "\u274c Modos: log, block, off")
    elif sub == "threshold" and len(parts) >= 3:
        try:
            threshold = int(parts[2])
            waf_module.set_threshold(threshold)
            bot_send(chat_id, f"\u2705 WAF threshold: {threshold}")
        except ValueError:
            bot_send(chat_id, "\u274c Debe ser un n\u00famero (1-100)")
    else:
        bot_send(chat_id,
            "<b>/waf \u2014 Web Application Firewall</b>\n\n"
            "<code>/waf status</code> \u2014 Estado del WAF\n"
            "<code>/waf mode log|block|off</code> \u2014 Modo\n"
            "<code>/waf threshold NUM</code> \u2014 Umbral (1-100)\n\n"
            "Detecta: SQLi, XSS, Path Traversal, CMD Injection, Scanners"
        )


def _cmd_rlimit(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "reset" and len(parts) >= 3:
        ip = parts[2]
        rate_limiter.reset(ip)
        bot_send(chat_id, f"\u2705 Rate limit reset para {ip}")
    elif sub == "check" and len(parts) >= 3:
        ip = parts[2]
        allowed, info = rate_limiter.check(ip, "/check")
        bot_send(chat_id, f"<b>Rate Limit: {ip}</b>\n\nPermitido: {allowed}\nL\u00edmite: {info['limit']}\nUsados (60s): {info['count_60s']}\nScore adaptativo: {info['adaptive_score']}")
    else:
        bot_send(chat_id,
            "<b>/rlimit \u2014 Rate Limiter Inteligente</b>\n\n"
            "<code>/rlimit reset IP</code> \u2014 Resetear l\u00edmite\n"
            "<code>/rlimit check IP</code> \u2014 Verificar estado\n\n"
            "Adaptive: reduce l\u00edmite si detecta actividad sospechosa"
        )


def _cmd_jwt(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "create" and len(parts) >= 3:
        subject = parts[2]
        scopes = parts[3].split(",") if len(parts) > 3 else ["api"]
        pair = auth_jwt.create_token_pair(subject, scopes)
        if pair:
            bot_send(chat_id, f"<b>\u2705 JWT creado para {subject}</b>\n\nAccess: <code>{pair['access_token'][:60]}...</code>\nRefresh: <code>{pair['refresh_token'][:60]}...</code>\nExpires: {pair['expires_in']}s\nScope: {pair['scope']}")
        else:
            bot_send(chat_id, "\u274c Error creando token JWT")
    elif sub == "revoke" and len(parts) >= 3:
        count = auth_jwt.revoke_all_for_user(parts[2])
        bot_send(chat_id, f"\u2705 {count} tokens revocados para {parts[2]}")
    elif sub == "list":
        tokens = auth_jwt.list_active_refresh_tokens()
        if not tokens:
            bot_send(chat_id, "<b>No hay tokens activos.</b>")
            return
        lines = ["<b>\U0001f510 Tokens JWT activos</b>\n"]
        for t in tokens:
            lines.append(f"\U0001f464 {t.get('subject', '?')} | {t.get('jti', '?')[:16]}... | expires {time.strftime('%d/%m', time.localtime(t.get('expires', 0)))}")
        bot_send(chat_id, "\n".join(lines))
    else:
        bot_send(chat_id,
            "<b>/jwt \u2014 Gesti\u00f3n de tokens JWT</b>\n\n"
            "<code>/jwt create SUBJECT [scopes]</code>\n"
            "<code>/jwt revoke SUBJECT</code>\n"
            "<code>/jwt list</code>\n\n"
            "Scopes: api, admin, monitor, readonly"
        )


def _cmd_tfa(chat_id: int, text: str, msg: dict) -> None:
    if chat_id != ADMIN_ID:
        bot_send(chat_id, "\U0001f6ab Comando solo para administradores.")
        return
    parts = text.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if not twofa.is_available():
        bot_send(chat_id, "\u274c pyotp no instalado. Usa: pip install pyotp")
        return
    if sub == "setup":
        result = twofa.setup("admin")
        if result:
            codes = "\n".join(f"  <code>{c}</code>" for c in result.get("backup_codes", []))
            bot_send(chat_id, f"<b>\U0001f510 2FA Configurado</b>\n\nSecreto: <code>{result['secret']}</code>\n\n<b>Backup codes (guardalos):</b>\n{codes}\n\nEscane\u00e1 el QR en la web /admin/tfa")
        else:
            bot_send(chat_id, "\u274c Error configurando 2FA")
    elif sub == "disable":
        twofa.disable("admin")
        bot_send(chat_id, "\u2705 2FA desactivado")
    elif sub == "enable":
        twofa.enable("admin")
        bot_send(chat_id, "\u2705 2FA activado")
    elif sub == "status":
        status = twofa.get_status("admin")
        enabled_str = "\u2705 Activado" if status["enabled"] else "\u274c Desactivado"
        bot_send(chat_id, f"<b>\U0001f510 2FA Status</b>\n\nEstado: {enabled_str}")
    else:
        bot_send(chat_id,
            "<b>/2fa \u2014 Autenticaci\u00f3n de dos factores</b>\n\n"
            "<code>/2fa setup</code> \u2014 Configurar 2FA (TOTP)\n"
            "<code>/2fa enable</code> \u2014 Activar 2FA\n"
            "<code>/2fa disable</code> \u2014 Desactivar 2FA\n"
            "<code>/2fa status</code> \u2014 Ver estado\n\n"
            "Usa Google Authenticator o similar"
        )


def _cmd_login(chat_id: int, text: str, msg: dict) -> None:
    parts = text.split()
    code = parts[1] if len(parts) > 1 else ""
    if not code:
        bot_send(chat_id,
            "\u26a0\ufe0f <b>Uso incorrecto</b>\n\n"
            "<code>/login KEY</code> (IP autom\u00e1tica)\n"
            "<code>/login KEY IP</code> (IP manual)\n\n"
            "Ejemplo:\n"
            "<code>/login TILINX-ABC123</code>"
        )
        return
    if len(parts) >= 3:
        ip = parts[2]
        if not is_valid_ip(ip):
            bot_send(chat_id, "\u26a0\ufe0f Direcci\u00f3n IP inv\u00e1lida.\nEjemplo: 192.168.1.100")
            return
        set_chat_ip(chat_id, ip)
        result = redeem_key(code, ip)
        msgs = {
            "OK": f"\u2705 <b>IP Activada!</b>\n\n\U0001f310 IP: <code>{ip}</code> (guardada)\n\U0001f511 Key: <code>{code}</code>\n\nTu proxy est\u00e1 listo. Disfruta.",
            "INVALID": "\u274c Key inv\u00e1lida. Verifica el c\u00f3digo e intenta de nuevo.",
            "ALREADY_USED": "\u23f3 Esta key ya fue usada anteriormente.",
        }
        bot_send(chat_id, msgs.get(result, "\u274c Error al procesar la key."))
        log.info(f"Redeem: {code} -> {ip} = {result}")
    else:
        stored_ip = get_chat_ip(chat_id)
        if stored_ip:
            result = redeem_key(code, stored_ip)
            if result == "OK":
                bot_send(chat_id,
                    f"\u2705 <b>IP Autom\u00e1tica!</b>\n\n"
                    f"\U0001f310 IP detectada: <code>{stored_ip}</code>\n"
                    f"\U0001f511 Key: <code>{code}</code>\n\n"
                    f"Tu proxy est\u00e1 listo. Disfruta."
                )
                log.info(f"Redeem (auto): {code} -> {stored_ip} = OK (chat {chat_id})")
            else:
                msgs = {
                    "INVALID": "\u274c Key inv\u00e1lida. Verifica el c\u00f3digo e intenta de nuevo.",
                    "ALREADY_USED": "\u23f3 Esta key ya fue usada anteriormente.",
                }
                bot_send(chat_id, msgs.get(result, "\u274c Error al procesar la key."))
        else:
            token = generate_verify_token(chat_id, code)
            verify_url = f"{PUBLIC_BASE_URL}/tg-verify/{chat_id}/{token}"
            bot_send(chat_id,
                f"\U0001f517 <b>Verific\u00e1 tu IP</b>\n\n"
                f"Hac\u00e9 clic en el enlace para detectar tu IP autom\u00e1ticamente:\n"
                f"{verify_url}\n\n"
                f"\u23f1 V\u00e1lido por 5 minutos\n\n"
                f"O us\u00e1:\n"
                f"<code>/login {parts[1]} TU_IP</code>"
            )

def _cmd_unknown(chat_id: int, text: str, msg: dict) -> None:
    bot_send(chat_id,
        f"\u26a0\ufe0f Comando no reconocido.\n"
        f"Us\u00e1 /help para ver los comandos disponibles."
    )

# ─── Command Registry ──────────────────────────────────

COMMANDS: Dict[str, HandlerFn] = {
    "/start": _cmd_start,
    "/help": _cmd_help,
    "/stats": _cmd_stats,
    "/ping": _cmd_ping,
    "/about": _cmd_about,
}

PREFIX_COMMANDS: Dict[str, HandlerFn] = {
    "/api": _cmd_api,
    "/adminx": _cmd_adminx,
    "/login": _cmd_login,
    "/redeem": _cmd_login,
    "/bulk": _cmd_bulk,
    "/csv": _cmd_csv,
    "/webhook": _cmd_webhook,
    "/filter": _cmd_filter,
    "/template": _cmd_template,
    "/task": _cmd_task,
    "/alert": _cmd_alert,
    "/waf": _cmd_waf,
    "/rlimit": _cmd_rlimit,
    "/jwt": _cmd_jwt,
    "/2fa": _cmd_tfa,
    "/tfa": _cmd_tfa,
}

EXACT_COMMANDS: Dict[str, HandlerFn] = {
    "/clients": _cmd_clients,
    "/users": _cmd_clients,
    "/ips": _cmd_clients,
}

def _dispatch(chat_id: int, text: str, msg: dict) -> None:
    handler = COMMANDS.get(text)
    if handler:
        handler(chat_id, text, msg)
        return
    handler = EXACT_COMMANDS.get(text)
    if handler:
        handler(chat_id, text, msg)
        return
    for prefix, handler in PREFIX_COMMANDS.items():
        if text.startswith(prefix):
            handler(chat_id, text, msg)
            return
    _cmd_unknown(chat_id, text, msg)

# ─── Polling Loop ───────────────────────────────────────

def bot_poll() -> None:
    global BOT_RUNNING, LAST_UPDATE, ERROR_COUNT
    if not BOT_TOKEN or not requests:
        log.warning("TilinX_BOT_TOKEN no configurado, bot desactivado")
        BOT_RUNNING = False
        return
    offset = 0
    BOT_RUNNING = True
    log.info("[Bot] TilinX iniciado (polling HTTP)")
    while BOT_RUNNING:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            if r.status_code != 200:
                error_msg = r.json().get("description", "unknown") if r.headers.get("content-type", "").startswith("application/json") else str(r.status_code)
                log.error(f"Bot API error: {error_msg}")
                ERROR_COUNT += 1
                if ERROR_COUNT > 10:
                    log.warning("Bot: demasiados errores, reiniciando offset...")
                    offset = 0
                    ERROR_COUNT = 0
                time.sleep(2)
                continue
            ERROR_COUNT = 0
            data = r.json()
            if not data.get("ok"):
                time.sleep(2)
                continue
            for up in data.get("result", []):
                offset = up["update_id"] + 1
                msg = up.get("message") or up.get("edited_message")
                if not msg or not msg.get("text"):
                    continue
                chat_id = msg["chat"]["id"]
                text = msg["text"].strip()
                with CHAT_RATE_LOCK:
                    now = time.time()
                    last = CHAT_RATE.get(chat_id, 0)
                    if now - last < COMMAND_COOLDOWN:
                        continue
                    CHAT_RATE[chat_id] = now
                if not text.startswith("/"):
                    continue
                LAST_UPDATE = time.time()
                _dispatch(chat_id, text, msg)
        except Exception as e:
            log.error(f"Error en polling del bot: {e}")
            ERROR_COUNT += 1
            time.sleep(2)

def _clean_rates_loop() -> None:
    while True:
        time.sleep(300)
        with CHAT_RATE_LOCK:
            now = time.time()
            expired = [cid for cid, ts in CHAT_RATE.items() if now - ts > 3600]
            for cid in expired:
                del CHAT_RATE[cid]

# ─── Lifecycle ─────────────────────────────────────────

def start_bot() -> None:
    if not BOT_TOKEN or not requests:
        log.warning("Bot no disponible: BOT_TOKEN o requests faltante")
        return
    if BOT_RUNNING:
        log.info("Bot ya est\u00e1 corriendo")
        return
    scheduler.start_scheduler()
    t = threading.Thread(target=bot_poll, daemon=True)
    t.start()
    _BOT_THREADS.append(t)
    tc = threading.Thread(target=_clean_rates_loop, daemon=True)
    tc.start()
    _BOT_THREADS.append(tc)
    log.info("Bot thread iniciado")

def stop_bot() -> None:
    global BOT_RUNNING
    BOT_RUNNING = False
    log.info("Bot detenido")

def get_bot_status() -> Dict[str, Any]:
    return {
        "running": BOT_RUNNING,
        "token_set": bool(BOT_TOKEN),
        "requests_available": requests is not None,
        "uptime": round(time.time() - START_TIME),
        "last_update": LAST_UPDATE,
        "errors": ERROR_COUNT,
    }

def _signal_handler(signum: int, frame) -> None:
    log.info(f"Se\u00f1al {signum} recibida, deteniendo bot...")
    stop_bot()

signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)

if __name__ == "__main__":
    start_bot()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        stop_bot()
