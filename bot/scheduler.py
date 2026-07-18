"""Планировщик: ежедневные отчёты и напоминания об обязательных платежах.

Работает без привязки к времени пользователя на сервере: каждый час проверяет
локальное время каждого пользователя и отправляет отчёт/напоминания в нужный час.
"""
from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import Config
from .database import Db
from .reports import build_report, fmt_money

logger = logging.getLogger(__name__)

REMINDER_HOUR = 10  # в какой локальный час слать напоминания о платежах


def _local_now(timezone: str) -> dt.datetime:
    try:
        return dt.datetime.now(ZoneInfo(timezone))
    except Exception:
        return dt.datetime.now(ZoneInfo("Europe/Moscow"))


async def _hourly_tick(bot: Bot, db: Db, config: Config) -> None:
    """Раз в час: рассылает то, что подошло по локальному времени пользователей."""
    # Ежедневные отчёты
    for user in await db.users_with_daily_report():
        now = _local_now(user.timezone)
        if now.hour != config.daily_report_hour:
            continue
        try:
            report = await build_report(db, user.id, user.currency, "today")
            await bot.send_message(user.id, "🌙 Итоги дня\n\n" + report)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось отправить отчёт %s: %s", user.id, exc)

    # Напоминания об обязательных платежах (UTC-дата берётся по локальной дате юзера)
    utc_today = dt.datetime.now(dt.timezone.utc).date()
    # соберём кандидатов на «вчера/сегодня/завтра», чтобы учесть смещения зон
    candidate_days = {
        utc_today - dt.timedelta(days=1),
        utc_today,
        utc_today + dt.timedelta(days=1),
    }
    reminders: list = []
    for day in candidate_days:
        reminders.extend(await db.reminders_due(day))

    for rem in reminders:
        user = await db.get_user(rem.user_id)
        if user is None:
            continue
        now = _local_now(user.timezone)
        # шлём только если у пользователя сейчас нужный час И платёж приходится на сегодня
        if now.hour != REMINDER_HOUR:
            continue
        if not _due_today_local(rem, now.date()):
            continue
        amount = f" — {fmt_money(rem.amount, user.currency)}" if rem.amount else ""
        try:
            await bot.send_message(
                user.id,
                f"🔔 Напоминание: сегодня платёж «<b>{rem.title}</b>»{amount}.\n"
                f"Когда оплатишь — просто напиши мне об этом, и я запишу расход.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось отправить напоминание %s: %s", user.id, exc)


def _due_today_local(rem, local_date: dt.date) -> bool:
    if rem.frequency == "weekly":
        return rem.weekday == local_date.weekday()
    if rem.frequency == "yearly":
        return rem.month == local_date.month and rem.day_of_month == local_date.day
    return rem.day_of_month == local_date.day


def setup_scheduler(bot: Bot, db: Db, config: Config) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _hourly_tick,
        trigger="cron",
        minute=0,
        args=(bot, db, config),
        id="hourly_tick",
        replace_existing=True,
    )
    return scheduler
