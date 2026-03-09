import unittest
from unittest.mock import patch, MagicMock, ANY
from pathlib import Path

from src.infrastructure.adapters.youtube_adapter import YouTubeAdapter

class TestYouTubeAdapter(unittest.TestCase):

    def test_get_video_info_enables_node_js_runtime(self):
        """
        Verifikasi bahwa adapter secara eksplisit mengaktifkan 'node' sebagai JS runtime,
        memastikan perilaku konsisten terlepas dari runtime lain yang terinstal.
        """
        # Arrange
        adapter = YouTubeAdapter(cookies_path="dummy/cookies.txt")
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        # Act
        with patch('yt_dlp.YoutubeDL') as MockYoutubeDL:
            # Atur mock agar tidak error saat dipanggil
            mock_instance = MockYoutubeDL.return_value
            mock_instance.__enter__.return_value.extract_info.return_value = {"title": "Test"}
            
            adapter.get_video_info(test_url)

            # Assert
            # Ambil argumen yang digunakan untuk menginisialisasi YoutubeDL
            called_opts = MockYoutubeDL.call_args.args[0]
            
            # Pastikan kita secara eksplisit mengaktifkan 'node'
            self.assertIn('js_runtimes', called_opts)
            self.assertEqual(called_opts['js_runtimes'], {'node': {}})
            mock_instance.__enter__.return_value.extract_info.assert_called_once_with(test_url, download=False)