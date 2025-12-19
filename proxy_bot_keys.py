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

# =========================
# CONFIGURACIÓN
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # DEBE existir en Render
ADMIN_ID = 7178424080               # TU ID
DB_FILE = "bot.db"

MAX_PROXIES = 10
REQUEST_TIMEOUT = 15

PROXY_URLS = {
    "http": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&country={country}",
    "socks4": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks4&country={country}",
    "socks5": "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&country={country}",
}

# =========================
# BASE DE DATOS
# =========================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS keys (
        code TEXT PRIMARY KEY,
        days INTEGER,
        used INTEGER DEFAULT 0
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

# =========================
# UTILIDADES
# =========================
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def has_access(user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT expires_at FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and datetime.fromisoformat(row[0]) > datetime.utcnow())

# =========================
# COMANDOS ADMIN
# =========================
async def createkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Uso: /createkey <dias>")
        return

    days = int(context.args[0])
    code = os.urandom(6).hex().upper()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO keys (code, days) VALUES (?, ?)", (code, days))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"🔑 *Key creada*\n\n`{code}`\n⏳ {days} días",
        parse_mode="Markdown"
    )

async def listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id, expires_at FROM users")
    rows = c.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No hay usuarios activos.")
        return

    msg = "👥 *Usuarios activos*\n\n"
    for uid, exp in rows:
        msg += f"{uid} → {exp}\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

# =========================
# COMANDOS USUARIO
# =========================
async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /redeem <key>")
        return

    code = context.args[0].upper()
    user_id = update.effective_user.id

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("SELECT days, used FROM keys WHERE code = ?", (code,))
    row = c.fetchone()

    if not row:
        await update.message.reply_text("❌ Key inválida.")
        conn.close()
        return

    days, used = row
    if used:
        await update.message.reply_text("❌ Esta key ya fue usada.")
        conn.close()
        return

    expires = datetime.utcnow() + timedelta(days=days)

    c.execute(
        "INSERT OR REPLACE INTO users (user_id, expires_at) VALUES (?, ?)",
        (user_id, expires.isoformat())
    )
    c.execute("UPDATE keys SET used = 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ *Acceso activado*\n⏳ Expira: `{expires}`",
        parse_mode="Markdown"
    )

async def myaccess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT expires_at FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("No tienes acceso activo.")
        return

    await update.message.reply_text(
        f"⏳ Acceso válido hasta:\n`{row[0]}`",
        parse_mode="Markdown"
    )

async def proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_access(update.effective_user.id):
        await update.message.reply_text("❌ No tienes acceso. Usa /redeem.")
        return

    if not context.args:
        await update.message.reply_text("Uso: /proxy <http|socks4|socks5> [PAIS]")
        return

    proxy_type = context.args[0].lower()
    if proxy_type not in PROXY_URLS:
        await update.message.reply_text("Tipo inválido: http | socks4 | socks5")
        return

    country = "ALL"
    if len(context.args) >= 2:
        country = context.args[1].upper()

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

    msg = f"🌍 *Proxys {proxy_type.upper()} ({country})*\n\n"
    msg += "\n".join(proxies)

    await update.message.reply_text(msg, parse_mode="Markdown")

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 *Live Proxy Checker Bot*\n\n"
        "/redeem <key>\n"
        "/myaccess\n"
        "/proxy <http|socks4|socks5> [PAIS]",
        parse_mode="Markdown"
    )

# =========================
# MAIN
# =========================
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN no está definido en variables de entorno")

    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("createkey", createkey))
    app.add_handler(CommandHandler("listusers", listusers))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("myaccess", myaccess))
    app.add_handler(CommandHandler("proxy", proxy))

    app.run_polling()

if __name__ == "__main__":
    main()
