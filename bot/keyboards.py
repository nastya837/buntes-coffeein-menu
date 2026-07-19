"""Клавиатуры бота — чтобы все функции были под рукой."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# Тексты кнопок нижнего меню (используются и в клавиатуре, и в обработчиках)
BTN_BALANCE = "💰 Баланс"
BTN_REPORT = "📊 Отчёт"
BTN_STATS = "📈 Статистика"
BTN_PAYMENTS = "🔔 Платежи"
BTN_ADVICE = "💡 Совет"
BTN_SETTINGS = "⚙️ Настройки"
BTN_ADD = "➕ Добавить трату"
BTN_HELP = "❓ Помощь"


def main_menu() -> ReplyKeyboardMarkup:
    """Постоянное нижнее меню — всегда под рукой."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_BALANCE), KeyboardButton(text=BTN_REPORT)],
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_PAYMENTS)],
            [KeyboardButton(text=BTN_ADVICE), KeyboardButton(text=BTN_SETTINGS)],
            [KeyboardButton(text=BTN_ADD), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Например: кофе 3 или зарплата 3000",
    )


def report_periods() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Сегодня", callback_data="report:today"),
                InlineKeyboardButton(text="🗓 Неделя", callback_data="report:week"),
            ],
            [
                InlineKeyboardButton(text="📆 Месяц", callback_data="report:month"),
                InlineKeyboardButton(text="🗂 Год", callback_data="report:year"),
            ],
            [
                InlineKeyboardButton(
                    text="📊 Диаграмма расходов", callback_data="chart:month"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 Траты по дням", callback_data="chart:daily"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📈 Сравнить с прошлым месяцем", callback_data="chart:compare"
                )
            ],
            [InlineKeyboardButton(text="💡 Совет по расходам", callback_data="report:advice")],
        ]
    )


def settings_menu(daily_on: bool, currency: str) -> InlineKeyboardMarkup:
    daily_label = "🔔 Ежедневный отчёт: ВКЛ" if daily_on else "🔕 Ежедневный отчёт: ВЫКЛ"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=daily_label, callback_data="settings:toggle_daily")],
            [
                InlineKeyboardButton(
                    text=f"💱 Валюта: {currency}", callback_data="settings:currency"
                )
            ],
            [InlineKeyboardButton(text="📤 Экспорт в CSV", callback_data="settings:export")],
            [InlineKeyboardButton(text="❓ Помощь", callback_data="settings:help")],
        ]
    )


def confirm_delete() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ Отменить последнюю запись", callback_data="tx:delete_last"
                )
            ]
        ]
    )


def payments_menu(reminders) -> InlineKeyboardMarkup:
    """Меню обязательных платежей: список с кнопками удаления + кнопки добавления."""
    rows = []
    for r in reminders:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 {r.title}", callback_data=f"pay:del:{r.id}"
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="➕ Ежемесячный", callback_data="pay:add:monthly"),
            InlineKeyboardButton(text="➕ Еженедельный", callback_data="pay:add:weekly"),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="➕ Ежегодный", callback_data="pay:add:yearly")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_with_limits(daily_on: bool, currency: str) -> InlineKeyboardMarkup:
    kb = settings_menu(daily_on, currency)
    kb.inline_keyboard.insert(
        2,
        [InlineKeyboardButton(text="🚦 Лимиты по категориям", callback_data="lim:open")],
    )
    return kb


def payment_freq_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📆 Раз в месяц", callback_data="payadd:monthly")],
            [InlineKeyboardButton(text="🗓 Раз в неделю", callback_data="payadd:weekly")],
            [InlineKeyboardButton(text="🗂 Раз в год", callback_data="payadd:yearly")],
        ]
    )


def payment_amount_skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Без суммы", callback_data="payadd:noamount")],
            [InlineKeyboardButton(text="✖️ Отмена", callback_data="payadd:cancel")],
        ]
    )


def weekday_kb() -> InlineKeyboardMarkup:
    names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    row1 = [InlineKeyboardButton(text=n, callback_data=f"payday:wd:{i}") for i, n in enumerate(names[:4])]
    row2 = [InlineKeyboardButton(text=n, callback_data=f"payday:wd:{i+4}") for i, n in enumerate(names[4:])]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2,
        [InlineKeyboardButton(text="✖️ Отмена", callback_data="payadd:cancel")]])


def month_day_kb() -> InlineKeyboardMarkup:
    days = [1, 5, 10, 15, 20, 25, 28]
    rows = []
    row = []
    for d in days:
        row.append(InlineKeyboardButton(text=str(d), callback_data=f"payday:dom:{d}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✏️ Другое число", callback_data="payday:other")])
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="payadd:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def limit_categories_kb(categories: list[str]) -> InlineKeyboardMarkup:
    rows, row = [], []
    for c in categories:
        row.append(InlineKeyboardButton(text=c, callback_data=f"lim:cat:{c}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="payadd:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def limits_menu(budgets) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"🗑 {b.category}", callback_data=f"lim:del:{b.id}")]
        for b in budgets
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить лимит", callback_data="lim:add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def add_hint_menu() -> InlineKeyboardMarkup:
    """Подсказки-примеры для добавления траты (нажми — скопируется в поле ввода)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎙 Голосом", callback_data="add:voice")],
            [InlineKeyboardButton(text="📸 Фото чека", callback_data="add:photo")],
        ]
    )
