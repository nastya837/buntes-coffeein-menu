# 🤖💰 Финансовый агент для Telegram

Личный финансовый ассистент в Telegram: ведёт учёт доходов и расходов, сам
определяет категорию, показывает отчёты и статистику, напоминает об
обязательных платежах и даёт советы, где можно сэкономить.

Работает **24/7 на сервере** — без привязки к твоему компьютеру.

---

## Что умеет

| Функция | Как пользоваться |
|---|---|
| **Учёт трат и доходов** | Пиши обычным текстом: `кофе 300`, `такси 450 и обед 600`, `зарплата 80000`. Бот сам определит категорию и посчитает баланс. |
| **Голосовые сообщения** 🎙️ | Наговори трату голосом — бот расшифрует и запишет *(нужен ключ OpenAI)*. |
| **Фото чека** 📸 | Пришли фото чека — бот распознает сумму и категорию *(нужен ключ OpenAI/Claude)*. |
| **Баланс** | `/balance` или кнопка «💰 Баланс». |
| **Отчёты** | `/report` — за день / неделю / месяц / год, с разбивкой по категориям. |
| **Статистика** | `/stats` — куда уходит больше всего денег за месяц. |
| **Графики** 📊 | Круговая диаграмма расходов, траты по дням и сравнение с прошлым месяцем — картинкой прямо в чате (кнопки под `/report`). |
| **Лимиты** 🚦 | Задай бюджет на категорию (напр. «Кафе 300/мес») — бот предупредит при 80% и превышении. `/limits` или ⚙️ Настройки → 🚦 Лимиты. |
| **Советы** 💡 | Спроси «где я перетрачиваю?», «как накопить на отпуск?» — ответит с учётом твоих данных *(нужен AI-ключ)*. |
| **Обязательные платежи** 🔔 | Пошагово кнопками (🔔 Платежи → ➕) или командой `/remind` — раз в неделю / месяц / год (аренда, подписки, страховки). Бот напомнит в нужный день. |
| **Ежедневный отчёт** | Включается в `/settings` — итоги дня приходят вечером. |
| **Экспорт** | `/export` — все операции в CSV (Excel). |
| **Отмена** | `/undo` — удалить последнюю запись. |

### Примеры обязательных платежей
```
/remind месяц 25 аренда 30000        # каждое 25-е число
/remind неделя пн подписка 500       # каждый понедельник
/remind год 15.03 страховка 12000    # раз в год, 15 марта
/remind 10 интернет 800              # кратко: раз в месяц, 10-го
/reminders                           # список всех платежей
```

---

## Как это работает

- **Python + aiogram 3** — Telegram-бот.
- **SQLite** — хранение операций (файл `data/finance.db`).
- **LLM (Claude или OpenAI)** — «мозг» агента: понимает сообщения, определяет
  категории, распознаёт голос и чеки, даёт советы.
- **APScheduler** — ежедневные отчёты и напоминания.

### Режим без AI-ключа
Бот **работает сразу**, даже без ключа OpenAI/Claude: понимает записи вида
`кофе 300` по встроенным правилам. Как только добавишь ключ в `.env` и
перезапустишь — включатся умные функции: голос, фото чеков, умная
категоризация и советы.

---

## 🚀 Запуск на сервере 24/7 (рекомендуется — Docker)

Нужен любой VPS с Linux (Ubuntu/Debian) и установленным Docker.

```bash
# 1. Клонируем проект на сервер
git clone https://github.com/nastya837/buntes-coffeein-menu.git
cd buntes-coffeein-menu

# 2. Создаём файл с настройками из примера
cp .env.example .env
nano .env        # вставь BOT_TOKEN (обязательно) и, при желании, ключ OpenAI

# 3. Запускаем
docker compose up -d --build

# Логи
docker compose logs -f

# Обновить после изменений
git pull && docker compose up -d --build
```

`restart: always` в `docker-compose.yml` гарантирует, что бот сам поднимется
после перезагрузки сервера или сбоя. База данных сохраняется в папке `data/`.

---

## Альтернатива: запуск через systemd (без Docker)

```bash
# На сервере
sudo useradd -r -s /bin/false finance
sudo mkdir -p /opt/finance-agent
sudo git clone https://github.com/nastya837/buntes-coffeein-menu.git /opt/finance-agent
cd /opt/finance-agent

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env && nano .env      # заполни BOT_TOKEN
sudo chown -R finance:finance /opt/finance-agent

# Ставим сервис автозапуска
sudo cp deploy/finance-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now finance-agent

# Статус и логи
systemctl status finance-agent
journalctl -u finance-agent -f
```

---

## Локальный запуск (для проверки)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # впиши BOT_TOKEN
python -m bot.main
```

---

## Где взять ключи

- **Токен бота** — у [@BotFather](https://t.me/BotFather): `/newbot` → скопируй токен в `BOT_TOKEN`.
- **Ключ OpenAI** — на platform.openai.com → API keys. Впиши в `OPENAI_API_KEY`,
  оставь `LLM_PROVIDER=openai`.
- **Ключ Claude (Anthropic)** — на console.anthropic.com. Впиши в `ANTHROPIC_API_KEY`
  и поставь `LLM_PROVIDER=anthropic`.

После добавления ключа перезапусти бота (`docker compose up -d` или
`systemctl restart finance-agent`).

---

## Настройки (`.env`)

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен Telegram-бота (обязательно). |
| `LLM_PROVIDER` | `openai` или `anthropic`. |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Ключ выбранного провайдера (можно позже). |
| `OPENAI_MODEL` / `ANTHROPIC_MODEL` | Модель. Для экономии: `gpt-4o-mini` / `claude-haiku-4-5`. |
| `DEFAULT_CURRENCY` | Валюта по умолчанию (`RUB`, `USD`, `EUR`…). |
| `DEFAULT_TIMEZONE` | Часовой пояс для отчётов (`Europe/Moscow`). |
| `DAILY_REPORT_HOUR` | Час ежедневного отчёта (0–23). |
| `DATABASE_PATH` | Путь к базе (по умолчанию `data/finance.db`). |

> ⚠️ Файл `.env` содержит секреты и **не** попадает в git (см. `.gitignore`).

---

## Структура проекта

```
bot/
  main.py          # точка входа, запуск бота и планировщика
  config.py        # чтение настроек из .env
  database.py      # модели и работа с SQLite
  llm.py           # AI-слой (Claude/OpenAI): разбор, голос, фото, советы
  fallback.py      # базовый разбор трат без AI-ключа
  handlers.py      # обработчики сообщений и кнопок
  keyboards.py     # клавиатуры
  reports.py       # отчёты и форматирование
  scheduler.py     # ежедневные отчёты и напоминания
  categories.py    # категории доходов/расходов
Dockerfile
docker-compose.yml
deploy/finance-agent.service   # автозапуск через systemd
```
