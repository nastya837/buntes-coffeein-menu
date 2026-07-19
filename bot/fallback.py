"""Простой разбор сообщений без LLM.

Работает, пока не подключён ключ OpenAI/Anthropic: понимает записи вида
«кофе 300», «такси 450 обед 600», «зарплата 80000» с помощью правил и
словаря ключевых слов. Умные функции (голос, фото, советы) при этом
сообщают, что заработают после подключения ключа.
"""
from __future__ import annotations

import re
from typing import Any

# Ключевые слова -> категория расходов
EXPENSE_KEYWORDS: dict[str, list[str]] = {
    "Продукты": ["продукт", "магазин", "супермаркет", "пятёроч", "пятероч", "ашан",
                 "лента", "перекрёсток", "перекресток", "еда домой", "овощи", "молоко",
                 "хлеб", "мясо", "вкусвилл", "магнит"],
    "Кафе и рестораны": ["кофе", "кафе", "ресторан", "обед", "ужин", "завтрак", "бар",
                          "старбакс", "кофейн", "фастфуд", "макдак", "kfc", "бургер",
                          "пицц", "суши", "доставка еды", "перекус", "капучино", "капуч",
                          "латте", "эспрессо", "американо", "раф", "флэт", "мокко",
                          "чай", "круассан", "десерт", "мороженое", "шаверм", "шаурм"],
    "Транспорт": ["такси", "метро", "автобус", "бензин", "заправк", "парковк",
                  "проезд", "трамвай", "самокат", "каршеринг", "uber", "яндекс такси"],
    "Жильё": ["аренда", "квартплата", "ипотек", "квартира", "жильё", "жилье"],
    "Коммунальные": ["коммуналк", "жкх", "электричеств", "газ", "вода", "отоплен"],
    "Здоровье": ["аптек", "лекарств", "врач", "клиник", "анализ", "стоматолог",
                 "таблетк", "витамин"],
    "Одежда": ["одежд", "обувь", "куртк", "джинс", "футболк", "кросс", "платье"],
    "Развлечения": ["кино", "театр", "концерт", "игр", "развлеч", "клуб", "боулинг"],
    "Образование": ["курс", "обучен", "книг", "учеб", "репетитор", "семинар"],
    "Путешествия": ["билет", "отель", "путешеств", "поездк", "тур", "авиабилет",
                    "гостиниц"],
    "Подарки": ["подар", "цвет", "сувенир"],
    "Связь и интернет": ["связь", "интернет", "мобильн", "телефон", "тариф", "мтс",
                          "билайн", "мегафон", "теле2"],
    "Подписки": ["подписк", "netflix", "spotify", "youtube", "яндекс плюс", "иви",
                 "кинопоиск"],
    "Спорт": ["спорт", "зал", "фитнес", "тренировк", "бассейн"],
    "Дети": ["ребён", "ребен", "детск", "садик", "школа", "игрушк"],
}

INCOME_KEYWORDS: dict[str, list[str]] = {
    "Зарплата": ["зарплат", "зп", "оклад", "получк"],
    "Аванс": ["аванс"],
    "Фриланс": ["фриланс", "подработк", "заказ", "проект"],
    "Бизнес": ["бизнес", "выручк", "продаж"],
    "Подарок": ["подарили", "подарок деньг"],
    "Инвестиции": ["дивиденд", "процент", "вклад", "инвест"],
    "Возврат": ["вернул", "возврат", "кэшбэк", "кешбэк"],
    "Премия": ["преми"],
}

INCOME_TRIGGERS = ["зарплат", "аванс", "премия", "премии", "получил", "получила",
                   "вернул", "доход", "выручк", "дивиденд", "кэшбэк", "кешбэк",
                   "подарили деньги", "пришло на карту", "фриланс", "подработ"]

# Пара «слово + число [множитель] [валюта]» — для нескольких трат в сообщении.
# Группы: (название) (число) (множитель тыс/к/k)
PAIR_RE = re.compile(
    r"([а-яёa-z][а-яёa-z\s]*?)\s*"
    r"(\d[\d\s]*(?:[.,]\d+)?)\s*"
    r"(тыс|к|k)?\s*"
    r"(?:евро|eur|€|руб\.?|р\.?|₽|rub|\$|usd|доллар\w*)?\b",
    re.IGNORECASE,
)
LEADING_JUNK_RE = re.compile(r"^(и|а|ещё|еще|плюс|на|за)\s+", re.IGNORECASE)

# «число [валюта] [на/за] слово» — для фраз вида «3 евро на капучино», «5 на обед»
NUM_FIRST_RE = re.compile(
    r"(\d[\d\s]*(?:[.,]\d+)?)\s*"
    r"(тыс|к|k)?\s*"
    r"(?:евро|eur|€|руб\.?|р\.?|₽|\$|доллар\w*|usd)?\s*"
    r"(?:на|за|для)?\s*"
    r"([а-яёa-z][а-яёa-z]+)",
    re.IGNORECASE,
)


def _parse_amount(raw: str, multiplier_token: str = "") -> float | None:
    cleaned = raw.strip().replace(" ", "").replace(",", ".")
    multiplier = 1000.0 if multiplier_token else 1.0
    try:
        return round(float(cleaned) * multiplier, 2)
    except ValueError:
        return None


def _categorize(word: str, is_income: bool) -> str:
    word = word.lower()
    table = INCOME_KEYWORDS if is_income else EXPENSE_KEYWORDS
    for category, keys in table.items():
        if any(k in word for k in keys):
            return category
    return "Прочее"


class FallbackLLM:
    """Заглушка LLM с тем же интерфейсом, что и LLMClient."""

    supports_ai = False

    async def analyze(self, text: str, context: str, currency: str) -> dict[str, Any]:
        lowered = text.lower()

        # Явный запрос отчёта
        if any(w in lowered for w in ["баланс", "отчёт", "отчет", "статистик",
                                      "сколько потрат", "сколько у меня"]):
            return {"intent": "report", "transactions": [], "reply": ""}

        pairs = PAIR_RE.findall(text)
        transactions = []
        for word, amount_raw, mult in pairs:
            word = word.strip(" ,.-—").strip()
            word = LEADING_JUNK_RE.sub("", word).strip()
            amount = _parse_amount(amount_raw, mult)
            if not word or amount is None or amount <= 0:
                continue
            # доход определяем по слову рядом с суммой или по общему тону сообщения
            is_income = any(t in word.lower() for t in INCOME_TRIGGERS) or (
                len(pairs) == 1 and any(t in lowered for t in INCOME_TRIGGERS)
            )
            transactions.append(
                {
                    "kind": "income" if is_income else "expense",
                    "amount": amount,
                    "category": _categorize(word, is_income),
                    "description": word[:255],
                }
            )

        # Если «слово+число» ничего не дало — пробуем «число+слово»
        # (например «3 евро на капучино», «5 на обед»)
        if not transactions:
            for amount_raw, mult, word in NUM_FIRST_RE.findall(text):
                word = LEADING_JUNK_RE.sub("", word.strip()).strip()
                amount = _parse_amount(amount_raw, mult)
                if not word or amount is None or amount <= 0:
                    continue
                if word.lower() in ("евро", "eur", "руб", "usd", "доллар", "долларов"):
                    continue  # это валюта, а не категория
                is_income = any(t in word.lower() for t in INCOME_TRIGGERS) or any(
                    t in lowered for t in INCOME_TRIGGERS
                )
                transactions.append(
                    {
                        "kind": "income" if is_income else "expense",
                        "amount": amount,
                        "category": _categorize(word, is_income),
                        "description": word[:255],
                    }
                )

        if transactions:
            return {"intent": "transaction", "transactions": transactions, "reply": ""}

        # Не смогли распарсить как трату — считаем вопросом/small talk
        return {
            "intent": "smalltalk",
            "transactions": [],
            "reply": (
                "Пока я работаю в базовом режиме (без AI-ключа) и понимаю записи вида "
                "«кофе 300» или «зарплата 80000». Умные советы, распознавание голосовых "
                "и фото чеков включатся, как только будет добавлен ключ OpenAI 🔑"
            ),
        }

    async def advice(self, question: str, context: str, currency: str) -> str:
        return (
            "💡 Совет с учётом твоих данных станет доступен после подключения ключа "
            "OpenAI. А пока подсказка по данным:\n\n" + context + "\n\n"
            "Посмотри /report — я покажу, на какие категории уходит больше всего."
        )
