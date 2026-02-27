import logging
import getpass
from pathlib import Path
from typing import Optional, List

from utils.models import Clip

class ConsoleUI:
    """Menangani interaksi antarmuka pengguna berbasis konsol."""

    @staticmethod
    def print_banner():
        print("=== HSU AI CLIPPER ===")

    @staticmethod
    def print_api_key_help():
        print("\n⚠️  Konfigurasi API Key Diperlukan atau Key Lama Tidak Valid")
        print("   Dapatkan di: https://aistudio.google.com/app/apikey")

    @staticmethod
    def get_api_key_input() -> Optional[str]:
        key = getpass.getpass("👉 Masukkan Gemini API Key (Input tersembunyi): ").strip()
        if not key:
            print("❌ API Key wajib diisi.")
            return None
        return key

    @staticmethod
    def show_checking_key():
        print("⏳ Memeriksa kunci...", end="\r", flush=True)

    @staticmethod
    def show_key_status(is_valid: bool):
        if is_valid:
            print(f"✅ API Key valid dan disimpan!{' '*20}")
        else:
            print(f"❌ API Key tidak valid. Silakan coba lagi.{' '*20}")

    @staticmethod
    def get_user_url() -> Optional[str]:
        url = input("\n👉 Masukkan URL YouTube: ").strip()
        if not url:
            print("❌ URL wajib diisi.")
            return None
        
        if "youtube.com" not in url and "youtu.be" not in url:
            print("❌ URL tidak valid. Harap masukkan link YouTube yang benar.")
            return None
            
        return url

    @staticmethod
    def get_manual_timestamps() -> Optional[List[Clip]]:
        """Meminta input timestamp manual dari pengguna."""
        print("\n👉 (Opsional) Masukkan timestamp manual (detik).")
        print("   Format: start-end, start-end (Contoh: 60-90, 125.5-150)")
        
        while True:
            user_input = input("   [Kosongkan untuk analisis AI]: ").strip()
            
            if not user_input:
                return None
            
            clips: List[Clip] = []
            try:
                # Split berdasarkan koma
                parts = user_input.split(',')
                for part in parts:
                    if '-' not in part: continue
                    start_str, end_str = part.split('-')
                    start = float(start_str.strip())
                    end = float(end_str.strip())
                    
                    if start >= end:
                        print(f"⚠️  Timestamp tidak valid (Start >= End): {part}")
                        continue
                        
                    clips.append(Clip(
                        title=f"Manual Clip {len(clips)+1}",
                        start_time=start,
                        end_time=end,
                        duration=end - start,
                        description="Manual timestamp",
                        energy_score=0,
                        vocal_energy="Unknown",
                        audio_justification="Manual",
                        caption=""
                    ))
                
                if not clips:
                    print("❌ Tidak ada timestamp valid yang ditemukan. Silakan coba lagi.")
                    continue
                    
                return clips
                
            except ValueError:
                print("❌ Format salah. Harap gunakan angka dan tanda hubung (-). Silakan coba lagi.")
                continue

    @staticmethod
    def show_progress(step_name: str):
        print(f"\n🚀 Memulai: {step_name}...", end="", flush=True)

    @staticmethod
    def show_summary_completion(summary_dir: Path):
        """Menampilkan pesan setelah tahap analisis AI selesai."""
        summary_file = summary_dir / "summary.json"
        if summary_file.exists() and summary_file.stat().st_size > 0:
            print(f"\n✨ Analisis Selesai! Hasil disimpan di: {summary_file}")
        else:
            print(f"\n⚠️  Analisis selesai, tapi file summary.json tidak ditemukan atau kosong.")

    @staticmethod
    def show_clips_completion(clips: List[Path]):
        """Menampilkan pesan setelah semua klip berhasil dibuat."""
        if not clips:
            print("\n⚠️  Proses pembuatan klip selesai, namun tidak ada klip yang dihasilkan.")
            return
        
        print(f"\n✨ Selesai! {len(clips)} klip berhasil dibuat:")
        for path in clips:
            print(f"   🎬 {path.name}")
        
        if clips:
            print(f"\n📂 Folder Output: {clips[0].parent}")

    @staticmethod
    def show_error(message: str, error: Exception):
        logging.error(f"{message}: {error}", exc_info=True)
        print(f"\n❌ {message}: {error}")
