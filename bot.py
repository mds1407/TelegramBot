import os
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from yt_dlp import YoutubeDL

# Configuration
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DEFAULT_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@MDS2030")
RATE_LIMIT_SECONDS = 5  # عدد الثواني المطلوب انتظارها بين طلبات التحميل

if not TOKEN or ADMIN_ID == 0:
    raise ValueError("BOT_TOKEN and ADMIN_ID must be set in environment variables.")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Database Setup
DB_NAME = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('force_join', 'enabled')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('required_channel', ?)", (DEFAULT_CHANNEL,))
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('error_notifications', 'enabled')")
    conn.commit()
    conn.close()

init_db()

# DB Helpers
def add_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_total_users() -> int:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_setting(key: str, default: str = "") -> str:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

# Anti-Spam / Rate Limit Tracker
user_last_request: Dict[int, datetime] = {}

def check_rate_limit(user_id: int) -> bool:
    """ترجع True إذا كان المستخدم متجاوزاً للحد الزمني (يجب منعه)"""
    now = datetime.now()
    if user_id in user_last_request:
        elapsed = (now - user_last_request[user_id]).total_seconds()
        if elapsed < RATE_LIMIT_SECONDS:
            return True
    user_last_request[user_id] = now
    return False

# Admin Helper
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def notify_admin_error(error_msg: str):
    if get_setting("error_notifications", "enabled") == "enabled" and ADMIN_ID != 0:
        try:
            await bot.send_message(ADMIN_ID, f"⚠️ **تنبيه خطأ في البوت:**\n\n`{error_msg}`", parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Failed to send error notification to admin: {e}")

# Helper: Check Subscription
async def check_subscription(user_id: int) -> bool:
    if get_setting("force_join", "enabled") == "disabled":
        return True
    
    channel = get_setting("required_channel", DEFAULT_CHANNEL)
    if not channel:
        return True

    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logging.error(f"Error checking subscription for {user_id}: {e}")
        return True  # تجنباً لحظر المستخدم في حال وجود خلل في الصلاحيات

def get_subscription_keyboard() -> InlineKeyboardMarkup:
    channel = get_setting("required_channel", DEFAULT_CHANNEL)
    clean_channel = channel.replace("@", "")
    url = f"https://t.me/{clean_channel}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 اشترك في القناة هنا", url=url)],
        [InlineKeyboardButton(text="✅ تحقق من الاشتراك", callback_data="check_sub")]
    ])
    return keyboard

# Admin Keyboard Helper
def get_admin_keyboard() -> InlineKeyboardMarkup:
    is_fj_enabled = get_setting("force_join", "enabled") == "enabled"
    fj_status = "مفعل 🟢" if is_fj_enabled else "معطل 🔴"
    
    is_err_enabled = get_setting("error_notifications", "enabled") == "enabled"
    err_status = "مفعلة 🔔" if is_err_enabled else "معطلة 🔕"
    
    current_channel = get_setting("required_channel", DEFAULT_CHANNEL)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 إذاعة للكل", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton(text=f"⚙️ الاشتراك الإجباري ({fj_status})", callback_data="toggle_fj")],
        [InlineKeyboardButton(text=f"🔔 التنبيهات المباشرة ({err_status})", callback_data="toggle_err")],
        [InlineKeyboardButton(text=f"✏️ تغيير القناة ({current_channel})", callback_data="change_channel")]
    ])
    return keyboard

# Command Handlers
@dp.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    add_user(user_id)
    
    if not await check_subscription(user_id):
        await message.answer(
            "⚠️ عذراً عزيزي، يجب عليك الاشتراك في قناة البوت أولاً لاستخدامه:\n\nبعد الاشتراك، اضغط على زر التحقق أسفله 👇",
            reply_markup=get_subscription_keyboard()
        )
        return

    await message.answer(
        "👋 أهلاً بك في بوت تحميل مقاطع تيك توك بدون علامة مائية!\n\n"
        "أرسل لي أي رابط من تيك توك وسأقوم بتحميله فوراً 🎬"
    )

# Admin Panel Command
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "🛠️ **أهلاً بك في لوحة تحكم الأدمن**",
        reply_markup=get_admin_keyboard(),
        parse_mode="Markdown"
    )

# Admin Callbacks
@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if await check_subscription(user_id):
        await callback.message.delete()
        await callback.message.answer("✅ شكراً لاشتراكك! يمكنك الآن إرسال رابط التيك توك للتحميل.")
    else:
        await callback.answer("❌ لم تشترك بعد في القناة! يرجى الاشتراك ثم المحاولة مرة أخرى.", show_alert=True)

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    total = get_total_users()
    await callback.message.answer(f"📊 **إحصائيات البوت:**\n\nإجمالي عدد المشتركين: `{total}` مستخدم", parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "toggle_fj")
async def toggle_fj_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    current = get_setting("force_join", "enabled")
    new_status = "disabled" if current == "enabled" else "enabled"
    set_setting("force_join", new_status)
    
    await callback.message.edit_reply_markup(reply_markup=get_admin_keyboard())
    await callback.answer(f"تم تغيير حالة الاشتراك الإجباري إلى: {new_status}")

@dp.callback_query(F.data == "toggle_err")
async def toggle_err_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    current = get_setting("error_notifications", "enabled")
    new_status = "disabled" if current == "enabled" else "enabled"
    set_setting("error_notifications", new_status)
    
    await callback.message.edit_reply_markup(reply_markup=get_admin_keyboard())
    await callback.answer(f"تم تغيير حالة تنبيهات الأخطاء إلى: {new_status}")

@dp.callback_query(F.data == "change_channel")
async def change_channel_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    await callback.message.answer("✏️ أرسل معرف القناة الجديد الآن (مثال: `@MyChannel`):")
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def broadcast_prompt(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    await callback.message.answer("📢 أرسل الرسالة التي تريد إرسالها لجميع المشتركين الآن (نص، صورة، أو فيديو):")
    await callback.answer()

# Channel Change Handler
@dp.message(F.text.startswith("@"))
async def set_channel_handler(message: Message):
    if is_admin(message.from_user.id):
        new_channel = message.text.strip()
        set_setting("required_channel", new_channel)
        await message.answer(f"✅ تم تحديث قناة الاشتراك الإجباري بنجاح إلى: {new_channel}")

# Video Downloader Handler
@dp.message(F.text.contains("tiktok.com"))
async def handle_tiktok(message: Message):
    user_id = message.from_user.id
    add_user(user_id)

    # Check Force Join
    if not await check_subscription(user_id):
        await message.answer(
            "⚠️ عذراً عزيزي، يجب عليك الاشتراك في قناة البوت أولاً لاستخدامه:\n\nبعد الاشتراك، اضغط على زر التحقق أسفله 👇",
            reply_markup=get_subscription_keyboard()
        )
        return

    # Check Rate Limit (Anti-Spam)
    if check_rate_limit(user_id):
        await message.answer("⚠️ يرجى الانتظار بضع ثوانٍ قبل إرسال رابط جديد لحماية السيرفر من الضغط.")
        return

    url = message.text.strip()
    status_msg = await message.answer("⏳ جاري التحميل، يرجى الانتظار...")

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'noplaylist': True,
        'quiet': True
    }

    try:
        os.makedirs("downloads", exist_ok=True)
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        video_file = types.FSInputFile(file_path)
        await message.answer_video(video=video_file, caption="✅ تم التحميل بنجاح بواسطة البوت!")
        await status_msg.delete()

        if os.path.exists(file_path):
            os.remove(file_path)

    except Exception as e:
        logging.error(f"Download Error: {e}")
        await status_msg.edit_text("❌ عذراً، تعذر تحميل المقطع. تأكد من أن الرابط صحيح وحساب صاحب المقطع عام وليس خاص.")
        await notify_admin_error(f"فشل تحميل فيديو للمستخدم `{user_id}`\nالرابط: {url}\nالخطأ: {e}")

# Broadcast Handler (For Admin)
@dp.message(F.from_user.id == ADMIN_ID)
async def handle_admin_messages(message: Message):
    # Ignore commands or TikTok links
    if message.text and (message.text.startswith("/") or "tiktok.com" in message.text or message.text.startswith("@")):
        return

    users = get_all_users()
    success = 0
    failed = 0

    status = await message.answer(f"⏳ جاري الإذاعة إلى {len(users)} مستخدم...")

    for uid in users:
        try:
            await message.copy_to(chat_id=uid)
            success += 1
        except Exception:
            failed += 1

    await status.edit_text(f"✅ اكتملت الإذاعة!\n\n🟢 تم الإرسال بنجاح: {success}\n🔴 فشل الإرسال (حظروا البوت): {failed}")

# Main
if __name__ == "__main__":
    import asyncio
    async def main():
        logging.info("Starting Bot...")
        await dp.start_polling(bot)

    asyncio.run(main())
