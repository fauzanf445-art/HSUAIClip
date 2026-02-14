import re
import subprocess
from pathlib import Path

class FFmpegUtils:
    """Kumpulan utilitas untuk operasi FFmpeg."""

    @staticmethod
    def _time_str_to_seconds(time_str: str) -> float:
        """Mengonversi string waktu HH:MM:SS.ss menjadi detik."""
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def get_duration(file_path: Path, ffprobe_path: str) -> float:
        """Menggunakan ffprobe untuk mendapatkan durasi total file media dalam detik."""
        command = [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as e:
            raise RuntimeError(f"Gagal mendapatkan durasi audio dengan ffprobe: {e}") from e

    @staticmethod
    def run_command(command: list[str], total_duration: float, label: str = "Memproses"):
        """
        Menjalankan perintah FFmpeg apa saja dengan progress bar.
        Cocok untuk encoding, muxing, atau filter complex.
        """
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', errors='ignore')

        if process.stdout is None:
            raise RuntimeError("Gagal mendapatkan stdout dari FFmpeg")

        # Setup regex dan validasi durasi untuk progress bar
        time_pattern = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})")
        duration_sec = total_duration if total_duration > 0 else 1.0

        print()
        for line in iter(process.stdout.readline, ''):
            match = time_pattern.search(line)
            if match:
                elapsed_time_str = match.group(1)
                # Aman memanggil method protected karena berada di class yang sama
                elapsed_sec = FFmpegUtils._time_str_to_seconds(elapsed_time_str)
                
                progress_percent = (elapsed_sec / duration_sec) * 100
                progress_percent = min(100, max(0, progress_percent))

                bar_length = 30
                filled_length = int(bar_length * progress_percent // 100)
                bar = '█' * filled_length + '-' * (bar_length - filled_length)
                
                print(f'\r   ⏳ {label}: [{bar}] {progress_percent:.1f}%', end='', flush=True)

        process.wait()
        print()

        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg gagal dengan kode exit {process.returncode}")
