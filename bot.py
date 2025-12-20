import os
import sqlite3
import aiohttp
import uuid
import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# --- CONFIGURACIÓN ---
BOT_TOKEN = "7984754462:AAHQRDlPrYgMpUsz3m4i7rzop9XT2lZaaJ0"
ADMIN_ID = 7178424080

# Configuración de logs para ver errores en Termux
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, expiry_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS keys 
                 (key_code TEXT PRIMARY KEY, duration_days INTEGER)''')
    conn.commit()
    conn.close()

def check_access(user_id):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT expiry_date FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result:
        expiry = datetime.fromisoformat(result[0])
        if expiry > datetime.now(timezone.utc):
            return True, expiry
    return False, None

# --- COMANDOS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"👋 ¡Hola {user_name}!\n\n"
        "✨ **Bienvenido al Proxy Hunter Pro**\n"
        "Este bot genera proxies privados de alta calidad.\n\n"
        "📜 **Comandos Disponibles:**\n"
        "• `/proxy [tipo] [pais]` - Ej: `/proxy socks5 US`\n"
        "• `/redeem [key]` - Activar tu suscripción\n"
        "• `/myaccess` - Ver vencimiento\n"
    )
    if update.effective_user.id == ADMIN_ID:
        welcome_text += "\n👑 **Admin:** `/genkey [días]`"
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    try:
        days = int(context.args[0])
        new_key = f"PREMIUM-{uuid.uuid4().hex[:8].upper()}"
        
        conn = sqlite3.connect('bot_database.db')
        conn.cursor().execute('INSERT INTO keys VALUES (?, ?)', (new_key, days))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ **Key Generada:**\n`{new_key}`\n⏳ Duración: {days} días", parse_mode='Markdown')
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Uso correcto: `/genkey 30`")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Debes poner la key: `/redeem KEY-XXX`")
        return

    key_input = context.args[0]
    user_id = update.effective_user.id

    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute('SELECT duration_days FROM keys WHERE key_code = ?', (key_input,))
    row = c.fetchone()

    if row:
        days = row[0]
        new_expiry = datetime.now(timezone.utc) + timedelta(days=days)
        c.execute('INSERT OR REPLACE INTO users (user_id, expiry_date) VALUES (?, ?)', 
                  (user_id, new_expiry.isoformat()))
        c.execute('DELETE FROM keys WHERE key_code = ?', (key_input,))
        conn.commit()
        await update.message.reply_text(f"🚀 ¡Acceso Activado!\nTu suscripción vence el: `{new_expiry.strftime('%Y-%m-%d')}`", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ La llave es inválida o ya fue usada.")
    conn.close()

async def get_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    has_access, expiry = check_access(user_id)

    if not has_access and user_id != ADMIN_ID:
        await update.message.reply_text("🚫 No tienes una suscripción activa. Compra una key primero.")
        return

    try:
        protocol = context.args[0].lower()
        country = context.args[1].upper()
        
        if protocol not in ['http', 'socks4', 'socks5']:
            await update.message.reply_text("❌ Tipo inválido. Usa: http, socks4 o socks5")
            return

        wait_msg = await update.message.reply_text(f"⏳ Buscando proxies en {country}...")

        url = f"https://api.proxyscrape.com/v2/?request=displayproxies&protocol={protocol}&timeout=10000&country={country}&ssl=all&anonymity=all"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.text()
                    if len(data.strip()) > 10:
                        file_path = f"proxies_{country}.txt"
                        with open(file_path, "w") as f:
                            f.write(data)
                        
                        await update.message.reply_document(
                            document=open(file_path, "rb"),
                            caption=f"✅ Proxies {protocol.upper()} encontrados en {country}."
                        )
                        os.remove(file_path)
                    else:
                        await update.message.reply_text(f"😕 No se encontraron proxies activos para {country} en este momento.")
                else:
                    await update.message.reply_text("❌ Error al conectar con el servidor de proxies.")
        
        await wait_msg.delete()

    except (IndexError, ValueError):
        await update.message.reply_text("❌ Uso: `/proxy [tipo] [país]`\nEjemplo: `/proxy socks5 US`")

async def my_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    has_access, expiry = check_access(update.effective_user.id)
    if has_access:
        await update.message.reply_text(f"✅ Tu acceso vence el: `{expiry.strftime('%Y-%m-%d %H:%M')}` UTC", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ No tienes una suscripción activa.")

# --- INICIO ---
if __name__ == '__main__':
    init_db()
    print("--- Cargando Proxy Hunter Pro ---")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("genkey", genkey))
    app.add_handler(CommandHandler("redeem", redeem))
    app.add_handler(CommandHandler("proxy", get_proxy))
    app.add_handler(CommandHandler("myaccess", my_access))

    print("--- Bot Funcionando Increíble ---")
    app.run_polling()
  
