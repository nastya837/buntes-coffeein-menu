"""Загрузка конфигурации из переменных окружения."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    llm_provider: str
    anthropic_api_key: str
    anthropic_model: str
    openai_api_key: str
    openai_model: str
    default_currency: str
    default_timezone: str
    daily_report_hour: int
    database_path: str

    @classmethod
    def from_env(cls) -> "Config":
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise RuntimeError(
                "Не задан BOT_TOKEN. Скопируй .env.example в .env и заполни его."
            )

        provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
        if provider not in ("anthropic", "openai"):
            raise RuntimeError("LLM_PROVIDER должен быть 'anthropic' или 'openai'.")

        # Ключ LLM необязателен: без него бот работает в базовом режиме
        # (простой разбор трат по тексту), а AI-функции включатся после
        # добавления ключа в .env.
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()

        try:
            hour = int(os.getenv("DAILY_REPORT_HOUR", "20"))
        except ValueError:
            hour = 20
        hour = max(0, min(23, hour))

        return cls(
            bot_token=bot_token,
            llm_provider=provider,
            anthropic_api_key=anthropic_key,
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8").strip(),
            openai_api_key=openai_key,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
            default_currency=os.getenv("DEFAULT_CURRENCY", "EUR").strip().upper(),
            default_timezone=os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow").strip(),
            daily_report_hour=hour,
            database_path=os.getenv("DATABASE_PATH", "data/finance.db").strip(),
        )
