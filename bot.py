import os
import asyncio
import logging
import yt_dlp

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, CallbackQuery
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 806382074

# معرف قناتك الإجبارية (استبدل @ChannelName بمعرف قناتك الحقيقي)
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@ChannelName")

bot = Bot(token=TOKEN)
dp = Dispatcher()

user_urls = {}

# --------------------------------------------------
# دالة التحقق من الاشتراك
# --------------------------------------------------
async def check_user_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        # التأكد أن حالة العضو ليست مغادرة أو محظور
        if member.status in ["creator", "administrator", "member"]:
            return True
        return False
    except TelegramBadRequest:
        # إذا حدث خطأ (مثلاً البوت ليس مشرفاً في القناة لفحص الأعضاء)
        return False
    except Exception:
        return False

# لوحة الاشتراك الإجباري
def get_subscription_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 اشترك في القناة هنا", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")],
            [InlineKeyboardButton(text="✅ تحقق من الاشتراك", callback_data="check_sub")]
        ]
    )

# --------------------------------------------------
# أمر البدء /start
# --------------------------------------------------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    if not await check_user_subscription(user_id):
        await message.answer(
            f"عذراً، يجب عليك الاشتراك في قناتنا أولاً لتتمكن من استخدام البوت!\n\nقناتنا: {REQUIRED_CHANNEL}\n\nبعد الاشتراك، اضغط على زر التحقق أسفله 👇",
            reply_markup=get_subscription_keyboard()
        )
        return
     
    await message.answer("أهلاً بك! أرسل لي رابط فيديو من التيك توك وسأقوم بتحميله لك.")

# --------------------------------------------------
# زر التحقق من الاشتراك
# --------------------------------------------------
@dp.callback_query(F.data == "check_sub")
async def process_check_sub(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if await check_user_subscription(user_id):
        await callback_query.message.edit_text("✨ شكراً لاشتراكك! يمكنك الآن إرسال رابط تيك توك للتحميل.")
    else:
        await callback_query.answer("⚠️ لم تقم بالاشتراك في القناة بعد، يرجى الاشتراك أولاً.", show_alert=True)

# --------------------------------------------------
# لوحة التحكم البسيطة للأدمن /admin
# --------------------------------------------------
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("أهلاً بك في لوحة تحكم الأدمن 👑\n\nنظام الاشتراك الإجباري مفعل ويعمل بكفاءة.")

# --------------------------------------------------
# استقبال الرابط
# --------------------------------------------------
@dp.message()
async def handle_message(message: Message):
    user_id = message.from_user.id
     
    # التحقق من الاشتراك الإجباري قبل قبول أي رابط
    if not await check_user_subscription(user_id):
        await message.answer(
            f"عذراً، يجب عليك الاشتراك في قناتنا أولاً لتتمكن من استخدام البوت!\n\nقناتنا: {REQUIRED_CHANNEL}",
            reply_markup=get_subscription_keyboard()
        )
        return

    if message.text and "tiktok.com" in message.text:
        user_urls[user_id] = message.text.strip()

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
     
    if not await check_user_subscription(user_id):
        await callback_query.message.edit_text(
            f"عذراً، اشترك في القناة أولاً:\n{REQUIRED_CHANNEL}",
            reply_markup=get_subscription_keyboard()
        )
        return

    url = user_urls.get(user_id)

    if not url:
        await callback_query.answer("انتهت الجلسة، يرجى إرسال الرابط مرة أخرى.", show_alert=True)
        return

    download_type = callback_query.data
    await callback_query.message.edit_text("⏳ جاري التحميل، لطفاً انتظر قليلاً...")

    if download_type == "download_video":
        output_filename = f"video_{user_id}.mp4"
        ydl_opts = {'format': 'best', 'outtmpl': output_filename, 'quiet': True}
    else:
        output_filename = f"audio_{user_id}.m4a"
        ydl_opts = {'format': 'bestaudio/best', 'outtmpl': output_filename, 'quiet': True}

    try:
        loop = asyncio.get_running_loop()
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        await loop.run_in_executor(None, download)

        if os.path.exists(output_filename):
            file_to_send = FSInputFile(output_filename)
            if download_type == "download_video":
                await bot.send_video(chat_id=user_id, video=file_to_send, caption="تم التحميل بنجاح! 🎬")
            else:
                await bot.send_audio(chat_id=user_id, audio=file_to_send, caption="تم استخراج الصوت بنجاح! 🎵")
             
            os.remove(output_filename)
            await callback_query.message.delete()
        else:
            await callback_query.message.edit_text("حدث خطأ أثناء التنزيل، يرجى التأكد من صحة الرابط.")
    except Exception as e:
        logging.error(f"Error: {e}")
        await callback_query.message.edit_text("فشل التحميل، يرجى المحاولة لاحقاً.")

# --------------------------------------------------
# التشغيل
# --------------------------------------------------
async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
