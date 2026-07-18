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


def prev_month_bounds(today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    """Границы предыдущего месяца."""
    today = today or dt.date.today()
    first_this = today.replace(day=1)
    last_prev = first_this - dt.timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev, last_prev


async def build_month_comparison(db: Db, user_id: int, currency: str):
    """Сравнение расходов текущего месяца с прошлым.

    Возвращает (текст, labels, prev_values, cur_values) для графика.
    """
    today = dt.date.today()
    cur_start = today.replace(day=1)
    prev_start, prev_end = prev_month_bounds(today)

    _, cur_exp = await db.period_totals(user_id, cur_start, today)
    _, prev_exp = await db.period_totals(user_id, prev_start, prev_end)

    cur_break = dict(await db.category_breakdown(user_id, "expense", cur_start, today))
    prev_break = dict(await db.category_breakdown(user_id, "expense", prev_start, prev_end))

    # Топ-категории по сумме за оба месяца
    cats = sorted(
        set(cur_break) | set(prev_break),
        key=lambda c: cur_break.get(c, 0) + prev_break.get(c, 0),
        reverse=True,
    )[:6]
    labels = cats
    prev_values = [prev_break.get(c, 0) for c in cats]
    cur_values = [cur_break.get(c, 0) for c in cats]

    diff = cur_exp - prev_exp
    if prev_exp > 0:
        pct = diff / prev_exp * 100
        trend = f"{'📈 больше' if diff > 0 else '📉 меньше'} на {abs(pct):.0f}%"
    else:
        trend = "нет данных за прошлый месяц"

    lines = [
        "📈 <b>Сравнение с прошлым месяцем</b>", "",
        f"Прошлый месяц: {fmt_money(prev_exp, currency)}",
        f"Текущий месяц: {fmt_money(cur_exp, currency)}",
        f"Итого: {trend}",
    ]
    # Категории с самым большим ростом
    growth = []
    for c in cats:
        d = cur_break.get(c, 0) - prev_break.get(c, 0)
        if d > 0:
            growth.append((c, d))
    growth.sort(key=lambda x: x[1], reverse=True)
    if growth:
        lines.append("")
        lines.append("<b>Где стала тратить больше:</b>")
        for c, d in growth[:3]:
            lines.append(f"{emoji_for(c)} {c}: +{fmt_money(d, currency)}")

    return "\n".join(lines), labels, prev_values, cur_values


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
