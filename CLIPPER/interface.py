import logging
from pathlib import Path
from typing import Optional

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
        key = input("👉 Masukkan Gemini API Key: ").strip()
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
    def show_progress(step_name: str):
        print(f"\n🚀 Memulai: {step_name}...", end="", flush=True)

    @staticmethod
    def show_completion(summarize_dir: Path):
        summary_file = summarize_dir / "summary.json"
        if summary_file.exists() and summary_file.stat().st_size > 0:
            print(f"\n✨ Analisis Selesai! Hasil: {summary_file}")
        else:
            print(f"\n⚠️  Selesai, tapi file output tidak ditemukan.")

    @staticmethod
    def show_error(message: str, error: Exception):
        logging.error(f"{message}: {error}", exc_info=True)
        print(f"\n❌ {message}: {error}")
