import os
import io
import re
import sys
import signal
import logging
import asyncio
from contextlib import asynccontextmanager
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
    PiperVoice = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)

# Глобальные переменные
voice_model: Optional[PiperVoice] = None
MODEL_PATH = "/app/models/en_US-amy-medium.onnx"
shutdown_event = asyncio.Event()


# ============================================================================
# ОБРАБОТКА СИГНАЛОВ (SIGTERM)
# ============================================================================

def handle_sigterm(signum, frame):
    """Обработчик сигнала SIGTERM от Render"""
    logger.info("📡 Received SIGTERM signal, initiating graceful shutdown...")
    asyncio.create_task(trigger_shutdown())


async def trigger_shutdown():
    """Триггер для graceful shutdown"""
    shutdown_event.set()


# ============================================================================
# LIFESPAN
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan контекст для загрузки/выгрузки модели"""
    global voice_model
    
    # Регистрируем обработчик SIGTERM
    signal.signal(signal.SIGTERM, handle_sigterm)
    logger.info("✅ SIGTERM handler registered")
    
    # STARTUP: загружаем модель
    try:
        if PiperVoice and Path(MODEL_PATH).exists():
            logger.info(f"Loading Piper model from {MODEL_PATH}...")
            voice_model = PiperVoice.load(MODEL_PATH)
            logger.info("✅ Piper model loaded successfully!")
        else:
            logger.warning("⚠️ Piper model not found or library not installed")
    except Exception as e:
        logger.error(f"❌ Failed to load Piper model: {e}")
    
    yield  # Здесь работает приложение
    
    # SHUTDOWN: ждём сигнал и выгружаем модель
    logger.info("🛑 Waiting for shutdown signal...")
    await shutdown_event.wait()
    
    logger.info("🛑 Unloading Piper model...")
    voice_model = None
    logger.info("✅ Piper model unloaded")


# Создаём FastAPI приложение с lifespan
app = FastAPI(
    title="Piper TTS Service", 
    version="1.0.0",
    lifespan=lifespan
)


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "amy"
    speed: Optional[float] = 1.0


# =============================================================================
# ENDPOINTS ДЛЯ UPTIMEROBOT
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
        "model_exists": Path(MODEL_PATH).exists() if MODEL_PATH else False,
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
    """Генерация аудио из текста"""
    if not voice_model:
        raise HTTPException(status_code=503, detail="TTS model not loaded")
    
    try:
        sentences = split_into_sentences(request.text)
        audio_chunks = []
        
        for sentence in sentences:
            if sentence.strip():
                logger.info(f"Generating audio for: {sentence[:50]}...")
                audio_bytes = io.BytesIO()
                voice_model.synthesize(sentence, audio_bytes)
                audio_chunks.append(audio_bytes.getvalue())
        
        combined_audio = combine_wav_chunks(audio_chunks)
        
        logger.info(f"✅ Generated {len(combined_audio)} bytes of audio")
        
        return Response(
            content=combined_audio,
            media_type="audio/wav",
            headers={"Content-Disposition": "attachment; filename=speech.wav"}
        )
        
    except Exception as e:
        logger.error(f"❌ TTS generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts/stream")
async def text_to_speech_stream(request: TTSRequest):
    """Потоковая генерация аудио"""
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
    """Разбивает текст на предложения"""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]


def combine_wav_chunks(chunks: list[bytes]) -> bytes:
    """Объединяет несколько WAV чанков в один файл"""
    if not chunks:
        return b""
    
    if len(chunks) == 1:
        return chunks[0]
    
    first_chunk = io.BytesIO(chunks[0])
    with wave.open(first_chunk, 'rb') as first_wav:
        params = first_wav.getparams()
        
        output = io.BytesIO()
        with wave.open(output, 'wb') as out_wav:
            out_wav.setparams(params)
            
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
    
    # Берём порт из переменной окружения
    port = int(os.environ.get("PORT", 8000))
    
    logger.info("=" * 50)
    logger.info(f"🚀 Starting Piper TTS Service")
    logger.info(f"📌 PORT from env: {os.environ.get('PORT', 'not set')}")
    logger.info(f"🔌 Binding to port: {port}")
    logger.info("=" * 50)
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info"
    )
