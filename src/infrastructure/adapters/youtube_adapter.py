import json
import os
import urllib.request
import logging
from pathlib import Path
from typing import Optional, Dict, Any, cast, Union, Tuple

import yt_dlp
from tqdm import tqdm

from src.domain.interfaces import IMediaDownloader

class YouTubeAdapter(IMediaDownloader):
    """
    Implementasi IMediaDownloader menggunakan yt-dlp.
    Menangani interaksi dengan YouTube: Metadata, Stream URL, Audio Download, dan Cookies.
    """

    def __init__(self, cookies_path: Optional[Union[str, Path]] = None, deno_path: Optional[str] = None):
        self.cookies_path = cookies_path
        self.deno_path = deno_path
        # Cache sederhana untuk menyimpan info video per URL untuk menghindari request berulang
        self._info_cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def extract_cookies_from_browser(target_path: Path) -> bool:
        """
        Mencoba mengekstrak cookies dari browser yang didukung.
        """
        supported_browsers = ["chrome", "firefox", "edge", "opera", "brave"]
        
        for browser in supported_browsers:
            opts: Any = {
                'cookiesfrombrowser': (browser,),
                'cookiefile': str(target_path),
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
            }

            try:
                logging.debug(f"Mencoba mengambil cookies dari browser: {browser}...")
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.extract_info("https://www.youtube.com", download=False)
            except Exception as e:
                logging.debug(f"Gagal mengambil cookies dari {browser}: {e}")
                continue

            if target_path.exists() and target_path.stat().st_size > 0:
                logging.info(f"✅ File cookies berhasil dibuat dari {browser}: {target_path}")
                return True
        
        return False

    @staticmethod
    def check_and_setup_cookies(cookies_path: Union[str, Path]) -> Optional[Path]:
        """
        Mengecek dan membantu pengguna membuat file cookies jika diperlukan.
        """        
        path_obj = Path(cookies_path)
        if path_obj.exists() and path_obj.stat().st_size > 0:
            logging.debug(f"✅ File cookies ditemukan di: {path_obj}")
            return path_obj

        if env_cookies := os.getenv("YOUTUBE_COOKIES"):
            try:
                logging.info("🍪 Menemukan cookies dari Environment Variable. Menyimpan ke file...")
                path_obj.parent.mkdir(parents=True, exist_ok=True)
                path_obj.write_text(env_cookies, encoding='utf-8')
                return path_obj
            except Exception as e:
                logging.error(f"Gagal menyimpan cookies dari Env: {e}")

        if YouTubeAdapter.extract_cookies_from_browser(path_obj):
            return path_obj
        
        logging.warning("⚠️ Gagal mengekstrak cookies. YouTube mungkin memblokir akses (Sign-in Required).")
        return None

    def _get_base_opts(self) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            'quiet': True,
            'no_warnings': False,
            'socket_timeout': 30,
            'retries': 10,
            'remote_components': ['ejs:npm', 'ejs:github'],
        }
        if self.deno_path:
            opts['js_runtimes'] = {'deno': {'path': self.deno_path}}
        if self.cookies_path:
            path_obj = Path(self.cookies_path)
            if path_obj.exists():
                opts['cookiefile'] = str(path_obj)
        return opts

    def get_video_info(self, url: str) -> Dict[str, Any]:
        if url in self._info_cache:
            return self._info_cache[url]

        opts = self._get_base_opts()
        opts['skip_download'] = True

        try:
            with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    self._info_cache[url] = cast(Dict[str, Any], info)
                    return self._info_cache[url]
        except Exception as e:
            logging.error(f"Extractor error: {e}")
        
        return {}

    def get_stream_urls(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        info = self.get_video_info(url)
        if not info:
            return None, None

        # 1. Cek requested_formats (biasanya tersedia jika info baru diambil)
        if 'requested_formats' in info:
            formats = info['requested_formats']
            video_format = next((f for f in formats if f.get('vcodec') != 'none' and f.get('url')), None)
            audio_format = next((f for f in formats if f.get('acodec') != 'none' and f.get('url')), None)
            if video_format:
                return video_format.get('url'), audio_format.get('url') if audio_format else None

        # 2. Jika tidak ada di cache info, coba ambil ulang khusus stream
        try:
            opts = self._get_base_opts()
            opts['format'] = 'bestvideo+bestaudio/best'
            with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                # Kita tidak simpan ke cache utama karena ini mungkin format spesifik
                stream_info = ydl.extract_info(url, download=False)
                if stream_info and 'requested_formats' in stream_info:
                    formats = stream_info['requested_formats']
                    video_format = next((f for f in formats if f.get('vcodec') != 'none' and f.get('url')), None)
                    audio_format = next((f for f in formats if f.get('acodec') != 'none' and f.get('url')), None)
                    if video_format:
                        return video_format.get('url'), audio_format.get('url') if audio_format else None
                
                if stream_info:
                    direct_url = stream_info.get('url')
                    if direct_url:
                        return direct_url, None
        except Exception as e:
            logging.error(f"Gagal mengambil stream URL: {e}")

        return None, None

    def download_audio(self, url: str, output_dir: str, filename_prefix: str) -> Optional[str]:
        try:
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            
            out_tmpl = out_path / f"{filename_prefix}.%(ext)s"
            
            # TQDM Progress Hook untuk yt-dlp
            pbar = None
            def tqdm_hook(d):
                nonlocal pbar
                if d['status'] == 'downloading':
                    if pbar is None:
                        pbar = tqdm(total=d.get('total_bytes'), unit='B', unit_scale=True, desc=f"🎵 Download Audio ({filename_prefix})")
                    pbar.update(d.get('downloaded_bytes', 0) - pbar.n)
                elif d['status'] == 'finished':
                    if pbar:
                        pbar.update(pbar.total - pbar.n) # Pastikan bar mencapai 100%
                        pbar.close()

            opts = self._get_base_opts()
            opts.update({
                'format': 'bestaudio/best',
                'outtmpl': str(out_tmpl),
                'progress_hooks': [tqdm_hook],
            })

            with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                info = ydl.extract_info(url, download=True)
                if info and 'ext' in info:
                    final_path = out_path / f"{filename_prefix}.{info['ext']}"
                    if final_path.exists():
                        return str(final_path)
            
            # Fallback check
            for file_path in out_path.glob(f"{filename_prefix}.*"):
                if file_path.suffix not in ['.part', '.ytdl']:
                    return str(file_path)
                    
        except Exception as e:
            logging.error(f"❌ Gagal mengunduh audio: {e}")
        return None

    def _parse_subtitle_json(self, target_url: str) -> Optional[str]:
        try:
            req = urllib.request.Request(target_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
            
            full_text = []
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

    def get_transcript(self, url: str) -> Optional[str]:
        # 1. Cek Cache
        info = self.get_video_info(url)
        
        # 2. Setup Request jika belum ada info subtitle
        if not info.get('requested_subtitles'):
            opts = self._get_base_opts()
            opts.update({
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['id', 'en', '.*'],
                'subtitlesformat': 'json3/json',
            })
            try:
                with yt_dlp.YoutubeDL(cast(Any, opts)) as ydl:
                    info = ydl.extract_info(url, download=False) or {}
            except Exception:
                pass

        requested_subs = info.get('requested_subtitles', {})
        if not requested_subs:
            return None

        target_url = None
        for lang in ['id', 'en']:
            if lang in requested_subs:
                target_url = requested_subs[lang].get('url')
                break
        
        if not target_url and requested_subs:
            target_url = next(iter(requested_subs.values())).get('url')

        return self._parse_subtitle_json(target_url) if target_url else None