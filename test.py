# --- Обработка подтверждения ---
@dp.callback_query(lambda c: c.data.startswith("approve:"))
async def approve_handler(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    city = user_city.get(user_id, "не вказано")

    # убираем кнопки у админа
    await callback.message.edit_reply_markup(reply_markup=None)
    await bot.send_message(user_id, "✅ Ваша анкета підтверджена і скоро буде опублікована!")
    await callback.answer("Заявка підтверджена!")

    # переносим заявку в очередь
    if user_id in pending_albums:
        moto_media, media_type = pending_albums[user_id]["media"]
        username = pending_albums[user_id]["username"]

        round_queues.setdefault(1, {}).setdefault(city, []).append(
            (user_id, moto_media, city, username, media_type)
        )
        user_photos_final[user_id] = (moto_media, city, username, media_type)
        del pending_albums[user_id]

    # если в городе >=2 участников → публикуем пары
    if len(round_queues[1][city]) >= 2:
        asyncio.create_task(publish_stage(1, city))

        # проверку голосов планируем через сутки
        scheduler.add_job(
            check_votes_and_prepare_next_round,
            "date",
            run_date=datetime.datetime.now() + datetime.timedelta(hours=24),
            args=[1]
        )


# --- Публикация тура ---
async def publish_stage(round_num: int, city: str):
    participants = round_queues.get(round_num, {}).get(city, [])
    pairs = make_pairs(participants)  # используем очередь напрямую, а не копию

    for pair in pairs:
        uids = [uid for uid, _, _, _, _ in pair]

        # формируем медиа
        media = []
        for i, (uid, moto, _, _, media_type) in enumerate(pair):
            if media_type == "photo":
                media.append(types.InputMediaPhoto(media=moto, caption=f"🏍️ Учасник {i+1}"))
            else:
                media.append(types.InputMediaVideo(media=moto, caption=f"🎥 Учасник {i+1}"))

        await bot.send_media_group(chat_id=CITY_CHANNELS[city], media=media)

        kb = get_vote_keyboard(round_num, *uids)
        msg = await bot.send_message(chat_id=CITY_CHANNELS[city], text=get_vote_text(round_num), reply_markup=kb)

        votes.setdefault(round_num, {})[msg.message_id] = {
            "participants": uids,
            "votes": {},
            "chat_id": CITY_CHANNELS[city]
        }


# --- Проверка голосов ---
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

        await bot.send_message(
            chat_id=CITY_CHANNELS.get(city, ADMIN_ID),
            text=f"🏆 Переможець батлу ({city}): @{username}" if username else f"🏆 Переможець батлу ({city}): ID {winner}"
        )

        del votes[round_num][msg_id]

    if round_num in votes and not votes[round_num]:
        del votes[round_num]

    # если есть участники → запускаем следующий тур
    if round_queues[next_round]:
        for city in round_queues[next_round]:
            if len(round_queues[next_round][city]) >= 2:
                asyncio.create_task(publish_stage(next_round, city))
                scheduler.add_job(
                    check_votes_and_prepare_next_round,
                    "date",
                    run_date=datetime.datetime.now() + datetime.timedelta(hours=24),
                    args=[next_round]
                )
