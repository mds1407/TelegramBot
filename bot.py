import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiohttp import web

# توكن البوت الخاص بك
TOKEN = "8701088285:AAHU4fvEdAUZstasTYcsXrMRmtiqdXB0izk"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# أمر البدء
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("أهلاً بك! أرسل لي رابط فيديو من التيك توك وسأقوم بتحميله لك فوراً.")

# معالجة رسائل الروابط أو النصوص الأخرى
@dp.message()
async def handle_message(message: types.Message):
    if message.text and "tiktok.com" in message.text:
        await message.answer("جاري معالجة وتحميل الفيديو، لطفاً انتظر قليلاً...")
        # هنا يتم وضع كود yt-dlp لاحقاً
    else:
        await message.answer("يرجى إرسال رابط تيك توك صحيح.")

# خادم ويب وهمي لكي تستجيب منصة Render للمنفذ (Port) المطلوب
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
    # تشغيل سيرفر الويب بالتوازي مع البوت
    await web_server()
    # بدء تشغيل البوت
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped!")
