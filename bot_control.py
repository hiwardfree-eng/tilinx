import sys, os, re, time, json, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import BOT_TOKEN
from logger import log
from keys import redeem_key

try:
    import requests
except ImportError:
    requests = None

IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

def is_valid_ip(text):
    if not IP_RE.match(text):
        return False
    parts = text.split(".")
    return all(0 <= int(p) <= 255 for p in parts)

def bot_send(chat_id, text, parse_mode="HTML"):
    if not requests:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
    except Exception:
        pass

def bot_poll():
    if not BOT_TOKEN or not requests:
        log.warning("TilinX_BOT_TOKEN not set or requests not available, bot disabled")
        return
    offset = 0
    log.info("Bot polling started (HTTP mode)")
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=35,
            )
            if r.status_code != 200:
                time.sleep(5)
                continue
            data = r.json()
            if not data.get("ok"):
                time.sleep(5)
                continue
            for up in data.get("result", []):
                offset = up["update_id"] + 1
                msg = up.get("message") or up.get("edited_message")
                if not msg:
                    continue
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "").strip()
                if text == "/start":
                    bot_send(chat_id,
                        "<b>⚡ TilinX</b>\n\n"
                        "To activate your IP:\n"
                        "<code>/redeem KEY_HERE YOUR_IP</code>\n\n"
                        "Example:\n"
                        "<code>/redeem TILINX-ABC123 192.168.1.100</code>"
                    )
                elif text.startswith("/redeem"):
                    parts = text.split()
                    if len(parts) < 3:
                        bot_send(chat_id, "Usage: /redeem <KEY> <IP>\nExample: /redeem TILINX-ABC123 192.168.1.100")
                        continue
                    code = parts[1]
                    ip = parts[2]
                    if not is_valid_ip(ip):
                        bot_send(chat_id, "⚠️ Invalid IP address.")
                        continue
                    result = redeem_key(code, ip)
                    msgs = {
                        "OK": f"✅ <b>IP Registered!</b>\n🌐 <code>{ip}</code>\n🔑 Key activated.",
                        "INVALID": "❌ Invalid key.",
                        "ALREADY_USED": "⏳ This key has already been used.",
                    }
                    bot_send(chat_id, msgs.get(result, "❌ Error."))
                else:
                    bot_send(chat_id,
                        "<b>⚡ TilinX</b>\n\n"
                        "To activate your IP:\n"
                        "<code>/redeem KEY_HERE YOUR_IP</code>\n\n"
                        "Example:\n"
                        "<code>/redeem TILINX-ABC123 192.168.1.100</code>"
                    )
        except Exception as e:
            log.error(f"Bot poll error: {e}")
            time.sleep(5)

def start_bot():
    t = threading.Thread(target=bot_poll, daemon=True)
    t.start()

if __name__ == "__main__":
    start_bot()
    while True:
        time.sleep(60)
