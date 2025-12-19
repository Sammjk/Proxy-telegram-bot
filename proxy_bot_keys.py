import os
import sqlite3
import aiohttp
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# =====================
# CONFIGURACIÓN
# =====================

BOT_TOKEN = os.getenv(7984754462:AAESm-FWCNkQQkjqZ1xL8qzdWLiTsKwW0kY)
ADMIN_ID = 7178424080
DB_FILE = "bot.db"

MAX_PROXIES = 10
REQUEST_TIMEOUT = 15

PROXY_URLS = {
    "http": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&country={country}",
    "socks4": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks4&country={country}",
    "socks5": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&country={country}",
}

# =====================
# BASE DE DATOS
# =====================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS keys (code TEXT PRIMARY KEY, days INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expires_at TEXT)")
    conn.commit()
    conn.close()

# =====================
# UTILIDADES
# =====================

def has_access(user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT expires_at FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row: return False
    # Corrección para v20: usar timezone.utc
    return datetime.fromisoformat(row[0]).replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)

# =====================
# COMANDOS
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Live Proxy Checker*\n\n/redeem <key>\n/myaccess\n/proxy <tipo> [PAIS]",
        parse_mode="Markdown"
    )

async def myaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = "✅ Activo" if has_access(update.effective_user.id) else "❌ No activo"
    await update.message.reply_text(f"Tu acceso está: {status}")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /redeem <key>")
        return
    
    code = context.args[0]
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT days FROM keys WHERE code = ?", (code,))
    row = c.fetchone()

    if not row:
        await update.message.reply_text("❌ Key inválida.")
        conn.close()
        return

    days = row[0]
    expires = datetime.now(timezone.utc) + timedelta(days=days)
    c.execute("REPLACE INTO users (user_id, expires_at) VALUES (?, ?)", (update.effective_user.id, expires.isoformat()))
    c.execute("DELETE FROM keys WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Acceso activado por {days} días.")

async def proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access(update.effective_user.id):
        await update.message.reply_text("❌ Sin acceso.")
        return

    if not context.args:
        await update.message.reply_text("Uso: /proxy <http|socks4|socks5> [PAIS]")
        return

    p_type = context.args[0].lower()
    country = context.args[1].upper() if len(context.args) > 1 else "ALL"
    
    if p_type not in PROXY_URLS:
        await update.message.reply_text("❌ Tipo inválido.")
        return

    url = PROXY_URLS[p_type].format(country=country)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=REQUEST_TIMEOUT) as r:
                text = await r.text()
    except:
        await update.message.reply_text("❌ Error de conexión.")
        return

    proxies = [p for p in text.splitlines() if ":" in p][:MAX_PROXIES]
    if not proxies:
        await update.message.reply_text("❌ No hay proxies.")
        return

    await update.message.reply_text(f"🌍 *{p_type.upper()}* ({country})\n\n" + "\n".join(proxies), parse_mode="Markdown")

# =====================
# MAIN
# =====================

def main():
    init_db()
    # Esta es la forma correcta para python-telegram-bot v20+
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("myaccess", myaccess))
    app.add_handler(CommandHandler("proxy", proxy))

    print("Bot corriendo...")
    app.run_polling()

if __name__ == "__main__":
    main()
    
