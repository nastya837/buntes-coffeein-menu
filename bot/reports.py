"""Формирование отчётов и текстовых сводок по финансам."""
from __future__ import annotations

import calendar
import datetime as dt

from .categories import emoji_for
from .database import Db


def fmt_money(amount: float, currency: str) -> str:
    """Форматирует сумму: 1234.5 -> '1 234,50 RUB'."""
    sign = "-" if amount < 0 else ""
    value = abs(amount)
    whole = f"{int(value):,}".replace(",", " ")
    frac = f"{value - int(value):.2f}"[2:]
    return f"{sign}{whole},{frac} {currency}"


def period_bounds(period: str, today: dt.date | None = None) -> tuple[dt.date, dt.date, str]:
    """Возвращает (начало, конец, подпись) для 'today'/'week'/'month'/'year'."""
    today = today or dt.date.today()
    if period == "today":
        return today, today, "сегодня"
    if period == "week":
        start = today - dt.timedelta(days=today.weekday())
        return start, today, "за неделю"
    if period == "year":
        return dt.date(today.year, 1, 1), today, f"за {today.year} год"
    # month по умолчанию
    start = today.replace(day=1)
    return start, today, "за месяц"


async def build_report(db: Db, user_id: int, currency: str, period: str) -> str:
    start, end, label = period_bounds(period)
    income, expense = await db.period_totals(user_id, start, end)
    net = income - expense

    lines = [f"📊 <b>Отчёт {label}</b> ({start.strftime('%d.%m')}–{end.strftime('%d.%m')})", ""]
    lines.append(f"⬆️ Доходы:  <b>{fmt_money(income, currency)}</b>")
    lines.append(f"⬇️ Расходы: <b>{fmt_money(expense, currency)}</b>")
    balance_emoji = "✅" if net >= 0 else "⚠️"
    lines.append(f"{balance_emoji} Итого:   <b>{fmt_money(net, currency)}</b>")

    breakdown = await db.category_breakdown(user_id, "expense", start, end)
    if breakdown:
        lines.append("")
        lines.append("<b>Расходы по категориям:</b>")
        for category, amount in breakdown[:12]:
            share = (amount / expense * 100) if expense else 0
            lines.append(
                f"{emoji_for(category)} {category}: "
                f"{fmt_money(amount, currency)} ({share:.0f}%)"
            )
    else:
        lines.append("")
        lines.append("Пока нет расходов за этот период.")

    return "\n".join(lines)


async def build_balance(db: Db, user_id: int, currency: str) -> str:
    balance = await db.balance(user_id)
    today = dt.date.today()
    m_start = today.replace(day=1)
    income, expense = await db.period_totals(user_id, m_start, today)
    return (
        f"💰 <b>Текущий баланс:</b> {fmt_money(balance, currency)}\n\n"
        f"За текущий месяц:\n"
        f"⬆️ Доходы: {fmt_money(income, currency)}\n"
        f"⬇️ Расходы: {fmt_money(expense, currency)}"
    )


async def build_context(db: Db, user_id: int, currency: str) -> str:
    """Короткая сводка для передачи в LLM (для вопросов и советов)."""
    today = dt.date.today()
    balance = await db.balance(user_id)
    m_start = today.replace(day=1)
    income, expense = await db.period_totals(user_id, m_start, today)
    breakdown = await db.category_breakdown(user_id, "expense", m_start, today)

    parts = [
        f"Валюта: {currency}.",
        f"Общий баланс: {balance:.2f}.",
        f"За текущий месяц доходы: {income:.2f}, расходы: {expense:.2f}.",
    ]
    if breakdown:
        cats = ", ".join(f"{c}: {a:.0f}" for c, a in breakdown[:10])
        parts.append(f"Расходы по категориям за месяц: {cats}.")
    else:
        parts.append("Операций за текущий месяц пока нет.")
    return " ".join(parts)


def export_csv_rows(transactions) -> str:
    """CSV-строка со всеми операциями (для /export)."""
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Дата", "Тип", "Сумма", "Валюта", "Категория", "Описание"])
    for t in transactions:
        writer.writerow(
            [
                t.op_date.isoformat(),
                "Доход" if t.kind == "income" else "Расход",
                f"{t.amount:.2f}",
                t.currency,
                t.category,
                t.description,
            ]
        )
    return buf.getvalue()
