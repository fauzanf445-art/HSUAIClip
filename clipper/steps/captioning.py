import logging
from pathlib import Path
from typing import Dict

from pipeline import ProcessingStep, ProcessingContext
from modules.subtitle_generator import SubtitleGenerator

class CaptioningStep(ProcessingStep):
    def execute(self, context: ProcessingContext):
        if not context.tracking_results:
            logging.warning("Tidak ada klip input untuk captioning.")
            return

        generator = SubtitleGenerator(
            download_root=str(self.core.paths.WHISPERMODELS_DIR),
            config=self.core.config
        )
        subtitle_map: Dict[Path, Path] = {}
        for result in context.tracking_results:
            clip_path = result["original_clip"]
            target_w = result["width"]
            target_h = result["height"]
            ass_path = clip_path.with_suffix('.ass')
            if ass_path.exists():
                logging.warning(f"♻️ Cache subtitle ditemukan: {ass_path.name}")
                subtitle_map[clip_path] = ass_path
                continue
            try:
                generator.generate_subtitles(
                    input_path=str(clip_path), 
                    output_path=str(ass_path),
                    chunk_size=self.core.config.KARAOKE_CHUNK_SIZE,
                    play_res_x=target_w, play_res_y=target_h
                )
                if ass_path.exists(): subtitle_map[clip_path] = ass_path
            except Exception as e:
                logging.error(f"Gagal membuat subtitle untuk {clip_path.name}: {e}")
        context.subtitle_map = subtitle_map