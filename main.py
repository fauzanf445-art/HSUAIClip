import os
import logging
from dotenv import load_dotenv

# Config & UI
from src.config.settings import AppConfig
from src.infrastructure.ui.console import ConsoleUI
from src.infrastructure.logging_config import setup_logging

# Adapters
from src.infrastructure.adapters.youtube_adapter import YouTubeAdapter
from src.infrastructure.adapters.ffmpeg_adapter import FFmpegAdapter
from src.infrastructure.adapters.gemini_adapter import GeminiAdapter
from src.infrastructure.adapters.whisper_adapter import WhisperAdapter
from src.infrastructure.adapters.mediapipe_adapter import MediaPipeAdapter

# Services
from src.application.services.media_service import MediaService
from src.application.services.audio_service import AudioService
from src.application.services.analysis_service import AnalysisService
from src.application.services.video_service import VideoService
from src.application.services.captioning_service import CaptioningService

# Pipeline
from src.application.pipeline.orchestrator import Orchestrator

def main():
    # 1. Setup Dasar
    config = AppConfig()
    
    # Inisialisasi Logging (File + Console TQDM)
    setup_logging(config.paths.LOG_FILE)
    
    ui = ConsoleUI()
    ui.print_banner()

    # 2. Load Environment Variables (API Key)
    load_dotenv(config.paths.ENV_FILE)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        api_key = ui.get_api_key()
        # Simpan ke .env sederhana
        with open(config.paths.ENV_FILE, "w") as f:
            f.write(f"GEMINI_API_KEY={api_key}")

    try:
        # 3. Inisialisasi Adapters (Infrastructure Layer)
        # Deno path opsional, bisa diambil dari shutil.which di dalam adapter jika perlu
        yt_adapter = YouTubeAdapter(cookies_path=config.paths.COOKIE_FILE)
        ffmpeg_adapter = FFmpegAdapter(bin_path="ffmpeg") # Asumsi di PATH atau bin/
        gemini_adapter = GeminiAdapter(api_key=api_key, model_name=config.gemini_model)
        
        # Deteksi hardware otomatis untuk Whisper
        whisper_hw = WhisperAdapter.detect_hardware()
        whisper_adapter = WhisperAdapter(**whisper_hw, download_root=str(config.paths.WHISPER_MODELS_DIR))
        
        mp_adapter = MediaPipeAdapter(model_path=str(config.paths.FACE_LANDMARKER_FILE), window_size=config.motion_window_size)

        # 4. Inisialisasi Services (Application Layer)
        media_service = MediaService(downloader=yt_adapter)
        audio_service = AudioService(downloader=yt_adapter, processor=ffmpeg_adapter)
        analysis_service = AnalysisService(analyzer=gemini_adapter)
        video_service = VideoService(processor=ffmpeg_adapter, tracker=mp_adapter)
        captioning_service = CaptioningService(transcriber=whisper_adapter)

        # 5. Jalankan Orchestrator
        orchestrator = Orchestrator(config, ui, media_service, audio_service, analysis_service, video_service, captioning_service)
        
        url = ui.get_video_url()
        orchestrator.run(url)

    except KeyboardInterrupt:
        print("\n👋 Dibatalkan pengguna.")

if __name__ == "__main__":
    main()