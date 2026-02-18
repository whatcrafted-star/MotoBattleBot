import asyncio
import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F

TOKEN = "8427517284:AAFqANQ1Okf8OAnp63eVI7UJfP7iX7IC1Ts"
ADMIN_ID = 5803112110

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Хранилища ---
round_queues = {}  # {round_num: {city: [список участников]}}
user_photos = {}   # {user_id: (file_id, media_type)}
user_photos_final = {}    # {user_id: (file_id, city, username, media_type)}
user_city = {}
pending_albums = {}       # {user_id: {"media": (file_id, media_type), "username": str}}
votes = {}         # {round_num: {msg_id: {user_id: voted_uid}}}

CITY_CHANNELS = {
    "Київ": -1003702188374,
    "Харків": -1003743863806,
    "Львів": -1003394222240,
    "Суми": -1003754209944,
    "Дніпро": -1003790850319,
    "Чернігів": -1003873530206,
    "Полтава": -1003832509271,
    "Вінниця": -1003696647087,
    "Волинь": -1003877739527,
    "Закарпаття": -1003715136126,
    "Житомир": -1003649498766,
    "Івано-Франківськ": -1003732056856,
    "Кіровоград": -1003872780440,
    "Миколаїв": -1003852488821,
    "Рівне": -1003678284761,
    "Тернопіль": -1003830259371,
    "Одеса": -1003857582693,
    "Хмельницький": -1003686419133,
    "Черкаси": -1003845400448,
    "Чернівці": -1003817623042
}

# --- Вспомогательные функции ---
def get_vote_text(round_num: int) -> str:
    return f"📣 Тур {round_num} 📣\n\nГолосуй за кращий мотоцикл!"

def get_vote_keyboard(round_num: int, *uids):
    buttons = []
    for i, uid in enumerate(uids, start=1):
        buttons.append([InlineKeyboardButton(text=f"Голос за {i}", callback_data=f"vote:{round_num}:{uid}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def seconds_until_10am(days_offset=0):
    now = datetime.datetime.now()
    target = (now + datetime.timedelta(days=days_offset)).replace(hour=10, minute=0, second=0, microsecond=0)
    return max(0, (target - now).total_seconds())

def make_pairs(queue):
    pairs = []
    while len(queue) > 3:
        pairs.append([queue.pop(0), queue.pop(0)])
    if len(queue) == 3:
        pairs.append(queue[:])
        queue.clear()
    elif len(queue) == 2:
        pairs.append([queue.pop(0), queue.pop(0)])
    return pairs

def get_battle_mode():
    day = datetime.date.today().toordinal()
    return "photo" if day % 2 == 0 else "video"

# --- Общий текст для оплаты ---
def get_payment_text():
    return (
        "Ціна входу: 50 грн 💳\n"
        "Гаманець кріптовалюти:\n"
        "`0xF7BeE7329fcA1662180c1d4d8e618F5CeAdD1587`\n"
        "Карта для оплати:\n"
        "1234 5678 9012 3456\n"
        "📄 Після оплати обов'язково скинь чек!"
    )

def get_help_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ℹ️ Допомога по оплаті", url="https://t.me/your_channel_here")]
    ])

# --- Обработка команд ---
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    if message.from_user.id in user_city:
        await message.answer(f"Привіт! Твій город: {user_city[message.from_user.id]} ✅\nКидай { 'відео' if get_battle_mode() == 'video' else 'фото' } свого мото 🚀")
    else:
        await message.answer("Привіт! Вкажи свій город командою /city <название>, щоб продовжити.")

@dp.message(Command("city"))
async def set_city(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2:
        city = parts[1]
        user_city[message.from_user.id] = city

        # если у пользователя уже есть заявка — обновим её город
        if message.from_user.id in pending_albums:
            pending_albums[message.from_user.id]["city"] = city

        await message.answer(
            f"✅ Твій город збережено: {city}\n"
            f"Тепер кидай { 'відео' if get_battle_mode() == 'video' else 'фото' } свого мото 🚀"
        )
    else:
        await message.answer("⚠️ Використай формат: /city <название>")

# --- Приём заявки (мотоцикл, фото) ---
@dp.message(F.photo)
async def handle_photo_submission(message: types.Message):
    if message.from_user.id in pending_albums:
        await handle_receipt(message)
        return

    if get_battle_mode() != "photo":
        return
    if message.from_user.id in user_photos:
        return

    city = user_city.get(message.from_user.id, "не вказано")
    user_photos[message.from_user.id] = (message.photo[-1].file_id, "photo")

    pending_albums[message.from_user.id] = {
        "media": (message.photo[-1].file_id, "photo"),
        "username": message.from_user.username or str(message.from_user.id),
        "city": city
    }

    await message.reply(get_payment_text(), parse_mode="Markdown", reply_markup=get_help_keyboard())

# --- Приём заявки (мотоцикл, видео) ---
@dp.message(F.video)
async def handle_video_submission(message: types.Message):
    if message.from_user.id in pending_albums:
        await handle_receipt(message)
        return

    if get_battle_mode() != "video":
        return
    if message.from_user.id in user_photos:
        return

    city = user_city.get(message.from_user.id, "не вказано")
    user_photos[message.from_user.id] = (message.video.file_id, "video")

    pending_albums[message.from_user.id] = {
        "media": (message.video.file_id, "video"),
        "username": message.from_user.username or str(message.from_user.id),
        "city": city
    }

    await message.reply(get_payment_text(), parse_mode="Markdown", reply_markup=get_help_keyboard())

# --- Приём чека ---
@dp.message(F.document | F.photo)
async def handle_receipt(message: types.Message):
    if message.from_user.id not in pending_albums:
        return

    moto_media, media_type = pending_albums[message.from_user.id]["media"]
    username = pending_albums[message.from_user.id]["username"]
    city = pending_albums[message.from_user.id]["city"]

    # формируем подпись для пользователя
    caption_user = f"@{username}" if username and not username.isdigit() else f"ID {username}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"approve:{message.from_user.id}")],
        [InlineKeyboardButton(text="❌ Відхилити", callback_data=f"reject:{message.from_user.id}")]
    ])

    if media_type == "photo":
        if message.photo and len(message.photo) > 0:
            media = [
                types.InputMediaPhoto(media=moto_media, caption=f"🏍️ Мото {caption_user}\n🌍 {city}"),
                types.InputMediaPhoto(media=message.photo[-1].file_id, caption="💳 Чек")
            ]
            await bot.send_media_group(ADMIN_ID, media=media)
        elif message.document:
            await bot.send_photo(
                ADMIN_ID,
                photo=moto_media,
                caption=f"🏍️ Мото {caption_user}\n🌍 {city}"
            )
            await bot.send_document(ADMIN_ID, document=message.document.file_id, caption="💳 Чек")

    elif media_type == "video":
        # всегда отправляем видео мото
        await bot.send_video(
            ADMIN_ID,
            video=moto_media,
            caption=f"🎥 Мото {caption_user}\n🌍 {city}"
        )
        # чек отдельно
        if message.photo and len(message.photo) > 0:
            await bot.send_photo(ADMIN_ID, photo=message.photo[-1].file_id, caption="💳 Чек")
        if message.document:
            await bot.send_document(ADMIN_ID, document=message.document.file_id, caption="💳 Чек")

    # сообщение админу с кнопками подтверждения/отклонення
    await bot.send_message(
        ADMIN_ID,
        f"📝 Нова заявка від {caption_user}\n🌍 Місто: {city}",
        reply_markup=kb
    )
    # сообщение пользователю
    await message.reply("✅ Чек отримано, очікуй підтвердження!")

# --- Обработка кнопок ---
@dp.callback_query(lambda c: c.data.startswith("approve:"))
async def approve_handler(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    city = user_city.get(user_id, "не вказано")

    await callback.message.edit_reply_markup(reply_markup=None)
    await bot.send_message(user_id, "✅ Ваша анкета підтверджена і скоро буде опублікована!")
    await callback.answer("Заявка підтверджена!")

    if user_id in pending_albums:
        moto_media, media_type = pending_albums[user_id]["media"]
        username = pending_albums[user_id]["username"]

        round_queues.setdefault(1, {}).setdefault(city, []).append((user_id, moto_media, city, username, media_type))
        user_photos_final[user_id] = (moto_media, city, username, media_type)
        del pending_albums[user_id]

    if len(round_queues[1][city]) >= 2:
        asyncio.create_task(schedule_stage(1, days_offset=0))


@dp.callback_query(lambda c: c.data.startswith("reject:"))
async def reject_handler(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=None)
    await bot.send_message(user_id, "❌ Ваша заявка була відхилена.")
    await callback.answer("Заявка відхилена!")
    if user_id in pending_albums:
        del pending_albums[user_id]


@dp.callback_query(lambda c: c.data.startswith("vote:"))
async def vote_handler(callback: types.CallbackQuery):
    _, round_num, voted_uid = callback.data.split(":")
    round_num = int(round_num)
    voted_uid = int(voted_uid)

    msg_id = callback.message.message_id
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    if round_num not in votes or msg_id not in votes[round_num]:
        await callback.answer("⚠️ Голосування недоступне.")
        return

    votes[round_num][msg_id]["votes"][user_id] = voted_uid

    tally = {}
    for uid in votes[round_num][msg_id]["votes"].values():
        tally[uid] = tally.get(uid, 0) + 1

    stats_text = f"{get_vote_text(round_num)}\n\n"
    for i, uid in enumerate(votes[round_num][msg_id]["participants"], start=1):
        _, _, username, _ = user_photos_final[uid]
        count = tally.get(uid, 0)
        stats_text += f"Учасник {i} (@{username if username else uid}): {count} голосів\n"

    kb = get_vote_keyboard(round_num, *votes[round_num][msg_id]["participants"])
    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=msg_id,
        text=stats_text,
        reply_markup=kb
    )

    await callback.answer("✅ Голос зараховано!")


# --- Этапы ---
async def schedule_stage(round_num: int, days_offset: int):
    await publish_stage(round_num)
    await check_votes_and_prepare_next_round(round_num)


async def publish_stage(round_num: int):
    city_groups = round_queues.get(round_num, {})

    for city, participants in city_groups.items():
        pairs = make_pairs(participants[:])

        for pair in pairs:
            uids = [uid for uid, _, _, _, _ in pair]
            media_types = [media_type for (_, _, _, _, media_type) in pair]

            if all(mt == "photo" for mt in media_types):
                media = [
                    types.InputMediaPhoto(media=moto, caption=f"🏍️ Учасник {i+1}")
                    for i, (uid, moto, _, _, _) in enumerate(pair)
                ]
                await bot.send_media_group(chat_id=CITY_CHANNELS[city], media=media)

            elif all(mt == "video" for mt in media_types):
                media = [
                    types.InputMediaVideo(media=moto, caption=f"🎥 Учасник {i+1}")
                    for i, (uid, moto, _, _, _) in enumerate(pair)
                ]
                await bot.send_media_group(chat_id=CITY_CHANNELS[city], media=media)

            else:
                for i, (uid, moto, _, _, media_type) in enumerate(pair):
                    if media_type == "photo":
                        await bot.send_photo(chat_id=CITY_CHANNELS[city], photo=moto, caption=f"🏍️ Учасник {i+1}")
                    else:
                        await bot.send_video(chat_id=CITY_CHANNELS[city], video=moto, caption=f"🎥 Учасник {i+1}")

            kb = get_vote_keyboard(round_num, *uids)
            msg = await bot.send_message(
                chat_id=CITY_CHANNELS[city],
                text=get_vote_text(round_num),
                reply_markup=kb
            )

            votes.setdefault(round_num, {})[msg.message_id] = {
                "participants": uids,
                "votes": {}
            }


async def check_votes_and_prepare_next_round(round_num: int):
    next_round = round_num + 1
    round_queues.setdefault(next_round, {})

    for msg_id, data in list(votes.get(round_num, {}).items()):
        tally = {}
        for voted_uid in data["votes"].values():
            tally[voted_uid] = tally.get(voted_uid, 0) + 1

        if not tally:
            continue

        winner = max(tally, key=tally.get)
        moto_media, city, username, media_type = user_photos_final[winner]

        round_queues[next_round].setdefault(city, []).append((winner, moto_media, city, username, media_type))

        if len(round_queues[next_round][city]) == 1 and next_round > round_num:
            await bot.send_message(
                chat_id=CITY_CHANNELS.get(city, ADMIN_ID),
                text=f"🏆 Переможець батлу ({city}): @{username}" if username else f"🏆 Переможець батлу ({city}): ID {winner}"
            )

        del votes[round_num][msg_id]

    if round_num in votes and not votes[round_num]:
        del votes[round_num]

    if round_queues[next_round]:
        asyncio.create_task(schedule_stage(next_round, days_offset=1))


# --- Основной запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
