import logging
import os
import concurrent.futures
from pathlib import Path
from tqdm import tqdm
from typing import List, Tuple, Optional

# Import Services
from src.application.services.media_service import MediaService
from src.application.services.audio_service import AudioService
from src.application.services.analysis_service import AnalysisService
from src.application.services.video_service import VideoService
from src.application.services.captioning_service import CaptioningService

# Import Config & UI
from src.config.settings import AppConfig
from src.infrastructure.cli_ui import ConsoleUI
from src.domain.models import Clip
from src.domain.interfaces import TrackResult

class Orchestrator:
    """
    Mengatur alur kerja (pipeline) utama aplikasi.
    Menghubungkan semua service untuk memproses video dari awal hingga akhir.
    """
    def __init__(
        self,
        config: AppConfig,
        ui: ConsoleUI,
        media_service: MediaService,
        audio_service: AudioService,
        analysis_service: AnalysisService,
        video_service: VideoService,
        captioning_service: CaptioningService
    ):
        self.config = config
        self.ui = ui
        self.media = media_service
        self.audio = audio_service
        self.analysis = analysis_service
        self.video = video_service
        self.captioning = captioning_service

    def _prepare_workspace(self, url: str) -> Tuple[str, Path]:
        """Mempersiapkan folder kerja untuk proses pipeline."""
        self.ui.show_step("Persiapan Workspace")
        safe_name = self.media.get_safe_filename(url)
        work_dir = self.config.paths.TEMP_DIR / safe_name
        work_dir.mkdir(parents=True, exist_ok=True)
        self.ui.log(f"Working Directory: {work_dir}")
        return safe_name, work_dir

    def _get_clips_for_processing(self, url: str, work_dir: Path) -> List[Clip]:
        """Mendapatkan daftar klip, baik dari input manual atau analisis AI."""
        self.ui.show_step("Analisis Konten")
        
        manual_timestamps = self.ui.get_manual_clips()
        if manual_timestamps:
            self.ui.log(f"Mode manual: {len(manual_timestamps)} klip akan diproses.")
            clips = []
            for i, ts in enumerate(manual_timestamps):
                start = ts['start_time']
                end = ts['end_time']
                clips.append(Clip(
                    id=f"manual_{i}",
                    title=f"Manual Clip {i+1}",
                    start_time=start,
                    end_time=end,
                    duration=end - start,
                    energy_score=0,
                    vocal_energy="N/A",
                    audio_justification="Manual",
                    description="Manual timestamp",
                    caption=""
                ))
            return clips
 
        self.ui.log("Mode AI: Menganalisis video untuk klip potensial...")
        transcript = self.media.get_transcript(url)
        
        audio_wav_path = self.audio.prepare_audio_for_analysis(url, work_dir, "full_audio")
        if not audio_wav_path:
            raise RuntimeError("Gagal menyiapkan audio untuk analisis.")

        prompt = self.config.get_prompt_template()
        cache_path = str(work_dir / "summary.json")
        
        summary = self.analysis.analyze_video(
            transcript=transcript,
            audio_path=str(audio_wav_path),
            prompt=prompt,
            cache_path=cache_path
        )
        self.ui.log(f"AI menemukan {len(summary.clips)} klip potensial.")
        return summary.clips

    def _cut_raw_clips(self, clips: List[Clip], url: str, work_dir: Path) -> List[Path]:
        """Memotong klip mentah dari stream video."""
        self.ui.show_step("Memotong Klip Video")
        video_url, audio_url = self.media.get_stream_urls(url)
        if not video_url:
            raise RuntimeError("Gagal mendapatkan URL stream video.")

        raw_clips_dir = work_dir / "raw_clips"
        created_clip_paths = self.video.batch_create_clips(
            clips=clips,
            video_url=video_url,
            audio_url=audio_url,
            output_dir=raw_clips_dir
        )
        self.ui.log(f"{len(created_clip_paths)} dari {len(clips)} klip berhasil dipotong.")
        return created_clip_paths

    def _track_clips(self, raw_clip_paths: List[Path], work_dir: Path) -> List[Tuple[Path, TrackResult]]:
        """Menjalankan motion tracking pada setiap klip mentah."""
        self.ui.show_step("Motion Tracking (MediaPipe)")
        tracked_dir = work_dir / "tracked_clips"
        tracked_results: List[Tuple[Path, TrackResult]] = []
        
        # Outer progress bar untuk setiap klip
        for clip_path in tqdm(raw_clip_paths, desc="Overall Tracking", unit="clip"):
            self.ui.log(f"Tracking klip: {clip_path.name}")
            output_tracked = tracked_dir / f"tracked_{clip_path.name}"
            
            # Inner progress bar untuk frame di dalam satu klip
            frame_pbar = tqdm(total=1, desc="   -> Frames", unit="frame", leave=False)
            
            def progress_cb(curr: int, total: int):
                if frame_pbar.total != total:
                    frame_pbar.total = total
                frame_pbar.update(curr - frame_pbar.n)
            
            try:
                # Eksekusi Sekuensial: Mencegah OOM dengan memproses satu per satu
                result = self.video.track_subject(str(clip_path), str(output_tracked), progress_callback=progress_cb)
                tracked_results.append((clip_path, result))
            except Exception as e:
                logging.error(f"❌ Gagal tracking klip {clip_path.name}: {e}")
                self.ui.log(f"⚠️ Skip klip {clip_path.name} karena error tracking.")
            finally:
                if not frame_pbar.disable:
                    frame_pbar.close()

        return tracked_results

    def _render_final_clips(self, tracked_results: List[Tuple[Path, TrackResult]], work_dir: Path, safe_name: str) -> List[Path]:
        """Membuat subtitle dan merender video final."""
        self.ui.show_step("Captioning & Rendering Final")
        final_dir = self.config.paths.OUTPUT_DIR / safe_name
        final_clips = []
        
        # Tentukan jumlah worker berdasarkan kemampuan hardware (GPU vs CPU)
        if self.video.processor.is_gpu_enabled:
            max_workers = 1
            logging.info("🚀 GPU Encoder terdeteksi: Rendering final dibatasi 1 worker.")
        else:
            max_workers = os.cpu_count() or 2
            logging.info(f"⚙️ CPU Encoder terdeteksi: Rendering final menggunakan {max_workers} worker.")

        def _process_render(item: Tuple[Path, TrackResult]) -> Optional[Path]:
            original_path, track_res = item
            try:
                sub_path = final_dir / "subs" / f"{original_path.stem}.ass"
                self.captioning.generate_subtitles_for_clip(
                    str(original_path), str(sub_path), work_dir, 
                    self.config.karaoke_chunk_size, track_res['width'], track_res['height']
                )

                final_out = final_dir / f"final_{original_path.name}"
                if self.video.render_final_video(
                    video_path=str(track_res['tracked_video']), 
                    audio_path=str(original_path), 
                    subtitle_path=str(sub_path), 
                    output_path=str(final_out), 
                    fonts_dir=str(self.config.paths.FONTS_DIR)
                ):
                    return final_out
            except Exception as e:
                logging.error(f"❌ Gagal merender klip {original_path.name}: {e}")
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_render, item): item for item in tracked_results}
            
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(tracked_results), desc="Rendering Clips", unit="clip"):
                result = future.result()
                if result:
                    final_clips.append(result)
                    
        return sorted(final_clips, key=lambda p: p.name)

    def run(self, url: str):
        """Menjalankan pipeline lengkap."""
        try:
            safe_name, work_dir = self._prepare_workspace(url)
            
            clips = self._get_clips_for_processing(url, work_dir)
            if not clips:
                self.ui.show_error("Tidak ada klip yang ditemukan atau dibuat.")
                return

            raw_clip_paths = self._cut_raw_clips(clips, url, work_dir)
            if not raw_clip_paths:
                self.ui.show_error("Gagal memotong klip mentah sama sekali.")
                return

            tracked_results = self._track_clips(raw_clip_paths, work_dir)
            
            final_clips = self._render_final_clips(tracked_results, work_dir, safe_name)

            self.ui.show_success(self.config.paths.OUTPUT_DIR / safe_name, final_clips)

        except Exception as e:
            logging.error("Orchestrator Error", exc_info=True)
            self.ui.show_error(str(e))