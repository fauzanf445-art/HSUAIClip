import subprocess
import logging
import os
from pathlib import Path
from typing import List, Optional, Callable, Tuple

from src.domain.interfaces import IVideoProcessor
from src.domain.exceptions import VideoProcessingError
from src.infrastructure.common.json_cache import JsonCache

class FFmpegAdapter(IVideoProcessor):
    """
    Implementasi IVideoProcessor menggunakan FFmpeg CLI.
    Menangani pemotongan, konversi, dan rendering video dengan deteksi hardware acceleration.
    """
    
    # Konstanta teknis
    CLIP_END_PADDING_SECONDS = 0.15
    SEEK_BUFFER_SECONDS = 5.0
    
    # Argumen audio standar
    AAC_AUDIO_ARGS = [
        '-c:a', 'aac',
        '-ar', '44100',
        '-b:a', '192k'
    ]
    
    # Argumen video CPU sebagai fallback
    CPU_VIDEO_ARGS = ['-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p']

    def __init__(self, bin_path: str = "ffmpeg", cache_path: Optional[Path] = None):
        self.bin_path = bin_path
        self.cache_path = cache_path
        self._video_args: List[str] = []
        self._common_args: List[str] = []
        self._codec_args: List[str] = []

    @property
    def is_gpu_enabled(self) -> bool:
        """Mengembalikan True jika encoder yang aktif bukan CPU default."""
        if not self._codec_args:
            self.initialize()
        return self._video_args != self.CPU_VIDEO_ARGS

    @staticmethod
    def _escape_ffmpeg_path(path_str: str) -> str:
        """
        Meng-escape path untuk digunakan di dalam filter complex FFmpeg.
        Ini penting untuk Windows (meng-handle C: dan path dengan karakter spesial.
        """
        p = Path(path_str).resolve().as_posix()
        # Di Windows, C:\path menjadi C:/path, lalu di-escape menjadi C\:/path
        return p.replace(':', '\\:')

    def _is_encoder_functional(self, encoder_name: str, test_args: List[str]) -> bool:
        """
        Menjalankan verifikasi aktif untuk sebuah encoder dengan command FFmpeg singkat.
        """
        logging.debug(f"   -> Memverifikasi fungsionalitas encoder: {encoder_name}...")
        cmd = [
            self.bin_path, '-nostats', '-y',
            '-f', 'lavfi', '-i', 'color=s=64x64:rate=30', # Input virtual kecil
            '-t', '0.1', # Durasi sangat pendek
        ]
        cmd.extend(test_args)
        cmd.extend(['-f', 'null', '-']) # Output ke null device

        try:
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            if process.returncode == 0:
                logging.debug(f"   ✅ Verifikasi {encoder_name} berhasil.")
                return True
            else:
                logging.debug(f"   ⚠️ Verifikasi {encoder_name} gagal. FFmpeg stderr:\n{process.stderr}")
                return False
        except FileNotFoundError:
            # This happens if ffmpeg itself is not found
            logging.error("❌ FFmpeg tidak ditemukan. Pastikan sudah terinstall dan ada di PATH sistem atau di folder 'bin'.")
            raise
        except Exception as e:
            logging.warning(f"   ⚠️ Exception saat verifikasi {encoder_name}: {e}")
            return False

    def _determine_best_encoder(self) -> Tuple[str, List[str]]:
        """Mendeteksi hardware acceleration (NVIDIA, Intel, AMD, Apple) secara aktif."""
        # Daftar encoder untuk dicoba, dalam urutan prioritas
        encoders_to_test = [
            ('h264_nvenc', "NVIDIA NVENC", ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '24', '-rc', 'vbr', '-tune', 'hq', '-pix_fmt', 'yuv420p']),
            ('h264_qsv', "Intel QuickSync (QSV)", ['-c:v', 'h264_qsv', '-global_quality', '23', '-preset', 'veryfast', '-pix_fmt', 'nv12']),
            ('h264_amf', "AMD AMF", ['-c:v', 'h264_amf', '-quality', '2', '-pix_fmt', 'yuv420p']),
            ('h264_videotoolbox', "Apple VideoToolbox", ['-c:v', 'h264_videotoolbox', '-b:v', '4M', '-pix_fmt', 'yuv420p'])
        ]

        for name, friendly_name, args in encoders_to_test:
            if self._is_encoder_functional(name, args):
                logging.info(f"🚀 FFmpeg Adapter: Menggunakan akselerasi hardware {friendly_name}.")
                return friendly_name, args

        logging.warning("⚠️ FFmpeg Adapter: Tidak ada akselerasi hardware fungsional yang terdeteksi. Menggunakan CPU (libx264).")
        return "CPU", self.CPU_VIDEO_ARGS

    def initialize(self):
        """
        Mendeteksi, memverifikasi, dan meng-cache argumen encoder. 
        Harus dipanggil sekali saat startup.
        """
        if self._codec_args: # Sudah diinisialisasi
            return

        # 1. Coba load dari cache
        loaded_from_cache = False
        if self.cache_path:
            data = JsonCache.load(self.cache_path)
            if data:
                self._video_args = data.get('video_args', [])
                encoder_name = data.get('encoder_name', 'Unknown')
                if self._video_args:
                    logging.info(f"🚀 FFmpeg Adapter: Menggunakan konfigurasi cached ({encoder_name}).")
                    loaded_from_cache = True

        # 2. Jika tidak ada cache, lakukan deteksi
        if not loaded_from_cache:
            friendly_name, self._video_args = self._determine_best_encoder()
            
            # Simpan ke cache
            if self.cache_path:
                cache_data = {'encoder_name': friendly_name, 'video_args': self._video_args}
                JsonCache.save(cache_data, self.cache_path)
        
        self._common_args = [
            '-r', '30', '-vsync', '1',
            '-avoid_negative_ts', 'make_zero',
            '-fflags', '+genpts+igndts',
            '-map_metadata', '0',
            '-threads', '0'
        ]
        
        # Gabungkan semua argumen yang akan sering digunakan
        self._codec_args = self._common_args + self._video_args + self.AAC_AUDIO_ARGS
        logging.debug(f"FFmpeg codec args initialized: {' '.join(self._codec_args)}")

    def _get_codec_args(self) -> List[str]:
        """Mengembalikan argumen klip yang sudah di-cache. Memiliki safeguard jika initialize() belum dipanggil."""
        if not self._codec_args:
            logging.debug("Lazy initialization: Detecting FFmpeg hardware support...")
            self.initialize()
        return self._codec_args

    def _get_cpu_codec_args(self) -> List[str]:
        """Mengembalikan argumen codec khusus untuk fallback CPU."""
        return self._common_args + self.CPU_VIDEO_ARGS + self.AAC_AUDIO_ARGS

    def _run_command(self, cmd: List[str], description: str) -> bool:
        """Helper untuk menjalankan subprocess dengan logging."""
        try:
            # Hapus argumen -nostats agar log bersih, karena stderr akan ditangkap
            cmd = [c for c in cmd if c != '-nostats']
            
            logging.debug(f"Running FFmpeg: {' '.join(cmd)}")
            process = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            if process.returncode != 0:
                logging.debug(f"❌ FFmpeg Failure Log ({description}):\n{process.stderr}")
                return False
                
            return True
        except Exception as e:
            logging.error(f"❌ Exception saat menjalankan FFmpeg ({description}): {e}")
            return False

    def _run_with_fallback(self, build_cmd_func: Callable[[List[str]], List[str]], description: str) -> bool:
        """
        Menjalankan command dengan mekanisme fallback ke CPU jika gagal.
        Tidak mengubah state instance secara permanen.
        """
        # Percobaan 1: Menggunakan argumen yang sudah di-cache (GPU atau CPU default)
        codec_args = self._get_codec_args()
        cmd = build_cmd_func(codec_args)
        if self._run_command(cmd, description):
            return True

        # Jika gagal, dan kita tidak sedang dalam mode CPU, coba fallback
        if self._video_args != self.CPU_VIDEO_ARGS:
            logging.warning(f"⚠️ Deteksi kegagalan pada {description}. Mencoba fallback ke CPU...")
            
            # Percobaan 2: Menggunakan argumen CPU secara eksplisit
            cpu_codec_args = self._get_cpu_codec_args()
            cmd_fallback = build_cmd_func(cpu_codec_args)
            
            if self._run_command(cmd_fallback, f"{description} (CPU Fallback)"):
                return True

        # Jika semua percobaan gagal
        return False

    def cut_clip(self, source_url: str, start: float, end: float, output_path: str, audio_url: Optional[str] = None) -> bool:
        """
        Memotong klip dari URL stream (atau file lokal).
        Menggunakan teknik seeking cepat + akurat dan mendukung fallback.
        """
        duration = (end - start) + self.CLIP_END_PADDING_SECONDS
        fast_seek_time = max(0, start - self.SEEK_BUFFER_SECONDS)
        accurate_seek_offset = self.SEEK_BUFFER_SECONDS if start > self.SEEK_BUFFER_SECONDS else start

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        def build_cmd(codec_args: List[str]) -> List[str]:
            cmd = [
                self.bin_path, '-nostats', '-y',
            ]
            
            # Tambahkan flag stabilitas jaringan untuk URL
            if source_url.startswith('http'):
                cmd.extend(['-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5'])

            cmd.extend(['-ss', f"{fast_seek_time:.6f}", '-i', source_url])

            if audio_url:
                if audio_url.startswith('http'):
                    cmd.extend(['-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5'])
                cmd.extend(['-ss', f"{fast_seek_time:.6f}", '-i', audio_url])

            cmd.extend(['-ss', f"{accurate_seek_offset:.6f}", '-t', f"{duration:.6f}"])

            if audio_url:
                # Map video dari input 0 dan audio dari input 1
                cmd.extend(['-map', '0:v:0', '-map', '1:a:0'])

            cmd.extend(codec_args)
            cmd.append(output_path)
            return cmd

        if not self._run_with_fallback(build_cmd, f"Cut Clip: {Path(output_path).name}"):
            raise VideoProcessingError(f"Gagal memotong klip: {Path(output_path).name}")
        
        return True

    def render_final(self, video_path: str, audio_path: str, subtitle_path: Optional[str], output_path: str, fonts_dir: Optional[str] = None) -> bool:
        """
        Merender hasil akhir: Video Tracked + Audio Asli + Subtitle (Burn-in).
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        def build_cmd(codec_args: List[str]) -> List[str]:
            # Filter Chain Construction
            filter_chain = "[0:v]null[v_out]"
            
            if subtitle_path and os.path.exists(subtitle_path):
                esc_sub = self._escape_ffmpeg_path(subtitle_path)
                
                fonts_opt = ""
                if fonts_dir and os.path.exists(fonts_dir):
                    esc_fonts = self._escape_ffmpeg_path(fonts_dir)
                    fonts_opt = f":fontsdir='{esc_fonts}'"

                filter_chain = f"[0:v]ass='{esc_sub}'{fonts_opt}[v_out]"

            cmd = [
                self.bin_path, '-nostats', '-y',
                '-i', video_path, # Input 0
                '-i', audio_path, # Input 1
                '-filter_complex', filter_chain,
                '-map', '[v_out]', '-map', '1:a:0',
                '-shortest'
            ]
            
            cmd.extend(codec_args)
            cmd.append(output_path)
            return cmd

        if not self._run_with_fallback(build_cmd, f"Render Final: {Path(output_path).name}"):
            raise VideoProcessingError(f"Gagal merender video final: {Path(output_path).name}")
            
        return True

    def convert_audio_to_wav(self, input_path: str, output_path: str) -> bool:
        """
        Mengonversi audio ke format WAV 16kHz Mono (standar untuk AI Speech Recognition).
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            self.bin_path, '-nostats', '-y',
            '-i', input_path,
            '-acodec', 'pcm_s16le',
            '-ac', '1',
            '-ar', '16000',
            output_path
        ]
        
        # Operasi ini hanya CPU, tidak perlu fallback
        if not self._run_command(cmd, "Convert Audio to WAV"):
            raise VideoProcessingError(f"Gagal mengonversi audio ke WAV: {input_path}")
            
        return True
