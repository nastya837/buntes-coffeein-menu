FROM python:3.11-slim

# Debian slim-образ не содержит UTF-8 локали, из-за чего Python может
# по умолчанию использовать ASCII для текста (падает на кириллице —
# например, при расшифровке голосовых сообщений). Форсируем UTF-8 везде.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/

# Каталог для базы данных (монтируется как volume)
RUN mkdir -p /app/data

CMD ["python", "-m", "bot.main"]
