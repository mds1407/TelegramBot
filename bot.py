import os
import asyncio
import logging
import sqlite3
import traceback
from datetime import datetime
from typing import Dict
import yt_dlp
from aiohttp import web

from aiogram import Bot, Dispatcher, BaseMiddleware, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# جلب التوكن والآيدي بأمان من متغيرات البيئة
TOKEN = os.getenv("BOT_TOKEN", "8701088285:AAEajC2J7QVkLyTNdanvE38K_Zoj-vCwNDQ")
ADMIN_ID = int(os.getenv("ADMIN_ID", "806382074"))
RATE_LIMIT_SECONDS = 5

# --------------------------------------------------
# خادم ويب وهمي لضمان استقرار الخدمة في Render
# --------------------------------------------------
async def handle_ping(request):
    return web.Response(text="Bot is running smoothly!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/health', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")

# --------------------------------------------------
# إعداد قاعدة البيانات (SQLite)
# --------------------------------------------------
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            key TEXT PRIMARY KEY,
            value INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('total_downloads', 0)")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('channel_id', '@MDS2030')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('force_join_enabled', 'false')")  # معطل افتراضياً بناءً على طلبك
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('notifications_enabled', 'true')")
    conn.commit()
    conn.close()

def get_setting(key: str, default: str = "") -> str:
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def add_user(user_id: int):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def increment_downloads():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE stats SET value = value + 1 WHERE key = 'total_downloads'")
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT value FROM stats WHERE key = 'total_downloads'")
    total_downloads = cursor.fetchone()[0]
    conn.close()
    return total_users, total_downloads

init_db()

# --------------------------------------------------
# نظام حماية السيرفر (Anti-Spam & Rate Limit)
# --------------------------------------------------
user_last_request: Dict[int, datetime] = {}

def is_rate_limited(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return False
    now = datetime.now()
    if user_id in user_last_request:
        elapsed = (now - user_last_request[user_id]).total_seconds()
        if elapsed < RATE_LIMIT_SECONDS:
            return True
    user_last_request[user_id] = now
    return False

# --------------------------------------------------
# إرسال تنبيهات الأخطاء للأدمن
# --------------------------------------------------
async def notify_admin_error(error_msg: str, user_id: int, url: str):
    notif_enabled = get_setting("notifications_enabled", "true")
    if notif_enabled != "true":
        return

    alert_text = (
        "⚠️ **تنبيه خطأ في البوت!**\n\n"
        f"👤 **المستخدم:** `{user_id}`\n"
        f"🔗 **الرابط:** `{url}`\n\n"
        f"❌ **تفاصيل الخطأ:**\n`{error_msg[:1000]}`"
    )
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=alert_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to send alert to admin: {e}")

# --------------------------------------------------
# حالات FSM للأدمن
# --------------------------------------------------
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    confirm_broadcast = State()
    waiting_for_channel = State()

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

user_urls = {}

# --------------------------------------------------
# Middleware لتسجيل المستخدمين فقط (بدون أي اشتراك إجباري)
# --------------------------------------------------
class UserTrackingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data: dict):
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            add_user(event.from_user.id)
        return await handler(event, data)

dp.message.middleware(UserTrackingMiddleware())
dp.callback_query.middleware(UserTrackingMiddleware())

# --------------------------------------------------
# لوحة تحكم الأدمن (/admin)
# --------------------------------------------------
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    current_channel = get_setting("channel_id", "@MDS2030")
    status_fj = "مفعل 🟢" if get_setting("force_join_enabled", "false") == "true" else "معطل 🔴"
    status_notif = "مفعلة 🔔" if get_setting("notifications_enabled", "true") == "true" else "معطلة 🔕"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 إذاعة للكل", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="📊 الإحصائيات", callback_data="admin_stats")],
            [InlineKeyboardButton(text=f"⚙️ الاشتراك الإجباري ({status_fj})", callback_data="toggle_force_join")],
            [InlineKeyboardButton(text=f"🔔 التنبيهات المباشرة ({status_notif})", callback_data="toggle_notifications")],
            [InlineKeyboardButton(text=f"✏️ تغيير القناة ({current_channel})", callback_data="change_channel")]
        ]
    )
    await message.answer("أهلاً بك في لوحة تحكم الأدمن 👑", reply_markup=keyboard)

@dp.callback_query(F.data == "toggle_force_join")
async def toggle_force_join(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        return
    current = get_setting("force_join_enabled", "false")
    new_val = "false" if current == "true" else "true"
    set_setting("force_join_enabled", new_val)
    await callback_query.answer("تم تغيير حالة الاشتراك الإجباري!")
    await cmd_admin(callback_query.message)

@dp.callback_query(F.data == "toggle_notifications")
async def toggle_notifications(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        return
    current = get_setting("notifications_enabled", "true")
    new_val = "false" if current == "true" else "true"
    set_setting("notifications_enabled", new_val)
    await callback_query.answer("تم تغيير حالة التنبيهات المباشرة!")
    await cmd_admin(callback_query.message)

@dp.callback_query(F.data == "change_channel")
async def prompt_change_channel(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_for_channel)
    await callback_query.message.answer("أرسل معرف القناة الجديد مع الـ @ (مثال: `@MDS2030`):", parse_mode="Markdown")
    await callback_query.answer()

@dp.message(AdminStates.waiting_for_channel)
async def process_new_channel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    new_ch = message.text.strip()
    if not new_ch.startswith("@"):
        new_ch = "@" + new_ch
    
    set_setting("channel_id", new_ch)
    await state.clear()
    await message.answer(f"✅ تم تحديث معرف القناة إلى: {new_ch}")

@dp.callback_query(F.data == "admin_stats")
async def process_admin_stats(callback_query: CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        return
    total_users, total_downloads = get_stats()
    text = (
        "📊 **إحصائيات البوت:**\n\n"
        f"👥 **عدد المشتركين الكلي:** {total_users}\n"
        f"📥 **إجمالي التحميلات:** {total_downloads}"
    )
    await callback_query.message.answer(text, parse_mode="Markdown")
    await callback_query.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def process_admin_broadcast(callback_query: CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback_query.message.answer("أرسل الآن الرسالة التي تريد إرسالها للجميع (نص، صورة، فيديو...):")
    await callback_query.answer()

@dp.message(AdminStates.waiting_for_broadcast)
async def receive_broadcast_message(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await state.update_data(broadcast_message_id=message.message_id, chat_id=message.chat.id)
    await state.set_state(AdminStates.confirm_broadcast)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تأكيد الإرسال", callback_data="confirm_send"),
                InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_send")
            ]
        ]
    )
    await message.reply("هل أنت متاكد من إرسال هذه الرسالة لجميع المستخدمين؟", reply_markup=keyboard)

@dp.callback_query(F.data == "cancel_send", AdminStates.confirm_broadcast)
async def cancel_broadcast(callback_query: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.edit_text("❌ تم إلغاء الإذاعة.")
    await callback_query.answer()

@dp.callback_query(F.data == "confirm_send", AdminStates.confirm_broadcast)
async def start_broadcast(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id = data.get("broadcast_message_id")
    from_chat_id = data.get("chat_id")
    await state.clear()

    await callback_query.message.edit_text("⏳ جاري بدء الإذاعة...")

    users = get_all_users()
    success = 0
    failed = 0

    for u_id in users:
        try:
            await bot.copy_message(chat_id=u_id, from_chat_id=from_chat_id, message_id=msg_id)
            success += 1
            await asyncio.sleep(0.05)
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
        except Exception:
            failed += 1

    report = (
        "🚀 **تمت الإذاعة بنجاح!**\n\n"
        f"✅ **تم الإرسال إلى:** {success}\n"
        f"❌ **فشل الإرسال إلى:** {failed}"
    )
    await callback_query.message.answer(report, parse_mode="Markdown")
    await callback_query.answer()

# --------------------------------------------------
# أمر البدء /start
# --------------------------------------------------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("أهلاً بك! أرسل لي رابط فيديو من التيك توك وسأعرض لك خيارات التحميل.")

# --------------------------------------------------
# استقبال الرابط
# --------------------------------------------------
@dp.message()
async def handle_message(message: Message):
    if message.text and "tiktok.com" in message.text:
        user_id = message.from_user.id
        
        if is_rate_limited(user_id):
            await message.answer(f"⚠️ **لطفاً انتظر {RATE_LIMIT_SECONDS} ثوانٍ بين كل طلب والآخر لحماية السيرفر من الضغط.**")
            return

        url = message.text.strip()
        user_urls[user_id] = url

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="فيديو 🎬", callback_data="download_video"),
                    InlineKeyboardButton(text="صوت 🎵", callback_data="download_audio")
                ]
            ]
        )
        await message.answer("اختر صيغة التحميل التي تريدها:", reply_markup=keyboard)

# --------------------------------------------------
# معالجة التنزيل
# --------------------------------------------------
@dp.callback_query(F.data.in_(["download_video", "download_audio"]))
async def process_download(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    url = user_urls.get(user_id)

    if not url:
        await callback_query.answer("انتهت جلسة التحميل، يرجى إرسال الرابط مرة أخرى.", show_alert=True)
        return

    download_type = callback_query.data
    await callback_query.message.edit_text("⏳ جاري التحميل والمعالجة، لطفاً انتظر قليلاً...")

    if download_type == "download_video":
        output_filename = f"video_{user_id}.mp4"
        ydl_opts = {
            'format': 'best',
            'outtmpl': output_filename,
            'quiet': True,
        }
    else:
        output_filename = f"audio_{user_id}.m4a"
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_filename,
            'quiet': True,
        }

    try:
        loop = asyncio.get_running_loop()
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        await loop.run_in_executor(None, download)

        if os.path.exists(output_filename):
            file_to_send = FSInputFile(output_filename)
            if download_type == "download_video":
                await bot.send_video(chat_id=user_id, video=file_to_send, caption="تم تحميل الفيديو بنجاح! 🎬")
            else:
                await bot.send_audio(chat_id=user_id, audio=file_to_send, caption="تم استخراج الصوت بنجاح! 🎵")
            
            increment_downloads()
            os.remove(output_filename)
            await callback_query.message.delete()
        else:
            await callback_query.message.edit_text("حدث خطأ أثناء التنزيل، يرجى التأكد من صحة الرابط.")
            await notify_admin_error("الملف لم يتكون بعد التنزيل.", user_id, url)
    except Exception as e:
        error_details = traceback.format_exc()
        await callback_query.message.edit_text("فشل التحميل، يرجى المحاولة لاحقاً.")
        await notify_admin_error(error_details, user_id, url)

# --------------------------------------------------
# التشغيل الرئيسي
# --------------------------------------------------
async def main():
    logging.basicConfig(level=logging.INFO)
    
    # إلغاء أي Webhook قديم لتفادي التعارض نهائياً
    await bot.delete_webhook(drop_pending_updates=True)
    
    # تشغيل خادم الويب الوهمي
    await start_web_server()
    
    # بدء التنسيق والاستجابة
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
