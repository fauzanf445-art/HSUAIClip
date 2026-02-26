import logging
from pathlib import Path
from typing import Dict, Any, List

from tqdm import tqdm

from pipeline import ProcessingStep, ProcessingContext
from modules.motion_tracker import FaceTrackerProcessor

class MotionTrackingStep(ProcessingStep):
    def execute(self, context: ProcessingContext):
        if not context.created_clips:
            logging.warning("Tidak ada klip input untuk tracking.")
            return

        work_dir = context.work_dir
        if not work_dir:
            raise ValueError("Working directory is not set. InitializationStep may have failed.")

        processor = FaceTrackerProcessor(model_path=str(self.core.paths.FACE_LANDMARKER_FILE))
        analysis_results: List[Dict[str, Any]] = []
        tracked_dir = work_dir / self.core.config.DIR_TRACKEDCLIPS
        tracked_dir.mkdir(parents=True, exist_ok=True)
        
        for clip_path in tqdm(context.created_clips, desc="👁️  Motion Tracking"):
            output_tracked_path = tracked_dir / f"tracked_{clip_path.stem}.mp4"
            with tqdm(total=100, desc=f"   -> Processing {clip_path.name}", leave=False, unit='%') as pbar:
                def progress_update(current: int, total: int):
                    percent = (current / total) * 100 if total > 0 else 0
                    pbar.n = int(percent)
                    pbar.refresh()
                result = processor.process_and_crop_video(
                    str(clip_path), str(output_tracked_path),
                    window_size=self.core.config.WINDOW_SIZE,
                    prediction_frames=self.core.config.PREDICTION_FRAMES,
                    progress_callback=progress_update,
                )
            if result:
                analysis_results.append({
                    "original_clip": clip_path,
                    "tracked_video": Path(result["tracked_video"]),
                    "width": result["width"],
                    "height": result["height"]
                })
            else:
                logging.error(f"   ❌ Gagal menganalisis tracking untuk {clip_path.name}")
        context.tracking_results = analysis_results