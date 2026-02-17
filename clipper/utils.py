import re
import subprocess
import logging
import os
import sys
from functools import lru_cache
from typing import List, Optional, Deque, Dict, Any
from collections import deque
import shutil
from pathlib import Path

class UtilsProgress:
    """
    Wrapper class untuk menangani eksekusi FFmpeg dengan progress bar otomatis.
    """
    
    def _print_progress(self, percent: float, task_name: str, extra_info: str = ""):
        """Menampilkan progress bar standar ke terminal."""
        bar_length = 25
        filled_length = int(bar_length * percent // 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        if len(extra_info) > 30:
            extra_info = extra_info[:27] + "..."
            
        try:
            sys.stdout.write(f"\r⏳ {task_name}: {bar} {int(percent)}% {extra_info}\033[K")
            sys.stdout.flush()
        
        except UnicodeEncodeError:
            # Fallback jika terminal tidak mendukung emoji (misal cmd.exe legacy)
            sys.stdout.write(f"\r[Progress] {task_name}: {bar} {int(percent)}% {extra_info}\033[K")
            sys.stdout.flush()

    TIME_PATTERN = re.compile(r'time=\s*(\d+):(\d{2}):(\d{2})\.(\d{2})')
    DURATION_PATTERN = re.compile(r'Duration: (\d+):(\d{2}):(\d{2})\.(\d{2})')

    AUDIO_ARGS = [
        '-c:a', 'aac',
        '-ar', '44100',
        '-b:a', '192k'
    ]

    @staticmethod
    @lru_cache(maxsize=1)
    def _get_ffmpeg_args():
        """
        Mendeteksi hardware acceleration yang tersedia dan mengembalikan list argumen FFmpeg.
        Mengembalikan konfigurasi lengkap FFmpeg (HW Accel + Audio Settings).
        """
        
        # Argumen dasar untuk memaksa Constant Frame Rate (CFR) dan set FPS
        # -vsync cfr memastikan interval antar frame benar-benar kaku
        fps_args = ['-r', '30', '-vsync', 'cfr']

        # Argumen audio dan stabilitas yang umum untuk semua konfigurasi
        common_args = [
            *UtilsProgress.AUDIO_ARGS,
            # Bendera stabilitas
            '-avoid_negative_ts', 'make_zero',
            '-fflags', '+genpts+igndts',
            '-map_metadata', '0',
            '-threads', '0'
        ]
        
        # 1. Cek NVIDIA NVENC (Prioritas Utama)
        try:
            subprocess.run(
                ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1', 
                 '-c:v', 'h264_nvenc', '-f', 'null', '-'], 
                check=True, capture_output=True
            )
            logging.info("🚀 Hardware Detected: NVIDIA NVENC")
            args = fps_args + [
                '-c:v', 'h264_nvenc',
                '-preset', 'p4',       # Balance antara speed dan quality
                '-cq', '23',           # Constant Quality
                '-rc', 'vbr',          # Variable Bitrate
                '-pix_fmt', 'yuv420p'  # Kompatibilitas universal
            ]
            args.extend(common_args)
            return args
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass # Lanjut ke pengecekan berikutnya

        # 2. Cek Intel QuickSync (QSV)
        try:
            subprocess.run(
                ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1', 
                 '-c:v', 'h264_qsv', '-f', 'null', '-'], 
                check=True, capture_output=True
            )
            logging.info("🚀 Hardware Detected: Intel QuickSync (QSV)")
            args = fps_args + [
                '-c:v', 'h264_qsv',
                '-global_quality', '23', # ICQ (Intelligent Constant Quality)
                '-preset', 'veryfast',   # Prioritaskan kecepatan, karena QSV sudah sangat efisien
                '-pix_fmt', 'nv12'       # Format warna standar Intel
            ]
            args.extend(common_args)
            return args
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass # Lanjut ke fallback

        # 3. Fallback ke CPU (libx264) - Berjalan di semua perangkat
        logging.info("⚠️ No GPU detected. Falling back to CPU (libx264).")   
        args = fps_args + [
            '-c:v', 'libx264',
            '-preset', 'ultrafast',  # Prioritaskan kecepatan encoding di CPU (kualitas lebih rendah)
        ]
        args.extend(common_args)
        return args

    @staticmethod
    def yt_dlp_progress_hook(d: Dict[str, Any]):
        """Progress hook khusus untuk menangani output dari yt-dlp."""
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            
            if total > 0:
                percent_val = (downloaded / total) * 100
                p_str = f"{percent_val:.1f}%"
                bar_length = 25
                filled_length = int(bar_length * percent_val // 100)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
            else:
                p_str = "Unknown%"
                bar = '░' * 25
            sys.stdout.write(f"\r⏳ Download: {bar} {p_str} \033[K")
            sys.stdout.flush()
        elif d['status'] == 'finished':
            sys.stdout.write(f"\r✅ Download selesai!{' ' * 50}\n")
            sys.stdout.flush()

    def execute(self, cmd: List[str], task_name: str):
        """
        Menjalankan perintah FFmpeg dan menampilkan progress bar.
        Durasi dideteksi otomatis dari output stderr FFmpeg.
        """
        executable = cmd[0]
        if shutil.which(executable) is None and not os.path.isfile(executable):
            logging.warning(f"⚠️ Program '{executable}' mungkin tidak ditemukan di PATH.")

        # Filter argumen stats agar tidak duplikat
        cmd = [arg for arg in cmd if arg not in ['-stats']]

        try:
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, encoding='utf-8', errors='ignore')
        except FileNotFoundError:
            raise FileNotFoundError(f"❌ FFmpeg tidak ditemukan saat mencoba menjalankan: {cmd[0]}")

        stderr_output: Deque[str] = deque([], maxlen=20)
        total_duration = 0.0
        
        if process.stderr is None:
            process.wait()
            return
        
        for line in process.stderr:
            stderr_output.append(line)

            # Coba tangkap durasi dari output FFmpeg jika belum diketahui
            if total_duration <= 0:
                duration_match = self.DURATION_PATTERN.search(line)
                if duration_match:
                    hours, minutes, seconds, hundredths = map(int, duration_match.groups())
                    total_duration = hours * 3600 + minutes * 60 + seconds + hundredths / 100

            if 'time=' in line:
                match = self.TIME_PATTERN.search(line)
                if match:
                    hours, minutes, seconds, hundredths = map(int, match.groups())
                    current_time = hours * 3600 + minutes * 60 + seconds + hundredths / 100
                    
                    percent = 0
                    if total_duration > 0:
                        percent = min(100, int((current_time / total_duration) * 100))
                    
                    self._print_progress(percent, task_name)

        process.wait()
        
        # Pastikan baris baru dicetak setelah progress selesai agar tidak tertimpa log berikutnya
        sys.stdout.write("\n")

        if process.returncode != 0:
            error_log = "".join(stderr_output)
            logging.error(f"FFmpeg Error during '{task_name}'. Details:\n{error_log}")
            raise subprocess.CalledProcessError(process.returncode, cmd, stderr="".join(stderr_output))

    def convert_to_mp3(self, input_path: Path, output_path: Path):
        """Mengkonversi file audio/video ke MP3 dengan progress bar."""
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        cmd = [
            'ffmpeg', '-y',
            '-i', str(input_path),
            '-vn', # No video
            '-c:a', 'libmp3lame',
            '-b:a', '192k',
            '-ar', '44100',
            str(output_path)
        ]
        
        logging.debug(f"🎵 Mengkonversi ke MP3: {output_path.name}")
        self.execute(cmd, "Konversi Audio")

    def process_dlp_clip(self, input_path: Path, output_path: Path, ffmpeg_args: Optional[List[str]] = None):
        """
        (Stage 2) Mengkonversi klip mentah dari yt-dlp ke format final dengan progress bar,
        memanfaatkan akselerasi hardware jika tersedia.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if ffmpeg_args is None:
            ffmpeg_args = UtilsProgress._get_ffmpeg_args()

        cmd = ['ffmpeg', '-y', '-i', str(input_path)] + ffmpeg_args + [str(output_path)]
        
        logging.info(f"🎬 Encoding Clip: {output_path.name}")
        self.execute(cmd, "Encoding Video")
