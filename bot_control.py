import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN
from logger import log
from keys import redeem_key

IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

def is_valid_ip(text: str) -> bool:
    if not IP_RE.match(text):
        return False
    parts = text.split(".")
    return all(0 <= int(p) <= 255 for p in parts)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>⚡ TilinX</b>\n\n"
        "To activate your IP:\n"
        "<code>/redeem KEY_HERE YOUR_IP</code>\n\n"
        "Example:\n"
        "<code>/redeem TILINX-ABC123 192.168.1.100</code>",
        parse_mode=ParseMode.HTML,
    )

async def cmd_redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /redeem <KEY> <IP>\nExample: /redeem TILINX-ABC123 192.168.1.100")
        return
    code = context.args[0]
    ip = context.args[1]
    if not is_valid_ip(ip):
        await update.message.reply_text("⚠️ Invalid IP address.")
        return
    result = redeem_key(code, ip)
    msgs = {
        "OK": f"✅ <b>IP Registered!</b>\n🌐 <code>{ip}</code>\n🔑 Key activated.",
        "INVALID": "❌ Invalid key.",
        "ALREADY_USED": "⏳ This key has already been used.",
    }
    await update.message.reply_text(msgs.get(result, "❌ Error."), parse_mode=ParseMode.HTML)

def start_bot():
    if not BOT_TOKEN:
        log.warning("TilinX_BOT_TOKEN not set, bot disabled")
        return
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app = Application.builder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("redeem", cmd_redeem))
        app.add_handler(MessageHandler(filters.TEXT, cmd_start))
        log.info("🚀 TilinX Bot starting (registration only)...")
        print("🚀 TilinX Bot running (registration only)...")
        app.run_polling(drop_pending_updates=True)
    except Exception as e:
        log.error(f"Bot error: {e}")

if __name__ == "__main__":
    start_bot()
