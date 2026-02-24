import cv2
import mediapipe as mp
import numpy as np
import os
import logging
import sys
from typing import Optional, Deque
from collections import deque
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from typing import List, Dict, Any

# --- Configuration ---
WINDOW_SIZE = 5
PREDICTION_FRAMES = 3
DRAW_EVERY_NTH = 20

class MotionTracker:
    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        # Perbaikan type hint untuk deque
        self.raw_history: Deque[np.ndarray] = deque(maxlen=window_size)
        
        self.kf_initialized = False
        self.state: Optional[np.ndarray] = None 
        self.covariance: Optional[np.ndarray] = None      
        
        # Inisialisasi matriks dengan tipe data eksplisit untuk menghindari komplain Pylance
        self.F = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=np.float32)
        self.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=np.float32)
        self.Q = np.eye(4, dtype=np.float32) * 1e-2
        self.R = np.eye(2, dtype=np.float32) * 1e-1

    def apply_filter(self, current_landmarks_np: np.ndarray) -> np.ndarray:
        self.raw_history.append(current_landmarks_np)
        # Simple Moving Average (SMA) smoothing
        history_stack = np.array(self.raw_history)
        return np.mean(history_stack, axis=0)

    def predict_motion(self, current_filtered_np: np.ndarray) -> np.ndarray:
        num_points = current_filtered_np.shape[0]
        
        if not self.kf_initialized or self.state is None or self.covariance is None:
            self.state = np.zeros((num_points, 4), dtype=np.float32)
            self.state[:, :2] = current_filtered_np
            self.covariance = np.tile(np.eye(4, dtype=np.float32), (num_points, 1, 1))
            self.kf_initialized = True
            return current_filtered_np

        # Operasi matriks sering memicu Pylance "None" check, gunakan asertif
        state = self.state
        cov = self.covariance

        # 1. Predict Step
        # Menggunakan np.matmul (@) secara eksplisit pada array multidimensi
        state = state @ self.F.T
        cov = (self.F @ cov) @ self.F.T + self.Q

        # 2. Update Step
        Z = current_filtered_np
        # Y: Residual, S: System Uncertainty, K: Kalman Gain
        Y = Z - (state @ self.H.T)
        S = (self.H @ cov) @ self.H.T + self.R
        K = (cov @ self.H.T) @ np.linalg.inv(S)
        
        # Update State & Covariance
        state = state + (K @ Y[:, :, np.newaxis]).squeeze(2)
        I = np.eye(4, dtype=np.float32)
        cov = (I - (K @ self.H)) @ cov

        self.state = state
        self.covariance = cov

        # 3. Future Prediction
        k = PREDICTION_FRAMES
        predicted_pos = state[:, :2] + (state[:, 2:] * k)
        
        return predicted_pos

class FaceTrackerProcessor:
    def __init__(self, model_path: str):
        self.model_path = model_path

    def visualize_results(self, image: np.ndarray, current_landmarks: Optional[np.ndarray], predicted_landmarks: Optional[np.ndarray]) -> np.ndarray:
        h, w, _ = image.shape
        curr_px: Optional[np.ndarray] = None
        
        if current_landmarks is not None:
            # Pylance butuh kepastian tipe data setelah operasi perkalian
            curr_px = (current_landmarks * np.array([w, h])).astype(np.int32)
            for pt in curr_px:
                cv2.circle(image, (int(pt[0]), int(pt[1])), 1, (0, 255, 0), -1)

        if predicted_landmarks is not None:
            pred_px = (predicted_landmarks * np.array([w, h])).astype(np.int32)
            for i, pt in enumerate(pred_px):
                if i % DRAW_EVERY_NTH == 0:
                    center = (int(pt[0]), int(pt[1]))
                    cv2.circle(image, center, 2, (0, 0, 255), -1)
                    if curr_px is not None:
                        start_pt = (int(curr_px[i][0]), int(curr_px[i][1]))
                        cv2.line(image, start_pt, center, (0, 0, 255), 1)
        return image

    def create_tracked_video(self, input_path: str, output_path: str) -> bool:
        """
        Memproses video: Deteksi wajah -> Crop 9:16 -> Tulis Video Baru (Tanpa Audio).
        Menggantikan logika FFmpeg sendcmd untuk menghindari error filter.
        """
        if not os.path.exists(self.model_path):
            logging.error(f"Model not found: {self.model_path}")
            return False

        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5
        )

        tracker_logic = MotionTracker(window_size=WINDOW_SIZE)

        try:
            with vision.FaceLandmarker.create_from_options(options) as landmarker:
                cap = cv2.VideoCapture(input_path)
                if not cap.isOpened():
                    logging.error(f"Gagal membuka video: {input_path}")
                    return False

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
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

                    detection_result = landmarker.detect_for_video(mp_image, timestamp_ms)

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
                        percent = int((frame_count / total_frames) * 100) if total_frames > 0 else 0
                        sys.stdout.write(f"\r   ⏳ Processing Frames: {percent}% ({frame_count}/{total_frames})")
                        sys.stdout.flush()

                cap.release()
                out.release()
                sys.stdout.write("\n")
                return True

        except Exception as e:
            logging.error(f"Error during video processing: {e}", exc_info=True)
            return False

    def analyze_video_for_cropping(self, video_path: str) -> Optional[Dict[str, Any]]:
        """
        Menganalisis video untuk mendeteksi wajah dan menghitung koordinat crop yang optimal per frame.
        Tidak menulis video, hanya mengembalikan data analisis.
        """
        if not os.path.exists(self.model_path):
            logging.error(f"Model not found: {self.model_path}")
            return None

        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.8,
        )

        tracker_logic = MotionTracker(window_size=WINDOW_SIZE)
        crop_data: List[Dict[str, Any]] = []

        try:
            with vision.FaceLandmarker.create_from_options(options) as landmarker:
                cap = cv2.VideoCapture(video_path)
                if not cap.isOpened():
                    logging.error(f"Gagal membuka video: {video_path}")
                    return None

                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

                target_h = height
                target_w = int(target_h * 9 / 16)
                if target_w % 2 != 0: target_w -= 1
                if width < target_w: target_w = width

                frame_count = 0
                cam_x, cam_y = width // 2, height // 2

                logging.info(f"   📐 Analyzing: {width}x{height} -> {target_w}x{target_h} @ {fps:.2f}fps")

                while cap.isOpened():
                    success, frame = cap.read()
                    if not success: break

                    frame_count += 1
                    timestamp_ms = int((frame_count * 1000) / fps)

                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

                    detection_result = landmarker.detect_for_video(mp_image, timestamp_ms)

                    if detection_result and detection_result.face_landmarks:
                        face_landmarks = detection_result.face_landmarks[0]
                        landmarks_np = np.array([[lm.x, lm.y] for lm in face_landmarks], dtype=np.float32)

                        current_filtered = tracker_logic.apply_filter(landmarks_np)
                        centroid = np.mean(current_filtered, axis=0)
                        cam_x = int(centroid[0] * width)
                        cam_y = int(centroid[1] * height)

                    x1 = max(0, min(cam_x - (target_w // 2), width - target_w))
                    y1 = max(0, min(cam_y - (target_h // 2), height - target_h))

                    crop_data.append({"timestamp": timestamp_ms / 1000.0, "x": x1, "y": y1})

                    if frame_count % 15 == 0:
                        percent = int((frame_count / total_frames) * 100) if total_frames > 0 else 0
                        sys.stdout.write(f"\r   ⏳ Analyzing Frames: {percent}% ({frame_count}/{total_frames})")
                        sys.stdout.flush()

                cap.release()
                sys.stdout.write("\n")
                return {"fps": fps, "target_w": target_w, "target_h": target_h, "crop_data": crop_data}
        except Exception as e:
            logging.error(f"Error during video analysis: {e}", exc_info=True)
            return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 2:
        proc = FaceTrackerProcessor(sys.argv[2])
        analysis_result = proc.analyze_video_for_cropping(sys.argv[1])
        if analysis_result:
            print("Analysis successful.")
            print(f"FPS: {analysis_result['fps']}")
            print(f"Target Res: {analysis_result['target_w']}x{analysis_result['target_h']}")
            print(f"Found {len(analysis_result['crop_data'])} data points.")
        else:
            print("Analysis failed.")