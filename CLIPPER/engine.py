import logging
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from .modules.downloader import Downloader, DownloaderSetup
from .modules.summarizer import GeminiSummarizer, GeminiSetup
from .interface import ConsoleUI
from .core import ProjectCore
from .utils import FFmpegUtils

class SetupEngine:
    """
    Engine untuk setup project (Folder, Aset, API Key) sebelum proses utama berjalan.
    """
    def __init__(self):
        self.core = ProjectCore()
        logging.info("✅ Inisialisasi sistem logging berhasil. Debug log aktif.")
        print(f"📝 Debug Log: {self.core.paths.LOG_FILE}")

    def run_system_check(self):
        """Menjalankan verifikasi aset sistem (FFmpeg, Model, dll)."""
        logging.info("⚙️ Menjalankan pemeriksaan sistem...")
        self.core.verify_assets()

class SummarizeEngine:
    def __init__(self, url: str):
        self.url = url        
        core = ProjectCore()
        core.verify_assets()
        self.paths = core.paths        
        self.api_key = self._resolve_api_key()
        self.prompt_text: str = ""
    

    def _resolve_api_key(self) -> str:
        """Mengelola logika validasi API Key dengan bantuan ConsoleUI."""
        try:
            # Coba validasi diam-diam dulu
            return GeminiSetup.validate_api_key(self.paths.ENV_FILE)
        except ValueError:
            # Jika gagal, minta input user via UI
            ConsoleUI.print_api_key_help()
            
            while True:
                user_input_key = ConsoleUI.get_api_key_input()
                if not user_input_key:
                    continue
                
                ConsoleUI.show_checking_key()
                if GeminiSetup.check_key_validity(user_input_key):
                    GeminiSetup.save_api_key(self.paths.ENV_FILE, user_input_key)
                    ConsoleUI.show_key_status(is_valid=True)
                    return user_input_key
                else:
                    ConsoleUI.show_key_status(is_valid=False)

    def _prepare_and_validate(self):
        """Tahap 0: Muat prompt (API Key diasumsikan sudah valid dari main)."""
        try:
            DownloaderSetup.check_and_setup_cookies(self.paths.COOKIE_FILE)
            logging.info("Tahap 0: Memuat prompt...")
            self.prompt_text = GeminiSetup.load_prompt(self.paths.PROMPT_FILE)
        except Exception as e:
            raise RuntimeError(f"Gagal pada tahap persiapan: {e}") from e

    def _download_media(self, work_dir: Path, video_info: Optional[Dict[str, Any]] = None) -> tuple[Path, str]:
        """Tahap 1: Unduh audio dan buat transkrip."""
        try:
            logging.info("Tahap 1: Memulai proses download...")
            cookie_path = str(self.paths.COOKIE_FILE) if self.paths.COOKIE_FILE.exists() else None
            downloader = Downloader(self.url, output_dir=work_dir, cookies_path=cookie_path, video_info=video_info)
            
            # 1. Cek Cache Audio Final
            final_audio_path = work_dir / "audio_for_ai.mp3"
            if not (final_audio_path.exists() and final_audio_path.stat().st_size > 10240):
                logging.info("File audio final tidak ditemukan atau tidak valid. Memulai proses download & konversi.")
                raw_path = None
                try:
                    # 2. Download Raw
                    raw_path = downloader.download_raw_audio()
                    if not raw_path:
                        raise RuntimeError("Gagal mengunduh audio mentah.")
                    
                    # 3. Convert using the new util function
                    exe_ext = ".exe" if os.name == 'nt' else ""
                    ffmpeg_path = ProjectCore.find_executable(f"ffmpeg{exe_ext}")
                    ffprobe_path = ProjectCore.find_executable(f"ffprobe{exe_ext}")
                    
                    if not ffmpeg_path or not ffprobe_path:
                        raise FileNotFoundError("❌ FFmpeg atau FFprobe tidak ditemukan.")

                    total_sec = FFmpegUtils.get_duration(raw_path, ffprobe_path)
                    ffmpeg_cmd = [str(ffmpeg_path), '-i', str(raw_path), '-y', '-vn', '-b:a', '192k', str(final_audio_path)]
                    
                    FFmpegUtils.run_command(ffmpeg_cmd, total_sec, label="Konversi Audio")
                finally:
                    if raw_path and raw_path.exists():
                        raw_path.unlink()

            transcript_path = downloader.download_transcript()
            transcript_text = transcript_path.read_text(encoding='utf-8') if transcript_path else ""

            return final_audio_path, transcript_text
        except Exception as e:
            raise RuntimeError(f"Gagal pada tahap download media: {e}") from e

    def _analyze_with_ai(self, audio_path: Path, transcript: str, work_dir: Path):
        """Tahap 2: Kirim data ke AI untuk dianalisis."""
        try:
            logging.info("Tahap 2: Memulai analisis AI...")
            summarizer = GeminiSummarizer(api_key=self.api_key, output_path=work_dir)
            summarizer.generate_summary_from_multimodal_inputs(
                prompt_template=self.prompt_text,
                transcript_text=transcript,
                audio_file_path=audio_path
            )
        except Exception as e:
            raise RuntimeError(f"Gagal pada tahap analisis AI: {e}") from e

    def run_summarization(self) -> Path:
        """
        Menjalankan alur kerja lengkap dengan penanganan error per tahap.
        """
        logging.info(f"🚀 Memulai engine untuk URL: {self.url}")
        ConsoleUI.show_progress("STEP 1 : Analize")
        
        # Jalankan persiapan awal (Cookies & Prompt)
        self._prepare_and_validate()

        # --- RESOLUSI FOLDER KERJA (DYNAMIC ID) ---
        # Kita perlu ID video untuk menentukan folder cache yang tepat
        cookie_path = str(self.paths.COOKIE_FILE) if self.paths.COOKIE_FILE.exists() else None
        yt_provider = DownloaderSetup(self.url, cookies_path=cookie_path)
        folder_name = yt_provider.get_folder_name()
        video_info = yt_provider.get_info()
        
        work_dir = self.paths.TEMP_DIR / folder_name
        if not work_dir.exists():
            work_dir.mkdir(parents=True, exist_ok=True)
            
        logging.info(f"📂 Working Directory: {work_dir}")

        # --- VALIDASI TAHAP AWAL (CACHING) ---
        # Cek apakah summary.json sudah ada dan valid
        summary_file = work_dir / "summary.json"
        if summary_file.exists():
            try:
                content = summary_file.read_text(encoding='utf-8')
                if content and json.loads(content):
                    logging.info("♻️ Cache ditemukan: summary.json sudah ada dan valid. Melewati analisis AI.")
                    return work_dir
            except json.JSONDecodeError:
                logging.warning("⚠️ File summary.json ditemukan tapi korup. Memulai ulang proses.")
        
        # --- PROSES UTAMA ---
        # Cek apakah audio sudah ada (Downloader menanganinya, tapi kita panggil untuk memastikan path)
        audio_path, transcript_text = self._download_media(work_dir, video_info)
        
        self._analyze_with_ai(audio_path, transcript_text, work_dir)

        logging.info("✅ Semua tahap berhasil diselesaikan.")
        return work_dir