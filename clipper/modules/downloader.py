import yt_dlp
import json
import urllib.request
import logging
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, cast, List

class DownloaderSetup:
    def __init__(self, url: str, cookies_path: Optional[str] = None):
        self.url = url
        self.cookies_path = cookies_path
        self.video_info: Optional[Dict[str, Any]] = None
    
    @staticmethod
    def check_and_setup_cookies(cookies_path: Any) -> Optional[Path]:
        """
        Mengecek dan membantu pengguna membuat file cookies jika diperlukan.
        Mencoba mengambil cookies dari berbagai browser secara otomatis.
        """        
        path_obj = Path(cookies_path)
        if path_obj.exists():
            logging.info(f"✅ File cookies ditemukan di: {path_obj}")
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
        
    def _get_info(self) -> Optional[Dict[str, Any]]:
        """
        Mengambil metadata.
        """
        if self.video_info:
            return self.video_info

        opts : Any = {
            'quiet': False,
            'no_warnings': False,
            'skip_download': True,
            'cookiefile': self.cookies_path,
            'logger': logging.getLogger(__name__),
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
        info = self._get_info()
        if not info: return "Unknown_Folder"
        
        channel = info.get('uploader', 'UnknownChannel')
        title = info.get('title', 'UnknownTitle')
        video_id = info.get('id', 'UnknownID')
        
        raw_name = f"[{channel}] [{title}] [{video_id}]"
        return "".join([c for c in raw_name if c.isalnum() or c in (' ', '-', '_', '[', ']')]).strip()

    def get_info(self) -> Optional[Dict[str, Any]]:
        return self._get_info()
    
    

class Downloader:
    def __init__(self, url: str, output_dir: Any, cookies_path: Optional[str] = None, download_progress_hook: Optional[Any] = None, postprocessor_hooks: Optional[Any]= None,
        video_info: Optional[Dict[str, Any]] = None,ffmpeg_path: Optional[str] = None, ffmpeg_vd_args: Optional[List[str]] = None):
        
        self.url = url
        self.cookies_path = cookies_path
        self.output_dir = Path(output_dir)
        self.video_info = video_info
        self.progress_hook = download_progress_hook
        self.postprocessor_hooks = postprocessor_hooks
        self.ffmpeg_path = ffmpeg_path 
        self.ffmpeg_args = ffmpeg_vd_args

    def _parse_subtitle_json(self, target_url: str) -> Optional[str]:
        """Helper untuk mengunduh dan memparsing JSON3 subtitle."""
        try:
            req = urllib.request.Request(target_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
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
            logging.info("♻️ Menggunakan metadata cache untuk transkrip.")
            return self._parse_subtitle_json(target_url)
            
        return None

    def download_transcript(self) -> Optional[Path]:
        """Membuat file transkrip dari video."""
        transcript_path = Path(self.output_dir) / "transcript.txt"
        
        # 1. Coba ambil dari cache info jika ada
        transcript_text = None
        if self.video_info:
            transcript_text = self._extract_transcript_from_cache()

        # 2. Jika tidak ada di cache, lakukan request baru (Fallback)
        if not transcript_text:
            opts: Any = {
                'quiet': False,
                'no_warnings': False,
                'skip_download': True,
                'cookiefile': self.cookies_path,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['id', 'en', '.*'],
                'subtitlesformat': 'json3',
                'logger': logging.getLogger(__name__),
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

        if transcript_text:
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(transcript_text)
            logging.info(f"Transkrip disimpan di: {transcript_path}")
            return transcript_path
        return None

    def download_raw_audio(self) -> Optional[Path]:
        """
        Mengunduh audio dan langsung mengkonversinya ke MP3 menggunakan postprocessor.
        """
        # Pattern untuk file raw
        output_filename = "audio_raw"
        
        opts: Any = {
            'format': 'bestaudio/best',
            'outtmpl': f"{output_filename}.%(ext)s",
            'paths': {'home': str(self.output_dir)},
            'cookiefile': self.cookies_path,
            'quiet': False,       # Izinkan output log (agar terlihat saat FFmpeg bekerja)
            'noprogress': True,   # Matikan bar bawaan yt-dlp (gunakan punya kita saja)
            'no_warnings': True,
            'logger': logging.getLogger(__name__),
            'ffmpeg_location': self.ffmpeg_path,
            'progress_hooks': [self.progress_hook] if self.progress_hook else [],
            'postprocessor_hooks': [self.postprocessor_hooks] if self.postprocessor_hooks else [],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

        logging.info("⏳ Memulai download & konversi audio...")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
            
            # Karena kita force mp3, file hasil pasti berakhiran .mp3
            expected_path = self.output_dir / f"{output_filename}.mp3"
            
            if expected_path.exists():
                logging.info(f"✅ Audio berhasil diunduh: {expected_path.name}")
                return expected_path
                
        except Exception as e:
            logging.error(f"❌ Gagal download audio: {e}")
        
        return None

    def download_clips(self, clips_data: List[Dict[str, Any]]) -> List[Path]:
        """
        Mengunduh potongan klip spesifik berdasarkan data (biasanya dari summary.json).
        Menggunakan fitur download_ranges yt-dlp untuk efisiensi bandwidth (Batch Download).
        """

        if not clips_data:
            logging.warning("⚠️ Tidak ada data klip untuk diunduh.")
            return []
        
        clips_dir = self.output_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        
        # Gunakan folder temp untuk memastikan kita menangkap file yang benar
        temp_dl_dir = clips_dir / "temp_dl"
        if temp_dl_dir.exists():
            shutil.rmtree(temp_dl_dir)
        temp_dl_dir.mkdir(parents=True, exist_ok=True)

        # 1. Kumpulkan semua range waktu
        ranges: List[Dict[str, float]] = []
        for c in clips_data:
            # Dukung berbagai format key (start_time dari JSON atau start umum)
            start = c.get('start_time')
            if start is None:
                start = c.get('start')
            
            end = c.get('end_time')
            if end is None:
                end = c.get('end')

            if start is not None and end is not None:
                ranges.append({'start_time': float(start), 'end_time': float(end)})

        if not ranges:
            logging.warning("⚠️ Tidak ada timestamp valid dalam daftar klip.")
            return []

        logging.info(f"✂️ Mengunduh {len(ranges)} klip secara batch...")

        # 2. Konfigurasi yt-dlp dengan download_ranges
        # Argumen FFmpeg diambil dari self.ffmpeg_args yang disuntikkan dari engine
        if not self.ffmpeg_args:
            logging.error("❌ FFmpeg args tidak ditemukan. Proses download klip dibatalkan.")
            return []

        def download_ranges_callback(info: Dict[str, Any], ydl: Any) -> List[Dict[str, float]]:
            return ranges

        opts: Any = {
            'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
            'paths': {'home': str(temp_dl_dir)},
            'outtmpl': "clip_%(section_start)s-%(section_end)s.%(ext)s",
            'download_ranges': download_ranges_callback,
            'force_keyframes_at_cuts': True,
            'cookiefile': self.cookies_path,
            'quiet': False,       # Izinkan output log
            'noprogress': True,   # Matikan bar bawaan yt-dlp
            'no_warnings': True,
            'logger': logging.getLogger(__name__),
            'ffmpeg_location': self.ffmpeg_path,
            'progress_hooks': [self.progress_hook] if self.progress_hook else [],
            'postprocessor_hooks': [self.postprocessor_hooks] if self.postprocessor_hooks else [],
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mkv',
            }],
            'postprocessor_args': {
                'FFmpegVideoConvertor': self.ffmpeg_args,
            },
        }

        downloaded_files: List[Path] = []
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
            
            # 3. Pindahkan file dari temp ke folder tujuan
            for f in temp_dl_dir.iterdir():
                if f.is_file() and f.suffix in ['.mp4', '.mkv', '.webm']:
                    dst_path = clips_dir / f.name
                    # Overwrite jika ada
                    shutil.move(str(f), str(dst_path))
                    downloaded_files.append(dst_path)
                    logging.info(f"✅ Berhasil: {dst_path.name}")
            
            # Bersihkan temp
            shutil.rmtree(temp_dl_dir, ignore_errors=True)
            
        except Exception as e:
            logging.error(f"❌ Gagal melakukan batch download clips: {e}")

        return downloaded_files
