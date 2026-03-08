import os
from src.config.settings import AppConfig
from src.infrastructure.cli_ui import ConsoleUI

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

class Container:
    """
    Dependency Injection Container.
    Bertanggung jawab untuk menginisialisasi semua adapter dan service,
    serta merakit Orchestrator.
    """
    def __init__(self, config: AppConfig, ui: ConsoleUI, api_key: str):
        self.config = config
        self.ui = ui
        
        # 1. Init Adapters
        self.yt_adapter = YouTubeAdapter(
            cookies_path=config.paths.COOKIE_FILE, 
            deno_path=str(config.paths.DENO_PATH)
        )
        
        # Setup FFmpeg Path (Prioritaskan local bin, fallback ke PATH)
        ffmpeg_binary = "ffmpeg.exe" if os.name == 'nt' else "ffmpeg"
        local_ffmpeg = config.paths.BIN_DIR / ffmpeg_binary
        ffmpeg_cmd = str(local_ffmpeg) if local_ffmpeg.exists() else "ffmpeg"

        self.ffmpeg_adapter = FFmpegAdapter(
            bin_path=ffmpeg_cmd,
            cache_path=config.paths.FFMPEG_CACHE_FILE
        )
        
        self.gemini_adapter = GeminiAdapter(api_key=api_key, model_name=config.gemini_model)
        
        whisper_hw = WhisperAdapter.detect_hardware()
        self.whisper_adapter = WhisperAdapter(**whisper_hw, download_root=str(config.paths.WHISPER_MODELS_DIR))
        
        self.mp_adapter = MediaPipeAdapter(
            model_path=str(config.paths.FACE_LANDMARKER_FILE), 
            window_size=config.motion_window_size
        )

        self.subtitle_writer = AssSubtitleWriter(config=config.subtitle)

        # 2. Init Services
        self.media_service = MediaService(downloader=self.yt_adapter)
        self.audio_service = AudioService(downloader=self.yt_adapter, processor=self.ffmpeg_adapter)
        self.analysis_service = AnalysisService(analyzer=self.gemini_adapter)
        self.video_service = VideoService(processor=self.ffmpeg_adapter, tracker=self.mp_adapter)
        self.captioning_service = CaptioningService(transcriber=self.whisper_adapter, writer=self.subtitle_writer)

        # 3. Init Orchestrator
        self.orchestrator = Orchestrator(
            config, ui, self.media_service, self.audio_service, 
            self.analysis_service, self.video_service, self.captioning_service
        )