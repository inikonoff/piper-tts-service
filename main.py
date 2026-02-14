import os
import io
import re
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
import wave

# Импорт Piper
try:
    from piper import PiperVoice
except ImportError:
    # Fallback для локальной разработки
    PiperVoice = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Piper TTS Service", version="1.0.0")

# Глобальная переменная для модели (загружаем один раз)
voice_model: Optional[PiperVoice] = None
MODEL_PATH = "/app/models/en_US-amy-medium.onnx"


@app.on_event("startup")
async def load_model():
    """Загружаем модель при старте сервиса"""
    global voice_model
    try:
        if PiperVoice and Path(MODEL_PATH).exists():
            logger.info(f"Loading Piper model from {MODEL_PATH}...")
            voice_model = PiperVoice.load(MODEL_PATH)
            logger.info("✅ Piper model loaded successfully!")
        else:
            logger.warning("⚠️ Piper model not found or library not installed")
    except Exception as e:
        logger.error(f"❌ Failed to load Piper model: {e}")


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "amy"  # Для совместимости с интерфейсом
    speed: Optional[float] = 1.0


# =============================================================================
# ENDPOINTS ДЛЯ UPTIMEROBOT И МОНИТОРИНГА
# =============================================================================

@app.get("/")
async def root():
    """Health check endpoint для UptimeRobot"""
    return {
        "service": "Piper TTS Service",
        "status": "healthy" if voice_model else "model_not_loaded",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Детальный health check для мониторинга"""
    return {
        "status": "healthy" if voice_model else "unhealthy",
        "model_loaded": voice_model is not None,
        "model_path": MODEL_PATH,
        "uptime": True,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/ping")
async def ping():
    """Быстрый ping endpoint для UptimeRobot"""
    return {
        "pong": True,
        "service": "piper-tts",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/status")
async def status():
    """Подробный статус сервиса"""
    return {
        "service": "Piper TTS Service",
        "version": "1.0.0",
        "model": {
            "loaded": voice_model is not None,
            "path": MODEL_PATH,
            "exists": Path(MODEL_PATH).exists() if MODEL_PATH else False
        },
        "piper_available": PiperVoice is not None,
        "timestamp": datetime.utcnow().isoformat()
    }


# =============================================================================
# TTS ENDPOINTS
# =============================================================================

@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Генерация аудио из текста (потоковая)
    
    Применяется оптимизация:
    1. Разбиваем текст на предложения
    2. Генерируем каждое предложение отдельно
    3. Склеиваем в один WAV файл
    """
    if not voice_model:
        raise HTTPException(status_code=503, detail="TTS model not loaded")
    
    try:
        # Разбиваем текст на предложения для потоковой генерации
        sentences = split_into_sentences(request.text)
        
        # Генерируем аудио для каждого предложения
        audio_chunks = []
        
        for sentence in sentences:
            if sentence.strip():
                logger.info(f"Generating audio for: {sentence[:50]}...")
                
                # Генерируем аудио
                audio_bytes = io.BytesIO()
                voice_model.synthesize(sentence, audio_bytes)
                audio_chunks.append(audio_bytes.getvalue())
        
        # Объединяем все чанки в один WAV
        combined_audio = combine_wav_chunks(audio_chunks)
        
        logger.info(f"✅ Generated {len(combined_audio)} bytes of audio")
        
        # Возвращаем как WAV файл
        return Response(
            content=combined_audio,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=speech.wav"
            }
        )
        
    except Exception as e:
        logger.error(f"❌ TTS generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts/stream")
async def text_to_speech_stream(request: TTSRequest):
    """
    Потоковая генерация аудио (для WebSocket в будущем)
    Пока просто возвращаем по предложениям
    """
    if not voice_model:
        raise HTTPException(status_code=503, detail="TTS model not loaded")
    
    async def generate():
        sentences = split_into_sentences(request.text)
        
        for sentence in sentences:
            if sentence.strip():
                audio_bytes = io.BytesIO()
                voice_model.synthesize(sentence, audio_bytes)
                yield audio_bytes.getvalue()
    
    return StreamingResponse(generate(), media_type="audio/wav")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def split_into_sentences(text: str) -> list[str]:
    """
    Разбивает текст на предложения для потоковой генерации
    Оптимизация из статьи: генерируем по предложениям
    """
    # Разбиваем по точкам, вопросам, восклицаниям
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def combine_wav_chunks(chunks: list[bytes]) -> bytes:
    """
    Объединяет несколько WAV чанков в один файл
    """
    if not chunks:
        return b""
    
    if len(chunks) == 1:
        return chunks[0]
    
    # Читаем параметры из первого чанка
    first_chunk = io.BytesIO(chunks[0])
    with wave.open(first_chunk, 'rb') as first_wav:
        params = first_wav.getparams()
        
        # Создаём выходной файл
        output = io.BytesIO()
        with wave.open(output, 'wb') as out_wav:
            out_wav.setparams(params)
            
            # Записываем аудио из всех чанков
            for chunk in chunks:
                chunk_io = io.BytesIO(chunk)
                with wave.open(chunk_io, 'rb') as chunk_wav:
                    out_wav.writeframes(chunk_wav.readframes(chunk_wav.getnframes()))
        
        return output.getvalue()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"🚀 Starting Piper TTS Service on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
