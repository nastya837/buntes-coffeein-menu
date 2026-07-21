#!/usr/bin/env bash
# Автообновление бота: если на GitHub появились новые коммиты в текущей ветке —
# подтягивает их и пересобирает контейнер. Запускается по расписанию (cron).
set -e
cd "$(dirname "$0")"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git fetch origin "$BRANCH" -q

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" != "$REMOTE" ]; then
  echo "$(date '+%F %T') | Найдено обновление ($LOCAL -> $REMOTE), обновляю…"
  git pull --ff-only origin "$BRANCH"
  docker compose up -d --build
  echo "$(date '+%F %T') | Готово."
else
  echo "$(date '+%F %T') | Обновлений нет."
fi
