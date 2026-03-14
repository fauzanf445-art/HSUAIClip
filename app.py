import os
import argparse
import logging
from dotenv import load_dotenv
import gradio as gr

# Config & UI
from src.config import AppConfig
from src.infrastructure.cli_ui import ConsoleUI
from src.common import setup_logging
from src.container import Container

class GradioUI(ConsoleUI):
    """Antarmuka Gradio yang kompatibel dengan antarmuka ConsoleUI."""
    def __init__(self):
        self.log_output = ""

    def log(self, msg: str):
        logging.info(f"   -> {msg}")
        self.log_output += f"{msg}\n"

    def show_step(self, step_name: str):
        logging.info(f"🚀 [STEP] {step_name}...")
        self.log_output += f"\n--- {step_name.upper()} ---\n"

    def get_manual_clips(self):
        # Di mode Web, kita asumsikan default adalah AI Analysis 
        # kecuali ditambahkan input khusus di UI Gradio
        return None

def process_via_web(url, api_key):
    """Fungsi jembatan antara Gradio UI dan Orchestrator."""
    if not url:
        yield "Error: URL YouTube wajib diisi.", None
        return
    if not api_key:
        yield "Error: Gemini API Key wajib diisi.", None
        return

    config = AppConfig()
    # Pastikan direktori tersedia
    config.paths.create_dirs()
    setup_logging(config.paths.LOG_FILE)
    
    ui = GradioUI()
    # Patch ui.log untuk melakukan yield secara tidak langsung (opsional) atau update manual
    try:
        yield "🚀 Memulai inisialisasi...", None
        container = Container(config, ui, api_key)
        
        # Setup Cookies jika ada di environment
        container.yt_adapter.check_and_setup_cookies(config.paths.COOKIE_FILE)
        
        url = url.split('#')[0].strip()
        ui.log(f"Memproses URL: {url}")
        yield ui.log_output, None
        
        container.orchestrator.run(url)
        
        # Mencari file hasil di folder output
        safe_name = container.provider_service.get_video_metadata(url).get('title', 'Unknown_Video')
        output_folder = config.paths.OUTPUT_DIR / safe_name
        video_files = list(output_folder.glob("final_*.mp4"))
        
        ui.log("✅ Proses Selesai!")
        yield ui.log_output, [str(v) for v in video_files]
    except Exception as e:
        yield f"Error: {str(e)}", None

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
    parser.add_argument("--web", action="store_true", help="Jalankan antarmuka Gradio")
    args = parser.parse_args()

    config = AppConfig()

    # Deteksi apakah berjalan di Hugging Face atau user meminta mode web
    if os.getenv("SPACE_ID") or args.web:
        print("🌐 Memulai HSU AI Clipper dalam mode Web (Gradio)...")
        with gr.Blocks(title="HSU AI Clipper") as demo:
            gr.Markdown("# 🎬 HSU AI Clipper")
            gr.Markdown("Otomatis buat video shorts dari YouTube menggunakan AI.")
            
            with gr.Row():
                with gr.Column():
                    url_input = gr.Textbox(label="YouTube URL", placeholder="https://www.youtube.com/watch?v=...")
                    api_input = gr.Textbox(label="Gemini API Key", type="password", value=os.getenv("GEMINI_API_KEY", ""))
                    btn = gr.Button("🚀 Mulai Proses", variant="primary")
                
                with gr.Column():
                    log_display = gr.Textbox(label="Process Logs", interactive=False, lines=10)
                    video_output = gr.Gallery(label="Generated Clips")

            btn.click(
                fn=process_via_web,
                inputs=[url_input, api_input],
                outputs=[log_display, video_output]
            )

        is_huggingface = os.getenv("SPACE_ID") is not None
        server_name = "0.0.0.0" if is_huggingface else "127.0.0.1"

        demo.launch(server_name=server_name, server_port=7860)
        return

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
        
        # Setup Cookies agar yt-dlp tidak terkena bot-check
        container.yt_adapter.check_and_setup_cookies(config.paths.COOKIE_FILE)

        # Gunakan URL dari argumen jika ada, jika tidak tanya user
        if args.url:
            url = args.url
        else:
            url = ui.get_video_url()
        
        url = url.split('#')[0].strip()
        if not url:
            ui.show_error("URL menjadi kosong setelah sanitasi. Harap berikan URL video yang valid.")
            return
            
        container.orchestrator.run(url)

    except KeyboardInterrupt:
        print("\n👋 Dibatalkan pengguna.")

if __name__ == "__main__":
    main()