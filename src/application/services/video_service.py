import logging
import concurrent.futures
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
from tqdm import tqdm

from src.domain.interfaces import IVideoProcessor, IFaceTracker
from src.domain.models import Clip

class VideoService:
    """
    Application Service untuk memanipulasi video.
    Mengorkestrasi pemotongan klip (FFmpeg) dan tracking wajah (MediaPipe).
    """

    def __init__(self, processor: IVideoProcessor, tracker: IFaceTracker):
        self.processor = processor
        self.tracker = tracker

    def batch_create_clips(self, clips: List[Clip], video_url: str, audio_url: Optional[str], output_dir: Path, max_workers: int = 2) -> List[Path]:
        """
        Membuat klip video dari stream URL secara paralel.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        created_files: List[Path] = []
        
        def _process_clip(clip: Clip) -> Optional[Path]:
            # Sanitasi nama file
            safe_title = "".join([c for c in clip.title if c.isalnum() or c in (' ', '_', '-')]).strip()
            # Gunakan ID pendek untuk keunikan
            filename = f"{clip.id[:8]}_{safe_title}.mp4"
            output_path = output_dir / filename
            
            # Cek cache
            if output_path.exists() and output_path.stat().st_size > 1024:
                logging.info(f"♻️ Klip cached: {filename}")
                return output_path

            success = self.processor.cut_clip(
                source_url=video_url,
                start=clip.start_time,
                end=clip.end_time,
                output_path=str(output_path),
                audio_url=audio_url
            )
            return output_path if success else None

        logging.info(f"🔄 Memproses {len(clips)} klip dengan {max_workers} threads...")
        
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

    def track_subject(self, input_path: str, output_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]:
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
