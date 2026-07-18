#!/usr/bin/env bash
# Локальный запуск финансового бота (macOS / Linux).
# Делает всё сам: окружение, зависимости, запуск.
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ Python 3 не найден."
  echo "   Установи его: brew install python   (или скачай с https://www.python.org/downloads/)"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "📦 Создаю виртуальное окружение…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "📥 Устанавливаю зависимости (первый раз ~1–2 минуты)…"
pip install -q --upgrade pip
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  Создан файл .env — открой его и впиши свои BOT_TOKEN и OPENAI_API_KEY."
  echo "    Открыть в редакторе:  open -e .env"
  echo "    Потом снова запусти:  ./run_local.sh"
  exit 1
fi

if grep -q "123456:AA" .env || grep -q "^BOT_TOKEN=$" .env; then
  echo "⚠️  Похоже, в .env ещё не вписан твой BOT_TOKEN. Открой: open -e .env"
  exit 1
fi

echo "🚀 Запускаю бота… Останови сочетанием Ctrl+C."
echo "   Когда увидишь «Бот запущен» — пиши боту /start в Telegram."
exec python -m bot.main
