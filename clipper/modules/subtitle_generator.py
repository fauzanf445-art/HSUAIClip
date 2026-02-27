import os
import logging
import torch

from typing import  Optional, Any
from faster_whisper import WhisperModel

class SubtitleGenerator:
    """
    Menghasilkan subtitle (.ass) menggunakan Faster-Whisper dengan pemilihan perangkat cerdas.
    """
    def __init__(self, download_root: Optional[str] = None, config: Optional[Any] = None):
        # Atribut ini akan diisi oleh _initialize_model_config
        self.device: str = "cpu"
        self.compute_type: str = "int8"
        self.model_size: str = "small"
        self.config = config
        
        self._initialize_model_config()
        
        logging.info(f"🚀 Initializing WhisperModel ({self.model_size}) on device: {self.device} ({self.compute_type})")
        
        try:
            self.model = WhisperModel(
                self.model_size, 
                device=self.device, 
                compute_type=self.compute_type, 
                download_root=download_root
            )
        except Exception as e:
            logging.error(f"Failed to initialize WhisperModel: {e}")
            raise

    def _initialize_model_config(self) -> None:
        """
        Mendeteksi kemampuan hardware untuk model AI (Torch/Whisper) dan memilih model yang sesuai.
        """
        try:
            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(0)
                vram_gb = props.total_memory / (1024**3)
                gpu_name = props.name
                logging.info(f"🚀 AI Hardware: NVIDIA GPU ({gpu_name}) | VRAM: {vram_gb:.2f}GB")

                # Gunakan konfigurasi terpusat jika tersedia
                if self.config and hasattr(self.config, 'WHISPER_MODELS'):
                    models = self.config.WHISPER_MODELS
                    if vram_gb >= models['high_end']['vram_min']:
                        self.model_size = models['high_end']['name']
                        logging.info(f"   -> Tier: High-End. Memilih model Whisper: {self.model_size}")
                        self.device, self.compute_type = "cuda", "float16"
                    elif vram_gb >= models['mid_range']['vram_min']:
                        self.model_size = models['mid_range']['name']
                        logging.info(f"   -> Tier: Mid-Range. Memilih model Whisper: {self.model_size}")
                        self.device, self.compute_type = "cuda", "float16"
                    else:
                        self.model_size = models['low_end']['name']
                        logging.warning(f"   -> Tier: Low-End GPU. VRAM < {models['mid_range']['vram_min']}GB. Fallback ke model: {self.model_size} di CPU.")
                        self.device, self.compute_type = "cpu", "int8"
                else:
                    # Fallback jika config tidak ada
                    if vram_gb >= 10: self.model_size = "large-v3"
                    elif vram_gb >= 4: self.model_size = "medium"
                    else: self.model_size = "small"
                    logging.warning("   -> Konfigurasi model tidak ditemukan, menggunakan fallback VRAM.")
                    self.device, self.compute_type = ("cuda", "float16") if self.model_size != "small" else ("cpu", "int8")

            else:
                logging.warning("⚠️ GPU tidak terdeteksi untuk AI. Menggunakan CPU.")
                self.model_size = self.config.WHISPER_MODELS['low_end']['name'] if self.config and hasattr(self.config, 'WHISPER_MODELS') else "small"
                logging.info(f"   -> Tier: CPU Only. Memilih model Whisper: {self.model_size}")
                self.device, self.compute_type = "cpu", "int8"
        except (ImportError, Exception):
            logging.warning("⚠️ Gagal mendeteksi GPU (Torch error?). Default ke CPU.")
            self.model_size = self.config.WHISPER_MODELS['low_end']['name'] if self.config and hasattr(self.config, 'WHISPER_MODELS') else "small"
            logging.info(f"   -> Tier: CPU Only (Detection Error). Memilih model Whisper: {self.model_size}")
            self.device, self.compute_type = "cpu", "int8"

    def format_timestamp(self, seconds: float) -> str:
        """
        Converts seconds to ASS timestamp format (H:MM:SS.cc).
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}:{minutes:02d}:{secs:05.2f}"

    def generate_ass_header(self, play_res_x: int = 1920, play_res_y: int = 1080) -> str:
        """
        Returns the standard V4+ Styles header for the .ass file.
        """
        # --- UKURAN FONT DINAMIS ---
        # Ukuran font dasar dan margin untuk video dengan tinggi 1080p
        base_font_size = 60
        base_margin_v = 60
        reference_height = 1080

        # Skalakan ukuran font dan margin berdasarkan tinggi video yang sebenarnya
        scale_factor = play_res_y / reference_height
        font_size = int(base_font_size * scale_factor)
        margin_v = int(base_margin_v * scale_factor)

        logging.info(f"   -> Menyesuaikan subtitle untuk resolusi {play_res_y}p. Ukuran Font: {font_size}, Margin-V: {margin_v}")

        return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Poppins Bold,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,3,2,0,8,10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def generate_subtitles(self, input_path: str, output_path: str, chunk_size: int, play_res_x: int = 1920, play_res_y: int = 1080) -> None:
        """
        Mentranskripsi media input (audio/video) dan menghasilkan file subtitle .ass.
        """
        if not os.path.exists(input_path):
            logging.error(f"Input file not found: {input_path}")
            return

        logging.info(f"🎙️ Starting transcription for: {input_path}")
        
        try:
            # Run transcription with word timestamps enabled
            # faster-whisper handles video files directly
            segments, info = self.model.transcribe(input_path, word_timestamps=True)
            
            # Collect all words from segments
            all_words = []
            for segment in segments:
                if segment.words:
                    all_words.extend(segment.words)
            
            if not all_words:
                logging.warning("No speech detected in the media file.")
                return

            logging.info(f"📝 Transcription complete. Found {len(all_words)} words. Generating subtitles...")

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(self.generate_ass_header(play_res_x, play_res_y))

                # Implementasi Chunking dengan animasi Pop & Bounce per kata
                word_chunks = [all_words[i:i + chunk_size] for i in range(0, len(all_words), chunk_size)]

                for chunk in word_chunks:
                    if not chunk:
                        continue

                    # Durasi baris adalah dari awal kata pertama hingga akhir kata terakhir
                    line_start_time = chunk[0].start
                    line_end_time = chunk[-1].end
                    
                    start_str = self.format_timestamp(line_start_time)
                    end_str = self.format_timestamp(line_end_time)

                    # Bangun teks untuk seluruh baris, dengan animasi per kata
                    dialogue_parts = ["{\\blur3}"] # Terapkan blur ke seluruh baris

                    for word in chunk:
                        text = word.word.strip()

                        # Pengaturan waktu relatif terhadap awal baris dialog
                        rel_start_ms = int((word.start - line_start_time) * 1000)
                        
                        # Tentukan durasi fase animasi (dalam ms)
                        jump_duration = 120
                        pop_duration = 150
                        settle_duration = 100

                        # Hitung waktu akhir untuk setiap fase
                        jump_end_ms = rel_start_ms + jump_duration
                        pop_end_ms = jump_end_ms + pop_duration
                        settle_end_ms = pop_end_ms + settle_duration

                        # Buat tag animasi berurutan: Lompat -> Pop -> Kembali Normal
                        anim_tags = (f"\\t({rel_start_ms},{jump_end_ms},\\fscy125\\fscx90)"
                                     f"\\t({jump_end_ms},{pop_end_ms},\\fscx115\\fscy115)"
                                     f"\\t({pop_end_ms},{settle_end_ms},\\fscx100\\fscy100)")
                        
                        dialogue_parts.append(f" {{{anim_tags}}}{text}")

                    dialogue_text = "".join(dialogue_parts)
                    # Tulis satu baris event untuk setiap kelompok kata
                    f.write(f"Dialogue: 0,{start_str},{end_str},Karaoke,,0,0,0,,{dialogue_text.strip()}\n")

            logging.info(f"✅ Subtitle disimpan di: {output_path}")

        except Exception as e:
            logging.error(f"Error during transcription/generation: {e}")
            raise
