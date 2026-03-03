import unittest
from unittest.mock import patch
import os
import shutil
import logging
from pathlib import Path
from dotenv import load_dotenv

# Config & UI
from src.config.settings import AppConfig
from src.infrastructure.ui.console import ConsoleUI

# Adapters
from src.infrastructure.adapters.youtube_adapter import YouTubeAdapter
from src.infrastructure.adapters.ffmpeg_adapter import FFmpegAdapter
from src.infrastructure.adapters.gemini_adapter import GeminiAdapter
from src.infrastructure.adapters.whisper_adapter import WhisperAdapter
from src.infrastructure.adapters.mediapipe_adapter import MediaPipeAdapter

# Services
from src.application.services.media_service import MediaService
from src.application.services.audio_service import AudioService
from src.application.services.analysis_service import AnalysisService
from src.application.services.video_service import VideoService
from src.application.services.captioning_service import CaptioningService

# Pipeline
from src.application.pipeline.orchestrator import Orchestrator

# --- Konfigurasi Tes ---
# Gunakan video pendek dan publik untuk konsistensi
TEST_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw" # "Me at the zoo"
TEST_VIDEO_SAFE_NAME = "Me at the zoo"

# Muat API key dari .env
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

@unittest.skipIf(not API_KEY, "GEMINI_API_KEY tidak ditemukan di .env. Tes integrasi dilewati.")
class TestFullPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        Mempersiapkan semua instance nyata yang diperlukan untuk pipeline.
        Ini seperti mini `main.py`.
        """
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        
        cls.config = AppConfig()
        cls.ui = ConsoleUI() # Kita tetap butuh instance-nya, meski tidak akan menampilkan ke user

        # Hapus output lama sebelum memulai
        shutil.rmtree(cls.config.paths.TEMP_DIR / TEST_VIDEO_SAFE_NAME, ignore_errors=True)
        shutil.rmtree(cls.config.paths.OUTPUT_DIR / TEST_VIDEO_SAFE_NAME, ignore_errors=True)

        # Inisialisasi semua komponen dengan implementasi nyata
        yt_adapter = YouTubeAdapter(cookies_path=cls.config.paths.COOKIE_FILE)
        ffmpeg_adapter = FFmpegAdapter(bin_path="ffmpeg")
        gemini_adapter = GeminiAdapter(api_key=API_KEY, model_name=cls.config.gemini_model)
        
        whisper_hw = WhisperAdapter.detect_hardware()
        whisper_adapter = WhisperAdapter(**whisper_hw, download_root=str(cls.config.paths.WHISPER_MODELS_DIR))
        
        mp_adapter = MediaPipeAdapter(model_path=str(cls.config.paths.FACE_LANDMARKER_FILE), window_size=cls.config.motion_window_size)

        media_service = MediaService(downloader=yt_adapter)
        audio_service = AudioService(downloader=yt_adapter, processor=ffmpeg_adapter)
        analysis_service = AnalysisService(analyzer=gemini_adapter)
        video_service = VideoService(processor=ffmpeg_adapter, tracker=mp_adapter)
        captioning_service = CaptioningService(transcriber=whisper_adapter)

        # Buat Orchestrator yang akan diuji
        cls.orchestrator = Orchestrator(
            cls.config, cls.ui, media_service, audio_service, 
            analysis_service, video_service, captioning_service
        )

    @classmethod
    def tearDownClass(cls):
        """Membersihkan file yang dihasilkan setelah tes selesai."""
        print("\nMembersihkan file tes...")
        temp_dir = cls.config.paths.TEMP_DIR / TEST_VIDEO_SAFE_NAME
        output_dir = cls.config.paths.OUTPUT_DIR / TEST_VIDEO_SAFE_NAME
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)
        print(f"Dihapus: {temp_dir}")
        print(f"Dihapus: {output_dir}")

    def test_run_pipeline_end_to_end_with_manual_clip(self):
        """
        Menjalankan pipeline lengkap dari awal hingga akhir menggunakan mode manual
        untuk mempercepat proses (menghindari panggilan AI yang mahal dan lama).
        """
        # Arrange
        # Kita "memalsukan" input pengguna untuk mode manual
        with patch.object(self.ui, 'get_manual_clips') as mock_get_manual:
            # Mock get_manual_clips untuk mengembalikan satu klip sederhana
            # Ini akan memotong video dari detik ke-2 hingga ke-7
            from src.domain.models import Clip
            manual_clip = Clip(id="test01", title="Test Clip", start_time=2.0, end_time=7.0, duration=5.0, energy_score=0, vocal_energy="", audio_justification="", description="", caption="")
            mock_get_manual.return_value = [manual_clip]

            # Act
            self.orchestrator.run(TEST_URL)

        # Assert
        # Verifikasi bahwa file output benar-benar dibuat
        output_dir = self.config.paths.OUTPUT_DIR / TEST_VIDEO_SAFE_NAME
        self.assertTrue(output_dir.exists(), "Folder output utama seharusnya dibuat.")

        final_clips = list(output_dir.glob("final_*.mp4"))
        self.assertGreater(len(final_clips), 0, "Seharusnya ada setidaknya satu file video final yang dirender.")
        
        first_clip = final_clips[0]
        self.assertGreater(first_clip.stat().st_size, 10 * 1024, f"File {first_clip.name} terlihat terlalu kecil (kurang dari 10KB).")
        print(f"\n✅ Verifikasi berhasil: File output '{first_clip.name}' dibuat dan valid.")

if __name__ == '__main__':
    unittest.main()
