import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
import yt_dlp

TOKEN = "8701088285:AAHU4fvedAUZStasTYcsXrMRmtiqdXB0oizk"

db = sqlite3.connect("bot_users.db")
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
db.commit()

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    db.commit()
    
    await message.answer(
        f"أهلاً بك يا {message.from_user.first_name} في بوت التحميل الخاص بك 🚀\n\n"
        "أرسل لي رابط فيديو تيك توك، وسأقوم بتحميله وإرساله لك فوراً بدون علامة مائية."
    )

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    await message.answer(f"📊 عدد المستخدمين الكلي للبوت: {count} مستخدم")

# جعل البوت يكتشف روابط تيك توك الكاملة أو المختصرة (vt.tiktok.com)
@dp.message(F.text.regexp(r"(https?://)?(www\.)?(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)/\S+"))
async def download_tiktok(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    db.commit()
    
    url = message.text.strip()
    processing_msg = await message.answer("⏳ ...جاري استخراج وتحميل الفيديو")
    
    output_filename = f"tiktok_{message.from_user.id}.mp4"
    
    try:
        ydl_opts = {
            'format': 'best',
            'outtmpl': output_filename,
            'quiet': True,
            'socket_timeout': 30,
            'nocheckcertificate': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        if os.path.exists(output_filename):
            video_file = types.FSInputFile(output_filename)
            await message.answer_video(
                video=video_file,
                caption="✅ تم التحميل بنجاح!"
            )
            await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
            os.remove(output_filename)
        else:
            await processing_msg.edit_text("❌ عذراً، لم أتمكن من تحميل الفيديو. تأكد أن الرابط صحيح")
            
    except Exception as e:
        logging.error(f"Error: {e}")
        await processing_msg.edit_text("⚠️ حدث خطأ أثناء التحميل.")

async def main():
    print("...البوت يعمل الآن")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
