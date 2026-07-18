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
        input_field_placeholder="Например: кофе 300 или зарплата 80000",
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


def add_hint_menu() -> InlineKeyboardMarkup:
    """Подсказки-примеры для добавления траты (нажми — скопируется в поле ввода)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎙 Голосом", callback_data="add:voice")],
            [InlineKeyboardButton(text="📸 Фото чека", callback_data="add:photo")],
        ]
    )
