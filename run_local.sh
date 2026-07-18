#!/usr/bin/env bash
# Локальный запуск финансового бота (macOS / Linux).
# Делает всё сам: окружение, зависимости, запуск.
set -e
cd "$(dirname "$0")"

# Ищем подходящий Python (нужен 3.10+)
PY=""
PYVER=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    ver=$("$c" -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "")
    [ -z "$ver" ] && continue
    minor=${ver#*.}
    if [ "${ver%%.*}" -eq 3 ] && [ "$minor" -ge 10 ]; then
      PY="$c"; PYVER="$ver"; break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "❌ Нужен Python 3.10 или новее (сейчас доступен только старый)."
  echo ""
  echo "   Установи Python 3.11:"
  echo "     brew install python@3.11"
  echo ""
  echo "   Если Homebrew не установлен, сначала выполни:"
  echo '     /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  echo ""
  echo "   Потом снова запусти:  bash run_local.sh"
  exit 1
fi
echo "🐍 Использую $PY (Python $PYVER)"

# Пересоздаём окружение, если оно было собрано на несовместимой версии
if [ -d ".venv" ] && [ ! -x ".venv/bin/python" ]; then
  rm -rf .venv
fi
if [ ! -d ".venv" ]; then
  echo "📦 Создаю виртуальное окружение…"
  "$PY" -m venv .venv
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
