import logging
import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv, set_key

from ..pipeline import ProcessingStep, ProcessingContext
from ..core import ProjectCore
from ..interface import ConsoleUI
from ..modules.downloader import Downloader
from ..modules.ai_analyzer import AIAnalyzer
from ..utils import FFmpegWrapper
from ..utils.models import VideoSummary

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

        yt_dlp_download = Downloader(context.url, cookies_path=self.core.paths.COOKIE_FILE, video_info=context.video_info, deno_path=context.deno_path)
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
        analyzer = AIAnalyzer(
            api_key=self.api_key, 
            model_name=self.core.config.GEMINI_MODEL
        )
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