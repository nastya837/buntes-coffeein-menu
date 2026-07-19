"""Обработчики сообщений и колбэков Telegram."""
from __future__ import annotations

import datetime as dt

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from .categories import EXPENSE_CATEGORIES, emoji_for
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
    limit_categories_kb,
    limits_menu,
    main_menu,
    month_day_kb,
    payment_amount_skip_kb,
    payments_menu,
    report_periods,
    settings_menu,
    settings_with_limits,
    weekday_kb,
)
from .llm import LLMClient
from .states import AddLimit, AddPayment
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
    "• <i>кофе 3</i>\n"
    "• <i>такси 12 и обед 20</i>\n"
    "• <i>зарплата 3000</i>\n\n"
    "Я сам определю категорию и посчитаю баланс. А ещё умею:\n"
    "🎙 распознавать голосовые и 📸 фото чеков\n"
    "📊 показывать отчёты и статистику\n"
    "🔔 напоминать об обязательных платежах\n"
    "💡 давать финансовые советы — просто спроси\n\n"
    "👇 Пользуйся кнопками меню снизу — там всё под рукой."
)

HELP = (
    "<b>Что я умею</b> 👇\n\n"
    "✍️ <b>Учёт.</b> Пиши операции текстом: «кофе 3», «зарплата 3000», "
    "«такси 12 и обед 20». Можно 🎙 голосом или 📸 фото чека.\n\n"
    "💰 <b>Баланс</b> — сколько сейчас на руках.\n"
    "📊 <b>Отчёт</b> — за день / неделю / месяц / год.\n"
    "📈 <b>Статистика</b> — куда уходит больше всего денег.\n"
    "💡 <b>Совет</b> — где можно сэкономить (спроси своими словами).\n\n"
    "🔔 <b>Платежи</b> — обязательные платежи (аренда, подписки, страховки). "
    "Добавляй пошагово кнопками: 🔔 Платежи → ➕.\n\n"
    "🚦 <b>Лимиты</b> — задай бюджет на категорию (⚙️ Настройки → 🚦 Лимиты). "
    "Предупрежу при 80% и превышении.\n\n"
    "📊 <b>Графики</b> — под /report: диаграмма расходов, траты по дням, "
    "сравнение с прошлым месяцем.\n\n"
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
    await _send_expense_pie(message, db, user, "month")


async def _send_expense_pie(message_or_query, db, user, period: str):
    """Строит и отправляет круговую диаграмму расходов за период."""
    from .charts import expense_pie
    from .reports import period_bounds

    start, end, label = period_bounds(period)
    breakdown = await db.category_breakdown(user.id, "expense", start, end)
    png = expense_pie(breakdown, user.currency, f"Расходы {label}")
    target = getattr(message_or_query, "message", message_or_query)
    if png is None:
        await target.answer("Пока нет расходов, чтобы построить диаграмму 🤷")
        return
    photo = BufferedInputFile(png, filename="expenses.png")
    await target.answer_photo(photo, caption=f"📊 Куда уходят деньги ({label})")


@router.message(F.text == BTN_ADD)
async def btn_add(message: Message, db: Db, config: Config):
    await _ensure_user(message, db, config)
    await message.answer(
        "✍️ Просто напиши трату или доход обычным текстом:\n"
        "• <i>кофе 3</i>\n"
        "• <i>такси 12 и обед 20</i>\n"
        "• <i>зарплата 3000</i>\n\n"
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
        reply_markup=settings_with_limits(user.daily_report, user.currency),
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
    "• Ежемесячно: <code>/remind месяц 25 аренда 1200</code>\n"
    "• Еженедельно: <code>/remind неделя пн подписка 10</code>\n"
    "• Ежегодно: <code>/remind год 15.03 страховка 300</code>\n"
    "• Кратко (по умолчанию раз в месяц): <code>/remind 25 аренда 1200</code>"
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
@router.message(StateFilter(None), F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, db: Db, llm: LLMClient, config: Config):
    user = await _ensure_user(message, db, config)
    text = message.text.strip()
    await message.bot.send_chat_action(message.chat.id, "typing")
    context = await build_context(db, user.id, user.currency)
    result = await llm.analyze(text, context, user.currency)
    await _dispatch(message, db, llm, user, result, text)


# ---------- Голосовые сообщения ----------
@router.message(StateFilter(None), F.voice | F.audio)
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
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("finance-agent").warning(
            "Transcribe failed (%s): %s", type(exc).__name__, exc
        )
        await message.answer(
            "Не удалось распознать голосовое 😔 Возможно, недоступен ключ OpenAI или "
            "закончились средства. Пока напиши трату текстом, например «кофе 3»."
        )
        return
    if not text:
        await message.answer("Кажется, в голосовом ничего не разобрать 🤔")
        return
    await message.answer(f"🎙️ Распознал: «{text}»")
    context = await build_context(db, user.id, user.currency)
    result = await llm.analyze(text, context, user.currency)
    await _dispatch(message, db, llm, user, result, text)


# ---------- Фото чеков ----------
@router.message(StateFilter(None), F.photo)
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

    # Предупреждения по лимитам категорий
    warnings = await _budget_warnings(db, user, {t["category"] for t in transactions
                                                 if t["kind"] == "expense"})
    if warnings:
        lines.append("")
        lines.extend(warnings)

    await message.answer("\n".join(lines), reply_markup=confirm_delete())


async def _budget_warnings(db, user, categories) -> list[str]:
    """Возвращает строки-предупреждения, если траты приблизились к лимиту или превысили его."""
    today = dt.date.today()
    start = today.replace(day=1)
    out = []
    for category in categories:
        budget = await db.get_budget(user.id, category)
        if not budget:
            continue
        spent = await db.category_spent(user.id, category, start, today)
        share = spent / budget.amount if budget.amount else 0
        if share >= 1.0:
            over = spent - budget.amount
            out.append(
                f"🔴 Лимит по «{category}» превышен! "
                f"{fmt_money(spent, user.currency)} из {fmt_money(budget.amount, user.currency)} "
                f"(+{fmt_money(over, user.currency)})"
            )
        elif share >= 0.8:
            out.append(
                f"🟡 По «{category}» уже {share*100:.0f}% лимита "
                f"({fmt_money(spent, user.currency)} из {fmt_money(budget.amount, user.currency)})"
            )
    return out


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


@router.callback_query(F.data == "chart:month")
async def cb_chart_month(query: CallbackQuery, db: Db, config: Config):
    user = await db.get_or_create_user(
        query.from_user.id, query.from_user.full_name,
        config.default_currency, config.default_timezone,
    )
    await query.answer("Строю диаграмму…")
    await _send_expense_pie(query, db, user, "month")


@router.callback_query(F.data == "chart:compare")
async def cb_chart_compare(query: CallbackQuery, db: Db, config: Config):
    user = await db.get_or_create_user(
        query.from_user.id, query.from_user.full_name,
        config.default_currency, config.default_timezone,
    )
    await query.answer("Сравниваю месяцы…")
    from .charts import month_compare_bar
    from .reports import build_month_comparison

    text, labels, prev_v, cur_v = await build_month_comparison(db, user.id, user.currency)
    await query.message.answer(text)
    png = month_compare_bar(
        labels, prev_v, cur_v, user.currency, "Расходы: прошлый vs текущий месяц"
    )
    if png:
        photo = BufferedInputFile(png, filename="compare.png")
        await query.message.answer_photo(photo)


@router.callback_query(F.data == "chart:daily")
async def cb_chart_daily(query: CallbackQuery, db: Db, config: Config):
    user = await db.get_or_create_user(
        query.from_user.id, query.from_user.full_name,
        config.default_currency, config.default_timezone,
    )
    await query.answer("Строю график по дням…")
    from .charts import daily_line

    today = dt.date.today()
    start = today.replace(day=1)
    totals = dict(await db.daily_expense_totals(user.id, start, today))
    days = list(range(1, today.day + 1))
    values = [totals.get(dt.date(today.year, today.month, d), 0.0) for d in days]
    if not any(values):
        await query.message.answer("За этот месяц ещё нет расходов для графика 🤷")
        return
    avg = sum(values) / len([v for v in values]) if values else 0
    png = daily_line(days, values, user.currency, "Траты по дням (текущий месяц)", avg)
    if png:
        await query.message.answer_photo(
            BufferedInputFile(png, filename="daily.png"),
            caption="📅 Динамика трат по дням",
        )


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
        reply_markup=settings_with_limits(new_value, user.currency)
    )
    await query.answer("Готово: " + ("включено" if new_value else "выключено"))


@router.callback_query(F.data == "settings:currency")
async def cb_currency(query: CallbackQuery):
    await query.message.answer(
        "Чтобы сменить валюту, отправь команду: <code>/currency EUR</code> "
        "(или USD, GBP, PLN и т.д.)"
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


# ==================================================================
#  Пошаговое добавление обязательного платежа (кнопками, FSM)
# ==================================================================
FREQ_TITLES = {"monthly": "ежемесячный", "weekly": "еженедельный", "yearly": "ежегодный"}


@router.callback_query(F.data.startswith("pay:add:"))
async def cb_pay_add(query: CallbackQuery, state: FSMContext):
    freq = query.data.split(":")[2]
    await state.clear()
    await state.update_data(frequency=freq)
    await state.set_state(AddPayment.title)
    await query.message.answer(
        f"➕ Новый <b>{FREQ_TITLES.get(freq, '')}</b> платёж.\n\n"
        f"Шаг 1/3. Как называется? Напиши, например: <i>Аренда</i>"
    )
    await query.answer()


@router.message(AddPayment.title)
async def fsm_payment_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()[:255]
    if not title:
        await message.answer("Напиши название платежа текстом 🙂")
        return
    await state.update_data(title=title)
    await state.set_state(AddPayment.amount)
    await message.answer(
        "Шаг 2/3. Какая сумма? Напиши число (например <i>1200</i>) "
        "или нажми кнопку.",
        reply_markup=payment_amount_skip_kb(),
    )


def _parse_number(text: str):
    cleaned = (text or "").strip().replace(" ", "").replace(",", ".")
    cleaned = cleaned.rstrip("€$₽").strip()
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


@router.message(AddPayment.amount)
async def fsm_payment_amount(message: Message, state: FSMContext):
    amount = _parse_number(message.text or "")
    if amount is None:
        await message.answer(
            "Не понял сумму. Напиши число, например <i>1200</i>, или нажми «Без суммы».",
            reply_markup=payment_amount_skip_kb(),
        )
        return
    await state.update_data(amount=amount)
    await _ask_payment_day(message, state)


@router.callback_query(AddPayment.amount, F.data == "payadd:noamount")
async def cb_payment_noamount(query: CallbackQuery, state: FSMContext):
    await state.update_data(amount=None)
    await _ask_payment_day(query.message, state)
    await query.answer()


async def _ask_payment_day(message, state: FSMContext):
    data = await state.get_data()
    freq = data["frequency"]
    await state.set_state(AddPayment.day)
    if freq == "weekly":
        await message.answer("Шаг 3/3. В какой день недели?", reply_markup=weekday_kb())
    elif freq == "yearly":
        await message.answer(
            "Шаг 3/3. Укажи дату в формате <b>ДД.ММ</b> (например <i>15.03</i>)."
        )
    else:  # monthly
        await message.answer("Шаг 3/3. Какого числа каждый месяц?", reply_markup=month_day_kb())


@router.callback_query(AddPayment.day, F.data.startswith("payday:wd:"))
async def cb_payment_weekday(query: CallbackQuery, state: FSMContext, db: Db, config: Config):
    weekday = int(query.data.split(":")[2])
    await _finalize_payment(query.message, state, db, config, query.from_user,
                            weekday=weekday)
    await query.answer()


@router.callback_query(AddPayment.day, F.data.startswith("payday:dom:"))
async def cb_payment_dom(query: CallbackQuery, state: FSMContext, db: Db, config: Config):
    day = int(query.data.split(":")[2])
    await _finalize_payment(query.message, state, db, config, query.from_user,
                            day_of_month=day)
    await query.answer()


@router.callback_query(AddPayment.day, F.data == "payday:other")
async def cb_payment_other_day(query: CallbackQuery, state: FSMContext):
    await state.update_data(await_text_day=True)
    await query.message.answer("Введи число месяца от 1 до 28:")
    await query.answer()


@router.message(AddPayment.day)
async def fsm_payment_day_text(message: Message, state: FSMContext, db: Db, config: Config):
    data = await state.get_data()
    freq = data["frequency"]
    text = (message.text or "").strip()
    if freq == "yearly":
        if "." not in text:
            await message.answer("Формат даты: <b>ДД.ММ</b>, например 15.03")
            return
        try:
            d, m = text.split(".")[:2]
            day, month = int(d), int(m)
            assert 1 <= month <= 12
        except (ValueError, AssertionError):
            await message.answer("Не понял дату. Пример: <i>15.03</i>")
            return
        await _finalize_payment(message, state, db, config, message.from_user,
                                day_of_month=day, month=month)
    else:  # monthly text day
        if not text.isdigit():
            await message.answer("Введи число от 1 до 28.")
            return
        await _finalize_payment(message, state, db, config, message.from_user,
                                day_of_month=int(text))


async def _finalize_payment(message, state, db, config, tg_user,
                            day_of_month=1, weekday=None, month=None):
    data = await state.get_data()
    user = await db.get_or_create_user(
        tg_user.id, tg_user.full_name, config.default_currency, config.default_timezone
    )
    await db.add_reminder(
        user.id, data["title"], data.get("amount"),
        frequency=data["frequency"], day_of_month=day_of_month,
        weekday=weekday, month=month,
    )
    await state.clear()
    amount_str = (
        f" на {fmt_money(data['amount'], user.currency)}" if data.get("amount") else ""
    )
    when = _describe_frequency(data["frequency"], day_of_month, weekday, month)
    await message.answer(
        f"✅ Готово! Платёж «<b>{data['title']}</b>»{amount_str} добавлен.\n{when}",
        reply_markup=main_menu(),
    )


@router.callback_query(F.data == "payadd:cancel")
async def cb_payadd_cancel(query: CallbackQuery, state: FSMContext):
    await state.clear()
    await query.message.answer("Отменил ✖️", reply_markup=main_menu())
    await query.answer()


# ==================================================================
#  Лимиты по категориям
# ==================================================================
async def _show_limits(target, db, user):
    budgets = await db.list_budgets(user.id)
    today = dt.date.today()
    start = today.replace(day=1)
    if not budgets:
        await target.answer(
            "🚦 <b>Лимиты по категориям</b>\n\nПока лимитов нет. Задай бюджет на категорию "
            "(напр. «Кафе и рестораны — 300/мес»), и я предупрежу при превышении.",
            reply_markup=limits_menu([]),
        )
        return
    lines = ["🚦 <b>Лимиты по категориям (за месяц):</b>", ""]
    for b in budgets:
        spent = await db.category_spent(user.id, b.category, start, today)
        share = spent / b.amount if b.amount else 0
        bar = _progress_bar(share)
        icon = "🔴" if share >= 1 else ("🟡" if share >= 0.8 else "🟢")
        lines.append(
            f"{icon} <b>{b.category}</b>\n"
            f"{bar} {fmt_money(spent, user.currency)} / {fmt_money(b.amount, user.currency)}"
        )
    await target.answer("\n".join(lines), reply_markup=limits_menu(budgets))


def _progress_bar(share: float, width: int = 10) -> str:
    filled = min(width, int(round(share * width)))
    return "▰" * filled + "▱" * (width - filled)


@router.message(Command("limits"))
async def cmd_limits(message: Message, db: Db, config: Config):
    user = await _ensure_user(message, db, config)
    await _show_limits(message, db, user)


@router.callback_query(F.data == "lim:open")
async def cb_lim_open(query: CallbackQuery, db: Db, config: Config):
    user = await db.get_or_create_user(
        query.from_user.id, query.from_user.full_name,
        config.default_currency, config.default_timezone,
    )
    await _show_limits(query.message, db, user)
    await query.answer()


@router.callback_query(F.data == "lim:add")
async def cb_lim_add(query: CallbackQuery):
    await query.message.answer(
        "Выбери категорию, для которой задать лимит:",
        reply_markup=limit_categories_kb(EXPENSE_CATEGORIES),
    )
    await query.answer()


@router.callback_query(F.data.startswith("lim:cat:"))
async def cb_lim_cat(query: CallbackQuery, state: FSMContext):
    category = query.data.split(":", 2)[2]
    await state.clear()
    await state.update_data(category=category)
    await state.set_state(AddLimit.amount)
    await query.message.answer(
        f"Какой месячный лимит на «<b>{category}</b>»? Напиши сумму, например <i>300</i>."
    )
    await query.answer()


@router.message(AddLimit.amount)
async def fsm_limit_amount(message: Message, state: FSMContext, db: Db, config: Config):
    amount = _parse_number(message.text or "")
    if amount is None:
        await message.answer("Напиши сумму числом, например <i>300</i>.")
        return
    data = await state.get_data()
    user = await _ensure_user(message, db, config)
    await db.set_budget(user.id, data["category"], amount)
    await state.clear()
    await message.answer(
        f"✅ Лимит на «<b>{data['category']}</b>» — {fmt_money(amount, user.currency)}/мес. "
        f"Предупрежу при 80% и превышении."
    )
    await _show_limits(message, db, user)


@router.callback_query(F.data.startswith("lim:del:"))
async def cb_lim_del(query: CallbackQuery, db: Db, config: Config):
    user = await db.get_or_create_user(
        query.from_user.id, query.from_user.full_name,
        config.default_currency, config.default_timezone,
    )
    budget_id = int(query.data.split(":")[2])
    await db.delete_budget(user.id, budget_id)
    budgets = await db.list_budgets(user.id)
    await query.message.edit_reply_markup(reply_markup=limits_menu(budgets))
    await query.answer("Лимит удалён ✅")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("Нечего отменять 🙂", reply_markup=main_menu())
        return
    await state.clear()
    await message.answer("Отменил ✖️", reply_markup=main_menu())


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
        await message.answer("Формат: <code>/currency EUR</code>")
        return
    currency = parts[1].strip().upper()[:8]
    await db.update_user(user.id, currency=currency)
    await message.answer(f"💱 Валюта изменена на <b>{currency}</b>")


@router.message(Command("timezone"))
async def cmd_timezone(message: Message, db: Db, config: Config):
    user = await _ensure_user(message, db, config)
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer(
            "Формат: <code>/timezone Europe/Berlin</code>\n"
            "Примеры: Europe/Berlin, Europe/Paris, Europe/Warsaw, Europe/Lisbon"
        )
        return
    tz = parts[1].strip()
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(tz)  # проверка, что зона существует
    except Exception:
        await message.answer(
            "Не знаю такой часовой пояс 🤔 Пример: <code>/timezone Europe/Berlin</code>"
        )
        return
    await db.update_user(user.id, timezone=tz)
    await message.answer(
        f"🕒 Часовой пояс: <b>{tz}</b>. Теперь отчёты и напоминания — по этому времени."
    )
