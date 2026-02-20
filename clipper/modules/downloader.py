import json
import urllib.request
import logging
from pathlib import Path
from typing import Optional, Dict, Any, cast, Union

import yt_dlp

class Downloader:
    def __init__(self, url: str, cookies_path: Optional[Union[str, Path]] = None, video_info: Optional[Dict[str, Any]] = None):
        
        self.url = url
        self.cookies_path = cookies_path
        self.video_info = video_info
    
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
            opts: Any = {
                'cookiesfrombrowser': (browser,),
                'cookiefile': str(path_obj),
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
            }

            try:
                logging.debug(f"Mencoba mengambil cookies dari browser: {browser}...")
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.extract_info("https://www.youtube.com", download=False)
            except Exception as e:
                # This is an expected failure if browser not installed or no cookies found
                logging.debug(f"Gagal mengambil cookies dari {browser}: {e}")
                continue  # Try the next browser

            # If the above succeeded, check if the file was actually created and is not empty.
            if path_obj.exists() and path_obj.stat().st_size > 0:
                logging.info(f"✅ File cookies berhasil dibuat dari {browser}: {path_obj}")
                return path_obj  # Success! Stop checking and return the path.
        
        logging.warning("⚠️ Tidak dapat membuat file cookies dari browser manapun.")
        return None
        
    def _get_base_opts(self) -> Dict[str, Any]:
        """Mengembalikan konfigurasi dasar yt-dlp (Timeout, Retry, Cookies)."""
        opts: Dict[str, Any] = {
            'quiet': True,
            'no_warnings': False,
            'socket_timeout': 30,
            'retries': 10,
        }
        
        if self.cookies_path:
            path_obj = Path(self.cookies_path)
            if path_obj.exists():
                opts['cookiefile'] = str(path_obj)
        
        return opts

    def get_info(self) -> Optional[Dict[str, Any]]:
        """
        Mengambil metadata.
        """
        if self.video_info:
            return self.video_info

        opts = self._get_base_opts()
        opts['skip_download'] = True

        try:
            with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
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
        langs = ["id", "en"]
        
        # Cek manual subtitles dan automatic captions
        subtitles = self.video_info.get("subtitles", {})
        automatic_captions = self.video_info.get("automatic_captions", {})
        
        # Gabungkan dan iterasi semua sources (subtitles + automatic_captions)
        all_sources = subtitles, automatic_captions
        
        # Buat generator expression untuk mencari URL json3
        target_url = next((
            fmt.get('url')
            for source in all_sources if source
            # Buat daftar pencarian bahasa yang unik dan terurut untuk menghindari pengecekan ganda.
            for lang in dict.fromkeys(langs + list(source.keys()))
            if lang in source
            for fmt in source[lang]
            if fmt.get('ext') == 'json3' and fmt.get('url')
        ), None)

        if target_url:
            logging.debug("♻️ Menggunakan metadata cache untuk transkrip.")
            return self._parse_subtitle_json(target_url)

        return None

    def download_transcript(self) -> Optional[str]:
        """Mengunduh teks transkrip dari video (mengembalikan string)."""
        # 1. Coba ambil dari cache info jika ada
        if self.video_info:
            transcript_text = self._extract_transcript_from_cache()
            if transcript_text:
                return transcript_text

        # 2. Jika tidak ada di cache, lakukan request baru (Fallback)
        logging.info("Transkrip tidak ditemukan di cache. Mengunduh via yt-dlp...")
        opts = self._get_base_opts()
        opts.update({
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['id', 'en', '.*'],  # Prioritas: id, en, lalu apa saja
            'subtitlesformat': 'json3',
        })
        
        info = None
        try:
            with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                info = ydl.extract_info(self.url, download=False)
        except Exception as e:
            logging.error(f"Gagal mengambil info transkrip: {e}")
            return None
        
        if not info or not (requested_subs := info.get('requested_subtitles')):
            logging.warning("Transkrip tidak ditemukan via yt-dlp request.")
            return None

        # Refactored Logic: Prioritaskan 'id', lalu 'en', lalu fallback.
        target_url = None
        priority_langs = ['id', 'en']

        for lang in priority_langs:
            if lang in requested_subs:
                target_url = requested_subs[lang].get('url')
                logging.debug(f"Memilih transkrip Bahasa: {lang}")
                break
        
        if not target_url:
            first_lang_key = next(iter(requested_subs))
            target_url = requested_subs[first_lang_key].get('url')
            logging.debug(f"Memilih transkrip fallback: {first_lang_key}")

        return self._parse_subtitle_json(target_url) if target_url else None
    
    def get_stream_urls(self, clip_title: str) -> Optional[tuple[Optional[str], Optional[str]]]:
        """
        Tahap Inisiasi: Mengambil URL stream video dan audio.
        Memprioritaskan cache, lalu jatuh kembali ke permintaan jaringan jika perlu.
        Mengembalikan tuple (video_url, audio_url) atau None jika gagal.
        """
        info_to_parse: Optional[Dict[str, Any]] = None

        # Tahap 1: Tentukan sumber informasi (cache atau network)
        if self.video_info:
            # Cek apakah cache sudah berisi informasi stream yang memadai
            has_url = 'url' in self.video_info and self.video_info['url']
            has_formats = 'requested_formats' in self.video_info
            if has_url or has_formats:
                logging.debug(f"♻️ Menggunakan metadata cache untuk URL stream '{clip_title}'...")
                info_to_parse = self.video_info

        # Jika cache tidak cukup, ambil dari network
        if not info_to_parse:
            try:
                logging.warning(f"⚠️ Cache URL tidak memadai untuk '{clip_title}'. Mengambil dari network...")
                opts = self._get_base_opts()
                opts['format'] = 'bestvideo+bestaudio/best'
                with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                    info_to_parse = cast(Dict[str, Any], ydl.extract_info(self.url, download=False))
            except Exception as e:
                logging.error(f"Gagal mengambil info stream untuk klip '{clip_title}': {e}")
                return None

        if not info_to_parse:
            logging.error(f"Tidak ada informasi video yang bisa diproses untuk '{clip_title}'.")
            return None

        # Tahap 2: Parsing informasi yang sudah didapat (dari cache atau network)
        # Prioritaskan format terpisah (kualitas terbaik)
        if 'requested_formats' in info_to_parse:
            formats = info_to_parse['requested_formats']
            video_format = next((f for f in formats if f.get('vcodec') != 'none' and f.get('url')), None)
            audio_format = next((f for f in formats if f.get('acodec') != 'none' and f.get('url')), None)
            if video_format:
                return video_format.get('url'), audio_format.get('url') if audio_format else None

        # Fallback ke URL tunggal jika format terpisah tidak ada
        if info_to_parse.get('url'):
            return info_to_parse['url'], None

        logging.error(f"Gagal menemukan URL stream yang valid di dalam metadata untuk '{clip_title}'.")
        return None
