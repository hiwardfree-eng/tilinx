import sys, os, re, time, json, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import BOT_TOKEN
from logger import log
from keys import redeem_key, list_keys
from database import load as load_db

try:
    import requests
except ImportError:
    requests = None

IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
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
                first = msg["chat"]["first_name"] or ""
                LAST_UPDATE = time.time()

                if text == "/start":
                    bot_send(chat_id,
                        f"<b>⚡ Bienvenido a TilinX, {first}!</b>\n\n"
                        f"Sistema de protección y aceleración para juegos.\n\n"
                        f"<b>Comandos disponibles:</b>\n"
                        f"• /redeem KEY IP — Activar tu IP con una key\n"
                        f"• /help — Ayuda detallada\n"
                        f"• /stats — Estadísticas del sistema\n"
                        f"• /ping — Latencia del bot\n"
                        f"• /about — Información del servicio\n\n"
                        f"<b>Ejemplo:</b>\n"
                        f"<code>/redeem TILINX-ABC123 192.168.1.100</code>\n\n"
                        f"📞 Contacto: @tilinX_fast"
                    )

                elif text == "/help":
                    bot_send(chat_id,
                        "<b>📖 Ayuda TilinX</b>\n\n"
                        "<b>🔑 /redeem KEY IP</b>\n"
                        "Canjea tu key y activa tu IP.\n"
                        "Ej: <code>/redeem TILINX-ABC123 192.168.1.100</code>\n\n"
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

                elif text.startswith("/redeem"):
                    parts = text.split()
                    if len(parts) < 3:
                        bot_send(chat_id,
                            "⚠️ <b>Uso incorrecto</b>\n\n"
                            "<code>/redeem KEY IP</code>\n\n"
                            "Ejemplo:\n"
                            "<code>/redeem TILINX-ABC123 192.168.1.100</code>"
                        )
                        continue
                    code = parts[1]
                    ip = parts[2]
                    if not is_valid_ip(ip):
                        bot_send(chat_id, "⚠️ Dirección IP inválida.\nEjemplo: 192.168.1.100")
                        continue
                    result = redeem_key(code, ip)
                    msgs = {
                        "OK": (
                            f"✅ <b>IP Activada!</b>\n\n"
                            f"🌐 IP: <code>{ip}</code>\n"
                            f"🔑 Key: <code>{code}</code>\n\n"
                            f"Tu proxy está listo. Disfruta."
                        ),
                        "INVALID": "❌ Key inválida. Verifica el código e intenta de nuevo.",
                        "ALREADY_USED": "⏳ Esta key ya fue usada anteriormente.",
                    }
                    bot_send(chat_id, msgs.get(result, "❌ Error al procesar la key."))
                    log.info(f"Redeem: {code} -> {ip} = {result}")

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
