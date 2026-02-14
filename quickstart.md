# ⚡ Quick Start - Piper TTS Service

## 5-минутный деплой на Render.com

### Шаг 1: Создайте GitHub репозиторий

```bash
# В папке piper-tts-service
git init
git add .
git commit -m "Initial commit: Piper TTS service"

# Создайте репозиторий на GitHub (назовите: piper-tts-service)
git remote add origin https://github.com/YOUR_USERNAME/piper-tts-service.git
git push -u origin main
```

### Шаг 2: Деплой на Render

1. Зайдите на https://render.com
2. **New** → **Web Service**
3. **Connect** ваш GitHub: `piper-tts-service`
4. Render автоматически обнаружит `render.yaml`
5. Нажмите **Deploy**

### Шаг 3: Дождитесь деплоя (5-10 минут)

Render:
1. Соберёт Docker образ
2. Скачает модель Piper (~50 MB)
3. Запустит сервис

### Шаг 4: Получите URL

После деплоя вы получите URL:
```
https://piper-tts-service-XXXX.onrender.com
```

### Шаг 5: Проверьте работу

```bash
# Health check
curl https://piper-tts-service-XXXX.onrender.com/health

# Должно вернуть:
# {"status": "healthy", "model_loaded": true}
```

### Шаг 6: Настройте основной бот

В `.env` вашего Speech Flow бота:

```bash
TTS_PROVIDER=piper
PIPER_TTS_URL=https://piper-tts-service-XXXX.onrender.com
```

### Готово! 🎉

Теперь ваш бот использует бесплатный Piper TTS!

---

## Быстрый тест

```bash
# Генерация аудио
curl -X POST https://piper-tts-service-XXXX.onrender.com/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello! This is Piper TTS speaking."}' \
  --output test.wav

# Проиграйте файл
# На Mac: afplay test.wav
# На Linux: aplay test.wav
# На Windows: start test.wav
```

---

## Что дальше?

- ✅ Сервис готов к использованию
- ✅ Автоматически перезапускается при падении
- ✅ Health checks настроены
- ✅ Бесплатно (750 часов/месяц)

**Если сервис засыпает:**
- Первый запрос после сна: 5-10 сек (норма)
- Последующие: 2-3 сек

**Чтобы не засыпал:**
- Используйте Render Paid ($7/мес)
- Или пингуйте каждые 10 минут (cron-job.org)
