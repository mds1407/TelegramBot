import os
import asyncio
import logging
import yt_dlp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiohttp import web

TOKEN = "8701088285:AAEajC2J7QVkLyTNdanvE38K_Zoj-vCwNDQ"

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("أهلاً بك! أرسل لي رابط فيديو من التيك توك وسأقوم بتحميله لك فوراً.")

@dp.message()
async def handle_message(message: types.Message):
    if message.text and "tiktok.com" in message.text:
        url = message.text.strip()
        processing_msg = await message.answer("جاري معالجة وتحميل الفيديو، لطفاً انتظر قليلاً...")
        
        output_filename = f"video_{message.from_user.id}.mp4"
        
        ydl_opts = {
            'format': 'best',
            'outtmpl': output_filename,
            'quiet': True,
        }
        
        try:
            # تحميل الفيديو باستخدام yt-dlp في الخلفية
            loop = asyncio.get_running_loop()
            def download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            
            await loop.run_in_executor(None, download)
            
            if os.path.exists(output_filename):
                # إرسال الفيديو للمستخدم
                video_file = types.FSInputFile(output_filename)
                await message.answer_video(video_file, caption="تم التحميل بنجاح بواسطة البوت!")
                # حذف الملف من السيرفر لتوفير المساحة
                os.remove(output_filename)
                await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
            else:
                await message.answer("عذراً، لم أتمكن من تحميل الفيديو. تأكد من صحة الرابط.")
        except Exception as e:
            logging.error(f"Download error: {e}")
            await message.answer("حدث خطأ أثناء تحميل الفيديو. حاول مرة أخرى لاحقاً.")
    else:
        await message.answer("يرجى إرسال رابط تيك توك صحيح.")

async def handle(request):
    return web.Response(text="Bot is running smoothly 24/7!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    # تنظيف أي Webhook قديم أو اتصالات معلقة لمنع أخطاء التعارض
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.gather(
        web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped!")
