from src.config import AppConfig
from src.infrastructure.cli_ui import ConsoleUI

# Adapters
from src.infrastructure.adapters.youtube_adapter import YouTubeAdapter
from src.infrastructure.adapters.ffmpeg_adapter import FFmpegAdapter
from src.infrastructure.adapters.gemini_adapter import GeminiAdapter
from src.infrastructure.adapters.whisper_adapter import WhisperAdapter
from src.infrastructure.adapters.mediapipe_adapter import MediaPipeAdapter
from src.infrastructure.adapters.subtitle_writer import AssSubtitleWriter

# Services
from src.service.provider_service import ProviderService
from src.service.editor_service import EditorService
from src.service.orchestrator import Orchestrator

class Container:
    def __init__(self, config: AppConfig, ui: ConsoleUI, api_key: str):
        self.config = config
        self.ui = ui
        
        # 1. Init Adapters
        self.yt_adapter = YouTubeAdapter(
            cookies_path=config.paths.COOKIE_FILE
        )
        
        # Gunakan 'ffmpeg' yang diasumsikan ada di PATH sistem
        self.ffmpeg_adapter = FFmpegAdapter(
            bin_path="ffmpeg",
            cache_path=config.paths.FFMPEG_CACHE_FILE
        )
        
        self.gemini_adapter = GeminiAdapter(api_key=api_key, model_name=config.gemini_model)
        
        whisper_hw = WhisperAdapter.detect_hardware()
        self.whisper_adapter = WhisperAdapter(**whisper_hw, download_root=str(config.paths.WHISPER_MODELS_DIR))
        
        self.mp_adapter = MediaPipeAdapter(
            model_path=str(config.paths.FACE_LANDMARKER_FILE), 
            window_size=config.motion_window_size,
            process_every_n_frames=config.motion_process_every_n_frames
        )

        self.subtitle_writer = AssSubtitleWriter(config=config.subtitle)

        # 2. Init Services (Abstraksi Baru)
        self.provider_service = ProviderService(
            downloader=self.yt_adapter,
            processor=self.ffmpeg_adapter,
            analyzer=self.gemini_adapter
        )
        
        self.editor_service = EditorService(
            processor=self.ffmpeg_adapter,
            tracker=self.mp_adapter,
            transcriber=self.whisper_adapter,
            writer=self.subtitle_writer
        )

        # 3. Init Orchestrator
        self.orchestrator = Orchestrator(
            config, ui, 
            provider=self.provider_service, 
            editor=self.editor_service
        )