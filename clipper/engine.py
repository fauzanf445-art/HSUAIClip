import logging
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
import concurrent.futures

from dotenv import load_dotenv, set_key
from .modules.downloader import Downloader
from .modules.summarizer import Summarizer
from .modules.processor import FaceTrackerProcessor
from .modules.captioner import KaraokeGenerator
from .interface import ConsoleUI
from .core import ProjectCore
from .utils import UtilsProgress
from .utils.models import Clip, VideoSummary

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

class CreateClipEngine:
    """
    Engine khusus untuk menangani pembuatan klip (Download & Re-encode).
    """
    def __init__(self, url: str, work_dir: Path, core: ProjectCore, video_info: Optional[Dict[str, Any]] = None):
        self.url = url
        self.work_dir = work_dir
        self.core = core
        self.paths = core.paths
        self.video_info = video_info
        self.cookies_path = self.paths.COOKIE_FILE

    def _process_single_clip(self, task: Dict[str, Any], ffmpeg_args: List[str], silent: bool = False) -> Optional[Path]:
        """
        Helper function untuk memproses satu klip dalam thread terpisah.
        """
        clip: Clip = task['clip_info']
        title = clip.title
        display_index = task.get('display_index', 0)
        total_clips = task.get('total_clips', 0)

        # Buat instance Downloader lokal untuk thread safety (terutama saat retry/reset info)
        local_downloader = Downloader(
            self.url, 
            cookies_path=self.cookies_path,
            # Copy video_info agar tidak request ulang jika sudah ada, 
            # tapi aman dimodifikasi lokal (reset) jika retry
            video_info=self.video_info.copy() if self.video_info else None
        )

        logging.debug(f"[{display_index}/{total_clips}] 🎬 Memproses: {title}")

        max_retries = 2
        for attempt in range(max_retries):
            try:
                stream_urls = local_downloader.get_stream_urls(title)
                runner = UtilsProgress()
                created_file = runner.create_clip_from_stream(stream_urls, task, ffmpeg_args, silent=silent)
                
                if created_file:
                    return created_file
                
                break 
            except subprocess.CalledProcessError as e:
                if "403 Forbidden" in (e.stderr or "") and attempt < max_retries - 1:
                    logging.warning(f"⚠️ URL stream kadaluarsa '{title}'. Retry...")
                    local_downloader.video_info = None
                    continue
                else:
                    logging.error(f"❌ Gagal memproses klip '{title}': {e}")
                    break
            except Exception as e:
                logging.error(f"❌ Gagal memproses klip '{title}': {e}")
                break
        return None

    def run_clipsengine(self, clips_data: List[Clip]) -> List[Path]:
        
        logging.debug("Tahap 3: Memproses klip...")
        all_clips = clips_data
        
        if not all_clips:
            logging.warning("Tidak ada data klip dalam summary.")
            return []
        
        # Siapkan folder output untuk klip
        clips_dir = self.work_dir / "rawclips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        # --- CACHING LOGIC ---
        tasks_to_run: List[Dict[str, Any]] = []
        existing_files: List[Path] = []
        
        logging.info(f"Memproses {len(all_clips)} klip...")

        for index, clip in enumerate(all_clips):
            title = clip.title
            safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '_')]).strip()
            
            # Truncate nama file klip agar tidak error FFmpeg (MAX_PATH)
            if len(safe_title) > 30: safe_title = safe_title[:30]
            
            base_filename = f"clip {index+1}-{safe_title}"
            
            # Cek berbagai format yang mungkin sudah ada (MKV, MP4, WEBM)
            found_existing = None
            for ext in ['.mkv', '.mp4', '.webm']:
                raw_path = clips_dir / f"{base_filename}{ext}"
                if raw_path.exists() and raw_path.stat().st_size > 1024:
                    found_existing = raw_path
                    break

            if found_existing:
                logging.warning(f"♻️ Cache ditemukan: Klip '{found_existing.name}' sudah ada.")
                logging.warning(f"[{index+1}/{len(all_clips)}] ♻️  Melewati (Cache): {title}")
                existing_files.append(found_existing)
            else:
                # Default format output (bisa diganti ke .mp4 jika diinginkan)
                expected_filepath = clips_dir / f"{base_filename}.mkv"
                
                tasks_to_run.append({
                    'clip_info': clip, 'output_path': expected_filepath,
                    'display_index': index + 1, 'total_clips': len(all_clips)
                })

        if not tasks_to_run:
            logging.warning(f"✅ Semua klip sudah ada di cache. Tidak ada yang perlu dibuat.")
            return sorted(existing_files, key=lambda p: p.name)

        # --- DOWNLOAD LOGIC ---
        
        ffmpeg_args = UtilsProgress.get_clip_creation_args()
        newly_created_files: List[Path] = []

        # --- Refactor: Global Progress Bar ---
        total_to_create = len(tasks_to_run)
        completed_count = 0
        progress_runner = UtilsProgress()
        progress_runner._print_progress(0, "Memotong Klip", f"0/{total_to_create} Klip")

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future_to_task = {
                executor.submit(self._process_single_clip, task, ffmpeg_args, silent=True): task
                for task in tasks_to_run
            }
            
            for future in concurrent.futures.as_completed(future_to_task):
                result = future.result()
                if result:
                    newly_created_files.append(result)
                
                completed_count += 1
                percent = (completed_count / total_to_create) * 100
                progress_runner._print_progress(percent, "Memotong Klip", f"{completed_count}/{total_to_create} Klip")
        
        sys.stdout.write("\n")
        mkv_files = sorted(existing_files + newly_created_files, key=lambda p: p.name)
        logging.info(f"✅ {len(newly_created_files)} klip baru berhasil dibuat. Total klip: {len(mkv_files)}.")
        return mkv_files

class MotionTrackingEngine:
    """
    Engine untuk menerapkan efek Motion Tracking/Face Prediction pada klip.
    """
    def __init__(self, work_dir: Path, core: ProjectCore):
        self.work_dir = work_dir
        self.core = core
        self.processor = FaceTrackerProcessor(str(self.core.paths.FACE_LANDMARKER_FILE))

    def run_tracking_engine(self, input_clips: List[Path]) -> List[Dict[str, Any]]:
        if not input_clips:
            logging.warning("Tidak ada klip input untuk tracking.")
            return []

        logging.info("Tahap 4: Menganalisis Motion Tracking (Python/OpenCV)...")
        
        analysis_results: List[Dict[str, Any]] = []
        
        for idx, clip_path in enumerate(input_clips):
            logging.info(f"[{idx+1}/{len(input_clips)}] 👁️  Tracking wajah pada: {clip_path.name}")
            
            # Panggil metode analisis yang baru
            analysis_data = self.processor.analyze_video_for_cropping(str(clip_path))

            if analysis_data:
                analysis_results.append({
                    "clip_path": clip_path,
                    "analysis_data": analysis_data
                })
            else:
                logging.error(f"   ❌ Gagal menganalisis tracking untuk {clip_path.name}")

        return analysis_results

class CaptioningEngine:
    """
    Engine untuk membuat subtitle karaoke dan membakarnya ke video.
    """
    def __init__(self, work_dir: Path, core: ProjectCore):
        self.work_dir = work_dir
        self.core = core
        self.generator = KaraokeGenerator(
            download_root=str(self.core.paths.WHISPERMODELS_DIR)
        )

    def run_captioning(self, tracking_results: List[Dict[str, Any]]) -> Dict[Path, Path]:
        if not tracking_results:
            logging.warning("Tidak ada klip input untuk captioning.")
            return {}

        logging.info("Tahap 5: Generating Karaoke Subtitles...")
        
        subtitle_map: Dict[Path, Path] = {}
        
        for result in tracking_results:
            clip_path = result["clip_path"]
            analysis_data = result["analysis_data"]
            
            # Generate file .ass
            ass_path = clip_path.with_suffix('.ass')
            
            if ass_path.exists():
                logging.warning(f"♻️ Cache subtitle ditemukan: {ass_path.name}")
                subtitle_map[clip_path] = ass_path
                continue

            try:
                # Extract target resolution from analysis data to ensure subtitles are scaled correctly
                target_w = analysis_data.get("target_w", 1080)
                target_h = analysis_data.get("target_h", 1920)

                # Whisper bisa menerima input video langsung untuk diambil audionya
                self.generator.transcribe_and_generate_karaoke(
                    str(clip_path), str(ass_path),
                    play_res_x=target_w, play_res_y=target_h
                )
                if ass_path.exists():
                    subtitle_map[clip_path] = ass_path
            except Exception as e:
                logging.error(f"Gagal membuat subtitle untuk {clip_path.name}: {e}")

        return subtitle_map

class RenderEngine:
    """
    Engine untuk merender video final dengan semua efek (crop, subtitle).
    """
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.output_dir = work_dir / "final_clips"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run_rendering(self, tracking_results: List[Dict[str, Any]], subtitle_map: Dict[Path, Path]) -> List[Path]:
        logging.info("Tahap 6: Merender Video Final (FFmpeg)...")
        final_files: List[Path] = []

        for result in tracking_results:
            clip_path = result["clip_path"]
            analysis_data = result["analysis_data"]
            subtitle_path = subtitle_map.get(clip_path)

            output_video_path = self.output_dir / f"final_{clip_path.stem}.mp4"

            if output_video_path.exists():
                logging.warning(f"♻️ Cache video final ditemukan: {output_video_path.name}")
                final_files.append(output_video_path)
                continue

            runner = UtilsProgress()
            if runner.render_with_effects(
                video_path=clip_path,
                subtitle_path=subtitle_path,
                analysis_data=analysis_data,
                output_path=output_video_path
            ):
                final_files.append(output_video_path)
            else:
                logging.error(f"❌ Gagal merender video final untuk {clip_path.name}")

        return final_files

class SummarizeEngine:
    def __init__(self, url: str, core: ProjectCore):
        self.url = url
        self.core = core
        self.paths = self.core.paths
        self.api_key = None # Lazy load: API Key hanya diminta jika mode Auto dijalankan
        self.prompt_text: str = ""

    def _resolve_api_key(self) -> str:
        """Mengelola logika validasi API Key dengan bantuan ConsoleUI."""
        # 1. Cek file .env
        if not self.paths.ENV_FILE.exists():
            self.paths.ENV_FILE.touch()

        load_dotenv(dotenv_path=self.paths.ENV_FILE)
        api_key = os.getenv("GEMINI_API_KEY")

        # 2. Validasi Key yang ada
        if api_key and Summarizer.check_key_validity(api_key):
            logging.info(f"✅ API Key terverifikasi valid.")
            return api_key

        # 3. Jika tidak ada/invalid, minta input user
        ConsoleUI.print_api_key_help()
        
        while True:
            user_input_key = ConsoleUI.get_api_key_input()
            if not user_input_key:
                continue
            
            ConsoleUI.show_checking_key()
            if Summarizer.check_key_validity(user_input_key):
                set_key(str(self.paths.ENV_FILE), "GEMINI_API_KEY", user_input_key)
                ConsoleUI.show_key_status(is_valid=True)
                return user_input_key
            else:
                ConsoleUI.show_key_status(is_valid=False)

    def _prepare_and_validate(self):
        """Tahap 0: Muat prompt (API Key diasumsikan sudah valid dari main)."""
        try:
            logging.debug(" Memuat prompt...")
            if not self.paths.PROMPT_FILE.exists():
                raise FileNotFoundError(f"❌ File prompt tidak ditemukan di: {self.paths.PROMPT_FILE}")
            self.prompt_text = self.paths.PROMPT_FILE.read_text(encoding='utf-8')
        except Exception as e:
            raise RuntimeError(f"Gagal pada tahap persiapan: {e}") from e

    def _download_media(self, work_dir: Path, video_info: Optional[Dict[str, Any]] = None) -> tuple[Path, str]:
        """Tahap 1: Unduh audio dan buat transkrip."""
        
        try:
            logging.debug("Tahap 1: Memulai proses download...")
            yt_dlp_download = Downloader(
                self.url,
                cookies_path=self.paths.COOKIE_FILE,
                video_info=video_info,
            )
            
            # 1. Cek Cache Audio Final (WAV)
            # Gunakan nama file yang konsisten dengan Downloader (get_folder_name + .mp3)
            safe_name = yt_dlp_download.get_folder_name()
            final_audio_path = work_dir / f"{safe_name}.wav"

            if not (final_audio_path.exists() and final_audio_path.stat().st_size > 10240):
                # Download RAW Audio (Format asli dari YouTube)
                raw_audio_path = yt_dlp_download.download_audio(work_dir)
                
                if not raw_audio_path or not raw_audio_path.exists():
                    raise RuntimeError("Gagal mengunduh audio raw.")
                
                # Konversi ke WAV dengan Progress Bar
                logging.info("🔄 Mengonversi audio ke WAV...")
                runner = UtilsProgress()
                converted_path = runner.convert_audio_to_wav(raw_audio_path, final_audio_path)
                
                if not converted_path:
                     raise RuntimeError("Gagal mengonversi audio ke WAV.")
                
                # Bersihkan file raw
                try:
                    raw_audio_path.unlink()
                except Exception:
                    pass

                final_audio_path = converted_path

            # 3. Download Transkrip (Dapatkan string, lalu engine yang simpan)
            transcript_text = yt_dlp_download.download_transcript() or ""
            try:
                if transcript_text:
                    transcript_path = work_dir / "transcript.txt"
                    transcript_path.write_text(transcript_text, encoding='utf-8')
                    logging.info(f"Transkrip disimpan di: {transcript_path}")
                else:
                    logging.info("Tidak ada transkrip yang tersedia atau gagal diunduh.")
            except Exception as e:
                logging.error(f"Gagal menyimpan transkrip: {e}")
                # It's important to continue even if saving the transcript fails
                pass
            logging.info("✅ Tahap 1: Download media selesai.")
            return final_audio_path, transcript_text
        except Exception as e:
            raise RuntimeError(f"Gagal pada tahap download media: {e}") from e

    def _analyze_with_ai(self, audio_path: Path, transcript: str, work_dir: Path):
        """Tahap 2: Kirim data ke AI untuk dianalisis."""
        try:
            logging.info("Tahap 2: Memulai analisis AI...")
            
            if not self.api_key:
                raise ValueError("API Key belum dikonfigurasi.")

            summarizer = Summarizer(api_key=self.api_key)
            result_data = summarizer.generate_summary(
                prompt_template=self.prompt_text,
                transcript_text=transcript,
                audio_file_path=audio_path
            )
            
            # Simpan hasil ke JSON
            json_output_path = work_dir / "summary.json"
            with open(json_output_path, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, indent=2, ensure_ascii=False)
            logging.info(f"💾 File JSON disimpan di: {json_output_path}")
            
        except Exception as e:
            raise RuntimeError(f"Gagal pada tahap analisis AI: {e}") from e

    def run_summarization(self, work_dir: Path, video_info: Optional[Dict[str, Any]]) -> None:
        """
        Menjalankan alur kerja lengkap dengan penanganan error per tahap.
        """
        ConsoleUI.show_progress("STEP 1 : Analyze")
        
        # Jalankan persiapan awal (Prompt)
        self._prepare_and_validate()
        
        # Folder kerja sudah ditentukan di run_project
        if not work_dir.exists():
            work_dir.mkdir(parents=True, exist_ok=True)
            
        logging.info(f"📂 Working Directory: {work_dir}")

        # --- VALIDASI TAHAP AWAL (CACHING) ---
        # Cek apakah summary.json sudah ada dan valid
        summary_file = work_dir / "summary.json"
        need_analysis = True

        if summary_file.exists():
            try:
                content = summary_file.read_text(encoding='utf-8')
                if content and json.loads(content):
                    logging.warning(f"♻️ Cache ditemukan: summary.json sudah ada dan valid. Melewati analisis AI.")
                    need_analysis = False
            except json.JSONDecodeError:
                logging.warning(f"⚠️ File summary.json ditemukan tapi korup. Memulai ulang proses.")
        
        # --- PROSES UTAMA ---
        if need_analysis:
            # Lazy Load API Key: Hanya minta jika benar-benar butuh analisis
            if not self.api_key:
                self.api_key = self._resolve_api_key()

            audio_path, transcript_text = self._download_media(work_dir, video_info)
            self._analyze_with_ai(audio_path, transcript_text, work_dir)
        
        return

def run_project(url: str) -> tuple[Path, List[Path]]:
    # 1. Setup Engine: Verifikasi sistem dan aset
    setup = SetupEngine()
    setup.run_system_check()
    core = setup.core # The single source of truth
    
    # 2. Input Manual (Opsional)
    manual_clips = ConsoleUI.get_manual_timestamps()

    # 3. Common Setup: Resolve Folder & Info (Diperlukan untuk Manual maupun Auto)
    Downloader.check_and_setup_cookies(core.paths.COOKIE_FILE)
    
    downloader = Downloader(url, cookies_path=core.paths.COOKIE_FILE)
    folder_name = downloader.get_folder_name()
    video_info = downloader.get_info()
    
    work_dir = core.paths.TEMP_DIR / folder_name
    if not work_dir.exists():
        work_dir.mkdir(parents=True, exist_ok=True)

    clips_data: List[Clip] = []

    if manual_clips:
        logging.info(f"👉 Mode Manual: Menggunakan {len(manual_clips)} klip dari input pengguna.")
        clips_data = manual_clips

    else:
        # Mode Auto: Jalankan SummarizeEngine
        summarizer = SummarizeEngine(url, core=core)
        summarizer.run_summarization(work_dir, video_info)
        
        # Muat hasil dari summary.json yang baru dibuat/cache
        summary_path = work_dir / "summary.json"
        if summary_path.exists():
            data = json.loads(summary_path.read_text(encoding='utf-8'))
            summary = VideoSummary.from_dict(data)
            clips_data = summary.clips

    # 4. Create Clip Engine: Potong video (Menerima data klip secara langsung)
    clips_engine = CreateClipEngine(url, work_dir=work_dir, core=core, video_info=video_info)
    createclips = clips_engine.run_clipsengine(clips_data)

    # 5. Motion Tracking Engine: Proses efek visual
    tracking_engine = MotionTrackingEngine(work_dir=work_dir, core=core)
    tracking_results = tracking_engine.run_tracking_engine(createclips)
    
    # 6. Captioning Engine: Generate Subtitles
    captioning_engine = CaptioningEngine(work_dir=work_dir, core=core)
    subtitle_map = captioning_engine.run_captioning(tracking_results)

    # 7. Render Engine: Gabungkan semua aset menjadi video final
    render_engine = RenderEngine(work_dir=work_dir)
    final_clips = render_engine.run_rendering(tracking_results, subtitle_map)

    return work_dir, final_clips