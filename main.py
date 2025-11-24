import logging
import requests
import json
import os
import asyncio
import pytz
import time
from datetime import datetime, time as dtime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    filters, ContextTypes, ConversationHandler, Defaults
)
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from cryptography.fernet import Fernet

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# --- لود کانفیگ ---
try:
    import config
    if not hasattr(config, 'ENCRYPTION_KEY'):
        print("Warning: ENCRYPTION_KEY missing. Generating temporary key.")
        config.ENCRYPTION_KEY = Fernet.generate_key().decode()
except ImportError:
    print("Error: config.py not found.")
    exit(1)

# --- تنظیمات ---
DATA_FILE = "servers.json"
SETTINGS_FILE = "settings.json"
BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)
CIPHER_SUITE = Fernet(config.ENCRYPTION_KEY.encode())

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

POSSIBLE_PATHS = ["/panel/api/server/getDb", "/server/getDb", "/xui/server/getDb", "/api/server/getDb"]
NAME, URL, USERNAME, PASSWORD = range(4)
BACK_BTN_TEXT = "🔙 بازگشت به منو"
BACK_MARKUP = ReplyKeyboardMarkup([[KeyboardButton(BACK_BTN_TEXT)]], resize_keyboard=True, one_time_keyboard=True)

# --- توابع رمزنگاری و فایل ---
def encrypt_text(text): return CIPHER_SUITE.encrypt(text.encode()).decode()
def decrypt_text(encrypted_text):
    try: return CIPHER_SUITE.decrypt(encrypted_text.encode()).decode()
    except: return encrypted_text

def load_servers():
    if not os.path.exists(DATA_FILE): return []
    try:
        with open(DATA_FILE, 'r') as f:
            servers = json.load(f)
            for s in servers: s['password'] = decrypt_text(s['password'])
            return servers
    except: return []

def save_servers(servers):
    import copy
    servers_encrypted = copy.deepcopy(servers)
    for s in servers_encrypted: s['password'] = encrypt_text(s['password'])
    with open(DATA_FILE, 'w') as f: json.dump(servers_encrypted, f, indent=4)

# --- مدیریت تنظیمات ---
def load_settings():
    default_settings = {"interval": 86400, "label": "هر 24 ساعت"}
    if not os.path.exists(SETTINGS_FILE): return default_settings
    try:
        with open(SETTINGS_FILE, 'r') as f: return json.load(f)
    except: return default_settings

def save_settings(interval, label):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump({"interval": interval, "label": label}, f)

def check_auth(user_id): return user_id == int(config.ADMIN_ID)

# --- توابع لاگین و بکاپ ---
def get_authenticated_session(server):
    session = requests.Session()
    base_url = server['url'].rstrip('/')
    login_url = f"{base_url}/login"
    delays = [0, 5, 10]
    for attempt, delay in enumerate(delays, 1):
        if delay > 0: time.sleep(delay)
        try:
            res = session.post(login_url, data={'username': server['username'], 'password': server['password']}, verify=False, timeout=10)
            if res.status_code == 200 and (session.cookies or "success" in res.text):
                return session, base_url, None
        except Exception as e:
            if attempt == 3: return None, None, str(e)
    return None, None, "Login Failed"

def perform_backup_sync(server):
    session, base_url, error = get_authenticated_session(server)
    if not session: return None, error
    
    saved_path = server.get('db_path')
    paths_to_scan = []
    if saved_path: paths_to_scan.append(saved_path)
    for p in POSSIBLE_PATHS:
        if p != saved_path: paths_to_scan.append(p)
    
    for path in paths_to_scan:
        if not path: continue
        try:
            db_res = session.get(f"{base_url}{path}", verify=False, timeout=15)
            if db_res.status_code == 200 and len(db_res.content) > 1000:
                safe_name = "".join([c for c in server['name'] if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).strip()
                if not safe_name: safe_name = "server"
                filename = f"{safe_name}.db"
                filepath = os.path.join(BACKUP_DIR, filename)
                with open(filepath, 'wb') as f: f.write(db_res.content)
                return filepath, path
        except: continue
    return None, "Path not found (404)"

def get_server_status_sync(server):
    session, base_url, error = get_authenticated_session(server)
    if not session: return f"🔴 **{server['name']}**\n⚠️ Offline: {error}"
    try:
        status_res = session.post(f"{base_url}/server/status", verify=False, timeout=10)
        if status_res.status_code == 200:
            data = status_res.json()
            if 'obj' in data: data = data['obj']
            cpu = data.get('cpu', 0)
            mem = data.get('mem', {})
            mem_percent = round((mem.get('current', 0) / mem.get('total', 1)) * 100, 1)
            uptime = data.get('uptime', 0)
            status_emoji = "🟢" if cpu < 80 else "🔴"
            return f"{status_emoji} **{server['name']}**\n💻 CPU: {cpu}% | RAM: {mem_percent}%\n⏳ Uptime: {uptime//86400}d\n🌐 `{server['url']}`"
    except: pass
    return f"🟢 **{server['name']}**\n(Login OK)\n🌐 `{server['url']}`"

async def perform_backup_async(server):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, perform_backup_sync, server)

async def get_status_async(server):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_server_status_sync, server)

async def update_job_schedule(application, interval, chat_id):
    job_queue = application.job_queue
    current_jobs = job_queue.get_jobs_by_name('backup_job')
    for job in current_jobs:
        job.schedule_removal()
    job_queue.run_repeating(scheduled_backup, interval=interval, first=interval, name='backup_job', chat_id=chat_id)
    logger.info(f"Schedule updated to every {interval} seconds.")

# --- منوها ---
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = load_settings()
    current_schedule = settings.get("label", "هر 24 ساعت")
    keyboard = [
        [InlineKeyboardButton("➕ افزودن سرور", callback_data='add_server'), InlineKeyboardButton("📋 مانیتورینگ", callback_data='list_servers')],
        [InlineKeyboardButton(f"⏱ زمان‌بندی: {current_schedule}", callback_data='schedule_menu')],
        [InlineKeyboardButton("📤 دریافت تنظیمات (Export)", callback_data='export_settings')],
        [InlineKeyboardButton("🚀 بکاپ‌گیری آنی", callback_data='backup_all')]
    ]
    
    # --- اضافه کردن متن هشدار به منوی اصلی ---
    msg = (
        f"🔐 **مدیریت بکاپ X-UI**\n"
        f"وضعیت: 🟢 فعال\n"
        f"تعداد سرورها: {len(load_servers())}\n\n"
        f"⚠️ **تذکر مهم:**\n"
        f"در صورت تغییر نسخه پنل (آپدیت/دانگرید)، حتماً از بخش مانیتورینگ، گزینه **«🔄 آپدیت مسیر»** را بزنید."
    )
    
    if update.message: await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else: await update.callback_query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def show_schedule_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("1 دقیقه", callback_data='set_time_60'), InlineKeyboardButton("5 دقیقه", callback_data='set_time_300')],
        [InlineKeyboardButton("10 دقیقه", callback_data='set_time_600'), InlineKeyboardButton("15 دقیقه", callback_data='set_time_900')],
        [InlineKeyboardButton("30 دقیقه", callback_data='set_time_1800'), InlineKeyboardButton("1 ساعت", callback_data='set_time_3600')],
        [InlineKeyboardButton("6 ساعت", callback_data='set_time_21600'), InlineKeyboardButton("12 ساعت", callback_data='set_time_43200')],
        [InlineKeyboardButton("هر روز (24 ساعت)", callback_data='set_time_86400')],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='main_menu')]
    ]
    await update.callback_query.edit_message_text("⏰ **تنظیم فاصله زمانی:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- هندلر دکمه‌ها ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not check_auth(query.from_user.id): return
    data = query.data

    if data == 'main_menu': await show_menu(update, context)
    elif data == 'schedule_menu': await show_schedule_menu(update)
    elif data == 'export_settings': await export_config_logic(update, context, chat_id=query.message.chat_id)
    
    elif data.startswith('set_time_'):
        seconds = int(data.split('_')[2])
        labels = {60: "1 دقیقه", 300: "5 دقیقه", 600: "10 دقیقه", 900: "15 دقیقه", 1800: "30 دقیقه", 3600: "1 ساعت", 21600: "6 ساعت", 43200: "12 ساعت", 86400: "24 ساعت"}
        label = labels.get(seconds, f"{seconds} ثانیه")
        save_settings(seconds, label)
        await update_job_schedule(context.application, seconds, query.message.chat_id)
        await query.edit_message_text(f"✅ زمان‌بندی: **{label}**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='main_menu')]]), parse_mode='Markdown')

    elif data == 'list_servers':
        servers = load_servers()
        if not servers: 
            await query.edit_message_text("لیست خالی است.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='main_menu')]]))
            return
        await query.message.reply_text("⏳ دریافت وضعیت...")
        tasks = [get_status_async(s) for s in servers]
        results = await asyncio.gather(*tasks)
        for idx, status_text in enumerate(results):
            keyboard = [
                [InlineKeyboardButton("🔄 آپدیت مسیر دیتابیس", callback_data=f"rescan_{idx}")],
                [InlineKeyboardButton(f"🗑 حذف {servers[idx]['name']}", callback_data=f"del_{idx}")]
            ]
            await query.message.reply_text(status_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        await query.message.reply_text("--- پایان ---", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 منو", callback_data='main_menu')]]))

    elif data == 'backup_all':
        await query.message.reply_text("⏳ بکاپ‌گیری شروع شد...")
        asyncio.create_task(run_backup_task(context, chat_id=query.message.chat_id))

    elif data.startswith('del_'):
        idx = int(data.split('_')[1])
        servers = load_servers()
        if 0 <= idx < len(servers):
            removed = servers.pop(idx)
            save_servers(servers)
            await query.edit_message_text(f"✅ سرور {removed['name']} حذف شد.")

    elif data.startswith('rescan_'):
        idx = int(data.split('_')[1])
        servers = load_servers()
        if 0 <= idx < len(servers):
            server = servers[idx]
            await query.message.reply_text(f"🔍 در حال اسکن مجدد مسیر برای **{server['name']}**...")
            filepath, new_path = await perform_backup_async(server)
            if filepath:
                os.remove(filepath)
                if server.get('db_path') != new_path:
                    server['db_path'] = new_path
                    servers[idx] = server
                    save_servers(servers)
                    await query.message.reply_text(f"✅ **مسیر آپدیت شد!**\nمسیر جدید: `{new_path}`", parse_mode='Markdown')
                else:
                    await query.message.reply_text(f"✅ مسیر فعلی صحیح است.\n`{new_path}`", parse_mode='Markdown')
            else:
                await query.message.reply_text(f"❌ خطا: نتوانستم مسیر دیتابیس را پیدا کنم.")

# --- بکاپ ---
async def run_backup_task(context, chat_id=None):
    if not chat_id: chat_id = int(config.ADMIN_ID)
    servers = load_servers()
    if not servers: return
    for server in servers:
        filepath, res = await perform_backup_async(server)
        if filepath:
            if server.get('db_path') != res:
                server['db_path'] = res
                save_servers(servers)
            try:
                now = datetime.now()
                caption = f"📦 **{server['name']}**\n📅 {now.strftime('%Y-%m-%d')}\n⏰ {now.strftime('%H:%M:%S')}"
                with open(filepath, 'rb') as f: await context.bot.send_document(chat_id=chat_id, document=f, caption=caption, parse_mode='Markdown')
                os.remove(filepath)
            except: pass
        else: await context.bot.send_message(chat_id=chat_id, text=f"❌ خطا {server['name']}:\n{res}")

async def scheduled_backup(context):
    chat_id = context.job.chat_id if context.job.chat_id else int(config.ADMIN_ID)
    await run_backup_task(context, chat_id=chat_id)

async def export_config_logic(update, context, chat_id):
    await context.bot.send_message(chat_id=chat_id, text="📥 ارسال فایل‌های تنظیمات...")
    try:
        for f_name in ["config.py", DATA_FILE, SETTINGS_FILE]:
            if os.path.exists(f_name):
                with open(f_name, "rb") as f: await context.bot.send_document(chat_id=chat_id, document=f)
    except Exception as e: await context.bot.send_message(chat_id=chat_id, text=f"❌ Error: {e}")

async def export_command_handler(update, context):
    if check_auth(update.effective_user.id): await export_config_logic(update, context, update.effective_chat.id)

# --- Conversation ---
async def back_to_main_menu(update, context): await update.message.reply_text("🔙 بازگشت.", reply_markup=ReplyKeyboardRemove()); await show_menu(update, context); return ConversationHandler.END
async def add_start_cmd(update, context): 
    if not check_auth(update.effective_user.id): return ConversationHandler.END
    await update.message.reply_text("1️⃣ نام سرور:", reply_markup=BACK_MARKUP); return NAME
async def add_start_btn(update, context):
    query = update.callback_query; await query.answer()
    if not check_auth(query.from_user.id): return ConversationHandler.END
    await query.message.reply_text("1️⃣ نام سرور:", reply_markup=BACK_MARKUP); return NAME
async def add_name(update, context): context.user_data['name'] = update.message.text; await update.message.reply_text("2️⃣ آدرس (http://ip:port):", reply_markup=BACK_MARKUP); return URL
async def add_url(update, context): context.user_data['url'] = update.message.text; await update.message.reply_text("3️⃣ یوزرنیم:", reply_markup=BACK_MARKUP); return USERNAME
async def add_user(update, context): context.user_data['username'] = update.message.text; await update.message.reply_text("4️⃣ پسورد:", reply_markup=BACK_MARKUP); return PASSWORD
async def add_pass(update, context):
    password = update.message.text
    temp = {'name': context.user_data['name'], 'url': context.user_data['url'], 'username': context.user_data['username'], 'password': password}
    msg = await update.message.reply_text("⏳ تست اتصال...", reply_markup=ReplyKeyboardRemove())
    fp, res = await perform_backup_async(temp)
    if fp:
        os.remove(fp); temp['db_path'] = res; servers = load_servers(); servers.append(temp); save_servers(servers)
        try: await msg.edit_text(f"✅ سرور اضافه شد.", parse_mode='Markdown')
        except: await update.message.reply_text(f"✅ سرور اضافه شد.")
    else:
        try: await msg.edit_text(f"❌ خطا:\n{res}")
        except: await update.message.reply_text(f"❌ خطا:\n{res}")
    return ConversationHandler.END

async def post_init(application: Application):
    commands = [("start", "🏠 منوی اصلی"), ("add", "➕ افزودن سرور"), ("export", "📤 بکاپ تنظیمات")]
    await application.bot.set_my_commands(commands)

def main():
    defaults = Defaults(tzinfo=pytz.timezone('Asia/Tehran'))
    app = Application.builder().token(config.BOT_TOKEN).defaults(defaults).post_init(post_init).build()
    
    settings = load_settings()
    initial_interval = settings.get("interval", 86400)
    app.job_queue.run_repeating(scheduled_backup, interval=initial_interval, first=initial_interval, name='backup_job', chat_id=int(config.ADMIN_ID))

    back_filter = filters.Regex(f"^{BACK_BTN_TEXT}$")
    conv = ConversationHandler(entry_points=[CommandHandler("add", add_start_cmd), CallbackQueryHandler(add_start_btn, pattern='^add_server$')],
        states={NAME:[MessageHandler(back_filter, back_to_main_menu), MessageHandler(filters.TEXT, add_name)], 
                URL:[MessageHandler(back_filter, back_to_main_menu), MessageHandler(filters.TEXT, add_url)], 
                USERNAME:[MessageHandler(back_filter, back_to_main_menu), MessageHandler(filters.TEXT, add_user)], 
                PASSWORD:[MessageHandler(back_filter, back_to_main_menu), MessageHandler(filters.TEXT, add_pass)]},
        fallbacks=[CommandHandler("cancel", back_to_main_menu)])
    
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("start", lambda u,c: show_menu(u,c) if check_auth(u.effective_user.id) else None))
    app.add_handler(CommandHandler("export", export_command_handler))
    
    print(f"Bot V13 Started. Schedule: {initial_interval}s")
    app.run_polling()

if __name__ == '__main__': main()
