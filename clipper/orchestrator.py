import logging
import json
import os
import subprocess
from tqdm import tqdm
from pathlib import Path
from typing import Optional, Dict, Any, List
import concurrent.futures

from dotenv import load_dotenv, set_key
from .modules.downloader import Downloader
from .modules.ai_analyzer import AIAnalyzer
from .modules.motion_tracker import FaceTrackerProcessor
from .modules.subtitle_generator import SubtitleGenerator
from .interface import ConsoleUI
from .core import ProjectCore
from .utils import FFmpegWrapper
from .utils.models import Clip, VideoSummary
from .pipeline import ProcessingContext, ProcessingStep, ProcessingPipeline

class SetupEngine:
    """
    Engine untuk setup project (Folder, Aset, API Key) sebelum proses utama berjalan.
    """
    def __init__(self):
        self.core = ProjectCore()
        logging.debug("✅ Inisialisasi sistem logging berhasil. Debug log aktif.")
        logging.info(f"📝 Debug Log: {self.core.paths.LOG_FILE}")

    def run_system_check(self):
        """Menjalankan verifikasi aset sistem (FFmpeg, Model, dll)."""
        logging.info("⚙️ Menjalankan pemeriksaan sistem...")
        self.core.verify_assets()

class InitializationStep(ProcessingStep):
    def execute(self, context: ProcessingContext):
        Downloader.check_and_setup_cookies(context.core.paths.COOKIE_FILE)
        
        deno_path = context.core.find_executable('deno.exe') or context.core.find_executable('deno')
        downloader = Downloader(context.url, cookies_path=context.core.paths.COOKIE_FILE, deno_path=deno_path)
        
        folder_name = downloader.get_folder_name()
        context.video_info = downloader.get_info()
        work_dir = context.core.paths.TEMP_DIR / folder_name
        work_dir.mkdir(parents=True, exist_ok=True)
        context.work_dir = work_dir
        logging.info(f"📂 Working Directory: {work_dir}")

class SummarizationStep(ProcessingStep):
    def __init__(self, core: ProjectCore):
        super().__init__(core)
        self.api_key: Optional[str] = None
        self.prompt_text: str = ""

    def _resolve_api_key(self) -> str:
        if not self.core.paths.ENV_FILE.exists():
            self.core.paths.ENV_FILE.touch()
        load_dotenv(dotenv_path=self.core.paths.ENV_FILE)
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key and AIAnalyzer.check_key_validity(api_key):
            logging.info("✅ API Key terverifikasi valid.")
            return api_key
        ConsoleUI.print_api_key_help()
        while True:
            user_input_key = ConsoleUI.get_api_key_input()
            if not user_input_key: continue
            ConsoleUI.show_checking_key()
            if AIAnalyzer.check_key_validity(user_input_key):
                set_key(str(self.core.paths.ENV_FILE), "GEMINI_API_KEY", user_input_key)
                ConsoleUI.show_key_status(is_valid=True)
                return user_input_key
            else:
                ConsoleUI.show_key_status(is_valid=False)

    def _prepare_and_validate(self):
        if not self.core.paths.PROMPT_FILE.exists():
            raise FileNotFoundError(f"❌ File prompt tidak ditemukan di: {self.core.paths.PROMPT_FILE}")
        self.prompt_text = self.core.paths.PROMPT_FILE.read_text(encoding='utf-8')

    def _prepare_analysis_assets(self, context: ProcessingContext) -> tuple[Path, str]:
        work_dir = context.work_dir
        if not work_dir:
            raise ValueError("Working directory is not set. InitializationStep may have failed.")

        deno_path = self.core.find_executable('deno.exe') or self.core.find_executable('deno')
        yt_dlp_download = Downloader(context.url, cookies_path=self.core.paths.COOKIE_FILE, video_info=context.video_info, deno_path=deno_path)
        safe_name = yt_dlp_download.get_folder_name()
        final_audio_path = work_dir / f"{safe_name}.wav"
        if not (final_audio_path.exists() and final_audio_path.stat().st_size > 10240):
            raw_audio_path = yt_dlp_download.download_audio(work_dir)
            if not raw_audio_path or not raw_audio_path.exists():
                raise RuntimeError("Gagal mengunduh audio raw.")
            runner = FFmpegWrapper()
            converted_path = runner.convert_audio_to_wav(raw_audio_path, final_audio_path)
            if not converted_path:
                raise RuntimeError("Gagal mengonversi audio ke WAV.")
            try:
                raw_audio_path.unlink()
            except Exception as e:
                logging.warning(f"⚠️ Gagal menghapus file audio raw sementara '{raw_audio_path.name}': {e}")
            final_audio_path = converted_path
        transcript_text = yt_dlp_download.download_transcript() or ""
        if transcript_text:
            (work_dir / "transcript.txt").write_text(transcript_text, encoding='utf-8')
        return final_audio_path, transcript_text

    def _analyze_with_ai(self, audio_path: Path, transcript: str, context: ProcessingContext):
        work_dir = context.work_dir
        if not work_dir:
            raise ValueError("Working directory is not set. InitializationStep may have failed.")

        if not self.api_key: raise ValueError("API Key belum dikonfigurasi.")
        analyzer = AIAnalyzer(api_key=self.api_key)
        result_data = analyzer.generate_summary(prompt_template=self.prompt_text, transcript_text=transcript, audio_file_path=audio_path)
        json_output_path = work_dir / "summary.json"
        with open(json_output_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)

    def execute(self, context: ProcessingContext):
        manual_clips = ConsoleUI.get_manual_timestamps()
        if manual_clips:
            logging.info(f"👉 Mode Manual: Menggunakan {len(manual_clips)} klip dari input pengguna.")
            context.clips_data = manual_clips
            return

        # Validasi bahwa work_dir sudah di-set oleh step sebelumnya
        work_dir = context.work_dir
        if not work_dir:
            # Ini seharusnya tidak pernah terjadi jika pipeline berjalan dengan benar
            raise ValueError("Working directory is not set. InitializationStep may have failed.")

        ConsoleUI.show_progress("STEP 1 : Analyze")
        self._prepare_and_validate()
        summary_file = work_dir / "summary.json"
        need_analysis = True
        if summary_file.exists():
            try:
                if content := summary_file.read_text(encoding='utf-8'):
                    if json.loads(content):
                        logging.warning("♻️ Cache ditemukan: summary.json sudah ada dan valid. Melewati analisis AI.")
                        need_analysis = False
            except (json.JSONDecodeError, FileNotFoundError):
                logging.warning("⚠️ File summary.json ditemukan tapi korup. Memulai ulang proses.")
        
        if need_analysis:
            if not self.api_key: self.api_key = self._resolve_api_key()
            audio_path, transcript_text = self._prepare_analysis_assets(context)
            self._analyze_with_ai(audio_path, transcript_text, context)

        if summary_file.exists():
            data = json.loads(summary_file.read_text(encoding='utf-8'))
            summary = VideoSummary.from_dict(data)
            context.clips_data = summary.clips

class ClipCreationStep(ProcessingStep):
    def _process_single_clip(self, task: Dict[str, Any], ffmpeg_args: List[str], context: ProcessingContext, silent: bool = False) -> Optional[Path]:
        clip: Clip = task['clip_info']
        title = clip.title
        deno_path = self.core.find_executable('deno.exe') or self.core.find_executable('deno')
        local_downloader = Downloader(
            context.url, 
            cookies_path=self.core.paths.COOKIE_FILE,
            video_info=context.video_info.copy() if context.video_info else None,
            deno_path=deno_path
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

def run_project(url: str) -> tuple[Path, List[Path]]:
    # 1. Setup Engine: Verifikasi sistem dan aset
    setup = SetupEngine()
    setup.run_system_check()
    core = setup.core

    # 2. Setup Pipeline
    context = ProcessingContext(url=url, core=core)
    pipeline = ProcessingPipeline(context)

    pipeline.add(InitializationStep(core))
    pipeline.add(SummarizationStep(core))
    pipeline.add(ClipCreationStep(core))
    pipeline.add(MotionTrackingStep(core))
    pipeline.add(CaptioningStep(core))
    pipeline.add(RenderingStep(core))

    # 3. Run Pipeline
    try:
        pipeline.run()
    except Exception:
        # The pipeline itself will log the detailed error.
        # We re-raise it to be caught by the main UI loop.
        raise

    # 4. Return results from context
    work_dir = context.work_dir if context.work_dir else Path.cwd()
    return work_dir, context.final_clips