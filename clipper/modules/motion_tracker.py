import cv2
import mediapipe as mp
import numpy as np
import os
import logging

from typing import Optional, Deque, Dict, Any, Callable
from collections import deque
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

class MotionTracker:
    def __init__(self, window_size: int):
        self.window_size = window_size
        # Perbaikan type hint untuk deque
        self.raw_history: Deque[np.ndarray] = deque(maxlen=window_size)

    def apply_filter(self, current_landmarks_np: np.ndarray) -> np.ndarray:
        self.raw_history.append(current_landmarks_np)
        # Simple Moving Average (SMA) smoothing
        history_stack = np.array(self.raw_history)
        return np.mean(history_stack, axis=0)

class FaceTrackerProcessor:
    def __init__(self, model_path: str):
        self.model_path = model_path
        
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model MediaPipe tidak ditemukan: {self.model_path}")

        # Inisialisasi model satu kali saat objek dibuat
        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5
        )
        logging.info("🧠 Memuat model MediaPipe FaceLandmarker...")
        self.landmarker = vision.FaceLandmarker.create_from_options(options)

    def close(self):
        """Membersihkan resource MediaPipe."""
        if hasattr(self, 'landmarker') and self.landmarker:
            self.landmarker.close()
            logging.debug("🧠 Model MediaPipe ditutup.")

    def process_and_crop_video(self, input_path: str, output_path: str, window_size: int, prediction_frames: int, progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[Dict[str, Any]]:
        """
        Memproses video: Deteksi wajah -> Crop 9:16 -> Tulis Video Baru (Tanpa Audio).
        Menggantikan logika FFmpeg sendcmd untuk menghindari error filter.
        """
        tracker_logic = MotionTracker(window_size=window_size)
        cap = None
        out = None

        try:
            cap = cv2.VideoCapture(input_path)
            if not cap.isOpened():
                logging.error(f"Gagal membuka video: {input_path}")
                return None

            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # Hitung Target Resolusi (9:16)
            target_h = height
            target_w = int(target_h * 9 / 16)
            if target_w % 2 != 0: target_w -= 1
            if width < target_w: target_w = width
            
            # Setup Video Writer (mp4v codec).
            # Use the static method `VideoWriter.fourcc` to be compliant with modern OpenCV standards
            # and resolve false-positive attribute errors from static analysis tools like Pylance.
            fourcc = cv2.VideoWriter.fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, fps, (target_w, target_h))
            
            frame_count = 0
            cam_x, cam_y = width // 2, height // 2

            logging.info(f"   📐 Processing: {width}x{height} -> {target_w}x{target_h} @ {fps:.2f}fps")

            while cap.isOpened():
                success, frame = cap.read()
                if not success: break

                frame_count += 1
                timestamp_ms = int((frame_count * 1000) / fps)

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image.create_from_array(rgb_frame)

                detection_result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

                if detection_result and detection_result.face_landmarks:
                    face_landmarks = detection_result.face_landmarks[0]
                    landmarks_np = np.array([[lm.x, lm.y] for lm in face_landmarks], dtype=np.float32)
                    current_filtered = tracker_logic.apply_filter(landmarks_np)
                    centroid = np.mean(current_filtered, axis=0)
                    cam_x = int(centroid[0] * width)
                    cam_y = int(centroid[1] * height)

                x1 = max(0, min(cam_x - (target_w // 2), width - target_w))
                y1 = max(0, min(cam_y - (target_h // 2), height - target_h))

                cropped_frame = frame[y1:y1+target_h, x1:x1+target_w]
                out.write(cropped_frame)

                if frame_count % 15 == 0:
                    if progress_callback:
                        progress_callback(frame_count, total_frames)

            return {
                "tracked_video": output_path,
                "width": target_w,
                "height": target_h
            }

        except Exception as e:
            logging.error(f"Error during video processing: {e}", exc_info=True)
            return None
        finally:
            if cap: cap.release()
            if out: out.release()
