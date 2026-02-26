import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
import concurrent.futures

from tqdm import tqdm

from pipeline import ProcessingStep, ProcessingContext
from modules.downloader import Downloader
from utils import FFmpegWrapper
from utils.models import Clip

class ClipCreationStep(ProcessingStep):
    def _process_single_clip(self, task: Dict[str, Any], ffmpeg_args: List[str], context: ProcessingContext, silent: bool = False) -> Optional[Path]:
        clip: Clip = task['clip_info']
        title = clip.title
        local_downloader = Downloader(
            context.url, 
            cookies_path=context.core.paths.COOKIE_FILE,
            video_info=context.video_info.copy() if context.video_info else None,
            deno_path=context.deno_path
        )
        max_retries = 2
        for attempt in range(max_retries):
            try:
                stream_urls = local_downloader.get_stream_urls(title)
                runner = FFmpegWrapper()
                created_file = runner.create_clip_from_stream(stream_urls, task, ffmpeg_args, silent=silent)
                if created_file: return created_file
                break
            except subprocess.CalledProcessError as e:
                if "403 Forbidden" in (e.stderr or "") and attempt < max_retries - 1:
                    logging.warning(f"⚠️ URL stream kadaluarsa '{title}'. Retry...")
                    local_downloader.video_info = None
                else:
                    logging.error(f"❌ Gagal memproses klip '{title}': {e}")
                    break
            except Exception as e:
                logging.error(f"❌ Gagal memproses klip '{title}': {e}")
                break
        return None

    def execute(self, context: ProcessingContext):
        if not context.clips_data:
            logging.warning("Tidak ada data klip untuk diproses. Melewati tahap pembuatan klip.")
            return
        
        work_dir = context.work_dir
        if not work_dir:
            raise ValueError("Working directory is not set. InitializationStep may have failed.")

        clips_dir = work_dir / self.core.config.DIR_RAWCLIPS
        clips_dir.mkdir(parents=True, exist_ok=True)
        tasks_to_run: List[Dict[str, Any]] = []
        existing_files: List[Path] = []
        
        for index, clip in enumerate(context.clips_data):
            title = clip.title
            safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '_')]).strip()
            if len(safe_title) > 30: safe_title = safe_title[:30]
            base_filename = f"clip {index+1}-{safe_title}"
            found_existing = None
            for ext in ['.mkv', '.mp4', '.webm']:
                raw_path = clips_dir / f"{base_filename}{ext}"
                if raw_path.exists() and raw_path.stat().st_size > 1024:
                    found_existing = raw_path
                    break
            if found_existing:
                existing_files.append(found_existing)
            else:
                expected_filepath = clips_dir / f"{base_filename}.mkv"
                tasks_to_run.append({
                    'clip_info': clip, 'output_path': expected_filepath,
                    'display_index': index + 1, 'total_clips': len(context.clips_data)
                })

        if not tasks_to_run:
            logging.warning(f"✅ Semua klip sudah ada di cache. Tidak ada yang perlu dibuat.")
            context.created_clips = sorted(existing_files, key=lambda p: p.name)
            return

        ffmpeg_args = FFmpegWrapper.get_clip_creation_args()
        newly_created_files: List[Path] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_task = {
                executor.submit(self._process_single_clip, task, ffmpeg_args, context, silent=True): task
                for task in tasks_to_run
            }
            for future in tqdm(concurrent.futures.as_completed(future_to_task), total=len(tasks_to_run), desc="Memotong Klip"):
                result = future.result()
                if result: newly_created_files.append(result)
        
        context.created_clips = sorted(existing_files + newly_created_files, key=lambda p: p.name)
        logging.info(f"✅ {len(newly_created_files)} klip baru berhasil dibuat. Total klip: {len(context.created_clips)}.")