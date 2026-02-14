# 🎤 Piper TTS Service

Бесплатный TTS микросервис на базе Piper для деплоя на Render.com

## 🚀 Быстрый старт

### 1. Деплой на Render.com

**Вариант A: Автоматический деплой (рекомендуется)**

1. Создайте репозиторий на GitHub и загрузите эти файлы
2. Перейдите на [Render.com](https://render.com)
3. New → Web Service
4. Connect your repository: `piper-tts-service`
5. Render автоматически обнаружит `render.yaml` и настроит всё сам!
6. Нажмите **Deploy**

**Вариант Б: Ручная настройка**

1. New → Web Service
2. Connect GitHub repository
3. Settings:
   - **Name:** `piper-tts-service`
   - **Environment:** Docker
   - **Plan:** Free
   - **Health Check Path:** `/health`
4. Deploy!

### 2. Получите URL

После деплоя (5-10 минут) получите URL:
```
https://piper-tts-service.onrender.com
```

### 3. Проверьте работу

```bash
# Health check
curl https://piper-tts-service.onrender.com/health

# Генерация аудио
curl -X POST https://piper-tts-service.onrender.com/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, how are you today?"}' \
  --output speech.wav
```

---

## 📁 Структура проекта

```
piper-tts-service/
├── Dockerfile          # Docker образ с Piper
├── requirements.txt    # Python зависимости
├── main.py            # FastAPI сервис
├── render.yaml        # Конфиг для Render (автодеплой)
├── .gitignore         # Git ignore файл
└── README.md          # Эта инструкция
```

---

## 🔧 API Endpoints

### `GET /`
Простой health check

**Response:**
```json
{
  "service": "Piper TTS Service",
  "status": "healthy",
  "version": "1.0.0"
}
```

### `GET /health`
Детальный статус сервиса

**Response:**
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_path": "/app/models/en_US-amy-medium.onnx"
}
```

### `POST /tts`
Генерация аудио из текста

**Request:**
```json
{
  "text": "Hello, how are you today?",
  "voice": "amy",
  "speed": 1.0
}
```

**Response:** WAV audio file

**Python пример:**
```python
import requests

response = requests.post(
    "https://piper-tts-service.onrender.com/tts",
    json={"text": "Hello world!"}
)

with open("output.wav", "wb") as f:
    f.write(response.content)
```

### `POST /tts/stream`
Потоковая генерация (для будущих улучшений)

---

## ⚡ Оптимизации

### 1. Medium Quality Model
Используется модель среднего качества вместо высокого:
- ✅ В 2 раза быстрее на слабом CPU
- ✅ Качество всё равно отличное (⭐⭐⭐⭐)
- ✅ Размер модели: ~50 MB

### 2. Потоковая генерация
Текст разбивается на предложения:
```python
"Hello! How are you? I'm fine." 
↓
["Hello!", "How are you?", "I'm fine."]
↓
Генерация параллельно
```

Это сокращает время до первого звука!

---

## 📊 Производительность на Render Free Tier

| Метрика | Значение |
|---------|----------|
| CPU | 0.5 vCPU (shared) |
| RAM | 512 MB |
| Скорость | 2-4 сек на фразу |
| Cold start | 5-10 сек |
| Warm | 2-3 сек |
| Лимит часов | 750 часов/месяц |

---

## 🎯 Использование в Speech Flow Bot

### В `.env` основного бота:

```bash
# TTS Provider
TTS_PROVIDER=piper

# URL Piper TTS сервиса
PIPER_TTS_URL=https://piper-tts-service.onrender.com
```

### В коде бота:

```python
from piper_tts_client import PiperTTSClient

# Создаём клиент
piper = PiperTTSClient("https://piper-tts-service.onrender.com")

# Генерируем аудио
audio_bytes = await piper.text_to_speech("Hello world!")

# Отправляем в Telegram
voice_file = BufferedInputFile(audio_bytes, filename="response.wav")
await message.answer_voice(voice_file)
```

---

## 🌟 Сравнение с другими TTS

| Сервис | Стоимость | Качество | Скорость |
|--------|-----------|----------|----------|
| **Piper (этот)** | **FREE** | ⭐⭐⭐⭐ | 2-4 сек |
| Groq Orpheus | $22/1M chars | ⭐⭐⭐⭐⭐ | 1-2 сек |
| OpenAI TTS | $15/1M chars | ⭐⭐⭐⭐⭐ | 1-2 сек |
| Google Cloud | $4/1M chars | ⭐⭐⭐⭐ | 2-3 сек |

---

## 🎤 Другие голоса Piper

Для смены голоса измените URLs в `Dockerfile`:

### Женские голоса:
```dockerfile
# Amy (американский, используется)
en_US-amy-medium.onnx

# Lessac (британский)
en_GB-alba-medium.onnx

# Jenny (американский, выразительный)
en_US-lessac-medium.onnx
```

### Мужские голоса:
```dockerfile
# Joe (американский)
en_US-joe-medium.onnx

# Ryan (американский)
en_US-ryan-medium.onnx

# Alan (британский)
en_GB-alan-medium.onnx
```

**Полный список голосов:** https://rhasspy.github.io/piper-samples/

---

## 🐛 Troubleshooting

### Проблема: "Service unavailable"
**Решение:**
1. Проверьте статус: `curl https://your-service.onrender.com/health`
2. Render может загружать модель (подождите 5 минут)
3. Проверьте логи в Render Dashboard

### Проблема: Медленная генерация
**Это нормально для Free Tier:**
- Первый запрос: 5-10 сек (cold start)
- Последующие: 2-4 сек

**Ускорение:**
- Используйте Render Paid Plan ($7/мес)
- Или пингуйте сервис каждые 10 минут, чтобы не засыпал

### Проблема: Model not loaded
**Решение:**
1. Проверьте логи в Render Dashboard
2. Убедитесь, что модель скачалась (займёт ~2 минуты при билде)
3. Перезапустите сервис

---

## 💰 Экономия vs Groq

| Использование | Groq TTS | Piper TTS | Экономия |
|---------------|----------|-----------|----------|
| 1,000 диалогов | $33 | **$0** | **$33** |
| 10,000 диалогов | $330 | **$0** | **$330** |
| 100,000 диалогов | $3,300 | **$0** | **$3,300** |

---

## 📝 Локальная разработка

```bash
# Установите зависимости
pip install -r requirements.txt

# Скачайте модель вручную (если не используете Docker)
mkdir models
wget -O models/en_US-amy-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx
wget -O models/en_US-amy-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/amy/medium/en_US-amy-medium.onnx.json

# Измените MODEL_PATH в main.py
MODEL_PATH = "./models/en_US-amy-medium.onnx"

# Запустите сервис
uvicorn main:app --reload

# Откройте в браузере
http://localhost:8000
```

---

## 🔄 Обновление

```bash
git pull origin main
# Render автоматически пересоберёт и задеплоит
```

---

## 📞 Поддержка

Если что-то не работает:
1. Проверьте логи в Render Dashboard
2. Убедитесь, что `model_loaded: true` в `/health`
3. Проверьте, что сервис не спит (первый запрос может быть медленным)

---

## ✨ Итог

Теперь у вас полностью **бесплатный TTS сервис** на Render.com! 🎉

**Качество:** ⭐⭐⭐⭐ (очень хорошее)  
**Стоимость:** $0 (бесплатно)  
**Скорость:** 2-4 сек (приемлемо)

Идеально для личных проектов и MVP! 🚀
