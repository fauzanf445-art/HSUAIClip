import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import numpy as np
import logging
from pathlib import Path
from typing import Optional, Callable, List

from src.domain.interfaces import IFaceTracker, TrackResult

class MediaPipeAdapter(IFaceTracker):
    """
    Implementasi IFaceTracker menggunakan MediaPipe Face Landmarker (Tasks API).
    """

    def __init__(self, model_path: str, window_size: int = 5):
        self.model_path = model_path
        self.window_size = window_size

        # Cek model file
        if not Path(model_path).exists():
            logging.warning(f"⚠️ Model MediaPipe tidak ditemukan di: {model_path}")

    def track_and_crop(self, input_path: str, output_path: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> TrackResult:
        """
        Melakukan tracking wajah dan cropping vertikal (9:16).
        """
        # Setup MediaPipe Tasks (Inisialisasi per klip)
        BaseOptions = python.BaseOptions
        FaceLandmarker = vision.FaceLandmarker
        FaceLandmarkerOptions = vision.FaceLandmarkerOptions
        VisionRunningMode = vision.RunningMode

        base_options = BaseOptions(model_asset_path=self.model_path)
        options = FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=VisionRunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5
        )

        # Buat instance model baru untuk klip ini
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

            # Setup Output Video (9:16)
            target_aspect_ratio = 9 / 16
            out_height = orig_height
            out_width = int(out_height * target_aspect_ratio)
            
            # Setup Video Writer
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            fourcc = cv2.VideoWriter.fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, fps, (out_width, out_height))
            
            frame_idx = 0
            center_x_history: List[float] = []
            last_center_x = orig_width // 2  # Posisi awal default
            last_timestamp_ms = -1  # Melacak timestamp terakhir untuk menjamin urutan naik

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                # Konversi ke RGB untuk MediaPipe
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

                # Deteksi Wajah
                # Hitung timestamp dasar berdasarkan FPS
                timestamp_ms = int((frame_idx * 1000) / fps)
                
                # Pastikan timestamp selalu naik (monotonically increasing)
                if timestamp_ms <= last_timestamp_ms:
                    timestamp_ms = last_timestamp_ms + 1
                last_timestamp_ms = timestamp_ms

                detection_result = landmarker.detect_for_video(mp_image, timestamp_ms)

                # Tentukan Center Crop
                center_x = last_center_x # Gunakan posisi terakhir jika wajah hilang

                if detection_result.face_landmarks:
                    face_landmarks = detection_result.face_landmarks[0]
                    avg_x = sum([lm.x for lm in face_landmarks]) / len(face_landmarks)
                    current_center_x = int(avg_x * orig_width)
                    
                    # Smoothing
                    center_x_history.append(current_center_x)
                    if len(center_x_history) > self.window_size:
                        center_x_history.pop(0)
                    
                    center_x = int(sum(center_x_history) / len(center_x_history))
                    last_center_x = center_x # Update posisi terakhir

                # Hitung koordinat crop
                x1 = max(0, center_x - out_width // 2)
                x2 = x1 + out_width
                
                # Koreksi batas
                if x1 < 0:
                    x1 = 0
                    x2 = out_width
                if x2 > orig_width:
                    x2 = orig_width
                    x1 = x2 - out_width

                # Crop
                cropped_frame = frame[:, x1:x2]
                if cropped_frame.shape[1] != out_width or cropped_frame.shape[0] != out_height:
                    cropped_frame = cv2.resize(cropped_frame, (out_width, out_height))
                
                out.write(cropped_frame)

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
            # Bersihkan model dan video capture setiap selesai satu klip
            landmarker.close()
            if cap:
                cap.release()
            if out:
                out.release()