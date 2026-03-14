import unittest
from unittest.mock import patch
import os
import shutil
import logging
from pathlib import Path
from dotenv import load_dotenv

# Config & UI
from src.config import AppConfig
from src.infrastructure.cli_ui import ConsoleUI
from src.container import Container

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

        # Replikasi setup environment yang sekarang ada di main.py
        # untuk memastikan test berjalan dalam kondisi yang sama.
        cls.config.paths.create_dirs()

        cls.ui = ConsoleUI() # Kita tetap butuh instance-nya, meski tidak akan menampilkan ke user

        # Hapus output lama sebelum memulai
        shutil.rmtree(cls.config.paths.TEMP_DIR / TEST_VIDEO_SAFE_NAME, ignore_errors=True)
        shutil.rmtree(cls.config.paths.OUTPUT_DIR / TEST_VIDEO_SAFE_NAME, ignore_errors=True)

        # Inisialisasi via Container
        cls.container = Container(cls.config, cls.ui, API_KEY)
        cls.orchestrator = cls.container.orchestrator

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
        # Kita "memalsukan" input pengguna untuk mode manual.
        # UI sekarang mengembalikan dictionary, bukan objek Clip.
        with patch.object(self.ui, 'get_manual_clips') as mock_get_manual:
            # Ini akan memotong video dari detik ke-2 hingga ke-7
            manual_timestamps = [{'start_time': 2.0, 'end_time': 7.0}]
            mock_get_manual.return_value = manual_timestamps

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
