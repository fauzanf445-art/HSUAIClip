from abc import ABC, abstractmethod
from typing import List, Any, Dict, Optional, Callable
from .models import Clip, VideoSummary

class IVideoProcessor(ABC):
    """Interface untuk manipulasi video (FFmpeg/OpenCV)."""
    @abstractmethod
    def cut_clip(self, source_url: str, start: float, end: float, output_path: str, audio_url: Optional[str] = None) -> bool: ...
    
    @abstractmethod
    def render_final(self, video_path: str, audio_path: str, subtitle_path: Optional[str], output_path: str, fonts_dir: Optional[str] = None) -> bool: ...

    @abstractmethod
    def convert_audio_to_wav(self, input_path: str, output_path: str) -> bool: ...

class ITranscriber(ABC):
    """Interface untuk AI Transcriber (Whisper)."""
    @abstractmethod
    def transcribe(self, audio_path: str) -> List[Dict[str, Any]]: ...

class IContentAnalyzer(ABC):
    """Interface untuk AI Analysis (Gemini)."""
    @abstractmethod
    def analyze_content(self, transcript: str, audio_path: str, prompt: str) -> VideoSummary: ...

class IFaceTracker(ABC):
    """Interface untuk Motion Tracking (MediaPipe)."""
    @abstractmethod
    def track_and_crop(self, input_path: str, output_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]: ...

class IMediaDownloader(ABC):
    """Interface untuk mengunduh media dan metadata (yt-dlp)."""
    @abstractmethod
    def get_video_info(self, url: str) -> Dict[str, Any]: ...
    
    @abstractmethod
    def get_stream_urls(self, url: str) -> tuple[Optional[str], Optional[str]]: ...
    
    @abstractmethod
    def download_audio(self, url: str, output_dir: str, filename_prefix: str) -> Optional[str]: ...
    
    @abstractmethod
    def get_transcript(self, url: str) -> Optional[str]: ...