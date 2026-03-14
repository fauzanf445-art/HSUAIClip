import logging
import os
import concurrent.futures
from pathlib import Path
from typing import List, Optional, Callable
from tqdm import tqdm

from src.domain.interfaces import IVideoProcessor, IFaceTracker, ITranscriber, ISubtitleWriter, TrackResult
from src.domain.models import Clip
from src.infrastructure.common.utils import sanitize_filename

class EditorService:

    def __init__(self, processor: IVideoProcessor, tracker: IFaceTracker, transcriber: ITranscriber, writer: ISubtitleWriter):
        self.processor = processor
        self.tracker = tracker
        self.transcriber = transcriber
        self.writer = writer

    def batch_create_clips(self, clips: List[Clip], video_url: str, audio_url: Optional[str], output_dir: Path) -> List[Path]:
        """
        Membuat klip video dari stream URL secara paralel.
        Jumlah workers disesuaikan otomatis berdasarkan jenis encoder (GPU/CPU).
        """
        if self.processor.is_gpu_enabled:
            max_workers = 1 
            logging.info("🚀 GPU Encoder terdeteksi: Membatasi proses paralel ke 1 worker untuk stabilitas.")
        else:
            max_workers = os.cpu_count() or 2
            logging.info(f"⚙️ CPU Encoder terdeteksi: Menggunakan {max_workers} worker paralel.")

        output_dir.mkdir(parents=True, exist_ok=True)
        created_files: List[Path] = []
        
        def _process_clip(clip: Clip) -> Optional[Path]:            
            safe_title = sanitize_filename(clip.title)
            filename = f"{clip.id[:8]}_{safe_title}.mp4"            
            output_path = output_dir / filename
            
            # Cek cache
            if output_path.exists() and output_path.stat().st_size > 1024:
                logging.debug(f"♻️ Klip cached: {filename}")
                return output_path

            success = self.processor.cut_clip(
                source_url=video_url,
                start=clip.start_time,
                end=clip.end_time,
                output_path=str(output_path),
                audio_url=audio_url
            )
            return output_path if success else None

        logging.info(f"🔄 Memulai pemotongan {len(clips)} klip...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_clip = {executor.submit(_process_clip, c): c for c in clips}
            
            # Bungkus iterator dengan tqdm untuk menampilkan progress bar dengan ETA
            progress_iterator = concurrent.futures.as_completed(future_to_clip)
            for future in tqdm(progress_iterator, total=len(clips), desc="Cutting Clips", unit="clip"):
                clip = future_to_clip[future]
                try:
                    path = future.result()
                    if path:
                        created_files.append(path)
                        clip.raw_path = str(path) # Update model domain dengan path fisik
                    else:
                        tqdm.write(f"⚠️ Gagal membuat klip: {clip.title}")
                except Exception as e:
                    tqdm.write(f"❌ Error pada klip {clip.title}: {e}")

        return sorted(created_files, key=lambda p: p.name)

    def track_subject(self, input_path: str, output_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> TrackResult:
        """
        Menjalankan motion tracking pada video input.
        """
        return self.tracker.track_and_crop(input_path, output_path, progress_callback)

    def render_final_video(self, video_path: str, audio_path: str, subtitle_path: Optional[str], output_path: str, fonts_dir: Optional[str] = None) -> bool:
        """
        Merender video final dengan subtitle dan audio asli.
        """
        return self.processor.render_final(video_path, audio_path, subtitle_path, output_path, fonts_dir)

    def convert_to_wav(self, input_path: str, output_path: str) -> bool:
        return self.processor.convert_audio_to_wav(input_path, output_path)

    def generate_subtitles_for_clip(
        self,
        clip_audio_path: str,
        output_subtitle_path: str,
        cache_dir: Path,
        chunk_size: int,
        video_width: int,
        video_height: int
    ) -> Optional[Path]:
        """
        Membuat file subtitle .ass untuk satu klip.
        """
        output_path = Path(output_subtitle_path)
        
        if output_path.exists():
            logging.debug(f"♻️ Subtitle .ass cached: {output_path.name}")
            return output_path

        # transcription_cache_path = cache_dir / f"{Path(clip_audio_path).stem}_transcript.json"
        # transcription_data = self._get_transcription_data(clip_audio_path, transcription_cache_path)
        return None