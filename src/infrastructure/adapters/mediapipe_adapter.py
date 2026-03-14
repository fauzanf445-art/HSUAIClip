import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np
import logging
import urllib.request
from pathlib import Path
from typing import Optional, Callable

from src.domain.interfaces import IFaceTracker, TrackResult

class MediaPipeAdapter(IFaceTracker):
    """
    Implementasi IFaceTracker menggunakan MediaPipe Face Landmarker (Tasks API).
    """

    MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

    def __init__(self, model_path: str, window_size: int = 5, process_every_n_frames: int = 3):
        self.model_path = model_path
        self.window_size = window_size
        self.process_every_n_frames = process_every_n_frames
        self._gpu_fallback_logged = False

        # Cek model file
        if not Path(model_path).exists():
            logging.warning(f"⚠️ Model MediaPipe tidak ditemukan di: {model_path}")
            self._download_model(Path(model_path))

    def _download_model(self, target_path: Path):
        """Mengunduh model Face Landmarker dari Google Storage."""
        logging.info(f"⬇️ Sedang mengunduh model dari: {self.MODEL_URL}")
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(self.MODEL_URL) as response:
                if response.status == 200:
                    with open(target_path, 'wb') as f:
                        f.write(response.read())
                    logging.info("✅ Download model selesai.")
                else:
                    raise IOError(f"HTTP Error: {response.status}")
        except Exception as e:
            logging.error(f"❌ Gagal mengunduh model: {e}")
            raise RuntimeError("Gagal mengunduh model MediaPipe. Periksa koneksi internet.")

    def track_and_crop(self, input_path: str, output_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> TrackResult:
        # Setup MediaPipe Tasks
        BaseOptions = python.BaseOptions
        FaceLandmarker = vision.FaceLandmarker
        FaceLandmarkerOptions = vision.FaceLandmarkerOptions
        VisionRunningMode = vision.RunningMode

        # 1. Inisialisasi Landmarker dengan Safe Fallback (GPU -> CPU)
        landmarker = None
        try:
            # Coba inisialisasi dengan GPU
            base_options = BaseOptions(model_asset_path=self.model_path, delegate=BaseOptions.Delegate.GPU)
            options = FaceLandmarkerOptions(
                base_options=base_options,
                running_mode=VisionRunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5
            )
            landmarker = FaceLandmarker.create_from_options(options)
            logging.info("🚀 MediaPipe: Menggunakan GPU Delegate.")
        except Exception as e:
            if not self._gpu_fallback_logged:
                logging.warning(f"⚠️ MediaPipe GPU gagal. Fallback ke CPU (Pesan ini hanya muncul sekali).")
                self._gpu_fallback_logged = True
            
            logging.debug(f"⚠️ MediaPipe GPU gagal ({e}). Fallback ke CPU.")
            # Fallback ke CPU
            base_options = BaseOptions(model_asset_path=self.model_path, delegate=BaseOptions.Delegate.CPU)
            options = FaceLandmarkerOptions(
                base_options=base_options,
                running_mode=VisionRunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5
            )
            landmarker = FaceLandmarker.create_from_options(options)

        cap = None
        out = None

        try:
            cap = cv2.VideoCapture(input_path)
            if not cap.isOpened():
                raise RuntimeError(f"Gagal membuka video: {input_path}")

            # Properti Video Asli
            orig_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            orig_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 30.0 # Fallback jika FPS tidak valid
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # Validasi dimensi video
            if orig_width == 0 or orig_height == 0:
                raise RuntimeError(f"Gagal membaca dimensi video dari {input_path}. File mungkin korup.")

            # Setup Output Video (9:16)
            target_aspect_ratio = 9 / 16
            out_height = orig_height
            out_width = int(out_height * target_aspect_ratio)
            
            # Setup Video Writer
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            fourcc = cv2.VideoWriter.fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, fps, (out_width, out_height))
            
            # Tracking Variables
            frame_idx = 0
            last_timestamp_ms = -1
            
            # EMA (Exponential Moving Average) Variables
            ema_alpha = 0.2  # Faktor smoothing (0.0 - 1.0)
            current_center_x = float(orig_width // 2) # Mulai dari tengah
            
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                # 2. Deteksi pada setiap frame
                # Konversi ke RGB untuk MediaPipe
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

                # Hitung timestamp (Monotonically Increasing)
                timestamp_ms = int((frame_idx * 1000) / fps)
                if timestamp_ms <= last_timestamp_ms:
                    timestamp_ms = last_timestamp_ms + 1
                last_timestamp_ms = timestamp_ms

                detection_result = landmarker.detect_for_video(mp_image, timestamp_ms)

                # 3. Update Center dengan Landmark Hidung (Index 4) & EMA
                if detection_result.face_landmarks:
                    # Ambil landmark hidung (index 4) sebagai referensi stabil
                    nose_landmark = detection_result.face_landmarks[0][4]
                    target_x = nose_landmark.x * orig_width
                    
                    # Terapkan EMA untuk pergerakan kamera yang halus
                    current_center_x = (ema_alpha * target_x) + ((1 - ema_alpha) * current_center_x)

                # 4. Hitung Koordinat Crop dengan presisi dan batasan
                # Logika ini memastikan hasil crop memiliki lebar yang benar dan berada dalam batas video.
                actual_crop_width = min(out_width, orig_width)
                
                # Tentukan batas kiri (x1) dari area crop, berpusat pada subjek
                x1 = int(current_center_x - actual_crop_width / 2)

                # Jaga agar window crop tidak keluar dari batas video (clamping)
                x1 = max(0, x1) # Cegah nilai negatif
                x1 = min(x1, orig_width - actual_crop_width) # Cegah sisi kanan crop melebihi batas

                x2 = x1 + actual_crop_width

                # 5. Crop & Resize Cerdas (Hanya jika perlu)
                cropped_frame = frame[:, x1:x2]
                
                # Selalu resize untuk memastikan dimensi output konsisten.
                # Menghilangkan optimasi sebelumnya untuk menjamin setiap frame sesuai target.
                final_frame = cv2.resize(cropped_frame, (out_width, out_height), interpolation=cv2.INTER_AREA)
                
                out.write(final_frame)

                frame_idx += 1
                if progress_callback:
                    progress_callback(frame_idx, total_frames)

            return {
                "tracked_video": output_path,
                "width": out_width,
                "height": out_height
            }

        except Exception as e:
            logging.error(f"Error during video processing: {e}", exc_info=True)
            raise
        finally:
            # 6. Cleanup Resource (Mencegah OOM)
            if landmarker:
                landmarker.close()
            if cap:
                cap.release()
            if out:
                out.release()