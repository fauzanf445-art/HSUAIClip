import json
import urllib.request
import logging
from pathlib import Path
from typing import Optional, Dict, Any, cast, Union

import yt_dlp
from yt_dlp.utils import download_range_func

class Downloader:
    def __init__(self, url: str, cookies_path: Optional[Union[str, Path]] = None, download_progress_hook: Optional[Any] = None, video_info: Optional[Dict[str, Any]] = None):
        
        self.url = url
        self.cookies_path = cookies_path
        self.video_info = video_info
        self.download_progress_hook = download_progress_hook
    
    @staticmethod
    def check_and_setup_cookies(cookies_path: Union[str, Path]) -> Optional[Path]:
        """
        Mengecek dan membantu pengguna membuat file cookies jika diperlukan.
        Mencoba mengambil cookies dari berbagai browser secara otomatis.
        """        
        path_obj = Path(cookies_path)
        if path_obj.exists():
            logging.debug(f"✅ File cookies ditemukan di: {path_obj}")
            return path_obj

        supported_browsers = ["chrome", "firefox", "edge", "opera", "brave"]
        
        for browser in supported_browsers:
            opts: Any= {
                'cookiesfrombrowser': (browser,),
                'cookiefile': str(path_obj),
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
            }
            
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.extract_info("https://www.youtube.com", download=False)
                
                if path_obj.exists():
                    logging.info(f"✅ File cookies berhasil dibuat dari {browser}: {path_obj}")
                    return path_obj
            except Exception as e:
                logging.error(f"❌ Gagal mengambil cookies dari {browser}: {e}")
                continue
        
        return None
        
    def get_info(self) -> Optional[Dict[str, Any]]:
        """
        Mengambil metadata.
        """
        if self.video_info:
            return self.video_info

        opts : Any = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'cookiefile': self.cookies_path,
            'socket_timeout': 30,
            'retries': 10,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                raw = ydl.extract_info(self.url, download=False)

                info = cast(Dict[str, Any], raw)

                self.video_info = info
                return info
        except Exception as e:
            logging.error(f"Extractor error: {e}")
            return None

    def get_folder_name(self) -> str:
        info = self.get_info()
        if not info: return "Unknown_Folder"
        
        channel = info.get('uploader', 'UnknownChannel')
        title = info.get('title', 'UnknownTitle')
        video_id = info.get('id', 'UnknownID')
        
        # Batasi panjang channel dan title agar folder tidak terlalu panjang
        if len(channel) > 20: channel = channel[:20]
        if len(title) > 30: title = title[:30]
        
        raw_name = f"{channel}-{title}[{video_id}]"
        return "".join([c for c in raw_name if c.isalnum() or c in (' ', '-', '_', '[', ']')]).strip()

    def _parse_subtitle_json(self, target_url: str) -> Optional[str]:
        """Helper untuk mengunduh dan memparsing JSON3 subtitle."""
        try:
            req = urllib.request.Request(target_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
            
            full_text : list[str] = []
            for event in data.get('events', []):
                segs = event.get('segs')
                if segs:
                    text = "".join([s.get('utf8', '') for s in segs]).strip()
                    start_sec = event.get('tStartMs', 0) / 1000.0
                    if text:
                        full_text.append(f"[{start_sec:.2f}] {text}")
            
            return "\n".join(full_text)
        except Exception as e:
            logging.error(f"Error parsing subtitle: {e}")
            return None

    def _extract_transcript_from_cache(self) -> Optional[str]:
        """Mencoba mengambil URL subtitle dari cached video_info."""
        if not self.video_info: return None
        
        # Prioritas bahasa
        langs = ['id', 'en']
        
        # Cek manual subtitles dan automatic captions
        sources = [
            self.video_info.get('subtitles', {}),
            self.video_info.get('automatic_captions', {})
        ]

        target_url = None
        
        # Cari format json3 yang sesuai
        for source in sources:
            if not source: continue
            # Cek berdasarkan prioritas bahasa
            for lang in langs:
                if lang in source:
                    for fmt in source[lang]:
                        if fmt.get('ext') == 'json3':
                            target_url = fmt.get('url')
                            break
                if target_url: break
            
            # Jika belum ketemu, ambil bahasa apa saja yang punya json3
            if not target_url:
                for lang, formats in source.items():
                    for fmt in formats:
                        if fmt.get('ext') == 'json3':
                            target_url = fmt.get('url')
                            break
                    if target_url: break
            
            if target_url: break

        if target_url:
            logging.debug("♻️ Menggunakan metadata cache untuk transkrip.")
            return self._parse_subtitle_json(target_url)
            
        return None

    def download_transcript(self) -> Optional[str]:
        """Mengunduh teks transkrip dari video (mengembalikan string)."""
        # 1. Coba ambil dari cache info jika ada
        transcript_text = None
        if self.video_info:
            transcript_text = self._extract_transcript_from_cache()

        # 2. Jika tidak ada di cache, lakukan request baru (Fallback)
        if not transcript_text:
            opts: Any = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'cookiefile': self.cookies_path,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['id', 'en', '.*'],
                'subtitlesformat': 'json3',
                'socket_timeout': 30,
                'retries': 10,
            }
            
            info = None
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(self.url, download=False)
            except Exception as e:
                logging.error(f"Gagal mengambil info transkrip: {e}")
            
            if info:
                requested_subs = info.get('requested_subtitles')
                if requested_subs:
                    # Ambil bahasa pertama yang lolos seleksi yt-dlp
                    lang_code = list(requested_subs.keys())[0]
                    target_url = requested_subs[lang_code].get('url')
                    if target_url:
                        transcript_text = self._parse_subtitle_json(target_url)
                else:
                    logging.warning("Transkrip tidak ditemukan via yt-dlp request.")

        return transcript_text
    
    def download_raw_audio(self, output_dir: Path) -> Optional[Path]:
        """
        Mengunduh audio mentah (tanpa konversi).
        Returns: Path file yang diunduh (misal .webm atau .m4a)
        """

        # 1. Konfigurasi Dasar
        outtmpl = str(output_dir / "raw_audio.%(ext)s")
        cookies_path = self.cookies_path if self.cookies_path else None
        opts: Any = {
            'format': 'bestaudio/best',
            'outtmpl': outtmpl,
            'cookiefile': cookies_path,
            'quiet': True,
            'no_warnings': True,
            'no_progress': True,
            'progress_hooks': [self.download_progress_hook] if self.download_progress_hook else [],
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'windowsfilenames': True,
            'concurrent_fragment_downloads': 4,
            'http_chunk_size': 10485760, # 10MB
            'console_title': False,
        }

        logging.info("⏳ Mengunduh audio mentah...")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # download=True mengembalikan list dict info jika berhasil
                info = ydl.extract_info(self.url, download=True)
                
                if 'requested_downloads' in info:
                    filepath = info['requested_downloads'][0]['filepath']
                    return Path(filepath)
                
                # Fallback jika struktur info berbeda
                return Path(ydl.prepare_filename(info))
                
        except Exception as e:
            logging.error(f"❌ Gagal download audio: {e}")
        
        return None


    def download_single_clip(self, task: Dict[str, Any]) -> Optional[Path]:
        """
        Mengunduh satu potongan klip spesifik menggunakan fitur download_ranges yt-dlp.

        Args:
            task: Dictionary yang berisi 'clip_info' dan 'output_path'.

        Returns:
            Path ke file yang dibuat jika berhasil, jika tidak None.

        """
        
        clip = task['clip_info']
        filepath = task['output_path']
        start = clip['start_time']
        end = clip['end_time']
        title = clip['title']

        cookies_path = self.cookies_path if self.cookies_path else None

        filepath.parent.mkdir(parents=True, exist_ok=True)

        opts: Any =  {
            # 1. Konfigurasi Dasar
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': str(filepath),
            'download_ranges': download_range_func([title], [(start, end)]),
            'force_keyframes_at_cuts': True,
            'quiet': True,
            'no_warnings': True,
            'verbose': False,
            'cookiefile': cookies_path,
            'progress_hooks': [self.download_progress_hook] if self.download_progress_hook else [],
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'windowsfilenames': True,
            'concurrent_fragment_downloads': 4,
            'http_chunk_size': 10485760, # 10MB

        }
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                # Gunakan extract_info(download=True) untuk mendapatkan path file final
                info = ydl.extract_info(self.url, download=True)
                
                downloaded_path_str = None
                if 'requested_downloads' in info and info.get('requested_downloads'):
                    downloaded_path_str = info['requested_downloads'][0]['filepath']
                else:
                    # Fallback jika 'requested_downloads' tidak ada
                    downloaded_path_str = ydl.prepare_filename(info)

                if downloaded_path_str:
                    downloaded_path = Path(downloaded_path_str)
                    if downloaded_path.exists() and downloaded_path.stat().st_size > 100:
                        logging.info(f"   ✅ Selesai disimpan: {downloaded_path.name}")
                        return downloaded_path
        except Exception as e:
                logging.error(f"   ❌ Gagal mengunduh '{title}': {e}")
        
        logging.warning(f"   ⚠️ File unduhan tidak ditemukan atau kosong untuk klip '{title}'.")
        return None