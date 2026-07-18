FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/

# Каталог для базы данных (монтируется как volume)
RUN mkdir -p /app/data

CMD ["python", "-m", "bot.main"]
