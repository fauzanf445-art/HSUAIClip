import logging
import os
import sys
import urllib.request
import shutil
import subprocess

from pathlib import Path
from types import SimpleNamespace
from typing import Any

class ProjectCore:
    """
    Kelas inti untuk mengelola konfigurasi jalur dan pengaturan proyek.
    """
    MP_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

    _assets_verified = False

    def __init__(self):
        self.paths = self._setup_paths()
        self.config = self._setup_config()
        self._setup_logging()
        self._create_folder_structure()
        self._register_bin_to_path()
        
        logging.debug("🚀 ProjectCore: Infrastruktur siap digunakan.")

    def _setup_config(self) -> SimpleNamespace:
        """
        Mengkonfigurasi semua parameter dan nilai-nilai yang dapat disesuaikan.
        """
        # --- AI Analysis ---
        ai_analysis = {
            "GEMINI_MODEL": "gemini-flash-latest",
        }

        # --- Motion Tracking ---
        motion_tracking = {
            "WINDOW_SIZE": 5,
            "PREDICTION_FRAMES": 3,
        }

        # --- Captioning ---
        captioning: dict[str, Any] = {
            "KARAOKE_CHUNK_SIZE": 3,
            # Definisi model Whisper berdasarkan VRAM
            "WHISPER_MODELS": {
                "high_end": {"name": "large-v3", "vram_min": 10},
                "mid_range": {"name": "medium", "vram_min": 4},
                "low_end": {"name": "small", "vram_min": 0}, # Fallback
            }
        }

        # --- File & Directory ---
        # Nama folder, bukan path lengkap. Path lengkap dibuat di engine.
        file_system = {
            "DIR_RAWCLIPS": "rawclips",
            "DIR_TRACKEDCLIPS": "tracked_clips",
            "DIR_FINALCLIPS": "final_clips",
        }
        
        return SimpleNamespace(
            **motion_tracking,
            **ai_analysis,
            **captioning,
            **file_system
        )

    def _get_base_path(self) -> Path:
        """Menentukan root directory project berdasarkan environment."""
        if env_base := os.getenv('HSU_AI_CLIP_HOME'):
            logging.info(f"📂 Menggunakan path dari Environment: {env_base}")
            return Path(env_base)
            
        if 'google.colab' in sys.modules:
            logging.info("☁️ Deteksi Google Colab: Mengarahkan ke Google Drive.")
            return Path('/content/drive/MyDrive/HSUAICLIP_Workspace')
            
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent
            
        # Fallback: relative to this file
        return Path(__file__).parent.parent.resolve()

    def _setup_paths(self) -> SimpleNamespace:
        """
        Mengkonfigurasi semua path yang dibutuhkan aplikasi.
        """
        BASE_DIR = self._get_base_path()

        # 2. Struktur Folder Utama
        folder_structure = {
            "TEMP_DIR": BASE_DIR / "Temp",
            "FONTS_DIR": BASE_DIR / "fonts",
            "FILE_DIR": BASE_DIR / "files",
            "MODELS_DIR": BASE_DIR / "models",
            "BIN_DIR": BASE_DIR / "bin",
        }

        # 3. Sub-folder (Workspace)
        sub_folders = {
            "WHISPERMODELS_DIR": folder_structure["MODELS_DIR"] / "whispermodels",
            "MEDIAPIPE_DIR": folder_structure["MODELS_DIR"] / "mpmodels",
        }

        # 4. Definisi File Spesifik
        all_dirs = {**folder_structure, **sub_folders}
        files = {
            "FACE_LANDMARKER_FILE": all_dirs["MEDIAPIPE_DIR"] / "face_landmarker.task",
            "ENV_FILE": all_dirs["FILE_DIR"] / ".env",
            "PROMPT_FILE": BASE_DIR / "clipper" / "_files" / "gemini_prompt.txt",
            "LOG_FILE": all_dirs["TEMP_DIR"] / "debug.log",
            "COOKIE_FILE": all_dirs["FILE_DIR"] / "cookies.txt",
        }

        return SimpleNamespace(BASE_DIR=BASE_DIR, **folder_structure, **sub_folders, **files, _dirs_map=all_dirs)

    def _create_folder_structure(self):
        """Membuat folder fisik berdasarkan konfigurasi path."""
        for p_name, p_path in self.paths._dirs_map.items():
            if not p_path.exists():
                logging.debug(f"📁 Folder {p_name} dibuat.")
                p_path.mkdir(parents=True, exist_ok=True)

    def _register_bin_to_path(self):
        """Menambahkan folder bin lokal dan path Colab ke PATH environment."""
        # 1. Add local bin directory
        bin_dir = str(self.paths.BIN_DIR.resolve())
        if bin_dir not in os.environ["PATH"]:
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]
            logging.debug(f"🔗 Menambahkan {bin_dir} ke System PATH.")

        # 2. Add Colab-specific Deno path if in Colab environment
        if 'google.colab' in sys.modules:
            colab_deno_path = "/root/.deno/bin"
            if Path(colab_deno_path).exists() and colab_deno_path not in os.environ["PATH"]:
                os.environ["PATH"] = colab_deno_path + os.pathsep + os.environ["PATH"]
                logging.debug(f"🔗 Menambahkan path Deno Colab: {colab_deno_path}")

    def _setup_logging(self):
        """Mengaktifkan logging ke file debug.log dan konsol (INFO+)."""
        # 1. Pastikan folder log ada
        self.paths.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # 2. Reset Root Logger (PENTING: Hapus konfigurasi lama/bawaan)
        logger = logging.getLogger()
        if logger.hasHandlers():
            logger.handlers.clear()
            
        # Ubah ke DEBUG agar Root Logger mengizinkan semua pesan lewat ke Handler
        logger.setLevel(logging.DEBUG)

        # 3. File Handler: Catat SEMUA (Info, Warning, Error) ke file
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        file_handler = logging.FileHandler(self.paths.LOG_FILE, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # 4. Console Handler: Tampilkan INFO+ ke layar (UI Utama)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(console_handler)

        # 5. Bungkam Log Library Eksternal yang Berisik (HTTP Requests, dll)
        for lib in ['urllib3', 'google','google_genai.models', 'httpx', 'httpcore', 'requests']:
            logging.getLogger(lib).setLevel(logging.WARNING)

    def verify_assets(self):
        """Memastikan semua aset eksternal (model) tersedia."""
        if ProjectCore._assets_verified:
            return

        self._verify_mediapipe_files(self.paths.FACE_LANDMARKER_FILE)
        self._verify_binaries()
        
        ProjectCore._assets_verified = True

    def _verify_mediapipe_files(self, path: Path) -> None:
        """Verifikasi file krusial dan unduh jika tidak ada."""
        if not path.exists():
            logging.warning(f"⚠️ Model MediaPipe tidak ditemukan di {path}")
            try:
                logging.info("📥 Mengunduh model face landmarker (sekitar 5-10MB)...")
                urllib.request.urlretrieve(self.MP_MODEL_URL, path)
                logging.info("✅ Unduhan berhasil.")
            except Exception as e:
                logging.error(f"❌ Gagal mengunduh model: {e}")
                sys.exit(1)

    def _verify_binaries(self):
        """Memastikan FFmpeg dan Deno terinstall secara manual."""
        required_tools = ["ffmpeg", "ffprobe", "deno"]
        missing = []
        
        for tool in required_tools:
            # Cek tool (misal: ffmpeg) atau tool.exe untuk Windows
            if not self.find_executable(tool) and not self.find_executable(tool + ".exe"):
                missing.append(tool)
        
        if missing:
            logging.error(f"❌ Tool berikut tidak ditemukan di PATH atau folder bin/: {', '.join(missing)}")
            logging.error("   ⚠️  Aplikasi ini TIDAK mengunduh dependensi secara otomatis demi keamanan.")
            logging.error("   👉  Silakan baca README.md untuk panduan instalasi manual.")
            sys.exit(1)

    @staticmethod
    def find_executable(name: str) -> Any: # Menggunakan Any atau Optional[str]
        """Mencari file eksekusi di direktori root proyek atau di PATH sistem."""
        # 1. Cek Root Project
        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).parent
        else:
            # File ada di clipper/core.py, jadi naik 2 level untuk ke Root (HSUAICLIP)
            base_path = Path(__file__).parent.parent.resolve()
            
        local_path = base_path / name
        if local_path.exists() and local_path.is_file():
            return str(local_path)
        
        # 2. Cek folder bin (Standar baru)
        bin_path = base_path / "bin" / name
        if bin_path.exists() and bin_path.is_file():
            return str(bin_path)

        # 3. Cek PATH Sistem
        
        return shutil.which(name)