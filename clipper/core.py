import logging
import os
import sys
import urllib.request
import zipfile
import io
import shutil
import tarfile
import stat
import subprocess

from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Any

class ProjectCore:
    """
    Kelas inti untuk mengelola konfigurasi jalur dan pengaturan proyek.
    """
    MP_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

    DEPENDENCIES = {
        "win32": [
            {
                "name": "FFmpeg",
                "target_filename": "ffmpeg.exe",
                "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
                "archive_path": "bin/ffmpeg.exe",
            },
            {
                "name": "FFprobe",
                "target_filename": "ffprobe.exe",
                "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
                "archive_path": "bin/ffprobe.exe",
            },
            {
                "name": "Deno",
                "target_filename": "deno.exe",
                "url": "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
                "archive_path": "deno.exe",
            }
        ]
    }

    _assets_verified = False

    def __init__(self):
        self.paths = self._setup_paths()        
        self._setup_logging()
        self._create_folder_structure()
        self._register_bin_to_path()
        
        logging.debug("🚀 ProjectCore: Infrastruktur siap digunakan.")

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
            "PROMPT_FILE": all_dirs["FILE_DIR"] / "gemini_prompt.txt",
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
        """Menambahkan folder bin lokal ke PATH environment sementara."""
        bin_dir = str(self.paths.BIN_DIR.resolve())
        if bin_dir not in os.environ["PATH"]:
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]
            logging.debug(f"🔗 Menambahkan {bin_dir} ke System PATH.")

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
        for lib in ['urllib3', 'google','google_genai.models', 'httpx', 'httpcore', 'requests','yt-dlp']:
            logging.getLogger(lib).setLevel(logging.DEBUG)


    def verify_assets(self):
        """Memastikan semua aset eksternal (model) tersedia."""
        if ProjectCore._assets_verified:
            return

        self._verify_mediapipe_files(self.paths.FACE_LANDMARKER_FILE)
        self._verify_dependencies()
        
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

    def _verify_dependencies(self):
        """Memeriksa dan mengunduh file eksekusi yang dibutuhkan seperti FFmpeg dan Deno."""
        sys_platform = sys.platform

        # 1. Khusus Linux/Mac: Install FFmpeg via PIP (static-ffmpeg)
        if sys_platform in ["linux", "darwin"]:
            if not (self.find_executable("ffmpeg") and self.find_executable("ffprobe")):
                logging.info("📥 FFmpeg tidak ditemukan. Menginstall via pip (static-ffmpeg)...")
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "static-ffmpeg"])
                    import static_ffmpeg # type: ignore
                    static_ffmpeg.add_paths()  # type: ignore
                    logging.info("✅ FFmpeg & FFprobe berhasil diinstall via pip.")
                except Exception as e:
                    logging.error(f"❌ Gagal menginstall static-ffmpeg: {e}")

            # 2. Install Deno via Shell Script (Official)
            self._install_deno()

        # 2. Dependensi Lain (Deno, atau FFmpeg Windows)
        if sys_platform in self.DEPENDENCIES:
            for dep in self.DEPENDENCIES[sys_platform]:
                # Copy agar tidak mengubah atribut class secara permanen
                current_dep = dep.copy()

                self._download_and_setup_tool(current_dep)

    def _install_deno(self):
        """Instalasi Deno via shell script."""
        if sys.platform in ["linux", "darwin"]:
            # 2. Install Deno via Shell Script (Official)
            deno_installed = self.find_executable("deno")

            if not deno_installed:
                logging.info("📥 Deno tidak ditemukan. Menginstall via script official (curl | sh)...")
                try:
                    subprocess.run("curl -fsSL https://deno.land/install.sh | sh", shell=True, check=True, capture_output=True)

                    # Lokasi default installasi Deno (~/.deno/bin/deno)
                    deno_home_bin = Path.home() / ".deno" / "bin" / "deno"
                    target_link = self.paths.BASE_DIR / "deno"

                    if deno_home_bin.exists():
                        self._create_symlink_or_copy(deno_home_bin, target_link)
                    else:
                        logging.warning("⚠️ Deno terinstall tapi tidak ditemukan di ~/.deno/bin")
                except Exception as e:
                    logging.error(f"❌ Gagal menginstall Deno via script: {e}")

    def _create_symlink_or_copy(self, deno_home_bin: Path, target_link: Path):
        """Membuat symlink atau menyalin file, lalu mengatur permission execute."""
        
        if not target_link.exists():
            # Buat symlink/copy ke root project agar find_executable menemukannya
            try:
                os.symlink(deno_home_bin, target_link)
            except OSError:
                shutil.copy2(deno_home_bin, target_link)
            
            st = os.stat(target_link)
            os.chmod(target_link, st.st_mode | stat.S_IEXEC)
            logging.info(f"✅ Deno berhasil di-link ke: {target_link}")
        return target_link

    def _extract_archive(self, data: bytes, url: str, archive_path_suffix: str, target_path: Path):
        """Mengekstrak file spesifik dari arsip ZIP atau TAR."""
        file_obj = io.BytesIO(data)
        
        if url.endswith(".zip"):
            with zipfile.ZipFile(file_obj) as z:
                member = next((m for m in z.namelist() if m.endswith(archive_path_suffix)), None)
                if not member:
                    raise FileNotFoundError(f"'{archive_path_suffix}' tidak ditemukan dalam ZIP.")
                with z.open(member) as source, open(target_path, "wb") as dest:
                    shutil.copyfileobj(source, dest)
                    
        elif url.endswith(".tar.xz") or url.endswith(".tar.gz"):
            with tarfile.open(fileobj=file_obj, mode="r:*") as t:
                member = next((m for m in t.getmembers() if m.name.endswith(archive_path_suffix)), None)
                if not member:
                    raise FileNotFoundError(f"'{archive_path_suffix}' tidak ditemukan dalam TAR.")
                
                extracted_f = t.extractfile(member)
                if extracted_f:
                    with open(target_path, "wb") as dest:
                        shutil.copyfileobj(extracted_f, dest)

    def _download_and_setup_tool(self, dep_info: Dict[str, Any]) -> None:
        try:
            found_path = self.find_executable(str(dep_info["target_filename"]))
            
            if found_path:
                logging.debug(f"✅ Dependensi '{dep_info['name']}' ditemukan: {found_path}")
                return

            logging.warning(f"📥 Dependensi '{dep_info['name']}' tidak ditemukan. Memulai unduhan...")
            
            base_dir = self.paths.BIN_DIR
            target_path = base_dir / str(dep_info["target_filename"])
            url = dep_info["url"]
            archive_path_suffix = dep_info["archive_path"]

            with urllib.request.urlopen(url) as response:
                data = response.read()

            self._extract_archive(data, url, archive_path_suffix, target_path)
            
            if os.name != 'nt':
                st = os.stat(target_path)
                os.chmod(target_path, st.st_mode | stat.S_IEXEC)

            logging.info(f"✅ '{dep_info['name']}' berhasil di-setup di: {target_path.name}")
        except Exception as e:
            logging.error(f"❌ Gagal mengunduh/mengekstrak '{dep_info['name']}': {e}")
            logging.warning(f"⚠️ Gagal setup '{dep_info['name']}'. Harap install manual jika terjadi error.")

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