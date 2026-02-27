import re
import subprocess
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path

from tqdm import tqdm
from .models import Clip

class FFmpegWrapper:
    """
    Wrapper class untuk menangani eksekusi FFmpeg dengan progress bar otomatis.
    Menggantikan UtilsProgress lama.
    """
    
    TIME_PATTERN = re.compile(r'time=\s*(\d+):(\d{2}):(\d{2})\.(\d{2})') # Used for non-cutting tasks
    DURATION_PATTERN = re.compile(r'Duration: (\d+):(\d{2}):(\d{2})\.(\d{2})')

    # Argumen audio untuk klip video (AAC - format umum untuk MP4/MKV)
    AAC_AUDIO_ARGS = [
        '-c:a', 'aac',
        '-ar', '44100',
        '-b:a', '192k'
    ]

    # Konstanta untuk pemotongan klip
    CLIP_END_PADDING_SECONDS = 0.15
    SEEK_BUFFER_SECONDS = 5.0

    _cached_ffmpeg_clip_args: Optional[List[str]] = None

    def __init__(self):
        pass # No longer needs to initialize ConsoleProgressBar

    @staticmethod
    def _check_encoder_exists(encoder: str) -> bool:
        """
        Memeriksa apakah encoder yang diberikan ada dalam daftar encoder FFmpeg.
        """
        try:
            result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, check=True)
            return encoder in result.stdout
        except subprocess.CalledProcessError as e:
            logging.error(f"Gagal memeriksa encoder: {e}")
            return False

    @staticmethod
    def _get_video_encoder_args() -> List[str]:
        """
        Mendeteksi hardware acceleration yang tersedia dan mengembalikan list argumen FFmpeg *hanya untuk video*.
        """
        # 1. Cek NVIDIA NVENC (Prioritas Utama)
        try:
            if not FFmpegWrapper._check_encoder_exists('h264_nvenc'):
                raise FileNotFoundError("Encoder h264_nvenc tidak ditemukan.")

            subprocess.run(
                ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=256x256:d=0.1', 
                 '-c:v', 'h264_nvenc', '-f', 'null', '-'], 
                check=True, capture_output=True
            )
            logging.info("🚀 Hardware Detected: NVIDIA NVENC")
            return [
                '-c:v', 'h264_nvenc',
                '-preset', 'p4',
                '-cq', '24',           # Constant Quality
                '-rc', 'vbr',          # Variable Bitrate
                '-tune', 'hq',         # High Quality tuning
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
        """
        if FFmpegWrapper._cached_ffmpeg_clip_args is not None:
            return FFmpegWrapper._cached_ffmpeg_clip_args

        logging.debug("🔄 Membuat argumen FFmpeg untuk klip...")
        video_args = FFmpegWrapper._get_video_encoder_args()
        
        fps_args = ['-r', '30', '-vsync', '1']
        common_args = [
            '-avoid_negative_ts', 'make_zero',
            '-fflags', '+genpts+igndts',
            '-map_metadata', '0',
            '-threads', '0'
        ]
        
        args = fps_args + video_args + FFmpegWrapper.AAC_AUDIO_ARGS + common_args
        
        logging.debug(f"✅ Argumen FFmpeg berhasil dibuat: {args}")
        FFmpegWrapper._cached_ffmpeg_clip_args = args
        return args

    def _execute_with_stderr_parse(self, cmd: List[str], task_name: str, total_duration: Optional[float] = None, silent: bool = False):
        """Eksekusi FFmpeg dengan progress dari parsing stderr."""
        with tqdm(total=100, desc=task_name, disable=silent, leave=False, unit='%') as pbar:
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace')
            
            if not process.stderr:
                if process: process.wait()
                return

            try:
                stderr_output: List[str] = []
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
                            current_time = h * 3600 + m * 60 + s + hs / 100
                            percent = min(100, (current_time / total_duration_from_ffmpeg) * 100) if total_duration_from_ffmpeg > 0 else 0
                            pbar.n = int(percent)
                            pbar.refresh()
                
                process.wait()
                if process.returncode != 0:
                    error_log = "".join(stderr_output)
                    logging.error(f"FFmpeg Error during '{task_name}'. Details:\n{error_log}")
                    raise subprocess.CalledProcessError(process.returncode, cmd, stderr=error_log)
            except Exception as e:
                logging.error(f"Error parsing FFmpeg output: {e}")
                if process: process.kill()
                raise

    def execute(self, cmd: List[str], task_name: str, total_duration: Optional[float] = None, silent: bool = False):
        """Menjalankan perintah FFmpeg dan menampilkan progress bar."""
        cmd = [arg for arg in cmd if arg not in ['-stats']]
        self._execute_with_stderr_parse(cmd, task_name, total_duration, silent=silent)

    def create_clip_from_stream(self, stream_urls: Optional[tuple[Optional[str], Optional[str]]], task: Dict[str, Any], ffmpeg_args: List[str], silent: bool = False) -> Optional[Path]:
        """Membuat klip video presisi dari stream URL menggunakan FFmpeg."""
        clip: Clip = task['clip_info']
        output_path = task['output_path']
        start = clip.start_time
        end = clip.end_time
        title = clip.title
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

        cmd.extend([*ffmpeg_args, '-y', str(output_path)])

        try:
            self.execute(cmd, f"Processing: {output_path.name}", total_duration=duration, silent=silent)
            return output_path if output_path.exists() and output_path.stat().st_size > 1024 else None
        except Exception as e:
            logging.error(f"   ❌ Eksekusi FFmpeg gagal untuk klip '{title}': {e}")
            return None

    def convert_audio_to_wav(self, input_path: Path, output_path: Path) -> Optional[Path]:
        """Mengonversi file audio ke format WAV (16kHz, Mono)."""
        cmd = [
            'ffmpeg', '-y',
            '-i', str(input_path),
            '-acodec', 'pcm_s16le', '-ac', '1', '-ar', '16000',
            str(output_path)
        ]
        try:
            self.execute(cmd, "Konversi Audio", total_duration=None, silent=False)
            if output_path.exists() and output_path.stat().st_size > 1024: return output_path
        except Exception as e:
            logging.error(f"❌ Gagal konversi audio: {e}")
        return None

    def render_final_clip(self, video_path: Path, audio_path: Path, subtitle_path: Optional[Path], output_path: Path, fonts_dir: Optional[Path] = None) -> bool:
        """
        Merender video final dengan menggabungkan:
        1. Video hasil crop (OpenCV)
        2. Audio dari klip asli
        3. Subtitle (jika ada)
        """        
        try:
            encoder_args = self.get_clip_creation_args()
            
            # Input 0: Video Cropped (Tanpa Audio)
            # Input 1: Audio Source (Klip Asli)
            
            filter_chain = "[0:v]null[v_out]" # Default pass-through jika tidak ada subtitle
            if subtitle_path and subtitle_path.exists():
                # Escape sequence untuk FFmpeg filter:
                # 1. Backslash (\) -> \\
                # 2. Kutip satu (') -> '\''
                # 3. Titik dua (:) -> \:
                escaped_sub_path = subtitle_path.resolve().as_posix().replace('\\', '\\\\').replace("'", "'\\''").replace(':', '\\:')
                
                fonts_opt = ""
                if fonts_dir and fonts_dir.exists():
                    escaped_fonts_dir = fonts_dir.resolve().as_posix().replace('\\', '\\\\').replace("'", "'\\''").replace(':', '\\:')
                    fonts_opt = f":fontsdir='{escaped_fonts_dir}'"

                filter_chain = f"[0:v]ass='{escaped_sub_path}'{fonts_opt}[v_out]"

            cmd = [
                'ffmpeg', '-y', '-nostats',
                '-i', str(video_path), 
                '-i', str(audio_path),
                '-filter_complex', filter_chain,
                '-map', '[v_out]', '-map', '1:a:0',
                '-shortest', *encoder_args, str(output_path)
            ]

            total_duration = None
            try:
                probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(video_path)]
                total_duration = float(subprocess.check_output(probe_cmd).decode('utf-8').strip())
            except Exception as e:
                logging.warning(f"Could not determine video duration with ffprobe for progress bar: {e}")

            self.execute(cmd, f"Rendering: {output_path.name}", total_duration=total_duration, silent=False)
            return True
        except Exception as e:
            logging.error(f"Gagal merender video: {e}", exc_info=True)
            return False