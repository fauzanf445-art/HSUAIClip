import logging
from pathlib import Path
from typing import Optional, Dict, Any

from src.domain.interfaces import IMediaDownloader, IVideoProcessor, IContentAnalyzer
from src.domain.models import VideoSummary, Clip
from src.infrastructure.common.utils import JsonCache

class ProviderService:
    def __init__(self, downloader: IMediaDownloader, processor: IVideoProcessor, analyzer: IContentAnalyzer):
        self.downloader = downloader
        self.processor = processor
        self.analyzer = analyzer

    def get_video_metadata(self, url: str) -> Dict[str, Any]:
        return self.downloader.get_video_info(url)

    def get_transcript(self, url: str) -> str:
        transcript = self.downloader.get_transcript(url)

        if not transcript:
            logging.warning("⚠️ Transkrip tidak ditemukan. Analisis AI mungkin kurang akurat.")
            return ""
        return transcript

    def get_stream_urls(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """Mengambil URL stream video dan audio terbaik."""
        return self.downloader.get_stream_urls(url)
    
    def prepare_audio_for_analysis(self, url: str, work_dir: Path, filename_prefix: str) -> Path:
        """
        Memastikan file audio WAV yang siap untuk dianalisis tersedia.
        Mengatur alur: Cek Cache -> Unduh -> Konversi -> Hapus File Mentah.

        Raises:
            ConnectionError: Jika download gagal.
            IOError: Jika konversi gagal.
        """
        wav_path = work_dir / f"{filename_prefix}.wav"

        if wav_path.exists() and wav_path.stat().st_size > 10240:
            logging.debug(f"♻️ Audio WAV cached: {wav_path.name}")
            return wav_path

        # 2. Unduh audio mentah
        raw_audio_path_str = self.downloader.download_audio(url, str(work_dir), filename_prefix)
        if not raw_audio_path_str:
            # Downloader seharusnya sudah mencatat error spesifik.
            raise ConnectionError("Gagal mengunduh audio. Periksa koneksi internet atau URL video. Lihat log untuk detail dari yt-dlp.")
        
        raw_audio_path = Path(raw_audio_path_str)

        # 3. Konversi ke WAV
        logging.debug(f"⚙️ Mengonversi {raw_audio_path.name} ke format WAV...")
        success = self.processor.convert_audio_to_wav(str(raw_audio_path), str(wav_path))
        
        # 4. Hapus file mentah setelah konversi
        raw_audio_path.unlink(missing_ok=True)

        if success and wav_path.exists():
            return wav_path
        
        raise IOError("Gagal mengonversi audio ke format WAV. Periksa instalasi FFmpeg dan file audio sumber.")

    def analyze_video(self, transcript: str, audio_path: str, prompt: str, cache_path: Optional[str] = None) -> VideoSummary:
        if cache_path:
            cached_summary = self._load_from_cache(cache_path)
            if cached_summary:
                return cached_summary

        logging.info("🧠 Memulai analisis konten dengan AI...")
        summary = self.analyzer.analyze_content(transcript, audio_path, prompt)

        if cache_path:
            self._save_to_cache(summary, cache_path)

        return summary

    def _load_from_cache(self, path: str) -> Optional[VideoSummary]:
        """Helper internal untuk memuat JSON cache ke Domain Model."""
        data = JsonCache.load(Path(path))
        if not data:
            return None
        
        try:
            # Rekonstruksi objek Domain dari JSON (Manual Mapping)
            clips = []
            clips = [Clip.from_dict(c_data) for c_data in data.get('clips', [])]

            return VideoSummary(
                video_title=data.get('video_title', ''),
                audio_energy_profile=data.get('audio_energy_profile', ''),
                clips=clips
            )
        except Exception as e:
            logging.warning(f"⚠️ Struktur cache tidak valid: {e}")
            return None

    def _save_to_cache(self, summary: VideoSummary, path: str):
        data = {
            "video_title": summary.video_title,
            "audio_energy_profile": summary.audio_energy_profile,
            "clips": [c.to_dict() for c in summary.clips]
        }
        JsonCache.save(data, Path(path))