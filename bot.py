import os
import asyncio
import logging
import yt_dlp
from aiogram import Bot, Dispatcher, BaseMiddleware, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

TOKEN = "8701088285:AAEAjC2J7QVkLyTNdanvE38K_Zoj-vCwNDQ"
CHANNEL_ID = "@MDS2030"
CHANNEL_LINK = "https://t.me/MDS2030"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# قاموس مؤقت لتخزين روابط المستخدمين حسب الرسالة
user_urls = {}

# --------------------------------------------------
# Middleware للتحقق من الاشتراك الإجباري
# --------------------------------------------------
class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id

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
@dp.callback_query(lambda c: c.data == "check_subscription")
async def check_subscription_callback(callback_query: types.CallbackQuery):
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
                    InlineKeyboardButton(text="صوت MP3 🎵", callback_data="download_audio")
                ]
            ]
        )
        await message.answer("اختر صيغة التحميل التي تريدها:", reply_markup=keyboard)

# --------------------------------------------------
# معالجة الضغط على أزرار التنزيل (فيديو أو صوت)
# --------------------------------------------------
@dp.callback_query(lambda c: c.data in ["download_video", "download_audio"])
async def process_download(callback_query: types.CallbackQuery):
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
        output_filename = f"audio_{user_id}.mp3"
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_filename,
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
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
