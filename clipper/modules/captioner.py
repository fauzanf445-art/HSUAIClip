import os
import logging
import torch
import random
from pathlib import Path
from typing import List, Tuple, Optional

from faster_whisper import WhisperModel

class KaraokeGenerator:
    """
    Generates karaoke-style subtitles (.ass) using Faster-Whisper with smart device selection.
    """
    def __init__(self, download_root: Optional[str] = None):
        # Atribut ini akan diisi oleh _initialize_model_config
        self.device: str = "cpu"
        self.compute_type: str = "int8"
        self.model_size: str = "small"
        
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

                if vram_gb >= 10:
                    self.model_size = "large-v3"
                    logging.info(f"   -> Tier: High-End. Memilih model Whisper: {self.model_size}")
                    self.device, self.compute_type = "cuda", "float16"
                elif vram_gb >= 4:
                    self.model_size = "medium"
                    logging.info(f"   -> Tier: Mid-Range. Memilih model Whisper: {self.model_size}")
                    self.device, self.compute_type = "cuda", "float16"
                else:
                    self.model_size = "small"
                    logging.warning(f"   -> Tier: Low-End GPU. VRAM < 4GB. Fallback ke model: {self.model_size} di CPU.")
                    self.device, self.compute_type = "cpu", "int8"
            else:
                logging.warning("⚠️ GPU tidak terdeteksi untuk AI. Menggunakan CPU.")
                self.model_size = "small"
                logging.info(f"   -> Tier: CPU Only. Memilih model Whisper: {self.model_size}")
                self.device, self.compute_type = "cpu", "int8"
        except (ImportError, Exception):
            logging.warning("⚠️ Gagal mendeteksi GPU (Torch error?). Default ke CPU.")
            self.model_size = "small"
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
        return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Poppins,60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,3,2,10,10,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def transcribe_and_generate_karaoke(self, input_path: str, output_path: str, play_res_x: int = 1920, play_res_y: int = 1080):
        """
        Transcribes the input media (audio/video) and generates an .ass subtitle file with karaoke effects.
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

            # Konfigurasi untuk Sliding Window
            chunk_size = 3

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(self.generate_ass_header(play_res_x, play_res_y))

                # Implementasi Sliding Window
                for i in range(len(all_words)):
                    window = all_words[i:i + chunk_size]
                    if not window:
                        continue

                    # Waktu mulai adalah awal kata pertama di jendela
                    start_time = window[0].start
                    
                    # Waktu selesai adalah awal kata BERIKUTNYA (untuk efek hilang-muncul)
                    if i + 1 < len(all_words):
                        end_time = all_words[i+1].start
                    else:
                        # Untuk baris terakhir, berakhir saat kata terakhir selesai
                        end_time = window[-1].end

                    # Pastikan durasi tidak negatif jika ada tumpang tindih kecil
                    if end_time <= start_time:
                        end_time = window[-1].end
                    
                    start_str = self.format_timestamp(start_time)
                    end_str = self.format_timestamp(end_time)

                    dialogue_text = "{\\blur3}"

                    for j, word in enumerate(window):
                        w_start = word.start
                        w_end = word.end
                        text = word.word.strip().replace('.', '').replace(',', '').replace('?', '').replace('!', '')

                        if j > 0:
                            dialogue_text += " "
                        
                        rel_start = int((w_start - start_time) * 1000)
                        
                        # Random Font Size (90% - 110%)
                        scale = random.randint(90, 110)
                        
                        # Animasi: Base Scale -> Scale Up 120% saat mulai -> Scale Down ke Random saat selesai
                        anim_tags = f"\\fscx{scale}\\fscy{scale}\\t({rel_start},{rel_start+100},\\fscx120\\fscy120)\\t({rel_start+100},{rel_start+200},\\fscx{scale}\\fscy{scale})"
                        
                        dialogue_text += f"{{{anim_tags}}}{text}"

                    # Write the event line
                    f.write(f"Dialogue: 0,{start_str},{end_str},Karaoke,,0,0,0,,{dialogue_text}\n")

            logging.info(f"✅ Karaoke subtitles saved to: {output_path}")

        except Exception as e:
            logging.error(f"Error during transcription/generation: {e}")
            raise
