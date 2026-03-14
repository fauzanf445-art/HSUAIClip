import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

class JsonCache:
    """Utilitas untuk menangani cache data dalam format JSON."""
    @staticmethod
    def load(path: Path) -> Optional[Any]:
        if not path.exists():
            return None
        try:
            logging.debug(f"♻️ Memuat dari cache: {path.name}")
            return json.loads(path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, Exception) as e:
            logging.warning(f"⚠️ Cache korup atau tidak valid ({path.name}): {e}")
            return None

    @staticmethod
    def save(data: Any, path: Path) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            logging.debug(f"💾 Disimpan ke cache: {path.name}")
            return True
        except Exception as e:
            logging.error(f"❌ Gagal menyimpan cache ({path.name}): {e}")
            return False

def sanitize_filename(name: str) -> str:
    """Membersihkan string agar aman digunakan sebagai nama file/folder."""
    # Hapus semua karakter yang bukan alfanumerik, spasi, strip, atau underscore
    raw_safe = re.sub(r'[^\w\s\-_]', '', name).strip()
    # Ganti beberapa spasi atau karakter whitespace lainnya menjadi satu spasi tunggal
    return re.sub(r'\s+', ' ', raw_safe)