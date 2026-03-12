import logging
from typing import Optional, Dict, Any, Tuple
from src.domain.interfaces import IMediaDownloader
from src.infrastructure.common.utils import sanitize_filename

class MediaService:
    """
    Application Service untuk mengambil informasi media dan stream URL.
    """
    def __init__(self, downloader: IMediaDownloader):
        self.downloader = downloader

    def get_video_metadata(self, url: str) -> Dict[str, Any]:
        """Mengambil metadata video (judul, channel, dll)."""
        return self.downloader.get_video_info(url)

    def get_transcript(self, url: str) -> str:
        """Mengambil transkrip video."""
        transcript = self.downloader.get_transcript(url)
        if not transcript:
            logging.warning("⚠️ Transkrip tidak ditemukan. Analisis AI mungkin kurang akurat.")
            return ""
        return transcript

    def get_stream_urls(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Mengambil URL stream video dan audio terbaik."""
        return self.downloader.get_stream_urls(url)

    def get_safe_filename(self, url: str) -> str:
        """Membuat nama file aman dari judul video."""
        info = self.get_video_metadata(url)
        title = info.get('title', 'Unknown_Video')
        safe_title = sanitize_filename(title)
        return safe_title[:50] # Batasi panjang