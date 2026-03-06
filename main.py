import os
from dotenv import load_dotenv


# Config & UI
from src.config.settings import AppConfig
from src.infrastructure.cli_ui import ConsoleUI
from src.infrastructure.common.logger import setup_logging

# Adapters
from src.infrastructure.adapters.youtube_adapter import YouTubeAdapter
from src.infrastructure.adapters.ffmpeg_adapter import FFmpegAdapter
from src.infrastructure.adapters.gemini_adapter import GeminiAdapter
from src.infrastructure.adapters.whisper_adapter import WhisperAdapter
from src.infrastructure.adapters.mediapipe_adapter import MediaPipeAdapter
from src.infrastructure.adapters.subtitle_writer import AssSubtitleWriter

# Services
from src.application.services.media_service import MediaService
from src.application.services.audio_service import AudioService
from src.application.services.analysis_service import AnalysisService
from src.application.services.video_service import VideoService
from src.application.services.captioning_service import CaptioningService

# Pipeline
from src.application.pipeline.orchestrator import Orchestrator

def setup_environment(config: AppConfig):
    """
    Mempersiapkan lingkungan eksekusi: membuat folder yang diperlukan
    dan mendaftarkan direktori binary ke PATH sistem.
    """
    # 1. Membuat semua direktori yang diperlukan
    for path in [config.paths.TEMP_DIR, config.paths.OUTPUT_DIR, config.paths.MODELS_DIR, 
                 config.paths.FILES_DIR, config.paths.WHISPER_MODELS_DIR, config.paths.MEDIAPIPE_DIR, config.paths.LOGS_DIR]:
        path.mkdir(parents=True, exist_ok=True)

    # 2. Menambahkan folder bin ke PATH agar FFmpeg dapat ditemukan
    bin_path = str(config.paths.BIN_DIR.resolve())
    if bin_path not in os.environ["PATH"]:
        os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]

def main():
    config = AppConfig()
    setup_environment(config)
    setup_logging(config.paths.LOG_FILE)
    
    ui = ConsoleUI()
    ui.print_banner()

    load_dotenv(config.paths.ENV_FILE)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        api_key = ui.get_api_key()
        with open(config.paths.ENV_FILE, "w") as f:
            f.write(f"GEMINI_API_KEY={api_key}")

    try:
        yt_adapter = YouTubeAdapter(cookies_path=config.paths.COOKIE_FILE, deno_path=str(config.paths.DENO_PATH))
        ffmpeg_adapter = FFmpegAdapter(bin_path="ffmpeg")
        ffmpeg_adapter.initialize()
        gemini_adapter = GeminiAdapter(api_key=api_key, model_name=config.gemini_model)
        
        whisper_hw = WhisperAdapter.detect_hardware()
        whisper_adapter = WhisperAdapter(**whisper_hw, download_root=str(config.paths.WHISPER_MODELS_DIR))
        
        mp_adapter = MediaPipeAdapter(model_path=str(config.paths.FACE_LANDMARKER_FILE), window_size=config.motion_window_size)

        subtitle_writer_adapter = AssSubtitleWriter()

        # 4. Inisialisasi Services (Application Layer)
        media_service = MediaService(downloader=yt_adapter)
        audio_service = AudioService(downloader=yt_adapter, processor=ffmpeg_adapter)
        analysis_service = AnalysisService(analyzer=gemini_adapter)
        video_service = VideoService(processor=ffmpeg_adapter, tracker=mp_adapter)
        captioning_service = CaptioningService(transcriber=whisper_adapter, writer=subtitle_writer_adapter)

        # 5. Jalankan Orchestrator
        orchestrator = Orchestrator(config, ui, media_service, audio_service, analysis_service, video_service, captioning_service)
        
        url = ui.get_video_url()
        orchestrator.run(url)

    except KeyboardInterrupt:
        print("\n👋 Dibatalkan pengguna.")

if __name__ == "__main__":
    main()