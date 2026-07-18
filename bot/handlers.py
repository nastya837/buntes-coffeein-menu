"""Обработчики сообщений и колбэков Telegram."""
from __future__ import annotations

import datetime as dt

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .categories import emoji_for
from .config import Config
from .database import Db
from .keyboards import (
    BTN_ADD,
    BTN_ADVICE,
    BTN_BALANCE,
    BTN_HELP,
    BTN_PAYMENTS,
    BTN_REPORT,
    BTN_SETTINGS,
    BTN_STATS,
    add_hint_menu,
    confirm_delete,
    main_menu,
    payments_menu,
    report_periods,
    settings_menu,
)
from .llm import LLMClient
from .reports import (
    build_balance,
    build_context,
    build_report,
    export_csv_rows,
    fmt_money,
)

router = Router()

WELCOME = (
    "Привет! Я твой финансовый агент 🤖💰\n\n"
    "Просто пиши мне о своих тратах и доходах обычным языком:\n"
    "• <i>кофе 300</i>\n"
    "• <i>такси 450 и обед 600</i>\n"
    "• <i>зарплата 80000</i>\n\n"
    "Я сам определю категорию и посчитаю баланс. А ещё умею:\n"
    "🎙 распознавать голосовые и 📸 фото чеков\n"
    "📊 показывать отчёты и статистику\n"
    "🔔 напоминать об обязательных платежах\n"
    "💡 давать финансовые советы — просто спроси\n\n"
    "👇 Пользуйся кнопками меню снизу — там всё под рукой."
)

HELP = (
    "<b>Что я умею</b> 👇\n\n"
    "✍️ <b>Учёт.</b> Пиши операции текстом: «кофе 300», «зарплата 80000», "
    "«такси 450 и обед 600». Можно 🎙 голосом или 📸 фото чека.\n\n"
    "💰 <b>Баланс</b> — сколько сейчас на руках.\n"
    "📊 <b>Отчёт</b> — за день / неделю / месяц / год.\n"
    "📈 <b>Статистика</b> — куда уходит больше всего денег.\n"
    "💡 <b>Совет</b> — где можно сэкономить (спроси своими словами).\n\n"
    "🔔 <b>Платежи</b> — обязательные платежи (аренда, подписки, страховки):\n"
    "• <code>/remind месяц 25 аренда 30000</code>\n"
    "• <code>/remind неделя пн подписка 500</code>\n"
    "• <code>/remind год 15.03 страховка 12000</code>\n\n"
    "⚙️ <b>Настройки</b> — ежедневный отчёт, валюта, экспорт в CSV.\n"
    "↩️ <code>/undo</code> — удалить последнюю запись.\n\n"
    "Все функции доступны кнопками меню снизу."
)


async def _ensure_user(message: Message, db: Db, config: Config):
    return await db.get_or_create_user(
        telegram_id=message.from_user.id,
        full_name=message.from_user.full_name,
        currency=config.default_currency,
        timezone=config.default_timezone,
    )


# ---------- Команды ----------
@router.message(CommandStart())
async def cmd_start(message: Message, db: Db, config: Config):
    await _ensure_user(message, db, config)
    await message.answer(WELCOME, reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP)


@router.message(Command("menu"))
async def cmd_menu(message: Message, db: Db, config: Config):
    await _ensure_user(message, db, config)
    await message.answer("Меню всегда снизу 👇 Выбери, что нужно.", reply_markup=main_menu())


@router.message(Command("balance"))
@router.message(F.text == BTN_BALANCE)
async def cmd_balance(message: Message, db: Db, config: Config):
    user = await _ensure_user(message, db, config)
    await message.answer(await build_balance(db, user.id, user.currency))


@router.message(Command("report"))
@router.message(F.text == BTN_REPORT)
async def cmd_report(message: Message, db: Db, config: Config):
    await _ensure_user(message, db, config)
    await message.answer("За какой период показать отчёт?", reply_markup=report_periods())


@router.message(Command("stats"))
@router.message(F.text == BTN_STATS)
async def cmd_stats(message: Message, db: Db, config: Config):
    user = await _ensure_user(message, db, config)
    await message.answer(await build_report(db, user.id, user.currency, "month"))


@router.message(F.text == BTN_ADD)
async def btn_add(message: Message, db: Db, config: Config):
    await _ensure_user(message, db, config)
    await message.answer(
        "✍️ Просто напиши трату или доход обычным текстом:\n"
        "• <i>кофе 300</i>\n"
        "• <i>такси 450 и обед 600</i>\n"
        "• <i>зарплата 80000</i>\n\n"
        "Или пришли 🎙 голосовое / 📸 фото чека — я распознаю сам.",
        reply_markup=add_hint_menu(),
    )


@router.message(F.text == BTN_HELP)
async def btn_help(message: Message):
    await message.answer(HELP)


@router.message(Command("undo"))
async def cmd_undo(message: Message, db: Db, config: Config):
    user = await _ensure_user(message, db, config)
    tx = await db.delete_last_transaction(user.id)
    if tx is None:
        await message.answer("Нет операций для удаления.")
        return
    await message.answer(
        f"↩️ Удалил: {tx.category} — {fmt_money(tx.amount, tx.currency)}\n"
        f"Новый баланс: {fmt_money(await db.balance(user.id), user.currency)}"
    )


@router.message(Command("advice"))
@router.message(F.text == BTN_ADVICE)
async def cmd_advice(message: Message, db: Db, llm: LLMClient, config: Config):
    user = await _ensure_user(message, db, config)
    await message.bot.send_chat_action(message.chat.id, "typing")
    context = await build_context(db, user.id, user.currency)
    text = await llm.advice(
        "Проанализируй мои финансы за месяц и дай 2-3 практических совета, "
        "где можно оптимизировать расходы.",
        context,
        user.currency,
    )
    await message.answer("💡 " + text)


@router.message(Command("settings"))
@router.message(F.text == BTN_SETTINGS)
async def cmd_settings(message: Message, db: Db, config: Config):
    user = await _ensure_user(message, db, config)
    await message.answer(
        "⚙️ <b>Настройки</b>",
        reply_markup=settings_menu(user.daily_report, user.currency),
    )


@router.message(Command("export"))
async def cmd_export(message: Message, db: Db, config: Config):
    user = await _ensure_user(message, db, config)
    transactions = await db.all_transactions(user.id)
    if not transactions:
        await message.answer("Пока нечего выгружать — нет операций.")
        return
    csv_data = export_csv_rows(transactions).encode("utf-8-sig")
    file = BufferedInputFile(csv_data, filename="finance_export.csv")
    await message.answer_document(file, caption="📤 Все твои операции")


WEEKDAYS = {
    "пн": 0, "понедельник": 0, "вт": 1, "вторник": 1, "ср": 2, "среда": 2,
    "чт": 3, "четверг": 3, "пт": 4, "пятница": 4, "сб": 5, "суббота": 5,
    "вс": 6, "воскресенье": 6,
}
WEEKDAY_NAMES = ["понедельник", "вторник", "среду", "четверг", "пятницу",
                 "субботу", "воскресенье"]
REMIND_HELP = (
    "Обязательные платежи — <code>/remind</code>:\n"
    "• Ежемесячно: <code>/remind месяц 25 аренда 30000</code>\n"
    "• Еженедельно: <code>/remind неделя пн подписка 500</code>\n"
    "• Ежегодно: <code>/remind год 15.03 страховка 12000</code>\n"
    "• Кратко (по умолчанию раз в месяц): <code>/remind 25 аренда 30000</code>"
)


def _split_amount(tokens: list[str]) -> tuple[list[str], float | None]:
    """Отделяет сумму (последний числовой токен) от названия."""
    if tokens and tokens[-1].replace(".", "", 1).replace(",", "", 1).isdigit():
        amount = float(tokens[-1].replace(",", "."))
        return tokens[:-1], amount
    return tokens, None


@router.message(Command("remind"))
async def cmd_remind(message: Message, db: Db, config: Config):
    user = await _ensure_user(message, db, config)
    parts = (message.text or "").split(maxsplit=1)
    tokens = parts[1].split() if len(parts) > 1 else []
    if not tokens:
        await message.answer(REMIND_HELP)
        return

    freq_word = tokens[0].lower()
    frequency = "monthly"
    day_of_month, weekday, month = 1, None, None
    idx = 0

    if freq_word in ("неделя", "неделю", "еженедельно", "week"):
        frequency = "weekly"
        idx = 1
        if len(tokens) > 1 and tokens[1].lower() in WEEKDAYS:
            weekday = WEEKDAYS[tokens[1].lower()]
            idx = 2
        else:
            await message.answer(
                "Укажи день недели. Пример: <code>/remind неделя пн подписка 500</code>"
            )
            return
    elif freq_word in ("год", "ежегодно", "year"):
        frequency = "yearly"
        idx = 1
        if len(tokens) > 1 and "." in tokens[1]:
            try:
                d, m = tokens[1].split(".")[:2]
                day_of_month, month = int(d), int(m)
                idx = 2
            except ValueError:
                await message.answer(
                    "Дата в формате ДД.ММ. Пример: "
                    "<code>/remind год 15.03 страховка 12000</code>"
                )
                return
        else:
            await message.answer(
                "Укажи дату ДД.ММ. Пример: <code>/remind год 15.03 страховка 12000</code>"
            )
            return
    elif freq_word in ("месяц", "ежемесячно", "month"):
        frequency = "monthly"
        idx = 1
        if len(tokens) > 1 and tokens[1].isdigit():
            day_of_month = int(tokens[1])
            idx = 2
    elif freq_word.isdigit():
        frequency = "monthly"
        day_of_month = int(freq_word)
        idx = 1
    else:
        await message.answer(REMIND_HELP)
        return

    rest = tokens[idx:]
    title_tokens, amount = _split_amount(rest)
    title = " ".join(title_tokens) or "Платёж"
    await db.add_reminder(
        user.id, title, amount, frequency=frequency,
        day_of_month=day_of_month, weekday=weekday, month=month,
    )

    amount_str = f" на {fmt_money(amount, user.currency)}" if amount else ""
    when = _describe_frequency(frequency, day_of_month, weekday, month)
    await message.answer(f"🔔 Обязательный платёж создан: <b>{title}</b>{amount_str}\n{when}")


def _describe_frequency(frequency, day_of_month, weekday, month) -> str:
    if frequency == "weekly":
        return f"Каждую {WEEKDAY_NAMES[weekday or 0]}."
    if frequency == "yearly":
        return f"Ежегодно {day_of_month:02d}.{(month or 1):02d}."
    return f"Ежемесячно {min(28, max(1, day_of_month))}-го числа."


@router.message(Command("reminders"))
@router.message(F.text == BTN_PAYMENTS)
async def cmd_reminders(message: Message, db: Db, config: Config):
    user = await _ensure_user(message, db, config)
    reminders = await db.list_reminders(user.id)
    if not reminders:
        await message.answer(
            "🔔 <b>Обязательные платежи</b>\n\nПока список пуст. Добавь платёж кнопкой ниже "
            "или командой:\n\n" + REMIND_HELP,
            reply_markup=payments_menu([]),
        )
        return
    lines = ["🔔 <b>Обязательные платежи:</b>", ""]
    total = 0.0
    for r in reminders:
        amount_str = f" — {fmt_money(r.amount, user.currency)}" if r.amount else ""
        if r.amount and r.frequency == "monthly":
            total += r.amount
        when = _describe_frequency(r.frequency, r.day_of_month, r.weekday, r.month)
        lines.append(f"• <b>{r.title}</b>{amount_str}\n  {when}")
    if total:
        lines.append(f"\n💳 Итого в месяц (ежемесячные): {fmt_money(total, user.currency)}")
    lines.append("\nНажми 🗑, чтобы удалить платёж, или ➕ чтобы добавить.")
    await message.answer("\n".join(lines), reply_markup=payments_menu(reminders))


@router.message(Command("delreminder"))
async def cmd_delreminder(message: Message, db: Db, config: Config):
    user = await _ensure_user(message, db, config)
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Формат: <code>/delreminder ID</code>")
        return
    ok = await db.delete_reminder(user.id, int(parts[1]))
    await message.answer("Удалил ✅" if ok else "Напоминание не найдено.")


async def _dispatch(message, db, llm, user, result, raw_text):
    """Единая обработка результата анализа (для текста, голоса и фото)."""
    intent = result["intent"]

    if intent == "transaction":
        await _save_transactions(message, db, user, result["transactions"], raw_text)
        return

    if intent == "report":
        await message.answer(await build_balance(db, user.id, user.currency))
        await message.answer("Показать подробный отчёт?", reply_markup=report_periods())
        return

    if intent == "question":
        reply = result["reply"]
        if not reply:
            context = await build_context(db, user.id, user.currency)
            reply = await llm.advice(raw_text, context, user.currency)
        await message.answer("💡 " + reply)
        return

    await message.answer(result["reply"] or "Напиши трату, например: «кофе 300» ☕")


# ---------- Свободный текст: главный «мозг» агента ----------
@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, db: Db, llm: LLMClient, config: Config):
    user = await _ensure_user(message, db, config)
    text = message.text.strip()
    await message.bot.send_chat_action(message.chat.id, "typing")
    context = await build_context(db, user.id, user.currency)
    result = await llm.analyze(text, context, user.currency)
    await _dispatch(message, db, llm, user, result, text)


# ---------- Голосовые сообщения ----------
@router.message(F.voice | F.audio)
async def handle_voice(message: Message, bot: Bot, db: Db, llm: LLMClient, config: Config):
    user = await _ensure_user(message, db, config)
    if not getattr(llm, "supports_ai", False) or llm.provider != "openai":
        await message.answer(
            "🎙️ Распознавание голосовых включится после подключения ключа OpenAI. "
            "Пока напиши трату текстом, например: «кофе 300»."
        )
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    voice = message.voice or message.audio
    file = await bot.get_file(voice.file_id)
    buf = await bot.download_file(file.file_path)
    audio_bytes = buf.read()
    try:
        text = await llm.transcribe(audio_bytes, filename="voice.ogg")
    except Exception:
        await message.answer("Не удалось распознать голосовое 😔 Попробуй ещё раз.")
        return
    if not text:
        await message.answer("Кажется, в голосовом ничего не разобрать 🤔")
        return
    await message.answer(f"🎙️ Распознал: «{text}»")
    context = await build_context(db, user.id, user.currency)
    result = await llm.analyze(text, context, user.currency)
    await _dispatch(message, db, llm, user, result, text)


# ---------- Фото чеков ----------
@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot, db: Db, llm: LLMClient, config: Config):
    user = await _ensure_user(message, db, config)
    if not getattr(llm, "supports_ai", False):
        await message.answer(
            "📸 Распознавание фото чеков включится после подключения AI-ключа. "
            "Пока напиши сумму текстом, например: «продукты 1500»."
        )
        return
    await message.bot.send_chat_action(message.chat.id, "typing")
    photo = message.photo[-1]  # самое большое разрешение
    file = await bot.get_file(photo.file_id)
    buf = await bot.download_file(file.file_path)
    image_bytes = buf.read()
    result = await llm.analyze_image(
        image_bytes,
        media_type="image/jpeg",
        context=await build_context(db, user.id, user.currency),
        currency=user.currency,
    )
    caption = message.caption or "чек с фото"
    await _dispatch(message, db, llm, user, result, caption)


async def _save_transactions(message, db, user, transactions, raw_text):
    saved = []
    for tx in transactions:
        obj = await db.add_transaction(
            user_id=user.id,
            kind=tx["kind"],
            amount=tx["amount"],
            currency=user.currency,
            category=tx["category"],
            description=tx["description"],
            op_date=dt.date.today(),
            raw_text=raw_text,
        )
        saved.append(obj)

    lines = []
    for obj in saved:
        arrow = "⬆️" if obj.kind == "income" else "⬇️"
        desc = f" — {obj.description}" if obj.description else ""
        lines.append(
            f"{arrow} {emoji_for(obj.category)} <b>{obj.category}</b>: "
            f"{fmt_money(obj.amount, user.currency)}{desc}"
        )
    balance = await db.balance(user.id)
    lines.append(f"\n💰 Баланс: <b>{fmt_money(balance, user.currency)}</b>")
    await message.answer("\n".join(lines), reply_markup=confirm_delete())


# ---------- Колбэки ----------
@router.callback_query(F.data.startswith("report:"))
async def cb_report(query: CallbackQuery, db: Db, config: Config):
    user = await db.get_or_create_user(
        query.from_user.id, query.from_user.full_name,
        config.default_currency, config.default_timezone,
    )
    period = query.data.split(":", 1)[1]
    await query.message.answer(await build_report(db, user.id, user.currency, period))
    await query.answer()


@router.callback_query(F.data == "tx:delete_last")
async def cb_delete_last(query: CallbackQuery, db: Db, config: Config):
    user = await db.get_or_create_user(
        query.from_user.id, query.from_user.full_name,
        config.default_currency, config.default_timezone,
    )
    tx = await db.delete_last_transaction(user.id)
    if tx is None:
        await query.answer("Нечего удалять")
        return
    await query.message.answer(
        f"↩️ Удалил: {tx.category} — {fmt_money(tx.amount, user.currency)}\n"
        f"Баланс: {fmt_money(await db.balance(user.id), user.currency)}"
    )
    await query.answer("Удалено")


@router.callback_query(F.data == "settings:toggle_daily")
async def cb_toggle_daily(query: CallbackQuery, db: Db, config: Config):
    user = await db.get_or_create_user(
        query.from_user.id, query.from_user.full_name,
        config.default_currency, config.default_timezone,
    )
    new_value = not user.daily_report
    await db.update_user(user.id, daily_report=new_value)
    await query.message.edit_reply_markup(
        reply_markup=settings_menu(new_value, user.currency)
    )
    await query.answer("Готово: " + ("включено" if new_value else "выключено"))


@router.callback_query(F.data == "settings:currency")
async def cb_currency(query: CallbackQuery):
    await query.message.answer(
        "Чтобы сменить валюту, отправь команду: <code>/currency USD</code> "
        "(или EUR, KZT, UAH и т.д.)"
    )
    await query.answer()


@router.callback_query(F.data == "settings:help")
async def cb_help(query: CallbackQuery):
    await query.message.answer(HELP)
    await query.answer()


@router.callback_query(F.data == "report:advice")
async def cb_report_advice(query: CallbackQuery, db: Db, llm: LLMClient, config: Config):
    user = await db.get_or_create_user(
        query.from_user.id, query.from_user.full_name,
        config.default_currency, config.default_timezone,
    )
    await query.answer("Анализирую…")
    context = await build_context(db, user.id, user.currency)
    text = await llm.advice(
        "Проанализируй мои расходы и подскажи 2-3 конкретных места, где можно сэкономить.",
        context,
        user.currency,
    )
    await query.message.answer("💡 " + text)


# ---- Управление обязательными платежами через кнопки ----
@router.callback_query(F.data.startswith("pay:del:"))
async def cb_pay_delete(query: CallbackQuery, db: Db, config: Config):
    user = await db.get_or_create_user(
        query.from_user.id, query.from_user.full_name,
        config.default_currency, config.default_timezone,
    )
    reminder_id = int(query.data.split(":")[2])
    ok = await db.delete_reminder(user.id, reminder_id)
    if not ok:
        await query.answer("Платёж не найден")
        return
    reminders = await db.list_reminders(user.id)
    await query.message.edit_reply_markup(reply_markup=payments_menu(reminders))
    await query.answer("Платёж удалён ✅")


@router.callback_query(F.data.startswith("pay:add:"))
async def cb_pay_add(query: CallbackQuery):
    kind = query.data.split(":")[2]
    templates = {
        "monthly": (
            "Добавить <b>ежемесячный</b> платёж — скопируй и поправь:\n"
            "<code>/remind месяц 25 аренда 30000</code>\n"
            "(25 — день месяца, аренда — название, 30000 — сумма)"
        ),
        "weekly": (
            "Добавить <b>еженедельный</b> платёж:\n"
            "<code>/remind неделя пн подписка 500</code>\n"
            "(пн — день недели: пн/вт/ср/чт/пт/сб/вс)"
        ),
        "yearly": (
            "Добавить <b>ежегодный</b> платёж:\n"
            "<code>/remind год 15.03 страховка 12000</code>\n"
            "(15.03 — дата ДД.ММ)"
        ),
    }
    await query.message.answer(templates.get(kind, REMIND_HELP))
    await query.answer()


@router.callback_query(F.data == "add:voice")
async def cb_add_voice(query: CallbackQuery):
    await query.message.answer(
        "🎙 Запиши голосовое сообщение с тратой, например: «потратил на продукты 1500». "
        "Я расшифрую и запишу (нужен ключ OpenAI)."
    )
    await query.answer()


@router.callback_query(F.data == "add:photo")
async def cb_add_photo(query: CallbackQuery):
    await query.message.answer(
        "📸 Пришли фото чека — я распознаю сумму и категорию (нужен AI-ключ)."
    )
    await query.answer()


@router.callback_query(F.data == "settings:export")
async def cb_export(query: CallbackQuery, db: Db, config: Config):
    user = await db.get_or_create_user(
        query.from_user.id, query.from_user.full_name,
        config.default_currency, config.default_timezone,
    )
    transactions = await db.all_transactions(user.id)
    if not transactions:
        await query.answer("Нет операций для выгрузки")
        return
    csv_data = export_csv_rows(transactions).encode("utf-8-sig")
    file = BufferedInputFile(csv_data, filename="finance_export.csv")
    await query.message.answer_document(file, caption="📤 Все твои операции")
    await query.answer()


@router.message(Command("currency"))
async def cmd_currency(message: Message, db: Db, config: Config):
    user = await _ensure_user(message, db, config)
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Формат: <code>/currency USD</code>")
        return
    currency = parts[1].strip().upper()[:8]
    await db.update_user(user.id, currency=currency)
    await message.answer(f"💱 Валюта изменена на <b>{currency}</b>")
