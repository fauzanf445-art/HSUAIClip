import re
import subprocess
import logging
import sys
from typing import List, Optional, Deque, Dict, Any
from pathlib import Path
from collections import deque
import time

class UtilsProgress:
    """
    Wrapper class untuk menangani eksekusi FFmpeg dengan progress bar otomatis.
    """
    
    def _print_progress(self, percent: float, task_name: str, extra_info: str = ""):
        # Optimization: Only update if percentage changed significantly or it's 100%
        # And also, throttle updates to avoid flickering
        current_time = time.time()
        # Update if percentage changed by at least 1%, or if it's the first update, or if it's 100%,
        # or if 0.1 seconds have passed since the last update.
        if (percent - self._last_printed_percent < 1.0 and percent < 100 and
            current_time - self._last_update_time < 0.1 and self._last_printed_percent != -1.0):
            return

        self._last_printed_percent = percent
        self._last_update_time = current_time
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

    def __init__(self):
        self._last_printed_percent = -1.0 # Initialize to a value that ensures first print
        self._last_update_time = 0.0 # Initialize last update time

    TIME_PATTERN = re.compile(r'time=\s*(\d+):(\d{2}):(\d{2})\.(\d{2})') # Used for non-cutting tasks
    DURATION_PATTERN = re.compile(r'Duration: (\d+):(\d{2}):(\d{2})\.(\d{2})')

    # Argumen audio untuk klip video (AAC - format umum untuk MP4/MKV)
    AAC_AUDIO_ARGS = [
        '-c:a', 'aac',
        '-ar', '44100',
        '-b:a', '192k'
    ]

    # Argumen audio untuk konversi ke MP3 (untuk analisis AI)
    MP3_AUDIO_ARGS = [
        '-c:a', 'libmp3lame',
        '-b:a', '128k',      # Bitrate yang seimbang untuk ucapan
        '-ar', '16000',      # Sample rate standar untuk speech-to-text
    ]

    # Konstanta untuk pemotongan klip
    CLIP_END_PADDING_SECONDS = 0.15
    SEEK_BUFFER_SECONDS = 5.0

    _cached_ffmpeg_clip_args: Optional[List[str]] = None

    @staticmethod
    def _get_video_encoder_args() -> List[str]:
        """
        Mendeteksi hardware acceleration yang tersedia dan mengembalikan list argumen FFmpeg *hanya untuk video*.
        """
        # 1. Cek NVIDIA NVENC (Prioritas Utama)
        try:
            subprocess.run(
                ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1', 
                 '-c:v', 'h264_nvenc', '-f', 'null', '-'], 
                check=True, capture_output=True
            )
            logging.info("🚀 Hardware Detected: NVIDIA NVENC")
            return [
                '-c:v', 'h264_nvenc',
                '-preset', 'p4',       # Balance antara speed dan quality
                '-cq', '23',           # Constant Quality
                '-rc', 'vbr',          # Variable Bitrate
                '-pix_fmt', 'yuv420p'  # Kompatibilitas universal
            ]
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
            return [
                '-c:v', 'h264_qsv',
                '-global_quality', '23', # ICQ (Intelligent Constant Quality)
                '-preset', 'veryfast',   # Prioritaskan kecepatan, karena QSV sudah sangat efisien
                '-pix_fmt', 'nv12'       # Format warna standar Intel
            ]
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass # Lanjut ke fallback

        # 3. Cek AMD AMF
        try:
            subprocess.run(
                ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1',
                 '-c:v', 'h264_amf', '-f', 'null', '-'],
                check=True, capture_output=True
            )
            logging.info("🚀 Hardware Detected: AMD AMF")
            return [
                '-c:v', 'h264_amf',
                '-quality', '2',       # 0=lossless, 1=best, 2=good balance
                '-pix_fmt', 'yuv420p'
            ]
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass # Lanjut ke pengecekan berikutnya

        # 4. Cek Apple VideoToolbox (macOS)
        try:
            subprocess.run(
                ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1',
                 '-c:v', 'h264_videotoolbox', '-f', 'null', '-'],
                check=True, capture_output=True
            )
            logging.info("🚀 Hardware Detected: Apple VideoToolbox")
            return [
                '-c:v', 'h264_videotoolbox',
                '-b:v', '4M',          # Bitrate-based quality
                '-pix_fmt', 'yuv420p'
            ]
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass # Lanjut ke fallback

        # 5. Fallback ke CPU (libx264) - Berjalan di semua perangkat
        logging.info("⚠️ No GPU detected. Falling back to CPU (libx264).")   
        return [
            '-c:v', 'libx264',
            '-preset', 'ultrafast',  # Prioritaskan kecepatan encoding di CPU
            '-pix_fmt', 'yuv420p'
        ]

    @staticmethod
    def get_clip_creation_args() -> List[str]:
        """
        Mengembalikan konfigurasi lengkap FFmpeg untuk pembuatan klip video.
        Menggabungkan argumen video (HW Accel), audio (AAC), dan argumen umum.
        """
        if UtilsProgress._cached_ffmpeg_clip_args is not None:
            return UtilsProgress._cached_ffmpeg_clip_args
        
        logging.debug("🔄 Membuat argumen FFmpeg untuk klip...")
        video_args = UtilsProgress._get_video_encoder_args()
        
        fps_args = ['-r', '30', '-vsync', 'cfr']
        
        common_args = [
            '-avoid_negative_ts', 'make_zero',
            '-fflags', '+genpts+igndts',
            '-map_metadata', '0',
            '-threads', '0'
        ]
        
        # Gabungkan semua: FPS + Video Encoder + Audio Encoder + Argumen Umum
        args = fps_args + video_args + UtilsProgress.AAC_AUDIO_ARGS + common_args
        
        logging.debug(f"✅ Argumen FFmpeg berhasil dibuat: {args}")
        UtilsProgress._cached_ffmpeg_clip_args = args
        return args

    def _execute_with_stderr_parse(self, cmd: List[str], task_name: str, total_duration: Optional[float] = None):
        """Eksekusi FFmpeg dengan progress dari parsing stderr (untuk konversi/download)."""
        try:
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, encoding='utf-8', errors='ignore')
            
            if not process.stderr:
                if process: process.wait()
                return

            stderr_output: Deque[str] = deque([], maxlen=20)
            total_duration_from_ffmpeg = total_duration if total_duration else 0.0

            for line in process.stderr:
                stderr_output.append(line)
                if total_duration_from_ffmpeg <= 0:
                    duration_match = self.DURATION_PATTERN.search(line)
                    if duration_match:
                        h, m, s, hs = map(int, duration_match.groups())
                        total_duration_from_ffmpeg = h * 3600 + m * 60 + s + hs / 100
                if 'time=' in line:
                    match = self.TIME_PATTERN.search(line)
                    if match:
                        h, m, s, hs = map(int, match.groups())
                        logging.debug(f"FFmpeg Output Line: {line.strip()}")
                        current_time = h * 3600 + m * 60 + s + hs / 100
                        percent = min(100, (current_time / total_duration_from_ffmpeg) * 100) if total_duration_from_ffmpeg > 0 else 0
                        self._print_progress(percent, task_name)
            
            process.wait()
            if process.returncode != 0:
                error_log = "".join(stderr_output)
                logging.error(f"FFmpeg Error during '{task_name}'. Details:\n{error_log}")
                raise subprocess.CalledProcessError(process.returncode, cmd, stderr=error_log)
        finally:
            sys.stdout.write("\n")

    def execute(self, cmd: List[str], task_name: str, total_duration: Optional[float] = None):
        """
        Menjalankan perintah FFmpeg dan menampilkan progress bar.
        Menggunakan parsing stderr untuk semua jenis tugas.
        """
        # Filter argumen stats agar tidak duplikat, karena kita menangani progress sendiri
        cmd = [arg for arg in cmd if arg not in ['-stats']]
        self._execute_with_stderr_parse(cmd, task_name, total_duration)

    def download_audio_from_stream(self, stream_urls: Optional[tuple[Optional[str], Optional[str]]], output_path: Path, duration: Optional[float] = None) -> Optional[Path]:
        """Mengunduh audio dari stream URL dan meng-encode ke MP3."""
        if not stream_urls:
            logging.error("❌ Gagal mendapatkan URL stream untuk audio.")
            return None
            
        video_url, audio_url = stream_urls
        target_url = audio_url if audio_url else video_url
        
        if not target_url:
             logging.error("❌ URL stream kosong.")
             return None

        # Opsi 4: Optimasi Jaringan untuk koneksi yang lebih tangguh
        network_args = [
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '5'
        ]

        # Opsi 5: Multithreading untuk memaksimalkan penggunaan CPU
        thread_args = ['-threads', '0']

        cmd = [
            'ffmpeg', '-y',
            *network_args,
            '-i', target_url,
            *self.MP3_AUDIO_ARGS,
            *thread_args,
            '-vn', str(output_path)
        ]
        
        try:
            self.execute(cmd, "Download Audio", total_duration=None)
            
            if output_path.exists() and output_path.stat().st_size > 1024:
                return output_path

        except Exception as e:
            logging.error(f"❌ Gagal download audio via FFmpeg: {e}")
        
        return None

    def create_clip_from_stream(self, stream_urls: Optional[tuple[Optional[str], Optional[str]]], task: Dict[str, Any], ffmpeg_args: List[str]) -> Optional[Path]:
        """Membuat klip video presisi dari stream URL menggunakan FFmpeg."""
        clip = task['clip_info']
        output_path = task['output_path']
        start = float(clip['start_time'])
        end = float(clip['end_time'])
        title = clip['title']
        duration = (end - start) + self.CLIP_END_PADDING_SECONDS

        if not stream_urls or not stream_urls[0]:
            logging.error(f"   ❌ Inisiasi gagal: Tidak dapat memperoleh URL stream untuk '{title}'. Melewati pemotongan.")
            return None
            
        video_url, audio_url = stream_urls
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fast_seek_time = max(0, start - self.SEEK_BUFFER_SECONDS)
        accurate_seek_offset = self.SEEK_BUFFER_SECONDS if start > self.SEEK_BUFFER_SECONDS else start

        cmd: List[str] = [
            'ffmpeg', '-nostats',
            '-ss', f"{fast_seek_time:.6f}", '-i', str(video_url),
        ]

        if audio_url:
            cmd.extend(['-ss', f"{fast_seek_time:.6f}", '-i', str(audio_url)])
        
        cmd.extend(['-ss', f"{accurate_seek_offset:.6f}", '-t', f"{duration:.6f}"])

        if audio_url:
            cmd.extend(['-map', '0:v:0', '-map', '1:a:0'])

        cmd.extend([*(ffmpeg_args or []), '-y', str(output_path)])

        try:
            self.execute(cmd, f"Memotong Klip: {output_path.name}", total_duration=duration)
            return output_path if output_path.exists() and output_path.stat().st_size > 1024 else None
        except Exception as e:
            logging.error(f"   ❌ Eksekusi FFmpeg gagal untuk klip '{title}': {e}")
            return None
