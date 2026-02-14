# Piper TTS Service для Render.com
FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Скачивание модели Piper (medium quality для баланса скорость/качество)
RUN mkdir -p /app/models && \
    wget -O /app/models/en_US-amy-medium.onnx \
    https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx && \
    wget -O /app/models/en_US-amy-medium.onnx.json \
    https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx.json

# Копирование кода приложения
COPY . .

# Expose порт
EXPOSE 8000

# Запуск FastAPI сервиса
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
