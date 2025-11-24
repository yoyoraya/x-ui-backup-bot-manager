import logging
import requests
import json
import os
import asyncio
import pytz
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    filters, ContextTypes, ConversationHandler, Defaults
)
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from cryptography.fernet import Fernet  # کتابخانه امنیت

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# --- لود کانفیگ ---
try:
    import config
    # بررسی وجود کلید رمزنگاری
    if not hasattr(config, 'ENCRYPTION_KEY'):
        print("Error: ENCRYPTION_KEY missing in config.py")
        # تولید کلید موقت برای جلوگیری از کرش (در اجراهای اول)
        config.ENCRYPTION_KEY = Fernet.generate_key().decode()
except ImportError:
    print("Error: config.py not found.")
    exit(1)

# --- تنظیمات ---
DATA_FILE = "servers.json"
BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)
CIPHER_SUITE = Fernet(config.ENCRYPTION_KEY.encode()) # موتور رمزنگاری

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

POSSIBLE_PATHS = ["/panel/api/server/getDb", "/server/getDb", "/xui/server/getDb", "/api/server/getDb"]
NAME, URL, USERNAME, PASSWORD = range(4)

# --- توابع امنیتی (جدید) ---
def encrypt_text(text):
    """متن را می‌گیرد و رمز شده برمی‌گرداند"""
    return CIPHER_SUITE.encrypt(text.encode()).decode()

def decrypt_text(encrypted_text):
    """متن رمز شده را می‌گیرد و اصلش را برمی‌گرداند"""
    try:
        return CIPHER_SUITE.decrypt(encrypted_text.encode()).decode()
    except:
        # اگر رمزگشایی نشد (یعنی متن ساده بوده)، همان را برگردان
        return encrypted_text

# --- مدیریت فایل ---
def load_servers():
    if not os.path.exists(DATA_FILE): return []
    try:
        with open(DATA_FILE, 'r') as f:
            servers = json.load(f)
            # موقع لود کردن، پسورد را برای استفاده در رم باز میکنیم
            for s in servers:
                s['password'] = decrypt_text(s['password'])
            return servers
    except: return []

def save_servers(servers):
    # کپی عمیق برای اینکه دیتا در رم دستکاری نشود
    import copy
    servers_encrypted = copy.deepcopy(servers)
    
    # قبل از ذخیره، پسوردها را رمزنگاری میکنیم
    for s in servers_encrypted:
        s['password'] = encrypt_text(s['password'])
        
    with open(DATA_FILE, 'w') as f:
        json.dump(servers_encrypted, f, indent=4)

def check_auth(user_id):
    return user_id == int(config.ADMIN_ID)

# --- هسته بکاپ ---
def perform_backup_logic(server):
    session = requests.Session()
    base_url = server['url'].rstrip('/')
    login_url = f"{base_url}/login"
    
    # نکته: اینجا server['password'] دیکریپت شده است (چون از load_servers آمده)
    
    for attempt in range(1, 4):
        try:
            res = session.post(login_url, data={'username': server['username'], 'password': server['password']}, verify=False, timeout=15)
            if res.status_code == 200 and (session.cookies or "success" in res.text):
                target_path = server.get('db_path')
                paths_to_try = [target_path] if target_path else POSSIBLE_PATHS
                for path in paths_to_try:
                    if not path: continue
                    try:
                        db_res = session.get(f"{base_url}{path}", verify=False, timeout=20)
                        if db_res.status_code == 200 and len(db_res.content) > 1000:
                            filename = f"{server['name']}_{datetime.now().strftime('%Y%m%d_%H%M')}.db"
                            filepath = os.path.join(BACKUP_DIR, filename)
                            with open(filepath, 'wb') as f: f.write(db_res.content)
                            return filepath, path
                    except: continue
                return None, "Path not found"
            if attempt == 3: return None, "Login Failed"
        except Exception as e:
            if attempt < 3: import time; time.sleep(5)
            else: return None, str(e)
    return None, "Unknown"

# --- منوها و هندلرها (بدون تغییر عمده) ---
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("➕ افزودن سرور", callback_data='add_server'), InlineKeyboardButton("📋 لیست سرورها", callback_data='list_servers')], [InlineKeyboardButton("🚀 بکاپ‌گیری آنی", callback_data='backup_all')]]
    msg = "🔐 **مدیریت بکاپ امن X-UI**\n\nوضعیت: 🟢 فعال (Encrypted Storage)"
    if update.message: await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else: await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not check_auth(query.from_user.id): return
    data = query.data

    if data == 'main_menu': await show_menu(update, context)
    elif data == 'add_server': await query.message.reply_text("دستور /add را ارسال کنید.")
    elif data == 'list_servers':
        servers = load_servers()
        if not servers: await query.edit_message_text("لیست خالی است.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='main_menu')]]))
        else:
            for idx, s in enumerate(servers):
                # نمایش امن: پسورد را نشان نمیدهیم
                await query.message.reply_text(f"🔒 **{s['name']}**\n🌐 `{s['url']}`", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"🗑 حذف {s['name']}", callback_data=f"del_{idx}")]]), parse_mode='Markdown')
            await query.message.reply_text("--- پایان ---", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data='main_menu')]]))

    elif data == 'backup_all':
        await query.message.reply_text("⏳ شروع بکاپ...")
        await run_backup_task(context)

    elif data.startswith('del_'):
        idx = int(data.split('_')[1])
        servers = load_servers()
        if 0 <= idx < len(servers):
            removed = servers.pop(idx)
            save_servers(servers) # ذخیره مجدد (با رمزنگاری)
            await query.edit_message_text(f"✅ {removed['name']} حذف شد.")

async def run_backup_task(context):
    servers = load_servers()
    if not servers: return
    for server in servers:
        filepath, res = perform_backup_logic(server)
        if filepath:
            if server.get('db_path') != res:
                server['db_path'] = res
                save_servers(servers)
            try:
                with open(filepath, 'rb') as f: await context.bot.send_document(chat_id=int(config.ADMIN_ID), document=f, caption=f"✅ {server['name']}", parse_mode='Markdown')
                os.remove(filepath)
            except: pass
        else:
            await context.bot.send_message(chat_id=int(config.ADMIN_ID), text=f"❌ {server['name']}: {res}")

async def scheduled_backup(context): await run_backup_task(context)

# --- Conversation ---
async def add_start(update, context): return NAME if check_auth(update.effective_user.id) else ConversationHandler.END
async def add_name(update, context): context.user_data['name'] = update.message.text; await update.message.reply_text("URL:"); return URL
async def add_url(update, context): context.user_data['url'] = update.message.text; await update.message.reply_text("Username:"); return USERNAME
async def add_user(update, context): context.user_data['username'] = update.message.text; await update.message.reply_text("Password:"); return PASSWORD
async def add_pass(update, context):
    password = update.message.text
    temp = {'name': context.user_data['name'], 'url': context.user_data['url'], 'username': context.user_data['username'], 'password': password}
    msg = await update.message.reply_text("⏳ تست اتصال...")
    fp, res = perform_backup_logic(temp)
    if fp:
        os.remove(fp)
        temp['db_path'] = res
        servers = load_servers()
        servers.append(temp)
        save_servers(servers) # اینجا اتوماتیک رمز میشه
        await msg.edit_text(f"✅ امن شد و ذخیره گردید.")
    else: await msg.edit_text(f"❌ خطا: {res}")
    return ConversationHandler.END
async def cancel(update, context): await update.message.reply_text("لغو."); return ConversationHandler.END
async def start(update, context): await show_menu(update, context) if check_auth(update.effective_user.id) else None

def main():
    defaults = Defaults(tzinfo=pytz.timezone('Asia/Tehran'))
    app = Application.builder().token(config.BOT_TOKEN).defaults(defaults).build()
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(ConversationHandler(entry_points=[CommandHandler("add", add_start)], states={NAME:[MessageHandler(filters.TEXT, add_name)], URL:[MessageHandler(filters.TEXT, add_url)], USERNAME:[MessageHandler(filters.TEXT, add_user)], PASSWORD:[MessageHandler(filters.TEXT, add_pass)]}, fallbacks=[CommandHandler("cancel", cancel)]))
    app.add_handler(CommandHandler("start", start))
    app.job_queue.run_repeating(scheduled_backup, interval=43200, first=10)
    app.run_polling()

if __name__ == '__main__': main()
