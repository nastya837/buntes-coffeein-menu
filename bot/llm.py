"""LLM-слой: разбор сообщений и финансовые советы.

Поддерживает двух провайдеров — Anthropic (Claude) и OpenAI — выбор через конфиг.
Агент решает, что делать с сообщением пользователя: записать операции,
показать отчёт или ответить на финансовый вопрос.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from .categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES
from .config import Config

# JSON-схема ответа агента при разборе сообщения.
ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["transaction", "question", "report", "smalltalk"],
            "description": (
                "transaction — пользователь сообщает о доходах/расходах; "
                "question — задаёт финансовый вопрос или просит совет; "
                "report — просит показать баланс/статистику/отчёт; "
                "smalltalk — приветствие или сообщение не по теме финансов."
            ),
        },
        "transactions": {
            "type": "array",
            "description": "Список операций, если intent=transaction. Иначе пустой.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": ["income", "expense"]},
                    "amount": {
                        "type": "number",
                        "description": "Положительная сумма операции.",
                    },
                    "category": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "Короткое описание операции.",
                    },
                },
                "required": ["kind", "amount", "category", "description"],
            },
        },
        "reply": {
            "type": "string",
            "description": (
                "Короткий ответ пользователю для intent=question/smalltalk. "
                "Для transaction/report можно оставить пустым."
            ),
        },
    },
    "required": ["intent", "transactions", "reply"],
}


def _system_prompt(currency: str) -> str:
    return (
        "Ты — финансовый ассистент в Telegram. Помогаешь пользователю вести учёт "
        "личных доходов и расходов, отвечаешь на вопросы про бюджет, накопления и "
        "инвестиции простым языком.\n\n"
        "Твоя задача — проанализировать сообщение пользователя и вернуть строго JSON "
        "по заданной схеме.\n\n"
        "Правила:\n"
        "1. Если пользователь сообщает о тратах или доходах (например «кофе 300», "
        "«такси 450 и обед 600», «зарплата 80000»), поставь intent=transaction и "
        "заполни массив transactions. В одном сообщении может быть несколько операций.\n"
        "2. Определи тип: расход (expense) или доход (income). Слова вроде «зарплата», "
        "«аванс», «премия», «вернули», «получил» обычно означают доход.\n"
        f"3. amount — положительное число в валюте {currency}. Не добавляй знак валюты.\n"
        "4. Подбери категорию из списка. Для расходов: "
        f"{', '.join(EXPENSE_CATEGORIES)}. Для доходов: {', '.join(INCOME_CATEGORIES)}. "
        "Если ничего не подходит — «Прочее».\n"
        "5. Если пользователь задаёт вопрос про финансы, просит совет или анализ — "
        "intent=question, дай полезный, доброжелательный и конкретный ответ в поле reply "
        "(используй данные о его финансах из контекста, если они есть).\n"
        "6. Если просит показать баланс, отчёт, статистику, сколько потратил — "
        "intent=report (массив transactions пустой, reply пустой).\n"
        "7. Приветствие или не по теме — intent=smalltalk с дружелюбным reply.\n"
        "Отвечай на русском. Возвращай только JSON, без пояснений."
    )


def _advice_system_prompt(currency: str) -> str:
    return (
        "Ты — персональный финансовый консультант в Telegram. Отвечай на русском, "
        "по делу, дружелюбно и практично. Опирайся на реальные данные пользователя, "
        "которые тебе передают. Давай конкретные рекомендации: где можно сэкономить, "
        "на что обратить внимание, как оптимизировать бюджет. Не выдумывай цифры, "
        f"которых нет в данных. Валюта пользователя — {currency}. "
        "Не давай советов по конкретным ценным бумагам как инвестиционную рекомендацию — "
        "говори про общие принципы. Пиши компактно, можно использовать эмодзи и списки."
    )


class LLMClient:
    """Единый интерфейс к Claude или OpenAI."""

    supports_ai = True

    def __init__(self, config: Config):
        self.config = config
        self.provider = config.llm_provider
        if self.provider == "anthropic":
            from anthropic import AsyncAnthropic

            self._anthropic = AsyncAnthropic(api_key=config.anthropic_api_key)
            self._model = config.anthropic_model
        else:
            from openai import AsyncOpenAI

            self._openai = AsyncOpenAI(api_key=config.openai_api_key)
            self._model = config.openai_model

    async def analyze(self, text: str, context: str, currency: str) -> dict[str, Any]:
        """Разбирает сообщение пользователя, возвращает структуру по ANALYSIS_SCHEMA."""
        system = _system_prompt(currency)
        user_content = (
            f"Сегодня {dt.date.today().isoformat()}.\n"
            f"Контекст по финансам пользователя:\n{context}\n\n"
            f"Сообщение пользователя:\n{text}"
        )
        try:
            if self.provider == "anthropic":
                raw = await self._anthropic_json(system, user_content)
            else:
                raw = await self._openai_json(system, user_content)
            data = json.loads(raw)
        except Exception:
            # Фолбэк: если LLM недоступен или вернул мусор — считаем это вопросом
            return {
                "intent": "smalltalk",
                "transactions": [],
                "reply": (
                    "Не удалось обработать сообщение 😔 Попробуй ещё раз или напиши "
                    "трату в формате «кофе 300»."
                ),
            }
        return self._normalize(data)

    async def advice(self, question: str, context: str, currency: str) -> str:
        """Свободный ответ финансового консультанта на вопрос пользователя."""
        system = _advice_system_prompt(currency)
        user_content = (
            f"Данные о финансах пользователя:\n{context}\n\n"
            f"Вопрос пользователя:\n{question}"
        )
        try:
            if self.provider == "anthropic":
                return await self._anthropic_text(system, user_content)
            return await self._openai_text(system, user_content)
        except Exception:
            return "Сейчас не получилось ответить 😔 Попробуй, пожалуйста, чуть позже."

    # ---- Anthropic ----
    async def _anthropic_json(self, system: str, user_content: str) -> str:
        resp = await self._anthropic.messages.create(
            model=self._model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            output_config={
                "format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA}
            },
        )
        return next(b.text for b in resp.content if b.type == "text")

    async def _anthropic_text(self, system: str, user_content: str) -> str:
        resp = await self._anthropic.messages.create(
            model=self._model,
            max_tokens=1200,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    # ---- OpenAI ----
    async def _openai_json(self, system: str, user_content: str) -> str:
        resp = await self._openai.chat.completions.create(
            model=self._model,
            max_tokens=1500,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": system
                    + "\nСхема JSON: "
                    + json.dumps(ANALYSIS_SCHEMA, ensure_ascii=False),
                },
                {"role": "user", "content": user_content},
            ],
        )
        return resp.choices[0].message.content or "{}"

    async def _openai_text(self, system: str, user_content: str) -> str:
        resp = await self._openai.chat.completions.create(
            model=self._model,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

    # ---- Голосовые сообщения ----
    async def transcribe(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        """Расшифровывает аудио в текст (только OpenAI Whisper)."""
        if self.provider != "openai":
            raise RuntimeError("Транскрипция доступна только с провайдером OpenAI.")
        import io

        buf = io.BytesIO(audio_bytes)
        buf.name = filename
        resp = await self._openai.audio.transcriptions.create(
            model="whisper-1", file=buf
        )
        return (resp.text or "").strip()

    # ---- Фото чеков (vision) ----
    async def analyze_image(
        self, image_bytes: bytes, media_type: str, context: str, currency: str
    ) -> dict[str, Any]:
        """Распознаёт чек на фото и возвращает операции по ANALYSIS_SCHEMA."""
        import base64

        b64 = base64.standard_b64encode(image_bytes).decode()
        system = _system_prompt(currency)
        instruction = (
            "На изображении — чек или скриншот оплаты. Извлеки итоговую сумму "
            "(или суммы) и определи категорию. Верни JSON по схеме. "
            "Обычно это один расход на итоговую сумму чека."
        )
        try:
            if self.provider == "anthropic":
                resp = await self._anthropic.messages.create(
                    model=self._model,
                    max_tokens=1200,
                    system=system,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": b64,
                                    },
                                },
                                {"type": "text", "text": instruction},
                            ],
                        }
                    ],
                    output_config={
                        "format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA}
                    },
                )
                raw = next(b.text for b in resp.content if b.type == "text")
            else:
                resp = await self._openai.chat.completions.create(
                    model=self._model,
                    max_tokens=1200,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": system
                            + "\nСхема JSON: "
                            + json.dumps(ANALYSIS_SCHEMA, ensure_ascii=False),
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": instruction},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{media_type};base64,{b64}"
                                    },
                                },
                            ],
                        },
                    ],
                )
                raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
        except Exception:
            return {
                "intent": "smalltalk",
                "transactions": [],
                "reply": "Не удалось распознать чек на фото 😔 Попробуй ещё раз.",
            }
        return self._normalize(data)

    # ---- Валидация ----
    @staticmethod
    def _normalize(data: dict[str, Any]) -> dict[str, Any]:
        intent = data.get("intent", "smalltalk")
        if intent not in ("transaction", "question", "report", "smalltalk"):
            intent = "smalltalk"
        txs = []
        for item in data.get("transactions", []) or []:
            try:
                amount = abs(float(item.get("amount", 0)))
            except (TypeError, ValueError):
                continue
            if amount <= 0:
                continue
            kind = item.get("kind", "expense")
            kind = "income" if kind == "income" else "expense"
            txs.append(
                {
                    "kind": kind,
                    "amount": round(amount, 2),
                    "category": (item.get("category") or "Прочее").strip()[:64],
                    "description": (item.get("description") or "").strip()[:255],
                }
            )
        # Если модель сказала transaction, но операций нет — это, скорее, вопрос
        if intent == "transaction" and not txs:
            intent = "question"
        return {
            "intent": intent,
            "transactions": txs,
            "reply": (data.get("reply") or "").strip(),
        }
