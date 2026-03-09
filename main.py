import os
import argparse
import sys
from dotenv import load_dotenv

# Config & UI
from src.config.settings import AppConfig
from src.infrastructure.cli_ui import ConsoleUI
from src.infrastructure.common.logger import setup_logging
from src.container import Container

def setup_environment(config: AppConfig):
    """
    Mempersiapkan lingkungan eksekusi dengan membuat semua folder yang diperlukan.
    """
    config.paths.create_dirs()

def main():
    # Setup Argument Parser
    parser = argparse.ArgumentParser(description="HSU AI Clipper - Automated Video Shorts Generator")
    parser.add_argument("url", nargs="?", help="URL Video YouTube yang akan memproses")
    parser.add_argument("--extract-cookies", action="store_true", help="Ekstrak cookies dari browser lokal")
    args = parser.parse_args()

    config = AppConfig()
    setup_environment(config)
    setup_logging(config.paths.LOG_FILE)
    
    ui = ConsoleUI()
    ui.print_banner()

    # Handle Command: Extract Cookies
    if args.extract_cookies:
        from src.infrastructure.adapters.youtube_adapter import YouTubeAdapter
        print("🍪 Memulai ekstraksi cookies...")
        if YouTubeAdapter.extract_cookies_from_browser(config.paths.COOKIE_FILE):
             print(f"✅ Cookies tersimpan di: {config.paths.COOKIE_FILE}")
        else:
             print("❌ Gagal mengekstrak cookies. Pastikan browser tertutup atau login YouTube.")
        return

    load_dotenv(config.paths.ENV_FILE)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        api_key = ui.get_api_key()
        with open(config.paths.ENV_FILE, "w") as f:
            f.write(f"GEMINI_API_KEY={api_key}")

    try:
        # Inisialisasi via Container
        container = Container(config, ui, api_key)
        
        # Gunakan URL dari argumen jika ada, jika tidak tanya user
        if args.url:
            url = args.url
        else:
            url = ui.get_video_url()
            
        container.orchestrator.run(url)

    except KeyboardInterrupt:
        print("\n👋 Dibatalkan pengguna.")

if __name__ == "__main__":
    main()