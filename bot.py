import os
import asyncio
import logging
import sqlite3
import yt_dlp
from aiogram import Bot, Dispatcher, BaseMiddleware, types, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = "8701088285:AAEajC2J7QVkLyTNdanvE38K_Zoj-vCwNDQ"
ADMIN_ID = 806382074  # ID الأدمن الخاص بك
CHANNEL_ID = "@MDS2030"
CHANNEL_LINK = "https://t.me/MDS2030"

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
    cursor.execute("INSERT OR IGNORE INTO stats (key, value) VALUES ('total_downloads', 0)")
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
# حالات FSM للإذاعة
# --------------------------------------------------
class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    confirm_broadcast = State()

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

user_urls = {}

# --------------------------------------------------
# Middleware للتحقق من الاشتراك الإجباري وحفظ المستخدم
# --------------------------------------------------
class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id
        add_user(user_id)  # تسجيل المستخدم في قاعدة البيانات تلقائياً

        try:
            member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            if member.status in ["creator", "administrator", "member"]:
                return await handler(event, data)
        except TelegramBadRequest:
            pass

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📢 اشترك في القناة أولاً", url=CHANNEL_LINK)],
                [InlineKeyboardButton(text="✅ تحقق من الاشتراك", callback_data="check_subscription")]
            ]
        )
        await event.answer(
            "⚠️ **عذراً، يجب عليك الاشتراك في القناة أولاً لاستخدام البوت.**\n\n"
            "اضغط على الزر أدناه للاشتراك، ثم اضغط على (تحقق من الاشتراك):",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

dp.message.middleware(ForceJoinMiddleware())

# --------------------------------------------------
# زر التحقق من الاشتراك
# --------------------------------------------------
@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            await callback_query.message.delete()
            await callback_query.message.answer("✅ تم التأكد من اشتراكك بنجاح! أرسل لي الآن رابط التيك توك لتحميله.")
        else:
            await callback_query.answer("❌ لم تشترك في القناة بعد! اشترك ثم اضغط تحقق.", show_alert=True)
    except Exception:
        await callback_query.answer("حدث خطأ أثناء التحقق، يرجى المحاولة لاحقاً.", show_alert=True)

# --------------------------------------------------
# لوحة تحكم الأدمن (/admin)
# --------------------------------------------------
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 إذاعة للكل", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="📊 الإحصائيات", callback_data="admin_stats")]
        ]
    )
    await message.answer("أهلاً بك في لوحة تحكم الأدمن 👑", reply_markup=keyboard)

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
    await state.set_state(BroadcastStates.waiting_for_message)
    await callback_query.message.answer("أرسل الآن الرسالة التي تريد إرسالها للجميع (نص، صورة، فيديو...):")
    await callback_query.answer()

@dp.message(BroadcastStates.waiting_for_message)
async def receive_broadcast_message(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await state.update_data(broadcast_message_id=message.message_id, chat_id=message.chat.id)
    await state.set_state(BroadcastStates.confirm_broadcast)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تأكيد الإرسال", callback_data="confirm_send"),
                InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_send")
            ]
        ]
    )
    await message.reply("هل أنت متاكد من إرسال هذه الرسالة لجميع المستخدمين؟", reply_markup=keyboard)

@dp.callback_query(F.data == "cancel_send", BroadcastStates.confirm_broadcast)
async def cancel_broadcast(callback_query: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.edit_text("❌ تم إلغاء الإذاعة.")
    await callback_query.answer()

@dp.callback_query(F.data == "confirm_send", BroadcastStates.confirm_broadcast)
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
            await asyncio.sleep(0.05)  # لتفادي حظر تليجرام للإرسال السريع
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
# استقبال الرابط وعرض أزرار الاختيار (فيديو / صوت)
# --------------------------------------------------
@dp.message()
async def handle_message(message: Message):
    if message.text and "tiktok.com" in message.text:
        url = message.text.strip()
        user_urls[message.from_user.id] = url

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
# معالجة التنزيل (فيديو أو صوت)
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
            
            increment_downloads()  # زيادة عداد التحميلات
            os.remove(output_filename)
            await callback_query.message.delete()
        else:
            await callback_query.message.edit_text("حدث خطأ أثناء التنزيل، يرجى التأكد من صحة الرابط.")
    except Exception as e:
        await callback_query.message.edit_text("فشل التحميل، يرجى المحاولة لاحقاً.")

# --------------------------------------------------
# تشغيل البوت
# --------------------------------------------------
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
