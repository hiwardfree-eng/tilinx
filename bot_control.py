import sys, os, re, time, json, threading, secrets
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import BOT_TOKEN, CHAT_IPS_PATH, ADMIN_ID
from logger import log
from keys import redeem_key, list_keys
from database import load as load_db

try:
    import requests
except ImportError:
    requests = None

IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
CHAT_IP_LOCK = threading.Lock()
CHAT_RATE_LOCK = threading.Lock()
CHAT_RATE = {}
COMMAND_COOLDOWN = 1.0  # seconds between commands per chat

def get_chat_ip(chat_id):
    if not os.path.exists(CHAT_IPS_PATH):
        return None
    try:
        with open(CHAT_IPS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(str(chat_id))
    except:
        return None

def set_chat_ip(chat_id, ip):
    with CHAT_IP_LOCK:
        data = {}
        if os.path.exists(CHAT_IPS_PATH):
            try:
                with open(CHAT_IPS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except:
                data = {}
        data[str(chat_id)] = ip
        with open(CHAT_IPS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

def generate_verify_token(chat_id, code):
    token = secrets.token_hex(8)
    verify_path = CHAT_IPS_PATH.replace(".json", "_pending.json")
    data = {}
    if os.path.exists(verify_path):
        try:
            with open(verify_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data[token] = {"chat_id": chat_id, "code": code, "time": time.time()}
    with open(verify_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return token

def consume_verify_token(token, ip):
    verify_path = CHAT_IPS_PATH.replace(".json", "_pending.json")
    if not os.path.exists(verify_path):
        return None
    try:
        with open(verify_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    entry = data.pop(token, None)
    if not entry:
        return None
    if time.time() - entry["time"] > 300:
        with open(verify_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return None
    with open(verify_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    chat_id = entry["chat_id"]
    code = entry["code"]
    set_chat_ip(chat_id, ip)
    result = redeem_key(code, ip)
    return {"chat_id": chat_id, "code": code, "ip": ip, "result": result}
START_TIME = time.time()
BOT_RUNNING = False
LAST_UPDATE = 0
ERROR_COUNT = 0

def is_valid_ip(text):
    if not IP_RE.match(text):
        return False
    parts = text.split(".")
    return all(0 <= int(p) <= 255 for p in parts)

def bot_req(method, **kwargs):
    if not requests or not BOT_TOKEN:
        return None
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
            params=kwargs,
            timeout=15,
        )
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        log.error(f"Telegram API error ({method}): {e}")
        return None

def bot_send(chat_id, text, parse_mode="HTML"):
    global LAST_UPDATE
    if not requests or not BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        LAST_UPDATE = time.time()
    except Exception as e:
        log.error(f"sendMessage error: {e}")

def get_stats_text():
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
            f"<b>📊 TilinX — Estadísticas</b>\n\n"
            f"🔑 Keys totales: {total}\n"
            f"✅ Keys activas: {active}\n"
            f"❌ Keys usadas: {used}\n"
            f"👥 IPs activas: {active_ips}\n"
            f"⏱ Uptime bot: {uptime_str}\n"
            f"🟢 Estado: OPERATIVO"
        )
    except Exception as e:
        return f"<b>📊 Estadísticas</b>\n\nError al obtener datos: {e}"

def bot_poll():
    global BOT_RUNNING, LAST_UPDATE, ERROR_COUNT
    if not BOT_TOKEN or not requests:
        log.warning("TilinX_BOT_TOKEN no configurado, bot desactivado")
        BOT_RUNNING = False
        return
    offset = 0
    BOT_RUNNING = True
    log.info("🤖 Bot TilinX iniciado (polling HTTP)")
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

                # Rate limiting per chat
                with CHAT_RATE_LOCK:
                    now = time.time()
                    last = CHAT_RATE.get(chat_id, 0)
                    if now - last < COMMAND_COOLDOWN:
                        continue
                    CHAT_RATE[chat_id] = now

                # Block non-command messages
                if not text.startswith("/"):
                    continue

                first = msg["chat"]["first_name"] or ""
                LAST_UPDATE = time.time()

                if text == "/start":
                    bot_send(chat_id,
                        f"<b>⚡ Bienvenido a TilinX, {first}!</b>\n\n"
                        f"Sistema de protección y aceleración para juegos.\n\n"
                        f"<b>Comandos disponibles:</b>\n"
                        f"• /login KEY IP — Activar tu IP con una key\n"
                        f"• /help — Ayuda detallada\n"
                        f"• /stats — Estadísticas del sistema\n"
                        f"• /ping — Latencia del bot\n"
                        f"• /about — Información del servicio\n\n"
                        f"<b>Ejemplo:</b>\n"
                        f"<code>/login TILINX-ABC123 192.168.1.100</code>\n\n"
                        f"📞 Contacto: @tilinX_fast"
                    )

                elif text == "/help":
                    bot_send(chat_id,
                        "<b>📖 Ayuda TilinX</b>\n\n"
                        "<b>🔑 /login KEY IP</b>\n"
                        "Canjea tu key y activa tu IP.\n"
                        "Ej: <code>/login TILINX-ABC123 192.168.1.100</code>\n\n"
                        "<b>📊 /stats</b>\n"
                        "Muestra estadísticas del sistema.\n\n"
                        "<b>🏓 /ping</b>\n"
                        "Comprueba la latencia del bot.\n\n"
                        "<b>ℹ️ /about</b>\n"
                        "Información del servicio.\n\n"
                        "¿Problemas? Contacta a @tilinX_fast"
                    )

                elif text == "/stats":
                    bot_send(chat_id, get_stats_text())

                elif text == "/ping":
                    t1 = time.time()
                    bot_req("getMe")
                    t2 = time.time()
                    ms = round((t2 - t1) * 1000)
                    bot_send(chat_id, f"🏓 <b>Pong!</b>\n⏱ Latencia: {ms}ms\n🟢 Bot operativo")

                elif text == "/about":
                    bot_send(chat_id,
                        "<b>ℹ️ Sobre TilinX</b>\n\n"
                        "Plataforma de proxy avanzado para gaming.\n"
                        "• Cifrado SSL/TLS militar\n"
                        "• Autenticación por key de un solo uso\n"
                        "• IP binding automático\n"
                        "• Latencia optimizada\n"
                        "• Anti-detección\n\n"
                        "🛡️ Versión 2.0\n"
                        "📞 @tilinX_fast"
                    )

                elif text == "/clients" or text == "/users" or text == "/ips":
                    if chat_id != ADMIN_ID:
                        bot_send(chat_id, "🚫 Comando solo para administradores.")
                        continue
                    # Load all data
                    chat_data = {}
                    if os.path.exists(CHAT_IPS_PATH):
                        chat_data = json.loads(open(CHAT_IPS_PATH, encoding="utf-8").read())
                    db = load_db()
                    keys_data = list_keys()
                    keys_map = {k["code"]: k for k in keys_data}
                    now = time.time()
                    lines = []
                    lines.append("<b>📋 CLIENTES REGISTRADOS</b>\n")
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
                                key_status = "✅ Activa"
                            elif k.get("used") and expires <= now:
                                key_status = "⏳ Expirada"
                            elif not k.get("used"):
                                key_status = "🆕 Sin usar"
                            else:
                                key_status = "❓ Desconocido"
                        used_at = ip_info.get("used_at", "")
                        if used_at:
                            used_at = time.strftime("%d/%m %H:%M", time.localtime(used_at if isinstance(used_at, (int, float)) else 0))
                        lines.append(
                            f"👤 <b>Chat</b>: <code>{cid}</code>\n"
                            f"  🌐 IP: <code>{ip}</code>\n"
                            f"  🔑 Key: <code>{key_code}</code> {key_label}\n"
                            f"  📌 Estado: {key_status}\n"
                            f"  🕐 Uso: {used_at}\n"
                        )
                    footer = f"\n<b>Total:</b> {len(chat_data)} cliente(s)"
                    if len(lines) > 1:
                        msg = "\n".join(lines) + footer
                    else:
                        msg = "<b>📋 No hay clientes registrados aún.</b>"
                    # Telegram max msg length ~4096; split if needed
                    while len(msg) > 4000:
                        idx = msg.rfind("\n", 0, 4000)
                        if idx < 0:
                            idx = 4000
                        bot_send(chat_id, msg[:idx])
                        msg = msg[idx:]
                    bot_send(chat_id, msg)

                elif text.startswith("/redeem") or text.startswith("/login"):
                    parts = text.split()
                    code = parts[1] if len(parts) > 1 else ""
                    if not code:
                        bot_send(chat_id,
                            "⚠️ <b>Uso incorrecto</b>\n\n"
                            "<code>/login KEY</code> (IP automática)\n"
                            "<code>/login KEY IP</code> (IP manual)\n\n"
                            "Ejemplo:\n"
                            "<code>/login TILINX-ABC123</code>"
                        )
                        continue
                    if len(parts) >= 3:
                        ip = parts[2]
                        if not is_valid_ip(ip):
                            bot_send(chat_id, "⚠️ Dirección IP inválida.\nEjemplo: 192.168.1.100")
                            continue
                        set_chat_ip(chat_id, ip)
                        result = redeem_key(code, ip)
                        msgs = {
                            "OK": (
                                f"✅ <b>IP Activada!</b>\n\n"
                                f"🌐 IP: <code>{ip}</code> (guardada)\n"
                                f"🔑 Key: <code>{code}</code>\n\n"
                                f"Tu proxy está listo. Disfruta."
                            ),
                            "INVALID": "❌ Key inválida. Verifica el código e intenta de nuevo.",
                            "ALREADY_USED": "⏳ Esta key ya fue usada anteriormente.",
                        }
                        bot_send(chat_id, msgs.get(result, "❌ Error al procesar la key."))
                        log.info(f"Redeem: {code} -> {ip} = {result}")
                    else:
                        stored_ip = get_chat_ip(chat_id)
                        if stored_ip:
                            result = redeem_key(code, stored_ip)
                            if result == "OK":
                                bot_send(chat_id,
                                    f"✅ <b>IP Automática!</b>\n\n"
                                    f"🌐 IP detectada: <code>{stored_ip}</code>\n"
                                    f"🔑 Key: <code>{code}</code>\n\n"
                                    f"Tu proxy está listo. Disfruta."
                                )
                                log.info(f"Redeem (auto): {code} -> {stored_ip} = OK (chat {chat_id})")
                            else:
                                msgs = {
                                    "INVALID": "❌ Key inválida. Verifica el código e intenta de nuevo.",
                                    "ALREADY_USED": "⏳ Esta key ya fue usada anteriormente.",
                                }
                                bot_send(chat_id, msgs.get(result, "❌ Error al procesar la key."))
                        else:
                            token = generate_verify_token(chat_id, code)
                            verify_url = f"https://tilinx.onrender.com/tg-verify/{chat_id}/{token}"
                            bot_send(chat_id,
                                f"🔗 <b>Verificá tu IP</b>\n\n"
                                f"Hacé clic en el enlace para detectar tu IP automáticamente:\n"
                                f"{verify_url}\n\n"
                                f"⏱ Válido por 5 minutos\n\n"
                                f"O usá:\n"
                                f"<code>/login {parts[1]} TU_IP</code>"
                            )

                elif text.startswith("/"):
                    bot_send(chat_id,
                        f"⚠️ Comando no reconocido.\n"
                        f"Usá /help para ver los comandos disponibles."
                    )

        except Exception as e:
            log.error(f"Error en polling del bot: {e}")
            ERROR_COUNT += 1
            time.sleep(2)

def start_bot():
    if not BOT_TOKEN or not requests:
        log.warning("Bot no disponible: BOT_TOKEN o requests faltante")
        return
    if BOT_RUNNING:
        log.info("Bot ya está corriendo")
        return
    t = threading.Thread(target=bot_poll, daemon=True)
    t.start()
    # Rate cleaner thread
    def clean_rates():
        while True:
            time.sleep(300)
            with CHAT_RATE_LOCK:
                now = time.time()
                expired = [cid for cid, ts in CHAT_RATE.items() if now - ts > 3600]
                for cid in expired:
                    del CHAT_RATE[cid]
    tc = threading.Thread(target=clean_rates, daemon=True)
    tc.start()
    log.info("Bot thread iniciado")

def stop_bot():
    global BOT_RUNNING
    BOT_RUNNING = False
    log.info("Bot detenido")

def get_bot_status():
    return {
        "running": BOT_RUNNING,
        "token_set": bool(BOT_TOKEN),
        "requests_available": requests is not None,
        "uptime": round(time.time() - START_TIME),
        "last_update": LAST_UPDATE,
        "errors": ERROR_COUNT,
    }

if __name__ == "__main__":
    start_bot()
    while True:
        time.sleep(60)
