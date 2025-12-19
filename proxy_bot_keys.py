import os
import sqlite3
import aiohttp
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# =====================
# CONFIGURACIÓN
# =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")  # VARIABLE DE ENTORNO EN RENDER
ADMIN_ID = 7178424080               # TU ID
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

    c.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            code TEXT PRIMARY KEY,
            days INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            expires_at TEXT
        )
    """)

    conn.commit()
    conn.close()

# =====================
# UTILIDADES
# =====================

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def has_access(user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT expires_at FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return False

    return datetime.fromisoformat(row[0]) > datetime.utcnow()

# =====================
# COMANDOS
# =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Live Proxy Checker Bot*\n\n"
        "/redeem <key>\n"
        "/myaccess\n"
        "/proxy <http|socks4|socks5> [PAIS]",
        parse_mode="Markdown"
    )


async def myaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access(update.effective_user.id):
        await update.message.reply_text("❌ No tienes acceso activo.")
        return

    await update.message.reply_text("✅ Tienes acceso activo.")


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
    expires = datetime.utcnow() + timedelta(days=days)

    c.execute(
        "REPLACE INTO users (user_id, expires_at) VALUES (?, ?)",
        (update.effective_user.id, expires.isoformat())
    )
    c.execute("DELETE FROM keys WHERE code = ?", (code,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Acceso activado por {days} días.")


async def proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access(update.effective_user.id):
        await update.message.reply_text("❌ No tienes acceso.")
        return

    if not context.args:
        await update.message.reply_text("Uso: /proxy <http|socks4|socks5> [PAIS]")
        return

    proxy_type = context.args[0].lower()
    country = context.args[1].upper() if len(context.args) > 1 else "ALL"

    if proxy_type not in PROXY_URLS:
        await update.message.reply_text("❌ Tipo inválido.")
        return

    url = PROXY_URLS[proxy_type].format(country=country)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=REQUEST_TIMEOUT) as r:
                text = await r.text()
    except Exception:
        await update.message.reply_text("❌ Error obteniendo proxys.")
        return

    proxies = [p for p in text.splitlines() if ":" in p][:MAX_PROXIES]

    if not proxies:
        await update.message.reply_text("❌ No se encontraron proxys.")
        return

    msg = f"🌍 *{proxy_type.upper()}* ({country})\n\n" + "\n".join(proxies)
    await update.message.reply_text(msg, parse_mode="Markdown")

# =====================
# MAIN
# =====================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN no está definido")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("myaccess", myaccess))
    app.add_handler(CommandHandler("proxy", proxy))

    app.run_polling()

if __name__ == "__main__":
    main()
