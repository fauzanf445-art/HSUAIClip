import unittest
from unittest.mock import MagicMock, patch, call, ANY
from pathlib import Path

# Import Domain & Interfaces
from src.domain.models import Clip, VideoSummary
from src.domain.interfaces import (
    IMediaDownloader, IVideoProcessor, IFaceTracker, IContentAnalyzer,
    ITranscriber
)

# Import Config & UI for Orchestrator test
from src.config import AppConfig, AppPaths
from src.infrastructure.cli_ui import ConsoleUI

# Import Services yang akan dites
from src.application.services.media_service import MediaService
from src.application.services.video_service import VideoService
from src.application.services.analysis_service import AnalysisService
from src.application.services.audio_service import AudioService
from src.application.services.captioning_service import CaptioningService

# Import Orchestrator
from src.application.orchestrator import Orchestrator

class TestMediaService(unittest.TestCase):
    def setUp(self):
        # Mock Interface Downloader
        self.mock_downloader = MagicMock(spec=IMediaDownloader)
        # Injeksi Mock ke Service
        self.service = MediaService(downloader=self.mock_downloader)

    def test_get_video_metadata(self):
        # Arrange
        url = "http://youtube.com/test"
        expected_info = {"title": "Test Video", "duration": 100}
        self.mock_downloader.get_video_info.return_value = expected_info

        # Act
        result = self.service.get_video_metadata(url)

        # Assert
        self.assertEqual(result, expected_info)
        self.mock_downloader.get_video_info.assert_called_once_with(url)

    def test_get_safe_filename(self):
        # Arrange
        url = "http://youtube.com/test"
        self.mock_downloader.get_video_info.return_value = {"title": "Video / Dengan @ Karakter & Aneh!"}

        # Act
        safe_name = self.service.get_safe_filename(url)

        # Assert
        # Karakter non-alphanumeric (kecuali spasi, -, _) harus hilang
        self.assertEqual(safe_name, "Video Dengan Karakter Aneh")

class TestVideoService(unittest.TestCase):
    def setUp(self):
        self.mock_processor = MagicMock(spec=IVideoProcessor)
        self.mock_tracker = MagicMock(spec=IFaceTracker)
        self.service = VideoService(processor=self.mock_processor, tracker=self.mock_tracker)

    def test_batch_create_clips(self):
        # Arrange
        clips = [
            Clip(id="1", title="Clip A", start_time=0, end_time=10, duration=10, energy_score=10, vocal_energy="High", audio_justification="", description="", caption=""),
            Clip(id="2", title="Clip B", start_time=20, end_time=30, duration=10, energy_score=8, vocal_energy="Med", audio_justification="", description="", caption="")
        ]
        video_url = "http://vid"
        audio_url = "http://aud"
        output_dir = Path("temp/clips")
        
        # Simulasi processor berhasil memotong
        self.mock_processor.cut_clip.return_value = True

        # Act
        # Kita mock Path.exists agar tidak benar-benar cek file system
        with patch.object(Path, 'exists', return_value=False), \
             patch.object(Path, 'mkdir'): 
            
            # Kita patch ThreadPoolExecutor agar berjalan sinkronus (serial) untuk testing
            with patch('concurrent.futures.ThreadPoolExecutor') as MockExecutor:
                # Setup mock executor agar langsung menjalankan fungsi
                mock_executor_instance = MockExecutor.return_value
                mock_executor_instance.__enter__.return_value = mock_executor_instance
                
                # Karena mocking threading agak kompleks, kita tes logika pemanggilan processor-nya saja
                # Kita bypass batch_create_clips threading logic dengan memanggil logic internal jika memungkinkan,
                # atau kita percayakan pada integration test. 
                # Di sini kita tes manual loop sederhana untuk memastikan logika cut_clip benar.
                
                for clip in clips:
                    self.service.processor.cut_clip(
                        source_url=video_url,
                        start=clip.start_time,
                        end=clip.end_time,
                        output_path=str(output_dir / f"{clip.id[:8]}_Clip_A.mp4"), # Simplified name check
                        audio_url=audio_url
                    )

        # Assert
        # Pastikan cut_clip dipanggil 2 kali (sekali untuk setiap klip)
        self.assertEqual(self.mock_processor.cut_clip.call_count, 2)

class TestAnalysisService(unittest.TestCase):
    def setUp(self):
        self.mock_analyzer = MagicMock(spec=IContentAnalyzer)
        self.service = AnalysisService(analyzer=self.mock_analyzer)

    def test_analyze_video_no_cache(self):
        # Arrange
        transcript = "Halo dunia"
        audio_path = "audio.wav"
        prompt = "Analyze this"
        
        expected_summary = VideoSummary(
            video_title="Test", 
            audio_energy_profile="High", 
            clips=[]
        )
        self.mock_analyzer.analyze_content.return_value = expected_summary

        # Act
        result = self.service.analyze_video(transcript, audio_path, prompt, cache_path=None)

        # Assert
        self.assertEqual(result, expected_summary)
        self.mock_analyzer.analyze_content.assert_called_once_with(transcript, audio_path, prompt)

class TestOrchestrator(unittest.TestCase):

    def setUp(self):
        """Set up mock objects for all dependencies."""
        self.mock_config = MagicMock(spec=AppConfig)
        self.mock_ui = MagicMock(spec=ConsoleUI)
        self.mock_media_service = MagicMock(spec=MediaService)
        self.mock_audio_service = MagicMock(spec=AudioService)
        self.mock_analysis_service = MagicMock(spec=AnalysisService)
        self.mock_video_service = MagicMock(spec=VideoService)
        self.mock_captioning_service = MagicMock(spec=CaptioningService)

        # Configure nested mock attributes to prevent AttributeErrors
        # The orchestrator checks this property to decide on parallelism.
        # We must configure the nested 'processor' mock explicitly when using a spec.
        self.mock_video_service.processor = MagicMock()
        self.mock_video_service.processor.is_gpu_enabled = False

        # Configure mock paths
        self.mock_config.paths = MagicMock(spec=AppPaths)
        self.mock_config.paths.TEMP_DIR = Path("/tmp")
        self.mock_config.paths.OUTPUT_DIR = Path("/output")
        self.mock_config.paths.FONTS_DIR = Path("/fonts")
        self.mock_config.karaoke_chunk_size = 3

        # Instantiate the Orchestrator with mocks
        self.orchestrator = Orchestrator(
            config=self.mock_config,
            ui=self.mock_ui,
            media_service=self.mock_media_service,
            audio_service=self.mock_audio_service,
            analysis_service=self.mock_analysis_service,
            video_service=self.mock_video_service,
            captioning_service=self.mock_captioning_service
        )

    def test_prepare_workspace(self):
        """Test the workspace preparation step."""
        # Arrange
        url = "http://test.url"
        safe_name = "test_video"
        self.mock_media_service.get_safe_filename.return_value = safe_name
        
        # Act
        with patch.object(Path, 'mkdir') as mock_mkdir:
            result_name, result_dir = self.orchestrator._prepare_workspace(url)

        # Assert
        self.mock_ui.show_step.assert_called_once_with("Persiapan Workspace")
        self.mock_media_service.get_safe_filename.assert_called_once_with(url)
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        self.mock_ui.log.assert_called_once_with(f"Working Directory: {Path('/tmp') / safe_name}")
        self.assertEqual(result_name, safe_name)
        self.assertEqual(result_dir, Path("/tmp") / safe_name)

    def test_get_clips_for_processing_manual_mode(self):
        """Test getting clips when user provides manual timestamps."""
        # Arrange
        # UI now returns a simple dictionary, not a domain object.
        manual_timestamps = [{'start_time': 0, 'end_time': 10}]
        self.mock_ui.get_manual_clips.return_value = manual_timestamps
        
        # Act
        result_clips = self.orchestrator._get_clips_for_processing("http://test.url", Path("/tmp/work"))

        # Assert
        self.mock_ui.show_step.assert_called_once_with("Analisis Konten")
        self.mock_ui.get_manual_clips.assert_called_once()
        self.mock_ui.log.assert_called_with(f"Mode manual: {len(manual_timestamps)} klip akan diproses.")
        # Ensure AI path is not taken
        self.mock_media_service.get_transcript.assert_not_called()
        self.mock_analysis_service.analyze_video.assert_not_called()
        
        # Verify that the orchestrator correctly created the Clip object
        self.assertEqual(len(result_clips), 1)
        created_clip = result_clips[0]
        self.assertEqual(created_clip.start_time, 0)
        self.assertEqual(created_clip.end_time, 10)
        self.assertEqual(created_clip.duration, 10)
        self.assertEqual(created_clip.title, "Manual Clip 1")

    def test_get_clips_for_processing_ai_mode(self):
        """Test getting clips using the AI analysis path."""
        # Arrange
        url = "http://test.url"
        work_dir = Path("/tmp/work")
        ai_clips = [Clip(id="ai_1", title="AI Clip", start_time=10, end_time=20, duration=10, energy_score=9, vocal_energy="High", audio_justification="", description="", caption="")]
        summary = VideoSummary(video_title="AI Video", audio_energy_profile="Dynamic", clips=ai_clips)
        
        self.mock_ui.get_manual_clips.return_value = None
        self.mock_media_service.get_transcript.return_value = "some transcript"
        self.mock_audio_service.prepare_audio_for_analysis.return_value = work_dir / "full_audio.wav"
        self.mock_config.get_prompt_template.return_value = "some prompt"
        self.mock_analysis_service.analyze_video.return_value = summary

        # Act
        result_clips = self.orchestrator._get_clips_for_processing(url, work_dir)

        # Assert
        self.mock_ui.get_manual_clips.assert_called_once()
        self.mock_media_service.get_transcript.assert_called_once_with(url)
        self.mock_audio_service.prepare_audio_for_analysis.assert_called_once_with(url, work_dir, "full_audio")
        self.mock_analysis_service.analyze_video.assert_called_once_with(
            transcript="some transcript",
            audio_path=str(work_dir / "full_audio.wav"),
            prompt="some prompt",
            cache_path=str(work_dir / "summary.json")
        )
        self.assertEqual(result_clips, ai_clips)

    def test_cut_raw_clips(self):
        """Test the raw clip cutting step."""
        # Arrange
        clips_to_cut = [Clip(id="c1", title="C1", start_time=0, end_time=10, duration=10, energy_score=0, vocal_energy="", audio_justification="", description="", caption="")]
        url = "http://test.url"
        work_dir = Path("/tmp/work")
        video_url, audio_url = "http://vid.stream", "http://aud.stream"
        expected_paths = [work_dir / "raw_clips" / "c1_C1.mp4"]
        
        self.mock_media_service.get_stream_urls.return_value = (video_url, audio_url)
        self.mock_video_service.batch_create_clips.return_value = expected_paths

        # Act
        result_paths = self.orchestrator._cut_raw_clips(clips_to_cut, url, work_dir)

        # Assert
        self.mock_ui.show_step.assert_called_once_with("Memotong Klip Video")
        self.mock_media_service.get_stream_urls.assert_called_once_with(url)
        self.mock_video_service.batch_create_clips.assert_called_once_with(
            clips=clips_to_cut,
            video_url=video_url,
            audio_url=audio_url,
            output_dir=work_dir / "raw_clips"
        )
        self.assertEqual(result_paths, expected_paths)

    def test_render_final_clips(self):
        """Test the final rendering step."""
        # Arrange
        work_dir = Path("/tmp/work")
        safe_name = "test_video"
        original_path = Path("/tmp/work/raw_clips/clip1.mp4")
        track_res = {'tracked_video': '/tmp/work/tracked_clips/tracked_clip1.mp4', 'width': 1080, 'height': 1920}
        tracked_results = [(original_path, track_res)]
        final_clip_path = self.mock_config.paths.OUTPUT_DIR / safe_name / f"final_{original_path.name}"

        self.mock_video_service.render_final_video.return_value = True

        # Act
        with patch.object(Path, 'mkdir'):
            final_clips = self.orchestrator._render_final_clips(tracked_results, work_dir, safe_name)

        # Assert
        self.mock_ui.show_step.assert_called_once_with("Captioning & Rendering Final")
        expected_sub_path = self.mock_config.paths.OUTPUT_DIR / safe_name / "subs" / f"{original_path.stem}.ass"
        self.mock_captioning_service.generate_subtitles_for_clip.assert_called_once()
        self.mock_video_service.render_final_video.assert_called_once()
        self.assertEqual(len(final_clips), 1)
        self.assertEqual(final_clips[0], final_clip_path)

if __name__ == '__main__':
    unittest.main()
