import os
import io
import re
import sys
import signal
import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, AsyncGenerator, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
import wave

# Импорт Piper
try:
    from piper import PiperVoice
except ImportError:
    PiperVoice = None

# Настройка логирования
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
executor = ThreadPoolExecutor(max_workers=4)  # Пул потоков для параллельной генерации


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
            logger.info("✅ Piper medium model loaded successfully!")
            logger.info(f"   - Sample rate: {voice_model.config.sample_rate}")
            logger.info(f"   - Voice: en_US-amy-medium")
            logger.info(f"   - Thread pool size: {executor._max_workers}")
        else:
            logger.warning("⚠️ Piper model not found or library not installed")
    except Exception as e:
        logger.error(f"❌ Failed to load Piper model: {e}")
    
    yield  # Здесь работает приложение
    
    # SHUTDOWN: ждём сигнал и выгружаем модель
    logger.info("🛑 Waiting for shutdown signal...")
    await shutdown_event.wait()
    
    logger.info("🛑 Shutting down thread pool...")
    executor.shutdown(wait=True)
    logger.info("✅ Thread pool executor shut down")
    
    logger.info("🛑 Unloading Piper model...")
    voice_model = None
    logger.info("✅ Piper model unloaded")


# Создаём FastAPI приложение с lifespan
app = FastAPI(
    title="Piper TTS Service (Optimized with Parallel Streaming)", 
    version="2.0.0",
    lifespan=lifespan
)


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "amy"
    speed: Optional[float] = 1.0


# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Health check endpoint для UptimeRobot"""
    return {
        "service": "Piper TTS Service (Optimized)",
        "status": "healthy" if voice_model else "model_not_loaded",
        "version": "2.0.0",
        "features": ["parallel_streaming", "thread_pool", "medium_quality"],
        "thread_pool_size": executor._max_workers,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Детальный health check для мониторинга"""
    return {
        "status": "healthy" if voice_model else "unhealthy",
        "model": {
            "loaded": voice_model is not None,
            "path": MODEL_PATH,
            "exists": Path(MODEL_PATH).exists() if MODEL_PATH else False,
            "type": "en_US-amy-medium"
        },
        "thread_pool": {
            "max_workers": executor._max_workers,
            "active": len(executor._threads)
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/ping")
async def ping():
    """Быстрый ping endpoint для UptimeRobot"""
    return {
        "pong": True,
        "service": "piper-tts-optimized",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/status")
async def status():
    """Подробный статус сервиса"""
    return {
        "service": "Piper TTS Service (Optimized)",
        "version": "2.0.0",
        "model": {
            "loaded": voice_model is not None,
            "path": MODEL_PATH,
            "exists": Path(MODEL_PATH).exists() if MODEL_PATH else False,
            "sample_rate": voice_model.config.sample_rate if voice_model else None
        },
        "piper_available": PiperVoice is not None,
        "features": {
            "parallel_streaming": True,
            "thread_pool": True,
            "medium_quality": True
        },
        "thread_pool_size": executor._max_workers,
        "timestamp": datetime.utcnow().isoformat()
    }


# =============================================================================
# OPTIMIZED TTS ENDPOINTS
# =============================================================================

def synthesize_sentence(sentence: str) -> Optional[bytes]:
    """
    Синхронная функция синтеза одного предложения (для выполнения в потоке)
    
    Args:
        sentence: Текст предложения
        
    Returns:
        bytes: Аудио в формате WAV или None в случае ошибки
    """
    try:
        audio_buffer = io.BytesIO()
        voice_model.synthesize(sentence, audio_buffer)
        return audio_buffer.getvalue()
    except Exception as e:
        logger.error(f"❌ Error synthesizing sentence '{sentence[:50]}...': {e}")
        return None


async def generate_sentence_chunk(sentence: str) -> Optional[bytes]:
    """
    Асинхронно генерирует аудио для одного предложения.
    Выполняется в отдельном потоке, чтобы не блокировать event loop.
    
    Args:
        sentence: Текст предложения
        
    Returns:
        bytes: Аудио в формате WAV или None в случае ошибки
    """
    if not voice_model or not sentence.strip():
        return None
    
    try:
        # Запускаем синтез в потоке из пула
        loop = asyncio.get_event_loop()
        audio_bytes = await loop.run_in_executor(
            executor,
            synthesize_sentence,
            sentence
        )
        return audio_bytes
    except Exception as e:
        logger.error(f"❌ Error generating sentence chunk: {e}")
        return None


async def stream_audio_chunks(sentences: List[str]) -> AsyncGenerator[bytes, None]:
    """
    Потоковая отправка аудио-чанков по мере готовности.
    Предложения обрабатываются параллельно, отправляются сразу как готовы.
    
    Args:
        sentences: Список предложений для озвучивания
        
    Yields:
        bytes: Аудио чанки в формате WAV
    """
    if not sentences:
        return
    
    logger.info(f"🚀 Starting parallel streaming for {len(sentences)} sentences")
    
    # Создаем задачи для всех предложений
    tasks = [generate_sentence_chunk(sentence) for sentence in sentences if sentence.strip()]
    
    if not tasks:
        return
    
    # Используем asyncio.as_completed для получения результатов по мере готовности
    completed = 0
    for task in asyncio.as_completed(tasks):
        chunk = await task
        if chunk:
            completed += 1
            logger.debug(f"📦 Sending chunk {completed}/{len(tasks)}: {len(chunk)} bytes")
            yield chunk
    
    logger.info(f"✅ Streaming completed: {completed}/{len(tasks)} chunks sent")


@app.post("/tts/stream")
async def text_to_speech_stream(request: TTSRequest):
    """
    Оптимизированный streaming TTS endpoint.
    Отправляет аудио чанками по мере готовности предложений.
    Предложения генерируются параллельно в пуле потоков.
    """
    if not voice_model:
        raise HTTPException(status_code=503, detail="TTS model not loaded")
    
    try:
        # Разбиваем текст на предложения
        sentences = split_into_sentences(request.text)
        
        if not sentences:
            raise HTTPException(status_code=400, detail="No text to synthesize")
        
        logger.info(f"📝 Processing {len(sentences)} sentences with parallel streaming")
        
        # Создаем streaming response
        return StreamingResponse(
            stream_audio_chunks(sentences),
            media_type="audio/wav",
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked",
                "X-Sentences-Count": str(len(sentences))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Streaming TTS failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Стандартный TTS endpoint (полная генерация, затем отправка).
    Сохранен для обратной совместимости, но тоже использует параллельную генерацию.
    """
    if not voice_model:
        raise HTTPException(status_code=503, detail="TTS model not loaded")
    
    try:
        sentences = split_into_sentences(request.text)
        
        if not sentences:
            raise HTTPException(status_code=400, detail="No text to synthesize")
        
        logger.info(f"📝 Generating full audio for {len(sentences)} sentences in parallel")
        
        # Генерируем все чанки параллельно
        tasks = [generate_sentence_chunk(sentence) for sentence in sentences if sentence.strip()]
        chunks = await asyncio.gather(*tasks)
        
        # Фильтруем None и объединяем
        valid_chunks = [chunk for chunk in chunks if chunk]
        
        if not valid_chunks:
            raise HTTPException(status_code=500, detail="No audio generated")
        
        # Объединяем все чанки в один WAV файл
        combined_audio = combine_wav_chunks(valid_chunks)
        
        logger.info(f"✅ Generated {len(combined_audio)} bytes of audio from {len(valid_chunks)} chunks")
        
        return Response(
            content=combined_audio,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=speech.wav",
                "X-Chunks-Count": str(len(valid_chunks))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ TTS generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def split_into_sentences(text: str) -> List[str]:
    """
    Улучшенное разбиение текста на предложения.
    Учитывает сокращения (Mr., Dr., etc.) и не разбивает по ним.
    """
    # Более точное разбиение с учетом распространенных сокращений
    # Сначала защищаем точки в сокращениях
    abbreviations = ['Mr', 'Mrs', 'Dr', 'Prof', 'Sr', 'Jr', 'vs', 'etc', 'e.g', 'i.e']
    protected_text = text
    
    for i, abbr in enumerate(abbreviations):
        protected_text = protected_text.replace(f'{abbr}.', f'__ABBR{i}__')
    
    # Разбиваем по границам предложений
    raw_sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', protected_text)
    
    # Восстанавливаем сокращения
    result = []
    for sentence in raw_sentences:
        for i, abbr in enumerate(abbreviations):
            sentence = sentence.replace(f'__ABBR{i}__', f'{abbr}.')
        result.append(sentence.strip())
    
    return [s for s in result if s]


def combine_wav_chunks(chunks: List[bytes]) -> bytes:
    """
    Объединяет несколько WAV чанков в один файл с правильными заголовками.
    Поддерживает чанки с разными параметрами, используя параметры первого чанка.
    
    Args:
        chunks: Список WAV чанков
        
    Returns:
        bytes: Объединенный WAV файл
    """
    if not chunks:
        return b""
    
    if len(chunks) == 1:
        return chunks[0]
    
    try:
        # Читаем параметры из первого чанка
        first_chunk = io.BytesIO(chunks[0])
        with wave.open(first_chunk, 'rb') as first_wav:
            params = first_wav.getparams()
            
            # Создаем выходной WAV файл
            output = io.BytesIO()
            with wave.open(output, 'wb') as out_wav:
                out_wav.setparams(params)
                
                # Записываем все чанки
                for i, chunk in enumerate(chunks):
                    try:
                        chunk_io = io.BytesIO(chunk)
                        with wave.open(chunk_io, 'rb') as chunk_wav:
                            # Проверяем, что параметры совместимы
                            if chunk_wav.getnchannels() != params.nchannels or \
                               chunk_wav.getsampwidth() != params.sampwidth or \
                               chunk_wav.getframerate() != params.framerate:
                                logger.warning(f"Chunk {i} has incompatible parameters, skipping")
                                continue
                            
                            out_wav.writeframes(chunk_wav.readframes(chunk_wav.getnframes()))
                    except Exception as e:
                        logger.warning(f"Error processing chunk {i}: {e}")
                        continue
            
            return output.getvalue()
            
    except Exception as e:
        logger.error(f"Error combining WAV chunks: {e}")
        # В случае ошибки возвращаем первый чанк
        return chunks[0]


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Берём порт из переменной окружения
    port = int(os.environ.get("PORT", 8000))
    
    logger.info("=" * 60)
    logger.info("🚀 Starting OPTIMIZED Piper TTS Service")
    logger.info(f"📌 PORT from env: {os.environ.get('PORT', 'not set')}")
    logger.info(f"🔌 Binding to port: {port}")
    logger.info(f"🎯 Model: en_US-amy-medium")
    logger.info(f"⚡ Features: Parallel Streaming + Thread Pool")
    logger.info(f"🧵 Thread pool size: {executor._max_workers}")
    logger.info("=" * 60)
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info"
    )
