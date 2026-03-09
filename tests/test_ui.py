import unittest
from unittest.mock import MagicMock
from pathlib import Path
import time

from src.infrastructure.cli_ui import ConsoleUI

class TestConsoleUI(unittest.TestCase):

    def setUp(self):
        """Inisialisasi instance ConsoleUI untuk setiap tes."""
        self.ui = ConsoleUI()

    def _create_mock_files(self, count: int, size_mb: int, start_time: float) -> list:
        """Helper untuk membuat data file palsu."""
        files = []
        for i in range(count):
            # Buat mock untuk Path object
            mock_path = MagicMock(spec=Path)
            mock_path.name = f"file_{i}.mp4"
            
            # Waktu modifikasi, file ke-0 adalah yang paling tua
            mtime = start_time + i
            
            # Mocking `stat()` sangat penting karena logika sorting di dalam
            # _get_files_to_prune memanggilnya lagi.
            mock_stat = MagicMock()
            mock_stat.st_mtime = mtime
            mock_path.stat.return_value = mock_stat
            
            # Data yang dikirim ke fungsi adalah tuple (path, mtime, size)
            files.append((mock_path, mtime, size_mb * 1024 * 1024))
        return files

    def test_get_files_to_prune_by_max_files(self):
        """
        Tes: Pemangkasan harus terjadi ketika jumlah file melebihi `max_files`.
        """
        # Arrange: Buat 12 file, batasnya 10.
        mock_files = self._create_mock_files(count=12, size_mb=10, start_time=time.time())
        max_files = 10
        max_size_mb = 500  # Batas ukuran tidak terlampaui

        # Act
        files_to_delete = self.ui._get_files_to_prune(mock_files, max_files, max_size_mb)

        # Assert: Harus menghapus 2 file paling tua.
        self.assertEqual(len(files_to_delete), 2)
        self.assertEqual(files_to_delete[0].name, "file_0.mp4")
        self.assertEqual(files_to_delete[1].name, "file_1.mp4")

    def test_get_files_to_prune_by_max_size(self):
        """
        Tes: Pemangkasan harus terjadi ketika total ukuran melebihi `max_size_mb`.
        """
        # Arrange: Buat 5 file @ 120MB = 600MB. Batasnya 500MB.
        mock_files = self._create_mock_files(count=5, size_mb=120, start_time=time.time())
        max_files = 10  # Batas jumlah file tidak terlampaui
        max_size_mb = 500

        # Act
        files_to_delete = self.ui._get_files_to_prune(mock_files, max_files, max_size_mb)

        # Assert: Cukup menghapus 1 file paling tua (120MB) untuk berada di bawah batas.
        # 600MB - 120MB = 480MB.
        self.assertEqual(len(files_to_delete), 1)
        self.assertEqual(files_to_delete[0].name, "file_0.mp4")

    def test_get_files_to_prune_combined_rules(self):
        """
        Tes: Pemangkasan harus menggabungkan kedua aturan (jumlah dan ukuran).
        """
        # Arrange: Buat 12 file @ 50MB = 600MB. Batas: 10 file, 500MB.
        mock_files = self._create_mock_files(count=12, size_mb=50, start_time=time.time())
        max_files = 10
        max_size_mb = 500

        # Act
        files_to_delete = self.ui._get_files_to_prune(mock_files, max_files, max_size_mb)

        # Assert:
        # Aturan jumlah file akan menandai file_0 dan file_1 untuk dihapus.
        # Aturan ukuran (600MB > 500MB) perlu menghapus 101MB.
        # Ini akan menandai file_0 (50MB), file_1 (50MB), dan file_2 (50MB).
        # Gabungan dari kedua aturan adalah {file_0, file_1, file_2}.
        self.assertEqual(len(files_to_delete), 3)
        self.assertEqual(files_to_delete[0].name, "file_0.mp4")
        self.assertEqual(files_to_delete[1].name, "file_1.mp4")
        self.assertEqual(files_to_delete[2].name, "file_2.mp4")

    def test_get_files_to_prune_no_pruning_needed(self):
        """
        Tes: Tidak ada pemangkasan yang harus terjadi jika semua batas terpenuhi.
        """
        # Arrange: 5 file @ 50MB = 250MB. Batas: 10 file, 500MB.
        mock_files = self._create_mock_files(count=5, size_mb=50, start_time=time.time())
        max_files = 10
        max_size_mb = 500

        # Act
        files_to_delete = self.ui._get_files_to_prune(mock_files, max_files, max_size_mb)

        # Assert: Daftar file yang akan dihapus harus kosong.
        self.assertEqual(len(files_to_delete), 0)

    def test_get_files_to_prune_empty_input(self):
        """
        Tes: Harus menangani input list kosong dengan aman.
        """
        # Arrange
        mock_files = []
        max_files = 10
        max_size_mb = 500

        # Act
        files_to_delete = self.ui._get_files_to_prune(mock_files, max_files, max_size_mb)

        # Assert
        self.assertEqual(len(files_to_delete), 0)

if __name__ == '__main__':
    unittest.main()