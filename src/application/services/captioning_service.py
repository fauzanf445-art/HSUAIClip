import logging
from pathlib import Path
from typing import List, Optional

from src.domain.interfaces import ITranscriber, ISubtitleWriter, TranscriptionSegment
from src.infrastructure.common.json_cache import JsonCache

class CaptioningService:
    """
    Application Service untuk mengelola pembuatan subtitle.
    Mengorkestrasi transkripsi (Whisper) dan penulisan file (ASS).
    """

    def __init__(self, transcriber: ITranscriber, writer: ISubtitleWriter):
        self.transcriber = transcriber
        # Dependency Inversion: Service ini bergantung pada abstraksi (ISubtitleWriter),
        # bukan pada implementasi konkret.
        self.writer = writer

    def _get_transcription_data(self, audio_path: str, cache_path: Path) -> Optional[List[TranscriptionSegment]]:
        """
        Mendapatkan data transkripsi, menggunakan cache jika tersedia.
        """
        data = JsonCache.load(cache_path)
        if data:
            return data

        # Jika tidak ada cache, jalankan transkripsi
        transcription_data = self.transcriber.transcribe(audio_path)
        
        # Simpan ke cache untuk penggunaan selanjutnya
        if transcription_data:
            JsonCache.save(transcription_data, cache_path)
            
        return transcription_data

    def generate_subtitles_for_clip(
        self,
        clip_audio_path: str,
        output_subtitle_path: str,
        cache_dir: Path,
        chunk_size: int,
        video_width: int,
        video_height: int
    ) -> Optional[Path]:
        """
        Membuat file subtitle .ass untuk satu klip.
        """
        output_path = Path(output_subtitle_path)
        
        if output_path.exists():
            logging.debug(f"♻️ Subtitle .ass cached: {output_path.name}")
            return output_path

        transcription_cache_path = cache_dir / f"{Path(clip_audio_path).stem}_transcript.json"
        transcription_data = self._get_transcription_data(clip_audio_path, transcription_cache_path)

        if not transcription_data:
            logging.warning(f"Tidak ada data transkripsi untuk {Path(clip_audio_path).name}.")
            return None

        self.writer.write_karaoke_subtitles(
            transcription_data, str(output_path), chunk_size, video_width, video_height
        )
        
        return output_path if output_path.exists() else None