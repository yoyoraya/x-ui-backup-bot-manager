import logging
import requests
import json
import os
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Disable SSL warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# --- Load Config ---
try:
    import config
except ImportError:
    print("Error: config.py not found.")
    exit(1)

# --- Settings ---
DATA_FILE = "servers.json"
BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

# --- Possible Paths ---
POSSIBLE_PATHS = [
    "/panel/api/server/getDb",
    "/server/getDb",
    "/xui/server/getDb",
    "/api/server/getDb"
]

NAME, URL, USERNAME, PASSWORD = range(4)

# --- Helper Functions ---
def load_servers():
    if not os.path.exists(DATA_FILE): return []
    try:
        with open(DATA_FILE, 'r') as f: return json.load(f)
    except: return []

def save_servers(servers):
    with open(DATA_FILE, 'w') as f: json.dump(servers, f, indent=4)

def check_auth(update: Update):
    return update.effective_user.id == int(config.ADMIN_ID)

def perform_backup_logic(server):
    session = requests.Session()
    base_url = server['url'].rstrip('/')
    login_url = f"{base_url}/login"
    
    try:
        # 1. Login
        res = session.post(login_url, data={'username': server['username'], 'password': server['password']}, verify=False, timeout=10)
        
        if res.status_code != 200 or (not session.cookies and "success" not in res.text):
            return None, "Login Failed (Check User/Pass)"

        # 2. Download DB
        target_path = server.get('db_path')
        paths_to_try = [target_path] if target_path else POSSIBLE_PATHS

        for path in paths_to_try:
            if not path: continue
            full_url = f"{base_url}{path}"
            try:
                db_res = session.get(full_url, verify=False, timeout=15)
                if db_res.status_code == 200 and len(db_res.content) > 1000:
                    filename = f"{server['name']}_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
                    filepath = os.path.join(BACKUP_DIR, filename)
                    with open(filepath, 'wb') as f:
                        f.write(db_res.content)
                    return filepath, path
            except:
                continue
        return None, "Database path not found (404)"
    except Exception as e:
        return None, str(e)

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update): return
    await update.message.reply_text(
        "👋 **X-UI Backup Manager**\n\nCommands:\n➕ /add - Add Server\n📋 /list - List Servers\n🚀 /backup - Backup Now\n❌ /delete - Delete Server",
        parse_mode='Markdown'
    )

async def list_servers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update): return
    servers = load_servers()
    if not servers:
        await update.message.reply_text("List is empty.")
        return
    text = "📋 **Servers:**\n\n"
    for i, s in enumerate(servers):
        path_info = s.get('db_path', 'Not Detected Yet')
        text += f"{i+1}. **{s['name']}**\n🌐 `{s['url']}`\n📂 Path: `{path_info}`\n\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def backup_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update): return
    servers = load_servers()
    if not servers:
        await update.message.reply_text("No servers configured.")
        return
    await update.message.reply_text(f"⏳ Backing up {len(servers)} servers...")
    
    for server in servers:
        msg = await update.message.reply_text(f"🔄 Connecting to **{server['name']}**...")
        filepath, result = perform_backup_logic(server)
        if filepath:
            if 'db_path' not in server or server['db_path'] != result:
                server['db_path'] = result
                save_servers(servers)
            caption = f"✅ **Backup Success**\n🖥 {server['name']}\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            with open(filepath, 'rb') as f:
                await update.message.reply_document(document=f, caption=caption, parse_mode='Markdown')
            os.remove(filepath)
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg.message_id)
        else:
            await msg.edit_text(f"❌ Error **{server['name']}**:\n{result}", parse_mode='Markdown')
    await update.message.reply_text("✅ Done.")

async def delete_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update): return
    await update.message.reply_text("To delete, please edit servers.json manually for now.")

# --- Add Server Conversation ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_auth(update): return ConversationHandler.END
    await update.message.reply_text("1️⃣ Enter Server Name:")
    return NAME

async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("2️⃣ Enter Full URL (http://ip:port):")
    return URL

async def add_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith("http"):
        await update.message.reply_text("❌ URL must start with http/https. Retry:")
        return URL
    context.user_data['url'] = url
    await update.message.reply_text("3️⃣ Enter Username:")
    return USERNAME

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['username'] = update.message.text
    await update.message.reply_text("4️⃣ Enter Password:")
    return PASSWORD

async def add_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text
    data = context.user_data
    status_msg = await update.message.reply_text("⏳ Testing connection...")
    
    temp_server = {'name': data['name'], 'url': data['url'], 'username': data['username'], 'password': password}
    filepath, result = perform_backup_logic(temp_server)
    
    if filepath:
        os.remove(filepath)
        temp_server['db_path'] = result
        servers = load_servers()
        servers.append(temp_server)
        save_servers(servers)
        await status_msg.edit_text(f"✅ **Success!**\nDB Path: `{result}`", parse_mode='Markdown')
    else:
        await status_msg.edit_text(f"❌ **Failed!**\nReason: {result}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

def main():
    application = Application.builder().token(config.BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_url)],
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pass)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_servers))
    application.add_handler(CommandHandler("backup", backup_now))
    application.add_handler(CommandHandler("delete", delete_server))
    application.add_handler(conv_handler)
    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
