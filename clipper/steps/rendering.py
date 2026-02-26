import logging
from pathlib import Path
from typing import List

from ..pipeline import ProcessingStep, ProcessingContext
from ..utils import FFmpegWrapper

class RenderingStep(ProcessingStep):
    def execute(self, context: ProcessingContext):
        if not context.tracking_results:
            logging.warning("Tidak ada hasil tracking untuk dirender.")
            return

        work_dir = context.work_dir
        if not work_dir:
            raise ValueError("Working directory is not set. InitializationStep may have failed.")

        output_dir = work_dir / self.core.config.DIR_FINALCLIPS
        output_dir.mkdir(parents=True, exist_ok=True)
        final_files: List[Path] = []

        for result in context.tracking_results:
            clip_path = result["original_clip"]
            tracked_video = result["tracked_video"]
            subtitle_path = context.subtitle_map.get(clip_path)
            output_video_path = output_dir / f"final_{clip_path.stem}.mp4"
            if output_video_path.exists():
                logging.warning(f"♻️ Cache video final ditemukan: {output_video_path.name}")
                final_files.append(output_video_path)
                continue
            runner = FFmpegWrapper()
            if runner.render_final_clip(
                video_path=tracked_video,
                audio_path=clip_path,
                subtitle_path=subtitle_path,
                output_path=output_video_path,
                fonts_dir=self.core.paths.FONTS_DIR
            ):
                final_files.append(output_video_path)
            else:
                logging.error(f"❌ Gagal merender video final untuk {clip_path.name}")
        context.final_clips = final_files