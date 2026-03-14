import logging

import logging.config
from pathlib import Path
from tqdm import tqdm

class TqdmLoggingHandler(logging.Handler):
    """
    Custom Logging Handler yang menggunakan tqdm.write() 
    agar output log tidak merusak tampilan progress bar yang sedang berjalan.
    """
    def emit(self, record: logging.LogRecord):
        try:
            # Ensure the message is a string before passing it to tqdm.write
            msg = self.format(record)
            tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)

def setup_logging(log_file: Path):
    # Pastikan folder logs ada
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging_config = {
        'version': 1,
        'disable_existing_loggers': True,  # Mencegah konflik dengan logger lain
        'formatters': {
            'file_format': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            },
            'console_format': {
                'format': '%(asctime)s - %(levelname)s - %(message)s',
                'datefmt': '%H:%M:%S'
            },
        },
        'handlers': {
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'file_format',
                'filename': log_file,
                'maxBytes': 5*1024*1024,
                'backupCount': 3,
                'encoding': 'utf-8',
                'level': logging.DEBUG,
            },
            'console': {
                'class': 'src.common.TqdmLoggingHandler',
                'formatter': 'console_format',
                'level': logging.INFO,
            },
        },
        'root': {
            'handlers': ['file', 'console'],
            'level': logging.DEBUG,
        },
        'loggers': {
            "googleapiclient": {"level": logging.WARNING, "propagate": False},
            "urllib3": {"level": logging.WARNING, "propagate": False},
            "absl": {"level": logging.WARNING, "propagate": False},
            "yt_dlp": {"level": logging.WARNING, "propagate": False},
            "httpx": {"level": logging.WARNING, "propagate": False},
            "httpcore": {"level": logging.WARNING, "propagate": False},
        }
    }

    logging.config.dictConfig(logging_config)
