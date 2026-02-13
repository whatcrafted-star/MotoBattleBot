import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta

TOKEN = "8427517284:AAFqANQ1Okf8OAnp63eVI7UJfP7iX7IC1Ts"
ADMIN_ID = 5803112110

bot = Bot(token=TOKEN)
dp = Dispatcher()

user_photos = {}
user_city = {}
pending_albums = {}
round1_queue = []   # очередь для первого тура
round2_queue = []   # очередь для второго тура
round3_queue = []   # очередь для третьего тура
current_round = 1   # текущий тур

# сохраняем опубликованные посты: {user_id: {"chat_id":..., "message_id":...}}
published_posts = {}
scheduler = AsyncIOScheduler()

CITY_CHANNELS = {
    "Київ": -1003702188374,
    "Харків": -1003743863806,
    "Львів": -1003394222240
}

def get_vote_text(round_num: int) -> str:
    if round_num == 1:
        title = "📣 перший тур 📣"
    elif round_num == 2:
        title = "📣 другий тур 📣"
    else:
        title = "📣 третій тур 📣"

    return f"""{title}

1 — ❤️
2 — 🔥

💎ПОСИЛАННЯ ДЛЯ ДРУГА 💎
Копіюй та відправляй для 
збільшення шанса на виграш:

https://t.me/motobattlekyiv
"""

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    if message.from_user.id in user_city:
        await message.answer(f"Привіт! Твій город: {user_city[message.from_user.id]} ✅\nКидай фото свого мото 🚀")
    else:
        await message.answer("Привіт! Вкажи свій город командою /city <название>, щоб продовжити.")

@dp.message(Command("city"))
async def set_city(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2:
        city = parts[1]
        user_city[message.from_user.id] = city
        await message.answer(f"✅ Твій город збережено: {city}\nТепер кидай фото свого мото 🚀")
    else:
        await message.answer("⚠️ Використай формат: /city <название>")

@dp.message(lambda msg: msg.photo and msg.from_user.id not in user_photos)
async def handle_photo(message: types.Message):
    user_photos[message.from_user.id] = message.photo[-1].file_id
    await message.reply("Ціна входу: 100 грн 💳\nКарта: 1234 5678 9012 3456\n📄 Після оплати обов'язково скинь чек!")

@dp.message(lambda msg: msg.document or (msg.photo and msg.from_user.id in user_photos))
async def handle_receipt(message: types.Message):
    moto_photo = user_photos.get(message.from_user.id)
    city = user_city.get(message.from_user.id, "не вказано")

    if moto_photo:
        caption = f"📝 Нова заявка від @{message.from_user.username or message.from_user.id}\n🌍 Город: {city}"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"approve:{message.from_user.id}")],
            [InlineKeyboardButton(text="❌ Відхилити", callback_data=f"reject:{message.from_user.id}")]
        ])

        if message.photo:  # чек как фото
            media = [
                types.InputMediaPhoto(media=moto_photo, caption=caption),
                types.InputMediaPhoto(media=message.photo[-1].file_id)
            ]
            await bot.send_media_group(chat_id=ADMIN_ID, media=media)
            await bot.send_message(ADMIN_ID, "Вибери дію:", reply_markup=kb)

            pending_albums[message.from_user.id] = moto_photo

        elif message.document:  # чек как PDF
            await bot.send_photo(ADMIN_ID, photo=moto_photo, caption=caption, reply_markup=kb)
            await bot.send_document(ADMIN_ID, message.document.file_id)

            pending_albums[message.from_user.id] = moto_photo

        del user_photos[message.from_user.id]
    else:
        await bot.send_message(ADMIN_ID, f"⚠️ Чек від @{message.from_user.username or message.from_user.id}, але фото мотоцикла не знайдено!")
        await bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)

    await message.reply("✅ Чек отримано, очікуй підтвердження!")

# --- Обработка кнопок ---
@dp.callback_query(lambda c: c.data.startswith("approve:"))
async def approve_handler(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    city = user_city.get(user_id, "не вказано")

    await callback.message.edit_reply_markup(reply_markup=None)
    await bot.send_message(user_id, "✅ Ваша анкета підтверджена і скоро буде опублікована!")
    await callback.answer("Заявка підтверджена!")

    # добавляем мотоцикл в очередь тура
    if user_id in pending_albums:
        round1_queue.append((user_id, pending_albums[user_id], city))
        del pending_albums[user_id]

    # если накопилось 2 мотоцикла → публикуем альбом
    if len(round1_queue) >= 2:
        uid1, moto1, city1 = round1_queue.pop(0)
        uid2, moto2, city2 = round1_queue.pop(0)

        combined_media = [
            types.InputMediaPhoto(media=moto1, caption="🏍️ Учасник 1"),
            types.InputMediaPhoto(media=moto2, caption="🏍️ Учасник 2")
        ]

        if city1 in CITY_CHANNELS:
            messages = await bot.send_media_group(chat_id=CITY_CHANNELS[city1], media=combined_media)
            # сохраняем ID первого сообщения альбома
            published_posts[uid1] = {"chat_id": CITY_CHANNELS[city1], "message_id": messages[0].message_id}
            published_posts[uid2] = {"chat_id": CITY_CHANNELS[city1], "message_id": messages[1].message_id}

            await bot.send_message(chat_id=CITY_CHANNELS[city1], text=get_vote_text(current_round))

@dp.callback_query(lambda c: c.data.startswith("reject:"))
async def reject_handler(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    await bot.send_message(user_id, "❌ Ваша анкета відхилена!")
    await callback.answer("Заявка відхилена!")
    await bot.send_message(ADMIN_ID, f"❌ Заявка від @{user_id} відхилена")

# --- Проверка голосов ---
@dp.message(Command("check_votes"))
async def check_votes(message: types.Message):
    # проверяем все опубликованные посты
    results = []
    for uid, post in published_posts.items():
        counts = await bot.get_message_reaction_count(
            chat_id=post["chat_id"],
            message_id=post["message_id"]
        )

        hearts = 0
        fires = 0
        for item in counts.reactions:
            if item.type.emoji == "❤️":
                hearts = item.count
            elif item.type.emoji == "🔥":
                fires = item.count

        if hearts > fires:
            results.append(f"Учасник {uid}: ❤️ переміг ({hearts} проти {fires})")
        elif fires > hearts:
            results.append(f"Учасник {uid}: 🔥 переміг ({fires} проти {hearts})")
        else:
            results.append(f"Учасник {uid}: нічия ({hearts}:{fires})")

    await message.answer("\n".join(results) if results else "⚠️ Немає постів для перевірки")

async def publish_round(round_num: int, queue: list, city: str = "Київ"):
    global current_round
    current_round = round_num

    if len(queue) >= 2:
        uid1, moto1, city1 = queue.pop(0)
        uid2, moto2, city2 = queue.pop(0)

        combined_media = [
            types.InputMediaPhoto(media=moto1, caption="🏍️ Учасник 1"),
            types.InputMediaPhoto(media=moto2, caption="🏍️ Учасник 2")
        ]

        if city1 in CITY_CHANNELS:
            # публикуем альбом
            messages = await bot.send_media_group(chat_id=CITY_CHANNELS[city1], media=combined_media)
            published_posts[uid1] = {"chat_id": CITY_CHANNELS[city1], "message_id": messages[0].message_id}
            published_posts[uid2] = {"chat_id": CITY_CHANNELS[city1], "message_id": messages[1].message_id}

            # добавляем текст для голосования
            await bot.send_message(chat_id=CITY_CHANNELS[city1], text=get_vote_text(round_num))

            # --- запускаем следующий тур через 30 секунд ---
            if round_num == 1:
                scheduler.add_job(
                    publish_round,
                    "date",
                    run_date=datetime.now() + timedelta(seconds=30),
                    args=[2, round2_queue]
                )
            elif round_num == 2:
                scheduler.add_job(
                    publish_round,
                    "date",
                    run_date=datetime.now() + timedelta(seconds=30),
                    args=[3, round3_queue]
                )

async def main():
    # тур 1 → каждый день в 10:00
    scheduler.add_job(lambda: asyncio.create_task(publish_round(1, round1_queue)), "cron", hour=10, minute=0)

    # --- запускаем второй тур через 30 секунд после публикации первого ---
    scheduler.add_job(
        lambda: asyncio.create_task(publish_round(2, round2_queue)),
        "date",
        run_date=datetime.now() + timedelta(seconds=30)
    )

    # тур 3 → ещё через день в 10:00
    scheduler.add_job(lambda: asyncio.create_task(check_votes_and_prepare_next_round()), "cron", hour=9, minute=55)
    scheduler.add_job(lambda: asyncio.create_task(publish_round(3, round3_queue)), "cron", hour=10, minute=0)

    scheduler.start()  # запускаем таймер
    await dp.start_polling(bot)  # запускаем бота

if __name__ == "__main__":
    asyncio.run(main())
