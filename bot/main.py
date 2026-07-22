"""Точка входа: запуск Telegram-бота (long polling)."""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from .config import Config
from .database import Db
from .handlers import router
from .scheduler import setup_scheduler

# На всякий случай явно переключаем stdout/stderr в UTF-8: в некоторых
# окружениях (например, минимальный Docker-образ без локали) Python может
# по умолчанию выбрать ASCII, и тогда логирование кириллицы падает с
# UnicodeEncodeError. reconfigure появился в Python 3.7+.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("finance-agent")


def build_llm(config: Config):
    """Возвращает LLM-клиент, а если ключа нет — простую заглушку-парсер."""
    has_key = (
        config.llm_provider == "anthropic" and config.anthropic_api_key
    ) or (config.llm_provider == "openai" and config.openai_api_key)
    if has_key:
        from .llm import LLMClient

        logger.info("LLM: %s (%s)", config.llm_provider, "ключ найден")
        return LLMClient(config)

    from .fallback import FallbackLLM

    logger.warning("LLM-ключ не задан — работаю в базовом режиме (без AI).")
    return FallbackLLM()


async def main() -> None:
    config = Config.from_env()

    db = Db(config.database_path)
    await db.init()

    llm = build_llm(config)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Зависимости, доступные в хендлерах как аргументы
    dp["db"] = db
    dp["llm"] = llm
    dp["config"] = config

    # Меню команд в Telegram (кнопка «/» и «Меню»)
    await bot.set_my_commands(
        [
            BotCommand(command="menu", description="🏠 Главное меню"),
            BotCommand(command="balance", description="💰 Баланс"),
            BotCommand(command="report", description="📊 Отчёт"),
            BotCommand(command="stats", description="📈 Статистика за месяц"),
            BotCommand(command="advice", description="💡 Совет по расходам"),
            BotCommand(command="reminders", description="🔔 Обязательные платежи"),
            BotCommand(command="limits", description="🚦 Лимиты по категориям"),
            BotCommand(command="settings", description="⚙️ Настройки"),
            BotCommand(command="currency", description="💱 Сменить валюту"),
            BotCommand(command="timezone", description="🕒 Часовой пояс"),
            BotCommand(command="export", description="📤 Экспорт в CSV"),
            BotCommand(command="undo", description="↩️ Удалить последнюю запись"),
            BotCommand(command="help", description="❓ Помощь"),
        ]
    )

    scheduler = setup_scheduler(bot, db, config)
    scheduler.start()

    me = await bot.get_me()
    logger.info("Бот запущен: @%s (id=%s)", me.username, me.id)

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановлено.")
