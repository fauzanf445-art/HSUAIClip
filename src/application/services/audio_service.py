import logging
from pathlib import Path
from typing import Optional

from src.domain.interfaces import IMediaDownloader, IVideoProcessor

class AudioService:
    """
    Application Service untuk menangani semua operasi terkait audio,
    seperti mengunduh dan mengonversi.
    """

    def __init__(self, downloader: IMediaDownloader, processor: IVideoProcessor):
        self.downloader = downloader
        self.processor = processor

    def prepare_audio_for_analysis(self, url: str, work_dir: Path, filename_prefix: str) -> Path:
        """
        Memastikan file audio WAV yang siap untuk dianalisis tersedia.
        Mengatur alur: Cek Cache -> Unduh -> Konversi -> Hapus File Mentah.

        Raises:
            ConnectionError: Jika download gagal.
            IOError: Jika konversi gagal.
        """
        wav_path = work_dir / f"{filename_prefix}.wav"

        # 1. Cek cache file WAV final
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