import re
import subprocess
import logging
import os
from functools import lru_cache
from typing import List, Optional, Callable, Dict, Any, Deque
from collections import deque
import shutil

# Pre-compile regex untuk performa parsing log FFmpeg yang lebih baik (CPU Efficient)
TIME_PATTERN = re.compile(r'time=(\d+):(\d{2}):(\d{2})\.(\d{2})')

@lru_cache(maxsize=128)
def get_duration(file_path: str) -> float:
    """Mendapatkan durasi file media dalam detik untuk perhitungan progres (Cached)."""
    # Optimasi: Cek eksistensi file sebelum memanggil subprocess yang mahal
    if not os.path.exists(file_path):
        return 0.0

    # Coba cari ffprobe di path atau gunakan default
    ffprobe_cmd = "ffprobe"
    
    cmd = [
        ffprobe_cmd, '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        str(file_path)
    ]
    try:
        # Gunakan shell=True di Windows jika path tidak ditemukan langsung, atau rely on PATH
        return float(subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode('utf-8').strip())
    except Exception as e:
        logging.warning(f"Gagal mendapatkan durasi untuk {file_path}: {e}")
        return 0.0

def get_ffmpeg_args():
    """
    Mendeteksi hardware acceleration yang tersedia dan mengembalikan list argumen FFmpeg.
    Mengembalikan konfigurasi lengkap FFmpeg (HW Accel + Audio Settings).
    """
    
    # Argumen dasar untuk memaksa Constant Frame Rate (CFR) dan set FPS
    # -vsync cfr memastikan interval antar frame benar-benar kaku
    fps_args = ['-r', '30', '-vsync', 'cfr']
    
    # 1. Cek NVIDIA NVENC
    try:
        subprocess.run(
            ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1', 
             '-c:v', 'h264_nvenc', '-f', 'null', '-'], 
            check=True, capture_output=True
        )
        logging.info("🚀 Hardware Detected: NVIDIA NVENC")
        base_args = fps_args + [
            '-c:v', 'h264_nvenc',
            '-preset', 'p4',       # Balance antara speed dan quality
            '-cq', '23',           # Constant Quality
            '-rc', 'vbr',          # Variable Bitrate
            '-pix_fmt', 'yuv420p'  # Kompatibilitas universal
        ]
    except (subprocess.CalledProcessError, FileNotFoundError):
        base_args = fps_args + [
            '-c:v', 'libx264',
            '-preset', 'medium'
        ]

    # 2. Cek Intel QuickSync (QSV)
    try:
        subprocess.run(
            ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1', 
             '-c:v', 'h264_qsv', '-f', 'null', '-'], 
            check=True, capture_output=True
        )
        logging.info("🚀 Hardware Detected: Intel QuickSync (QSV)")
        base_args = fps_args + [
            '-c:v', 'h264_qsv',
            '-global_quality', '23', # ICQ (Intelligent Constant Quality)
            '-preset', 'veryslow',   # QSV sangat cepat, bisa pakai preset lambat agar kualitas maksimal
            '-pix_fmt', 'nv12'       # Format warna standar Intel
        ]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 3. Fallback ke CPU (libx264) - Berjalan di semua perangkat
    logging.info("⚠️ No GPU detected. Falling back to CPU (libx264).")   
    args = base_args
    
    args.extend([
        '-c:a', 'aac',          # Codec Audio
        '-ar', '44100',
        '-map_metadata', '-1',
    ])
    return args


def _print_progress(percent: float, task_name: str, extra_info: str = ""):
    """Menampilkan progress bar standar ke terminal."""
    bar_length = 25
    filled_length = int(bar_length * percent // 100)
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    if len(extra_info) > 30:
        extra_info = extra_info[:27] + "..."
        
    try:
        print(f"\r⏳ {task_name}: {bar} {int(percent)}% {extra_info}{' '*10}", end='', flush=True)
    except UnicodeEncodeError:
        # Fallback jika terminal tidak mendukung emoji (misal cmd.exe legacy)
        print(f"\r[Progress] {task_name}: {bar} {int(percent)}% {extra_info}{' '*10}", end='', flush=True)

def ffmpeg_progress_hook(cmd: List[str], total_duration: float, task_name: str, progress_callback: Optional[Callable[[int, str], None]] = None):
    """
    Menjalankan perintah FFmpeg dan menampilkan progress bar.
    Jika total_duration 0, mencoba mendeteksi otomatis dari input file di cmd.
    """
    # Deteksi otomatis durasi jika tidak disediakan
    if total_duration <= 0:
        try:
            if '-i' in cmd:
                idx = cmd.index('-i')
                if idx + 1 < len(cmd):
                    total_duration = get_duration(cmd[idx + 1])
        except Exception:
            pass

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
    
    if process.stderr is None:
        process.wait()
        return
    
    for line in process.stderr:
        stderr_output.append(line)
        if 'time=' in line:
            match = TIME_PATTERN.search(line)
            if match:
                hours, minutes, seconds, hundredths = map(int, match.groups())
                current_time = hours * 3600 + minutes * 60 + seconds + hundredths / 100
                
                percent = 0
                if total_duration > 0:
                    percent = min(100, int((current_time / total_duration) * 100))
                
                if progress_callback:
                    progress_callback(percent, task_name)
                else:
                    _print_progress(percent, task_name)

    process.wait()
    if not progress_callback: print('\r', end='', flush=True)

    if process.returncode != 0:
        error_log = "".join(stderr_output)
        logging.error(f"FFmpeg Error during '{task_name}'. Details:\n{error_log}")
        raise subprocess.CalledProcessError(process.returncode, cmd, stderr="".join(stderr_output))

def downloader_progress_hook(d: Dict[str, Any]) -> None:
    """Hook untuk menampilkan progress bar download yt-dlp di terminal."""
    if d['status'] == 'downloading':
        # Hapus try-except global agar error tidak tertelan diam-diam
        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
        downloaded = d.get('downloaded_bytes', 0)
        
        percent = 0
        if total > 0:
            percent = (downloaded / total) * 100
        
        speed = d.get('speed')
        speed_str = "N/A"
        if speed and speed > 0:
            speed_str = f"{speed/1024/1024:.1f}MiB/s" if speed > 1024*1024 else f"{speed/1024:.1f}KiB/s"
        
        _print_progress(percent, "Downloading", f"| {speed_str}")
    elif d['status'] == 'finished':
        print(f'\r✅ Download selesai.{" "*50}', flush=True)
