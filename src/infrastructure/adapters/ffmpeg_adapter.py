import subprocess
import logging
import os
from pathlib import Path
from typing import List, Optional, Callable

from src.domain.interfaces import IVideoProcessor

class FFmpegAdapter(IVideoProcessor):
    """
    Implementasi IVideoProcessor menggunakan FFmpeg CLI.
    Menangani pemotongan, konversi, dan rendering video dengan deteksi hardware acceleration.
    """
    
    # Konstanta teknis
    CLIP_END_PADDING_SECONDS = 0.15
    SEEK_BUFFER_SECONDS = 5.0
    
    AAC_AUDIO_ARGS = [
        '-c:a', 'aac',
        '-ar', '44100',
        '-b:a', '192k'
    ]

    def __init__(self, bin_path: str = "ffmpeg"):
        self.bin_path = bin_path
        self._cached_args: Optional[List[str]] = None
        self._force_cpu: bool = False

    def _check_encoder_exists(self, encoder: str) -> bool:
        try:
            result = subprocess.run([self.bin_path, '-encoders'], capture_output=True, text=True, check=True)
            return encoder in result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _get_video_encoder_args(self) -> List[str]:
        """Mendeteksi hardware acceleration (NVIDIA, Intel, AMD, Apple)."""
        if self._force_cpu:
            logging.info("⚠️ FFmpeg Adapter: Fallback mode active. Menggunakan CPU (libx264).")
            return ['-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p']

        encoders = [
            ('h264_nvenc', "NVIDIA NVENC", ['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '24', '-rc', 'vbr', '-tune', 'hq', '-pix_fmt', 'yuv420p']),
            ('h264_qsv', "Intel QuickSync (QSV)", ['-c:v', 'h264_qsv', '-global_quality', '23', '-preset', 'veryfast', '-pix_fmt', 'nv12']),
            ('h264_amf', "AMD AMF", ['-c:v', 'h264_amf', '-quality', '2', '-pix_fmt', 'yuv420p']),
            ('h264_videotoolbox', "Apple VideoToolbox", ['-c:v', 'h264_videotoolbox', '-b:v', '4M', '-pix_fmt', 'yuv420p'])
        ]

        for encoder_name, friendly_name, args in encoders:
            if self._check_encoder_exists(encoder_name):
                logging.info(f"🚀 FFmpeg Adapter: Menggunakan {friendly_name}")
                return args

        logging.info("⚠️ FFmpeg Adapter: GPU tidak terdeteksi. Menggunakan CPU (libx264).")
        return ['-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p']

    def _get_clip_args(self) -> List[str]:
        if self._cached_args:
            return self._cached_args
            
        video_args = self._get_video_encoder_args()
        common_args = [
            '-r', '30', '-vsync', '1',
            '-avoid_negative_ts', 'make_zero',
            '-fflags', '+genpts+igndts',
            '-map_metadata', '0',
            '-threads', '0'
        ]
        self._cached_args = common_args + video_args + self.AAC_AUDIO_ARGS
        return self._cached_args

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
                logging.error(f"❌ FFmpeg Error ({description}):\n{process.stderr}")
                return False
                
            return True
        except Exception as e:
            logging.error(f"❌ Exception saat menjalankan FFmpeg ({description}): {e}")
            return False

    def _run_with_fallback(self, build_cmd_func: Callable[[], List[str]], description: str) -> bool:
        """Menjalankan command dengan mekanisme fallback ke CPU jika gagal."""
        cmd = build_cmd_func()
        if self._run_command(cmd, description):
            return True
        
        if not self._force_cpu:
            logging.warning(f"⚠️ Deteksi kegagalan pada {description}. Mencoba fallback ke CPU...")
            self._force_cpu = True
            self._cached_args = None # Reset cache agar _get_clip_args mengambil args CPU
            
            cmd = build_cmd_func() # Rebuild command
            return self._run_command(cmd, f"{description} (CPU Fallback)")
            
        return False

    def cut_clip(self, source_url: str, start: float, end: float, output_path: str, audio_url: Optional[str] = None) -> bool:
        """
        Memotong klip dari URL stream (atau file lokal).
        Menggunakan teknik seeking cepat + akurat.
        """
        duration = (end - start) + self.CLIP_END_PADDING_SECONDS
        fast_seek_time = max(0, start - self.SEEK_BUFFER_SECONDS)
        accurate_seek_offset = self.SEEK_BUFFER_SECONDS if start > self.SEEK_BUFFER_SECONDS else start

        # Pastikan folder output ada
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        def build_cmd() -> List[str]:
            cmd = [
                self.bin_path, '-nostats', '-y',
                '-ss', f"{fast_seek_time:.6f}", '-i', source_url
            ]

            if audio_url:
                cmd.extend(['-ss', f"{fast_seek_time:.6f}", '-i', audio_url])

            cmd.extend(['-ss', f"{accurate_seek_offset:.6f}", '-t', f"{duration:.6f}"])

            if audio_url:
                # Map video dari input 0 dan audio dari input 1
                cmd.extend(['-map', '0:v:0', '-map', '1:a:0'])

            # Tambahkan encoder args
            cmd.extend(self._get_clip_args())
            cmd.append(output_path)
            return cmd

        return self._run_with_fallback(build_cmd, f"Cut Clip: {Path(output_path).name}")

    def render_final(self, video_path: str, audio_path: str, subtitle_path: Optional[str], output_path: str, fonts_dir: Optional[str] = None) -> bool:
        """
        Merender hasil akhir: Video Tracked + Audio Asli + Subtitle (Burn-in).
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        def build_cmd() -> List[str]:
            # Filter Chain Construction
            filter_chain = "[0:v]null[v_out]" # Default pass-through
            
            if subtitle_path and os.path.exists(subtitle_path):
                # Escape path untuk filter FFmpeg
                # Windows path separator (\) harus di-escape menjadi (\\) atau (\\\\) dalam filter complex
                # Cara paling aman adalah menggunakan forward slash (/) dan escape titik dua (:)
                
                def escape_ffmpeg_path(path_str: str) -> str:
                    p = Path(path_str).resolve().as_posix()
                    return p.replace(':', '\\:')

                esc_sub = escape_ffmpeg_path(subtitle_path)
                
                fonts_opt = ""
                if fonts_dir and os.path.exists(fonts_dir):
                    esc_fonts = escape_ffmpeg_path(fonts_dir)
                    fonts_opt = f":fontsdir='{esc_fonts}'"

                filter_chain = f"[0:v]ass='{esc_sub}'{fonts_opt}[v_out]"

            cmd = [
                self.bin_path, '-nostats', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-filter_complex', filter_chain,
                '-map', '[v_out]', '-map', '1:a:0',
                '-shortest'
            ]
            
            cmd.extend(self._get_clip_args())
            cmd.append(output_path)
            return cmd

        return self._run_with_fallback(build_cmd, f"Render Final: {Path(output_path).name}")

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
        
        return self._run_command(cmd, "Convert Audio to WAV")
