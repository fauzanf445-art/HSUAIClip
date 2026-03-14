import json
import logging
from pathlib import Path
from typing import Any, Optional

class JsonCache:
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