"""
src/infrastructure/logging/logging_config.py
Konfigurasi logging terpusat untuk HSUAIClip.
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tqdm import tqdm

class TqdmLoggingHandler(logging.Handler):
    """
    Custom Logging Handler yang menggunakan tqdm.write() 
    agar output log tidak merusak tampilan progress bar yang sedang berjalan.
    """
    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)

def setup_logging(log_file: Path, log_level=logging.INFO):
    """
    Mengonfigurasi root logger untuk menulis ke file dan konsol (via tqdm).
    """
    # Pastikan folder logs ada
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Formatters
    # File: Lengkap dengan timestamp, level, nama logger
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Console: Lebih ringkas untuk dibaca user
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')

    # 1. File Handler (Menyimpan semua log) dengan Rotasi
    # maxBytes=5*1024*1024 (5MB), backupCount=3 (simpan 3 file lama: app.log.1, app.log.2, dst)
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(log_level)

    # 2. Console Handler (Menampilkan ke layar via TQDM)
    console_handler = TqdmLoggingHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(log_level)

    # Konfigurasi Root Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Bersihkan handler lama (jika ada) untuk mencegah duplikasi
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Kurangi noise dari library eksternal
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("absl").setLevel(logging.WARNING)
