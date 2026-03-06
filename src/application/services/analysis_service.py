import json
import logging
from pathlib import Path
from typing import Optional

from src.domain.interfaces import IContentAnalyzer
from src.domain.models import VideoSummary, Clip

class AnalysisService:
    """
    Application Service yang bertanggung jawab untuk menganalisis konten video.
    Mengatur alur: Cek Cache -> Panggil AI Adapter -> Simpan Cache.
    """
    def __init__(self, analyzer: IContentAnalyzer):
        # Dependency Injection: Service tidak tahu kita pakai Gemini/OpenAI,
        # dia hanya tahu ada sesuatu yang memenuhi kontrak IContentAnalyzer.
        self.analyzer = analyzer

    def analyze_video(self, transcript: str, audio_path: str, prompt: str, cache_path: Optional[str] = None) -> VideoSummary:
        """
        Menjalankan proses analisis utama.
        """
        # 1. Cek Cache (Jika path output diberikan)
        if cache_path:
            cached_summary = self._load_from_cache(cache_path)
            if cached_summary:
                return cached_summary

        # 2. Lakukan Analisis via Adapter
        logging.info("🧠 Memulai analisis konten dengan AI...")
        summary = self.analyzer.analyze_content(transcript, audio_path, prompt)

        # 3. Simpan Hasil ke Cache
        if cache_path:
            self._save_to_cache(summary, cache_path)

        return summary

    def _load_from_cache(self, path: str) -> Optional[VideoSummary]:
        """Helper internal untuk memuat JSON cache ke Domain Model."""
        file_path = Path(path)
        if not file_path.exists():
            return None
        
        try:
            logging.debug(f"♻️ Memuat hasil analisis dari cache: {file_path.name}")
            data = json.loads(file_path.read_text(encoding='utf-8'))
            
            # Rekonstruksi objek Domain dari JSON (Manual Mapping)
            clips = []
            clips = [Clip.from_dict(c_data) for c_data in data.get('clips', [])]

            return VideoSummary(
                video_title=data.get('video_title', ''),
                audio_energy_profile=data.get('audio_energy_profile', ''),
                clips=clips
            )
        except Exception as e:
            logging.warning(f"⚠️ Cache korup atau tidak valid: {e}")
            return None

    def _save_to_cache(self, summary: VideoSummary, path: str):
        """Helper internal untuk menyimpan Domain Model ke JSON."""
        try:
            # Konversi Domain Model ke Dictionary menggunakan metode to_dict()
            # Ini menghilangkan duplikasi logika dan mematuhi prinsip DRY.
            data = {
                "video_title": summary.video_title,
                "audio_energy_profile": summary.audio_energy_profile,
                # Setiap objek Clip sekarang bertanggung jawab atas serialisasinya sendiri.
                "clips": [c.to_dict() for c in summary.clips]
            }
            
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            logging.debug(f"💾 Hasil analisis disimpan ke: {path}")
        except Exception as e:
            logging.error(f"❌ Gagal menyimpan cache: {e}")