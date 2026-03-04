import os
import sys
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class AppPaths:
    # Base Directory (Root Project)
    # Gunakan default_factory agar aman dan dinamis
    BASE_DIR: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent.resolve())
    
    # Folder Struktur (init=False artinya field ini diisi otomatis oleh __post_init__)
    TEMP_DIR: Path = field(init=False)
    OUTPUT_DIR: Path = field(init=False)
    MODELS_DIR: Path = field(init=False)
    FILES_DIR: Path = field(init=False)
    FONTS_DIR: Path = field(init=False)
    BIN_DIR: Path = field(init=False)
    LOGS_DIR: Path = field(init=False)
    LOG_FILE: Path = field(init=False)
    
    # Sub-folder Models
    WHISPER_MODELS_DIR: Path = field(init=False)
    MEDIAPIPE_DIR: Path = field(init=False)
    
    # Files
    ENV_FILE: Path = field(init=False)
    COOKIE_FILE: Path = field(init=False)
    PROMPT_FILE: Path = field(init=False)
    FACE_LANDMARKER_FILE: Path = field(init=False)

    def __post_init__(self):
        """Menghitung path turunan berdasarkan BASE_DIR saat ini."""
        self.TEMP_DIR = self.BASE_DIR / "Temp"
        self.OUTPUT_DIR = self.BASE_DIR / "Output"
        self.MODELS_DIR = self.BASE_DIR / "models"
        self.FILES_DIR = self.BASE_DIR / "files"
        self.FONTS_DIR = self.BASE_DIR / "fonts"
        self.BIN_DIR = self.BASE_DIR / "bin"
        
        self.LOGS_DIR = self.BASE_DIR / "logs"
        self.LOG_FILE = self.LOGS_DIR / "app.log"
        
        self.WHISPER_MODELS_DIR = self.MODELS_DIR / "whispermodels"
        self.MEDIAPIPE_DIR = self.MODELS_DIR / "mpmodels"
        
        self.ENV_FILE = self.FILES_DIR / ".env"
        self.COOKIE_FILE = self.FILES_DIR / "cookies.txt"
        self.PROMPT_FILE = self.BASE_DIR / "src" / "assets" / "prompts" / "gemini_prompt.txt"
        self.FACE_LANDMARKER_FILE = self.MEDIAPIPE_DIR / "face_landmarker.task"

@dataclass
class AppConfig:
    # Pastikan menggunakan default_factory (ini yang memperbaiki error mutable default)
    paths: AppPaths = field(default_factory=AppPaths)
    
    # AI Config
    gemini_model: str = "gemini-flash-latest"
    
    # Motion Tracking
    motion_window_size: int = 5
    
    # Captioning
    karaoke_chunk_size: int = 3
    
    # Whisper Model Strategy (Simple)
    whisper_model_size: str = "small" 
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    def get_prompt_template(self) -> str:
        """Memuat prompt template, fallback ke default jika file tidak ada."""
        if self.paths.PROMPT_FILE.exists():
            return self.paths.PROMPT_FILE.read_text(encoding='utf-8')
        
        # Default Prompt jika file hilang
        return """
        Role: Content Strategist. Analyze audio & transcript for viral clips.
        Requirements:
        1. Timestamps: Float seconds (aligned with transcript).
        2. Language: Indonesian.
        3. Output JSON: { "video_title": "...", "audio_energy_profile": "...", "clips": [ ... ] }
        """