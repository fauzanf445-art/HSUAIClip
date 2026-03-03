import logging
import torch
from typing import List, Optional, Dict
from faster_whisper import WhisperModel, Segment

from src.domain.interfaces import ITranscriber, TranscriptionSegment, TranscriptionWord

class WhisperAdapter(ITranscriber):
    """
    Implementasi ITranscriber menggunakan faster-whisper.
    Bertanggung jawab murni untuk transkripsi audio ke data terstruktur.
    """

    def __init__(self, model_size: str, device: str, compute_type: str, download_root: Optional[str] = None):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        
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

    @staticmethod
    def detect_hardware() -> Dict[str, str]:
        """
        Mendeteksi hardware dan mengembalikan konfigurasi optimal untuk Whisper.
        Returns:
            Dict[str, str]: Berisi 'model_size', 'device', dan 'compute_type'.
        """
        try:
            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(0)
                vram_gb = props.total_memory / (1024**3)
                gpu_name = props.name
                logging.info(f"🚀 AI Hardware: NVIDIA GPU ({gpu_name}) | VRAM: {vram_gb:.2f}GB")

                if vram_gb >= 10: model_size = "large-v3"
                elif vram_gb >= 4: model_size = "medium"
                else:
                    logging.warning(f"   -> VRAM < 4GB. Fallback ke model 'small' di CPU.")
                    return {'model_size': 'small', 'device': 'cpu', 'compute_type': 'int8'}
                
                logging.info(f"   -> Tier: GPU. Memilih model Whisper: {model_size}")
                return {'model_size': model_size, 'device': 'cuda', 'compute_type': 'float16'}
            else:
                logging.warning("⚠️ GPU tidak terdeteksi untuk AI. Menggunakan CPU.")
                return {'model_size': 'small', 'device': 'cpu', 'compute_type': 'int8'}
        except Exception as e:
            logging.warning(f"⚠️ Gagal mendeteksi GPU (Torch error: {e}). Default ke CPU.")
            return {'model_size': 'small', 'device': 'cpu', 'compute_type': 'int8'}

    def _segment_to_dict(self, segment: Segment) -> TranscriptionSegment:
        """Mengubah objek Segment dari faster-whisper menjadi dictionary."""
        words_list: List[TranscriptionWord] = []
        if segment.words:
            for w in segment.words:
                words_list.append({
                    'word': w.word,
                    'start': w.start,
                    'end': w.end,
                    'probability': w.probability
                })
        return {
            "start": segment.start, "end": segment.end, "text": segment.text, "words": words_list
        }

    def transcribe(self, audio_path: str) -> List[TranscriptionSegment]:
        """
        Mentranskripsi file audio dan mengembalikan hasilnya sebagai list of dictionaries.
        """
        logging.info(f"🎙️ Memulai transkripsi untuk: {audio_path}")
        try:
            segments, info = self.model.transcribe(audio_path, word_timestamps=True)
            
            results = [self._segment_to_dict(seg) for seg in segments]
            
            logging.info(f"📝 Transkripsi selesai. Bahasa terdeteksi: {info.language} (Prob: {info.language_probability:.2f})")
            return results
        except Exception as e:
            logging.error(f"Error during transcription: {e}")
            raise